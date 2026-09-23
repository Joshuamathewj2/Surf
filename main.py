import threading
import os
from agent.loop import run

# Enable High DPI scaling for PyQt5
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

# Attempt basic import to fail gracefully if PyQt5 is missing
try:
    from interface.hud import start_hud
except ImportError:
    print("Warning: PyQt5 not installed. HUD disabled.")
    start_hud = None

if __name__ == "__main__":
    if start_hud:
        # Start agent loop in a separate daemon thread
        agent_thread = threading.Thread(target=run, daemon=True)
        agent_thread.start()
        
        # Start HUD in the main thread (blocks until sys.exit)
        start_hud()
    else:
        # Fallback if no GUI
        run()
