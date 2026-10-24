"""
agent/scheduler.py
Timers, alarms and reminders. One background thread checks what is due twice a second and
hands it to a callback (which speaks, chimes and makes the robot react).

Alarms and reminders are saved to disk so they survive a restart; timers are not (a
"5 minute timer" from yesterday is meaningless).
"""
import itertools
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from core import config
from core.logger import get_logger

logger = get_logger("scheduler")


@dataclass
class Job:
    id: int
    kind: str  # "timer" | "alarm" | "reminder"
    due: float  # epoch seconds
    label: str = ""  # reminder text, or a timer's name
    duration: int = 0  # timers: the length that was asked for, for "your 5 minute timer"


class Scheduler:
    def __init__(self, path: Optional[Path] = None, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path) if path else config.DATA_DIR / "reminders.json"
        self.clock = clock
        self.on_fire: Callable[[Job], None] = lambda job: None
        self._jobs: list[Job] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._load()

    # ------------------------------------------------------------------ persistence

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in raw:
            try:
                job = Job(**item)
            except TypeError:
                continue
            job.id = next(self._ids)
            self._jobs.append(job)

    def _save(self) -> None:
        keep = [asdict(j) for j in self._jobs if j.kind != "timer"]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(keep, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            logger.error(f"Couldn't save reminders: {e}")

    # ------------------------------------------------------------------ API

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="Scheduler")
            self._thread.start()

    def add(self, kind: str, due: float, label: str = "", duration: int = 0) -> Job:
        with self._lock:
            job = Job(next(self._ids), kind, due, label, duration)
            self._jobs.append(job)
            self._jobs.sort(key=lambda j: j.due)
            self._save()
        logger.info(f"Scheduled {kind} '{label}' at {time.strftime('%H:%M:%S', time.localtime(due))}")
        return job

    def jobs(self, kind: Optional[str] = None) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs if kind is None or j.kind == kind]

    def cancel(self, kind: Optional[str] = None) -> list[Job]:
        """Cancel every job of `kind` (all kinds if None). Returns what was cancelled."""
        with self._lock:
            gone = [j for j in self._jobs if kind is None or j.kind == kind]
            self._jobs = [j for j in self._jobs if j not in gone]
            self._save()
        return gone

    def due_jobs(self) -> list[Job]:
        """Pop everything that is due now (also used by tests instead of the thread)."""
        now = self.clock()
        with self._lock:
            due = [j for j in self._jobs if j.due <= now]
            if due:
                self._jobs = [j for j in self._jobs if j not in due]
                self._save()
        return due

    def _run(self) -> None:
        while True:
            for job in self.due_jobs():
                try:
                    self.on_fire(job)
                except Exception as e:  # a broken callback must not stop future reminders
                    logger.error(f"Reminder callback failed: {e}", exc_info=True)
            time.sleep(0.5)


scheduler = Scheduler()
