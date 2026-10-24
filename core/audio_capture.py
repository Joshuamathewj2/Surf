"""
core/audio_capture.py
Microphone capture with end-of-speech detection.

The Endpointer decides when an utterance starts and ends from per-chunk loudness:
  * the speech gate is calibrated from ambient noise at the start;
  * speech must cross the gate for 2 consecutive chunks (a single click doesn't count);
  * once speaking, a chunk only counts as speech while it stays above a fraction of the
    loudest speech so far. Gating only on ambient noise made fans/AC hum look like
    "still talking", which is why the old capture ran for 14 s on short commands.
"""
from dataclasses import dataclass, field

import numpy as np

from core import config
from core.logger import get_logger

logger = get_logger("audio")


def rms(chunk: np.ndarray) -> float:
    """Root-mean-square level on a 0..1 scale for float32 or int16 audio."""
    if chunk.size == 0:
        return 0.0
    data = chunk.astype(np.float32)
    if np.issubdtype(chunk.dtype, np.integer):
        data /= 32768.0
    return float(np.sqrt(np.mean(data**2)))


@dataclass
class Endpointer:
    chunk_sec: float
    silence_limit_sec: float = config.VAD_SILENCE_LIMIT_SEC
    min_record_sec: float = config.VAD_MIN_RECORD_SEC
    max_wait_sec: float = config.VAD_MAX_WAIT_SEC
    max_record_sec: float = config.VAD_MAX_RECORD_SEC
    release_ratio: float = config.VAD_RELEASE_RATIO
    calibration_chunks: int = 4
    # Known background level (e.g. measured while waiting for the wake word). When given,
    # calibration is skipped, so speech that starts immediately isn't mistaken for noise.
    ambient: float | None = None

    gate: float = 0.0
    peak: float = 0.0
    started: bool = False
    elapsed: float = 0.0
    speech_sec: float = 0.0
    silence_sec: float = 0.0
    _onset_run: int = 0
    _calibration: list = field(default_factory=list)

    def feed(self, level: float) -> str:
        """Feed one chunk's RMS. Returns 'calibrating' | 'waiting' | 'speaking' | 'done' | 'timeout'."""
        self.elapsed += self.chunk_sec
        if self.ambient is not None and not self.gate:
            self.gate = float(np.clip(self.ambient * 2.5, 0.004, 0.03))
            self._calibration = [self.ambient] * self.calibration_chunks
        if len(self._calibration) < self.calibration_chunks:
            self._calibration.append(level)
            if len(self._calibration) == self.calibration_chunks:
                ambient = float(np.median(self._calibration))
                self.gate = float(np.clip(ambient * 2.5, 0.004, 0.03))
                logger.debug(f"ambient={ambient:.4f} gate={self.gate:.4f}")
            return "calibrating"

        if not self.started:
            self._onset_run = self._onset_run + 1 if level > self.gate else 0
            if self._onset_run >= 2:
                self.started = True
                self.peak = level
                self.speech_sec = self.chunk_sec * 2
                return "speaking"
            return "timeout" if self.elapsed >= self.max_wait_sec else "waiting"

        self.peak = max(self.peak, level)
        self.speech_sec += self.chunk_sec
        still_talking = level > max(self.gate, self.peak * self.release_ratio)
        self.silence_sec = 0.0 if still_talking else self.silence_sec + self.chunk_sec
        if self.speech_sec >= self.max_record_sec:
            return "done"
        if self.silence_sec >= self.silence_limit_sec and self.speech_sec >= self.min_record_sec:
            return "done"
        return "speaking"


def record_utterance(
    stream,
    chunk_size: int,
    sample_rate: int = config.AUDIO_SAMPLE_RATE,
    ambient: float | None = None,
    on_level=None,
) -> np.ndarray:
    """Read from an open sounddevice stream until the utterance ends. Returns float32 audio
    (with a little lead-in so the first word isn't clipped), or an empty array on timeout.
    `on_level(rms)` is called for every chunk (the robot's aura follows your voice)."""
    endpointer = Endpointer(chunk_sec=chunk_size / sample_rate, ambient=ambient)
    frames: list[np.ndarray] = []
    lead_in: list[np.ndarray] = []
    while True:
        chunk, _ = stream.read(chunk_size)
        flat = chunk.flatten()
        audio = flat.astype(np.float32) / 32768.0 if flat.dtype == np.int16 else flat.astype(np.float32)
        level = rms(audio)
        if on_level is not None:
            on_level(level)
        state = endpointer.feed(level)
        if state in ("calibrating", "waiting"):
            lead_in = (lead_in + [audio])[-4:]
            continue
        if state == "timeout":
            logger.debug("No speech started within the wait window.")
            return np.array([], dtype=np.float32)
        if not frames:
            frames.extend(lead_in)
            print("  >> Hearing you...", flush=True)
        frames.append(audio)
        if state == "done":
            break
    data = np.concatenate(frames)
    logger.info(f"Captured {len(data) / sample_rate:.2f}s of speech.")
    return data


def record_audio_with_vad() -> np.ndarray:
    """Open the default microphone and capture one utterance (used without a wake word)."""
    import sounddevice as sd

    print("[Voice] Listening... (speak now)", flush=True)
    try:
        with sd.InputStream(
            samplerate=config.AUDIO_SAMPLE_RATE,
            channels=config.AUDIO_CHANNELS,
            dtype="float32",
            blocksize=config.AUDIO_CHUNK_SIZE,
        ) as stream:
            return record_utterance(stream, config.AUDIO_CHUNK_SIZE)
    except Exception as e:
        logger.error(f"Microphone capture error: {e}")
        return np.array([], dtype=np.float32)
