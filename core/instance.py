"""
core/instance.py
One Surf at a time. The first launch owns a named mutex; a second launch (e.g. clicking the
desktop shortcut again) signals it to bring the robot back on screen, then exits.
"""
import ctypes
import threading
from typing import Callable

MUTEX_NAME = "Local\\SurfAssistant"
SHOW_EVENT_NAME = "Local\\SurfAssistantShow"
ERROR_ALREADY_EXISTS = 183
INFINITE = 0xFFFFFFFF
EVENT_MODIFY_STATE = 0x0002

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CreateEventW.restype = ctypes.c_void_p
_kernel32.OpenEventW.restype = ctypes.c_void_p
_handles = []  # keep the mutex and event open for the life of the process


def claim() -> bool:
    """True if this is the only Surf running. Otherwise asks the running one to show itself."""
    mutex = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if mutex and ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
        _handles.append(mutex)
        return True
    event = _kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
    if event:
        _kernel32.SetEvent(ctypes.c_void_p(event))
        _kernel32.CloseHandle(ctypes.c_void_p(event))
    return False


def on_show_request(callback: Callable[[], None]) -> None:
    """Run callback (on a background thread) whenever another launch asks us to show up."""
    event = _kernel32.CreateEventW(None, False, False, SHOW_EVENT_NAME)  # auto-reset
    _handles.append(event)

    def wait() -> None:
        while _kernel32.WaitForSingleObject(ctypes.c_void_p(event), INFINITE) == 0:
            callback()

    threading.Thread(target=wait, daemon=True, name="ShowRequests").start()
