"""
tray/icon.py
System tray icon for Surf.
"""
import pystray
from PIL import Image, ImageDraw
import os
import threading

def create_image():
    image = Image.new('RGB', (64, 64), color=(20, 20, 20))
    d = ImageDraw.Draw(image)
    d.text((12, 25), "SURF", fill=(100, 200, 255))
    return image

icon = None

def run_tray():
    global icon
    
    def on_quit(icon, item):
        icon.stop()
        os._exit(0)
        
    menu = pystray.Menu(
        pystray.MenuItem('Surf AI (Daemon)', lambda: None, enabled=False),
        pystray.MenuItem('Quit', on_quit)
    )
    
    icon = pystray.Icon("surf_ai", create_image(), "Surf AI", menu)
    icon.run()

def start_tray_thread():
    t = threading.Thread(target=run_tray, daemon=True)
    t.start()
