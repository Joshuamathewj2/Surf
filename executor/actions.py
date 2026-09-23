"""
executor/actions.py
Executes desktop automation actions using pyautogui and subprocess.
Each function maps to a supported action from the LLM planner.
"""

import time
import datetime
import os
import subprocess
import pyautogui
import webbrowser
import pygetwindow as gw

import config
from agent.speaker import speak

# Safety: give the user a chance to abort by moving the mouse to a corner
pyautogui.FAILSAFE = True
# Minimal pause between pyautogui calls (reduced for speed)
pyautogui.PAUSE = 0.05


def open_start_menu():
    """Simulate pressing the Windows key to open the Start menu."""
    print("  [Action] Opening Start menu...")
    pyautogui.press("win")
    time.sleep(config.DELAY_BETWEEN_ACTIONS)

def open_app(app_name: str):
    print(f"[EXEC] open_app('{app_name}')")
    
    # Try using app_index first
    from agent.app_index import find_app
    path = find_app(app_name)
    if path:
        try:
            if os.path.isdir(path):
                subprocess.Popen(['code', path], shell=True)
                speak(f"Opening project {app_name} in VS Code")
            else:
                os.startfile(path)
                speak(f"Opening {app_name}")
            return
        except Exception as e:
            print(f"[WARN] Failed to open via app_index: {e}")
            
    try:
        subprocess.Popen(app_name)
        print(f"[OK] Opened {app_name} via subprocess")
        speak(f"Opening {app_name}")
    except FileNotFoundError:
        print(f"[WARN] FileNotFoundError for {app_name}, falling back to Start menu")
        pyautogui.press("win")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.5)
        pyautogui.press("enter")
        print(f"[OK] Opened {app_name} via Start menu")
        speak(f"Opening {app_name}")

def run_command(cmd: str):
    """Run a shell/subprocess command."""
    print(f"  [Action] Running command: {cmd}")
    subprocess.Popen(cmd, shell=True)
    time.sleep(config.DELAY_BETWEEN_ACTIONS)

def open_chrome():
    pyautogui.press("win")
    time.sleep(0.5)
    pyautogui.write("chrome")
    pyautogui.press("enter")
    speak("Opening Chrome")

def close_chrome():
    windows = gw.getWindowsWithTitle("Chrome")
    for w in windows:
        try:
            w.close()
        except:
            pass

def youtube_search(query):
    if not query:
        print("[WARN] Empty query")
        return
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    webbrowser.open(url)

def play_spotify(query: str):
    print(f"  [Action] Playing on Spotify: {query}")
    # Use URI scheme to instantly start search in the app
    subprocess.Popen(f'start spotify:search:"{query}"', shell=True)
    
    # Verification 1: Wait for Spotify to appear
    print("  [Action] Waiting for Spotify to load...")
    spotify_opened = False
    for i in range(10):
        time.sleep(0.5)
        wins = gw.getWindowsWithTitle("Spotify")
        if wins:
            spotify_opened = True
            try:
                wins[0].activate()
            except:
                pass
            break

    if not spotify_opened:
        print("  [Error] Failed to verify if Spotify opened. Is it installed?")
        return

    # Actually play the top result
    # We allow a moment for the search to load, then send tabs to focus the play button
    time.sleep(1.5)
    pyautogui.press("tab")
    time.sleep(0.1)
    pyautogui.press("tab")
    time.sleep(0.1)
    pyautogui.press("enter")
    
    # Verification 2: Check window title for playback change
    print("  [Action] Verifying playback...")
    time.sleep(1.0)
    wins = gw.getWindowsWithTitle("Spotify")
    if wins and len(wins) > 0:
        print(f"  [Action] Done. Current Spotify Window: '{wins[0].title}'")
    else:
        print("  [Warning] Could not see Spotify window to verify playing state.")

def open_url(url: str):
    print(f"[EXEC] open_url('{url}')")
    webbrowser.open(url)
    print(f"[OK] Opened URL: {url}")
    speak("Opening URL")

def google_search(query: str):
    print(f"[EXEC] google_search('{query}')")
    webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
    print(f"[OK] Opened google search for {query}")
    speak(f"Searching google for {query.replace('+', ' ')}")

def new_browser_tab():
    print("[EXEC] new_browser_tab()")
    pyautogui.hotkey("ctrl", "t")
    print("[OK] Opened new tab")

def close_browser_tab():
    print("[EXEC] close_browser_tab()")
    pyautogui.hotkey("ctrl", "w")
    print("[OK] Closed tab")

def take_screenshot():
    print("[EXEC] take_screenshot()")
    import datetime
    filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    pyautogui.screenshot(filename)
    print(f"[OK] Screenshot saved: {filename}")
    speak("Screenshot saved")

def volume_up():
    print("[EXEC] volume_up()")
    pyautogui.press("volumeup", presses=3)
    print("[OK] Volume up")

def volume_down():
    print("[EXEC] volume_down()")
    pyautogui.press("volumedown", presses=3)
    print("[OK] Volume down")

def mute_audio():
    print("[EXEC] mute_audio()")
    pyautogui.press("volumemute")
    print("[OK] Audio muted")

def click_text(target: str):
    """Find text on screen and click it."""
    print(f"[EXEC] click_text('{target}')")
    from vision.screen_reader import find_text_on_screen
    coords = find_text_on_screen(target)
    if coords:
        pyautogui.click(coords[0], coords[1])
        print(f"[OK] Clicked '{target}' at {coords}")
    else:
        print(f"[WARN] Text '{target}' not found on screen")

def type_text(text: str):
    """Type a string character by character with a small interval."""
    print(f'  [Action] Typing: "{text}"')
    pyautogui.typewrite(text, interval=0.05)
    time.sleep(config.DELAY_BETWEEN_ACTIONS)

def press_key(key: str):
    """Press a single keyboard key (e.g., enter, esc, tab)."""
    print(f"  [Action] Pressing key: {key}")
    pyautogui.press(key)
    time.sleep(config.DELAY_BETWEEN_ACTIONS)

def hotkey(*keys):
    """Press a keyboard shortcut (e.g., ctrl+t)."""
    print(f"  [Action] Hotkey: {'+'.join(keys)}")
    pyautogui.hotkey(*keys)
    time.sleep(config.DELAY_BETWEEN_ACTIONS)

def wait(seconds):
    """Pause execution for a given number of seconds."""
    secs = float(seconds)
    print(f"  [Action] Waiting {secs}s...")
    time.sleep(secs)

def click(x: int, y: int):
    """Click at the specified screen coordinates."""
    print(f"  [Action] Clicking at ({x}, {y})")
    pyautogui.click(x, y)
    time.sleep(config.DELAY_BETWEEN_ACTIONS)

def scroll(direction: str, amount: int = 3):
    """Scroll up or down."""
    print(f"  [Action] Scrolling {direction} by {amount}")
    if direction == "up":
        pyautogui.scroll(amount)
    else:
        pyautogui.scroll(-amount)
    time.sleep(config.DELAY_BETWEEN_ACTIONS)

def focus_window(title: str):
    """Bring a window to front by partial title match."""
    print(f"  [Action] Focusing window: {title}")
    wins = gw.getWindowsWithTitle(title)
    if wins:
        wins[0].activate()
        time.sleep(0.5)
    else:
        print(f"  [Warning] Window '{title}' not found.")

# ---------------------------------------------------------------------------
# Dispatcher – routes a single action dict to the right function
# ---------------------------------------------------------------------------

def _has_placeholder(value) -> bool:
    """Returns True if a value is an LLM placeholder like <X coordinate>."""
    if isinstance(value, str):
        return value.strip().startswith('<') and value.strip().endswith('>')
    return False

def execute_action(action: dict):
    """
    Takes one action dictionary (from the planner) and calls the
    corresponding function. Skips actions that contain placeholder values.
    """
    action_type = action.get("action", "")

    # ── Guard: skip any action whose values are LLM placeholders ──────────
    for key, val in action.items():
        if key != "action" and _has_placeholder(str(val)):
            print(f"  [Skip] Action '{action_type}' has placeholder value for '{key}': {val}")
            return

    try:
        if action_type == "open_start_menu":
            open_start_menu()

        elif action_type == "open_app":
            name = action.get("name", "")
            if name:
                open_app(name)
            else:
                print("  [Warning] 'open_app' missing 'name' field.")

        elif action_type == "run_command":
            cmd = action.get("cmd", "")
            if cmd:
                run_command(cmd)
            else:
                print("  [Warning] 'run_command' missing 'cmd' field.")

        elif action_type == "open_url":
            url = action.get("url", "")
            if url:
                open_url(url)
            else:
                print("  [Warning] 'open_url' missing 'url' field.")

        elif action_type == "type":
            text = action.get("text", "")
            if text:
                type_text(text)
            else:
                print("  [Warning] 'type' action missing 'text' field – skipped.")

        elif action_type == "press":
            key = action.get("key", "")
            if key:
                press_key(key)
            else:
                print("  [Warning] 'press' action missing 'key' field – skipped.")

        elif action_type == "hotkey":
            keys = action.get("keys", [])
            if keys:
                hotkey(*keys)
            else:
                print("  [Warning] 'hotkey' missing 'keys' field.")

        elif action_type == "wait":
            wait(action.get("seconds", 1))

        elif action_type == "click":
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                click(int(x), int(y))

            else:
                print("  [Warning] 'click' action missing coordinates – skipped.")

        elif action_type == "scroll":
            scroll(action.get("direction", "down"), action.get("amount", 3))

        elif action_type == "focus_window":
            focus_window(action.get("title", ""))

        elif action_type == "take_screenshot":
            take_screenshot()

        elif action_type == "trigger_n8n":
            from executor.n8n_bridge import trigger_n8n
            trigger_n8n(action.get("workflow", ""), action.get("payload", {}))

        elif action_type == "open_folder":
            from executor.files import open_folder
            open_folder(action.get("path", ""))

        elif action_type == "youtube_search":
            youtube_search(action.get("query", ""))

        else:
            print(f"  [Warning] Unknown action type: '{action_type}' – skipped.")

    except Exception as e:
        print(f"  [Error] Failed to execute '{action_type}': {e}")
