import json

from agent.context import Conversation
from agent.memory import Memory
from agent.scheduler import Scheduler


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_scheduler_fires_due_jobs_in_order(tmp_path):
    clock = Clock()
    s = Scheduler(tmp_path / "r.json", clock=clock)
    s.add("timer", 1060, duration=60)
    s.add("reminder", 1030, "stretch")
    assert s.due_jobs() == []
    clock.t = 1045
    assert [j.label for j in s.due_jobs()] == ["stretch"]
    clock.t = 2000
    assert [j.kind for j in s.due_jobs()] == ["timer"]
    assert s.jobs() == []


def test_alarms_and_reminders_survive_a_restart_but_timers_do_not(tmp_path):
    path = tmp_path / "r.json"
    s = Scheduler(path, clock=Clock())
    s.add("timer", 5000, duration=60)
    s.add("alarm", 6000)
    s.add("reminder", 7000, "call mom")
    saved = json.loads(path.read_text())
    assert sorted(j["kind"] for j in saved) == ["alarm", "reminder"]
    again = Scheduler(path, clock=Clock())
    assert sorted(j.kind for j in again.jobs()) == ["alarm", "reminder"]


def test_cancel_by_kind(tmp_path):
    s = Scheduler(tmp_path / "r.json", clock=Clock())
    s.add("timer", 5000)
    s.add("alarm", 6000)
    assert [j.kind for j in s.cancel("timer")] == ["timer"]
    assert [j.kind for j in s.jobs()] == ["alarm"]
    assert len(s.cancel()) == 1


def test_memory_round_trip(tmp_path):
    m = Memory(tmp_path / "m.json")
    m.set_name("joshua")
    m.remember("my locker code is 4512")
    m.remember("My locker code is 4512")  # duplicates are ignored
    m.remember("my sister's birthday is on March 3")
    again = Memory(tmp_path / "m.json")
    assert again.name == "Joshua"
    assert again.facts() == ["my locker code is 4512", "my sister's birthday is on March 3"]
    ctx = again.prompt_context()
    assert "Joshua" in ctx and "locker code is 4512" in ctx


def test_memory_forget(tmp_path):
    m = Memory(tmp_path / "m.json")
    m.remember("my locker code is 4512")
    m.remember("my car is blue")
    assert m.forget("my locker code") == 1
    assert m.facts() == ["my car is blue"]
    assert m.forget("the moon") == 0
    assert m.forget("") == 1
    assert m.facts() == []


def test_conversation_merges_turns_and_expires():
    c = Conversation(turns=3, ttl=60)
    c.add("user", "who wrote the ramayana", now=0)
    c.add("assistant", "Let me think.", now=1)
    c.add("assistant", "Valmiki.", now=5)
    assert c.messages(now=10) == [
        {"role": "user", "content": "who wrote the ramayana"},
        {"role": "assistant", "content": "Let me think. Valmiki."},
    ]
    assert c.last_reply() == "Let me think. Valmiki."
    assert c.messages(now=100) == []  # went quiet: a new topic starts fresh


def test_conversation_keeps_only_recent_turns():
    c = Conversation(turns=2, ttl=60)
    for i in range(5):
        c.add("user", f"q{i}", now=i)
        c.add("assistant", f"a{i}", now=i)
    assert [m["content"] for m in c.messages(now=5)] == ["q3", "a3", "q4", "a4"]
