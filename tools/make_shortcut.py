"""
tools/make_shortcut.py
Put a Surf icon on the Desktop and in the Start Menu, so Surf starts without a terminal.

    .venv\\Scripts\\python tools\\make_shortcut.py

The shortcuts run main.pyw with the venv's pythonw.exe (no console window). Clicking one
while Surf is already running brings the robot back on screen. To get a taskbar button,
right-click Surf in the Start Menu and choose "Pin to taskbar" (Windows doesn't let apps
pin themselves).
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "interface" / "assets" / "surf.ico"
ROBOT_FRAME = ROOT / "interface" / "assets" / "robot" / "idle_0.png"


def make_icon() -> Path:
    img = Image.open(ROBOT_FRAME).convert("RGBA")
    head = img.crop((0, 0, img.width, int(img.height * 0.62)))  # helmet and face, like the tray icon
    head = head.crop(head.getbbox())
    side = max(head.size)
    square = Image.new("RGBA", (side, side))
    square.paste(head, ((side - head.width) // 2, (side - head.height) // 2), head)
    square.save(ICON, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    return ICON


def make_shortcuts() -> list[str]:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        raise SystemExit(f"pythonw.exe not found next to {sys.executable}; run this with the venv's python")
    script = f"""
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {{
    $path = Join-Path $dir 'Surf.lnk'
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = '{pythonw}'
    $lnk.Arguments = '"{ROOT / "main.pyw"}"'
    $lnk.WorkingDirectory = '{ROOT}'
    $lnk.IconLocation = '{ICON},0'
    $lnk.Description = 'Surf: your voice assistant (Hey Surf)'
    $lnk.Save()
    $path
}}
"""
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


if __name__ == "__main__":
    print(f"icon: {make_icon()}")
    for path in make_shortcuts():
        print(f"shortcut: {path}")
