"""
wake/detector.py
Wake word detector using openwakeword and sounddevice.
Listens continuously for wake word triggers at ~1% CPU without requiring PyAudio.
"""
import time
import threading
import numpy as np
from core.logger import get_logger

logger = get_logger("wake")

def start_listening(callback):
    """
    Starts the wake word detector stream using sounddevice and openwakeword.
    """
    def _listen():
        try:
            import sounddevice as sd
            import openwakeword
            from openwakeword.model import Model

            logger.info("Initializing OpenWakeWord detector...")
            try:
                # Load pre-trained models (e.g. alexa or jarvis)
                oww_model = Model(inference_framework="onnx")
            except Exception as e:
                logger.warning(f"Default openwakeword models unavailable ({e}). Wake word standby.")
                while True:
                    time.sleep(3600)

            RATE = 16000
            CHUNK = 1280

            logger.info("[WakeWord] Detector active and listening...")
            with sd.RawInputStream(samplerate=RATE, blocksize=CHUNK, channels=1, dtype='int16') as stream:
                while True:
                    data, overflowed = stream.read(CHUNK)
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    prediction = oww_model.predict(audio_data)

                    for mdl, score in prediction.items():
                        if score > 0.6:  # Detection threshold
                            logger.info(f"[WakeWord] Triggered: '{mdl}' (score: {score:.2f})")
                            callback()
                            time.sleep(1.5)  # Refractory period to avoid duplicate triggers
                            break

        except Exception as e:
            logger.error(f"[WakeWord Error] {e}")
            while True:
                time.sleep(3600)

    t = threading.Thread(target=_listen, daemon=True, name="WakeWordListener")
    t.start()
