import sounddevice as sd
from faster_whisper import WhisperModel
import config

_model = None

def load_model():
    global _model
    if _model is None:
        print("[VOICE] Loading model (first run downloads ~150MB)...")
        _model = WhisperModel(config.VOICE_MODEL, compute_type="int8")

def record_and_transcribe() -> str:
    print(f"[VOICE] Listening for {config.VOICE_DURATION} seconds...")
    audio = sd.rec(int(config.VOICE_DURATION * 16000), samplerate=16000, channels=1, dtype='float32')
    sd.wait()
    segments, _ = _model.transcribe(audio.flatten(), beam_size=5)
    return " ".join(seg.text for seg in segments).strip()
