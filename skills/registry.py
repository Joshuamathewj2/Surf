"""
skills/registry.py
Central registry for all active skills.
"""
from typing import List, Tuple, Dict, Any, Optional
from skills.base import BaseSkill
from skills.browser_skill import BrowserSkill
from skills.app_skill import AppSkill
from skills.system_skill import SystemSkill
from skills.notes_skill import NotesSkill
from core.logger import get_logger

logger = get_logger("skills.registry")

class SkillRegistry:
    def __init__(self):
        self._skills: List[BaseSkill] = []
        self._register_default_skills()

    def _register_default_skills(self):
        self.register(BrowserSkill())
        self.register(AppSkill())
        self.register(SystemSkill())
        self.register(NotesSkill())

    def register(self, skill: BaseSkill):
        self._skills.append(skill)
        logger.debug(f"Registered skill: {skill.name}")

    def dispatch(self, intent: str, slots: Dict[str, Any]) -> Tuple[bool, str]:
        """Finds a matching skill and executes the intent."""
        # Ensure intent is included in slots dictionary for the skill
        slots_with_intent = dict(slots)
        slots_with_intent["intent"] = intent

        for skill in self._skills:
            if skill.can_handle(intent, slots_with_intent):
                logger.info(f"Dispatching intent '{intent}' to skill '{skill.name}'")
                return skill.execute(slots_with_intent)

        logger.warning(f"No skill found to handle intent: {intent}")
        return False, f"Unsupported action: {intent}"

# Global registry instance
global_registry = SkillRegistry()

def dispatch_action(intent: str, slots: Dict[str, Any]) -> Tuple[bool, str]:
    return global_registry.dispatch(intent, slots)
