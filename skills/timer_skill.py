"""
skills/timer_skill.py
"Set a timer for 10 minutes", "wake me up at 6:30", "remind me to call mom at 7 pm",
"how long is left on my timer", "what are my reminders", "cancel the alarm".
"""
import datetime
import re
import time
from typing import Any, Dict, Tuple

from agent.scheduler import Job, scheduler
from agent.spoken import spoken_duration
from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.timer")

KIND_WORDS = {"timer": "timer", "alarm": "alarm", "reminder": "reminder"}


def clock_text(epoch: float, now: float) -> str:
    """'7:30 PM', or 'tomorrow at 7:30 AM' when it isn't today."""
    when = datetime.datetime.fromtimestamp(epoch)
    today = datetime.datetime.fromtimestamp(now).date()
    hour = when.hour % 12 or 12
    text = f"{hour}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"
    if when.date() == today + datetime.timedelta(days=1):
        return f"tomorrow at {text}"
    if when.date() != today:
        return f"{when.strftime('%A')} at {text}"
    return text


def alert_text(job: Job) -> str:
    """What Surf says when a job fires."""
    if job.kind == "timer":
        length = re.sub(r"\b(hour|minute|second)s\b", r"\1", spoken_duration(job.duration))  # "5 minute timer"
        name = f"{job.label} timer" if job.label else f"{length} timer"
        return f"Your {name} is done!"
    if job.kind == "alarm":
        return "It's " + clock_text(job.due, job.due) + ". Time to wake up!" if not job.label else f"Alarm: {job.label}"
    return f"Reminder: {job.label}"


class TimerSkill(BaseSkill):
    name = "timer"

    HANDLED_INTENTS = {"set_timer", "set_alarm", "set_reminder", "timer_status", "list_reminders", "cancel_timer"}

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        now = time.time()
        scheduler.start()

        if intent == "set_timer":
            seconds = int(slots.get("seconds") or 0)
            if seconds <= 0:
                return False, "How long should the timer be?"
            scheduler.add("timer", now + seconds, slots.get("label", ""), seconds)
            return True, f"Timer set for {spoken_duration(seconds)}."

        if intent == "set_alarm":
            due = float(slots.get("due") or 0)
            if due <= now:
                return False, "What time should I set the alarm for?"
            scheduler.add("alarm", due, slots.get("label", ""))
            return True, f"Alarm set for {clock_text(due, now)}."

        if intent == "set_reminder":
            task = slots.get("task", "").strip()
            due = float(slots.get("due") or 0)
            if not task:
                return False, "What should I remind you about?"
            if due <= now:
                return False, "When should I remind you? Try: remind me in 10 minutes to stretch."
            scheduler.add("reminder", due, task)
            when = (f"in {spoken_duration(round(due - now))}" if due - now < 3600 else f"at {clock_text(due, now)}")
            return True, f"OK, I'll remind you to {task} {when}."

        if intent == "timer_status":
            timers = scheduler.jobs("timer")
            if not timers:
                return True, "You don't have any timers running."
            parts = [f"{spoken_duration(max(1, round(t.due - now)))} left" for t in timers]
            if len(parts) == 1:
                return True, f"Your timer has {parts[0]}."
            return True, f"You have {len(parts)} timers: " + ", ".join(parts) + "."

        if intent == "list_reminders":
            kind = KIND_WORDS.get(slots.get("kind", ""), None)
            jobs = scheduler.jobs(kind)
            if not jobs:
                return True, f"You don't have any {kind + 's' if kind else 'reminders, alarms or timers'}."
            items = []
            for j in jobs[:5]:
                if j.kind == "reminder":
                    items.append(f"{j.label} at {clock_text(j.due, now)}")
                elif j.kind == "alarm":
                    items.append(f"an alarm at {clock_text(j.due, now)}")
                else:
                    items.append(f"a timer with {spoken_duration(max(1, round(j.due - now)))} left")
            return True, "You have " + "; ".join(items) + "."

        if intent == "cancel_timer":
            kind = KIND_WORDS.get(slots.get("kind", ""), None)
            gone = scheduler.cancel(kind)
            if not gone:
                return True, f"There's no {kind or 'timer, alarm or reminder'} to cancel."
            what = kind or "timer"
            return True, f"Cancelled {len(gone)} {what}s." if len(gone) > 1 else f"Cancelled your {gone[0].kind}."

        return False, f"Unknown timer action: {intent}"
