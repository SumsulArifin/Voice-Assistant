FROM python:3.11-slim

# portaudio19-dev: build PyAudio; espeak: pyttsx3 TTS backend on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev portaudio19-dev espeak alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No mic/speaker by default in a container; --text --mute keeps it usable headless.
# Drop those flags (and pass through audio devices, see docker-compose.yml) for voice I/O.
CMD ["python", "-m", "assistant", "--text", "--mute"]
