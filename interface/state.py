"""
interface/state.py
What the assistant is doing right now, published to the robot overlay.
Zero Qt dependencies: the overlay lives in its own process (see interface/bus.py).

States: idle | listening | thinking | executing | speaking | error
"""
from interface.bus import emit


def set_state(state: str, text: str = "") -> None:
    emit("state", state=state, text=text)


def set_mood(mood: str) -> None:
    """A one-off reaction from the robot: happy, sad, dance, heart, wave, confused..."""
    emit("mood", mood=mood)
