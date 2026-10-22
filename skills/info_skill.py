"""
skills/info_skill.py
Spoken answers: time, date, and general questions via the local LLM.
"""
import datetime
from typing import Any, Dict, Tuple

from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.info")


def spoken_time(now: datetime.datetime) -> str:
    hour = now.hour % 12 or 12
    suffix = "AM" if now.hour < 12 else "PM"
    return f"It's {hour}:{now.minute:02d} {suffix}"


def spoken_date(now: datetime.datetime) -> str:
    return f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}"


class InfoSkill(BaseSkill):
    name = "info"

    HANDLED_INTENTS = {"tell_time", "tell_date", "ask"}

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        now = datetime.datetime.now()
        if intent == "tell_time":
            return True, spoken_time(now)
        if intent == "tell_date":
            return True, spoken_date(now)
        if intent == "ask":
            from llm.planner import ask

            answer = ask(slots.get("question", ""))
            if answer:
                return True, answer
            return False, "I can't reach the language model right now. Is Ollama running?"
        return False, f"Unknown info action: {intent}"
