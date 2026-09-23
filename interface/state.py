"""
interface/state.py
Lightweight HUD state bridge using a shared temp file.
Zero Qt dependencies: completely eliminates DLL/OpenMP collisions with faster-whisper.
"""
import os
import json
import tempfile

STATE_FILE = os.path.join(tempfile.gettempdir(), "surf_hud_state.json")

def set_state(state: str, text: str = ""):
    """Updates HUD state without importing PyQt5 in the agent process."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"state": state, "text": text}, f)
    except Exception:
        pass

def get_state() -> dict:
    """Reads current HUD state."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"state": "idle", "text": "IDLE"}
