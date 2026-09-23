import pyautogui
from PIL import Image

def capture_screen() -> Image.Image:
    """Captures the primary screen and returns a PIL Image."""
    return pyautogui.screenshot()
