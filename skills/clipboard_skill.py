"""
skills/clipboard_skill.py
Work with whatever you copied: "read my clipboard", "summarise what I copied",
"translate this to French", "explain this". Copy text anywhere (Ctrl+C), then ask.
"""
from typing import Any, Dict, Tuple

from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.clipboard")

MAX_READ_CHARS = 600


def get_clipboard_text() -> str:
    import win32clipboard
    import win32con

    win32clipboard.OpenClipboard()
    try:
        return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
    except (TypeError, win32clipboard.error):
        return ""
    finally:
        win32clipboard.CloseClipboard()


class ClipboardSkill(BaseSkill):
    name = "clipboard"

    HANDLED_INTENTS = {"read_clipboard", "clipboard_ai"}

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            text = get_clipboard_text().strip()
        except Exception as e:
            logger.error(f"Clipboard read failed: {e}")
            return False, "I couldn't read the clipboard."
        if not text:
            return False, "Your clipboard is empty. Copy some text first."
        if slots.get("intent") == "read_clipboard":
            if len(text) > MAX_READ_CHARS:
                return True, text[:MAX_READ_CHARS].rsplit(" ", 1)[0] + "... and more."
            return True, text

        from llm.planner import transform

        out = transform(slots.get("instruction", "Summarise this."), text)
        return (True, out) if out else (False, "I can't reach the language model right now.")
