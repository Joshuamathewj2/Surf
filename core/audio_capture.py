"""
core/audio_capture.py
Low-latency audio streaming with dynamic noise calibration and RMS Voice Activity Detection.
"""
import time
import sys
import numpy as np
import sounddevice as sd
from core import config
from core.logger import get_logger

logger = get_logger("audio")

def record_audio_with_vad(
    sample_rate: int = config.AUDIO_SAMPLE_RATE,
    silence_limit_sec: float = config.VAD_SILENCE_LIMIT_SEC,
    min_record_sec: float = config.VAD_MIN_RECORD_SEC,
    max_wait_speech_sec: float = 3.5,  # Stop after 3.5s if user hasn't started speaking
    max_record_sec: float = 6.0        # Max duration for a single command
) -> np.ndarray:
    """
    Dynamically listens to the microphone:
    1. Calibrates to ambient room noise in the first ~150ms.
    2. Detects speech onset automatically.
    3. Cuts off audio ~500ms after speech ends.
    """
    chunk_size = config.AUDIO_CHUNK_SIZE
    frames = []

    silence_chunks_limit = int((silence_limit_sec * sample_rate) / chunk_size)
    min_chunks = int((min_record_sec * sample_rate) / chunk_size)
    max_initial_wait_chunks = int((max_wait_speech_sec * sample_rate) / chunk_size)
    max_chunks = int((max_record_sec * sample_rate) / chunk_size)

    speech_started = False
    silent_chunks = 0
    calibration_frames = []

    print("[Voice] Listening... (speak now)", flush=True)

    try:
        with sd.InputStream(samplerate=sample_rate, channels=config.AUDIO_CHANNELS, dtype='float32', blocksize=chunk_size) as stream:
            # 1. Quick ambient noise calibration (first 3 chunks ~ 150ms)
            for _ in range(3):
                chk, _ = stream.read(chunk_size)
                flat = chk.flatten()
                calibration_frames.append(flat)
                frames.append(flat)

            ambient_rms = np.sqrt(np.mean(np.concatenate(calibration_frames) ** 2))
            # Set dynamic threshold above ambient floor (min 0.0035, max 0.02)
            dynamic_threshold = float(np.clip(ambient_rms * 1.8, 0.0035, 0.025))
            logger.debug(f"Ambient noise floor: {ambient_rms:.5f}, Speech trigger threshold: {dynamic_threshold:.5f}")

            # 2. Main recording loop
            for chunk_idx in range(len(calibration_frames), max_chunks):
                chunk, overflowed = stream.read(chunk_size)
                flat_chunk = chunk.flatten()
                frames.append(flat_chunk)

                rms = np.sqrt(np.mean(flat_chunk ** 2))

                if rms > dynamic_threshold:
                    if not speech_started:
                        print("  >> Hearing you speak...", flush=True)
                        logger.debug(f"Speech detected (RMS: {rms:.4f} > {dynamic_threshold:.4f})")
                        speech_started = True
                    silent_chunks = 0
                else:
                    if speech_started:
                        silent_chunks += 1
                        if silent_chunks >= silence_chunks_limit and chunk_idx >= min_chunks:
                            logger.debug("Silence cutoff reached after speech. Ending capture.")
                            break
                    else:
                        # User has not spoken yet; check if wait timeout reached
                        if chunk_idx >= max_initial_wait_chunks:
                            logger.debug("No speech detected within initial wait window.")
                            break

    except Exception as e:
        logger.error(f"Microphone capture error: {e}")
        return np.array([], dtype=np.float32)

    if not speech_started:
        return np.array([], dtype=np.float32)

    print("  >> Processing...", flush=True)
    audio_data = np.concatenate(frames)
    duration = len(audio_data) / sample_rate
    logger.info(f"Captured {duration:.2f}s of speech.")
    return audio_data
