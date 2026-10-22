"""
agent/safety.py
Blocks destructive requests before they reach any skill or the LLM planner.

Matching is on whole words/phrases: a naive substring check blocked harmless
requests such as "search for information" (it contains "format").
"""
import re

BLOCKED_PATTERNS = [
    r"\bdelete\b",
    r"\berase\b",
    r"\bwipe\b",
    r"\bformat (?:the |my )?(?:disk|drive|pc|computer|[a-z]:)",
    r"\bshut ?down\b",
    r"\brestart (?:the |my )?(?:pc|computer|system)\b",
    r"\bremove all\b",
    r"\brm -rf\b",
    r"\bdel /[sfq]\b",
    r"\bkill (?:all|every)\b",
    r"\buninstall\b",
    r"\bregistry\b",
]

_BLOCKED = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]


def is_safe(command: str) -> bool:
    return not any(p.search(command) for p in _BLOCKED)
