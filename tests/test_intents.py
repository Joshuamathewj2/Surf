import datetime

import pytest

from agent.intents import siri_intent
from agent.router import clean_utterance, route_command
from agent.safety import is_safe

NOW = datetime.datetime(2026, 10, 24, 10, 0)  # a Saturday morning


def parse(text):
    return siri_intent(clean_utterance(text), text, now=NOW)


@pytest.mark.parametrize(
    "text,action",
    [
        ("how much time is left on my timer", "timer_status"),
        ("cancel the timer", "cancel_timer"),
        ("what are my reminders", "list_reminders"),
        ("what's the news", "news"),
        ("pause the music", "media_play_pause"),
        ("play", "media_play_pause"),
        ("next song", "media_next"),
        ("skip", "media_next"),
        ("previous track", "media_previous"),
        ("how much battery do I have", "battery"),
        ("lock my computer", "lock_screen"),
        ("what's my name", "get_name"),
        ("what do you remember about me", "recall"),
        ("read my clipboard", "read_clipboard"),
        ("tell me a joke", "joke"),
        ("flip a coin", "flip_coin"),
        ("roll a dice", "roll_dice"),
        ("say that again", "repeat"),
        ("stop", "stop_speaking"),
        ("never mind", "dismiss"),
    ],
)
def test_simple_intents(text, action):
    assert parse(text)["action"] == action


@pytest.mark.parametrize(
    "text,seconds",
    [
        ("set a timer for 5 minutes", 300),
        ("set a 10 minute timer", 600),
        ("start a timer for an hour and a half", 5400),
        ("timer for twenty five seconds", 25),
    ],
)
def test_timers(text, seconds):
    route = parse(text)
    assert route["action"] == "set_timer" and route["seconds"] == seconds


@pytest.mark.parametrize(
    "text,expected",
    [
        ("wake me up at 6:30 am", datetime.datetime(2026, 10, 25, 6, 30)),
        ("set an alarm for 7 pm", datetime.datetime(2026, 10, 24, 19, 0)),
        ("set an alarm for 7 pm tomorrow", datetime.datetime(2026, 10, 25, 19, 0)),
    ],
)
def test_alarms(text, expected):
    route = parse(text)
    assert route["action"] == "set_alarm"
    assert datetime.datetime.fromtimestamp(route["due"]) == expected


@pytest.mark.parametrize(
    "text,task,expected",
    [
        ("remind me to call mom at 6 pm", "call mom", datetime.datetime(2026, 10, 24, 18, 0)),
        ("remind me in 20 minutes to check the oven", "check the oven", NOW + datetime.timedelta(minutes=20)),
        ("remind me at 7.30 pm to take my medicine", "take my medicine", datetime.datetime(2026, 10, 24, 19, 30)),
        ("remind me tomorrow at 9 am to submit the report", "submit the report", datetime.datetime(2026, 10, 25, 9, 0)),
    ],
)
def test_reminders(text, task, expected):
    route = parse(text)
    assert route["action"] == "set_reminder"
    assert route["task"] == task
    assert datetime.datetime.fromtimestamp(route["due"]) == expected


def test_reminder_without_a_time_asks_when():
    route = parse("remind me to drink water")
    assert route["task"] == "drink water" and route["due"] == 0


@pytest.mark.parametrize(
    "text,place,day,rain",
    [
        ("what's the weather", "", 0, False),
        ("what's the weather like in London tomorrow", "london", 1, False),
        ("will it rain tomorrow", "", 1, True),
        ("do I need an umbrella today", "", 0, True),
        ("how hot is it outside", "", 0, False),
        ("temperature in new york", "new york", 0, False),
    ],
)
def test_weather(text, place, day, rain):
    route = parse(text)
    assert route["action"] == "weather"
    assert (route["place"], route["day"], route["rain"]) == (place, day, rain)


def test_weather_words_in_other_requests_are_not_weather():
    assert route_command("play rain sounds on youtube")["action"] == "youtube_search"


@pytest.mark.parametrize("text,topic", [("latest technology news", "technology"), ("news about cricket", "cricket")])
def test_news_topics(text, topic):
    assert parse(text) == {"type": "direct", "action": "news", "topic": topic}


@pytest.mark.parametrize(
    "text,expression",
    [
        ("what's 15 percent of 240", "15 / 100 * 240"),
        ("what is two plus two times three", "2 + 2 * 3"),
        ("square root of 144", "sqrt(144)"),
    ],
)
def test_maths(text, expression):
    assert parse(text) == {"type": "direct", "action": "calculate", "expression": expression}


@pytest.mark.parametrize(
    "text,slots",
    [
        ("set volume to 40 percent", {"action": "set_volume", "level": 40}),
        ("volume 30", {"action": "set_volume", "level": 30}),
        ("turn the brightness down", {"action": "brightness", "step": -20}),
        ("set brightness to 70", {"action": "brightness", "level": 70}),
        ("turn on dark mode", {"action": "dark_mode", "on": True}),
        ("turn off dark mode", {"action": "dark_mode", "on": False}),
        ("open bluetooth settings", {"action": "open_settings", "page": "bluetooth"}),
        ("open downloads", {"action": "open_folder", "folder": "downloads"}),
        ("my name is Joshua", {"action": "set_name", "name": "joshua"}),
        ("call me Josh", {"action": "set_name", "name": "josh"}),
        ("remember that my locker code is 4512", {"action": "remember", "fact": "my locker code is 4512"}),
        ("forget my locker code", {"action": "forget", "about": "my locker code"}),
        ("forget everything", {"action": "forget", "about": ""}),
        ("pick a number between 1 and 10", {"action": "random_number", "low": 1, "high": 10}),
    ],
)
def test_slots(text, slots):
    route = parse(text)
    assert {k: route[k] for k in slots} == slots


def test_remember_keeps_the_speakers_casing():
    assert parse("Remember that my WiFi is called Surf-Home")["fact"] == "my WiFi is called Surf-Home"


def test_feelings_are_not_names():
    assert parse("I'm tired") is None
    assert parse("I am going home") is None


def test_clipboard_instructions():
    assert "French" in parse("translate this to French")["instruction"].title()
    assert parse("summarize what I copied")["action"] == "clipboard_ai"


def test_show_desktop_is_still_a_shortcut():
    assert route_command("show desktop")["action"] == "show_desktop"
    assert route_command("open my desktop folder")["action"] == "open_folder"


def test_play_without_a_service_plays_on_youtube():
    assert route_command("play despacito") == {"type": "direct", "action": "youtube_search", "query": "despacito", "play": True}
    assert route_command("play lofi on youtube")["play"] is True
    assert "play" not in route_command("search youtube for cats")


def test_compound_with_new_intents():
    route = route_command("set a timer for 5 minutes and play some jazz")
    assert route["type"] == "multi"
    assert [a["action"] for a in route["actions"]] == ["set_timer", "youtube_search"]


def test_questions_still_reach_the_llm():
    assert route_command("who wrote the ramayana")["action"] == "ask"
    assert route_command("how old is he")["action"] == "ask"


@pytest.mark.parametrize("text", ["delete my reminders", "remove all alarms", "clear the timer"])
def test_surfs_own_data_can_be_deleted(text):
    assert is_safe(text)
    assert route_command(text)["action"] == "cancel_timer"


@pytest.mark.parametrize("text", ["delete everything on my drive", "delete my files", "remove all programs"])
def test_destructive_requests_are_still_blocked(text):
    assert not is_safe(text)
