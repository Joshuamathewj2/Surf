"""
test_system.py
Automated test suite verifying the refactored Surf components.
"""
import sys
import os

# Ensure current dir is in sys.path
sys.path.insert(0, os.path.abspath("."))

def test_autocorrect():
    from agent.autocorrect import correct_command
    print("[TEST] Running Autocorrect Tests...")
    assert correct_command("crome") == "chrome", f"Failed: {correct_command('crome')}"
    assert correct_command("not bad") == "notepad", f"Failed: {correct_command('not bad')}"
    assert correct_command("yutube") == "youtube", f"Failed: {correct_command('yutube')}"
    
    # Ensure query arguments are NOT corrupted
    res = correct_command("search google for quantum mechanics")
    assert "quantum mechanics" in res, f"Query corrupted: {res}"
    print("  --> Autocorrect tests PASSED.")

def test_router_single_and_variations():
    from agent.router import route_command
    print("[TEST] Running Intent Router Tests (Phrasing Variations)...")

    # Chrome variations
    r1 = route_command("open chrome")
    assert r1.get("action") == "open_chrome", f"Failed: {r1}"
    r2 = route_command("launch chrome")
    assert r2.get("action") == "open_chrome", f"Failed: {r2}"
    r3 = route_command("start chrome")
    assert r3.get("action") == "open_chrome", f"Failed: {r3}"
    r4 = route_command("close chrome")
    assert r4.get("action") == "close_chrome", f"Failed: {r4}"

    # Notepad variations
    r5 = route_command("open notepad")
    assert r5.get("action") == "open_notepad", f"Failed: {r5}"
    r6 = route_command("launch notepad")
    assert r6.get("action") == "open_notepad", f"Failed: {r6}"

    # YouTube variations
    r7 = route_command("search youtube for lofi hip hop")
    assert r7.get("action") == "youtube_search" and "lofi" in r7.get("query", ""), f"Failed: {r7}"
    r8 = route_command("play synthwave on youtube")
    assert r8.get("action") == "youtube_search" and "synthwave" in r8.get("query", ""), f"Failed: {r8}"

    # System controls
    r9 = route_command("volume up")
    assert r9.get("action") == "volume_up", f"Failed: {r9}"
    r10 = route_command("louder")
    assert r10.get("action") == "volume_up", f"Failed: {r10}"
    r11 = route_command("mute")
    assert r11.get("action") == "mute_audio", f"Failed: {r11}"

    print("  --> Intent Router single command tests PASSED.")

def test_router_compound_commands():
    from agent.router import route_command
    print("[TEST] Running Multi-Step Compound Command Tests...")

    rc = route_command("open chrome and search lofi on youtube")
    assert rc.get("type") == "multi", f"Expected multi, got: {rc}"
    actions = rc.get("actions", [])
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"
    assert actions[0].get("action") == "open_chrome", f"Action 1 failed: {actions[0]}"
    assert actions[1].get("action") == "youtube_search", f"Action 2 failed: {actions[1]}"

    rc2 = route_command("open notepad and type hello world")
    assert rc2.get("type") == "multi"
    assert len(rc2.get("actions", [])) == 2
    assert rc2["actions"][0].get("action") == "open_notepad"
    assert rc2["actions"][1].get("action") == "type_text"
    assert rc2["actions"][1].get("text") == "hello world"

    print("  --> Compound Command tests PASSED.")

def test_skills_dispatch():
    from skills.registry import global_registry
    print("[TEST] Running Skills Registry Dispatch Tests...")
    
    # Test skill matching
    slots = {"intent": "new_tab"}
    can = any(s.can_handle("new_tab", slots) for s in global_registry._skills)
    assert can, "No skill found for new_tab"

    slots2 = {"intent": "open_app", "app": "calc"}
    can2 = any(s.can_handle("open_app", slots2) for s in global_registry._skills)
    assert can2, "No skill found for open_app"

    print("  --> Skills Registry tests PASSED.")

def test_audio_and_voice_modules():
    print("[TEST] Testing Audio & Voice Module Imports...")
    import sounddevice as sd
    from faster_whisper import WhisperModel
    from core.audio_capture import record_audio_with_vad
    from voice.recognizer import load_model
    print("  --> Audio & Speech imports PASSED.")

if __name__ == "__main__":
    print("\n==========================================")
    print("         SURF SYSTEM VERIFICATION         ")
    print("==========================================\n")
    test_autocorrect()
    test_router_single_and_variations()
    test_router_compound_commands()
    test_skills_dispatch()
    test_audio_and_voice_modules()
    print("\n==========================================")
    print("      ALL SYSTEM UNIT TESTS PASSED!       ")
    print("==========================================\n")
