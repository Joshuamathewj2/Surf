"""
skills/shortcut_skill.py
Everyday keyboard actions ("save", "undo", "go back", "switch window"...) handled
instantly instead of asking the LLM to invent a plan for them.
"""
import time
from typing import Any, Dict, Tuple

from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.shortcut")

# intent -> (keys, spoken feedback). One tuple = one hotkey; a list of tuples = a sequence.
SHORTCUTS: Dict[str, Tuple[tuple, str]] = {
    "save": (("ctrl", "s"), "Saved"),
    "undo": (("ctrl", "z"), "Undone"),
    "redo": (("ctrl", "y"), "Redone"),
    "copy": (("ctrl", "c"), "Copied"),
    "paste": (("ctrl", "v"), "Pasted"),
    "cut": (("ctrl", "x"), "Cut"),
    "select_all": (("ctrl", "a"), "Selected everything"),
    "find": (("ctrl", "f"), "Find"),
    "print": (("ctrl", "p"), "Opening print"),
    "new_window": (("ctrl", "n"), "New window"),
    "go_back": (("alt", "left"), "Going back"),
    "go_forward": (("alt", "right"), "Going forward"),
    "refresh": (("f5",), "Refreshing"),
    "next_tab": (("ctrl", "tab"), "Next tab"),
    "previous_tab": (("ctrl", "shift", "tab"), "Previous tab"),
    "switch_window": (("alt", "tab"), "Switched window"),
    "minimize_window": (("win", "down"), "Minimised"),
    "maximize_window": (("win", "up"), "Maximised"),
    "show_desktop": (("win", "d"), "Showing the desktop"),
    "close_window": (("alt", "f4"), "Closed the window"),
    "zoom_in": (("ctrl", "="), "Zooming in"),
    "zoom_out": (("ctrl", "-"), "Zooming out"),
    "reset_zoom": (("ctrl", "0"), "Zoom reset"),
    "snap_left": (("win", "left"), "Snapped left"),
    "snap_right": (("win", "right"), "Snapped right"),
    "press_enter": (("enter",), ""),
    "press_escape": (("esc",), ""),
}


class ShortcutSkill(BaseSkill):
    name = "shortcuts"

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in SHORTCUTS or intent in ("scroll_up", "scroll_down")

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        import pyautogui

        intent = slots.get("intent", "")
        try:
            if intent in ("scroll_up", "scroll_down"):
                pyautogui.scroll(700 if intent == "scroll_up" else -700)
                return True, ""
            keys, feedback = SHORTCUTS[intent]
            logger.info(f"{intent}: {'+'.join(keys)}")
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
            time.sleep(0.05)
            return True, feedback
        except Exception as e:
            logger.error(f"Shortcut {intent} failed: {e}")
            return False, "That shortcut didn't work"
