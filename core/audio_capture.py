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
    # --- Pull ALL timing values from config so they're tunable without touching code ---
    silence_limit_sec: float = config.VAD_SILENCE_LIMIT_SEC,   # 1.2s — wait a full beat after speech ends
    min_record_sec: float = config.VAD_MIN_RECORD_SEC,          # 0.8s — arm silence detection only after this
    max_wait_speech_sec: float = config.VAD_MAX_WAIT_SEC,       # 5.0s — give up if no speech starts
    max_record_sec: float = config.VAD_MAX_RECORD_SEC           # 14.0s — absolute recording ceiling
) -> np.ndarray:
    """
    Dynamically listens to the microphone:
    1. Calibrates to ambient room noise in the first ~250ms (5 chunks).
    2. Detects speech onset automatically.
    3. Cuts off audio only after VAD_SILENCE_LIMIT_SEC of sustained silence post-speech.

    Key parameters are all config-driven — tune them in core/config.py or via env vars
    without touching this file.
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
            # 1. Ambient noise calibration: use 5 chunks (~250ms) for a more stable floor.
            # More samples = less chance of a transient spike inflating the noise floor.
            N_CALIBRATION_CHUNKS = 5
            for _ in range(N_CALIBRATION_CHUNKS):
                chk, _ = stream.read(chunk_size)
                flat = chk.flatten()
                calibration_frames.append(flat)
                frames.append(flat)

            ambient_rms = np.sqrt(np.mean(np.concatenate(calibration_frames) ** 2))

            # Multiplier raised from 1.8x → 2.2x.
            # WHY: 1.8x was triggering on soft breathing/HVAC and treating it as speech onset.
            # That produced very short "captures" (< 1s) of near-silence which Whisper then
            # hallucinated as words (e.g. "Head soft."). 2.2x means only clear voiced speech
            # crosses the gate. Clamp range keeps it sane on both very quiet and noisy mics.
            dynamic_threshold = float(np.clip(ambient_rms * 2.2, 0.004, 0.030))
            logger.debug(
                f"Ambient RMS: {ambient_rms:.5f} | Speech gate: {dynamic_threshold:.5f} "
                f"| Silence window: {silence_limit_sec:.1f}s | Max: {max_record_sec:.0f}s"
            )

            # 2. Main recording loop
            for chunk_idx in range(N_CALIBRATION_CHUNKS, max_chunks):
                chunk, overflowed = stream.read(chunk_size)
                flat_chunk = chunk.flatten()
                frames.append(flat_chunk)

                rms = np.sqrt(np.mean(flat_chunk ** 2))

                if rms > dynamic_threshold:
                    if not speech_started:
                        print("  >> Hearing you speak...", flush=True)
                        logger.debug(f"Speech onset (RMS: {rms:.4f} > gate: {dynamic_threshold:.4f})")
                        speech_started = True
                    # Reset the silence counter each time speech energy is detected
                    silent_chunks = 0

                else:
                    if speech_started:
                        silent_chunks += 1
                        # Only fire cutoff if we've recorded the minimum required audio
                        if silent_chunks >= silence_chunks_limit and chunk_idx >= min_chunks:
                            logger.debug(
                                f"Silence cutoff: {silent_chunks} quiet chunks "
                                f"(>= limit {silence_chunks_limit}) after {chunk_idx} total chunks."
                            )
                            break
                    else:
                        # Speech hasn't started yet — check the onset timeout
                        if chunk_idx >= max_initial_wait_chunks:
                            logger.debug("No speech detected within onset-wait window. Aborting.")
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
