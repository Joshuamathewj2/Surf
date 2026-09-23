"""
skills/base.py
Base abstraction for modular desktop automation skills.
"""
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional

class BaseSkill(ABC):
    """Abstract interface that all automation skills must implement."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the skill."""
        pass

    @abstractmethod
    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        """Determines if this skill can process the given intent."""
        pass

    @abstractmethod
    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Executes the skill's action.
        Returns:
            (success: bool, verbal_feedback: str)
        """
        pass
