"""
core/desktop.py
Reliable keyboard/window primitives shared by skills and the executor.
"""
import time

from core import config
from core.logger import get_logger

logger = get_logger("desktop")


def wait_for_window(title_part: str, timeout: float = config.WINDOW_WAIT_SEC):
    """Wait until a window whose title contains `title_part` exists, then focus it.
    Returns the window, or None if it never appeared."""
    import pygetwindow as gw

    deadline = time.time() + timeout
    while time.time() < deadline:
        wins = [w for w in gw.getWindowsWithTitle(title_part) if w.title]
        if wins:
            win = wins[0]
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
            except Exception:
                # activate() can raise even when focus was granted; verify below
                pass
            time.sleep(0.25)
            return win
        time.sleep(0.15)
    logger.warning(f"Window containing '{title_part}' did not appear within {timeout:.0f}s")
    return None


def _set_clipboard(text: str) -> str | None:
    """Put text on the clipboard; return the previous text so it can be restored."""
    import win32clipboard
    import win32con

    previous = None
    win32clipboard.OpenClipboard()
    try:
        try:
            previous = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except (TypeError, win32clipboard.error):
            previous = None
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()
    return previous


def type_text(text: str) -> None:
    """Type any Unicode text into the focused window.

    pyautogui.typewrite() silently drops non-ASCII characters (₹, é, emoji, Tamil...),
    so text is pasted through the clipboard and the user's clipboard is restored after.
    """
    import pyautogui

    if not text:
        return
    try:
        previous = _set_clipboard(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
        if previous is not None:
            _set_clipboard(previous)
    except ImportError:
        pyautogui.typewrite(text, interval=0.02)
