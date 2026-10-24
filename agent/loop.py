"""
agent/loop.py
Interactive front-ends over the shared command pipeline.
"""
import os

from agent.pipeline import handle_command, start_background_services
from core.logger import get_logger

logger = get_logger("loop")

BANNER = r"""
 ____  _   _ ____  _____
/ ___|| | | |  _ \|  ___|
\___ \| | | | |_) | |_
 ___) | |_| |  _ <|  _|
|____/ \___/|_| \_\_|

  Your local assistant for Windows (v4)
"""

EXIT_WORDS = {"exit", "quit", "q", "goodbye", "bye surf"}


def run_text() -> None:
    """Type commands at a prompt (great for testing without a microphone)."""
    from agent import remote

    start_background_services()
    remote.serve_in_background(handle_command)  # robot clicks and commands typed into the robot
    print("\n[Text mode] Type a command, or 'exit' to quit.")
    while True:
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
    """Hands-free mode: 'Hey Surf' + command (or click the robot)."""
    from llm.planner import warm_up
    from voice.assistant import run_wake_loop

    warm_up()
    start_background_services()
    try:
        run_wake_loop(handle_command)
    except KeyboardInterrupt:
        print("\nGoodbye!")


def run() -> None:
    print(BANNER)
    try:
        mode = input("Mode: [1] Text  [2] Voice (\"Hey Surf\") -> ").strip()
    except (EOFError, KeyboardInterrupt):
        os._exit(0)
    run_voice() if mode == "2" else run_text()
