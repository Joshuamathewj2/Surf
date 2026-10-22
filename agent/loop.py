"""
agent/loop.py
Interactive front-ends over the shared command pipeline.
"""
import os

from agent.pipeline import handle_command
from core.logger import get_logger
from interface.state import set_state

logger = get_logger("loop")

BANNER = r"""
 ____  _   _ ____  _____
/ ___|| | | |  _ \|  ___|
\___ \| | | | |_) | |_
 ___) | |_| |  _ <|  _|
|____/ \___/|_| \_\_|

  Local voice assistant for Windows (v3)
"""

EXIT_WORDS = {"exit", "quit", "q", "goodbye", "bye surf"}


def run_text() -> None:
    """Type commands at a prompt (great for testing without a microphone)."""
    print("\n[Text mode] Type a command, or 'exit' to quit.")
    while True:
        set_state("listening", "AWAITING INPUT")
        try:
            text = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            break
        handle_command(text)
    print("Goodbye!")


def run_voice() -> None:
    """Hands-free mode: 'Hey Jarvis' + command."""
    from llm.planner import warm_up
    from voice.assistant import run_wake_loop

    warm_up()
    try:
        run_wake_loop(handle_command)
    except KeyboardInterrupt:
        print("\nGoodbye!")


def run() -> None:
    print(BANNER)
    try:
        mode = input("Mode: [1] Text  [2] Voice (\"Hey Jarvis\") -> ").strip()
    except (EOFError, KeyboardInterrupt):
        os._exit(0)
    run_voice() if mode == "2" else run_text()
