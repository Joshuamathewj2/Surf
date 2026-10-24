"""
agent/speaker.py
Text-to-speech feedback and short audio cues.

pyttsx3 on Windows only speaks the FIRST utterance when one engine is reused
from a worker thread (later runAndWait() calls return instantly, silently).
So the worker creates a fresh SAPI engine per utterance, inside a COM apartment.

Everything spoken is also published to the robot overlay (speech bubble + "speaking" aura),
and "stop" cuts Surf off mid-sentence.
"""
import queue
import threading

import numpy as np

from core import config
from interface.bus import emit

_speech_queue: "queue.Queue[str | None]" = queue.Queue()
_muted = False
_stop = threading.Event()


def _pick_voice(engine) -> None:
    wanted = config.TTS_VOICE.lower()
    if not wanted:
        return
    for voice in engine.getProperty("voices"):
        if wanted in voice.name.lower():
            engine.setProperty("voice", voice.id)
            return


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
            if not _stop.is_set():
                emit("speaking", value=True)
                engine = pyttsx3.init()
                _pick_voice(engine)
                engine.setProperty("rate", config.TTS_RATE)
                engine.setProperty("volume", 1.0)
                # "stop" sets the flag; the engine checks it at every word boundary.
                engine.connect("started-word", lambda *a, e=engine: _stop.is_set() and e.stop())
                engine.say(text)
                engine.runAndWait()
                engine.stop()
        except Exception as e:  # never let TTS take the assistant down
            print(f"[TTS Error] {e}")
        finally:
            _speech_queue.task_done()
            if _speech_queue.empty():
                _stop.clear()
                emit("speaking", value=False)


threading.Thread(target=_speaker_worker, daemon=True, name="Speaker").start()


def speak(text: str) -> None:
    """Print, show in the robot's speech bubble, and speak text in the background."""
    if not text:
        return
    print(f"  [Surf] {text}")
    emit("say", text=text)
    if not _muted:
        _stop.clear()
        _speech_queue.put(text)


def stop() -> None:
    """Stop talking now and drop anything still queued."""
    _stop.set()
    while True:
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
        except queue.Empty:
            break


def wait_until_done() -> None:
    """Block until everything queued has been spoken (so the mic doesn't hear Surf)."""
    _speech_queue.join()


def set_muted(muted: bool) -> None:
    global _muted
    _muted = muted
    if muted:
        stop()


def chime(rising: bool = True) -> None:
    """Short two-tone cue: rising = "I'm listening", falling = "done/cancelled"."""
    _play_tones((660, 990) if rising else (880, 560))


def alert_chime() -> None:
    """Three bright tones for timers and reminders."""
    _play_tones((880, 1175, 1568, 0, 880, 1175, 1568))


def _play_tones(tones) -> None:
    try:
        import sounddevice as sd

        sr = 22050
        parts = []
        for freq in tones:
            t = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
            env = np.minimum(1, np.minimum(t, t[::-1]) * 60)  # 15 ms fade in/out, no clicks
            parts.append(0.25 * np.sin(2 * np.pi * freq * t) * env if freq else np.zeros_like(t))
        sd.play(np.concatenate(parts).astype(np.float32), sr)
        sd.wait()
    except Exception:
        pass
