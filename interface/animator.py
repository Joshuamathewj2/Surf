"""
interface/animator.py
The robot's behaviour: which sprite frame to show, where to stand, and how to move.
Pure Python (no Qt), so it can be unit-tested; interface/companion.py only draws its output.

Layers, highest priority first:
  1. being dragged / falling back to the taskbar
  2. a one-off reaction ("mood": happy, dance, heart...) for a second or two
  3. the assistant's state: listening, thinking, executing, speaking, error
  4. idle life: breathing, blinking, looking around, wandering along the taskbar,
     and eventually sitting down and dozing off
"""
import math
import random
from dataclasses import dataclass
from typing import Optional

# clip name -> (sprite animation, frame order, frames per second, loops)
# The art (tools/extract_sprites.py) has breathing, wide-eyed, sitting, thinking and walking frames;
# the other animations reuse the closest of those and get their motion procedurally in tick().
CLIPS: dict[str, tuple[str, list[int], float, bool]] = {
    "breathe": ("idle", [0, 1, 2, 3, 4, 5, 4, 3, 2, 1], 5, True),
    "look_around": ("think", [0] * 10, 5, False),  # stops to ponder for a couple of seconds
    "blink": ("blink", [0, 0], 7, False),  # a quick wide-eyed glance
    "wink": ("blink", [0, 0, 0], 6, False),
    "walk_right": ("walk_right", [], 8, True),
    "walk_left": ("walk_left", [], 8, True),
    "run_right": ("run_right", [], 13, True),
    "run_left": ("run_left", [], 13, True),
    "jump": ("jump", [0], 1, False),
    "land": ("land", [5, 3, 0], 9, False),  # squashed on impact, springing back up
    "dangle": ("jump", [0], 1, True),
    "sit": ("sit", [0], 2, False),
    "sleep": ("sleep", [0], 1, True),
    "dance": ("dance", [0, 2, 4, 2], 6, True),
    "fail": ("fail", [0], 1, False),
}
# Single-frame poses: animation name == clip name.
POSES = ("wave", "happy", "clap", "sad", "think", "point", "heart", "cheer", "lightbulb",
         "confused", "angry", "surprised", "hello", "bye", "victory")
for _pose in POSES:
    CLIPS[_pose] = (_pose, [0], 1, True)

# How long a mood plays before the robot goes back to what it was doing (seconds).
MOOD_SECONDS = {"dance": 4.0, "sleep": 3.0, "fail": 2.6, "jump": 1.2, "bye": 2.4, "wink": 0.6}
DEFAULT_MOOD_SECONDS = 2.2

# Assistant state -> the clip that represents it.
STATE_CLIPS = {
    "listening": "breathe",
    "thinking": "think",
    "executing": "point",
    "speaking": "breathe",
    "error": "sad",
}
# Entering a state can play a short intro first (e.g. waving hello when you wake it).
STATE_INTROS = {"listening": ("hello", 0.7)}

SLEEP_AFTER_SEC = 240.0
WALK_SPEED = 62.0  # logical px per second (matches the 8 fps stride)


@dataclass
class Pose:
    anim: str  # sprite animation name (folder key in sprites.json)
    frame: int  # index into that animation's frames
    x: float  # robot centre, logical px in screen coordinates
    lift: float  # px above the taskbar: being carried or falling (moves the window)
    bob: float  # small procedural hop drawn inside the window (px up)
    angle: float  # degrees, rotation around the feet
    glow: str  # "", "listen", "think", "speak": the Siri-style aura behind the robot
    sleeping: bool


class Animator:
    def __init__(self, frame_counts: dict[str, int], roam: bool = True, rng: Optional[random.Random] = None):
        self.frame_counts = frame_counts
        self.roam = roam
        self.rng = rng or random.Random()
        self.state = "idle"
        self.min_x, self.max_x = 0.0, 1000.0
        self.x = 900.0
        self.lift = 0.0
        self.fall_speed = 0.0
        self.dragging = False

        self._clip = "breathe"
        self._clip_start = 0.0
        self._mood: Optional[str] = None
        self._mood_until = 0.0
        self._intro: Optional[str] = None
        self._intro_until = 0.0
        self._last_activity = 0.0
        self._next_idle_event = 3.0
        self._walk_target: Optional[float] = None
        self._sleeping = False
        self._landing_until = 0.0

    # ------------------------------------------------------------------ inputs

    def set_bounds(self, min_x: float, max_x: float) -> None:
        self.min_x, self.max_x = min_x, max(min_x, max_x)
        self.x = min(max(self.x, self.min_x), self.max_x)

    def activity(self, now: float) -> None:
        """Something happened (an event, a click): wake up and reset the idle timers."""
        self._last_activity = now
        self._walk_target = None
        if self._sleeping:
            self._sleeping = False
            self.mood("jump", now)
        self._next_idle_event = now + self.rng.uniform(3, 6)

    def on_state(self, state: str, now: float) -> None:
        if state == self.state:
            return
        self.state = state
        self.activity(now)
        intro = STATE_INTROS.get(state)
        if intro and not self._mood:
            self._intro, self._intro_until = intro[0], now + intro[1]

    def mood(self, mood: str, now: float, seconds: Optional[float] = None) -> None:
        if mood not in CLIPS:
            return
        if mood != "jump" and mood != "sleep":
            self._last_activity = now
            self._sleeping = False
        self._walk_target = None
        self._mood = mood
        self._mood_until = now + (seconds or MOOD_SECONDS.get(mood, DEFAULT_MOOD_SECONDS))
        self._clip_start = now

    def start_drag(self, now: float) -> None:
        self.dragging = True
        self.activity(now)

    def drag_to(self, x: float, lift: float) -> None:
        self.x = min(max(x, self.min_x), self.max_x)
        self.lift = max(0.0, lift)

    def end_drag(self, now: float) -> None:
        self.dragging = False
        self.fall_speed = 0.0
        self.activity(now)

    # ------------------------------------------------------------------ tick

    def _frames(self, clip: str) -> tuple[str, list[int], float, bool]:
        anim, order, fps, loop = CLIPS[clip]
        count = self.frame_counts.get(anim, 1)
        order = [i for i in order if i < count] or list(range(count))
        return anim, order, fps, loop

    def _frame_of(self, clip: str, now: float) -> tuple[str, int, bool]:
        """(animation, frame index, finished) for a clip started at self._clip_start."""
        anim, order, fps, loop = self._frames(clip)
        step = int((now - self._clip_start) * fps)
        if loop:
            return anim, order[step % len(order)], False
        return anim, order[min(step, len(order) - 1)], step >= len(order)

    def _set_clip(self, clip: str, now: float) -> None:
        if clip != self._clip:
            self._clip = clip
            self._clip_start = now

    def _idle_clip(self, now: float, dt: float) -> str:
        if self._sleeping:
            return "sleep"
        if now - self._last_activity > SLEEP_AFTER_SEC:
            if self._clip == "sit":
                _, _, done = self._frame_of("sit", now)
                if done and now - self._clip_start > 3.0:
                    self._sleeping = True
                    return "sleep"
            return "sit"
        if self._walk_target is not None:
            step = WALK_SPEED * dt
            if abs(self._walk_target - self.x) <= step:
                self.x = self._walk_target
                self._walk_target = None
            else:
                self.x += step if self._walk_target > self.x else -step
                return "walk_right" if self._walk_target > self.x else "walk_left"
        if self._clip in ("look_around", "blink", "wink"):
            _, _, done = self._frame_of(self._clip, now)
            if not done:
                return self._clip
        if now >= self._next_idle_event:
            self._next_idle_event = now + self.rng.uniform(3.5, 8.0)
            roll = self.rng.random()
            span = self.max_x - self.min_x
            if self.roam and roll < 0.18 and span > 200:
                self._walk_target = self.rng.uniform(self.min_x + 40, self.max_x - 40)
                return "walk_right" if self._walk_target > self.x else "walk_left"
            if roll < 0.35:
                return "look_around"
            if roll < 0.42:
                return "wink"
            return "blink"
        return "breathe"

    def tick(self, now: float, dt: float) -> Pose:
        angle = 0.0
        glow = {"listening": "listen", "thinking": "think", "speaking": "speak"}.get(self.state, "")

        if self.dragging:
            self._set_clip("dangle", now)
            angle = 6.0 * math.sin(now * 5.0)
        elif self.lift > 0.5:  # dropped mid-air: fall back onto the taskbar
            self.fall_speed += 1800.0 * dt
            self.lift = max(0.0, self.lift - self.fall_speed * dt)
            self._set_clip("dangle", now)
            if self.lift == 0.0:
                self._landing_until = now + 0.35
                self._set_clip("land", now)
        elif now < self._landing_until:
            self._set_clip("land", now)
        elif self._mood and now < self._mood_until:
            self._set_clip(self._mood, now)
        else:
            if self._mood:
                self._mood = None
            if self._intro and now < self._intro_until:
                self._set_clip(self._intro, now)
            elif self.state in STATE_CLIPS:
                self._intro = None
                self._set_clip(STATE_CLIPS[self.state], now)
            else:
                self._intro = None
                self._set_clip(self._idle_clip(now, dt), now)

        anim, frame, _ = self._frame_of(self._clip, now)
        bob = 0.0
        # Procedural life so single-frame poses don't look frozen.
        if not self.dragging and self.lift == 0.0:
            if self._clip in ("wave", "hello", "bye"):
                angle = 5.0 * math.sin(now * 7.0)
            elif self._clip in ("happy", "cheer", "victory", "clap", "heart"):
                bob = abs(math.sin(now * 6.0)) * 7.0
            elif self._clip == "dance":
                angle = 7.0 * math.sin(now * 6.0)
                bob = abs(math.sin(now * 6.0)) * 6.0
            elif self._clip == "jump":  # one hop, waking up with a start
                t = (now - self._clip_start) / 0.45
                bob = 22.0 * math.sin(math.pi * t) if t < 1 else 0.0
            elif self._clip in ("sad", "fail"):
                angle = -4.0
                bob = 1.0 + math.sin(now * 1.5)
            elif self._clip == "think":
                angle = 3.0 * math.sin(now * 1.6)
                bob = 1.5 + 1.5 * math.sin(now * 2.0)
            elif self._clip in ("surprised", "lightbulb"):
                bob = abs(math.sin(now * 4.0)) * 4.0
            elif self._clip == "angry":
                angle = 2.5 * math.sin(now * 30.0)
            elif self._clip == "sleep":
                bob = 0.0
            elif self.state == "speaking":
                bob = abs(math.sin(now * 9.0)) * 2.5
        return Pose(anim, frame, self.x, self.lift, bob, angle, glow, self._sleeping)
