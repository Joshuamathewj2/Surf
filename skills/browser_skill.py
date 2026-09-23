"""
skills/browser_skill.py
Skill for handling web browser automation: Chrome, YouTube, search, tabs.
"""
import subprocess
import webbrowser
import urllib.parse
import os
from typing import Dict, Any, Tuple
from skills.base import BaseSkill
from core.logger import get_logger

logger = get_logger("skills.browser")

def find_chrome_path() -> str:
    """Finds the actual full path to chrome.exe via Registry or standard locations."""
    # 1. Check Windows Registry App Paths
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass
    except Exception:
        pass

    # 2. Check standard directory locations
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    # 3. Check system PATH
    import shutil
    p = shutil.which("chrome") or shutil.which("chrome.exe")
    if p:
        return p

    return ""

class BrowserSkill(BaseSkill):
    name = "browser"

    HANDLED_INTENTS = {
        "open_chrome",
        "close_chrome",
        "youtube_search",
        "google_search",
        "open_url",
        "new_tab",
        "close_tab",
        "open_youtube"
    }

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        
        try:
            if intent == "open_chrome":
                return self._open_chrome()
            elif intent == "close_chrome":
                return self._close_chrome()
            elif intent in ("youtube_search", "open_youtube"):
                query = slots.get("query", "").strip()
                return self._youtube_search(query)
            elif intent == "google_search":
                query = slots.get("query", "").strip()
                return self._google_search(query)
            elif intent == "open_url":
                url = slots.get("url", "").strip()
                return self._open_url(url)
            elif intent == "new_tab":
                return self._new_tab()
            elif intent == "close_tab":
                return self._close_tab()
            else:
                return False, f"Unknown browser action: {intent}"
        except Exception as e:
            logger.error(f"Browser action failed: {e}", exc_info=True)
            return False, f"Failed browser action: {e}"

    def _open_chrome(self) -> Tuple[bool, str]:
        logger.info("Opening Google Chrome...")
        chrome_bin = find_chrome_path()
        if chrome_bin:
            try:
                subprocess.Popen([chrome_bin])
                return True, "Opening Chrome"
            except Exception as e:
                logger.debug(f"Direct launch of {chrome_bin} failed: {e}")

        # Fallback to default web browser
        webbrowser.open("https://google.com")
        return True, "Opening browser"

    def _close_chrome(self) -> Tuple[bool, str]:
        logger.info("Closing Google Chrome...")
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle("Chrome")
            if windows:
                for w in windows:
                    try:
                        w.close()
                    except Exception:
                        pass
                return True, "Closed Chrome windows"
        except Exception as e:
            logger.debug(f"pygetwindow close failed: {e}")

        # Fallback to graceful taskkill if pygetwindow fails
        try:
            subprocess.run(["taskkill", "/IM", "chrome.exe"], capture_output=True, timeout=3)
            return True, "Closed Chrome"
        except Exception as e:
            return False, f"Could not close Chrome: {e}"

    def _youtube_search(self, query: str) -> Tuple[bool, str]:
        if not query:
            logger.info("Opening YouTube homepage...")
            webbrowser.open("https://www.youtube.com")
            return True, "Opening YouTube"

        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        logger.info(f"Opening YouTube search for: '{query}'")
        webbrowser.open(url)
        return True, f"Searching YouTube for {query}"

    def _google_search(self, query: str) -> Tuple[bool, str]:
        if not query:
            webbrowser.open("https://www.google.com")
            return True, "Opening Google"

        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}"
        logger.info(f"Searching Google for: '{query}'")
        webbrowser.open(url)
        return True, f"Searching Google for {query}"

    def _open_url(self, url: str) -> Tuple[bool, str]:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        logger.info(f"Opening URL: {url}")
        webbrowser.open(url)
        return True, f"Opening {url}"

    def _new_tab(self) -> Tuple[bool, str]:
        import pyautogui
        logger.info("Opening new browser tab...")
        pyautogui.hotkey("ctrl", "t")
        return True, "Opened new tab"

    def _close_tab(self) -> Tuple[bool, str]:
        import pyautogui
        logger.info("Closing active browser tab...")
        pyautogui.hotkey("ctrl", "w")
        return True, "Closed tab"
