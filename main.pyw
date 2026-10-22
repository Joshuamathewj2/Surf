"""
main.pyw
Background mode: no console window, a tray icon, and always listening for "Hey Jarvis".
Start it with pythonw.exe (double-click) or add a shortcut to shell:startup.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from agent.pipeline import handle_command  # noqa: E402
from core.logger import get_logger  # noqa: E402
from llm.planner import warm_up  # noqa: E402
from tray.icon import start_tray_thread  # noqa: E402
from voice.assistant import run_wake_loop  # noqa: E402

logger = get_logger("daemon")

if __name__ == "__main__":
    logger.info("Surf background mode starting")
    try:
        start_tray_thread()
    except Exception as e:
        logger.warning(f"Tray icon unavailable: {e}")
    warm_up()
    try:
        run_wake_loop(handle_command)
    except Exception as e:
        logger.error(f"Wake loop stopped: {e}", exc_info=True)
    os._exit(0)
