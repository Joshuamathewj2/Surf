"""
core/config.py
Unified, environment-aware configuration for Surf Desktop Assistant.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Local LLM Planner Settings ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("SURF_LLM_MODEL", "phi3:mini")
LLM_TIMEOUT = float(os.getenv("SURF_LLM_TIMEOUT", "6.0"))

# --- Automation Settings ---
DELAY_BETWEEN_ACTIONS = float(os.getenv("SURF_ACTION_DELAY", "0.1"))
SCREENSHOT_DIR = os.getenv("SURF_SCREENSHOT_DIR", str(BASE_DIR))

# Default to pre-cached 'tiny' for instant offline loading and ~200ms inference
VOICE_MODEL = os.getenv("SURF_VOICE_MODEL", "tiny")
VOICE_DEVICE = "cpu"
VOICE_COMPUTE_TYPE = "int8"

# --- Audio Capture & VAD Settings ---
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_CHUNK_SIZE = 1024
VAD_ENERGY_THRESHOLD = float(os.getenv("SURF_VAD_THRESHOLD", "0.015"))
# --- KEY FIX: was 0.55s — caused premature cutoff on natural mid-sentence pauses ---
# 1.2s means Surf waits a full beat after you stop talking before cutting off.
# For compound commands ("open notepad and write..."), you need this headroom.
VAD_SILENCE_LIMIT_SEC = float(os.getenv("SURF_SILENCE_LIMIT", "1.2"))
# Must buffer at least 0.8s before silence detection arms itself
VAD_MIN_RECORD_SEC = float(os.getenv("SURF_VAD_MIN", "0.8"))
# 14s ceiling: long enough for any realistic command, prevents runaway capture
VAD_MAX_RECORD_SEC = float(os.getenv("SURF_VAD_MAX", "14.0"))
# How long to wait for the user to START speaking before giving up (was hardcoded 3.5s)
VAD_MAX_WAIT_SEC = float(os.getenv("SURF_VAD_MAX_WAIT", "5.0"))

# --- OCR / Vision Settings ---
TESSERACT_PATH = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

# --- Logging Settings ---
LOG_FILE = os.getenv("SURF_LOG_FILE", str(BASE_DIR / "surf.log"))
LOG_LEVEL = os.getenv("SURF_LOG_LEVEL", "INFO")
