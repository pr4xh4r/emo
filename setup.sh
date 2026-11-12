#!/bin/bash
# ═══════════════════════════════════════════════
# EMO Robot — One-Shot Setup Script
# Run: bash setup.sh
# ═══════════════════════════════════════════════
set -e

echo "🤖 EMO Robot Setup"
echo "===================="

# 1. System packages
echo "[1/6] Installing system packages..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv \
    portaudio19-dev espeak libfreetype6-dev libjpeg-dev \
    libopenjp2-7 libopenblas-dev python3-picamera2

# 2. Python venv
echo "[2/6] Creating Python virtual environment..."
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate

# 3. Pip packages
echo "[3/6] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Vosk model
echo "[4/6] Downloading Vosk speech model (~40MB)..."
mkdir -p models
if [ ! -d "models/vosk-model-small-en-us-0.15" ]; then
    cd models
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
    unzip -q vosk-model-small-en-us-0.15.zip
    rm vosk-model-small-en-us-0.15.zip
    cd ..
fi

# 5. Enable SPI (for LCD display)
echo "[5/6] Enabling SPI interface..."
sudo raspi-config nonint do_spi 0 2>/dev/null || echo "SPI: set manually via raspi-config"

# 6. Swap (safety net for 4GB RAM)
echo "[6/6] Setting up swap (2GB)..."
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile 2>/dev/null || true
sudo dphys-swapfile setup 2>/dev/null || true
sudo dphys-swapfile swapon 2>/dev/null || true

# Create data directory
mkdir -p data

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Set your Telegram bot token in config.py"
echo "  2. Put PDFs in ~/emo/data/"
echo "  3. Make sure Ollama is running: ollama serve"
echo "  4. Run: source venv/bin/activate && python3 main.py"
echo ""
echo "🤖 EMO is ready to build!"
