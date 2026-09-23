import sys
import math
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QBrush, QFont, QPen, QRadialGradient

from interface.state import get_state, set_state

class HUDController(QObject):
    state_changed = pyqtSignal(str, str)

# Global controller instance
_controller = None

class ArcReactorHUD(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        if self.controller is not None:
            self.controller.state_changed.connect(self.update_state)

        # State poll timer
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self._poll_shared_state)
        self.state_timer.start(60)

    def _poll_shared_state(self):
        st = get_state()
        state = st.get("state", "idle")
        text = st.get("text", "")
        if state != self.current_state or (text and text != self.display_text):
            self.update_state(state, text)

        # State definitions: color is stored as tuple (r, g, b) to avoid mutation bugs
        self.states = {
            "listening": {
                "color": (0, 200, 255),     # Neon Blue
                "label": "LISTENING",
                "speed": 4,
                "intensity": 1.0
            },
            "thinking": {
                "color": (200, 50, 255),    # Purple
                "label": "THINKING",
                "speed": 8,
                "intensity": 1.2
            },
            "executing": {
                "color": (50, 255, 150),    # Green
                "label": "EXECUTING",
                "speed": 12,
                "intensity": 1.5
            },
            "error": {
                "color": (255, 50, 50),     # Red
                "label": "ERROR",
                "speed": 20,
                "intensity": 2.0
            },
            "idle": {
                "color": (0, 100, 200),     # Dim Blue
                "label": "IDLE",
                "speed": 1,
                "intensity": 0.5
            }
        }

        self.current_state = "idle"
        self.display_text = "IDLE"

        # Animation variables
        self.rotation_angle = 0.0
        self.pulse_phase = 0.0
        self.glow_factor = 0.0

        self.initUI()

        # Animation timer (30ms ~ 33 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(30)

    def initUI(self):
        # Window Setup: frameless, always-on-top, transparent
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Fixed 200x220 window (extra height for label below reactor)
        self.setFixedSize(200, 220)

        # Position: CENTER BOTTOM of screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 20  # 20px margin from bottom
        self.move(x, y)

    def update_state(self, state, text):
        if state in self.states:
            self.current_state = state
            self.display_text = text if text else self.states[state]["label"]
        self.update()

    def _get_color(self, alpha=255) -> QColor:
        """Always creates a fresh QColor from the tuple to avoid mutation."""
        r, g, b = self.states[self.current_state]["color"]
        return QColor(r, g, b, alpha)

    def animate(self):
        try:
            state_config = self.states[self.current_state]

            # Update rotation angle
            self.rotation_angle = (self.rotation_angle + state_config["speed"]) % 360

            # Update pulse via sin wave (0.0 to 1.0)
            self.pulse_phase += 0.1 * state_config["intensity"]
            self.glow_factor = (math.sin(self.pulse_phase) + 1) / 2

            self.update()
        except Exception:
            pass  # Silently ignore errors during shutdown

    def closeEvent(self, event):
        """Stop the animation timer cleanly before the window closes."""
        self.timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Center of the reactor (vertically centered with space for label below)
            cx = self.width() / 2.0
            cy = (self.height() - 35) / 2.0  # shift up to leave room for label
            center = QPointF(cx, cy)

            # ── 1. Outer ambient glow ──────────────────────────────────────────
            glow_radius = 85.0 + (8.0 * self.glow_factor)
            glow_grad = QRadialGradient(center, glow_radius)
            glow_alpha = 90 if self.current_state != "idle" else 30
            glow_col = self._get_color(glow_alpha)
            glow_grad.setColorAt(0.0, glow_col)
            glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(glow_grad))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(center, glow_radius, glow_radius)

            # ── 2. Outer rotating segmented ring ──────────────────────────────
            painter.save()
            painter.translate(center)
            painter.rotate(self.rotation_angle)

            # Error state: flashing alpha
            if self.current_state == "error":
                flash_alpha = 150 + int(100 * math.sin(self.pulse_phase * 2))
                ring_color = self._get_color(max(50, min(255, flash_alpha)))
            else:
                ring_color = self._get_color(220)

            ring_pen = QPen(ring_color, 3)
            ring_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(ring_pen)

            # 4 rotating arc segments
            for i in range(4):
                start_angle = (i * 90 + 10) * 16
                span_angle = 70 * 16
                painter.drawArc(QRectF(-70, -70, 140, 140), start_angle, span_angle)

            # Power nodes at each segment boundary
            node_color = self._get_color(255)
            painter.setBrush(QBrush(node_color))
            painter.setPen(Qt.NoPen)
            for i in range(4):
                node_angle_rad = math.radians(i * 90)
                nx = 70 * math.cos(node_angle_rad)
                ny = 70 * math.sin(node_angle_rad)
                painter.drawEllipse(QPointF(nx, ny), 4, 4)

            painter.restore()

            # ── 3. Counter-rotating inner ring ────────────────────────────────
            painter.save()
            painter.translate(center)
            painter.rotate(-self.rotation_angle * 0.5)

            inner_ring_color = self._get_color(160)
            painter.setPen(QPen(inner_ring_color, 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), 54, 54)

            painter.restore()

            # ── 4. Solid inner ring border ────────────────────────────────────
            solid_ring = self._get_color(110)
            painter.setPen(QPen(solid_ring, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 54, 54)

            # ── 5. Inner glowing core ─────────────────────────────────────────
            core_radius = 34.0 + (4.0 * self.glow_factor)
            core_grad = QRadialGradient(center, core_radius)
            core_grad.setColorAt(0.0,  QColor(255, 255, 255, 240))
            core_grad.setColorAt(0.35, self._get_color(230))
            core_grad.setColorAt(0.7,  self._get_color(140))
            core_grad.setColorAt(1.0,  self._get_color(50))

            painter.setBrush(QBrush(core_grad))
            painter.setPen(QPen(self._get_color(180), 1))
            painter.drawEllipse(center, core_radius, core_radius)

            # ── 6. Innermost detail ring ──────────────────────────────────────
            detail_color = QColor(255, 255, 255, 160)
            painter.setPen(QPen(detail_color, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 14, 14)

            # ── 7. Status label (below reactor) ──────────────────────────────
            label_color = self._get_color(200)
            painter.setPen(label_color)
            font = QFont("Segoe UI", 8, QFont.Light)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 3)
            painter.setFont(font)
            label_rect = QRectF(0, self.height() - 32, float(self.width()), 28)
            painter.drawText(label_rect, Qt.AlignCenter, self.display_text.upper())

        except Exception:
            pass  # Suppress all errors during shutdown


def start_hud():
    global _controller
    app = QApplication(sys.argv)
    _controller = HUDController()
    widget = ArcReactorHUD(_controller)
    widget.show()
    sys.exit(app.exec_())
