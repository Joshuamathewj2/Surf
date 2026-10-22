from agent import pipeline


class Recorder:
    def __init__(self, results=None):
        self.calls = []
        self.spoken = []
        self.results = results or {}

    def dispatch(self, action):
        self.calls.append(action)
        return self.results.get(action["action"], (True, f"did {action['action']}"))

    def speak(self, text):
        self.spoken.append(text)


def run(text, rec, monkeypatch=None):
    return pipeline.handle_command(text, speak=rec.speak, dispatch=rec.dispatch)


def test_direct_command_dispatches_and_speaks():
    rec = Recorder()
    out = run("hey jarvis open chrome", rec)
    assert out.ok and out.route == "direct"
    assert rec.calls[0]["action"] == "open_chrome"
    assert rec.spoken == ["did open_chrome"]


def test_blocked_command_never_dispatches():
    rec = Recorder()
    out = run("delete everything in documents", rec)
    assert out.route == "blocked" and not rec.calls


def test_multi_step_types_into_the_opened_window():
    rec = Recorder()
    out = run("open notepad and write a poem about rain", rec)
    assert out.route == "multi" and out.ok
    assert [c["action"] for c in rec.calls] == ["open_notepad", "compose"]
    # compose must not open a second Notepad after the first step opened one
    assert rec.calls[1]["open_first"] is False


def test_standalone_compose_opens_notepad():
    rec = Recorder()
    run("write a short note about tomorrow's meeting", rec)
    assert rec.calls[0]["action"] == "compose" and rec.calls[0]["open_first"] is True


def test_multi_step_stops_on_failure():
    rec = Recorder(results={"open_chrome": (False, "Chrome isn't installed")})
    out = run("open chrome and search youtube for lofi", rec)
    assert not out.ok
    assert len(rec.calls) == 1
    assert rec.spoken == ["Chrome isn't installed"]


def test_unknown_request_uses_planner(monkeypatch):
    executed = []
    import executor.actions
    import llm.planner

    plan = [{"action": "hotkey", "keys": ["win", "left"]}, {"action": "hotkey", "keys": ["alt", "tab"]}]
    monkeypatch.setattr(llm.planner, "plan_actions", lambda cmd: plan)
    monkeypatch.setattr(executor.actions, "execute_action", lambda step: executed.append(step) or True)
    rec = Recorder()
    out = run("arrange my two windows side by side", rec)
    assert out.route == "llm" and out.ok
    assert executed == plan
    assert rec.spoken[0] == "Let me figure that out."  # acknowledged before the slow LLM call


def test_everyday_shortcut_never_reaches_the_planner(monkeypatch):
    import llm.planner

    monkeypatch.setattr(llm.planner, "plan_actions", lambda cmd: (_ for _ in ()).throw(AssertionError("LLM called")))
    rec = Recorder()
    assert run("save this document", rec).route == "direct"
    assert rec.calls[0]["action"] == "save"


def test_planner_unavailable_is_reported(monkeypatch):
    import llm.planner

    monkeypatch.setattr(llm.planner, "plan_actions", lambda cmd: [])
    rec = Recorder()
    out = run("rearrange my desktop icons by colour", rec)
    assert not out.ok and "couldn't" in rec.spoken[-1]


def test_blank_notepad_detection():
    # Windows 11 restores session tabs: only a new "Untitled" Notepad tab is safe to type into.
    from skills.notes_skill import _is_blank_notepad

    assert _is_blank_notepad("Untitled - Notepad")
    assert not _is_blank_notepad("PARALLEL_PLAN.md - Notepad")
    assert not _is_blank_notepad("Untitled - Paint")
