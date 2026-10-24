"""The robot's behaviour (pure Python) and the assistant <-> overlay link. No Qt needed."""
import json
import os
import random
import time
from multiprocessing.connection import Client
from pathlib import Path

from interface.animator import CLIPS, SLEEP_AFTER_SEC, Animator
from interface.bus import Bus

ASSETS = Path(__file__).resolve().parent.parent / "interface" / "assets" / "robot"
MANIFEST = json.loads((ASSETS / "sprites.json").read_text())
COUNTS = {name: len(files) for name, files in MANIFEST["frames"].items()}


def make(roam=False):
    a = Animator(COUNTS, roam=roam, rng=random.Random(1))
    a.set_bounds(200, 1800)
    a.x = 1000
    return a


def test_every_clip_points_at_real_frames():
    for clip, (anim, order, fps, loop) in CLIPS.items():
        assert anim in COUNTS, clip
        for i in order:
            assert i < COUNTS[anim], (clip, i)
    for files in MANIFEST["frames"].values():
        for f in files:
            assert (ASSETS / f).exists()


def test_frames_are_transparent_pngs():
    from PIL import Image

    img = Image.open(ASSETS / "idle_0.png")
    assert img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0  # corners are see-through
    assert img.getpixel((img.width // 2, img.height // 3))[3] == 255  # the helmet is solid


def test_states_pick_poses_and_auras():
    a = make()
    a.on_state("thinking", 0)
    pose = a.tick(0.1, 0.016)
    assert pose.anim == "think" and pose.glow == "think"
    a.on_state("listening", 1)
    assert a.tick(1.1, 0.016).anim == "hello"  # waves hello first...
    pose = a.tick(2.5, 0.016)
    assert pose.anim == "idle" and pose.glow == "listen"  # ...then listens
    a.on_state("error", 3)
    assert a.tick(3.1, 0.016).anim == "sad"


def test_moods_play_then_return_to_the_state():
    a = make()
    a.on_state("idle", 0)
    a.mood("dance", 0)
    assert a.tick(1.0, 0.016).anim == "dance"
    assert a.tick(10.0, 0.016).anim != "dance"
    a.mood("not-a-real-mood", 11)
    assert a.tick(11.1, 0.016).anim != "not-a-real-mood"


def test_falls_asleep_when_left_alone_and_wakes_up():
    a = make()
    t = 0.0
    a.activity(t)
    t = SLEEP_AFTER_SEC + 1
    assert a.tick(t, 0.016).anim == "sit"
    for _ in range(10):
        t += 1
        pose = a.tick(t, 1.0)
    assert pose.anim == "sleep" and pose.sleeping
    a.on_state("listening", t)
    assert not a.tick(t + 0.1, 0.016).sleeping


def test_dropping_it_mid_air_falls_back_to_the_taskbar():
    a = make()
    a.start_drag(0)
    a.drag_to(5000, 300)  # clamped to the screen
    assert a.x == 1800 and a.tick(0.1, 0.016).lift == 300
    a.end_drag(0.2)
    t = 0.2
    for _ in range(100):
        t += 0.016
        pose = a.tick(t, 0.016)
    assert pose.lift == 0.0


def test_wanders_only_when_allowed():
    for roam in (False, True):
        a = make(roam=roam)
        start = a.x
        t = 0.0
        for _ in range(4000):  # ~65 s of idle time
            t += 0.016
            a.tick(t, 0.016)
        assert (a.x != start) == roam
        assert 200 <= a.x <= 1800


def test_bus_round_trip():
    bus = Bus()
    port, key = bus.start()
    conn = Client(("127.0.0.1", port), authkey=key)
    try:
        assert conn.recv()["type"] == "state"  # a new overlay is told the current state
        bus.publish({"type": "say", "text": "hello"})
        assert conn.recv() == {"type": "say", "text": "hello"}
        conn.send({"cmd": "text", "text": "what time is it"})
        deadline = time.time() + 3
        msg = None
        while msg is None and time.time() < deadline:
            msg = bus.poll()
            time.sleep(0.01)
        assert msg == {"cmd": "text", "text": "what time is it"}
    finally:
        conn.close()


def test_bus_rejects_the_wrong_key():
    import multiprocessing

    bus = Bus()
    port, _ = bus.start()
    try:
        Client(("127.0.0.1", port), authkey=os.urandom(16))
        raise AssertionError("connected with a wrong key")
    except multiprocessing.AuthenticationError:
        pass
