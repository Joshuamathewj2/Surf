"""
voice/recognizer.py
High-performance, low-latency Speech Recognition using faster-whisper
and dynamic Voice Activity Detection (VAD).
"""
import time
from faster_whisper import WhisperModel
from core import config
from core.logger import get_logger
from core.audio_capture import record_audio_with_vad

logger = get_logger("voice")

_model = None

def load_model(model_name: str = config.VOICE_MODEL):
    """Loads faster-whisper with explicit CPU int8 optimization."""
    global _model
    if _model is None:
        logger.info(f"Loading speech model '{model_name}' on CPU (int8)...")
        start = time.time()
        _model = WhisperModel(
            model_name,
            device=config.VOICE_DEVICE,
            compute_type=config.VOICE_COMPUTE_TYPE
        )
        logger.info(f"Speech model ready in {time.time() - start:.2f}s.")
    return _model

def record_and_transcribe() -> str:
    """
    Dynamically listens until silence is detected, then transcribes immediately.
    """
    global _model
    if _model is None:
        load_model()

    logger.info("Listening for command (speak naturally)...")
    audio = record_audio_with_vad()

    if len(audio) == 0:
        logger.debug("No audio captured.")
        return ""

    logger.info("Transcribing audio...")
    start_t = time.time()
    try:
        segments, info = _model.transcribe(
            audio,
            beam_size=1, # Greedy search for sub-second command decoding
            language="en"
        )
        transcribed_text = " ".join(seg.text for seg in segments).strip()
        elapsed = time.time() - start_t
        logger.info(f"Transcribed in {elapsed:.2f}s: \"{transcribed_text}\"")
        return transcribed_text
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        return ""
