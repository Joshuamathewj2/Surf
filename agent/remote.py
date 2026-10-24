"""
agent/remote.py
Commands that come from the robot overlay (see interface/bus.py): click-to-talk, typed
commands, mute, stop talking, quit.
"""
import os
import threading
from typing import Callable

from core.logger import get_logger
from interface.bus import bus

logger = get_logger("remote")


def apply(msg: dict, handle: Callable[[str], object], listen: Callable[[], None]) -> None:
    from agent import speaker

    cmd = msg.get("cmd")
    if cmd == "text" and msg.get("text", "").strip():
        logger.info(f"Typed command: {msg['text']!r}")
        print(f'\n[You typed] "{msg["text"]}"')
        handle(msg["text"])
    elif cmd == "listen":
        listen()
    elif cmd == "mute":
        speaker.set_muted(bool(msg.get("value")))
        logger.info(f"Voice {'muted' if msg.get('value') else 'unmuted'} from the robot menu")
    elif cmd == "stop":
        speaker.stop()
    elif cmd == "quit":
        logger.info("Quit requested from the robot menu")
        speaker.speak("Goodbye!")
        speaker.wait_until_done()
        os._exit(0)


def serve_in_background(handle: Callable[[str], object]) -> None:
    """For front-ends without a microphone loop (text mode): handle robot commands on a
    thread, and capture one utterance from the mic when the robot is clicked."""
    # Import the heavy modules (numpy, the skills, the recogniser) here on the main thread.
    # Loading numpy's C extension from a background thread while the main thread is blocked
    # in input() hangs on Windows, and the robot's commands would never run.
    import core.audio_capture  # noqa: F401
    import skills.registry  # noqa: F401
    import voice.recognizer  # noqa: F401
    from agent import speaker  # noqa: F401

    listening = threading.Lock()

    def capture() -> None:
        from core.audio_capture import record_audio_with_vad
        from interface.state import set_state
        from voice.recognizer import transcribe

        try:
            set_state("listening", "LISTENING")
            audio = record_audio_with_vad()
            text = ""
            if audio.size:
                set_state("thinking", "TRANSCRIBING")
                text = transcribe(audio)
            set_state("idle")
        finally:
            listening.release()
        if text:
            print(f'\n[You] "{text}"')
            handle(text)

    def listen_once() -> None:
        # On its own thread, so commands typed into the robot don't wait for the microphone.
        if listening.acquire(blocking=False):
            threading.Thread(target=capture, daemon=True, name="ClickToTalk").start()

    def loop() -> None:
        while True:
            msg = bus.commands.get()
            try:
                apply(msg, handle, listen_once)
            except Exception as e:
                logger.error(f"Robot command failed: {e}", exc_info=True)

    threading.Thread(target=loop, daemon=True, name="RobotCommands").start()
