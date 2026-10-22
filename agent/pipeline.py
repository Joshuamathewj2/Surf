"""
agent/pipeline.py
One command pipeline shared by text mode, voice mode and the background daemon:

    utterance -> autocorrect -> safety -> router -> skills | LLM planner -> spoken feedback
"""
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from agent.autocorrect import correct_command
from agent.router import route_command
from agent.safety import is_safe
from core.logger import get_logger
from interface.state import set_state

logger = get_logger("pipeline")

# Steps after which a following "write/type ..." should go into the app that was just opened.
OPENS_A_WINDOW = {"open_notepad", "open_app", "open_chrome", "open_url", "open_youtube"}
# Actions that wait on the local LLM: acknowledge first so the user isn't left in silence.
SLOW_ACTIONS = {"ask": "Let me think.", "compose": "Writing that now."}


@dataclass
class Outcome:
    ok: bool
    route: str
    replies: List[str] = field(default_factory=list)


def _default_speak(text: str) -> None:
    from agent.speaker import speak

    speak(text)


def _dispatch(action: Dict[str, Any]) -> tuple[bool, str]:
    from skills.registry import dispatch_action

    return dispatch_action(action["action"], action)


def handle_command(
    text: str,
    speak: Callable[[str], None] = _default_speak,
    dispatch: Callable[[Dict[str, Any]], tuple[bool, str]] = _dispatch,
) -> Outcome:
    """Run one utterance end to end. `speak`/`dispatch` are injectable for tests."""
    corrected = correct_command(text)
    if corrected != text.lower().strip():
        logger.info(f'Corrected "{text}" -> "{corrected}"')

    if not is_safe(corrected):
        set_state("error", "BLOCKED")
        speak("I won't do that. It looks like a destructive system command.")
        return Outcome(False, "blocked", ["blocked"])

    route = route_command(corrected)
    kind = route["type"]
    replies: List[str] = []

    def say(msg: str) -> None:
        if msg:
            replies.append(msg)
            speak(msg)

    if kind == "empty":
        return Outcome(True, "empty")

    if kind == "direct":
        set_state("executing", route["action"].upper())
        if route["action"] in SLOW_ACTIONS:
            say(SLOW_ACTIONS[route["action"]])  # local LLM replies take a few seconds
        if route["action"] == "compose":
            route = {**route, "open_first": True}
        ok, feedback = dispatch(route)
        say(feedback)
        set_state("idle", "IDLE")
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
                say(feedback)
                break
            previous = step["action"]
        if ok:
            say("Done")
        set_state("idle", "IDLE")
        return Outcome(ok, "multi", replies)

    # Unknown request: let the local LLM plan it.
    set_state("thinking", "PLANNING")
    say("Let me figure that out.")
    from llm.planner import plan_actions

    steps = plan_actions(corrected)
    if not steps:
        set_state("error", "NO PLAN")
        say("Sorry, I couldn't work out how to do that.")
        return Outcome(False, "llm", replies)

    from executor.actions import execute_action

    set_state("executing", f"{len(steps)} STEPS")
    logger.info(f"Planner produced {len(steps)} step(s): {steps}")
    ok = all(execute_action(step) for step in steps)
    say("Done" if ok else "Some of that didn't work.")
    set_state("idle", "IDLE")
    return Outcome(ok, "llm", replies)
