import pytest

from agent.router import clean_utterance, route_command, split_compound_command


@pytest.mark.parametrize(
    "text,action",
    [
        ("open chrome", "open_chrome"),
        ("launch chrome", "open_chrome"),
        ("close chrome", "close_chrome"),
        ("open notepad", "open_notepad"),
        ("start notes", "open_notepad"),
        ("open youtube", "open_youtube"),
        ("take a screenshot", "take_screenshot"),
        ("volume up", "volume_up"),
        ("turn the volume down", "volume_down"),
        ("mute", "mute_audio"),
        ("new tab", "new_tab"),
        ("close this tab", "close_tab"),
        ("what time is it", "tell_time"),
        ("what's the date", "tell_date"),
        ("open calculator", "open_app"),
        ("click Save", "click_text"),
    ],
)
def test_direct_intents(text, action):
    assert route_command(text).get("action") == action


@pytest.mark.parametrize(
    "text,action,slot,value",
    [
        ("search youtube for lofi hip hop", "youtube_search", "query", "lofi hip hop"),
        ("play synthwave on youtube", "youtube_search", "query", "synthwave"),
        ("play rock and roll on youtube", "youtube_search", "query", "rock and roll"),
        ("play bohemian rhapsody on spotify", "play_spotify", "query", "bohemian rhapsody"),
        ("google quantum computing", "google_search", "query", "quantum computing"),
        ("search for the best biryani in chennai", "google_search", "query", "the best biryani in chennai"),
        ("open github.com", "open_url", "url", "github.com"),
        ("open vs code", "open_app", "app", "vs code"),
    ],
)
def test_slots(text, action, slot, value):
    route = route_command(text)
    assert route.get("action") == action
    assert route.get(slot) == value


def test_wake_words_and_filler_are_stripped():
    assert clean_utterance("Hey Jarvis, can you please open Chrome?") == "open chrome"
    assert route_command("Hey Jarvis open notepad please").get("action") == "open_notepad"
    assert route_command("Jarvis").get("type") == "empty"


def test_literal_typing_keeps_original_casing():
    route = route_command("Hey Jarvis type Hello World")
    assert route["action"] == "type_text"
    assert route["text"] == "Hello World"


def test_compose_vs_literal_write():
    assert route_command("write a poem about rain")["action"] == "compose"
    assert route_command("write an email to my manager saying I'm late")["action"] == "compose"
    assert route_command("write hello there")["action"] == "type_text"


def test_questions_get_spoken_answers():
    route = route_command("who wrote the Ramayana?")
    assert route["action"] == "ask"
    assert route_command("explain black holes simply")["action"] == "ask"


def test_compound_split_only_before_a_new_action():
    assert split_compound_command("open chrome and search lofi on youtube") == [
        "open chrome",
        "search lofi on youtube",
    ]
    assert split_compound_command("play rock and roll on youtube") == ["play rock and roll on youtube"]


def test_multi_step_command():
    route = route_command("open notepad and type hello world")
    assert route["type"] == "multi"
    assert [a["action"] for a in route["actions"]] == ["open_notepad", "type_text"]


def test_compound_with_unknown_part_goes_to_planner():
    # Regression: unknown parts used to become silent no-op steps ("Step 1: None").
    assert route_command("open notepad and then rearrange my desktop icons")["type"] == "llm"


def test_unknown_goes_to_planner():
    assert route_command("rearrange my windows side by side")["type"] == "llm"


@pytest.mark.parametrize(
    "text,action",
    [
        ("save", "save"),
        ("save this file", "save"),
        ("undo that", "undo"),
        ("copy this", "copy"),
        ("paste it", "paste"),
        ("select all", "select_all"),
        ("go back", "go_back"),
        ("go to the previous page", "go_back"),
        ("refresh the page", "refresh"),
        ("next tab", "next_tab"),
        ("switch windows", "switch_window"),
        ("minimize this window", "minimize_window"),
        ("show desktop", "show_desktop"),
        ("zoom in", "zoom_in"),
        ("scroll down", "scroll_down"),
        ("hey jarvis press enter", "press_enter"),
    ],
)
def test_everyday_shortcuts_skip_the_llm(text, action):
    assert route_command(text).get("action") == action


def test_shortcut_phrases_only_match_whole_utterances():
    # "save" inside a longer request must not trigger Ctrl+S
    assert route_command("save the date on google calendar").get("action") != "save"


def test_copy_and_paste_compound():
    route = route_command("select all and copy it")
    assert [a["action"] for a in route["actions"]] == ["select_all", "copy"]
