"""
skills/info_skill.py
Spoken answers: time, date, maths, small talk, jokes, coin flips, and general questions.

Questions go to the local LLM with the recent conversation (so follow-ups work), what Surf
remembers about you, and, for factual "who/what is ..." questions, the matching Wikipedia
summary so answers about real-world facts aren't limited to the model's training data.
"""
import datetime
import random
import re
from typing import Any, Dict, Optional, Tuple

from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.info")

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I told my computer I needed a break. It said: no problem, I'll go to sleep.",
    "Why did the robot go on vacation? It needed to recharge its batteries.",
    "What do you call a computer that sings? A Dell.",
    "Why was the computer cold? It left its Windows open.",
    "I'd tell you a UDP joke, but you might not get it.",
    "Why did the scarecrow win an award? Because he was outstanding in his field.",
    "What's a robot's favourite snack? Computer chips.",
    "Why don't keyboards ever sleep? Because they have two shifts.",
    "There are 10 kinds of people in the world: those who understand binary and those who don't.",
    "Why did the smartphone need glasses? It lost all its contacts.",
    "What did the router say to the doctor? It hurts when IP.",
]

HELP = (
    "I can open apps and websites, play music, search the web, tell you the weather and the news, "
    "answer questions, do maths, set timers, alarms and reminders, remember things for you, "
    "summarise or translate what you copied, write emails and notes, and control volume, brightness, "
    "media and your screen."
)

# Factual questions worth grounding with Wikipedia. Pronoun follow-ups ("how old is he") and
# personal questions ("what's my name") are left to the conversation context instead.
_FACT_Q = re.compile(
    r"^(?:who|what|where|when|which)\s+(?:is|was|are|were|did|invented|discovered|founded|wrote|painted|built|"
    r"created|directed|won)\b|^tell me (?:about|more about)\b|^(?:how (?:tall|old|big|far|long|many|much))\b"
)
_NOT_FACTUAL = re.compile(r"\b(?:you|your|yourself|my|me|i|he|she|it|they|him|her|them|his|its|their|this|that)\b")


def spoken_time(now: datetime.datetime) -> str:
    hour = now.hour % 12 or 12
    suffix = "AM" if now.hour < 12 else "PM"
    return f"It's {hour}:{now.minute:02d} {suffix}"


def spoken_date(now: datetime.datetime) -> str:
    return f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}"


def wiki_topic(question: str) -> Optional[str]:
    """The search phrase for a factual question, or None if Wikipedia wouldn't help."""
    q = question.lower().strip(" ?.!")
    if not _FACT_Q.search(q):
        return None
    q = re.sub(r"^tell me (?:more )?about\s+", "", q)
    if _NOT_FACTUAL.search(q):
        return None
    q = re.sub(r"^(?:who|what|where|when|which)\s+(?:is|was|are|were)\s+(?:the |a |an )?", "", q)
    return q or None


def answer_question(question: str) -> Tuple[bool, str]:
    from agent.context import conversation
    from agent.memory import memory
    from llm.planner import ask
    from skills.web_skill import first_sentences, wiki_summary

    topic = wiki_topic(question)
    reference = wiki_summary(topic) if topic else None
    answer = ask(question, conversation.messages(), memory.prompt_context(), reference or "")
    if answer:
        return True, answer
    if reference:  # no local LLM: the encyclopedia still knows
        return True, first_sentences(reference, 2)
    return False, "I can't reach the language model right now. Is Ollama running?"


class InfoSkill(BaseSkill):
    name = "info"

    HANDLED_INTENTS = {
        "tell_time", "tell_date", "ask", "wake_ack", "greet", "how_are_you", "who_are_you", "thank_you",
        "goodbye", "help", "calculate", "joke", "flip_coin", "roll_dice", "random_number", "repeat",
    }

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        now = datetime.datetime.now()
        if intent == "tell_time":
            return True, spoken_time(now)
        if intent == "tell_date":
            return True, spoken_date(now)
        if intent == "wake_ack":
            return True, "Yes? I'm listening."
        if intent == "greet":
            from agent.memory import memory

            part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
            name = f", {memory.name}" if memory.name else ""
            return True, f"Good {part}{name}! What can I do for you?"
        if intent == "how_are_you":
            return True, random.choice([
                "I'm doing great, thanks for asking! How can I help?",
                "Running smoothly and fully charged. What's up?",
                "Never better! What can I do for you?",
            ])
        if intent == "who_are_you":
            return True, "I'm Surf, your assistant. I live right here on your PC, and everything you say stays on it."
        if intent == "thank_you":
            return True, random.choice(["You're welcome!", "Anytime!", "Happy to help!"])
        if intent == "goodbye":
            return True, "Goodbye! Have a great day!"
        if intent == "help":
            return True, HELP
        if intent == "calculate":
            return self._calculate(slots.get("expression", ""))
        if intent == "joke":
            return True, random.choice(JOKES)
        if intent == "flip_coin":
            return True, f"It's {random.choice(['heads', 'tails'])}."
        if intent == "roll_dice":
            return True, f"You rolled a {random.randint(1, 6)}."
        if intent == "random_number":
            lo, hi = int(slots.get("low", 1)), int(slots.get("high", 100))
            lo, hi = min(lo, hi), max(lo, hi)
            return True, f"{random.randint(lo, hi)}."
        if intent == "repeat":
            from agent.context import conversation

            last = conversation.last_reply()
            return (True, last) if last else (False, "I haven't said anything yet.")
        if intent == "ask":
            return answer_question(slots.get("question", ""))
        return False, f"Unknown info action: {intent}"

    def _calculate(self, expression: str) -> Tuple[bool, str]:
        from agent.spoken import evaluate, spoken_number

        try:
            value = evaluate(expression)
        except ZeroDivisionError:
            return False, "You can't divide by zero."
        except (ValueError, SyntaxError, OverflowError, TypeError):
            return False, "I couldn't work that out."
        return True, f"That's {spoken_number(value)}."
