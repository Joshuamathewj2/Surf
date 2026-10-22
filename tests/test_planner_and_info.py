import datetime

from llm.planner import validate_actions
from skills.info_skill import spoken_date, spoken_time


def test_valid_plan_passes():
    plan = {"actions": [{"action": "open_app", "name": "notepad"}, {"action": "wait", "seconds": 1.5}, {"action": "type", "text": "hi"}]}
    assert [s["action"] for s in validate_actions(plan)] == ["open_app", "wait", "type"]


def test_shell_and_unknown_actions_are_dropped():
    plan = [
        {"action": "run_command", "cmd": "del /s /q C:\\"},
        {"action": "click", "x": 10, "y": 20},
        {"action": "take_screenshot"},
    ]
    assert validate_actions(plan) == [{"action": "take_screenshot"}]


def test_placeholders_and_missing_fields_are_dropped():
    plan = [{"action": "type", "text": "<text to type>"}, {"action": "open_app"}, {"action": "type", "text": ""}]
    assert validate_actions(plan) == []


def test_waits_are_capped():
    assert validate_actions([{"action": "wait", "seconds": 600}])[0]["seconds"] == 10


def test_bare_list_and_alternate_keys():
    assert validate_actions({"steps": [{"action": "press", "key": "enter"}]}) == [{"action": "press", "key": "enter"}]
    assert validate_actions("nonsense") == []


def test_spoken_time_and_date():
    t = datetime.datetime(2026, 10, 22, 15, 5)
    assert spoken_time(t) == "It's 3:05 PM"
    assert spoken_time(t.replace(hour=0)) == "It's 12:05 AM"
    assert spoken_date(t) == "Today is Thursday, 22 October 2026"


def test_numeric_strings_are_coerced():
    assert validate_actions([{"action": "wait", "seconds": "2"}]) == [{"action": "wait", "seconds": 2.0}]
