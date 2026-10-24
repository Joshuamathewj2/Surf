"""
agent/pipeline.py
One command pipeline shared by text mode, voice mode, the background daemon and the robot:

    utterance -> autocorrect -> safety -> router -> skills | LLM planner -> spoken feedback

Along the way it tells the robot overlay what is happening (state + a reaction when done)
and records the exchange so follow-up questions have context.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from agent.autocorrect import correct_command
from agent.context import conversation
from agent.router import route_command
from agent.safety import is_safe
from core.logger import get_logger
from interface.bus import emit
from interface.state import set_mood, set_state

logger = get_logger("pipeline")

# Steps after which a following "write/type ..." should go into the app that was just opened.
OPENS_A_WINDOW = {"open_notepad", "open_app", "open_chrome", "open_url", "open_youtube"}
# Actions that wait on the local LLM: acknowledge first so the user isn't left in silence.
SLOW_ACTIONS = {"ask": "Let me think.", "compose": "Writing that now.", "clipboard_ai": "One moment."}
# Actions that wait on the network or the LLM: the robot shows "thinking" instead of "executing".
THINKING_ACTIONS = {"ask", "compose", "clipboard_ai", "weather", "news"}
# How the robot reacts when an action succeeds.
MOODS = {
    "greet": "wave", "how_are_you": "happy", "who_are_you": "hello", "thank_you": "heart", "goodbye": "bye",
    "help": "lightbulb", "ask": "lightbulb", "calculate": "lightbulb", "tell_time": "point", "tell_date": "point",
    "weather": "lightbulb", "news": "point", "joke": "happy", "flip_coin": "clap", "roll_dice": "clap",
    "random_number": "clap", "set_timer": "clap", "set_alarm": "clap", "set_reminder": "clap",
    "set_name": "heart", "get_name": "wave", "remember": "lightbulb", "recall": "think", "forget": "wink",
    "play_spotify": "dance", "media_next": "dance", "media_previous": "dance", "take_screenshot": "surprised",
    "compose": "victory", "clipboard_ai": "lightbulb", "dark_mode": "wink", "battery": "point",
}
_busy = threading.Lock()  # voice, typed and robot commands never run at the same time


@dataclass
class Outcome:
    ok: bool
    route: str
    replies: List[str] = field(default_factory=list)


def _default_speak(text: str) -> None:
    from agent.speaker import speak

    speak(text)


def _quit() -> None:
    """Close Surf once the goodbye has been spoken; the robot exits when its bus link drops."""
    import os

    from agent.speaker import wait_until_done

    wait_until_done()
    time.sleep(0.6)  # let the robot wave
    os._exit(0)


def _dispatch(action: Dict[str, Any]) -> tuple[bool, str]:
    from skills.registry import dispatch_action

    return dispatch_action(action["action"], action)


def handle_command(
    text: str,
    speak: Callable[[str], None] = _default_speak,
    dispatch: Callable[[Dict[str, Any]], tuple[bool, str]] = _dispatch,
) -> Outcome:
    """Run one utterance end to end. `speak`/`dispatch` are injectable for tests."""
    with _busy:
        emit("heard", text=text.strip())
        replies: List[str] = []
        try:
            outcome = _handle(text, speak, dispatch, replies)
        finally:
            set_state("idle", "IDLE")
        spoken = [r for r in replies if r not in SLOW_ACTIONS.values()]
        if outcome.route not in ("empty", "quiet"):
            conversation.add("user", text.strip())
            conversation.add("assistant", " ".join(spoken))
        return outcome


def _handle(text: str, speak, dispatch, replies: List[str]) -> Outcome:
    corrected = correct_command(text)
    if corrected != text.lower().strip():
        logger.info(f'Corrected "{text}" -> "{corrected}"')

    def say(msg: str) -> None:
        if msg:
            replies.append(msg)
            speak(msg)

    if not is_safe(corrected):
        set_state("error", "BLOCKED")
        set_mood("angry")
        say("I won't do that. It looks like a destructive system command.")
        return Outcome(False, "blocked", replies)

    route = route_command(corrected)
    kind = route["type"]

    if kind == "empty":
        say("Yes? I'm listening.")
        return Outcome(True, "empty", replies)

    if kind == "direct" and route["action"] in ("stop_speaking", "dismiss"):
        from agent.speaker import stop

        stop()
        return Outcome(True, "quiet", replies)

    if kind == "direct" and route["action"] == "quit_surf":
        logger.info("Quit requested by voice")
        set_mood("bye")
        say("Goodbye!")
        threading.Thread(target=_quit, daemon=True, name="Quit").start()
        return Outcome(True, "direct", replies)

    if kind == "direct":
        action = route["action"]
        set_state("thinking" if action in THINKING_ACTIONS else "executing", action.upper())
        if action in SLOW_ACTIONS:
            say(SLOW_ACTIONS[action])  # local LLM replies take a few seconds
        if action == "compose":
            route = {**route, "open_first": True}
        ok, feedback = dispatch(route)
        _react(action, ok, route)
        say(feedback)
        return Outcome(ok, "direct", replies)

    if kind == "multi":
        set_state("executing", f"{len(route['actions'])} STEPS")
        ok = True
        previous = None
        for step in route["actions"]:
            if step["action"] in ("compose", "type_text"):
                # Type into the window the previous step opened instead of opening another one.
                step = {**step, "open_first": previous not in OPENS_A_WINDOW and step["action"] == "compose"}
                if previous in OPENS_A_WINDOW:
                    time.sleep(1.0)  # let the new window settle and take focus
            step_ok, feedback = dispatch(step)
            ok = ok and step_ok
            if not step_ok:
                set_mood("sad")
                say(feedback)
                break
            previous = step["action"]
        if ok:
            set_mood("victory")
            say("Done")
        return Outcome(ok, "multi", replies)

    # Unknown request: let the local LLM plan it.
    set_state("thinking", "PLANNING")
    say("Let me figure that out.")
    from llm.planner import plan_actions

    steps = plan_actions(corrected)
    if not steps:
        set_mood("confused")
        say("Sorry, I couldn't work out how to do that.")
        return Outcome(False, "llm", replies)

    from executor.actions import execute_action

    set_state("executing", f"{len(steps)} STEPS")
    logger.info(f"Planner produced {len(steps)} step(s): {steps}")
    ok = all(execute_action(step) for step in steps)
    set_mood("victory" if ok else "sad")
    say("Done" if ok else "Some of that didn't work.")
    return Outcome(ok, "llm", replies)


def _react(action: str, ok: bool, route: Dict[str, Any]) -> None:
    if not ok:
        set_mood("sad")
    elif action == "youtube_search" and route.get("play"):
        set_mood("dance")
    elif action in MOODS:
        set_mood(MOODS[action])


# ---------------------------------------------------------------------------- reminders


def announce(job) -> None:
    """A timer, alarm or reminder is due: make sure the user notices."""
    from agent.speaker import alert_chime, speak
    from skills.timer_skill import alert_text

    text = alert_text(job)
    logger.info(f"Due: {text}")
    emit("alert", text=text)
    alert_chime()
    speak(text)


def start_background_services() -> None:
    """Things that run regardless of the front-end: the reminder clock."""
    from agent.scheduler import scheduler

    scheduler.on_fire = announce
    scheduler.start()
