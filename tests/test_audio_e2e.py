"""
End-to-end audio test without a microphone: synthesise speech with the system voice,
then run it through the real wake-word model, end-of-speech detector and Whisper.

Skipped automatically where SAPI voices or the models aren't available (e.g. CI on Linux).
"""
import os
import tempfile
import wave

import numpy as np
import pytest

pytestmark = pytest.mark.slow


def synth(text: str) -> np.ndarray:
    """Return 16 kHz int16 speech for `text` using the Windows SAPI voice."""
    pyttsx3 = pytest.importorskip("pyttsx3")
    path = os.path.join(tempfile.mkdtemp(), "speech.wav")
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.save_to_file(text, path)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        pytest.skip(f"No TTS voice available: {e}")
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        pytest.skip("TTS produced no audio")
    with wave.open(path) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    idx = np.arange(0, len(audio), sr / 16000)
    return np.interp(idx, np.arange(len(audio)), audio).astype(np.int16)


@pytest.fixture(scope="module")
def detector():
    try:
        from wake.detector import WakeWordDetector

        return WakeWordDetector()
    except Exception as e:
        pytest.skip(f"Wake word model unavailable: {e}")


def peak_score(detector, audio: np.ndarray) -> float:
    detector.reset()
    best = 0.0
    for i in range(0, len(audio) - 1280, 1280):
        best = max(best, detector.score(audio[i : i + 1280]))
    return best


def test_wake_word_fires_on_hey_surf_only(detector):
    silence = np.zeros(16000, dtype=np.int16)
    assert peak_score(detector, np.concatenate([silence, synth("Hey Surf"), silence])) > 0.8
    assert peak_score(detector, np.concatenate([silence, synth("Open the window please"), silence])) < 0.3
    noise = (np.random.default_rng(0).standard_normal(16000 * 3) * 400).astype(np.int16)
    assert peak_score(detector, noise) < 0.3


def test_transcribe_spoken_command_and_route_it():
    from agent.router import route_command
    from voice.recognizer import transcribe

    audio = synth("Open notepad and type hello world").astype(np.float32) / 32768
    text = transcribe(audio)
    assert "notepad" in text.lower() and "hello" in text.lower()
    route = route_command(text)
    assert route["type"] == "multi"
    assert [a["action"] for a in route["actions"]] == ["open_notepad", "type_text"]


def test_silence_and_noise_transcribe_to_nothing():
    from voice.recognizer import transcribe

    noise = np.random.default_rng(1).standard_normal(16000 * 2).astype(np.float32) * 0.01
    assert transcribe(np.zeros(16000 * 2, dtype=np.float32)) == ""
    assert transcribe(noise) == ""


class FakeMic:
    """Stands in for sounddevice.InputStream, playing pre-recorded int16 audio in real-sized frames."""

    def __init__(self, audio: np.ndarray):
        self.audio, self.pos, self.read_available = audio, 0, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n):
        chunk = self.audio[self.pos : self.pos + n]
        if len(chunk) < n:
            raise StopIteration  # end of the recording: stop the loop
        self.pos += n
        return chunk.reshape(-1, 1), False


def test_wake_loop_hands_the_spoken_command_to_the_pipeline(monkeypatch, detector):
    import sounddevice

    import agent.speaker
    import voice.assistant

    silence = np.zeros(16000, dtype=np.int16)
    room = (np.random.default_rng(2).standard_normal(16000) * 30).astype(np.int16)
    audio = np.concatenate([room, synth("Hey Surf"), silence[:4000], synth("What time is it?"), silence, silence])
    monkeypatch.setattr(sounddevice, "InputStream", lambda **kw: FakeMic(audio))
    monkeypatch.setattr(agent.speaker, "chime", lambda rising=True: None)

    heard = []
    with pytest.raises(StopIteration):
        voice.assistant.run_wake_loop(heard.append)
    assert len(heard) == 1
    assert "time" in heard[0].lower()
