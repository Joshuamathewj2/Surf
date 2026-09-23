"""
executor/files.py
OS-level file operations without requiring pyautogui.
"""
import os
import subprocess
from agent.speaker import speak

def open_folder(path: str):
    print(f"[Run] open_folder('{path}')")
    if os.path.exists(path):
        os.startfile(path)
        speak("Opening folder")
    else:
        print(f"[Error] Folder not found: {path}")
        speak("Folder not found")

def create_file(path: str, content: str = ""):
    print(f"[Run] create_file('{path}')")
    try:
        with open(path, "w") as f:
            f.write(content)
        speak("File created")
    except Exception as e:
        print(f"[Error] Could not create file: {e}")

def search_file(directory: str, filename: str):
    print(f"[Run] search_file('{filename}' in '{directory}')")
    # basic recursive search
    for root, dirs, files in os.walk(directory):
        if filename in files:
            found = os.path.join(root, filename)
            print(f"[Found] {found}")
            speak("File found")
            return found
    print("[Not Found]")
    speak("File not found")
    return None
