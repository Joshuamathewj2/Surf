"""
agent/memory.py
Things Surf remembers about you between runs: your name and facts you asked it to keep
("remember that my locker code is 4512"). Stored locally in a small JSON file.
"""
import datetime
import json
import re
import threading
from pathlib import Path
from typing import Optional

from core import config
from core.logger import get_logger

logger = get_logger("memory")


class Memory:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else config.DATA_DIR / "memory.json"
        self._lock = threading.Lock()
        self._data: Optional[dict] = None

    def _load(self) -> dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}
            self._data.setdefault("name", None)
            self._data.setdefault("facts", [])
        return self._data

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            logger.error(f"Couldn't save memory: {e}")

    @property
    def name(self) -> Optional[str]:
        with self._lock:
            return self._load()["name"]

    def set_name(self, name: str) -> None:
        with self._lock:
            self._load()["name"] = name.strip().title()
            self._save()

    def facts(self) -> list[str]:
        with self._lock:
            return [f["text"] for f in self._load()["facts"]]

    def remember(self, fact: str) -> str:
        """Store a fact as the user said it ("my locker code is 4512"). Returns the stored text."""
        fact = fact.strip().rstrip(".")
        with self._lock:
            data = self._load()
            if not any(f["text"].lower() == fact.lower() for f in data["facts"]):
                data["facts"].append({"text": fact, "added": datetime.datetime.now().isoformat(timespec="seconds")})
                self._save()
        return fact

    def forget(self, about: str) -> int:
        """Forget facts mentioning `about` (all of them if `about` is empty). Returns how many."""
        words = [w for w in re.findall(r"\w+", about.lower()) if len(w) > 2 and w not in ("that", "the", "about", "my")]
        with self._lock:
            data = self._load()
            before = len(data["facts"])
            if not words:
                data["facts"] = []
            else:
                data["facts"] = [f for f in data["facts"] if not all(w in f["text"].lower() for w in words)]
            removed = before - len(data["facts"])
            if removed:
                self._save()
        return removed

    def prompt_context(self) -> str:
        """A few lines for the LLM's system prompt so answers can use what you told Surf."""
        lines = []
        if self.name:
            lines.append(f"The user's name is {self.name}.")
        facts = self.facts()
        if facts:
            lines.append("Things the user asked you to remember (their own words):")
            lines.extend(f"- {f}" for f in facts[-25:])
        return "\n".join(lines)


memory = Memory()
