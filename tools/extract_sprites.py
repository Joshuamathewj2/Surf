"""
tools/extract_sprites.py
Cut the robot sprite sheets (generated with Google Flow from docs/surf.png) into transparent
animation frames.

    python tools/extract_sprites.py [out_dir]

Inputs, both on a flat chroma-green background:
  docs/sprites/surf_poses.jpg  4 poses in a row: standing, standing wide-eyed, sitting, thinking
  docs/sprites/surf_walk.jpg   6-frame walk cycle facing right

This script:
  1. keys out the green (soft edges, with green spill removed from the robot's rim),
  2. finds each robot as a connected blob, so stray claws and the sheet watermark are handled,
  3. scales both sheets so the walking robot is as tall as the standing one,
  4. pads every frame of an animation to one canvas, bottom-aligned and centred on the helmet,
     so playback doesn't jitter,
  5. derives breathing frames from the standing pose and a left walk by mirroring,
  6. writes <out_dir>/<anim>_<n>.png and <out_dir>/sprites.json. Animations the art doesn't
     cover (moods like "happy" or "sad") reuse the closest pose; interface/animator.py adds
     the motion procedurally.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
POSES_SHEET = ROOT / "docs" / "sprites" / "surf_poses.jpg"
WALK_SHEET = ROOT / "docs" / "sprites" / "surf_walk.jpg"
DEFAULT_OUT = ROOT / "interface" / "assets" / "robot"

POSE_NAMES = ["idle", "blink", "sit", "think"]  # left to right on the poses sheet
STAND_H = 420  # stored height of the standing robot in px (~3.5x the default 120px on screen)
BREATHE_FRAMES = 6
BREATHE_SQUASH = 0.016  # deepest breath: 1.6% shorter, a little wider
KEY_SOLID, KEY_CLEAR = 35, 95  # greenness (g - max(r, b)) at which a pixel is fully robot / background
MERGE_PX = 6  # parts of one robot closer than this belong together (the robots nearly touch)
MIN_AREA = 20000  # smaller blobs (the watermark, specks) are dropped

# Animation names interface/animator.py plays -> the generated animation they reuse.
ALIASES = {
    "run_right": "walk_right", "run_left": "walk_left",
    "jump": "idle", "land": "idle", "dance": "idle", "wave": "idle", "hello": "idle", "bye": "idle",
    "happy": "idle", "clap": "idle", "heart": "idle", "cheer": "idle", "victory": "idle",
    "sad": "think", "fail": "think", "confused": "think", "point": "think", "lightbulb": "think",
    "surprised": "blink", "angry": "blink",
    "sleep": "sit",
}


def _key(path: Path) -> np.ndarray:
    """RGBA float array with the chroma green made transparent."""
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    rb = np.maximum(r, b)
    alpha = np.clip((KEY_CLEAR - (g - rb)) / (KEY_CLEAR - KEY_SOLID), 0.0, 1.0)
    rgb[..., 1] = np.minimum(g, rb + 6)  # despill: no pixel of the robot is greener than this
    return np.dstack([rgb, alpha * 255])


def _robots(rgba: np.ndarray, expected: int) -> list[tuple[np.ndarray, float]]:
    """Each robot on the sheet, left to right, as (tight RGBA crop, helmet centre x in the crop)."""
    solid = rgba[..., 3] > 128
    groups, _ = ndimage.label(ndimage.binary_dilation(solid, iterations=MERGE_PX))
    sizes = ndimage.sum(solid, groups, index=range(1, groups.max() + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= MIN_AREA]
    if len(keep) != expected:
        raise SystemExit(f"expected {expected} robots, found {len(keep)}")
    keep.sort(key=lambda i: ndimage.center_of_mass(groups == i)[1])
    out = []
    for i in keep:
        mine = (groups == i) & (rgba[..., 3] > 0)
        ys, xs = np.nonzero(mine)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = rgba[y0:y1, x0:x1].copy()
        crop[..., 3] *= mine[y0:y1, x0:x1]
        # The helmet is the top 45% of the robot; centring on it keeps the head steady.
        head = crop[: int(crop.shape[0] * 0.45), :, 3] > 128
        out.append((crop, float(np.nonzero(head)[1].mean())))
    return out


def _resize(crop: np.ndarray, cx: float, scale: float, sx: float = 1.0) -> tuple[Image.Image, float]:
    # Premultiply so edge colours don't bleed while resampling.
    pre = crop.copy()
    pre[..., :3] *= pre[..., 3:4] / 255
    img = Image.fromarray(np.clip(pre, 0, 255).astype(np.uint8), "RGBA")
    w, h = max(1, round(img.width * scale * sx)), max(1, round(img.height * scale))
    small = np.asarray(img.resize((w, h), Image.LANCZOS)).astype(np.float32)
    a = small[..., 3:4]
    small[..., :3] = np.where(a > 0, small[..., :3] * 255 / np.maximum(a, 1), 0)
    small[..., 1] = np.minimum(small[..., 1], np.maximum(small[..., 0], small[..., 2]) + 6)  # despill again
    return Image.fromarray(np.clip(small, 0, 255).astype(np.uint8), "RGBA"), cx * scale * sx


def _canvas(frames: list[tuple[Image.Image, float]]) -> list[Image.Image]:
    """Pad frames to one size: bottoms aligned, helmet centres on the canvas centre line."""
    half = max(max(cx, im.width - cx) for im, cx in frames)
    w, h = int(np.ceil(half * 2)) + 2, max(im.height for im, _ in frames)
    out = []
    for im, cx in frames:
        c = Image.new("RGBA", (w, h))
        c.paste(im, (round(w / 2 - cx), h - im.height))
        out.append(c)
    return out


def main(out_dir: Path) -> None:
    poses = _robots(_key(POSES_SHEET), len(POSE_NAMES))
    walk = _robots(_key(WALK_SHEET), 6)
    scale = STAND_H / poses[0][0].shape[0]
    walk_scale = STAND_H / float(np.median([c.shape[0] for c, _ in walk]))

    anims: dict[str, list[Image.Image]] = {}
    for name, (crop, cx) in zip(POSE_NAMES, poses):
        anims[name] = _canvas([_resize(crop, cx, scale)])
    stand, cx = poses[0]
    anims["idle"] = _canvas([
        _resize(stand, cx, scale * (1 - d), (1 + d * 0.5) / (1 - d))
        for d in (BREATHE_SQUASH * k / (BREATHE_FRAMES - 1) for k in range(BREATHE_FRAMES))
    ])
    anims["walk_right"] = _canvas([_resize(c, x, walk_scale) for c, x in walk])
    anims["walk_left"] = [im.transpose(Image.FLIP_LEFT_RIGHT) for im in anims["walk_right"]]

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in list(out_dir.glob("*.png")):
        old.unlink()
    manifest = {"frames": {}, "size": {}}
    for name, frames in anims.items():
        files = []
        for n, im in enumerate(frames):
            files.append(f"{name}_{n}.png")
            im.save(out_dir / files[-1], optimize=True)
        manifest["frames"][name] = files
        manifest["size"][name] = list(frames[0].size)
    for alias, target in ALIASES.items():
        manifest["frames"][alias] = manifest["frames"][target]
        manifest["size"][alias] = manifest["size"][target]
    (out_dir / "sprites.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {sum(len(f) for f in anims.values())} frames to {out_dir}")
    for name, frames in anims.items():
        print(f"  {name}: {len(frames)} x {frames[0].size}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT)
