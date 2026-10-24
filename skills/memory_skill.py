"""
skills/memory_skill.py
"Call me Josh", "remember that my locker code is 4512", "what do you remember",
"forget my locker code", "forget everything". Remembered facts are also given to the LLM,
so "what's my locker code?" is answered from memory.
"""
from typing import Any, Dict, Tuple

from agent.memory import memory
from skills.base import BaseSkill


def second_person(fact: str) -> str:
    """'my car is blue' -> 'your car is blue' (for reading facts back)."""
    swaps = {"my": "your", "i": "you", "i'm": "you're", "me": "you", "mine": "yours", "am": "are"}
    return " ".join(swaps.get(w.lower(), w) for w in fact.split())


class MemorySkill(BaseSkill):
    name = "memory"

    HANDLED_INTENTS = {"set_name", "get_name", "remember", "recall", "forget"}

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        if intent == "set_name":
            name = slots.get("name", "").strip()
            if not name:
                return False, "What should I call you?"
            memory.set_name(name)
            return True, f"Nice to meet you, {memory.name}. I'll remember that."
        if intent == "get_name":
            return (True, f"You're {memory.name}.") if memory.name else (True, "I don't know your name yet. Say: call me, and your name.")
        if intent == "remember":
            fact = slots.get("fact", "").strip()
            if not fact:
                return False, "What should I remember?"
            memory.remember(fact)
            return True, f"Got it. I'll remember that {second_person(fact)}."
        if intent == "recall":
            facts = memory.facts()
            if not facts and not memory.name:
                return True, "You haven't asked me to remember anything yet."
            parts = [f"your name is {memory.name}"] if memory.name else []
            parts += [second_person(f) for f in facts[-6:]]
            return True, "I remember that " + "; ".join(parts) + "."
        if intent == "forget":
            about = slots.get("about", "")
            removed = memory.forget(about)
            if not about:
                return True, "Done. I've forgotten everything you told me."
            return (True, "OK, I've forgotten that.") if removed else (False, "I don't remember anything like that.")
        return False, f"Unknown memory action: {intent}"
