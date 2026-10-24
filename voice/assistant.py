"""
voice/assistant.py
The hands-free loop: wait for "Hey Surf" -> chime -> capture command -> act -> repeat.

One microphone stream is shared by the wake-word detector and command capture, so
there is no device re-open delay (and no WASAPI sample-rate errors from a second stream).
"""
import collections
import time

import numpy as np

from core import config
from core.audio_capture import record_utterance, rms
from core.logger import get_logger
from interface.bus import bus, emit
from interface.state import set_state

logger = get_logger("assistant")


def _flush(stream) -> None:
    """Drop audio buffered while Surf was busy or speaking, so it can't hear itself."""
    available = getattr(stream, "read_available", 0)
    if available:
        stream.read(available)


def run_wake_loop(handle) -> None:
    """Block forever, calling handle(text) for each command spoken after the wake word."""
    import sounddevice as sd

    from agent.speaker import chime, speak, wait_until_done
    from voice.recognizer import load_model, transcribe
    from wake.detector import FRAME, WakeWordDetector

    detector = WakeWordDetector()
    load_model()
    ambient_levels: collections.deque[float] = collections.deque(maxlen=50)  # ~4 s of history

    wake_name = config.WAKE_WORD.replace("_", " ").title()
    print(f'\n[Surf] Ready. Say "{wake_name}" followed by a command.  (Ctrl+C to quit)')
    set_state("idle", f"SAY {wake_name.upper()}")

    from agent import remote

    with sd.InputStream(samplerate=config.AUDIO_SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME) as stream:
        while True:
            frame, _ = stream.read(FRAME)
            level = rms(frame)
            clicked = False
            msg = bus.poll()  # the robot was clicked, or a command was typed into it
            if msg is not None:
                if msg.get("cmd") == "listen":
                    clicked = True
                else:
                    remote.apply(msg, handle, lambda: None)
                    wait_until_done()
                    _flush(stream)
                    detector.reset()
                    set_state("idle", f"SAY {wake_name.upper()}")
                    continue
            if not clicked and not detector.detected(frame):
                ambient_levels.append(level)
                continue

            logger.info("Robot clicked" if clicked else "Wake word detected")
            set_state("listening", "LISTENING")
            chime(rising=True)
            _flush(stream)  # don't let the chime itself count as the start of speech
            ambient = float(np.median(ambient_levels)) if ambient_levels else None
            audio = record_utterance(stream, FRAME, ambient=ambient, on_level=lambda v: emit("level", value=v))
            text = ""
            if audio.size:
                set_state("thinking", "TRANSCRIBING")
                text = transcribe(audio)

            if text:
                print(f'\n[You] "{text}"')
                handle(text)
            else:
                chime(rising=False)
                speak("I'm listening.")
                logger.info("Nothing heard after the wake word.")

            wait_until_done()
            time.sleep(0.2)
            _flush(stream)
            detector.reset()
            set_state("idle", f"SAY {wake_name.upper()}")
