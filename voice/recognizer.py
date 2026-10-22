"""
voice/recognizer.py
Speech-to-text with faster-whisper, hardened against hallucinations.

Whisper is trained on subtitles, so on silence, breathing or background noise it
"hears" phrases like "Thank you very much." or "Thanks for watching!". Surf's old
log shows exactly that being sent to the LLM as commands. Three defences:
  1. Silero VAD inside faster-whisper drops non-speech audio before decoding;
  2. segments Whisper itself marks as unlikely speech / low confidence are dropped;
  3. known subtitle hallucinations are rejected when they are the whole utterance.
"""
import re
import time

import numpy as np

from core import config
from core.audio_capture import record_audio_with_vad
from core.logger import get_logger

logger = get_logger("voice")

_model = None

HALLUCINATIONS = {
    "thank you", "thank you very much", "thanks", "thanks for watching", "thank you for watching",
    "please subscribe", "subscribe", "like and subscribe", "bye", "bye bye", "you", "okay", "ok",
    "so", "uh", "um", "hmm", "oh", "the end", "music", "applause", "silence",
}

# Biases decoding toward command vocabulary (app names are otherwise often misspelt).
COMMAND_PROMPT = (
    "Hey Jarvis, open Notepad. Open Chrome. Search YouTube for lofi music. Play on Spotify. "
    "Take a screenshot. Volume up. What time is it? Open VS Code, Calculator, File Explorer."
)


def load_model(model_name: str = config.VOICE_MODEL):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        logger.info(f"Loading speech model '{model_name}' ({config.VOICE_DEVICE}, {config.VOICE_COMPUTE_TYPE})...")
        start = time.time()
        _model = WhisperModel(model_name, device=config.VOICE_DEVICE, compute_type=config.VOICE_COMPUTE_TYPE)
        logger.info(f"Speech model ready in {time.time() - start:.1f}s.")
    return _model


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z' ]+", "", text.lower()).strip()


def is_hallucination(text: str) -> bool:
    norm = _normalise(text)
    if not norm:
        return True
    # Whisper often repeats the hallucination: "Thank you. Thank you very much. Thank you."
    pieces = {p.strip() for p in re.split(r"[.!?,]+", text.lower()) if p.strip()}
    return norm in HALLUCINATIONS or bool(pieces) and all(_normalise(p) in HALLUCINATIONS for p in pieces)


def accept_segments(segments) -> str:
    """Join the segments Whisper is confident are speech."""
    kept = []
    for seg in segments:
        if seg.no_speech_prob > config.NO_SPEECH_PROB_MAX and seg.avg_logprob < -0.5:
            logger.debug(f"Dropped probable non-speech: {seg.text!r} (no_speech={seg.no_speech_prob:.2f})")
            continue
        if seg.avg_logprob < config.AVG_LOGPROB_MIN:
            logger.debug(f"Dropped low-confidence: {seg.text!r} (logprob={seg.avg_logprob:.2f})")
            continue
        kept.append(seg.text.strip())
    return " ".join(kept).strip()


def transcribe(audio: np.ndarray) -> str:
    if audio.size < config.AUDIO_SAMPLE_RATE * 0.3:
        return ""
    model = load_model()
    start = time.time()
    segments, _ = model.transcribe(
        audio.astype(np.float32),
        language="en",
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        condition_on_previous_text=False,
        initial_prompt=COMMAND_PROMPT,
    )
    text = accept_segments(list(segments))
    logger.info(f'Transcribed in {time.time() - start:.2f}s: "{text}"')
    if is_hallucination(text):
        if text:
            logger.info(f'Ignoring likely hallucination: "{text}"')
        return ""
    return text


def record_and_transcribe() -> str:
    """Listen for one utterance on the default microphone and return its text ("" if none)."""
    load_model()
    audio = record_audio_with_vad()
    return transcribe(audio) if audio.size else ""
