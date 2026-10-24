"""
interface/bus.py
Two-way link between the assistant process and the robot overlay process.

The overlay runs in its own process (Qt and faster-whisper must not share one), so the
assistant listens on a localhost socket and the overlay connects to it:

    assistant -> overlay   {"type": "state", "state": "thinking", "text": "..."}
                           {"type": "heard", "text": "..."}       what the user said
                           {"type": "say", "text": "..."}         what Surf is saying
                           {"type": "mood", "mood": "dance"}      one-off reaction
                           {"type": "level", "value": 0.4}        mic level while listening
    overlay -> assistant   {"cmd": "listen"} | {"cmd": "text", "text": "..."} |
                           {"cmd": "mute", "value": True} | {"cmd": "stop"} | {"cmd": "quit"}

When no overlay is connected every publish is a no-op, so the assistant runs the same with
or without the robot. Messages are authenticated with a random per-run key.
"""
import os
import queue
import secrets
import subprocess
import sys
import threading
from multiprocessing.connection import Client, Connection, Listener
from typing import Any, Optional

from core import config
from core.logger import get_logger

logger = get_logger("bus")

ENV_PORT = "SURF_BUS_PORT"
ENV_KEY = "SURF_BUS_KEY"


class Bus:
    def __init__(self) -> None:
        self.commands: "queue.Queue[dict]" = queue.Queue()
        self._conns: list[Connection] = []
        self._lock = threading.Lock()
        self._listener: Optional[Listener] = None
        self._key = secrets.token_bytes(16)
        self._last_state: dict = {"type": "state", "state": "idle", "text": ""}

    @property
    def running(self) -> bool:
        return self._listener is not None

    def start(self) -> tuple[int, bytes]:
        """Start listening on a free localhost port. Returns (port, authkey)."""
        if self._listener is None:
            self._listener = Listener(("127.0.0.1", 0), authkey=self._key)
            threading.Thread(target=self._accept_loop, daemon=True, name="BusAccept").start()
        return self._listener.address[1], self._key

    def _accept_loop(self) -> None:
        while True:
            try:
                conn = self._listener.accept()
            except Exception as e:  # bad authkey, listener closed...
                logger.debug(f"Bus accept failed: {e}")
                if self._listener is None:
                    return
                continue
            with self._lock:
                self._conns.append(conn)
            self._send(conn, self._last_state)  # sync a late-joining overlay
            threading.Thread(target=self._read_loop, args=(conn,), daemon=True, name="BusRead").start()

    def _read_loop(self, conn: Connection) -> None:
        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                break
            if isinstance(msg, dict) and "cmd" in msg:
                logger.info(f"From the robot: {msg.get('cmd')}")
                self.commands.put(msg)
        self._drop(conn)

    def _send(self, conn: Connection, msg: dict) -> None:
        try:
            conn.send(msg)
        except (OSError, EOFError, ValueError):
            self._drop(conn)

    def _drop(self, conn: Connection) -> None:
        with self._lock:
            if conn in self._conns:
                self._conns.remove(conn)
        try:
            conn.close()
        except OSError:
            pass

    def publish(self, msg: dict) -> None:
        if msg.get("type") == "state":
            self._last_state = msg
        with self._lock:
            conns = list(self._conns)
        for conn in conns:
            self._send(conn, msg)

    def poll(self) -> Optional[dict]:
        """Next command from the overlay, or None."""
        try:
            return self.commands.get_nowait()
        except queue.Empty:
            return None


bus = Bus()


def emit(kind: str, **data: Any) -> None:
    """Publish an event to the overlay (no-op when there is none)."""
    if bus.running:
        bus.publish({"type": kind, **data})


_overlay: Optional[subprocess.Popen] = None


def launch_overlay() -> Optional[subprocess.Popen]:
    """Start the robot companion in its own process, connected to this process's bus.
    Does nothing if it is already running."""
    global _overlay
    if _overlay is not None and _overlay.poll() is None:
        return _overlay
    port, key = bus.start()
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw  # no console window for the overlay
    env = {**os.environ, ENV_PORT: str(port), ENV_KEY: key.hex()}
    try:
        _overlay = subprocess.Popen([exe, "-m", "interface.companion"], cwd=str(config.BASE_DIR), env=env)
        return _overlay
    except Exception as e:
        logger.warning(f"Could not start the robot overlay: {e}")
        return None


def connect_from_env() -> Connection:
    """Overlay side: connect to the assistant that launched us."""
    return Client(("127.0.0.1", int(os.environ[ENV_PORT])), authkey=bytes.fromhex(os.environ[ENV_KEY]))
