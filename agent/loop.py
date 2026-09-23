"""
agent/loop.py
Main agent loop: takes user input, calls the LLM planner, and
executes the resulting actions sequentially.
"""

import json
import sys
import os

try:
    from interface.hud import set_state
except ImportError:
    # Graceful fallback if no UI
    def set_state(*args, **kwargs): pass

# We ensure we can import all modules
try:
    from llm.planner import plan_actions
    from executor.actions import (
        execute_action, open_chrome, close_chrome, youtube_search,
        open_app, google_search, open_url, new_browser_tab, close_browser_tab,
        take_screenshot, volume_up, volume_down, mute_audio, click_text, play_spotify
    )
    from agent.router import route_command
    from agent.autocorrect import correct_command
    from agent.safety import is_safe
    from voice.recognizer import load_model, record_and_transcribe
except ImportError as e:
    print(f"Missing a dependency for imports: {e}")
    sys.exit(1)

BANNER = r"""
 ____  _   _ ____  _____
/ ___|| | | |  _ \|  ___|
\___ \| | | | |_) | |_
 ___) | |_| |  _ <|  _|
|____/ \___/|_| \_\_|

  Local AI Desktop Automation Agent
"""

def run():
    print(BANNER)
    try:
        mode = input("Mode: [1] Text  [2] Voice → ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
        os._exit(0)
        
    if mode == "2":
        load_model()
        
    while True:
        set_state("idle", "")
        
        if mode == "2":
            set_state("listening", "LISTENING")
            user_input = record_and_transcribe()
            if user_input:
                print("[VOICE INPUT]", user_input)
        else:
            try:
                set_state("listening", "AWAITING INPUT")
                user_input = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                os._exit(0)

        if not user_input:
            set_state("idle", "IDLE")
            continue

        if user_input.lower() in ["exit", "quit", "q", "3"]:
            print("Goodbye!")
            os._exit(0)

        # Correct
        user_input = correct_command(user_input)

        # Safety Check
        if not is_safe(user_input):
            set_state("error", "RESTRICTED")
            print("[BLOCKED] Unsafe command")
            continue

        # Route
        route = route_command(user_input)

        # Execute
        if route["type"] == "direct":
            set_state("executing", "EXECUTING")
            if route["action"] == "open_chrome":
                open_chrome()
            elif route["action"] == "close_chrome":
                close_chrome()
            elif route["action"] == "youtube_search":
                youtube_search(route.get("query", ""))
            elif route["action"] == "play_spotify":
                play_spotify(route.get("query", ""))
            elif route["action"] == "open_app":
                open_app(route["app"])
            elif route["action"] == "google_search":
                google_search(route["query"])
            elif route["action"] == "open_url":
                open_url(route["url"])
            elif route["action"] == "new_browser_tab":
                new_browser_tab()
            elif route["action"] == "close_browser_tab":
                close_browser_tab()
            elif route["action"] == "take_screenshot":
                take_screenshot()
            elif route["action"] == "volume_up":
                volume_up()
            elif route["action"] == "volume_down":
                volume_down()
            elif route["action"] == "mute_audio":
                mute_audio()
            elif route["action"] == "click_text":
                click_text(route["target"])
            elif route["action"] == "vision_click":
                # Fallback to click_text if vision_click matches
                click_text(route["target"])
            set_state("idle", "IDLE")
        else:
            set_state("thinking", "PLANNING")
            print(f'\n[Planner] Interpreting: "{user_input}" ...')
            
            # Vision and Memory integration for smarter planning
            try:
                from vision.screen_reader import read_screen_text
                from agent.memory import get_context_string, add_to_memory
                
                screen_text = read_screen_text()
                mem_context = get_context_string()
                
                context = mem_context
                if screen_text:
                    context += f" (Context: Current screen contains text: {screen_text[:500]})"
                user_input_with_context = user_input + context
            except Exception as e:
                print(f"  [WARN] Vision/Memory context failed: {e}")
                user_input_with_context = user_input

            steps = plan_actions(user_input_with_context)
            
            if not steps:
                set_state("error", "PLAN FAILED")
                print("[Planner] No actions generated. Try rephrasing.\n")
                continue
                
            print(f"[Planner] Generated {len(steps)} action(s):")
            print(json.dumps(steps, indent=2))
            
            set_state("executing", f"RUNNING {len(steps)} STEPS")
            print("\n[Executor] Running actions...")
            for i, step in enumerate(steps, 1):
                print(f"\n  Step {i}/{len(steps)}:")
                execute_action(step)
            print("\n[Done] All actions executed.\n")
            try:
                from agent.memory import add_to_memory
                add_to_memory(user_input, f"Executed {len(steps)} steps successfully.")
            except:
                pass
            set_state("idle", "IDLE")
