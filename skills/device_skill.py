"""
skills/device_skill.py
Siri-style device control: media playback, exact volume, battery, brightness, lock screen,
dark mode, Settings pages and common folders. No extra dependencies: media and volume use
virtual key presses, the rest plain Win32 calls.
"""
import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.device")

VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAE, 0xAF
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB3
KEYEVENTF_KEYUP = 0x2

SETTINGS_PAGES = {
    "bluetooth": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi",
    "wi-fi": "ms-settings:network-wifi",
    "network": "ms-settings:network",
    "internet": "ms-settings:network",
    "display": "ms-settings:display",
    "screen": "ms-settings:display",
    "sound": "ms-settings:sound",
    "audio": "ms-settings:sound",
    "battery": "ms-settings:batterysaver",
    "power": "ms-settings:powersleep",
    "update": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
    "notifications": "ms-settings:notifications",
    "apps": "ms-settings:appsfeatures",
    "privacy": "ms-settings:privacy",
    "personalization": "ms-settings:personalization",
    "background": "ms-settings:personalization-background",
    "wallpaper": "ms-settings:personalization-background",
    "mouse": "ms-settings:mousetouchpad",
    "keyboard": "ms-settings:typing",
    "storage": "ms-settings:storagesense",
    "time": "ms-settings:dateandtime",
    "date": "ms-settings:dateandtime",
    "language": "ms-settings:regionlanguage",
    "accounts": "ms-settings:yourinfo",
    "printers": "ms-settings:printers",
    "focus": "ms-settings:quiethours",
    "night light": "ms-settings:nightlight",
    "": "ms-settings:",
}
FOLDERS = ("downloads", "documents", "desktop", "pictures", "music", "videos")


def _tap(vk: int, times: int = 1) -> None:
    keybd = ctypes.windll.user32.keybd_event
    for _ in range(times):
        keybd(vk, 0, 0, 0)
        keybd(vk, 0, KEYEVENTF_KEYUP, 0)


def battery_status() -> Tuple[int, bool, int]:
    """(percent, plugged in, seconds left or -1). Percent is 255 when there is no battery."""

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    status = SYSTEM_POWER_STATUS()
    ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    seconds = status.BatteryLifeTime if status.BatteryLifeTime != 0xFFFFFFFF else -1
    return status.BatteryLifePercent, status.ACLineStatus == 1, seconds


def _powershell(script: str) -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return out.stdout.strip()


def get_brightness() -> int | None:
    out = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
    return int(out.splitlines()[0]) if out and out.splitlines()[0].isdigit() else None


def set_brightness(level: int) -> None:
    level = max(0, min(100, int(level)))  # an int: nothing user-controlled reaches the script
    _powershell(
        "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
        f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={level}}}"
    )


def set_dark_mode(dark: bool) -> None:
    import winreg

    key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 0 if dark else 1)


class DeviceSkill(BaseSkill):
    name = "device"

    HANDLED_INTENTS = {
        "media_play_pause", "media_next", "media_previous", "set_volume", "battery", "lock_screen",
        "brightness", "open_settings", "open_folder", "dark_mode",
    }

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        if sys.platform != "win32":
            return False, "That only works on Windows."
        try:
            return getattr(self, "_" + intent)(slots)
        except Exception as e:
            logger.error(f"{intent} failed: {e}", exc_info=True)
            return False, "That didn't work"

    def _media_play_pause(self, slots) -> Tuple[bool, str]:
        _tap(VK_MEDIA_PLAY_PAUSE)
        return True, ""

    def _media_next(self, slots) -> Tuple[bool, str]:
        _tap(VK_MEDIA_NEXT)
        return True, "Next track"

    def _media_previous(self, slots) -> Tuple[bool, str]:
        _tap(VK_MEDIA_PREV)
        return True, "Previous track"

    def _set_volume(self, slots) -> Tuple[bool, str]:
        level = max(0, min(100, int(slots.get("level", 50))))
        _tap(VK_VOLUME_DOWN, 50)  # each key step is 2%: go to zero, then count up
        _tap(VK_VOLUME_UP, round(level / 2))
        return True, f"Volume set to {level} percent"

    def _battery(self, slots) -> Tuple[bool, str]:
        percent, plugged, seconds = battery_status()
        if percent == 255:
            return True, "This PC doesn't have a battery."
        text = f"Your battery is at {percent} percent"
        if plugged:
            text += " and charging" if percent < 100 else " and plugged in"
        elif seconds > 0:
            h, m = divmod(seconds // 60, 60)
            text += f", about {h} hours and {m} minutes left" if h else f", about {m} minutes left"
        return True, text + "."

    def _lock_screen(self, slots) -> Tuple[bool, str]:
        ctypes.windll.user32.LockWorkStation()
        return True, ""

    def _brightness(self, slots) -> Tuple[bool, str]:
        level, step = slots.get("level"), slots.get("step", 0)
        if level is None:
            current = get_brightness()
            if current is None:
                return False, "I can't change the brightness of this screen."
            level = current + step
        level = max(5, min(100, int(level)))
        set_brightness(level)
        return True, f"Brightness {level} percent"

    def _open_settings(self, slots) -> Tuple[bool, str]:
        page = slots.get("page", "")
        uri = SETTINGS_PAGES.get(page)
        if uri is None:
            return False, f"I don't know the {page} settings page."
        os.startfile(uri)
        return True, f"Opening {page} settings" if page else "Opening Settings"

    def _open_folder(self, slots) -> Tuple[bool, str]:
        name = slots.get("folder", "")
        path = Path.home() / name.capitalize()
        if not path.exists():
            onedrive = Path.home() / "OneDrive" / name.capitalize()
            path = onedrive if onedrive.exists() else path
        if not path.exists():
            return False, f"I couldn't find your {name} folder."
        os.startfile(str(path))
        return True, f"Opening {name}"

    def _dark_mode(self, slots) -> Tuple[bool, str]:
        dark = bool(slots.get("on", True))
        set_dark_mode(dark)
        return True, "Dark mode on" if dark else "Light mode on"
