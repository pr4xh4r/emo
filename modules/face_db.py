"""Face Recognition Database — Enroll, recognize, greet by name."""
import os
import json
import time

try:
    import cv2
    _CV = True
except ImportError:
    _CV = False

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

import config


class FaceDB:
    """Lightweight face recognition using OpenCV LBPH recognizer."""

    def __init__(self):
        self._people = {}        # {label_id: name}
        self._meta_path = config.FACES_DIR / "people.json"
        self._recognizer = None
        self._next_label = 0

        self._load_metadata()
        self._train()

    # ── public API ───────────────────────────

    def enroll(self, frame, name):
        """Save face from frame under given name. Returns True on success."""
        if not _CV or frame is None:
            return False

        gray_face = self._extract_face(frame)
        if gray_face is None:
            return False

        # create person dir
        person_dir = config.FACES_DIR / name.lower().replace(" ", "_")
        person_dir.mkdir(exist_ok=True)

        # save multiple angles (we take what we have)
        count = len(list(person_dir.glob("*.jpg")))
        path = person_dir / f"face_{count}.jpg"
        cv2.imwrite(str(path), gray_face)

        # update metadata
        label = self._get_or_create_label(name)
        self._save_metadata()

        # retrain
        self._train()
        print(f"[FACE_DB] Enrolled '{name}' (image #{count})")
        return True

    def enroll_multiple(self, frames, name):
        """Enroll multiple face frames for better accuracy."""
        saved = 0
        for frame in frames:
            if self.enroll(frame, name):
                saved += 1
        return saved

    def recognize(self, frame):
        """Recognize face in frame. Returns (name, confidence) or (None, 0)."""
        if not _CV or self._recognizer is None or frame is None:
            return None, 0

        gray_face = self._extract_face(frame)
        if gray_face is None:
            return None, 0

        try:
            label, confidence = self._recognizer.predict(gray_face)
            # LBPH confidence: lower = better match, < 80 is good
            if confidence < 80:
                name = self._people.get(str(label), "Unknown")
                return name, round(100 - confidence, 1)
            return None, 0
        except Exception:
            return None, 0

    def list_people(self):
        """Return list of enrolled names."""
        return list(set(self._people.values()))

    def forget(self, name):
        """Remove a person from the database."""
        import shutil
        person_dir = config.FACES_DIR / name.lower().replace(" ", "_")
        if person_dir.exists():
            shutil.rmtree(person_dir)

        # remove from metadata
        to_remove = [k for k, v in self._people.items() if v == name]
        for k in to_remove:
            del self._people[k]
        self._save_metadata()
        self._train()
        print(f"[FACE_DB] Forgot '{name}'")

    # ── internal methods ─────────────────────

    def _extract_face(self, frame):
        """Detect and crop face, convert to grayscale 100x100."""
        if not _CV:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        if len(faces) == 0:
            return None

        # take largest face
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_crop = gray[y:y+h, x:x+w]
        face_resized = cv2.resize(face_crop, (100, 100))
        return face_resized

    def _get_or_create_label(self, name):
        # check if name already has a label
        for label, n in self._people.items():
            if n == name:
                return int(label)
        label = self._next_label
        self._people[str(label)] = name
        self._next_label += 1
        return label

    def _train(self):
        """Train LBPH recognizer on all saved face images."""
        if not _CV:
            return

        faces = []
        labels = []

        for label_str, name in self._people.items():
            label = int(label_str)
            person_dir = config.FACES_DIR / name.lower().replace(" ", "_")
            if not person_dir.exists():
                continue
            for img_path in person_dir.glob("*.jpg"):
                img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    img = cv2.resize(img, (100, 100))
                    faces.append(img)
                    labels.append(label)

        if len(faces) < 1:
            self._recognizer = None
            return

        self._recognizer = cv2.face.LBPHFaceRecognizer_create()
        self._recognizer.train(faces, np.array(labels))
        print(f"[FACE_DB] Trained on {len(faces)} images, {len(set(labels))} people")

    def _load_metadata(self):
        if self._meta_path.exists():
            with open(self._meta_path) as f:
                data = json.load(f)
                self._people = data.get("people", {})
                self._next_label = data.get("next_label", 0)

    def _save_metadata(self):
        with open(self._meta_path, "w") as f:
            json.dump({
                "people": self._people,
                "next_label": self._next_label
            }, f, indent=2)
