"""
agent/context.py
Short-term conversation memory, so follow-ups work like they do with Siri:

    "Who wrote the Ramayana?"  ->  "Valmiki..."
    "When did he live?"        ->  the LLM sees the previous exchange and knows who "he" is.

Exchanges expire after a few minutes of silence so an old topic doesn't leak into a new one.
"""
import threading
import time
from collections import deque
from typing import Optional

from core import config


class Conversation:
    def __init__(self, turns: int = config.CONTEXT_TURNS, ttl: float = config.CONTEXT_TTL_SEC) -> None:
        self.ttl = ttl
        self._turns: deque = deque(maxlen=turns * 2)  # (role, text, timestamp)
        self._lock = threading.Lock()

    def add(self, role: str, text: str, now: Optional[float] = None) -> None:
        if not text:
            return
        now = time.time() if now is None else now
        with self._lock:
            if self._turns and self._turns[-1][0] == role:
                # Several spoken replies to one request ("Let me think." + the answer) are one turn.
                prev_role, prev_text, _ = self._turns.pop()
                text = f"{prev_text} {text}"
            self._turns.append((role, text, now))

    def messages(self, now: Optional[float] = None) -> list[dict]:
        """Recent exchanges as chat messages, oldest first ([] once the conversation went quiet)."""
        now = time.time() if now is None else now
        with self._lock:
            if not self._turns or now - self._turns[-1][2] > self.ttl:
                return []
            return [{"role": role, "content": text} for role, text, _ in self._turns]

    def last_reply(self) -> Optional[str]:
        with self._lock:
            for role, text, _ in reversed(self._turns):
                if role == "assistant":
                    return text
        return None

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()


conversation = Conversation()
