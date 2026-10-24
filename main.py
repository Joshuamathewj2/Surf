"""
main.py
Surf entry point.

    python main.py              interactive menu
    python main.py --voice      hands-free: say "Hey Surf" + a command, or click the robot
    python main.py --text       type commands
    python main.py --no-robot   without the robot companion on the taskbar
"""
import argparse
import os
import sys

# Never let the Windows console crash on Unicode output.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Surf: local assistant for Windows")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--voice", action="store_true", help='hands-free mode ("Hey Surf")')
    group.add_argument("--text", action="store_true", help="type commands")
    parser.add_argument("--no-robot", action="store_true", help="don't show the robot companion")
    parser.add_argument("--hud", action="store_true", help=argparse.SUPPRESS)  # old flag: the robot is on by default
    args = parser.parse_args()

    from core import config

    if config.ROBOT and not args.no_robot and os.getenv("SURF_HUD") != "0":
        from interface.bus import launch_overlay

        launch_overlay()  # its own process: Qt and faster-whisper must not share one

    from agent.loop import BANNER, run, run_text, run_voice

    if args.voice:
        print(BANNER)
        run_voice()
    elif args.text:
        print(BANNER)
        run_text()
    else:
        run()


if __name__ == "__main__":
    main()
