from types import SimpleNamespace

import numpy as np
import pytest

from core.audio_capture import Endpointer, rms
from voice.recognizer import accept_segments, is_hallucination

CHUNK = 0.064  # 1024 samples at 16 kHz


def run_endpointer(levels, **kw):
    ep = Endpointer(chunk_sec=CHUNK, **kw)
    states = [ep.feed(level) for level in levels]
    return states, ep


def test_rms_handles_float_and_int16():
    assert rms(np.zeros(100, dtype=np.float32)) == 0.0
    assert rms(np.full(100, 0.5, dtype=np.float32)) == pytest.approx(0.5)
    assert rms(np.full(100, 16384, dtype=np.int16)) == pytest.approx(0.5)


def test_ends_shortly_after_speech_stops():
    quiet, loud = 0.002, 0.08
    levels = [quiet] * 4 + [loud] * 20 + [quiet] * 30
    states, ep = run_endpointer(levels)
    assert "done" in states
    done_at = states.index("done")
    # speech ends at chunk 24; cutoff should come ~0.9 s later, not seconds later
    assert (done_at - 24) * CHUNK == pytest.approx(0.9, abs=0.15)


def test_background_hum_does_not_keep_recording():
    # Regression: a fan just above the ambient gate kept capture running for 14 s.
    ambient, speech, hum = 0.004, 0.10, 0.012
    levels = [ambient] * 4 + [speech] * 15 + [hum] * 60
    states, _ = run_endpointer(levels)
    assert "done" in states and states.index("done") < 4 + 15 + 20


def test_single_click_is_not_speech():
    levels = [0.002] * 4 + [0.2] + [0.002] * 90
    states, _ = run_endpointer(levels, max_wait_sec=3.0)
    assert "speaking" not in states and states[-1] == "timeout"


def test_known_ambient_skips_calibration():
    # "Hey Jarvis, open notepad" in one breath: speech starts in the very first chunks.
    levels = [0.09] * 15 + [0.002] * 20
    states, ep = run_endpointer(levels, ambient=0.003)
    assert states[1] == "speaking"
    assert "done" in states


@pytest.mark.parametrize(
    "text", ["Thank you.", "Thank you. Thank you very much. Thank you very much.", "Thanks for watching!", "", "  ...  "]
)
def test_hallucinations_rejected(text):
    assert is_hallucination(text)


@pytest.mark.parametrize("text", ["Open Notepad.", "thank you, now open chrome", "What time is it?"])
def test_real_commands_kept(text):
    assert not is_hallucination(text)


def seg(text, no_speech=0.1, logprob=-0.3):
    return SimpleNamespace(text=text, no_speech_prob=no_speech, avg_logprob=logprob)


def test_low_confidence_segments_dropped():
    segments = [seg(" Open Chrome."), seg(" you", no_speech=0.9, logprob=-0.9), seg(" blah", logprob=-1.6)]
    assert accept_segments(segments) == "Open Chrome."
