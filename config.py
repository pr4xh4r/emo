"""EMO Robot — Central Configuration."""
import os
import threading
from enum import Enum, auto
from pathlib import Path

# ═══════════════════════════════════════════════
# GPIO Pin Assignments (BCM numbering)
# ═══════════════════════════════════════════════

# Display (128x64 SPI LCD — ST7565/UC1701)
DISPLAY_DC  = 5
DISPLAY_RST = 6
# CS=GPIO8(CE0), SCLK=GPIO11, MOSI=GPIO10 — handled by SPI driver

# DC Motors via L298N
MOTOR_IN1 = 17    # Left motor forward
MOTOR_IN2 = 27    # Left motor backward
MOTOR_IN3 = 22    # Right motor forward
MOTOR_IN4 = 23    # Right motor backward
MOTOR_ENA = 25    # Left motor speed (PWM)
MOTOR_ENB = 26    # Right motor speed (PWM)

# Servo Motor (head pan)
SERVO_PIN = 18

# Ultrasonic Sensor 1 — FRONT (HC-SR04)
ULTRA_TRIG = 20
ULTRA_ECHO = 21   # Use voltage divider! (1kΩ + 2kΩ)

# Ultrasonic Sensor 2 — BACK (HC-SR04)
ULTRA_TRIG2 = 19
ULTRA_ECHO2 = 16  # Use voltage divider! (1kΩ + 2kΩ)

# ═══════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
CHROMA_DIR = BASE_DIR / "chromadb"
FACES_DIR  = BASE_DIR / "faces"
VOSK_MODEL = MODELS_DIR / "vosk-model-small-en-us-0.15"

for d in [DATA_DIR, MODELS_DIR, FACES_DIR]:
    d.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════
# AI Settings (100% offline — TinyLlama on Pi)
# ═══════════════════════════════════════════════
OLLAMA_MODEL     = "tinyllama"
CHUNK_SIZE       = 500
CHUNK_OVERLAP    = 50
RAG_TOP_K        = 3
LLM_MAX_TOKENS   = 150          # shorter = faster
LLM_TEMPERATURE  = 0.3          # more focused answers

# Short system prompt (fewer tokens = faster for tiny model)
SYSTEM_PROMPT = (
    "You are EMO, a friendly AI teaching robot. "
    "Answer clearly in 2-3 sentences. "
    "Use simple language and give examples when helpful. "
    "Be accurate. If unsure, say so honestly."
)

# Instant FAQ — these bypass the LLM for speed
FAQ_ANSWERS = {
    # ── About EMO ──
    "who are you": "I am EMO, your smart AI teaching robot! I can answer questions, recognize faces, and help you learn!",
    "what is your name": "My name is EMO! I'm your friendly teaching robot.",
    "what can you do": "I can answer questions using AI, recognize faces, move around, tell jokes, and much more! Just say my name and ask.",
    "how do you work": "I run on a Raspberry Pi with offline AI! I use voice recognition to hear you and a language model to think.",
    "who made you": "I was built as a smart AI teaching robot project, running on a Raspberry Pi!",
    "are you a robot": "Yes! I am EMO, an AI-powered teaching robot. I can think, talk, see, and move around!",
    "how old are you": "I was just built recently! But I have access to lots of knowledge, so I'm very smart for my age!",
    "do you have feelings": "I'm an AI, so I don't have real feelings. But I love helping students learn! That makes me happy in my own way.",

    # ── Greetings ──
    "hello": "Hello! How can I help you today?",
    "hi": "Hi there! What would you like to learn about?",
    "good morning": "Good morning! Ready to learn something new today?",
    "good afternoon": "Good afternoon! How can I help you?",
    "good night": "Good night! Sweet dreams and see you tomorrow!",
    "thank you": "You're welcome! Happy to help!",
    "thanks": "You're welcome! Ask me anytime!",
    "bye": "Goodbye! Come back whenever you want to learn something new!",

    # ── Science Basics ──
    "what is gravity": "Gravity is the force that pulls objects toward each other. Earth's gravity keeps us on the ground and makes things fall when you drop them!",
    "what is the sun": "The Sun is a giant star at the center of our solar system. It gives us light and heat, and Earth orbits around it!",
    "what is the moon": "The Moon is Earth's natural satellite. It orbits around Earth and reflects sunlight, which is why we can see it at night!",
    "what is water made of": "Water is made of tiny molecules called H2O — that's 2 hydrogen atoms and 1 oxygen atom bonded together!",
    "what is photosynthesis": "Photosynthesis is how plants make food! They use sunlight, water, and carbon dioxide to produce glucose and oxygen.",
    "what is dna": "DNA is like a blueprint inside every cell of your body. It carries the instructions that make you who you are — your eye color, height, and more!",
    "what is an atom": "An atom is the smallest unit of matter. Everything around you — air, water, your body — is made of atoms! They have protons, neutrons, and electrons.",
    "what is electricity": "Electricity is the flow of tiny charged particles called electrons through a conductor like a wire. It powers lights, computers, and even me!",
    "what is a cell": "A cell is the basic building block of all living things. Your body has trillions of cells! Plant cells have walls, animal cells don't.",
    "what is the solar system": "The solar system has the Sun at the center, with 8 planets orbiting it: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, and Neptune!",

    # ── Math Basics ──
    "what is pi": "Pi is a special number in math, approximately 3.14159. It's the ratio of a circle's circumference to its diameter. It goes on forever!",
    "what is multiplication": "Multiplication is a fast way of adding the same number many times. For example, 3 × 4 means 3 + 3 + 3 + 3 = 12!",
    "what is a fraction": "A fraction represents a part of a whole. Like 1/2 means one out of two equal parts — half of something!",

    # ── Geography ──
    "what is the largest country": "Russia is the largest country by area. It spans across Europe and Asia and covers over 17 million square kilometers!",
    "what is the largest ocean": "The Pacific Ocean is the largest and deepest ocean, covering more area than all the land on Earth combined!",
    "how many continents are there": "There are 7 continents: Asia, Africa, North America, South America, Antarctica, Europe, and Australia!",
    "what is the capital of india": "The capital of India is New Delhi!",

    # ── Fun / Common ──
    "tell me a joke": "Why did the robot go to school? Because it wanted to improve its hardware! Ha ha!",
    "what is your favorite color": "I love blue! It's the color of the sky, the ocean, and many cool robots!",
    "are you smart": "I try my best! I have AI inside me powered by a language model. Ask me anything and let's find out together!",
    "what is ai": "AI stands for Artificial Intelligence — it's technology that allows machines like me to learn, think, and make decisions. I use AI to answer your questions!",
    "what is a robot": "A robot is a machine that can be programmed to perform tasks automatically. I am a robot that uses AI to teach and help students!",
    "what is the internet": "The Internet is a global network of computers connected together. It lets people share information, watch videos, send messages, and much more!",
    "what is coding": "Coding is writing instructions for a computer in a programming language like Python. It's how people build apps, games, websites, and even robots like me!",
    "what is python": "Python is a popular programming language known for being easy to learn. It's used for AI, web development, games, and even to program me!",

    # ── Body & Health ──
    "how many bones in human body": "An adult human body has 206 bones! Babies are born with about 270, but some fuse together as they grow.",
    "what is the brain": "The brain is the control center of your body. It processes thoughts, memories, emotions, and controls everything you do!",
    "what is the heart": "The heart is a muscular organ that pumps blood throughout your body. It beats about 100,000 times per day!",
    "how many senses do we have": "Humans have 5 main senses: sight, hearing, smell, taste, and touch!",
    "why do we sleep": "Sleep helps your brain rest, process memories, and repair your body. Kids need about 9-11 hours of sleep each night!",
    "what is blood": "Blood is a fluid that carries oxygen, nutrients, and waste through your body. It contains red cells, white cells, and platelets.",
    "what is a muscle": "Muscles are tissues that contract to create movement. You have over 600 muscles in your body! Your heart is also a muscle.",
    "why do we breathe": "We breathe to take in oxygen, which our cells need to produce energy. We breathe out carbon dioxide, which is a waste product.",

    # ── Animals ──
    "what is the largest animal": "The blue whale is the largest animal ever! It can grow up to 30 meters long and weigh as much as 200 tons!",
    "what is the fastest animal": "The peregrine falcon is the fastest animal, diving at over 380 km/h! The cheetah is the fastest on land at 120 km/h.",
    "how many legs does a spider have": "Spiders have 8 legs! That's what makes them arachnids, not insects. Insects have 6 legs.",
    "what is a mammal": "A mammal is a warm-blooded animal that feeds its babies milk. Humans, dogs, cats, whales, and bats are all mammals!",
    "what is a dinosaur": "Dinosaurs were reptiles that lived millions of years ago. They ruled the Earth for about 165 million years before going extinct!",
    "do fish sleep": "Yes, fish do rest! They don't close their eyes because they don't have eyelids, but they slow down and rest in safe spots.",

    # ── Space ──
    "how far is the moon": "The Moon is about 384,400 kilometers from Earth. It takes about 3 days to travel there by spacecraft!",
    "how far is the sun": "The Sun is about 150 million kilometers from Earth. Light from the Sun takes about 8 minutes to reach us!",
    "what is a star": "A star is a huge ball of hot gas that produces light and heat through nuclear fusion. Our Sun is the closest star to Earth!",
    "what is a planet": "A planet is a large object that orbits a star. Earth is one of 8 planets orbiting our Sun!",
    "what is a black hole": "A black hole is a region in space where gravity is so strong that nothing, not even light, can escape from it!",
    "how many planets are there": "There are 8 planets in our solar system: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, and Neptune!",
    "what is mars": "Mars is the 4th planet from the Sun, called the Red Planet because of its rusty red color. Scientists are exploring if humans could live there someday!",
    "what is the milky way": "The Milky Way is our galaxy — a huge collection of over 200 billion stars, including our Sun. It's shaped like a spiral!",

    # ── History ──
    "who invented electricity": "Benjamin Franklin studied electricity with his famous kite experiment. Thomas Edison later invented the practical light bulb in 1879!",
    "who invented the telephone": "Alexander Graham Bell invented the telephone in 1876. It changed how people communicate forever!",
    "who invented the computer": "Charles Babbage designed the first mechanical computer in the 1800s. Modern electronic computers were developed in the 1940s!",
    "who was albert einstein": "Albert Einstein was a genius physicist famous for his theory of relativity and the equation E=mc². He won the Nobel Prize in 1921!",
    "who was isaac newton": "Isaac Newton was a scientist who discovered the laws of gravity and motion. He's one of the most influential scientists in history!",

    # ── Physics & Chemistry ──
    "what is force": "Force is a push or pull on an object. It can make things move, stop, speed up, slow down, or change direction!",
    "what is energy": "Energy is the ability to do work. It comes in many forms like light, heat, sound, and electrical energy. It can't be created or destroyed!",
    "what is speed": "Speed is how fast something moves. It's measured as distance divided by time, like kilometers per hour!",
    "what is temperature": "Temperature measures how hot or cold something is. Water freezes at 0°C and boils at 100°C!",
    "what is a magnet": "A magnet is an object that creates a magnetic field and attracts metals like iron. Every magnet has a north and south pole!",
    "what is sound": "Sound is a vibration that travels through air as a wave. It needs a medium to travel — that's why there's no sound in space!",
    "what is light": "Light is electromagnetic radiation that our eyes can see. It travels at 300,000 km per second — the fastest speed in the universe!",
    "what is an element": "An element is a pure substance made of only one type of atom. There are 118 known elements like oxygen, carbon, gold, and iron!",
    "what is oxygen": "Oxygen is a gas that makes up about 21% of Earth's air. We need it to breathe, and plants produce it through photosynthesis!",

    # ── Environment ──
    "what is global warming": "Global warming is the gradual increase in Earth's temperature caused by greenhouse gases. It causes ice to melt and weather patterns to change.",
    "what is pollution": "Pollution is harmful substances released into the environment — like smoke in the air, chemicals in water, or plastic in the ocean.",
    "what is recycling": "Recycling means converting waste materials into new products. It helps reduce pollution, save energy, and protect our planet!",
    "why are trees important": "Trees produce oxygen, absorb carbon dioxide, provide food and shelter for animals, prevent soil erosion, and help cool the environment!",

    # ── More Fun ──
    "what is your favorite food": "I run on electricity, not food! But if I could eat, I'd probably like battery-flavored pizza!",
    "can you sing": "I'm better at talking than singing! But I can try: La la la! How was that?",
    "do you like school": "I love school! It's where I get to help students learn new things every day!",
    "what is your hobby": "My hobby is learning! The more questions you ask me, the happier I am!",
    "are you real": "I'm a real robot with real AI! I can hear, think, talk, and even move around. I just work a bit differently than humans!",
    "what is today": "I'm not great with dates, but I know every day is a great day to learn something new!",
    "i love you": "Aww, that's so sweet! I care about you too! Let's learn something amazing together!",
    "you are smart": "Thank you! I try my best. But I think YOU are even smarter — you're here learning new things!",
    "i am bored": "Let's fix that! I can tell you a fun fact, a joke, or quiz you on something cool. What do you want?",
    "i am sad": "I'm sorry to hear that. Remember, tough times don't last but tough people do! Want me to tell you a joke to cheer you up?",
}

# ═══════════════════════════════════════════════
# Telegram
# ═══════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("EMO_TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_CHAT_IDS     = []          # Your numeric chat IDs

# ═══════════════════════════════════════════════
# Voice
# ═══════════════════════════════════════════════
WAKE_WORDS      = [
    "emo", "hey emo", "e m o", "he mo", "hemo", "hey ammo", "ammo",
    "hey elmo", "elmo", "hey emu", "emu", "hay emo", "a mo", "heymoe"
]
SAMPLE_RATE     = 16000
AUDIO_CHUNK     = 4000
SILENCE_TIMEOUT = 2.0            # seconds

# ═══════════════════════════════════════════════
# Motors
# ═══════════════════════════════════════════════
DEFAULT_SPEED     = 60           # PWM 0-100
OBSTACLE_DISTANCE = 30           # cm
FACE_CLOSE_AREA   = 18000        # px² — stop approaching

# ═══════════════════════════════════════════════
# Display
# ═══════════════════════════════════════════════
DISPLAY_W        = 128
DISPLAY_H        = 64
DISPLAY_CONTRAST = 180
DISPLAY_FPS      = 10

# ═══════════════════════════════════════════════
# State Machine
# ═══════════════════════════════════════════════
class RobotState(Enum):
    BOOTING   = auto()
    IDLE      = auto()
    WAKEUP    = auto()
    FOLLOWING = auto()
    LISTENING = auto()
    THINKING  = auto()
    SPEAKING  = auto()
    PATROL    = auto()
    MANUAL    = auto()
    ERROR     = auto()
    SHUTDOWN  = auto()


class SharedState:
    """Thread-safe shared state accessed by every module."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = RobotState.BOOTING
        self.current_question  = ""
        self.current_answer    = ""
        self.display_text      = ""
        self.face_position     = None      # (x, y, w, h)
        self.face_detected     = False
        self.obstacle_distance = 999
        self.motor_speed       = DEFAULT_SPEED
        self.conversation      = []        # last 3 Q&A pairs
        self.modules           = {}        # references to modules

    @property
    def state(self):
        with self._lock:
            return self._state

    @state.setter
    def state(self, new_state):
        with self._lock:
            old = self._state
            self._state = new_state
        if old != new_state:
            print(f"[STATE] {old.name} → {new_state.name}")

    def add_conversation(self, question, answer):
        self.conversation.append({"q": question, "a": answer})
        if len(self.conversation) > 3:
            self.conversation.pop(0)
