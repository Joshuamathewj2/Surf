"""
core/config.py
Unified, environment-aware configuration for Surf. Every value can be overridden
with an environment variable so it can be tuned without touching code.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Local LLM (Ollama) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
OLLAMA_URL = os.getenv("OLLAMA_URL", f"{OLLAMA_HOST}/api/generate")
MODEL_NAME = os.getenv("SURF_LLM_MODEL", "llama3.2")
# Cold-loading a model can take 10-20 s on a laptop; the model is pre-warmed at startup.
LLM_TIMEOUT = float(os.getenv("SURF_LLM_TIMEOUT", "45"))
LLM_KEEP_ALIVE = os.getenv("SURF_LLM_KEEP_ALIVE", "30m")

# --- Automation ---
DELAY_BETWEEN_ACTIONS = float(os.getenv("SURF_ACTION_DELAY", "0.1"))
SCREENSHOT_DIR = os.getenv("SURF_SCREENSHOT_DIR", str(Path.home() / "Pictures" / "Surf"))
WINDOW_WAIT_SEC = float(os.getenv("SURF_WINDOW_WAIT", "5.0"))  # max wait for a launched app's window

# --- Speech recognition (faster-whisper) ---
VOICE_MODEL = os.getenv("SURF_VOICE_MODEL", "base.en")
VOICE_DEVICE = os.getenv("SURF_VOICE_DEVICE", "cpu")
VOICE_COMPUTE_TYPE = os.getenv("SURF_VOICE_COMPUTE", "int8")
# Segments whisper itself thinks are probably not speech are dropped.
NO_SPEECH_PROB_MAX = float(os.getenv("SURF_NO_SPEECH_MAX", "0.6"))
AVG_LOGPROB_MIN = float(os.getenv("SURF_LOGPROB_MIN", "-1.0"))

# --- Wake word (openWakeWord) ---
WAKE_WORD = os.getenv("SURF_WAKE_WORD", "hey_jarvis")
WAKE_THRESHOLD = float(os.getenv("SURF_WAKE_THRESHOLD", "0.5"))

# --- Audio capture & end-of-speech detection ---
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_CHUNK_SIZE = 1024  # 64 ms at 16 kHz
# Stop after this much quiet once speech has started (long enough for a natural pause).
VAD_SILENCE_LIMIT_SEC = float(os.getenv("SURF_SILENCE_LIMIT", "0.9"))
VAD_MIN_RECORD_SEC = float(os.getenv("SURF_VAD_MIN", "0.6"))
VAD_MAX_RECORD_SEC = float(os.getenv("SURF_VAD_MAX", "10.0"))
VAD_MAX_WAIT_SEC = float(os.getenv("SURF_VAD_MAX_WAIT", "5.0"))
# A chunk counts as "still speaking" while above this fraction of the loudest speech so far.
VAD_RELEASE_RATIO = float(os.getenv("SURF_VAD_RELEASE", "0.18"))

# --- OCR / vision ---
TESSERACT_PATH = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

# --- Logging ---
LOG_FILE = os.getenv("SURF_LOG_FILE", str(BASE_DIR / "surf.log"))
LOG_LEVEL = os.getenv("SURF_LOG_LEVEL", "INFO")
