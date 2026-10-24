"""
executor/actions.py
Executes the validated steps produced by llm/planner.py.
Only allowlisted actions exist here: there is deliberately no shell execution.
"""
import time
import urllib.parse
import webbrowser
from typing import Any, Callable, Dict

import pyautogui

from core import config
from core.desktop import type_text, wait_for_window
from core.logger import get_logger

logger = get_logger("executor")

# Move the mouse to any screen corner to abort automation instantly.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

ALLOWED_KEYS = {
    "enter", "esc", "escape", "tab", "backspace", "delete", "space", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown", "f5", "win",
    "ctrl", "alt", "shift", "a", "c", "v", "x", "z", "s", "t", "w", "n", "f", "l", "r", "p",
}


def _open_app(step: Dict[str, Any]) -> None:
    from skills.app_skill import AppSkill

    AppSkill()._launch_app(step["name"])


def _youtube(step: Dict[str, Any]) -> None:
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(step["query"]))


def _google(step: Dict[str, Any]) -> None:
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(step["query"]))


def _open_url(step: Dict[str, Any]) -> None:
    url = step["url"]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)


def _press(step: Dict[str, Any]) -> None:
    key = step["key"].lower()
    if key in ALLOWED_KEYS:
        pyautogui.press(key)


def _hotkey(step: Dict[str, Any]) -> None:
    keys = [k.lower() for k in step["keys"]]
    if keys and all(k in ALLOWED_KEYS for k in keys):
        pyautogui.hotkey(*keys)


def _scroll(step: Dict[str, Any]) -> None:
    amount = int(step.get("amount", 5)) * 100
    pyautogui.scroll(amount if step["direction"] == "up" else -amount)


def _screenshot(_: Dict[str, Any]) -> None:
    from skills.system_skill import SystemSkill

    SystemSkill()._take_screenshot()


def _skill(intent: str, **slots: Any) -> None:
    """Run a skill from a plan and say what it reports (e.g. the weather)."""
    from agent.speaker import speak
    from skills.registry import dispatch_action

    ok, feedback = dispatch_action(intent, slots)
    if feedback:
        speak(feedback)
    if not ok:
        raise RuntimeError(feedback or intent)


def _media(step: Dict[str, Any]) -> None:
    intent = {"next": "media_next", "previous": "media_previous"}.get(step["command"].lower(), "media_play_pause")
    _skill(intent)


HANDLERS: Dict[str, Callable[[Dict[str, Any]], None]] = {
    "open_app": _open_app,
    "open_url": _open_url,
    "youtube_search": _youtube,
    "google_search": _google,
    "type": lambda s: type_text(s["text"]),
    "press": _press,
    "hotkey": _hotkey,
    "wait": lambda s: time.sleep(float(s["seconds"])),
    "scroll": _scroll,
    "focus_window": lambda s: wait_for_window(s["title"], timeout=2),
    "take_screenshot": _screenshot,
    "open_start_menu": lambda s: pyautogui.press("win"),
    "set_timer": lambda s: _skill("set_timer", seconds=int(max(1, min(float(s["seconds"]), 86400)))),
    "media": _media,
    "weather": lambda s: _skill("weather", place=str(s.get("place", "")), day=int(s.get("day", 0) or 0)),
}


def execute_action(step: Dict[str, Any]) -> bool:
    """Run one validated planner step. Returns False if it failed."""
    handler = HANDLERS.get(step.get("action", ""))
    if handler is None:
        logger.warning(f"Skipping unsupported action: {step}")
        return False
    try:
        logger.info(f"Executing {step}")
        handler(step)
        time.sleep(config.DELAY_BETWEEN_ACTIONS)
        return True
    except pyautogui.FailSafeException:
        logger.warning("Aborted: mouse moved to a screen corner (pyautogui failsafe).")
        raise
    except Exception as e:
        logger.error(f"Action {step.get('action')} failed: {e}")
        return False
