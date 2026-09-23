"""
agent/speaker.py
Text-to-speech module for verbal feedback.
"""
import pyttsx3
import threading
import queue

_speech_queue = queue.Queue()

def _speaker_worker():
    engine = pyttsx3.init()
    engine.setProperty('rate', 170)
    while True:
        text = _speech_queue.get()
        if text is None:
            break
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"[TTS Error] {e}")
        _speech_queue.task_done()

# Start the worker thread
threading.Thread(target=_speaker_worker, daemon=True).start()

def speak(text: str):
    """Speaks the text aloud in the background."""
    print(f"  [TTS] {text}")
    _speech_queue.put(text)
