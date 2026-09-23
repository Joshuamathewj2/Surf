"""
core/audio_capture.py
Low-latency audio streaming with RMS-based Voice Activity Detection (VAD).
Replaces rigid blocking waits with dynamic silence cutoff.
"""
import time
import numpy as np
import sounddevice as sd
from core import config
from core.logger import get_logger

logger = get_logger("audio")

def record_audio_with_vad(
    sample_rate: int = config.AUDIO_SAMPLE_RATE,
    energy_threshold: float = config.VAD_ENERGY_THRESHOLD,
    silence_limit_sec: float = config.VAD_SILENCE_LIMIT_SEC,
    min_record_sec: float = config.VAD_MIN_RECORD_SEC,
    max_record_sec: float = config.VAD_MAX_RECORD_SEC
) -> np.ndarray:
    """
    Records audio dynamically: starts immediately, detects speech start,
    and terminates as soon as silence is sustained after speaking.
    Returns 1D float32 numpy array normalized for whisper (-1.0 to 1.0).
    """
    logger.debug("Opening audio input stream with dynamic VAD...")
    frames = []
    chunk_size = config.AUDIO_CHUNK_SIZE

    speech_started = False
    silent_chunks = 0
    silence_chunks_limit = int((silence_limit_sec * sample_rate) / chunk_size)
    min_chunks = int((min_record_sec * sample_rate) / chunk_size)
    max_chunks = int((max_record_sec * sample_rate) / chunk_size)

    start_time = time.time()

    with sd.InputStream(samplerate=sample_rate, channels=config.AUDIO_CHANNELS, dtype='float32', blocksize=chunk_size) as stream:
        for chunk_idx in range(max_chunks):
            chunk, overflowed = stream.read(chunk_size)
            if overflowed:
                logger.debug("Audio buffer overflow occurred; continuing.")
            
            flat_chunk = chunk.flatten()
            frames.append(flat_chunk)

            # Compute RMS energy
            rms = np.sqrt(np.mean(flat_chunk ** 2))

            if rms > energy_threshold:
                if not speech_started:
                    logger.debug(f"Speech detected (RMS: {rms:.4f})")
                    speech_started = True
                silent_chunks = 0
            else:
                if speech_started:
                    silent_chunks += 1
                    if silent_chunks >= silence_chunks_limit and chunk_idx >= min_chunks:
                        logger.debug(f"Silence cutoff reached ({silent_chunks * chunk_size / sample_rate:.2f}s). Stopping capture.")
                        break

    elapsed = time.time() - start_time
    if not frames:
        return np.array([], dtype=np.float32)

    audio_data = np.concatenate(frames)
    logger.info(f"Captured {len(audio_data)/sample_rate:.2f}s of audio in {elapsed:.2f}s.")
    return audio_data
