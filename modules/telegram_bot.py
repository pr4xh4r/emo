"""Telegram Bot — Full admin control center for EMO.

Production-ready with:
- All original commands preserved
- New: /text — ingest raw text into RAG
- New: /faq — add/list instant FAQ answers
- New: /log — view recent Q&A
- New: /photo — capture camera photo
- New: /shutdown — graceful shutdown
- New: /volume — set speaker volume
- Retry logic for Telegram conflicts
- Structured logging
"""
import os
import asyncio
import logging
import time as _time
import psutil
import config
from config import RobotState

log = logging.getLogger("emo.telegram")

try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        ContextTypes, filters
    )
    _TG = True
except ImportError:
    _TG = False
    log.warning("python-telegram-bot not installed")


def _is_admin(update: "Update") -> bool:
    if not config.ADMIN_CHAT_IDS:
        return True  # no restriction if no admin IDs set
    return update.effective_chat.id in config.ADMIN_CHAT_IDS


class TelegramBot:
    def __init__(self, shared_state):
        self.shared = shared_state
        self.app = None

    def start(self):
        if not _TG:
            log.error("Cannot start — library missing")
            return
        if config.TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            log.error("Set TELEGRAM_BOT_TOKEN in config.py first!")
            return
        import threading
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        # suppress noisy Telegram conflict warnings
        logging.getLogger("telegram.ext.Updater").setLevel(logging.CRITICAL)

        # force-clear old bot sessions via direct HTTP API
        try:
            import urllib.request
            url = (f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
                   f"/deleteWebhook?drop_pending_updates=true")
            urllib.request.urlopen(url, timeout=10)
            url2 = (f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
                    f"/getUpdates?offset=-1")
            urllib.request.urlopen(url2, timeout=10)
            log.info("Cleared old sessions")
        except Exception:
            pass

        # wait for any old polling to fully disconnect
        _time.sleep(5)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.app = Application.builder().token(
            config.TELEGRAM_BOT_TOKEN).build()

        # ── command handlers ──
        cmds = {
            "start": self._cmd_start,
            "help": self._cmd_start,
            "status": self._cmd_status,
            "ask": self._cmd_ask,
            "text": self._cmd_text,
            "faq": self._cmd_faq,
            "log": self._cmd_log,
            "forward": self._cmd_forward,
            "backward": self._cmd_backward,
            "left": self._cmd_left,
            "right": self._cmd_right,
            "stop": self._cmd_stop,
            "patrol": self._cmd_patrol,
            "speed": self._cmd_speed,
            "look": self._cmd_look,
            "say": self._cmd_say,
            "speak": self._cmd_speak,
            "volume": self._cmd_volume,
            "photo": self._cmd_photo,
            "ingest": self._cmd_ingest,
            "clear": self._cmd_clear,
            "docs": self._cmd_docs,
            "face": self._cmd_face,
            "reboot": self._cmd_reboot,
            "shutdown": self._cmd_shutdown,
        }
        for name, handler in cmds.items():
            self.app.add_handler(CommandHandler(name, handler))

        # PDF upload handler
        self.app.add_handler(
            MessageHandler(filters.Document.PDF, self._handle_pdf))

        log.info("Bot starting...")

        # manual async polling with retry
        async def _start():
            await self.app.initialize()
            await self.app.start()

            for attempt in range(5):
                try:
                    await self.app.updater.start_polling(
                        drop_pending_updates=True)
                    log.info("Bot running!")
                    break
                except Exception as e:
                    if "Conflict" in str(e) and attempt < 4:
                        wait = 3 * (attempt + 1)
                        log.warning(f"Conflict — retrying in {wait}s "
                                    f"(attempt {attempt+1}/5)")
                        await asyncio.sleep(wait)
                    else:
                        log.error(f"Failed to start: {e}")
                        return

            while self.shared.state != RobotState.SHUTDOWN:
                await asyncio.sleep(1)
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

        loop.run_until_complete(_start())

    # ═══════════════════════════════════════════
    # COMMANDS
    # ═══════════════════════════════════════════

    async def _cmd_start(self, update: Update,
                         ctx: ContextTypes.DEFAULT_TYPE):
        msg = (
            "🤖 *EMO Robot — Admin Panel*\n\n"
            "🧠 *AI / Brain*\n"
            "/ask `<question>` — Ask EMO\n"
            "/text `<content>` — Add text to knowledge\n"
            "/faq `<q> | <a>` — Add instant FAQ\n"
            "/faq — List all FAQs\n"
            "/ingest — Re-ingest all PDFs\n"
            "/clear — Clear knowledge base\n"
            "/docs — List loaded documents\n"
            "📄 Send PDF — auto-ingest\n\n"
            "🚗 *Movement*\n"
            "/forward /backward /left /right\n"
            "/stop — Stop all motors\n"
            "/patrol — Toggle patrol mode\n"
            "/speed `<0-100>` — Motor speed\n"
            "/look `<0-180>` — Servo angle\n\n"
            "🖥️ *Display & Voice*\n"
            "/say `<text>` — Show on display + speak\n"
            "/speak `<text>` — Speak only (no display)\n"
            "/volume `<0-100>` — Set volume\n\n"
            "📸 *Camera*\n"
            "/photo — Capture and send photo\n"
            "/face `<expr>` — Set face expression\n\n"
            "⚙️ *System*\n"
            "/status — System info\n"
            "/log — Recent Q&A log\n"
            "/reboot — Reboot RPi\n"
            "/shutdown — Graceful shutdown\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_status(self, update: Update,
                          ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        try:
            temp = psutil.sensors_temperatures()
            cpu_temp = (temp["cpu_thermal"][0].current
                        if "cpu_thermal" in temp else "N/A")
        except Exception:
            cpu_temp = "N/A"

        brain = self.shared.modules.get("brain")
        chunks = brain.collection.count() if (
            brain and brain.collection) else 0
        faq_count = len(brain.list_faq()) if brain else 0

        msg = (
            f"📊 *EMO Status*\n\n"
            f"State: `{self.shared.state.name}`\n"
            f"CPU: `{cpu}%` | Temp: `{cpu_temp}°C`\n"
            f"RAM: `{mem.used//1048576}MB / {mem.total//1048576}MB` "
            f"(`{mem.percent}%`)\n"
            f"Knowledge: `{chunks}` chunks\n"
            f"FAQs: `{faq_count}` cached\n"
            f"Obstacle: `{self.shared.obstacle_distance}` cm\n"
            f"Face: `{'Detected' if self.shared.face_detected else 'None'}`\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_ask(self, update: Update,
                       ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        q = " ".join(ctx.args) if ctx.args else ""
        if not q:
            await update.message.reply_text("Usage: /ask What is gravity?")
            return
        brain = self.shared.modules.get("brain")
        if not brain:
            await update.message.reply_text("❌ Brain not loaded")
            return
        await update.message.reply_text("🤔 Thinking...")
        answer = brain.ask(q)
        self.shared.add_conversation(q, answer)
        await update.message.reply_text(f"🤖 {answer}")

    # ── NEW: Text ingestion ──
    async def _cmd_text(self, update: Update,
                        ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        text = " ".join(ctx.args) if ctx.args else ""
        if not text:
            await update.message.reply_text(
                "Usage: /text <content to add to knowledge base>\n"
                "Example: /text The mitochondria is the powerhouse "
                "of the cell. It produces ATP through cellular "
                "respiration.")
            return
        brain = self.shared.modules.get("brain")
        if not brain:
            await update.message.reply_text("❌ Brain not loaded")
            return
        n = brain.ingest_text(text, source="telegram_text")
        total = brain.collection.count() if brain.collection else 0
        await update.message.reply_text(
            f"✅ Text ingested!\n"
            f"Chunks added: `{n}`\n"
            f"Total knowledge: `{total}` chunks",
            parse_mode="Markdown")

    # ── NEW: FAQ management ──
    async def _cmd_faq(self, update: Update,
                       ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        brain = self.shared.modules.get("brain")
        if not brain:
            await update.message.reply_text("❌ Brain not loaded")
            return

        text = " ".join(ctx.args) if ctx.args else ""
        if not text:
            # list existing FAQs
            faqs = brain.list_faq()
            if faqs:
                lines = [f"• `{q}`" for q in faqs[:20]]
                msg = ("📋 *Instant FAQs:*\n" + "\n".join(lines) +
                       f"\n\nTotal: {len(faqs)}")
            else:
                msg = "No FAQs set. Use: /faq question | answer"
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        if "|" not in text:
            await update.message.reply_text(
                "Usage: /faq What is EMO? | EMO is a smart AI robot!")
            return

        parts = text.split("|", 1)
        question = parts[0].strip()
        answer = parts[1].strip()
        brain.add_faq(question, answer)
        await update.message.reply_text(
            f"✅ FAQ added!\n"
            f"Q: `{question}`\n"
            f"A: {answer}", parse_mode="Markdown")

    # ── NEW: Q&A log ──
    async def _cmd_log(self, update: Update,
                       ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        log_file = config.BASE_DIR / "conversation_log.txt"
        if not log_file.exists():
            await update.message.reply_text("📝 No conversations logged yet.")
            return
        try:
            content = log_file.read_text()
            # get last 5 entries
            entries = content.strip().split("\n\n")
            recent = entries[-5:] if len(entries) > 5 else entries
            text = "\n\n".join(recent)
            if len(text) > 4000:
                text = text[-4000:]
            await update.message.reply_text(
                f"📝 *Recent Conversations:*\n\n```\n{text}\n```",
                parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error reading log: {e}")

    # ── NEW: Camera photo ──
    async def _cmd_photo(self, update: Update,
                         ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        camera = self.shared.modules.get("camera")
        if not camera:
            await update.message.reply_text("❌ Camera not available")
            return
        try:
            photo_path = camera.take_photo()
            if photo_path and os.path.exists(photo_path):
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M:%S")
                await update.message.reply_photo(
                    open(photo_path, "rb"),
                    caption=f"📸 Captured at {ts}")
            else:
                await update.message.reply_text(
                    "❌ Failed to capture photo")
        except Exception as e:
            await update.message.reply_text(f"❌ Photo error: {e}")

    # ── NEW: Speak (voice only, no display) ──
    async def _cmd_speak(self, update: Update,
                         ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        text = " ".join(ctx.args) if ctx.args else ""
        if not text:
            await update.message.reply_text("Usage: /speak Hello everyone!")
            return
        v = self.shared.modules.get("voice")
        if v:
            v.speak(text)
        await update.message.reply_text(f"🔊 Speaking: {text}")

    # ── NEW: Volume control ──
    async def _cmd_volume(self, update: Update,
                          ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        if not ctx.args:
            await update.message.reply_text("Usage: /volume 80")
            return
        try:
            vol = int(ctx.args[0])
            vol = max(0, min(100, vol))
            v = self.shared.modules.get("voice")
            if v and v.tts:
                v.tts.setProperty("volume", vol / 100.0)
            # also try system volume via amixer
            os.system(f"amixer set Master {vol}% 2>/dev/null")
            await update.message.reply_text(f"🔊 Volume → {vol}%")
        except ValueError:
            await update.message.reply_text("Usage: /volume 80")

    # ── NEW: Graceful shutdown ──
    async def _cmd_shutdown(self, update: Update,
                            ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        await update.message.reply_text("🛑 EMO shutting down...")
        v = self.shared.modules.get("voice")
        if v:
            try:
                v.speak("Shutting down. Goodbye everyone!")
            except Exception:
                pass
        self.shared.state = RobotState.SHUTDOWN

    # ── movement commands ────────────────────
    async def _cmd_forward(self, update: Update,
                           ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        m = self.shared.modules.get("motors")
        if m:
            m.forward(1.0)
        await update.message.reply_text("⬆️ Forward")

    async def _cmd_backward(self, update: Update,
                            ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        m = self.shared.modules.get("motors")
        if m:
            m.backward(1.0)
        await update.message.reply_text("⬇️ Backward")

    async def _cmd_left(self, update: Update,
                        ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        m = self.shared.modules.get("motors")
        if m:
            m.turn_left(0.5)
        await update.message.reply_text("⬅️ Left")

    async def _cmd_right(self, update: Update,
                         ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        m = self.shared.modules.get("motors")
        if m:
            m.turn_right(0.5)
        await update.message.reply_text("➡️ Right")

    async def _cmd_stop(self, update: Update,
                        ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        m = self.shared.modules.get("motors")
        if m:
            m.stop_patrol()
            m.stop_follow()
            m.stop()
        self.shared.state = RobotState.IDLE
        await update.message.reply_text("🛑 Stopped")

    async def _cmd_patrol(self, update: Update,
                          ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        m = self.shared.modules.get("motors")
        if not m:
            await update.message.reply_text("❌ Motors not loaded")
            return
        if self.shared.state == RobotState.PATROL:
            m.stop_patrol()
            self.shared.state = RobotState.IDLE
            await update.message.reply_text("🛑 Patrol OFF")
        else:
            self.shared.state = RobotState.PATROL
            m.start_patrol()
            await update.message.reply_text("🚗 Patrol ON")

    async def _cmd_speed(self, update: Update,
                         ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        if not ctx.args:
            await update.message.reply_text("Usage: /speed 75")
            return
        s = int(ctx.args[0])
        m = self.shared.modules.get("motors")
        if m:
            m.set_speed(s)
        self.shared.motor_speed = s
        await update.message.reply_text(f"🏎️ Speed: {s}%")

    async def _cmd_look(self, update: Update,
                        ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        if not ctx.args:
            await update.message.reply_text("Usage: /look 90")
            return
        angle = int(ctx.args[0])
        m = self.shared.modules.get("motors")
        if m:
            m.servo_angle(angle)
        await update.message.reply_text(f"👀 Servo → {angle}°")

    # ── display commands ─────────────────────
    async def _cmd_say(self, update: Update,
                       ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        text = " ".join(ctx.args) if ctx.args else ""
        if not text:
            await update.message.reply_text("Usage: /say Hello class!")
            return
        d = self.shared.modules.get("display")
        if d:
            d.show_answer(text)
        v = self.shared.modules.get("voice")
        if v:
            v.speak(text)
        await update.message.reply_text(f"🔊 Said: {text}")

    async def _cmd_face(self, update: Update,
                        ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        expr = ctx.args[0].lower() if ctx.args else "idle"
        state_map = {
            "happy": RobotState.IDLE,
            "listening": RobotState.LISTENING,
            "thinking": RobotState.THINKING,
            "speaking": RobotState.SPEAKING,
            "sad": RobotState.ERROR,
        }
        st = state_map.get(expr, RobotState.IDLE)
        self.shared.state = st
        await update.message.reply_text(f"😊 Face → {expr}")

    # ── brain commands ───────────────────────
    async def _cmd_ingest(self, update: Update,
                          ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        brain = self.shared.modules.get("brain")
        if not brain:
            await update.message.reply_text("❌ Brain not loaded")
            return
        await update.message.reply_text("📚 Ingesting all PDFs...")
        n = brain.ingest_all()
        await update.message.reply_text(f"✅ Ingested {n} chunks")

    async def _cmd_clear(self, update: Update,
                         ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        brain = self.shared.modules.get("brain")
        if brain:
            brain.clear_knowledge()
        await update.message.reply_text("🗑️ Knowledge base cleared")

    async def _cmd_docs(self, update: Update,
                        ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        brain = self.shared.modules.get("brain")
        if not brain:
            await update.message.reply_text("❌ Brain not loaded")
            return
        docs = brain.list_documents()
        if docs:
            msg = ("📄 *Loaded Documents:*\n" +
                   "\n".join(f"• `{d}`" for d in docs))
        else:
            msg = "📄 No documents loaded. Send a PDF to upload!"
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_reboot(self, update: Update,
                          ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        await update.message.reply_text("♻️ Rebooting...")
        os.system("sudo reboot")

    # ── PDF upload ───────────────────────────
    async def _handle_pdf(self, update: Update,
                          ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update):
            return
        doc = update.message.document
        if not doc.file_name.endswith(".pdf"):
            await update.message.reply_text("❌ Only PDF files accepted")
            return

        await update.message.reply_text(
            f"📥 Downloading {doc.file_name}...")
        tg_file = await ctx.bot.get_file(doc.file_id)
        path = config.DATA_DIR / doc.file_name
        await tg_file.download_to_drive(str(path))

        brain = self.shared.modules.get("brain")
        if brain:
            n = brain.ingest_pdf(str(path))
            total = brain.collection.count()
            await update.message.reply_text(
                f"✅ *{doc.file_name}* loaded!\n"
                f"Chunks added: `{n}`\n"
                f"Total knowledge: `{total}` chunks",
                parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "⚠️ PDF saved but brain not loaded")
