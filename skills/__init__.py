"""
Skills package initialization.
"""
from skills.base import BaseSkill
from skills.registry import SkillRegistry, global_registry, dispatch_action

__all__ = ["BaseSkill", "SkillRegistry", "global_registry", "dispatch_action"]
