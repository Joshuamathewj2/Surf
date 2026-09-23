"""
skills/system_skill.py
Skill for handling system audio volume, screenshots, and screen interactions.
"""
import datetime
import os
from typing import Dict, Any, Tuple
from skills.base import BaseSkill
from core import config
from core.logger import get_logger

logger = get_logger("skills.system")

class SystemSkill(BaseSkill):
    name = "system"

    HANDLED_INTENTS = {
        "volume_up",
        "volume_down",
        "mute_audio",
        "take_screenshot",
        "click_text"
    }

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        import pyautogui

        try:
            if intent == "volume_up":
                logger.info("Increasing volume...")
                pyautogui.press("volumeup", presses=3)
                return True, "Volume up"
            elif intent == "volume_down":
                logger.info("Decreasing volume...")
                pyautogui.press("volumedown", presses=3)
                return True, "Volume down"
            elif intent == "mute_audio":
                logger.info("Toggling mute...")
                pyautogui.press("volumemute")
                return True, "Muted audio"
            elif intent == "take_screenshot":
                return self._take_screenshot()
            elif intent == "click_text":
                target = slots.get("target", "")
                return self._click_text(target)
            else:
                return False, f"Unknown system action: {intent}"
        except Exception as e:
            logger.error(f"System action failed: {e}", exc_info=True)
            return False, f"Failed system action: {e}"

    def _take_screenshot(self) -> Tuple[bool, str]:
        import pyautogui
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)
        filename = os.path.join(config.SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
        logger.info(f"Capturing screenshot: {filename}")
        pyautogui.screenshot(filename)
        return True, "Screenshot saved"

    def _click_text(self, target: str) -> Tuple[bool, str]:
        if not target:
            return False, "No target text provided."
        import pyautogui
        from vision.screen_reader import find_text_on_screen
        logger.info(f"Looking for screen text to click: '{target}'")
        coords = find_text_on_screen(target)
        if coords:
            pyautogui.click(coords[0], coords[1])
            logger.info(f"Clicked '{target}' at {coords}")
            return True, f"Clicked {target}"
        else:
            logger.warning(f"Could not find '{target}' on screen.")
            return False, f"Could not find {target} on screen"
