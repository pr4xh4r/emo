"""RAG Brain — ChromaDB + TinyLlama (100% offline).

Pipeline: FAQ cache → RAG context → TinyLlama.
Optimized for speed on Raspberry Pi 4GB.
"""
import os
import re
import time
import hashlib
import logging
import config

log = logging.getLogger("emo.brain")

try:
    import chromadb
    _CHROMA = True
except ImportError:
    _CHROMA = False
    log.warning("chromadb not installed")

try:
    import ollama as _ollama_pkg
    _OLLAMA = True
except ImportError:
    _OLLAMA = False
    log.warning("ollama not installed")

try:
    from pypdf import PdfReader
    _PDF = True
except ImportError:
    _PDF = False
    log.warning("pypdf not installed")


class Brain:
    def __init__(self, shared_state):
        self.shared = shared_state
        self.collection = None
        self.client = None
        self._faq = dict(config.FAQ_ANSWERS)

        if _CHROMA:
            config.CHROMA_DIR.mkdir(exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=str(config.CHROMA_DIR))
            self.collection = self.client.get_or_create_collection(
                name="emo_knowledge",
                metadata={"hnsw:space": "cosine"})
            n = self.collection.count()
            log.info(f"ChromaDB ready — {n} chunks")

        # warm up TinyLlama (loads model into RAM)
        if _OLLAMA:
            try:
                _ollama_pkg.generate(
                    model=config.OLLAMA_MODEL,
                    prompt="Hi",
                    options={"num_predict": 1}
                )
                log.info(f"TinyLlama warmed up ✓")
            except Exception as e:
                log.error(f"Ollama warmup failed: {e}")

    # ══════════════════════════════════════════
    # FAQ — instant answers (no LLM)
    # ══════════════════════════════════════════
    def add_faq(self, question, answer):
        key = question.lower().strip()
        self._faq[key] = answer
        log.info(f"FAQ added: '{key}'")

    def check_faq(self, question):
        q = question.lower().strip()
        if q in self._faq:
            return self._faq[q]
        for key, ans in self._faq.items():
            if key in q or q in key:
                return ans
        return None

    def list_faq(self):
        return list(self._faq.keys())

    # ══════════════════════════════════════════
    # Ingestion (PDF + text)
    # ══════════════════════════════════════════
    def ingest_pdf(self, filepath):
        if not _PDF or not self.collection:
            return 0
        try:
            reader = PdfReader(filepath)
        except Exception as e:
            log.error(f"Cannot read {filepath}: {e}")
            return 0
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        if not text.strip():
            return 0
        return self._store_chunks(text, os.path.basename(filepath))

    def ingest_text(self, text, source="telegram_input"):
        if not self.collection:
            return 0
        return self._store_chunks(text, source)

    def _store_chunks(self, text, source):
        chunks = self._chunk_text(text)
        if not chunks:
            return 0
        ids, docs, metas = [], [], []
        for i, chunk in enumerate(chunks):
            cid = hashlib.md5(f"{source}_{i}_{chunk[:50]}".encode()).hexdigest()
            ids.append(cid)
            docs.append(chunk)
            metas.append({"source": source, "chunk": i})
        self.collection.upsert(ids=ids, documents=docs, metadatas=metas)
        log.info(f"Ingested '{source}' → {len(chunks)} chunks")
        return len(chunks)

    def ingest_all(self):
        total = 0
        for f in config.DATA_DIR.glob("*.pdf"):
            total += self.ingest_pdf(str(f))
        if self.collection:
            log.info(f"Total: {self.collection.count()} chunks")
        return total

    def clear_knowledge(self):
        if self.client:
            self.client.delete_collection("emo_knowledge")
            self.collection = self.client.get_or_create_collection(
                name="emo_knowledge",
                metadata={"hnsw:space": "cosine"})
            log.info("Knowledge base cleared")

    def list_documents(self):
        if not self.collection or self.collection.count() == 0:
            return []
        results = self.collection.get(include=["metadatas"])
        sources = set()
        for m in results["metadatas"]:
            sources.add(m.get("source", "unknown"))
        return sorted(sources)

    # ══════════════════════════════════════════
    # Ask (FAQ → RAG → TinyLlama)
    # ══════════════════════════════════════════
    def ask(self, question):
        # 1. FAQ — instant
        faq = self.check_faq(question)
        if faq:
            log.info(f"FAQ hit: '{question[:40]}'")
            return faq

        if not _OLLAMA:
            return "Ollama is not running. Please start it."

        # 2. RAG context
        context = self._get_context(question)

        # 3. Build short prompt
        history = ""
        if self.shared.conversation:
            last = self.shared.conversation[-1]
            history = f"Previous: Q={last['q'][:50]} A={last['a'][:50]}\n"

        if context:
            prompt = (
                f"{config.SYSTEM_PROMPT}\n\n"
                f"Context:\n{context}\n\n"
                f"{history}"
                f"Question: {question}\n"
                f"Answer:"
            )
        else:
            prompt = (
                f"{config.SYSTEM_PROMPT}\n\n"
                f"{history}"
                f"Question: {question}\n"
                f"Answer:"
            )

        # 4. Generate
        return self._generate(prompt)

    def _get_context(self, question):
        if not self.collection or self.collection.count() == 0:
            return ""
        try:
            results = self.collection.query(
                query_texts=[question],
                n_results=config.RAG_TOP_K,
                include=["documents", "distances"]
            )
            if not results["documents"] or not results["documents"][0]:
                return ""
            # only use relevant chunks
            parts = []
            for doc, dist in zip(results["documents"][0],
                                 results["distances"][0]):
                if dist < 1.5:
                    parts.append(doc)
            return "\n".join(parts)
        except Exception:
            return ""

    def _generate(self, prompt):
        try:
            resp = _ollama_pkg.generate(
                model=config.OLLAMA_MODEL,
                prompt=prompt,
                options={
                    "temperature": config.LLM_TEMPERATURE,
                    "num_predict": config.LLM_MAX_TOKENS,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_ctx": 1024,   # smaller context = faster
                }
            )
            answer = resp["response"].strip()
            if answer:
                log.info(f"TinyLlama answered ✓")
                return self._clean(answer)
        except Exception as e:
            log.error(f"Ollama error: {e}")
        return "Sorry, I'm having trouble right now. Try again!"

    def _clean(self, text):
        # stop at any leaked "Question:" or role markers
        for marker in ["Question:", "Student:", "Human:", "User:"]:
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx]
        # remove markdown
        text = re.sub(r'\*+', '', text)
        text = re.sub(r'#+\s*', '', text)
        return text.strip()

    # ══════════════════════════════════════════
    # Chunking
    # ══════════════════════════════════════════
    def _chunk_text(self, text):
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        if not sentences:
            return [text[:config.CHUNK_SIZE]] if text.strip() else []
        chunks = []
        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(current) + len(s) + 1 < config.CHUNK_SIZE:
                current = (current + " " + s).strip()
            else:
                if current:
                    chunks.append(current)
                current = s
        if current:
            chunks.append(current)
        # overlap
        if len(chunks) > 1:
            overlapped = [chunks[0]]
            for i in range(1, len(chunks)):
                tail = chunks[i-1][-config.CHUNK_OVERLAP:]
                sp = tail.find(' ')
                if sp > 0:
                    tail = tail[sp+1:]
                overlapped.append(tail + " " + chunks[i])
            return overlapped
        return chunks if chunks else [text[:config.CHUNK_SIZE]]
