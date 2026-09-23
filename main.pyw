"""
main.pyw
Background daemon executable for Surf AI.
Runs silently with no console window.
"""
import os
import sys
import time

from tray.icon import start_tray_thread
from wake.detector import start_listening
from agent.router import route_command
from executor.actions import execute_action
from voice.recognizer import record_and_transcribe, load_model
from agent.speaker import speak

def handle_wake_word():
    # Wake word detected, trigger voice capture
    speak("Yes?")
    command = record_and_transcribe()
    if command:
        print(f"[Daemon] Recognized: {command}")
        route = route_command(command)
        if route.get("type") == "direct":
            from executor.actions import globals as ex_globals
            # Or simpler, map them natively, but for daemon we should reuse logic
            # actually our route_command just returns dict. We can route it via execute_action indirectly
            # but direct actions are handled inline in loop.py usually.
            # Let's import the same execution block as loop.py.
            try:
                from executor.actions import (
                    open_chrome, close_chrome, youtube_search, play_spotify,
                    open_app, google_search, open_url, new_browser_tab, close_browser_tab,
                    take_screenshot, volume_up, volume_down, mute_audio, click_text
                )
                action = route.get("action")
                if action == "open_chrome": open_chrome()
                elif action == "close_chrome": close_chrome()
                elif action == "youtube_search": youtube_search(route.get("query", ""))
                elif action == "play_spotify": play_spotify(route.get("query", ""))
                elif action == "open_app": open_app(route["app"])
                elif action == "google_search": google_search(route["query"])
                elif action == "open_url": open_url(route["url"])
                elif action == "new_browser_tab": new_browser_tab()
                elif action == "close_browser_tab": close_browser_tab()
                elif action == "take_screenshot": take_screenshot()
                elif action == "volume_up": volume_up()
                elif action == "volume_down": volume_down()
                elif action == "mute_audio": mute_audio()
                elif action == "click_text": click_text(route["target"])
            except Exception as e:
                print(f"[Daemon Exec Error] {e}")

if __name__ == "__main__":
    print("[Daemon] Starting Surf AI silently...")
    # Pre-load models
    load_model()
    
    # Start tray
    start_tray_thread()
    
    # Start wake word
    start_listening(handle_wake_word)

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    os._exit(0)
