"""
skills/notes_skill.py
Notepad, typing, and LLM-composed writing ("write a short email saying I'll be late").
"""
import subprocess
import time
from typing import Any, Dict, Tuple

import pygetwindow as gw

from core.desktop import type_text, wait_for_window
from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.notes")


def open_notepad() -> bool:
    """Open Notepad on a fresh, empty tab.

    Windows 11 Notepad restores previous session tabs, so the window that appears may be
    showing one of the user's own documents. Surf must never type into those: if the
    focused tab isn't a new "Untitled" one, open a new tab (Ctrl+N) and wait for it.
    """
    import pyautogui

    subprocess.Popen("notepad.exe")
    # Typing before the window has focus sends keystrokes to whatever was focused before.
    win = wait_for_window("Notepad")
    if win is None:
        return False
    time.sleep(0.3)  # Notepad may switch to its new tab a moment after the window appears
    win = gw.getActiveWindow() or win
    if not _is_blank_notepad(win.title):
        logger.info(f"Notepad opened on '{win.title}'; opening a new blank tab instead")
        pyautogui.hotkey("ctrl", "n")
        deadline = time.time() + 3
        while time.time() < deadline:
            active = gw.getActiveWindow()
            if active is not None and _is_blank_notepad(active.title):
                return True
            time.sleep(0.15)
        logger.warning("Couldn't get a blank Notepad tab; refusing to type into an existing document")
        return False
    return True


def _is_blank_notepad(title: str) -> bool:
    t = title.lower()
    return t.startswith("untitled") and "notepad" in t


class NotesSkill(BaseSkill):
    name = "notes"

    HANDLED_INTENTS = {"open_notepad", "type_text", "create_note", "compose"}

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        try:
            if intent == "open_notepad":
                logger.info("Opening Notepad...")
                return (True, "Opening Notepad") if open_notepad() else (False, "Notepad didn't open")

            if intent in ("type_text", "create_note"):
                if slots.get("open_first") and not open_notepad():
                    return False, "Notepad didn't open"
                text = slots.get("text", "")
                if not text:
                    return True, "Ready"
                logger.info(f"Typing {len(text)} characters into the active window")
                type_text(text)
                return True, "Done"

            if intent == "compose":
                return self._compose(slots.get("prompt", ""), open_first=slots.get("open_first", True))

            return False, f"Unknown notes action: {intent}"
        except Exception as e:
            logger.error(f"Notes action failed: {e}", exc_info=True)
            return False, "Something went wrong while typing"

    def _compose(self, prompt: str, open_first: bool) -> Tuple[bool, str]:
        from llm.planner import compose

        if not prompt:
            return False, "What should I write?"
        logger.info(f"Composing: {prompt}")
        text = compose(prompt)
        if not text:
            return False, "I couldn't reach the language model to write that"
        if open_first and not open_notepad():
            return False, "Notepad didn't open"
        type_text(text)
        return True, "Here you go"
