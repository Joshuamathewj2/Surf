import pytest

from agent.autocorrect import correct_command
from agent.safety import is_safe


@pytest.mark.parametrize(
    "text",
    ["delete all my files", "format the disk", "format c:", "shut down the computer", "shutdown", "rm -rf /", "uninstall chrome"],
)
def test_destructive_requests_are_blocked(text):
    assert not is_safe(text)


@pytest.mark.parametrize(
    "text",
    [
        "search for information about mars",  # regression: "format" inside "information"
        "google how to format a resume",
        "play shut up and dance on youtube",
        "open notepad",
    ],
)
def test_harmless_requests_pass(text):
    assert is_safe(text)


def test_autocorrect_fixes_misheard_names():
    assert correct_command("crome") == "chrome"
    assert correct_command("not bad") == "notepad"
    assert correct_command("open not bad") == "open notepad"
    assert correct_command("search yutube for lofi") == "search youtube for lofi"


def test_autocorrect_leaves_normal_speech_alone():
    assert correct_command("that movie was not bad") == "that movie was not bad"
    assert "quantum mechanics" in correct_command("search google for quantum mechanics")
