import time

import pytest

from agent.scheduler import Job, Scheduler
from skills import info_skill, timer_skill, web_skill
from skills.info_skill import InfoSkill, wiki_topic
from skills.memory_skill import second_person
from skills.timer_skill import TimerSkill, alert_text

FORECAST = {
    "current": {"temperature_2m": 29.4, "apparent_temperature": 33.2, "weather_code": 1},
    "daily": {
        "weather_code": [80, 63, 0],
        "temperature_2m_max": [30.6, 29.1, 31.0],
        "temperature_2m_min": [25.2, 24.8, 25.5],
        "precipitation_probability_max": [94, 70, 5],
    },
}


@pytest.fixture
def fresh_scheduler(tmp_path, monkeypatch):
    s = Scheduler(tmp_path / "r.json")
    monkeypatch.setattr(timer_skill, "scheduler", s)
    monkeypatch.setattr(s, "start", lambda: None)
    return s


def run(skill, intent, **slots):
    return skill.execute({"intent": intent, **slots})


def test_timer_skill_sets_and_reports(fresh_scheduler):
    skill = TimerSkill()
    assert run(skill, "set_timer", seconds=300) == (True, "Timer set for 5 minutes.")
    ok, text = run(skill, "timer_status")
    assert ok and "left" in text
    assert run(skill, "cancel_timer", kind="timer") == (True, "Cancelled your timer.")
    assert run(skill, "timer_status") == (True, "You don't have any timers running.")


def test_reminder_needs_a_time(fresh_scheduler):
    ok, text = run(TimerSkill(), "set_reminder", task="drink water", due=0)
    assert not ok and "When" in text
    ok, text = run(TimerSkill(), "set_reminder", task="drink water", due=time.time() + 600)
    assert ok and text.startswith("OK, I'll remind you to drink water in 10 minutes")


def test_alert_texts():
    assert alert_text(Job(1, "timer", 0, "", 300)) == "Your 5 minute timer is done!"
    assert alert_text(Job(1, "timer", 0, "pasta", 60)) == "Your pasta timer is done!"
    assert alert_text(Job(1, "reminder", 0, "call mom")) == "Reminder: call mom"


def test_weather_today_and_rain_questions():
    today = web_skill.describe_weather(FORECAST, "Chennai")
    assert today.startswith("It's 29 degrees with mostly clear skies in Chennai, feels like 33.")
    assert "high is 31 and the low is 25, with a 94 percent chance of rain" in today
    assert web_skill.describe_weather(FORECAST, "Chennai", 1, rain_question=True).startswith("Yes, rain is likely")
    assert web_skill.describe_weather(FORECAST, "Chennai", 2, rain_question=True).startswith("No rain expected")
    assert web_skill.describe_weather(FORECAST, "Chennai", 1).startswith("Tomorrow in Chennai: rain")


def test_offline_mode_never_touches_the_network(monkeypatch):
    monkeypatch.setattr(web_skill.config, "ONLINE", False)
    monkeypatch.setattr(web_skill.requests, "get", lambda *a, **k: pytest.fail("went online"))
    ok, text = web_skill.WebSkill().execute({"intent": "weather", "place": "paris"})
    assert not ok and "offline" in text
    assert web_skill.first_youtube_video("lofi") is None


def test_headlines_strip_publishers(monkeypatch):
    rss = b"""<rss><channel>
      <item><title>Big launch today - The Daily</title></item>
      <item><title>Rain expected all week - Weather Now</title></item>
      <item><title>Rain expected all week - Another Paper</title></item>
      <item><title>Team wins final - Sports Desk</title></item>
    </channel></rss>"""

    class Resp:
        content = rss

    monkeypatch.setattr(web_skill, "_get", lambda url, **p: Resp())
    assert web_skill.headlines("", "IN") == ["Big launch today", "Rain expected all week", "Team wins final"]


@pytest.mark.parametrize(
    "question,topic",
    [
        ("who wrote the ramayana", "who wrote the ramayana"),
        ("who is the prime minister of india", "prime minister of india"),
        ("tell me about black holes", "black holes"),
        ("what is photosynthesis?", "photosynthesis"),
        ("how old is he", None),
        ("what's my locker code", None),
        ("why is the sky blue", None),
    ],
)
def test_wiki_topic(question, topic):
    assert wiki_topic(question) == topic


def test_answers_fall_back_to_wikipedia_without_the_llm(monkeypatch):
    import llm.planner
    from skills import web_skill as w

    monkeypatch.setattr(llm.planner, "ask", lambda *a, **k: None)
    monkeypatch.setattr(w, "wiki_summary", lambda topic: "Valmiki is the poet of the Ramayana. He is called Adi Kavi. More.")
    assert info_skill.answer_question("who wrote the ramayana") == (
        True, "Valmiki is the poet of the Ramayana. He is called Adi Kavi.")


def test_answers_pass_history_memory_and_reference_to_the_llm(monkeypatch):
    import llm.planner
    from agent.context import conversation
    from skills import web_skill as w

    seen = {}

    def fake_ask(question, history, personal, reference):
        seen.update(question=question, history=history, reference=reference)
        return "Valmiki."

    monkeypatch.setattr(llm.planner, "ask", fake_ask)
    monkeypatch.setattr(w, "wiki_summary", lambda topic: "REF")
    conversation.clear()
    conversation.add("user", "tell me about the ramayana")
    conversation.add("assistant", "It's an epic.")
    assert info_skill.answer_question("who wrote the ramayana") == (True, "Valmiki.")
    assert seen["reference"] == "REF" and len(seen["history"]) == 2
    conversation.clear()


@pytest.mark.parametrize(
    "expression,answer",
    [("15 / 100 * 240", "That's 36."), ("2 + 2 * 3", "That's 8."), ("sqrt(2)", "That's 1.4142."), ("1 / 0", None)],
)
def test_calculate(expression, answer):
    ok, text = InfoSkill().execute({"intent": "calculate", "expression": expression})
    assert (text if ok else None) == answer


def test_random_number_in_range():
    for _ in range(20):
        ok, text = InfoSkill().execute({"intent": "random_number", "low": 3, "high": 5})
        assert ok and int(text.rstrip(".")) in (3, 4, 5)


def test_second_person():
    assert second_person("my car is blue and I love it") == "your car is blue and you love it"
