"""128×64 SPI LCD (ST7565 / UC1701) — Big animated eyes + text mode.

Display Layout (128×64 pixels):
- Eyes: Centered on screen, filling most of the area
- Text: Word-wrapped with scroll, status bar on top
- Animations: Blink, tracking, thinking dots, speaking mouth
"""
import time
import logging
import threading
from datetime import datetime

log = logging.getLogger("emo.display")

try:
    from luma.core.interface.serial import spi
    from luma.lcd.device import uc1701x
    _LCD = True
except ImportError:
    _LCD = False
    log.warning("luma.lcd not found — headless mode")

try:
    from PIL import Image, ImageDraw, ImageFont, ImageChops
    _PIL = True
except ImportError:
    _PIL = False

import config
from config import RobotState

# ─── Screen dimensions ──────────────────────
W = 128
H = 64
CX = W // 2   # center X = 64
CY = 28       # eye center Y (slightly above center for face balance)

# ─── Font helper ─────────────────────────────
def _load_font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()

FONT_SM = _load_font(8)  if _PIL else None
FONT_MD = _load_font(10) if _PIL else None
FONT_LG = _load_font(14) if _PIL else None


class DisplayManager:
    def __init__(self, shared_state):
        self.shared = shared_state
        self.device = None
        self._running = False
        self._frame = 0
        self._answer_lines = []
        self._scroll_idx = 0
        self._scroll_timer = 0
        self._status_text = ""  # temporary status like "Thinking..."

        if _LCD:
            try:
                serial = spi(port=0, device=0,
                             gpio_DC=config.DISPLAY_DC,
                             gpio_RST=config.DISPLAY_RST)
                self.device = uc1701x(serial, rotate=0)
                self.device.contrast(config.DISPLAY_CONTRAST)
                log.info("LCD connected")
            except Exception as e:
                log.error(f"LCD init failed: {e}")

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False
        if self.device:
            self.device.hide()

    def show_answer(self, text):
        """Word-wrap text for display. Fits 21 chars per line on 128px."""
        if text == "Thinking...":
            self._status_text = text
            return
        self._status_text = ""
        words = text.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= 21:
                cur += (" " if cur else "") + w
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        self._answer_lines = lines
        self._scroll_idx = 0
        self._scroll_timer = 0

    def clear_text(self):
        self._answer_lines = []
        self._status_text = ""

    # ── main render loop ─────────────────────
    def _loop(self):
        while self._running:
            if not self.device or not _PIL:
                time.sleep(1)
                continue
            try:
                img = Image.new("1", (W, H), 0)
                draw = ImageDraw.Draw(img)
                st = self.shared.state

                if st == RobotState.BOOTING:
                    self._draw_boot(draw)
                elif st == RobotState.SHUTDOWN:
                    self._draw_shutdown(draw)
                elif st == RobotState.SPEAKING and self._answer_lines:
                    self._draw_text(draw)
                elif st == RobotState.THINKING or self._status_text:
                    self._draw_eyes(draw, st)
                    self._draw_status_bar(draw)
                else:
                    self._draw_eyes(draw, st)

                # Fix hardware vertical wrap offset (split screen)
                img = ImageChops.offset(img, 0, 32)
                self.device.display(img)
                self._frame += 1
            except Exception as e:
                log.error(f"Render: {e}")
            time.sleep(1.0 / config.DISPLAY_FPS)

    # ═════════════════════════════════════════
    # BOOT & SHUTDOWN
    # ═════════════════════════════════════════
    def _draw_boot(self, draw):
        # EMO title centered
        draw.text((44, 5), "EMO", fill=1, font=FONT_LG)
        draw.text((12, 25), "Smart Teaching Robot", fill=1, font=FONT_SM)
        dots = "." * ((self._frame // 5) % 4)
        draw.text((35, 38), f"Booting{dots}", fill=1, font=FONT_SM)
        # progress bar centered
        pct = min(self._frame * 3, 100)
        draw.rectangle([(14, 50), (114, 58)], outline=1)
        bar_w = int(pct * 0.98)
        draw.rectangle([(16, 52), (16 + bar_w, 56)], fill=1)

    def _draw_shutdown(self, draw):
        # sleeping eyes — horizontal lines centered
        draw.line([(24, CY), (54, CY)], fill=1, width=3)
        draw.line([(74, CY), (104, CY)], fill=1, width=3)
        draw.text((20, 50), "Goodbye! Zzz..", fill=1, font=FONT_MD)

    # ═════════════════════════════════════════
    # FULL SCREEN TEXT (when EMO speaks)
    # ═════════════════════════════════════════
    def _draw_text(self, draw):
        """Full screen scrolling text during speaking."""
        # thin top bar
        t = datetime.now().strftime("%H:%M")
        draw.text((2, 0), t, fill=1, font=FONT_SM)
        draw.text((100, 0), "EMO", fill=1, font=FONT_SM)
        draw.line([(0, 10), (127, 10)], fill=1)

        # show 4 lines of text (each ~12px high)
        vis = self._answer_lines[self._scroll_idx:self._scroll_idx + 4]
        for i, line in enumerate(vis):
            draw.text((2, 13 + i * 12), line, fill=1, font=FONT_MD)

        # bottom bar: page indicator + speaking animation
        total_pages = max(1, (len(self._answer_lines) + 3) // 4)
        cur_page = self._scroll_idx // 4 + 1
        draw.text((90, 55), f"{cur_page}/{total_pages}", fill=1, font=FONT_SM)

        # speaking dots animation
        n = (self._frame // 3) % 4
        for i in range(n):
            draw.ellipse((4 + i*8, 56, 8 + i*8, 60), fill=1)

        # auto-scroll every 3s
        self._scroll_timer += 1
        if self._scroll_timer > config.DISPLAY_FPS * 3:
            self._scroll_timer = 0
            self._scroll_idx += 4
            if self._scroll_idx >= len(self._answer_lines):
                self._scroll_idx = 0

    # ═════════════════════════════════════════
    # STATUS BAR (Thinking..., Listening...)
    # ═════════════════════════════════════════
    def _draw_status_bar(self, draw):
        """Small status text at bottom of screen."""
        if self._status_text:
            dots = "." * ((self._frame // 4) % 4)
            text = self._status_text.rstrip(".") + dots
            # center the text
            tw = len(text) * 6
            x = max(0, (W - tw) // 2)
            draw.text((x, 55), text, fill=1, font=FONT_SM)

    # ═════════════════════════════════════════
    # BIG EYES — centered, filling the screen
    # ═════════════════════════════════════════
    def _draw_eyes(self, draw, state):
        """Full screen animated eyes — EMO's face."""

        # ── EXACT 100x50 CENTERED VIEWPORT GEOMETRY ──
        # Cardboard window is extremely small! Treat as 100x50.
        # X range: 14 to 114 (center CX=64)
        # Y range: 7 to 57  (center CY=32)
        
        # DEBUG: Draw a literal rectangle so the user can see the 100x50 border
        draw.rectangle([(14, 7), (114, 57)], outline=1)
        
        EYE_R = 9   # medium radius
        GAP = 16    # closer together
        CY_EYE = 28 # Just above true center (32) to leave room for mouth

        LCX = CX - GAP  # 54
        RCX = CX + GAP  # 74

        # bounding boxes
        LE = (LCX - EYE_R, CY_EYE - EYE_R, LCX + EYE_R, CY_EYE + EYE_R)
        RE = (RCX - EYE_R, CY_EYE - EYE_R, RCX + EYE_R, CY_EYE + EYE_R)

        # pupil size
        PR = 2 

        blink = (self._frame % 35) < 2

        # ═══ IDLE — happy eyes that TRACK faces ═══
        if state == RobotState.IDLE:
            if blink:
                draw.line([(LE[0], CY_EYE), (LE[2], CY_EYE)], fill=1, width=2)
                draw.line([(RE[0], CY_EYE), (RE[2], CY_EYE)], fill=1, width=2)
            else:
                draw.ellipse(LE, fill=1)
                draw.ellipse(RE, fill=1)
                px, py = 0, 0
                face = self.shared.face_position
                if face and self.shared.face_detected:
                    fx = face[0] + face[2] // 2
                    fy = face[1] + face[3] // 2
                    px = max(-2, min(2, int((fx - 320) / 100)))
                    py = max(-1, min(1, int((fy - 240) / 100)))
                # draw pupils
                draw.ellipse((LCX - PR + px, CY_EYE - 2 + py,
                              LCX + PR + px, CY_EYE - 2 + PR*2 + py), fill=0)
                draw.ellipse((RCX - PR + px, CY_EYE - 2 + py,
                              RCX + PR + px, CY_EYE - 2 + PR*2 + py), fill=0)
            # tiny smile arc (Y=36 to 42)
            draw.arc([(CX - 8, 36), (CX + 8, 42)], 0, 180, fill=1, width=2)

        # ═══ LISTENING — big wide alert eyes ═══
        elif state == RobotState.LISTENING:
            BR = EYE_R + 2
            draw.ellipse((LCX - BR, CY_EYE - BR, LCX + BR, CY_EYE + BR), fill=1)
            draw.ellipse((RCX - BR, CY_EYE - BR, RCX + BR, CY_EYE + BR), fill=1)
            draw.ellipse((LCX - PR, CY_EYE - 2, LCX + PR, CY_EYE - 2 + PR*2), fill=0)
            draw.ellipse((RCX - PR, CY_EYE - 2, RCX + PR, CY_EYE - 2 + PR*2), fill=0)
            # tiny open mouth (Y=38 to 41)
            draw.ellipse([(CX - 3, 38), (CX + 3, 41)], outline=1, width=2)
            # "Listening" label at top inside 80x40 (Y=12)
            draw.text((40, 12), "Listening", fill=1, font=FONT_SM)

        # ═══ THINKING — squinting + animated dots ═══
        elif state == RobotState.THINKING:
            draw.line([(LE[0], CY_EYE - 1), (LE[2], CY_EYE + 1)], fill=1, width=3)
            draw.line([(RE[0], CY_EYE + 1), (RE[2], CY_EYE - 1)], fill=1, width=3)
            dots = (self._frame // 4) % 4
            dot_start = CX - 10
            for i in range(dots):
                draw.ellipse((dot_start + i * 8, 38, dot_start + i * 8 + 2, 40), fill=1)

        # ═══ SPEAKING — normal eyes + animated mouth ═══
        elif state == RobotState.SPEAKING:
            draw.ellipse(LE, fill=1)
            draw.ellipse(RE, fill=1)
            draw.ellipse((LCX - PR, CY_EYE - 2, LCX + PR, CY_EYE - 2 + PR*2), fill=0)
            draw.ellipse((RCX - PR, CY_EYE - 2, RCX + PR, CY_EYE - 2 + PR*2), fill=0)
            # tiny animated mouth changing height around Y=40
            mh = [1, 3, 5, 3][self._frame % 4]
            draw.ellipse([(CX - 6, 40 - mh//2), (CX + 6, 40 + mh//2)], fill=1)

        # ═══ WAKEUP / FOLLOWING — excited sparkly eyes ═══
        elif state in (RobotState.WAKEUP, RobotState.FOLLOWING):
            BR = EYE_R + 2
            draw.ellipse((LCX - BR, CY_EYE - BR, LCX + BR, CY_EYE + BR), fill=1)
            draw.ellipse((RCX - BR, CY_EYE - BR, RCX + BR, CY_EYE + BR), fill=1)
            draw.ellipse((LCX - PR, CY_EYE - 2, LCX + PR, CY_EYE - 2 + PR*2+1), fill=0)
            draw.ellipse((RCX - PR, CY_EYE - 2, RCX + PR, CY_EYE - 2 + PR*2+1), fill=0)
            if self._frame % 6 < 3:
                draw.line([(CX - 1, CY_EYE - 8), (CX + 1, CY_EYE - 8)], fill=1)
                draw.line([(CX, CY_EYE - 9), (CX, CY_EYE - 7)], fill=1)
            draw.arc([(CX - 10, 36), (CX + 10, 42)], 0, 180, fill=1, width=2)

        # ═══ PATROL — scanning eyes ═══
        elif state == RobotState.PATROL:
            draw.ellipse(LE, fill=1)
            draw.ellipse(RE, fill=1)
            shift = [0, 1, 2, 1, 0, -1, -2, -1][self._frame % 8]
            draw.ellipse((LCX - PR + shift, CY_EYE - 2,
                          LCX + PR + shift, CY_EYE - 2 + PR*2), fill=0)
            draw.ellipse((RCX - PR + shift, CY_EYE - 2,
                          RCX + PR + shift, CY_EYE - 2 + PR*2), fill=0)
            draw.arc([(CX - 8, 36), (CX + 8, 40)], 0, 180, fill=1, width=2)
            d = self.shared.obstacle_distance
            if d < config.OBSTACLE_DISTANCE:
                draw.text((45, 42), f"! {d:.0f}cm", fill=1, font=FONT_SM)

        # ═══ ERROR — X eyes + frown ═══
        elif state == RobotState.ERROR:
            draw.line([(LCX - 4, CY_EYE - 4), (LCX + 4, CY_EYE + 4)], fill=1, width=2)
            draw.line([(LCX - 4, CY_EYE + 4), (LCX + 4, CY_EYE - 4)], fill=1, width=2)
            draw.line([(RCX - 4, CY_EYE - 4), (RCX + 4, CY_EYE + 4)], fill=1, width=2)
            draw.line([(RCX - 4, CY_EYE + 4), (RCX + 4, CY_EYE - 4)], fill=1, width=2)
            draw.arc([(CX - 8, 38), (CX + 8, 44)], 180, 360, fill=1, width=2)

        # ═══ MANUAL / DEFAULT — normal eyes ═══
        else:
            draw.ellipse(LE, fill=1)
            draw.ellipse(RE, fill=1)
            draw.ellipse((LCX - PR, CY_EYE - 2, LCX + PR, CY_EYE - 2 + PR*2), fill=0)
            draw.ellipse((RCX - PR, CY_EYE - 2, RCX + PR, CY_EYE - 2 + PR*2), fill=0)
            draw.line([(CX - 6, 38), (CX + 6, 38)], fill=1, width=1)
