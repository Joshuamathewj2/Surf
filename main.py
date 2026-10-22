"""
main.py
Surf entry point.

    python main.py            interactive menu
    python main.py --voice    hands-free: say "Hey Jarvis" + a command
    python main.py --text     type commands
    python main.py --hud      also show the ArcReactor HUD (combine with either mode)
"""
import argparse
import os
import subprocess
import sys

# Never let the Windows console crash on Unicode output.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def launch_hud_process() -> None:
    """Run the PyQt5 HUD in its own process (Qt and faster-whisper must not share one)."""
    try:
        hud_script = os.path.join(os.path.dirname(__file__), "interface", "hud.py")
        subprocess.Popen([sys.executable, hud_script])
    except Exception as e:
        print(f"[Warning] Could not start HUD: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Surf: local voice assistant for Windows")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--voice", action="store_true", help='hands-free mode ("Hey Jarvis")')
    group.add_argument("--text", action="store_true", help="type commands")
    parser.add_argument("--hud", action="store_true", help="show the HUD overlay")
    args = parser.parse_args()

    if args.hud or os.getenv("SURF_HUD") == "1":
        launch_hud_process()

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
