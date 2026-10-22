"""
wake/detector.py
"Hey Jarvis" wake word with openWakeWord (runs on CPU at ~1-2% load).

The previous version loaded openWakeWord's default Model(), whose model files were
never downloaded, so it logged a warning and slept forever: the daemon could never
wake. It would also have reacted to every bundled phrase ("alexa", "timer", ...).
Now exactly one wake word is loaded and its model files are fetched on first use.
"""
import numpy as np

from core import config
from core.logger import get_logger

logger = get_logger("wake")

FRAME = 1280  # openWakeWord expects 80 ms frames of 16 kHz int16 audio


def ensure_models(wakeword: str = config.WAKE_WORD) -> None:
    """Download the wake-word model (and the shared feature models) if they're missing."""
    import glob
    import os

    import openwakeword
    from openwakeword.utils import download_models

    folder = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
    have_wake = glob.glob(os.path.join(folder, f"{wakeword}*.onnx"))
    have_features = glob.glob(os.path.join(folder, "melspectrogram.onnx")) and glob.glob(
        os.path.join(folder, "embedding_model.onnx")
    )
    if not (have_wake and have_features):
        logger.info(f"Downloading wake word model '{wakeword}' (one-time, ~4 MB)...")
        download_models(model_names=[wakeword])


class WakeWordDetector:
    def __init__(self, wakeword: str = config.WAKE_WORD, threshold: float = config.WAKE_THRESHOLD):
        from openwakeword.model import Model

        ensure_models(wakeword)
        self.wakeword = wakeword
        self.threshold = threshold
        self._model = Model(wakeword_models=[wakeword], inference_framework="onnx")

    def score(self, frame: np.ndarray) -> float:
        """Confidence (0-1) that the wake word just ended in this 80 ms int16 frame."""
        prediction = self._model.predict(frame.astype(np.int16).flatten())
        return float(max(prediction.values())) if prediction else 0.0

    def detected(self, frame: np.ndarray) -> bool:
        return self.score(frame) >= self.threshold

    def reset(self) -> None:
        """Clear the model's rolling audio buffer (call after handling a command)."""
        self._model.reset()
