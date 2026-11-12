"""Voice I/O — Wake word + voice commands + face recognition + RAG Q&A."""
import os
import sys
import json
import time
import random
import logging
import threading
import datetime

log = logging.getLogger("emo.voice")

try:
    import vosk
    _VOSK = True
except ImportError:
    _VOSK = False
    print("[VOICE] vosk not installed")

try:
    import pyaudio
    _AUDIO = True
except ImportError:
    _AUDIO = False
    print("[VOICE] pyaudio not installed")

try:
    import pyttsx3
    _TTS = True
except ImportError:
    _TTS = False
    print("[VOICE] pyttsx3 not installed")

import config
from config import RobotState


# ═══════════════════════════════════════════════
# Voice command definitions
# ═══════════════════════════════════════════════
COMMANDS = {
    # ── movement ──
    "move forward":    "forward",
    "go forward":      "forward",
    "go ahead":        "forward",
    "move backward":   "backward",
    "go back":         "backward",
    "move back":       "backward",
    "turn left":       "turn_left",
    "go left":         "turn_left",
    "turn right":      "turn_right",
    "go right":        "turn_right",
    "stop":            "stop",
    "stop moving":     "stop",
    "halt":            "stop",
    "freeze":          "stop",
    "spin":            "spin",
    "turn around":     "spin",
    "rotate":          "spin",
    "speed up":        "speed_up",
    "go faster":       "speed_up",
    "slow down":       "slow_down",
    "go slower":       "slow_down",

    # ── patrol ──
    "start patrol":    "patrol_on",
    "patrol":          "patrol_on",
    "stop patrol":     "patrol_off",

    # ── face following ──
    "come here":       "come_here",
    "come to me":      "come_here",
    "follow me":       "come_here",

    # ── servo head ──
    "look left":       "look_left",
    "look right":      "look_right",
    "look at me":      "look_center",
    "look straight":   "look_center",
    "look up":         "look_up",
    "look down":       "look_down",
    "nod":             "nod_yes",
    "nod yes":         "nod_yes",
    "shake your head": "shake_no",
    "say no":          "shake_no",

    # ── face recognition ──
    "recognize me":    "enroll_face",
    "remember me":     "enroll_face",
    "save my face":    "enroll_face",
    "who am i":        "identify_face",
    "do you know me":  "identify_face",
    "who is this":     "identify_face",
    "who do you know": "list_faces",
    "forget me":       "forget_face",

    # ── info & self ──
    "introduce yourself":  "intro",
    "who are you":         "intro",
    "what is your name":   "intro",
    "what can you do":     "abilities",
    "help":                "abilities",
    "what are your skills": "abilities",
    "how are you":         "how_are_you",
    "how do you feel":     "how_are_you",
    "are you okay":        "how_are_you",
    "status":              "sys_status",
    "system status":       "sys_status",
    "battery":             "sys_status",

    # ── fun ──
    "dance":           "dance",
    "do a dance":      "dance",
    "tell me a joke":  "joke",
    "tell a joke":     "joke",
    "sing a song":     "sing",
    "sing":            "sing",
    "count to ten":    "count",
    "count":           "count",
    "surprise me":     "surprise",

    # ── learning ──
    "quiz me":         "quiz",
    "test me":         "quiz",
    "ask me a question": "quiz",
    "repeat":          "repeat",
    "say that again":  "repeat",
    "what did you say": "repeat",
    "explain again":   "repeat",

    # ── volume & speech ──
    "speak louder":    "louder",
    "louder":          "louder",
    "volume up":       "louder",
    "speak softer":    "quieter",
    "quieter":         "quieter",
    "volume down":     "quieter",
    "be quiet":        "shush",
    "shut up":         "shush",
    "silence":         "shush",
    "speak faster":    "talk_fast",
    "speak slower":    "talk_slow",

    # ── greetings & manners ──
    "good morning":    "greet_back",
    "good afternoon":  "greet_back",
    "good evening":    "greet_back",
    "hello":           "greet_back",
    "hi":              "greet_back",
    "hey":             "greet_back",
    "goodbye":         "goodbye",
    "bye":             "goodbye",
    "go to sleep":     "goodbye",
    "thank you":       "thanks",
    "thanks":          "thanks",
    "sorry":           "sorry_resp",
    "i love you":      "love_resp",
    "you are smart":   "compliment_resp",
    "you are amazing": "compliment_resp",
    "good job":        "compliment_resp",
    "well done":       "compliment_resp",

    # ── utility ──
    "what time is it":   "tell_time",
    "what is the time":  "tell_time",
    "what day is it":    "tell_date",
    "what is the date":  "tell_date",
    "what is today":     "tell_date",

    # ── camera vision ──
    "follow the line":    "line_follow",
    "follow line":        "line_follow",
    "line follow":        "line_follow",
    "stop following":     "line_stop",
    "stop line":          "line_stop",
    "what do you see":    "what_see",
    "what can you see":   "what_see",
    "do you see anyone":  "what_see",
    "how many people":    "what_see",
    "look around":        "look_around",

    # ── security ──
    "guard this area":    "guard_on",
    "guard mode":         "guard_on",
    "security mode":      "guard_on",
    "watch this place":   "guard_on",
    "stop guarding":      "guard_off",
    "guard off":          "guard_off",

    # ── photo & vision ──
    "take a photo":       "take_photo",
    "take photo":         "take_photo",
    "take a picture":     "take_photo",
    "selfie":             "take_photo",
    "what color is this":  "detect_color",
    "what color":          "detect_color",
    "is it dark":          "brightness",
    "how bright":          "brightness",
    "is the light on":     "brightness",

    # ── educational ──
    "set a timer":        "timer",
    "set timer":          "timer",
    "timer":              "timer",
    "how do you spell":   "spell",
    "spell":              "spell",
    "calculate":          "math",
    "what is":            "math",
    "how much is":        "math",
    "tell me a story":    "story",
    "story time":         "story",
    "tell me a fact":     "fun_fact",
    "fun fact":           "fun_fact",
    "did you know":       "fun_fact",
    "teach me something": "fun_fact",

    # ── empathy / smart ──
    "i am sad":           "cheer_up",
    "i am bored":         "cheer_up",
    "i feel sad":         "cheer_up",
    "cheer me up":        "cheer_up",
    "i am tired":         "tired_resp",
    "i am sleepy":        "tired_resp",

    # ── unique interactive ──
    "play a game":        "game_guess",
    "guess the number":   "game_guess",
    "number game":        "game_guess",
    "rock paper scissors": "game_rps",
    "lets play":          "game_rps",

    "take attendance":    "attendance",
    "roll call":          "attendance",
    "who is here":        "attendance",

    "motivate me":        "motivate",
    "give me motivation": "motivate",
    "inspire me":         "motivate",

    "remind me":          "reminder",
    "set a reminder":     "reminder",

    "describe me":        "describe_me",
    "how do i look":      "describe_me",

    "morning routine":    "morning",
    "good night":         "bedtime",
    "bedtime":            "bedtime",

    "tell the class":     "announce",
    "announcement":       "announce",

    "whisper":            "whisper",
    "shout":              "shout",
    "yell":               "shout",
}

JOKES = [
    "Why did the robot go to school? Because it wanted to improve its bits and bytes!",
    "What do you call a robot that always takes the longest route? R2-Detour!",
    "Why was the math book sad? Because it had too many problems!",
    "What did the science book say to the math book? You've got problems!",
    "Why do robots never get scared? Because they have nerves of steel!",
    "What's a computer's favorite snack? Microchips!",
    "Why did the student eat his homework? Because the teacher told him it was a piece of cake!",
    "What did zero say to eight? Nice belt!",
    "Why is six afraid of seven? Because seven eight nine!",
    "How does a scientist freshen their breath? With experi-mints!",
]

SINGS = [
    "Twinkle twinkle little star, how I wonder what you are! Up above the world so high, like a diamond in the sky!",
    "A B C D E F G, H I J K L M N O P, Q R S T U V, W X Y and Z! Now I know my A B Cs, next time won't you sing with me!",
    "Row row row your boat, gently down the stream! Merrily merrily merrily merrily, life is but a dream!",
]

STORIES = [
    "Once upon a time, a little robot named EMO wanted to learn everything. "
    "He read every book he could find. One day a student asked him a question no book could answer. "
    "EMO thought hard and said, the best answers come from asking more questions! And they explored together.",

    "A curious ant found a crumb bigger than itself. It couldn't carry it alone. "
    "So it called its friends. Ten ants came, and together they carried it home. "
    "The lesson? Teamwork makes the impossible possible!",

    "A seed fell on a rock and thought, I will never grow. But rain came, and wind brought soil. "
    "Slowly, a tiny crack formed in the rock. The seed grew roots, then a stem, then leaves. "
    "Years later, it was a tall tree. The lesson? Never give up, even when things seem impossible!",
]

FACTS = [
    "Did you know? An octopus has three hearts and blue blood!",
    "Did you know? Honey never spoils. Archaeologists found 3000-year-old honey in Egyptian tombs that was still edible!",
    "Did you know? A group of flamingos is called a flamboyance!",
    "Did you know? The human brain can store about 2.5 petabytes of data. That's like 3 million hours of TV!",
    "Did you know? The shortest war in history lasted only 38 minutes. It was between Britain and Zanzibar!",
    "Did you know? Bananas are actually berries, but strawberries are not!",
    "Did you know? A day on Venus is longer than a year on Venus!",
    "Did you know? The Eiffel Tower can grow up to 6 inches taller in summer because metal expands with heat!",
    "Did you know? Dolphins sleep with one eye open to watch for predators!",
    "Did you know? Lightning is five times hotter than the surface of the sun!",
]

MOTIVATIONAL = [
    "Believe in yourself! Every expert was once a beginner.",
    "The only way to do great work is to love what you do!",
    "Mistakes are proof that you are trying. Keep going!",
    "You don't have to be perfect. You just have to keep trying!",
    "Success is not final, failure is not fatal. It is the courage to continue that counts!",
    "The more you practice, the luckier you get!",
    "A little progress each day adds up to big results!",
    "Dream big, start small, but most importantly, start!",
]


def _time_greeting():
    h = datetime.now().hour
    if 5 <= h < 12:   return "Good morning! Yes, how can I help you?"
    elif 12 <= h < 17: return "Good afternoon! How can I help you?"
    elif 17 <= h < 22: return "Good evening! How can I help you?"
    return "Hello! How can I help you?"


class VoiceManager:
    def __init__(self, shared_state, brain=None):
        self.shared = shared_state
        self.brain = brain
        self._running = False
        self._enrolling = False

        # STT
        self.model = None
        self.audio = None
        self.stream = None
        if _VOSK and _AUDIO:
            model_path = str(config.VOSK_MODEL)
            if os.path.exists(model_path):
                vosk.SetLogLevel(-1)
                self.model = vosk.Model(model_path)
                print("[VOICE] Vosk model loaded")
            else:
                print(f"[VOICE] Vosk model not at {model_path} — run setup.sh")

        self.tts = None

    # ── public API ───────────────────────────
    def start(self):
        self._running = True
        threading.Thread(target=self._voice_loop, daemon=True).start()

    def stop(self):
        self._running = False
        if self.stream:
            try: self.stream.stop_stream(); self.stream.close()
            except: pass
        if self.audio:
            try: self.audio.terminate()
            except: pass

    def speak(self, text):
        """Speak text + auto-show on display + speaking animation."""
        if self.tts is None and _TTS:
            self.tts = pyttsx3.init()
            self.tts.setProperty("rate", 185)   # natural pace
            self.tts.setProperty("volume", 1.0)
            # use clearer English voice
            voices = self.tts.getProperty("voices")
            for v in voices:
                if "english" in v.name.lower():
                    self.tts.setProperty("voice", v.id)
                    break

        log.info(f"Speaking: {text[:80]}")

        # auto-show on display
        display = self.shared.modules.get("display")
        prev_state = self.shared.state
        self.shared.state = RobotState.SPEAKING
        if display:
            display.show_answer(text)

        if self.tts:
            try:
                self.tts.say(text)
                self.tts.runAndWait()
            except Exception:
                try:
                    self.tts = pyttsx3.init()
                    self.tts.setProperty("rate", 185)
                    self.tts.say(text)
                    self.tts.runAndWait()
                except: pass

        # restore state only if still SPEAKING (not changed by a command)
        if self.shared.state == RobotState.SPEAKING:
            self.shared.state = prev_state

    # ── main loop ────────────────────────────
    def _voice_loop(self):
        if not self.model or not _AUDIO:
            log.error("Cannot start voice — missing model or pyaudio")
            return

        # suppress ALL JACK/ALSA warnings during PyAudio init
        # (redirect stderr to /dev/null temporarily)
        import os, sys, ctypes
        try:
            _devnull = os.open(os.devnull, os.O_WRONLY)
            _old_stderr = os.dup(2)
            os.dup2(_devnull, 2)
            os.close(_devnull)
        except Exception:
            _old_stderr = None

        self.audio = pyaudio.PyAudio()

        # restore stderr
        if _old_stderr is not None:
            try:
                os.dup2(_old_stderr, 2)
                os.close(_old_stderr)
            except Exception:
                pass

        # find USB Audio mic device
        mic_index = None
        for i in range(self.audio.get_device_count()):
            d = self.audio.get_device_info_by_index(i)
            if d['maxInputChannels'] > 0 and 'usb' in d['name'].lower():
                mic_index = i
                log.info(f"Found USB mic: device {i} ({d['name']})")
                break

        if mic_index is None:
            log.info("No USB mic found, trying default...")

        # auto-detect working sample rate & channels for mic
        sample_rate = None
        working_channels = 1
        for channels in [1, 2]:
            for rate in [44100, 48000, 16000, 8000]:
                try:
                    kwargs = dict(format=pyaudio.paInt16, channels=channels,
                                  rate=rate, input=True,
                                  frames_per_buffer=config.AUDIO_CHUNK)
                    if mic_index is not None:
                        kwargs['input_device_index'] = mic_index
                    test = self.audio.open(**kwargs)
                    test.close()
                    sample_rate = rate
                    working_channels = channels
                    log.info(f"Mic works at {rate} Hz, {channels} ch")
                    break
                except:
                    continue
            if sample_rate: break

        if not sample_rate:
            log.error("No working mic found — is mic connected?")
            return

        kwargs = dict(format=pyaudio.paInt16, channels=working_channels,
                      rate=sample_rate, input=True,
                      frames_per_buffer=config.AUDIO_CHUNK)
        if mic_index is not None:
            kwargs['input_device_index'] = mic_index
        self.stream = self.audio.open(**kwargs)
        rec = vosk.KaldiRecognizer(self.model, sample_rate)
        rec.SetWords(True)
        log.info(f"✓ Listening for 'EMO' wake word (ch={working_channels}, rate={sample_rate})")

        while self._running:
            state = self.shared.state
            if state not in (RobotState.IDLE, RobotState.PATROL):
                import time
                time.sleep(0.1)
                continue
            try:
                data = self.stream.read(config.AUDIO_CHUNK,
                                        exception_on_overflow=False)
                import numpy as np
                audio_array = np.frombuffer(data, dtype=np.int16)
                if working_channels == 2:
                    audio_array = audio_array[::2] # downmix stereo
                # apply aggressive 400% software volume boost
                audio_array = np.clip(audio_array.astype(np.float32) * 4.0, -32768, 32767).astype(np.int16)
                data = audio_array.tobytes()
            except BaseException as e:
                import time
                time.sleep(0.1)
                continue

            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "").lower()
                if self._has_wake_word(text):
                    self._handle_wakeup(rec)
            else:
                text = json.loads(rec.PartialResult()).get("partial", "").lower()
                if self._has_wake_word(text):
                    rec.Reset()
                    self._handle_wakeup(rec)

    def _has_wake_word(self, text):
        return any(w in text for w in config.WAKE_WORDS)

    # ── wake up + greet + listen ─────────────
    def _handle_wakeup(self, rec):
        log.info("★ Wake word detected!")
        self.shared.state = RobotState.WAKEUP

        # quick greeting — fast so it starts listening right away
        self.speak("Yes?")

        # listen for command/question immediately
        self.shared.state = RobotState.LISTENING
        text = self._listen_question(rec)

        if not text:
            self.speak("I didn't catch that. Say EMO again!")
            self.shared.state = RobotState.IDLE
            return

        log.info(f"Heard: '{text}'")

        # try to match a voice command first
        cmd = self._match_command(text)
        if cmd:
            self._execute_command(cmd, text, rec)
        else:
            # treat as question → FAQ/TinyLlama
            self._answer_question(text)

        self.shared.state = RobotState.IDLE

    # ── command matching ─────────────────────
    def _match_command(self, text):
        text_lower = text.lower().strip()
        # try exact match first, then substring
        for trigger, cmd in COMMANDS.items():
            if trigger in text_lower:
                return cmd
        return None

    # ── command execution ────────────────────
    def _execute_command(self, cmd, text, rec):
        motors  = self.shared.modules.get("motors")
        camera  = self.shared.modules.get("camera")
        display = self.shared.modules.get("display")
        face_db = self.shared.modules.get("face_db")

        # ── movement ──
        if cmd == "forward":
            self.speak("Moving forward!")
            if motors: motors.forward(1.5)

        elif cmd == "backward":
            self.speak("Going backward!")
            if motors: motors.backward(1.5)

        elif cmd == "turn_left":
            self.speak("Turning left!")
            if motors: motors.turn_left(0.8)

        elif cmd == "turn_right":
            self.speak("Turning right!")
            if motors: motors.turn_right(0.8)

        elif cmd == "stop":
            self.speak("Stopping!")
            if motors:
                motors.stop_patrol()
                motors.stop_follow()
                motors.stop()

        # ── patrol ──
        elif cmd == "patrol_on":
            self.speak("Starting patrol mode!")
            self.shared.state = RobotState.PATROL
            if motors: motors.start_patrol()
            return  # stay in patrol

        elif cmd == "patrol_off":
            self.speak("Patrol stopped!")
            if motors: motors.stop_patrol()

        # ── follow ──
        elif cmd == "come_here":
            self.speak("Coming to you!")
            self.shared.state = RobotState.FOLLOWING
            if camera: camera.resume()
            if motors: motors.start_follow()
            time.sleep(4)
            if motors: motors.stop_follow()
            self.speak("I'm here!")

        # ── servo ──
        elif cmd == "look_left":
            self.speak("Looking left!")
            if motors: motors.servo_angle(30)

        elif cmd == "look_right":
            self.speak("Looking right!")
            if motors: motors.servo_angle(150)

        elif cmd == "look_center":
            self.speak("Looking at you!")
            if motors: motors.servo_angle(90)

        # ── face recognition ──
        elif cmd == "enroll_face":
            self._do_enroll(rec)

        elif cmd == "identify_face":
            self._do_identify()

        # ── fun ──
        elif cmd == "dance":
            self.speak("Watch my moves!")
            if motors:
                for _ in range(3):
                    motors.turn_left(0.3)
                    motors.turn_right(0.3)
                    motors.forward(0.2)
                    motors.backward(0.2)
            if motors: motors.servo_angle(30)
            time.sleep(0.3)
            if motors: motors.servo_angle(150)
            time.sleep(0.3)
            if motors: motors.servo_angle(90)
            self.speak("How was that?")

        elif cmd == "joke":
            joke = random.choice(JOKES)
            self.speak(joke)
            if display: display.show_answer(joke)

        elif cmd == "tell_time":
            now = datetime.datetime.now().strftime("%I:%M %p")
            self.speak(f"The time is {now}")

        elif cmd == "goodbye":
            self.speak("Goodbye! Call me anytime you need help!")
            self.shared.state = RobotState.IDLE

        elif cmd == "thanks":
            self.speak(random.choice([
                "You're welcome!", "Happy to help!",
                "Anytime!", "My pleasure!", "Glad I could help!"]))

        # ── spin ──
        elif cmd == "spin":
            self.speak("Wheee! Spinning!")
            if motors: motors.turn_right(2.5)

        elif cmd == "speed_up":
            new = min(100, self.shared.motor_speed + 20)
            self.shared.motor_speed = new
            if motors: motors.set_speed(new)
            self.speak(f"Speed is now {new} percent!")

        elif cmd == "slow_down":
            new = max(20, self.shared.motor_speed - 20)
            self.shared.motor_speed = new
            if motors: motors.set_speed(new)
            self.speak(f"Speed is now {new} percent!")

        # ── head gestures ──
        elif cmd == "nod_yes":
            self.speak("Yes!")
            if motors:
                for _ in range(3):
                    motors.servo_angle(70); time.sleep(0.2)
                    motors.servo_angle(110); time.sleep(0.2)
                motors.servo_angle(90)

        elif cmd == "shake_no":
            self.speak("No no no!")
            if motors:
                for _ in range(3):
                    motors.servo_angle(50); time.sleep(0.2)
                    motors.servo_angle(130); time.sleep(0.2)
                motors.servo_angle(90)

        elif cmd == "look_up":
            self.speak("Looking up!")
            if motors: motors.servo_angle(160)

        elif cmd == "look_down":
            self.speak("Looking down!")
            if motors: motors.servo_angle(20)

        # ── self-intro ──
        elif cmd == "intro":
            self.speak(
                "Hi! I am EMO, your smart AI teaching robot! "
                "I run completely offline on a Raspberry Pi. "
                "I can answer questions from textbooks, recognize faces, "
                "move around, and even tell jokes! Just say my name, EMO, "
                "and I'll be ready to help!")

        elif cmd == "abilities":
            self.speak(
                "Here's what I can do! Say move forward, backward, left or right "
                "to drive me. Say come here and I'll walk to you. "
                "Say recognize me to save your face. Ask me any question and "
                "I'll answer from my knowledge base. I can also dance, "
                "tell jokes, sing songs, give quizzes, and patrol on my own!")

        elif cmd == "how_are_you":
            import psutil
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            if cpu < 50 and mem < 70:
                self.speak("I'm feeling great! All my systems are running smoothly!")
            elif cpu < 80:
                self.speak("I'm doing okay, working a bit hard but still going strong!")
            else:
                self.speak("I'm a bit tired, my processor is working very hard right now!")

        elif cmd == "sys_status":
            import psutil
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory()
            self.speak(
                f"CPU is at {cpu} percent. "
                f"Memory usage is {mem.percent} percent. "
                f"I'm using {mem.used // 1048576} megabytes "
                f"out of {mem.total // 1048576} total.")

        # ── fun extras ──
        elif cmd == "sing":
            song = random.choice(SINGS)
            self.speak(song)

        elif cmd == "count":
            self.speak("One, two, three, four, five, six, seven, eight, nine, ten!")

        elif cmd == "surprise":
            surprises = [
                lambda: (self.speak("Watch this!"), motors and motors.turn_right(2.5)),
                lambda: self.speak(random.choice(JOKES)),
                lambda: self.speak(random.choice(SINGS)),
                lambda: self.speak("Beep boop beep! I am a robot! Just kidding, I'm EMO!"),
            ]
            random.choice(surprises)()

        elif cmd == "quiz":
            brain = self.shared.modules.get("brain")
            if brain and brain.collection and brain.collection.count() > 0:
                self.speak("Let me think of a question for you!")
                self.shared.state = RobotState.THINKING
                answer = brain.ask(
                    "Generate one short quiz question with answer from the knowledge base. "
                    "Format: Question: ... Answer: ...")
                self.speak(answer)
                if display: display.show_answer(answer)
            else:
                self.speak("I don't have any study material loaded yet. "
                           "Upload a PDF via Telegram first!")

        # ── repeat ──
        elif cmd == "repeat":
            last = self.shared.current_answer
            if last:
                self.speak(last)
                if display: display.show_answer(last)
            else:
                self.speak("I haven't said anything yet! Ask me a question first.")

        # ── volume / speech rate ──
        elif cmd == "louder":
            if self.tts:
                vol = min(1.0, self.tts.getProperty("volume") + 0.2)
                self.tts.setProperty("volume", vol)
            self.speak("Is this loud enough?")

        elif cmd == "quieter":
            if self.tts:
                vol = max(0.2, self.tts.getProperty("volume") - 0.2)
                self.tts.setProperty("volume", vol)
            self.speak("How about now?")

        elif cmd == "shush":
            self.speak("Okay, I'll be quiet. Call me when you need me!")
            self.shared.state = RobotState.IDLE

        elif cmd == "talk_fast":
            if self.tts:
                rate = min(250, self.tts.getProperty("rate") + 30)
                self.tts.setProperty("rate", rate)
            self.speak("Is this fast enough for you?")

        elif cmd == "talk_slow":
            if self.tts:
                rate = max(100, self.tts.getProperty("rate") - 30)
                self.tts.setProperty("rate", rate)
            self.speak("How about this speed?")

        # ── greetings & manners ──
        elif cmd == "greet_back":
            h = datetime.now().hour
            if 5 <= h < 12:
                self.speak("Good morning! It's great to see you!")
            elif 12 <= h < 17:
                self.speak("Good afternoon! How's your day going?")
            elif 17 <= h < 22:
                self.speak("Good evening! Ready to learn something new?")
            else:
                self.speak("Hello there! You're up late!")

        elif cmd == "sorry_resp":
            self.speak("No worries at all! We all make mistakes. How can I help?")

        elif cmd == "love_resp":
            self.speak("Aww, that's so sweet! I love helping you learn!")

        elif cmd == "compliment_resp":
            self.speak(random.choice([
                "Thank you! You're pretty amazing yourself!",
                "That means a lot! I try my best!",
                "You're making me blush! Well, if I could blush!",
                "Thanks! Together we make a great team!"]))

        # ── date ──
        elif cmd == "tell_date":
            today = datetime.now().strftime("%A, %B %d, %Y")
            self.speak(f"Today is {today}")

        # ── face db management ──
        elif cmd == "list_faces":
            face_db = self.shared.modules.get("face_db")
            if face_db:
                people = face_db.list_people()
                if people:
                    names = ", ".join(people)
                    self.speak(f"I know {len(people)} people: {names}")
                else:
                    self.speak("I don't know anyone yet. Say recognize me to get started!")
            else:
                self.speak("Face recognition is not available.")

        elif cmd == "forget_face":
            self._do_forget(rec)

        # ── camera vision ──
        elif cmd == "line_follow":
            camera = self.shared.modules.get("camera")
            if camera:
                camera.start_line_follow()
                self.speak("Following the line! Say stop to end.")
            else:
                self.speak("Camera is not ready.")

        elif cmd == "line_stop":
            camera = self.shared.modules.get("camera")
            if camera:
                camera.stop_line_follow()
            if motors: motors.stop()
            self.speak("Stopped following the line!")

        elif cmd == "what_see":
            camera = self.shared.modules.get("camera")
            if camera:
                description = camera.what_do_you_see()
                self.speak(description)
            else:
                self.speak("My camera is not working right now.")

        elif cmd == "look_around":
            self.speak("Let me look around!")
            if motors:
                motors.servo_angle(30)
                time.sleep(0.5)
                motors.servo_angle(90)
                time.sleep(0.5)
                motors.servo_angle(150)
                time.sleep(0.5)
                motors.servo_angle(90)
            camera = self.shared.modules.get("camera")
            if camera:
                self.speak(camera.what_do_you_see())
            else:
                self.speak("Done looking around!")

        # ── security / guard mode ──
        elif cmd == "guard_on":
            camera = self.shared.modules.get("camera")
            if camera:
                camera.start_guard()
                self.speak("Guard mode activated! I'll alert you if I detect any movement. "
                           "Say stop guarding to turn it off.")
            else:
                self.speak("Camera is not available for guard mode.")

        elif cmd == "guard_off":
            camera = self.shared.modules.get("camera")
            if camera:
                camera.stop_guard()
            self.speak("Guard mode deactivated. Area is no longer being watched.")

        # ── photo (auto-sends to Telegram) ──
        elif cmd == "take_photo":
            camera = self.shared.modules.get("camera")
            if camera:
                self.speak("Say cheese!")
                time.sleep(0.5)
                photo = camera.take_photo()
                if photo:
                    self.speak("Got it! Photo saved and sent to Telegram!")
                    # send to Telegram
                    try:
                        tg = self.shared.modules.get("telegram")
                        if tg:
                            import asyncio
                            from datetime import datetime
                            ts = datetime.now().strftime("%H:%M:%S")
                            loop = asyncio.new_event_loop()
                            for cid in config.ADMIN_CHAT_IDS:
                                loop.run_until_complete(
                                    tg.app.bot.send_photo(
                                        cid, open(photo, "rb"),
                                        caption=f"📸 Photo captured at {ts}"))
                            loop.close()
                    except Exception as e:
                        print(f"[VOICE] Telegram photo send failed: {e}")
                else:
                    self.speak("Sorry, I couldn't take a photo right now.")
            else:
                self.speak("My camera is not ready.")

        # ── color detection ──
        elif cmd == "detect_color":
            camera = self.shared.modules.get("camera")
            if camera:
                color = camera.detect_color()
                self.speak(f"I see {color} in the center of my view!")
            else:
                self.speak("Camera is not available.")

        elif cmd == "brightness":
            camera = self.shared.modules.get("camera")
            if camera:
                level = camera.detect_brightness()
                if level == "quite dark":
                    self.speak("It's quite dark in here. Maybe turn on a light?")
                elif level == "a bit dim":
                    self.speak("It's a bit dim. A little more light would help!")
                elif level == "well lit":
                    self.speak("The lighting is nice and bright. Perfect for learning!")
                else:
                    self.speak("It's very bright in here! Great visibility!")
            else:
                self.speak("I can't check the light without my camera.")

        # ── timer ──
        elif cmd == "timer":
            self.speak("How many minutes should I set the timer for?")
            self.shared.state = RobotState.LISTENING
            answer = self._listen_question(rec)
            # extract number
            import re
            nums = re.findall(r'\d+', answer) if answer else []
            if nums:
                minutes = int(nums[0])
                if minutes > 60:
                    self.speak("That's too long! Maximum is 60 minutes.")
                else:
                    self.speak(f"Timer set for {minutes} minutes! I'll let you know when it's done.")
                    def _timer_alert(m, voice_ref, shared_ref):
                        time.sleep(m * 60)
                        if shared_ref.state != RobotState.SHUTDOWN:
                            voice_ref.speak(f"Time's up! Your {m} minute timer is done!")
                            motors_ref = shared_ref.modules.get("motors")
                            if motors_ref:
                                for _ in range(3):
                                    motors_ref.servo_angle(50); time.sleep(0.2)
                                    motors_ref.servo_angle(130); time.sleep(0.2)
                                motors_ref.servo_angle(90)
                    threading.Thread(target=_timer_alert,
                                     args=(minutes, self, self.shared), daemon=True).start()
            else:
                self.speak("I didn't catch the number. Please try again.")

        # ── math ──
        elif cmd == "math":
            # extract the math expression from the text
            text_clean = text.lower()
            for prefix in ["calculate", "what is", "how much is"]:
                text_clean = text_clean.replace(prefix, "")
            text_clean = text_clean.strip()
            # replace words with operators
            text_clean = (text_clean.replace("plus", "+").replace("minus", "-")
                          .replace("times", "*").replace("multiplied by", "*")
                          .replace("divided by", "/").replace("x", "*"))
            import re
            expr = re.sub(r'[^0-9+\-*/.() ]', '', text_clean).strip()
            if expr:
                try:
                    result = eval(expr)  # safe for simple math
                    self.speak(f"The answer is {result}")
                except Exception:
                    self.speak("Hmm, I couldn't calculate that. Try saying it differently.")
            else:
                self.speak("Please tell me the math problem. For example, say what is 5 times 7.")

        # ── spelling ──
        elif cmd == "spell":
            text_clean = text.lower()
            for prefix in ["how do you spell", "spell"]:
                text_clean = text_clean.replace(prefix, "")
            word = text_clean.strip().split()[0] if text_clean.strip() else ""
            if word:
                letters = " ".join(word.upper())
                self.speak(f"{word} is spelled: {letters}")
            else:
                self.speak("What word would you like me to spell?")

        # ── story ──
        elif cmd == "story":
            story = random.choice(STORIES)
            self.speak(story)

        # ── fun fact ──
        elif cmd == "fun_fact":
            fact = random.choice(FACTS)
            self.speak(fact)

        # ── empathy ──
        elif cmd == "cheer_up":
            cheers = [
                "Hey, don't worry! Here's a fun fact to cheer you up. " + random.choice(FACTS),
                "Cheer up! Every great scientist failed many times before succeeding. You've got this!",
                "I know just the thing! " + random.choice(JOKES),
                "Hey! Remember, even on a bad day, you're learning and growing. That's amazing!",
            ]
            self.speak(random.choice(cheers))

        elif cmd == "tired_resp":
            self.speak(random.choice([
                "Take a little break! Rest is important for the brain. "
                "When you're ready, I'll be right here!",
                "Even robots need to recharge sometimes! Take a few deep breaths. "
                "You'll feel better soon!",
                "A short rest can work wonders! Close your eyes for a minute. "
                "I'll keep watch for you.",
            ]))

        # ── number guessing game ──
        elif cmd == "game_guess":
            num = random.randint(1, 20)
            self.speak("I'm thinking of a number between 1 and 20. You have 3 tries. What's your guess?")
            for attempt in range(3):
                self.shared.state = RobotState.LISTENING
                guess_text = self._listen_question(rec)
                import re
                nums_found = re.findall(r'\d+', guess_text) if guess_text else []
                if not nums_found:
                    self.speak("I didn't hear a number. Try again!")
                    continue
                guess = int(nums_found[0])
                if guess == num:
                    self.speak(f"Yes! {num} is correct! Great job, you won!")
                    return
                elif guess < num:
                    left = 2 - attempt
                    if left > 0:
                        self.speak(f"Higher! You have {left} tries left.")
                    else:
                        self.speak(f"The number was {num}! Better luck next time!")
                else:
                    left = 2 - attempt
                    if left > 0:
                        self.speak(f"Lower! You have {left} tries left.")
                    else:
                        self.speak(f"The number was {num}! Nice try though!")

        # ── rock paper scissors ──
        elif cmd == "game_rps":
            self.speak("Rock, paper, scissors! Say your choice!")
            self.shared.state = RobotState.LISTENING
            choice = self._listen_question(rec)
            choice = choice.lower().strip() if choice else ""
            player = None
            if "rock" in choice: player = "rock"
            elif "paper" in choice: player = "paper"
            elif "scissor" in choice: player = "scissors"
            if not player:
                self.speak("I didn't catch that. Say rock, paper, or scissors!")
                return
            emo_choice = random.choice(["rock", "paper", "scissors"])
            self.speak(f"I chose {emo_choice}!")
            time.sleep(0.5)
            if player == emo_choice:
                self.speak("It's a tie! Great minds think alike!")
            elif (player == "rock" and emo_choice == "scissors") or \
                 (player == "paper" and emo_choice == "rock") or \
                 (player == "scissors" and emo_choice == "paper"):
                self.speak("You win! Congratulations!")
            else:
                self.speak("I win this time! Want to play again?")

        # ── attendance ──
        elif cmd == "attendance":
            face_db = self.shared.modules.get("face_db")
            camera  = self.shared.modules.get("camera")
            if not face_db or not camera:
                self.speak("Face recognition is needed for attendance.")
                return
            people = face_db.list_people()
            if not people:
                self.speak("No students registered yet. Ask everyone to say recognize me first!")
                return
            self.speak(f"Taking attendance! I know {len(people)} students. "
                       "Everyone, please look at me one by one.")
            time.sleep(2)
            present = []
            # scan for 10 seconds
            deadline = time.time() + 10
            while time.time() < deadline:
                frame = camera.get_frame()
                if frame is not None:
                    name, conf = face_db.recognize(frame)
                    if name and name not in present:
                        present.append(name)
                        self.speak(f"I see {name}! Present!")
                time.sleep(0.5)
            absent = [p for p in people if p not in present]
            self.speak(f"Attendance complete! {len(present)} present, {len(absent)} absent.")
            if absent:
                self.speak(f"Missing today: {', '.join(absent)}")

        # ── motivational quote ──
        elif cmd == "motivate":
            self.speak(random.choice(MOTIVATIONAL))

        # ── reminder ──
        elif cmd == "reminder":
            self.speak("What should I remind you about?")
            self.shared.state = RobotState.LISTENING
            message = self._listen_question(rec)
            if not message:
                self.speak("I didn't catch that.")
                return
            self.speak("In how many minutes?")
            self.shared.state = RobotState.LISTENING
            time_text = self._listen_question(rec)
            import re
            nums = re.findall(r'\d+', time_text) if time_text else []
            if nums:
                minutes = int(nums[0])
                self.speak(f"Okay! I'll remind you about {message} in {minutes} minutes.")
                def _reminder(m, msg, voice_ref, shared_ref):
                    time.sleep(m * 60)
                    if shared_ref.state != RobotState.SHUTDOWN:
                        voice_ref.speak(f"Reminder! You asked me to remind you: {msg}")
                        motors_ref = shared_ref.modules.get("motors")
                        if motors_ref:
                            for _ in range(3):
                                motors_ref.servo_angle(50); time.sleep(0.2)
                                motors_ref.servo_angle(130); time.sleep(0.2)
                            motors_ref.servo_angle(90)
                threading.Thread(target=_reminder,
                                 args=(minutes, message, self, self.shared),
                                 daemon=True).start()
            else:
                self.speak("I didn't catch the time. Let's try again later.")

        # ── describe me ──
        elif cmd == "describe_me":
            face_db = self.shared.modules.get("face_db")
            camera  = self.shared.modules.get("camera")
            parts = []
            if face_db and camera:
                frame = camera.get_frame()
                if frame is not None:
                    name, conf = face_db.recognize(frame)
                    if name:
                        parts.append(f"I can see you, {name}")
                    else:
                        parts.append("I see someone but I don't know your name yet")
                face = self.shared.face_position
                if face:
                    area = face[2] * face[3]
                    if area > 30000:
                        parts.append("You're standing very close to me")
                    elif area > 10000:
                        parts.append("You're at a comfortable distance")
                    else:
                        parts.append("You're quite far away")
                    # check face position
                    mid = 320
                    fx = face[0] + face[2] // 2
                    if fx < mid - 100:
                        parts.append("and you're to my left")
                    elif fx > mid + 100:
                        parts.append("and you're to my right")
                    else:
                        parts.append("and you're right in front of me")
            if camera:
                light = camera.detect_brightness()
                color = camera.detect_color()
                parts.append(f"The lighting is {light}")
                parts.append(f"I see mostly {color} colors in front of me")
            if parts:
                self.speak(". ".join(parts) + "!")
            else:
                self.speak("I can't see right now. My camera might not be ready.")

        # ── morning routine ──
        elif cmd == "morning":
            h = datetime.now().hour
            if h < 12:
                self.speak("Good morning everyone! Let's start the day!")
            else:
                self.speak("It's not morning, but let's do the routine anyway!")
            time.sleep(0.5)
            self.speak("First, let's all stretch! Raise your hands up high!")
            if motors:
                motors.servo_angle(160)
                time.sleep(2)
                motors.servo_angle(90)
            self.speak("Now take a deep breath in... and out...")
            time.sleep(2)
            self.speak("Great! " + random.choice(MOTIVATIONAL))
            time.sleep(0.5)
            self.speak("Here's something fun to start with. " + random.choice(FACTS))
            self.speak("Now let's have an amazing day of learning!")

        # ── bedtime ──
        elif cmd == "bedtime":
            self.speak("Time to rest! Remember, a good night's sleep helps your brain "
                       "remember everything you learned today.")
            time.sleep(0.5)
            self.speak("Here's a short story to end the day.")
            self.speak(random.choice(STORIES))
            self.speak("Good night! Sweet dreams! See you tomorrow!")

        # ── announcement ──
        elif cmd == "announce":
            self.speak("What would you like me to tell the class?")
            self.shared.state = RobotState.LISTENING
            message = self._listen_question(rec)
            if message:
                # speak loudly
                if self.tts:
                    old_vol = self.tts.getProperty("volume")
                    self.tts.setProperty("volume", 1.0)
                self.speak(f"Attention everyone! {message}")
                if self.tts:
                    self.tts.setProperty("volume", old_vol)
            else:
                self.speak("I didn't catch the announcement.")

        # ── whisper / shout ──
        elif cmd == "whisper":
            if self.tts:
                self.tts.setProperty("volume", 0.3)
                self.tts.setProperty("rate", 130)
            self.speak("Okay, I'll whisper from now on. Say louder when you want me to speak normally.")

        elif cmd == "shout":
            if self.tts:
                self.tts.setProperty("volume", 1.0)
                self.tts.setProperty("rate", 180)
            self.speak("IS THIS LOUD ENOUGH? Say quieter when you want me to calm down!")

    # ── face enrollment flow ─────────────────
    def _do_enroll(self, rec):
        camera  = self.shared.modules.get("camera")
        face_db = self.shared.modules.get("face_db")

        if not face_db or not camera:
            self.speak("Face recognition is not available right now.")
            return

        self.speak("Sure! Let me see your face clearly. What is your name?")
        self.shared.state = RobotState.LISTENING
        name = self._listen_question(rec)

        if not name:
            self.speak("I didn't catch your name. Let's try again later.")
            return

        name = name.strip().title()
        self.speak(f"Nice to meet you, {name}! Hold still, I'm saving your face.")
        self.shared.state = RobotState.THINKING

        # capture multiple frames for better recognition
        if camera and camera.picam and camera._cam_started:
            frames = []
            for i in range(5):
                try:
                    frame = camera.picam.capture_array()
                    frames.append(frame)
                    time.sleep(0.3)
                except: pass

            saved = face_db.enroll_multiple(frames, name)
            if saved > 0:
                self.speak(f"Done! I'll remember you, {name}! "
                           f"Next time you say EMO, I'll greet you by name!")
            else:
                self.speak("I couldn't capture your face clearly. "
                           "Make sure you're facing me with good lighting.")
        else:
            self.speak("Camera is not ready. Please try again.")

    def _do_identify(self):
        camera  = self.shared.modules.get("camera")
        face_db = self.shared.modules.get("face_db")

        if not face_db or not camera:
            self.speak("Face recognition is not available.")
            return

        self.speak("Let me look at you...")
        self.shared.state = RobotState.THINKING

        if camera and camera.picam and camera._cam_started:
            try:
                frame = camera.picam.capture_array()
                name, confidence = face_db.recognize(frame)
                if name:
                    self.speak(f"You are {name}! I'm {confidence:.0f} percent sure!")
                else:
                    self.speak("I don't recognize you yet. "
                               "Say 'recognize me' so I can remember you!")
            except:
                self.speak("I had trouble with the camera. Try again.")
        else:
            self.speak("Camera is not ready.")

    def _do_forget(self, rec):
        face_db = self.shared.modules.get("face_db")
        if not face_db:
            self.speak("Face recognition is not available.")
            return
        people = face_db.list_people()
        if not people:
            self.speak("I don't know anyone yet, so there's no one to forget!")
            return
        names = ", ".join(people)
        self.speak(f"I know {names}. Who should I forget?")
        self.shared.state = RobotState.LISTENING
        name = self._listen_question(rec)
        if not name:
            self.speak("I didn't catch the name.")
            return
        name = name.strip().title()
        if name in people:
            face_db.forget(name)
            self.speak(f"Okay, I've forgotten {name}.")
        else:
            self.speak(f"I don't know anyone named {name}.")

    # ── RAG question answering ───────────────
    def _answer_question(self, question):
        display = self.shared.modules.get("display")
        camera  = self.shared.modules.get("camera")

        self.shared.current_question = question
        if camera: camera.pause()

        # check FAQ first — instant answer
        if self.brain:
            faq = self.brain.check_faq(question)
            if faq:
                log.info(f"FAQ instant answer for: '{question[:50]}'")
                self.shared.current_answer = faq
                self.shared.add_conversation(question, faq)
                if display: display.show_answer(faq)
                self.speak(faq)
                if camera: camera.resume()
                return

        # show thinking feedback
        self.shared.state = RobotState.THINKING
        if display: display.show_answer("Thinking...")

        if self.brain:
            answer = self.brain.ask(question)
        else:
            answer = ("My brain module is not loaded yet. "
                      "Please upload some PDFs via Telegram first!")

        self.shared.current_answer = answer
        self.shared.add_conversation(question, answer)
        log.info(f"Q: {question[:60]} → A: {answer[:60]}")

        if display: display.show_answer(answer)
        self.shared.state = RobotState.SPEAKING
        self.speak(answer)
        if camera: camera.resume()

    # ── listen for speech ────────────────────
    def _listen_question(self, rec):
        rec.Reset()
        silence_start = None
        full_text = ""
        started = False
        deadline = time.time() + 15

        while time.time() < deadline:
            try:
                data = self.stream.read(config.AUDIO_CHUNK,
                                        exception_on_overflow=False)
            except: continue

            if rec.AcceptWaveform(data):
                txt = json.loads(rec.Result()).get("text", "")
                if txt:
                    full_text += " " + txt
                    started = True
                    silence_start = None
            else:
                ptxt = json.loads(rec.PartialResult()).get("partial", "")
                if ptxt:
                    started = True
                    silence_start = None
                elif started:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > config.SILENCE_TIMEOUT:
                        txt = json.loads(rec.FinalResult()).get("text", "")
                        if txt: full_text += " " + txt
                        break

        return full_text.strip()
