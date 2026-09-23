"""
main.py
Primary interactive entry point for Surf Desktop Agent.
Runs the agent loop directly on the main thread for rock-solid stability.
Optionally launches the ArcReactor HUD with --hud.
"""
import sys
import os
import subprocess

# Ensure Windows console never crashes on Unicode characters
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def launch_hud_process():
    """Launches the PyQt5 ArcReactor HUD in an isolated process."""
    try:
        hud_script = os.path.join(os.path.dirname(__file__), "interface", "hud.py")
        subprocess.Popen([sys.executable, hud_script])
    except Exception as e:
        print(f"[Warning] Could not start HUD: {e}")

if __name__ == "__main__":
    # Check if HUD was explicitly requested via CLI flag or env var
    if "--hud" in sys.argv or os.getenv("SURF_HUD", "0") == "1":
        launch_hud_process()

    from agent.loop import run
    run()
