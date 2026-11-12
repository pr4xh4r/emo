#!/usr/bin/env python3
"""EMO — Smart AI Teaching Robot (main orchestrator).

Production-ready with:
- Structured logging (file + console)
- Startup health checks
- Auto-kill old instances via PID lockfile
- JACK/ALSA warning suppression
- Graceful shutdown with cleanup
"""
import os
import sys
import time
import signal
import logging
from datetime import datetime
from pathlib import Path

# ══════════════════════════════════════════════
# Suppress JACK & ALSA warnings BEFORE any audio import
# ══════════════════════════════════════════════
os.environ['JACK_NO_START_SERVER'] = '1'
os.environ['JACK_NO_AUDIO_RESERVATION'] = '1'
try:
    import ctypes
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
    def _null_handler(filename, line, function, err, fmt):
        return
    _c_error_handler = ERROR_HANDLER_FUNC(_null_handler)
    _asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    _asound.snd_lib_error_set_handler(_c_error_handler)
except Exception:
    pass

import config
from config import RobotState, SharedState

# ══════════════════════════════════════════════
# Logging — file + console
# ══════════════════════════════════════════════
LOG_FILE = config.BASE_DIR / "emo.log"
CONV_LOG = config.BASE_DIR / "conversation_log.txt"
PIDFILE  = config.BASE_DIR / ".emo.pid"

log = logging.getLogger("emo")
log.setLevel(logging.INFO)
_fmt = logging.Formatter(
    "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S")
# console handler
_ch = logging.StreamHandler()
_ch.setFormatter(_fmt)
log.addHandler(_ch)
# file handler
try:
    _fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    _fh.setFormatter(_fmt)
    log.addHandler(_fh)
except Exception:
    pass

# ══════════════════════════════════════════════
# Graceful shutdown
# ══════════════════════════════════════════════
shared = SharedState()


def shutdown(sig=None, frame=None):
    log.info("Shutting down...")
    shared.state = RobotState.SHUTDOWN

    voice = shared.modules.get("voice")
    if voice:
        try:
            voice.speak("Goodbye everyone! See you next time!")
        except Exception:
            pass

    for name, mod in shared.modules.items():
        try:
            if hasattr(mod, "stop"):
                mod.stop()
            if hasattr(mod, "cleanup"):
                mod.cleanup()
            log.info(f"  ✓ {name} stopped")
        except Exception as e:
            log.error(f"  ✗ {name}: {e}")

    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except Exception:
        pass
    try:
        PIDFILE.unlink(missing_ok=True)
    except Exception:
        pass
    log.info("Goodbye! 👋")
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ══════════════════════════════════════════════
# Startup utilities
# ══════════════════════════════════════════════
def _kill_old_instances():
    """Kill any previous EMO process to avoid Telegram conflicts."""
    if PIDFILE.exists():
        try:
            old_pid = int(PIDFILE.read_text().strip())
            if old_pid != os.getpid():
                os.kill(old_pid, 9)
                log.info(f"Killed old instance (PID {old_pid})")
                time.sleep(2)
        except (ProcessLookupError, ValueError):
            pass
        except Exception as e:
            log.warning(f"Could not kill old PID: {e}")
    PIDFILE.write_text(str(os.getpid()))


def _health_checks():
    """Run startup health checks and report status."""
    checks = []

    # check Ollama
    try:
        import ollama as _ol
        _ol.list()
        checks.append("  ✓ Ollama running")
    except Exception:
        checks.append("  ✗ Ollama not running — /ask won't work")

    # check Vosk model
    if config.VOSK_MODEL.exists():
        checks.append("  ✓ Vosk speech model found")
    else:
        checks.append("  ✗ Vosk model missing — run setup.sh")

    # check data directory
    pdfs = list(config.DATA_DIR.glob("*.pdf"))
    checks.append(f"  ✓ {len(pdfs)} PDFs in data/")

    # check Telegram token
    if config.TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        checks.append("  ✓ Telegram token set")
    else:
        checks.append("  ✗ Telegram token not configured")

    return checks


# ══════════════════════════════════════════════
# Boot sequence
# ══════════════════════════════════════════════
def main():
    _kill_old_instances()

    log.info("=" * 50)
    log.info("  🤖 EMO — Smart AI Teaching Robot")
    log.info("  Edge AI • Offline • RAG-Powered")
    log.info("=" * 50)

    # health checks
    log.info("Running health checks...")
    for line in _health_checks():
        log.info(line)

    shared.state = RobotState.BOOTING

    # 1. Display (first — shows boot animation)
    log.info("[BOOT] 1/8 Display...")
    try:
        from modules.display import DisplayManager
        display = DisplayManager(shared)
        shared.modules["display"] = display
        display.start()
        time.sleep(0.5)
    except Exception as e:
        log.error(f"Display failed: {e}")

    # 2. Sensors
    log.info("[BOOT] 2/8 Sensors...")
    try:
        from modules.sensors import UltrasonicSensor
        sensor = UltrasonicSensor()
        shared.modules["sensor"] = sensor
    except Exception as e:
        log.error(f"Sensors failed: {e}")

    # 3. Motors
    log.info("[BOOT] 3/8 Motors...")
    try:
        from modules.motors import MotorController
        sensor = shared.modules.get("sensor")
        motors = MotorController(shared, sensor)
        shared.modules["motors"] = motors
    except Exception as e:
        log.error(f"Motors failed: {e}")

    # 4. Brain (RAG + LLM)
    log.info("[BOOT] 4/8 Brain (RAG + LLM)...")
    try:
        from modules.brain import Brain
        brain = Brain(shared)
        brain.ingest_all()
        shared.modules["brain"] = brain
    except Exception as e:
        log.error(f"Brain failed: {e}")

    # 5. Camera
    log.info("[BOOT] 5/8 Camera...")
    try:
        from modules.camera import CameraManager
        camera = CameraManager(shared)
        shared.modules["camera"] = camera
        camera.start()
    except Exception as e:
        log.error(f"Camera failed: {e}")

    # 6. Face Recognition DB
    log.info("[BOOT] 6/8 Face Recognition...")
    try:
        from modules.face_db import FaceDB
        face_db = FaceDB()
        shared.modules["face_db"] = face_db
    except Exception as e:
        log.error(f"Face DB failed: {e}")

    # 7. Voice (depends on brain)
    log.info("[BOOT] 7/8 Voice...")
    try:
        from modules.voice import VoiceManager
        brain = shared.modules.get("brain")
        voice = VoiceManager(shared, brain)
        shared.modules["voice"] = voice
        voice.start()
    except Exception as e:
        log.error(f"Voice failed: {e}")

    # 8. Telegram bot (depends on all modules)
    log.info("[BOOT] 8/8 Telegram Bot...")
    try:
        from modules.telegram_bot import TelegramBot
        tg = TelegramBot(shared)
        shared.modules["telegram"] = tg
        tg.start()
    except Exception as e:
        log.error(f"Telegram failed: {e}")

    # ── READY ──
    time.sleep(1)
    shared.state = RobotState.IDLE

    log.info("")
    log.info("=" * 50)
    log.info("  ✅ EMO is READY!")
    log.info(f"  Modules loaded: {list(shared.modules.keys())}")
    log.info(f"  State: {shared.state.name}")
    log.info("  Say 'EMO' to start talking!")
    log.info("=" * 50)

    # boot greeting
    voice = shared.modules.get("voice")
    if voice:
        try:
            voice.speak("Hello! I am EMO, your smart teaching robot! "
                        "I am ready to help you learn. Just say my name!")
        except Exception as e:
            log.error(f"Boot greeting failed: {e}")

    # conversation logger (background thread)
    import threading

    def _log_conversations():
        last_count = 0
        while shared.state != RobotState.SHUTDOWN:
            if len(shared.conversation) > last_count:
                for entry in shared.conversation[last_count:]:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        with open(CONV_LOG, "a") as f:
                            f.write(f"[{ts}]\n")
                            f.write(f"  Student: {entry['q']}\n")
                            f.write(f"  EMO:     {entry['a']}\n\n")
                    except Exception:
                        pass
                last_count = len(shared.conversation)
            time.sleep(2)

    threading.Thread(target=_log_conversations, daemon=True).start()

    # keep alive
    try:
        while shared.state != RobotState.SHUTDOWN:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()

    shutdown()


if __name__ == "__main__":
    main()
