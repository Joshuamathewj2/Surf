"""
interface/companion.py
Surf's robot companion: a little animated robot that lives on top of your taskbar, stays
above every app, and shows what Surf is doing. Think Siri's orb, but with a body.

    python -m interface.companion --demo     preview it without the assistant

Normally it is started by the assistant (interface/bus.py: launch_overlay) and talks to it
over the bus. Interactions:
    click            talk to Surf (same as saying "Hey Surf")
    double-click     type a command
    drag             pick it up and drop it somewhere else on the taskbar
    hover            it likes that
    right-click      menu: talk, type, wander on/off, mute, hide, quit

It hides itself while a fullscreen app (video, game, slideshow) is in front, unless Surf
is busy answering you.
"""
import ctypes
import json
import math
import os
import random
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap,
                         QRadialGradient, QTransform)
from PyQt5.QtWidgets import QAction, QApplication, QLineEdit, QMenu, QWidget

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config  # noqa: E402
from core.logger import get_logger  # noqa: E402
from interface.animator import Animator  # noqa: E402

logger = get_logger("companion")

ASSETS = ROOT / "interface" / "assets" / "robot"
SETTINGS_FILE = config.DATA_DIR / "companion.json"

WIN_W = 400
BUBBLE_H = 200  # room above the robot for the speech bubble
BUBBLE_MAX_W = 330
GROUND_PAD = 6  # px between the robot's feet and the bottom of the window
FADE_SEC = 0.16  # crossfade between animations

# Siri-ish aura colours per glow kind.
AURA = {
    "listen": [(0, 200, 255), (255, 64, 200), (140, 90, 255)],
    "think": [(170, 90, 255), (90, 140, 255), (255, 90, 200)],
    "speak": [(70, 220, 255), (140, 110, 255), (60, 255, 200)],
}
STATUS_TEXT = {"listening": "Listening", "thinking": "Thinking", "executing": "On it"}


# ---------------------------------------------------------------------------- Win32 helpers

_user32 = ctypes.windll.user32 if sys.platform == "win32" else None
HWND_TOPMOST = -1
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


def _keep_topmost(hwnd: int) -> None:
    if _user32:
        _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)


def _foreground_is_fullscreen(own_hwnd: int) -> bool:
    """True when the active window covers its whole monitor (a video, game or slideshow)."""
    if not _user32:
        return False
    hwnd = _user32.GetForegroundWindow()
    if not hwnd or hwnd == own_hwnd:
        return False
    cls = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return False  # the desktop itself
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
    _user32.GetMonitorInfoW(_user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))
    m = info.rcMonitor
    return rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom


def _foreground_window() -> int:
    return _user32.GetForegroundWindow() if _user32 else 0


def _force_foreground(hwnd: int) -> None:
    """Windows only lets the foreground app hand out focus. Borrow its input queue briefly so
    the command box really gets the keyboard (otherwise keystrokes go to the previous app)."""
    if not _user32:
        return
    fg = _user32.GetForegroundWindow()
    fg_thread = _user32.GetWindowThreadProcessId(fg, None)
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = fg_thread and fg_thread != me and _user32.AttachThreadInput(me, fg_thread, True)
    try:
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        _user32.SetFocus(hwnd)
    finally:
        if attached:
            _user32.AttachThreadInput(me, fg_thread, False)


def _restore_foreground(hwnd: int) -> None:
    if _user32 and hwnd:
        _user32.SetForegroundWindow(hwnd)


# ---------------------------------------------------------------------------- bus reader


class BusReader(QThread):
    message = pyqtSignal(dict)
    closed = pyqtSignal()

    def __init__(self, conn) -> None:
        super().__init__()
        self.conn = conn

    def run(self) -> None:
        while True:
            try:
                msg = self.conn.recv()
            except (EOFError, OSError):
                break
            if isinstance(msg, dict):
                self.message.emit(msg)
        self.closed.emit()


# ---------------------------------------------------------------------------- the window


class CommandBox(QWidget):
    """'Type to Surf': a small focusable popup above the robot."""

    submitted = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Ask Surf anything…")
        self.edit.setStyleSheet(
            "QLineEdit { background: rgba(22, 18, 40, 235); color: #f4f2ff; border: 1px solid rgba(160, 130, 255, 170);"
            " border-radius: 16px; padding: 7px 14px; font: 10.5pt 'Segoe UI'; selection-background-color: #7a5cff; }"
        )
        self.edit.returnPressed.connect(self._submit)
        self.resize(320, 40)
        self.edit.setGeometry(0, 2, 320, 36)
        self._previous = 0

    def open_at(self, center_x: int, bottom_y: int) -> None:
        self._previous = _foreground_window()
        self.move(center_x - self.width() // 2, bottom_y - self.height())
        self.edit.clear()
        self.show()
        self.raise_()
        _force_foreground(int(self.winId()))
        self.activateWindow()
        self.edit.setFocus()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close_box()
        else:
            super().keyPressEvent(e)

    def close_box(self) -> None:
        self.hide()
        _restore_foreground(self._previous)

    def _submit(self) -> None:
        text = self.edit.text().strip()
        self.close_box()  # give focus back first: "type hello" must type into *that* app
        if text:
            self.submitted.emit(text)


class Companion(QWidget):
    def __init__(self, conn=None, demo: bool = False) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.conn = conn
        self.demo = demo
        self.settings = self._load_settings()

        manifest = json.loads((ASSETS / "sprites.json").read_text(encoding="utf-8"))
        self.dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        self.robot_h = config.ROBOT_HEIGHT
        self.scale = self.robot_h / manifest["size"]["idle"][1]  # one scale for every frame
        self.frames: dict[str, list[QPixmap]] = {}
        loaded: dict[str, QPixmap] = {}  # many animations reuse the same pose files
        for name, files in manifest["frames"].items():
            pixmaps = []
            for f in files:
                if f not in loaded:
                    pm = QPixmap(str(ASSETS / f))
                    pm = pm.scaled(round(pm.width() * self.scale * self.dpr), round(pm.height() * self.scale * self.dpr),
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    pm.setDevicePixelRatio(self.dpr)
                    loaded[f] = pm
                pixmaps.append(loaded[f])
            self.frames[name] = pixmaps
        tallest = max(pm.height() / self.dpr for pms in self.frames.values() for pm in pms)
        self.win_h = int(BUBBLE_H + tallest + 24 + GROUND_PAD)
        self.resize(WIN_W, self.win_h)

        self.animator = Animator({k: len(v) for k, v in self.frames.items()}, roam=self.settings.get("roam", True))
        self.state = "idle"
        self.level = 0.0
        self.heard = ""
        self.reply = ""
        self.bubble_until = 0.0
        self.bubble_alpha = 0.0
        self.muted = self.settings.get("muted", False)
        self.speaking = False
        self.hidden_until = 0.0
        self.pose = None
        self._sprite_rect = QRectF()
        self._shown_anim = ""
        self._shown_pm: Optional[QPixmap] = None
        self._fade_from: Optional[QPixmap] = None
        self._fade_start = 0.0
        self._press_global = None
        self._press_offset = None
        self._dragged = False
        self._last_release = 0.0
        self._click_id = 0
        self._hover_since: Optional[float] = None
        self._last_pet = 0.0
        self._fullscreen_hidden = False
        self._last_tick = time.monotonic()

        self.box = CommandBox()
        self.box.submitted.connect(self._typed)

        self._place_on_screen()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self.housekeeping = QTimer(self)
        self.housekeeping.timeout.connect(self._housekeeping)
        self.housekeeping.start(1500)

        if conn is not None:
            self.reader = BusReader(conn)
            self.reader.message.connect(self._on_message)
            self.reader.closed.connect(QApplication.quit)
            self.reader.start()
            if self.muted:
                self._send({"cmd": "mute", "value": True})
        if demo:
            self._demo_step = 0
            self.demo_timer = QTimer(self)
            self.demo_timer.timeout.connect(self._demo_next)
            self.demo_timer.start(2600)
        self.animator.mood("hello", time.monotonic(), 2.0)

    # ------------------------------------------------------------------ geometry

    def _screen_rect(self):
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _place_on_screen(self) -> None:
        area = self._screen_rect()
        self.animator.set_bounds(area.left() + WIN_W / 2, area.right() - WIN_W / 2)
        frac = self.settings.get("x_frac", 0.92)
        self.animator.x = area.left() + WIN_W / 2 + frac * max(0, area.width() - WIN_W)
        self.animator.set_bounds(area.left() + WIN_W / 2, area.right() - WIN_W / 2)
        self._move_window()

    def _move_window(self) -> None:
        area = self._screen_rect()
        x = int(self.animator.x - WIN_W / 2)
        y = int(area.bottom() + 1 - self.win_h - self.animator.lift)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    # ------------------------------------------------------------------ settings

    def _load_settings(self) -> dict:
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_settings(self) -> None:
        area = self._screen_rect()
        span = max(1, area.width() - WIN_W)
        self.settings.update(
            x_frac=round((self.animator.x - area.left() - WIN_W / 2) / span, 4),
            roam=self.animator.roam,
            muted=self.muted,
        )
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.settings), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ talking to the assistant

    def _send(self, msg: dict) -> None:
        if self.conn is None:
            return
        try:
            self.conn.send(msg)
        except (OSError, EOFError) as e:
            logger.warning(f"Lost the assistant ({e}); closing the robot")
            QApplication.quit()

    def _on_message(self, msg: dict) -> None:
        now = time.monotonic()
        kind = msg.get("type")
        if kind == "state":
            self.state = msg.get("state", "idle")
            self.animator.on_state("speaking" if self.speaking and self.state == "idle" else self.state, now)
            if self.state == "listening":
                self.heard, self.reply = "", ""
                self._show_bubble(now, 30)
            elif self.state in ("thinking", "executing"):
                self._show_bubble(now, 30)
            elif self.state == "idle" and not self.reply:
                self.bubble_until = min(self.bubble_until, now + 1.0)
        elif kind == "heard":
            self.heard, self.reply = msg.get("text", ""), ""
            self._show_bubble(now, 30)
        elif kind == "say":
            self.reply = msg.get("text", "")
            self._show_bubble(now, min(16.0, 3.0 + 0.065 * len(self.reply)))
        elif kind == "mood":
            self.animator.mood(msg.get("mood", ""), now)
        elif kind == "speaking":
            self.speaking = bool(msg.get("value"))
            if self.state in ("idle", "executing"):
                self.animator.on_state("speaking" if self.speaking else self.state, now)
            if not self.speaking and self.reply:  # keep the answer up a moment after the voice stops
                self.bubble_until = max(self.bubble_until, now + 2.5)
        elif kind == "level":
            self.level = max(self.level, float(msg.get("value", 0.0)))
        elif kind == "show":  # the Surf shortcut was clicked while Surf was already running
            self.hidden_until = 0.0
            self.show()
            self.animator.mood("hello", now, 1.6)
        elif kind == "alert":  # timer / reminder: always show, even over fullscreen apps
            self.reply = msg.get("text", "")
            self.hidden_until = 0.0
            self.animator.mood("surprised", now, 3.0)
            self._show_bubble(now, 12.0)

    def _show_bubble(self, now: float, seconds: float) -> None:
        self.bubble_until = max(self.bubble_until, now + seconds) if self.state != "idle" else now + seconds

    def _typed(self, text: str) -> None:
        now = time.monotonic()
        self.heard, self.reply = text, ""
        self._show_bubble(now, 30)
        self.animator.activity(now)
        logger.info(f"Typed into the robot: {text!r}")
        self._send({"cmd": "text", "text": text})
        if self.demo:
            self._on_message({"type": "say", "text": f"(demo) You typed: {text}"})

    def _listen(self) -> None:
        self.animator.activity(time.monotonic())
        self._send({"cmd": "listen"})
        if self.demo:
            self._on_message({"type": "state", "state": "listening"})

    def _open_box(self) -> None:
        if self.box.isVisible():
            return
        g = self.mapToGlobal(self._sprite_rect.topLeft().toPoint())
        self.box.open_at(int(self.animator.x), g.y() - 8)

    # ------------------------------------------------------------------ animation loop

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._last_tick)
        self._last_tick = now
        self.pose = self.animator.tick(now, dt)
        self.level *= 0.88
        target = 1.0 if now < self.bubble_until and (self.heard or self.reply or self.state in STATUS_TEXT) else 0.0
        self.bubble_alpha += (target - self.bubble_alpha) * min(1.0, dt * 9)
        if (self._hover_since and now - self._hover_since > 1.4 and now - self._last_pet > 45
                and self.state == "idle" and not self._press_global):
            self._last_pet = now
            self.animator.mood("heart", now)
        self._move_window()
        self.update()

    def _housekeeping(self) -> None:
        now = time.monotonic()
        busy = self.state != "idle" or now < self.bubble_until
        want_hidden = now < self.hidden_until or (not busy and _foreground_is_fullscreen(int(self.winId())))
        if want_hidden and self.isVisible():
            self.hide()
        elif not want_hidden and not self.isVisible():
            self.show()
        if self.isVisible():
            _keep_topmost(int(self.winId()))

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event) -> None:
        if self.pose is None:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        pose = self.pose
        now = time.monotonic()
        pms = self.frames.get(pose.anim) or self.frames["idle"]
        pm = self._crossfaded(pose.anim, pms[min(pose.frame, len(pms) - 1)], now)
        w, h = pm.width() / self.dpr, pm.height() / self.dpr
        ground = self.win_h - GROUND_PAD
        cx = WIN_W / 2

        # Soft shadow on the taskbar; it shrinks as the robot is lifted.
        lift = pose.lift + pose.bob
        shadow_w = self.robot_h * 0.62 * max(0.35, 1 - lift / 260)
        grad = QRadialGradient(QPointF(cx, ground - 3), shadow_w / 2)
        grad.setColorAt(0, QColor(0, 0, 0, int(90 * max(0.3, 1 - lift / 200))))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QPointF(cx, ground - 3), shadow_w / 2, 7)

        # Siri-style aura behind the robot.
        if pose.glow:
            self._paint_aura(p, QPointF(cx, ground - self.robot_h * 0.55 - pose.bob), pose.glow, now)

        # The robot, rotated around its feet.
        p.save()
        p.translate(cx, ground - pose.bob)
        p.rotate(pose.angle)
        self._sprite_rect = QRectF(cx - w / 2, ground - pose.bob - h, w, h)
        p.drawPixmap(QRectF(-w / 2, -h, w, h), pm, QRectF(0, 0, pm.width(), pm.height()))
        p.restore()

        if pose.sleeping:
            self._paint_zzz(p, QPointF(cx + w * 0.3, self._sprite_rect.top() + h * 0.15), now)
        if self.bubble_alpha > 0.02:
            self._paint_bubble(p, cx, self._sprite_rect.top() + h * 0.08, now)
        p.end()

    def _crossfaded(self, anim: str, pm: QPixmap, now: float) -> QPixmap:
        """Blend from the last pose when the animation changes (standing -> walking -> sitting),
        so poses melt into each other instead of snapping. Frames within one animation don't fade."""
        if pm is not self._shown_pm:
            if anim != self._shown_anim and self._shown_pm is not None:
                self._fade_from, self._fade_start = self._shown_pm, now
            self._shown_anim, self._shown_pm = anim, pm
        t = (now - self._fade_start) / FADE_SEC
        if self._fade_from is None or t >= 1:
            self._fade_from = None
            return pm
        old = self._fade_from
        img = QImage(max(pm.width(), old.width()), max(pm.height(), old.height()), QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        q = QPainter(img)
        q.setRenderHint(QPainter.SmoothPixmapTransform)
        q.setCompositionMode(QPainter.CompositionMode_Plus)  # opacities t and 1-t add up to a solid robot
        for src, opacity in ((old, 1 - t), (pm, t)):
            q.setOpacity(opacity)
            # Explicit device-pixel rects: drawing a high-DPI pixmap by position alone would halve it.
            q.drawPixmap(QRectF((img.width() - src.width()) // 2, img.height() - src.height(), src.width(), src.height()),
                         src, QRectF(0, 0, src.width(), src.height()))
        q.end()
        out = QPixmap.fromImage(img)
        out.setDevicePixelRatio(self.dpr)
        return out

    def _paint_zzz(self, p: QPainter, origin: QPointF, now: float) -> None:
        font = QFont("Segoe UI", 1)
        for i in range(3):
            phase = (now * 0.45 + i / 3) % 1.0
            font.setPixelSize(int(9 + 7 * phase))
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor(170, 200, 255, int(230 * math.sin(math.pi * phase))))
            p.drawText(QPointF(origin.x() + 14 * phase + 3 * math.sin(now * 2 + i), origin.y() - 34 * phase), "z")

    def _paint_aura(self, p: QPainter, center: QPointF, kind: str, now: float) -> None:
        colors = AURA[kind]
        level = min(1.0, self.level * 6) if kind == "listen" else 0.25 + 0.15 * math.sin(now * 3)
        base = self.robot_h * (0.55 + 0.35 * level)
        speed = {"listen": 2.2, "think": 3.5, "speak": 1.6}[kind]
        p.setPen(Qt.NoPen)
        for i, (r, g, b) in enumerate(colors):
            a = now * speed + i * 2 * math.pi / 3
            off = QPointF(math.cos(a) * self.robot_h * 0.12, math.sin(a) * self.robot_h * 0.08)
            radius = base * (0.9 + 0.12 * math.sin(now * 2.7 + i))
            grad = QRadialGradient(center + off, radius)
            grad.setColorAt(0.0, QColor(r, g, b, 120))
            grad.setColorAt(0.45, QColor(r, g, b, 55))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setBrush(grad)
            p.drawEllipse(center + off, radius, radius)

    def _paint_bubble(self, p: QPainter, cx: float, robot_top: float, now: float) -> None:
        alpha = self.bubble_alpha
        status = ""
        if not self.reply and self.state in STATUS_TEXT:
            status = STATUS_TEXT[self.state] + "." * (1 + int(now * 2.5) % 3)
        heard = f"“{self.heard}”" if self.heard else ""
        body = self.reply or status
        if not heard and not body:
            return

        f_heard = QFont("Segoe UI", 9)
        f_heard.setItalic(True)
        f_body = QFont("Segoe UI Semibold" if not self.reply else "Segoe UI", 10)
        pad = 12
        inner = BUBBLE_MAX_W - 2 * pad
        flags = Qt.TextWordWrap | Qt.AlignLeft
        r_heard = QFontMetricsF(f_heard).boundingRect(QRectF(0, 0, inner, 1000), flags, heard) if heard else QRectF()
        r_body = QFontMetricsF(f_body).boundingRect(QRectF(0, 0, inner, 1000), flags, body) if body else QRectF()
        max_body_h = BUBBLE_H - 40 - r_heard.height()
        if r_body.height() > max_body_h:  # long answers: keep the last part visible
            r_body.setHeight(max_body_h)
        gap = 5 if heard and body else 0
        bw = min(BUBBLE_MAX_W, max(r_heard.width(), r_body.width()) + 2 * pad + 2)
        bh = r_heard.height() + r_body.height() + gap + 2 * pad - 2
        x = max(4.0, min(WIN_W - bw - 4.0, cx - bw / 2))
        y = robot_top - bh - 14
        rect = QRectF(x, y, bw, bh)

        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        tail = QPainterPath()
        tail.moveTo(cx - 9, rect.bottom() - 1)
        tail.lineTo(cx, rect.bottom() + 10)
        tail.lineTo(cx + 9, rect.bottom() - 1)
        path = path.united(tail)

        p.setOpacity(alpha)
        p.setBrush(QColor(20, 16, 36, 228))
        border = QColor(150, 120, 255, 200) if self.state != "listening" else QColor(0, 200, 255, 220)
        p.setPen(QPen(border, 1.3))
        p.drawPath(path)

        ty = rect.top() + pad - 1
        if heard:
            p.setFont(f_heard)
            p.setPen(QColor(190, 180, 225))
            p.drawText(QRectF(rect.left() + pad, ty, inner, r_heard.height()), flags, heard)
            ty += r_heard.height() + gap
        if body:
            p.setFont(f_body)
            p.setPen(QColor(246, 244, 255) if self.reply else QColor(120, 220, 255))
            p.drawText(QRectF(rect.left() + pad, ty, inner, r_body.height()), flags, body)
        p.setOpacity(1.0)

    # ------------------------------------------------------------------ mouse

    def _on_robot(self, pos) -> bool:
        return self._sprite_rect.adjusted(10, 6, -10, 0).contains(QPointF(pos))

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self._on_robot(e.pos()):
            self._press_global = e.globalPos()
            self._press_offset = e.globalPos().x() - self.animator.x
            self._dragged = False
        elif e.button() == Qt.LeftButton and self.bubble_alpha > 0.5:
            self.bubble_until = time.monotonic()  # click the bubble to dismiss it

    def mouseMoveEvent(self, e) -> None:
        on = self._on_robot(e.pos())
        self.setCursor(Qt.PointingHandCursor if on else Qt.ArrowCursor)
        if on and self._hover_since is None:
            self._hover_since = time.monotonic()
        elif not on:
            self._hover_since = None
        if self._press_global is None:
            return
        delta = e.globalPos() - self._press_global
        if not self._dragged and abs(delta.x()) + abs(delta.y()) > 6:
            self._dragged = True
            self.animator.start_drag(time.monotonic())
        if self._dragged:
            area = self._screen_rect()
            lift = area.bottom() + 1 - e.globalPos().y() - self.robot_h * 0.75 - GROUND_PAD
            self.animator.drag_to(e.globalPos().x() - self._press_offset, lift)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._press_global is None:
            return
        self._press_global = None
        if self._dragged:
            self.animator.end_drag(time.monotonic())
            self._save_settings()
        else:
            # Tell clicks from double-clicks ourselves: Qt's double-click event isn't reliable on
            # a window that never takes focus. A click only counts once no second one followed.
            now = time.monotonic()
            if now - self._last_release < QApplication.doubleClickInterval() / 1000:
                self._last_release = 0.0
                self._click_id += 1  # cancels the pending single click
                self._open_box()
                return
            self._last_release = now
            self._click_id += 1
            click = self._click_id
            QTimer.singleShot(QApplication.doubleClickInterval(), lambda: self._maybe_click(click))

    def _maybe_click(self, click: int) -> None:
        if click == self._click_id:
            self._listen()

    def mouseDoubleClickEvent(self, e) -> None:
        # Qt sends this instead of the second press; treat it as that press.
        self.mousePressEvent(e)

    def leaveEvent(self, _e) -> None:
        self._hover_since = None

    def contextMenuEvent(self, e) -> None:
        if not self._on_robot(e.pos()):
            return
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #1a1530; color: #eeeaff; border: 1px solid #5d4ab0; border-radius: 8px; padding: 6px;"
            " font: 10pt 'Segoe UI'; } QMenu::item { padding: 6px 22px 6px 14px; border-radius: 5px; }"
            " QMenu::item:selected { background: #3d2f80; } QMenu::separator { height: 1px; background: #3a3260;"
            " margin: 5px 8px; } QMenu::indicator { width: 12px; height: 12px; }"
        )
        talk = menu.addAction("Talk to Surf")
        type_ = menu.addAction("Type a command…")
        menu.addSeparator()
        roam = QAction("Let it wander", menu, checkable=True, checked=self.animator.roam)
        mute = QAction("Mute voice", menu, checkable=True, checked=self.muted)
        menu.addAction(roam)
        menu.addAction(mute)
        hide = menu.addAction("Hide for 10 minutes")
        menu.addSeparator()
        quit_ = menu.addAction("Quit Surf")
        chosen = menu.exec_(e.globalPos())
        now = time.monotonic()
        if chosen is talk:
            self._listen()
        elif chosen is type_:
            self._open_box()
        elif chosen is roam:
            self.animator.roam = roam.isChecked()
            self._save_settings()
        elif chosen is mute:
            self.muted = mute.isChecked()
            self._send({"cmd": "mute", "value": self.muted})
            self.animator.mood("wink" if not self.muted else "sad", now, 1.2)
            self._save_settings()
        elif chosen is hide:
            self.hidden_until = now + 600
            self.hide()
        elif chosen is quit_:
            self.animator.mood("bye", now)
            self._send({"cmd": "quit"})
            QTimer.singleShot(1200, QApplication.quit)

    # ------------------------------------------------------------------ demo

    def _demo_next(self) -> None:
        script = [
            {"type": "state", "state": "listening"},
            {"type": "level", "value": 0.12},
            {"type": "heard", "text": "what's the weather like today?"},
            {"type": "state", "state": "thinking"},
            {"type": "mood", "mood": "lightbulb"},
            {"type": "say", "text": "It's 29 degrees and sunny in Chennai, with a light breeze. No rain expected."},
            {"type": "state", "state": "idle"},
            {"type": "heard", "text": "play some lofi on youtube"},
            {"type": "mood", "mood": "dance"},
            {"type": "say", "text": "Playing lofi on YouTube"},
            {"type": "mood", "mood": "confused"},
            {"type": "mood", "mood": "heart"},
            {"type": "state", "state": "idle"},
        ]
        msg = script[self._demo_step % len(script)]
        self._demo_step += 1
        self._on_message(msg)


def main() -> None:
    try:  # sharp sprites on high-DPI screens
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except AttributeError:
        pass
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    demo = "--demo" in sys.argv
    conn = None
    if not demo:
        from interface.bus import ENV_PORT, connect_from_env

        if ENV_PORT not in os.environ:
            print("Run Surf (python main.py) to start the companion, or use --demo to preview it.")
            sys.exit(1)
        conn = connect_from_env()
    w = Companion(conn, demo=demo)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    random.seed()
    main()
