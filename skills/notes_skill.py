"""
skills/notes_skill.py
Skill for opening Notepad and writing text notes.
"""
import subprocess
import time
from typing import Dict, Any, Tuple
from skills.base import BaseSkill
from core.logger import get_logger

logger = get_logger("skills.notes")

class NotesSkill(BaseSkill):
    name = "notes"

    HANDLED_INTENTS = {
        "open_notepad",
        "type_text",
        "create_note"
    }

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        import pyautogui

        try:
            if intent == "open_notepad":
                logger.info("Opening Notepad...")
                subprocess.Popen("notepad.exe")
                return True, "Opening Notepad"

            elif intent in ("type_text", "create_note"):
                text = slots.get("text", "")
                should_open = slots.get("open_first", False)
                if should_open:
                    subprocess.Popen("notepad.exe")
                    time.sleep(0.8) # Wait for notepad window to register focus

                if text:
                    logger.info(f"Typing text into active window: '{text}'")
                    pyautogui.typewrite(text, interval=0.03)
                    return True, "Note typed"
                return True, "Opened Notepad"

            return False, f"Unknown notes action: {intent}"
        except Exception as e:
            logger.error(f"Notes action failed: {e}", exc_info=True)
            return False, f"Failed note action: {e}"
