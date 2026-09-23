"""
agent/loop.py
Main agent loop: handles text and voice input, intent routing,
modular skill dispatch, and LLM planning fallback.
"""
import json
import sys
import os
import time

try:
    from interface.hud import set_state
except ImportError:
    def set_state(*args, **kwargs): pass

from core.logger import get_logger
from agent.router import route_command
from agent.autocorrect import correct_command
from agent.safety import is_safe
from agent.speaker import speak
from skills.registry import dispatch_action

logger = get_logger("loop")

BANNER = r"""
 ____  _   _ ____  _____
/ ___|| | | |  _ \|  ___|
\___ \| | | | |_) | |_
 ___) | |_| |  _ <|  _|
|____/ \___/|_| \_\_|

  Local AI Desktop Automation Agent (v2.0)
"""

def execute_direct_intent(action_dict: dict) -> bool:
    """Executes a single direct intent using the modular skills registry."""
    action = action_dict.get("action", "")
    success, feedback = dispatch_action(action, action_dict)
    if feedback:
        speak(feedback)
    return success

def run():
    print(BANNER)
    try:
        mode = input("Mode: [1] Text  [2] Voice → ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
        os._exit(0)

    if mode == "2":
        try:
            from voice.recognizer import load_model
            load_model()
        except Exception as e:
            logger.warning(f"Voice model pre-load warning: {e}")

    while True:
        set_state("idle", "")

        if mode == "2":
            set_state("listening", "LISTENING")
            try:
                from voice.recognizer import record_and_transcribe
                user_input = record_and_transcribe()
            except Exception as e:
                logger.error(f"Voice capture error: {e}")
                user_input = ""

            if user_input:
                print(f"\n[VOICE INPUT] \"{user_input}\"")
        else:
            try:
                set_state("listening", "AWAITING INPUT")
                user_input = input("\n>>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                os._exit(0)

        if not user_input:
            set_state("idle", "IDLE")
            continue

        if user_input.lower() in ["exit", "quit", "q", "3"]:
            print("Goodbye!")
            os._exit(0)

        # 1. Phonetic & Entity Autocorrect
        corrected = correct_command(user_input)
        if corrected != user_input:
            logger.info(f"Corrected: \"{user_input}\" -> \"{corrected}\"")
            user_input = corrected

        # 2. Safety Gate
        if not is_safe(user_input):
            set_state("error", "RESTRICTED")
            print("[BLOCKED] Restricted or dangerous system command.")
            speak("Command blocked for safety.")
            continue

        # 3. Intent Routing
        route = route_command(user_input)

        # 4. Action Execution
        if route["type"] == "direct":
            set_state("executing", "EXECUTING")
            execute_direct_intent(route)
            set_state("idle", "IDLE")

        elif route["type"] == "multi":
            set_state("executing", "EXECUTING MULTI")
            logger.info(f"Executing compound command with {len(route['actions'])} steps:")
            for idx, sub_action in enumerate(route["actions"], 1):
                logger.info(f"Step {idx}: {sub_action.get('action')}")
                if sub_action.get("type") == "direct":
                    execute_direct_intent(sub_action)
                time.sleep(0.15)
            set_state("idle", "IDLE")

        else:
            # 5. LLM Planner Fallback
            set_state("thinking", "PLANNING")
            print(f'\n[Planner] Interpreting complex query: "{user_input}" ...')

            try:
                from llm.planner import plan_actions
                from executor.actions import execute_action

                # Only query vision if explicitly requested
                context = ""
                if any(w in user_input.lower() for w in ["screen", "button", "see", "click"]):
                    try:
                        from vision.screen_reader import read_screen_text
                        screen_text = read_screen_text()
                        if screen_text:
                            context = f" (Screen contains: {screen_text[:300]})"
                    except Exception:
                        pass

                steps = plan_actions(user_input + context)
                if not steps:
                    set_state("error", "PLAN FAILED")
                    print("[Planner] No actions generated (is Ollama running?). Try a direct command.\n")
                    speak("Could not generate a plan for that command.")
                    continue

                print(f"[Planner] Generated {len(steps)} action(s):")
                print(json.dumps(steps, indent=2))

                set_state("executing", f"RUNNING {len(steps)} STEPS")
                for i, step in enumerate(steps, 1):
                    print(f"  Step {i}/{len(steps)}:")
                    execute_action(step)
                print("[Done] All actions executed.\n")

            except Exception as e:
                logger.error(f"Planning failed: {e}")
                set_state("error", "ERROR")
                speak("Error during plan execution.")

            set_state("idle", "IDLE")
