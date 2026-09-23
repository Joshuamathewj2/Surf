"""
main.pyw
Background daemon executable for Surf AI.
Runs silently with system tray icon and wake word activation.
"""
import os
import sys
import time

from tray.icon import start_tray_thread
from agent.router import route_command
from voice.recognizer import record_and_transcribe, load_model
from agent.speaker import speak
from skills.registry import dispatch_action

def handle_wake_word():
    speak("Yes?")
    command = record_and_transcribe()
    if not command:
        return

    print(f"[Daemon] Recognized: {command}")
    route = route_command(command)

    if route.get("type") == "direct":
        success, feedback = dispatch_action(route["action"], route)
        if feedback:
            speak(feedback)

    elif route.get("type") == "multi":
        for a in route.get("actions", []):
            if a.get("type") == "direct":
                success, feedback = dispatch_action(a["action"], a)
                if feedback:
                    speak(feedback)
                time.sleep(0.15)

if __name__ == "__main__":
    print("[Daemon] Starting Surf AI silently...")
    try:
        load_model()
    except Exception as e:
        print(f"[Daemon] Voice model pre-load warning: {e}")

    # Start system tray
    try:
        start_tray_thread()
    except Exception as e:
        print(f"[Daemon] Tray start warning: {e}")

    # Start wake word listener
    try:
        from wake.detector import start_listening
        start_listening(handle_wake_word)
    except Exception as e:
        print(f"[Daemon] Wake word listener warning: {e}")

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    os._exit(0)
