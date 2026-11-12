"""Camera — Picamera2 (libcamera) + OpenCV face detection + line following."""
import time
import threading
import numpy as np

try:
    from picamera2 import Picamera2
    _CAM = True
except ImportError:
    _CAM = False
    print("[CAMERA] picamera2 not installed — run: sudo apt install python3-picamera2")

try:
    import cv2
    _CV = True
except ImportError:
    _CV = False

import config
from config import RobotState


class CameraManager:
    def __init__(self, shared_state):
        self.shared = shared_state
        self.picam = None
        self._running = False
        self._paused = False
        self._detector = None
        self._frame_w = 640
        self._frame_h = 480
        self._cam_started = False
        self._line_following = False
        self._guard_mode = False
        self._prev_gray = None       # for motion detection
        self._face_count = 0
        self._last_frame = None

        # OpenCV Haar Cascade (works on RPi ARM — no mediapipe needed)
        self._face_cascade = None
        if _CV:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_cascade = cv2.CascadeClassifier(cascade_path)
            print("[CAMERA] OpenCV face detector ready")

    def start(self):
        self._running = True
        threading.Thread(target=self._camera_loop, daemon=True).start()

    def stop(self):
        self._running = False
        self._line_following = False
        self._guard_mode = False
        self._release()

    def pause(self):
        """Briefly pause face detection (camera stays open for snapshots)."""
        self._paused = True
        print("[CAMERA] Detection paused")

    def resume(self):
        self._paused = False
        print("[CAMERA] Detection resumed")

    def get_frame(self):
        """Get current camera frame (for face_db and vision commands)."""
        if self.picam and self._cam_started:
            try:
                return self.picam.capture_array()
            except:
                return self._last_frame
        return self._last_frame

    def what_do_you_see(self):
        """Describe what the camera sees right now."""
        parts = []
        if self.shared.face_detected:
            n = self._face_count
            if n == 1:
                parts.append("I can see 1 person in front of me")
                face = self.shared.face_position
                if face:
                    area = face[2] * face[3]
                    if area > 30000:
                        parts.append("and they're very close")
                    elif area > 10000:
                        parts.append("at a medium distance")
                    else:
                        parts.append("but they're quite far away")
            else:
                parts.append(f"I can see {n} people")
        else:
            parts.append("I don't see anyone right now")

        d = self.shared.obstacle_distance
        if d < 30:
            parts.append(f"There's something {d:.0f} centimeters ahead of me")
        return ". ".join(parts) + "."

    # ── line following ───────────────────────
    def start_line_follow(self):
        self._line_following = True

    def stop_line_follow(self):
        self._line_following = False

    # ── guard / security mode ────────────────
    def start_guard(self):
        self._guard_mode = True
        self._prev_gray = None
        print("[CAMERA] Guard mode ON")

    def stop_guard(self):
        self._guard_mode = False
        print("[CAMERA] Guard mode OFF")

    def _check_motion(self, frame):
        """Compare with previous frame for motion. Returns True if motion detected."""
        if not _CV:
            return False
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        if self._prev_gray is None:
            self._prev_gray = gray
            return False
        diff = cv2.absdiff(self._prev_gray, gray)
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        motion_pixels = cv2.countNonZero(thresh)
        self._prev_gray = gray
        # motion if > 2% of pixels changed
        return motion_pixels > (self._frame_w * self._frame_h * 0.02)

    # ── take photo ───────────────────────────
    def take_photo(self):
        """Save current frame as photo. Returns file path or None."""
        frame = self.get_frame()
        if frame is None or not _CV:
            return None
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = config.BASE_DIR / f"photo_{ts}.jpg"
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(path), bgr)
        print(f"[CAMERA] Photo saved: {path}")
        return str(path)

    # ── color detection ──────────────────────
    def detect_color(self):
        """Detect the dominant color in the center of the frame."""
        frame = self.get_frame()
        if frame is None or not _CV:
            return "unknown"
        # look at center 100x100 patch
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        patch = frame[cy-50:cy+50, cx-50:cx+50]
        avg = patch.mean(axis=(0, 1))  # RGB averages
        r, g, b = int(avg[0]), int(avg[1]), int(avg[2])

        # simple color classification from RGB
        if r > 180 and g < 100 and b < 100: return "red"
        if r < 100 and g > 150 and b < 100: return "green"
        if r < 100 and g < 100 and b > 180: return "blue"
        if r > 200 and g > 200 and b < 100: return "yellow"
        if r > 200 and g > 130 and b < 80:  return "orange"
        if r > 150 and g < 80 and b > 150:  return "purple"
        if r > 200 and g > 200 and b > 200: return "white"
        if r < 60 and g < 60 and b < 60:    return "black"
        if abs(r-g) < 30 and abs(g-b) < 30: return "gray"
        if r > 180 and g > 100 and b > 100: return "pink"
        if r < 100 and g > 180 and b > 180: return "cyan"
        return "a mixed color"

    # ── brightness ───────────────────────────
    def detect_brightness(self):
        """Return brightness level description."""
        frame = self.get_frame()
        if frame is None or not _CV:
            return "unknown"
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        avg = gray.mean()
        if avg > 180:   return "very bright"
        elif avg > 120: return "well lit"
        elif avg > 60:  return "a bit dim"
        else:           return "quite dark"

    def detect_line(self, frame):
        """Detect dark line on floor. Returns: 'left', 'right', 'center', or 'lost'."""
        if not _CV or frame is None:
            return "lost"
        # look at bottom third of frame only (floor)
        h = frame.shape[0]
        roi = frame[int(h * 0.65):h, :]

        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        # threshold for dark line on light surface
        _, thresh = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)

        # find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return "lost"

        # largest contour = the line
        biggest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(biggest) < 500:
            return "lost"

        M = cv2.moments(biggest)
        if M["m00"] == 0:
            return "lost"

        cx = int(M["m10"] / M["m00"])
        frame_mid = roi.shape[1] // 2

        if cx < frame_mid - 80:
            return "left"
        elif cx > frame_mid + 80:
            return "right"
        return "center"

    # ── internal ─────────────────────────────
    def _open(self):
        if not _CAM or self._cam_started:
            return
        try:
            self.picam = Picamera2()
            cam_config = self.picam.create_preview_configuration(
                main={"size": (self._frame_w, self._frame_h), "format": "RGB888"})
            self.picam.configure(cam_config)
            self.picam.start()
            time.sleep(0.5)
            self._cam_started = True
            print("[CAMERA] Picamera2 started (libcamera)")
        except Exception as e:
            print(f"[CAMERA] Failed to start: {e}")
            self.picam = None

    def _release(self):
        if self.picam and self._cam_started:
            try:
                self.picam.stop()
                self.picam.close()
            except: pass
            self.picam = None
            self._cam_started = False

    def _camera_loop(self):
        print("[CAMERA] Starting camera loop")
        while self._running:
            # camera always tries to stay open
            try:
                self._open()
                if not self.picam:
                    time.sleep(1)
                    continue

                frame = self.picam.capture_array()
                if frame is None:
                    time.sleep(0.2)
                    continue

                self._last_frame = frame

                # skip heavy processing if paused (but camera stays open)
                if self._paused:
                    time.sleep(0.15)
                    continue

                # face detection (OpenCV Haar Cascade)
                if self._face_cascade is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                    faces = self._face_cascade.detectMultiScale(
                        gray, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))
                    if len(faces) > 0:
                        self._face_count = len(faces)
                        # pick largest face
                        areas = [w*h for (x,y,w,h) in faces]
                        idx = areas.index(max(areas))
                        x, y, w, h = faces[idx]
                        self.shared.face_position = (x, y, w, h)
                        self.shared.face_detected = True
                    else:
                        self.shared.face_position = None
                        self.shared.face_detected = False
                        self._face_count = 0

                # line following mode
                if self._line_following:
                    direction = self.detect_line(frame)
                    motors = self.shared.modules.get("motors")
                    if motors:
                        if direction == "left":
                            motors.turn_left(0.15)
                        elif direction == "right":
                            motors.turn_right(0.15)
                        elif direction == "center":
                            motors.forward(0.1)
                        else:  # lost
                            motors.stop()

                # guard / security mode
                if self._guard_mode:
                    if self._check_motion(frame):
                        print("[CAMERA] ⚠ Motion detected!")
                        voice = self.shared.modules.get("voice")
                        if voice:
                            voice.speak("Alert! I detected movement!")
                        # save photo of intruder
                        photo = self.take_photo()
                        # try to alert via Telegram
                        try:
                            tg = self.shared.modules.get("telegram")
                            if tg and photo:
                                import asyncio
                                loop = asyncio.new_event_loop()
                                # send to all admin chats
                                for cid in config.ADMIN_CHAT_IDS:
                                    loop.run_until_complete(
                                        tg.app.bot.send_photo(
                                            cid, open(photo, "rb"),
                                            caption="🚨 Motion detected! Guard mode alert."))
                                loop.close()
                        except Exception as e:
                            print(f"[CAMERA] Telegram alert failed: {e}")
                        time.sleep(5)  # cooldown between alerts

            except Exception as e:
                print(f"[CAMERA] Error: {e}")
                time.sleep(1)

            time.sleep(0.08)  # ~12 fps
