"""
agent/speaker.py
Text-to-speech feedback and short audio cues.

pyttsx3 on Windows only speaks the FIRST utterance when one engine is reused
from a worker thread (later runAndWait() calls return instantly, silently).
So the worker creates a fresh SAPI engine per utterance, inside a COM apartment.
"""
import queue
import threading

import numpy as np

_speech_queue: "queue.Queue[str | None]" = queue.Queue()
_muted = False


def _speaker_worker() -> None:
    try:
        import pythoncom

        pythoncom.CoInitialize()
    except ImportError:  # non-Windows: pyttsx3 picks another driver
        pass
    import pyttsx3

    while True:
        text = _speech_queue.get()
        if text is None:
            break
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:  # never let TTS take the assistant down
            print(f"[TTS Error] {e}")
        finally:
            _speech_queue.task_done()


threading.Thread(target=_speaker_worker, daemon=True, name="Speaker").start()


def speak(text: str) -> None:
    """Print and speak text in the background."""
    if not text:
        return
    print(f"  [Surf] {text}")
    if not _muted:
        _speech_queue.put(text)


def wait_until_done() -> None:
    """Block until everything queued has been spoken (so the mic doesn't hear Surf)."""
    _speech_queue.join()


def set_muted(muted: bool) -> None:
    global _muted
    _muted = muted


def chime(rising: bool = True) -> None:
    """Short two-tone cue: rising = "I'm listening", falling = "done/cancelled"."""
    try:
        import sounddevice as sd

        sr = 22050
        tones = (660, 990) if rising else (880, 560)
        parts = []
        for freq in tones:
            t = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
            env = np.minimum(1, np.minimum(t, t[::-1]) * 60)  # 15 ms fade in/out, no clicks
            parts.append(0.25 * np.sin(2 * np.pi * freq * t) * env)
        sd.play(np.concatenate(parts).astype(np.float32), sr)
        sd.wait()
    except Exception:
        pass
