"""
skills/app_skill.py
Skill for launching Windows desktop applications and controlling Spotify.
"""
import os
import subprocess
import time
from typing import Dict, Any, Tuple
from skills.base import BaseSkill
from core.logger import get_logger

logger = get_logger("skills.app")

KNOWN_APPS = {
    "notepad": "notepad.exe",
    "notes": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "vscode": "code.cmd",
    "vs code": "code.cmd",
    "code": "code.cmd",
    "paint": "mspaint.exe",
    "task manager": "taskmgr.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "whiteboard": "Microsoft Whiteboard",
    "spotify": "spotify.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe"
}

def resolve_windows_app_path(app_target: str) -> str:
    """Resolves an executable target using system PATH and Windows Registry App Paths."""
    import shutil
    # 1. Check system PATH
    p = shutil.which(app_target)
    if p:
        return p

    # 2. Check Windows Registry App Paths
    try:
        import winreg
        exe_name = app_target if app_target.endswith(".exe") else f"{app_target}.exe"
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                sub_key = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
                with winreg.OpenKey(root, sub_key) as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass
    except Exception:
        pass

    return ""

class AppSkill(BaseSkill):
    name = "app_launcher"

    HANDLED_INTENTS = {
        "open_app",
        "play_spotify"
    }

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        if intent == "open_app":
            app_name = slots.get("app", "").strip()
            return self._launch_app(app_name)
        elif intent == "play_spotify":
            query = slots.get("query", "").strip()
            return self._play_spotify(query)
        return False, f"Unhandled intent: {intent}"

    def _launch_app(self, app_name: str) -> Tuple[bool, str]:
        if not app_name:
            return False, "No application name specified."

        norm_name = app_name.lower().strip()
        logger.info(f"Launching application: '{norm_name}'")

        # 1. Check known binary map
        if norm_name in KNOWN_APPS:
            target = KNOWN_APPS[norm_name]
            resolved = resolve_windows_app_path(target)
            if resolved:
                try:
                    subprocess.Popen([resolved])
                    return True, f"Opening {app_name}"
                except Exception as e:
                    logger.debug(f"Direct launch of {resolved} failed: {e}")
            else:
                try:
                    subprocess.Popen(target, shell=True)
                    return True, f"Opening {app_name}"
                except Exception as e:
                    logger.debug(f"Direct binary launch failed for {target}: {e}")

        # 2. Check app_index (scanned Start Menu / Desktop shortcuts)
        try:
            from agent.app_index import find_app
            shortcut_path = find_app(norm_name)
            if shortcut_path and os.path.exists(shortcut_path):
                if os.path.isdir(shortcut_path):
                    subprocess.Popen(['code', shortcut_path], shell=True)
                    return True, f"Opening project {app_name} in VS Code"
                else:
                    os.startfile(shortcut_path)
                    return True, f"Opening {app_name}"
        except Exception as e:
            logger.debug(f"App index lookup failed for {norm_name}: {e}")

        # 3. Direct os.startfile attempt
        try:
            os.startfile(norm_name)
            return True, f"Opening {app_name}"
        except Exception:
            pass

        # 4. Fallback to Start Menu typing (last resort)
        try:
            import pyautogui
            logger.info(f"Falling back to Start Menu search for '{app_name}'")
            pyautogui.press("win")
            time.sleep(0.4)
            pyautogui.write(app_name, interval=0.03)
            time.sleep(0.3)
            pyautogui.press("enter")
            return True, f"Searching and opening {app_name}"
        except Exception as e:
            logger.error(f"Start Menu launch failed for {app_name}: {e}")
            return False, f"Could not find or launch {app_name}"

    def _play_spotify(self, query: str) -> Tuple[bool, str]:
        logger.info(f"Playing query on Spotify: '{query}'")
        try:
            if query:
                subprocess.Popen(f'start spotify:search:"{query}"', shell=True)
            else:
                subprocess.Popen("start spotify:", shell=True)

            # Give a brief moment for Spotify to focus and trigger play
            time.sleep(1.2)
            try:
                import pygetwindow as gw
                import pyautogui
                wins = gw.getWindowsWithTitle("Spotify")
                if wins:
                    wins[0].activate()
                    time.sleep(0.3)
                    pyautogui.press("tab")
                    time.sleep(0.1)
                    pyautogui.press("tab")
                    time.sleep(0.1)
                    pyautogui.press("enter")
            except Exception as e:
                logger.debug(f"Spotify play keystroke simulation skipped: {e}")

            msg = f"Playing {query} on Spotify" if query else "Opening Spotify"
            return True, msg
        except Exception as e:
            logger.error(f"Spotify playback failed: {e}")
            return False, f"Failed to play Spotify: {e}"
