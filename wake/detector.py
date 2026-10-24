"""
wake/detector.py
"Hey Surf" wake word with openWakeWord (runs on CPU at ~1-2% load).

Loads the custom or pre-trained wake word ONNX model (packaged in wake/models/
or downloaded from openWakeWord releases) along with shared feature extractors.
"""
import glob
import os
import numpy as np

from core import config
from core.logger import get_logger

logger = get_logger("wake")

FRAME = 1280  # openWakeWord expects 80 ms frames of 16 kHz int16 audio


def ensure_models(wakeword: str = config.WAKE_WORD) -> None:
    """Ensure the wake-word model and the shared feature models are present."""
    import openwakeword
    from openwakeword.utils import download_models

    folder = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
    local_model = os.path.join(os.path.dirname(__file__), "models", f"{wakeword}.onnx")

    if os.path.exists(local_model):
        dest = os.path.join(folder, f"{wakeword}.onnx")
        if not os.path.exists(dest):
            import shutil

            os.makedirs(folder, exist_ok=True)
            try:
                shutil.copy(local_model, dest)
            except Exception as e:
                logger.debug(f"Could not copy local wake model to site-packages: {e}")

    have_wake = glob.glob(os.path.join(folder, f"{wakeword}*.onnx")) or os.path.exists(local_model)
    have_features = glob.glob(os.path.join(folder, "melspectrogram.onnx")) and glob.glob(
        os.path.join(folder, "embedding_model.onnx")
    )
    if not (have_wake and have_features):
        logger.info(f"Downloading wake word model '{wakeword}' (one-time, ~4 MB)...")
        download_models(model_names=[wakeword] if not os.path.exists(local_model) else [])


class WakeWordDetector:
    def __init__(self, wakeword: str = config.WAKE_WORD, threshold: float = config.WAKE_THRESHOLD):
        from openwakeword.model import Model

        ensure_models(wakeword)
        self.wakeword = wakeword
        self.threshold = threshold

        local_model = os.path.join(os.path.dirname(__file__), "models", f"{wakeword}.onnx")
        if os.path.exists(local_model):
            self._model = Model(wakeword_models=[local_model], inference_framework="onnx")
        else:
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
