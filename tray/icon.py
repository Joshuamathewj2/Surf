"""
tray/icon.py
System tray icon for Surf: the robot's face, plus a menu to bring the robot back or quit.
"""
import os
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

ROBOT_FRAME = Path(__file__).resolve().parent.parent / "interface" / "assets" / "robot" / "idle_0.png"


def create_image() -> Image.Image:
    try:
        img = Image.open(ROBOT_FRAME).convert("RGBA")
        head = img.crop((0, 0, img.width, int(img.height * 0.62)))  # just the helmet and face
        side = max(head.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(head, ((side - head.width) // 2, (side - head.height) // 2), head)
        return square.resize((64, 64), Image.LANCZOS)
    except OSError:
        image = Image.new("RGB", (64, 64), color=(20, 20, 20))
        ImageDraw.Draw(image).text((12, 25), "SURF", fill=(100, 200, 255))
        return image


icon = None


def run_tray():
    global icon

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    def on_show_robot(icon, item):
        from interface.bus import launch_overlay

        launch_overlay()

    menu = pystray.Menu(
        pystray.MenuItem("Surf (listening for \"Hey Surf\")", lambda: None, enabled=False),
        pystray.MenuItem("Show robot", on_show_robot),
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon("surf_ai", create_image(), "Surf", menu)
    icon.run()


def start_tray_thread():
    t = threading.Thread(target=run_tray, daemon=True)
    t.start()
