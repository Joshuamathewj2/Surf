"""
main.pyw
Background mode: no console window, the robot companion on the taskbar, a tray icon, and
always listening for "Hey Surf". Start it with pythonw.exe (double-click), or the Desktop /
Start Menu shortcut from tools/make_shortcut.py. Launching it again while it runs just brings
the robot back on screen.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from core import instance  # noqa: E402

if not instance.claim():  # already running: it has been asked to show the robot
    sys.exit(0)

from agent.pipeline import handle_command, start_background_services  # noqa: E402
from core import config  # noqa: E402
from core.logger import get_logger  # noqa: E402
from interface.bus import emit, launch_overlay  # noqa: E402
from llm.planner import warm_up  # noqa: E402
from tray.icon import start_tray_thread  # noqa: E402
from voice.assistant import run_wake_loop  # noqa: E402

logger = get_logger("daemon")


def show_robot() -> None:
    logger.info("Launched again: bringing the robot back")
    launch_overlay()  # restarts it if it was closed
    emit("show")  # un-hides it if it was hidden


if __name__ == "__main__":
    logger.info("Surf background mode starting")
    instance.on_show_request(show_robot)
    if config.ROBOT:
        launch_overlay()
    try:
        start_tray_thread()
    except Exception as e:
        logger.warning(f"Tray icon unavailable: {e}")
    warm_up()
    start_background_services()
    try:
        run_wake_loop(handle_command)
    except Exception as e:
        logger.error(f"Wake loop stopped: {e}", exc_info=True)
    os._exit(0)
