"""Video clips re-rendered from replay logs. Runs are deterministic, so any stretch of one can be watched later
without slowing the bot down while it plays.

MP4 needs ffmpeg on PATH; without it clips are written as GIFs (every other frame).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from .emu import replay
from .record import Log

FPS = 59.7275  # Game Boy frame rate


class ClipWriter:
    def __init__(self, out: Path, scale: int = 3):
        self.scale = scale
        self.ffmpeg = shutil.which("ffmpeg")
        self.out = out.with_suffix(".mp4" if self.ffmpeg else ".gif")
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.frames: list[Image.Image] = []
        self.count = 0
        self.proc = None
        if self.ffmpeg:
            self.proc = subprocess.Popen(
                [self.ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "160x144",
                 "-r", f"{FPS}", "-i", "-", "-vf", f"scale={160 * scale}:{144 * scale}:flags=neighbor",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(self.out)],
                stdin=subprocess.PIPE)

    def add(self, rgb: np.ndarray) -> None:
        self.count += 1
        if self.proc:
            self.proc.stdin.write(np.ascontiguousarray(rgb, dtype=np.uint8).tobytes())
        elif self.count % 2:
            self.frames.append(Image.fromarray(rgb).resize((160 * self.scale, 144 * self.scale), Image.NEAREST))

    def close(self) -> Path:
        if self.proc:
            self.proc.stdin.close()
            self.proc.wait()
        elif self.frames:
            self.frames[0].save(self.out, save_all=True, append_images=self.frames[1:], duration=33, loop=0)
        return self.out


def render(log: Log, start: int, end: int, out: Path, base: tuple[bytes, int, int] | None = None) -> Path:
    """Render frames [start, end) of `log` to `out`. `base` = (state, frame, n_ops) to replay from (a snapshot
    taken while recording this log) instead of from power-on."""
    writer = ClipWriter(out)
    try:
        replay(log, until=end, base=base, frames_from=start, on_frame=lambda e: writer.add(e.screen()))
    finally:
        path = writer.close()
    return path


def nearest_state(run_dir: Path, frame: int) -> tuple[bytes, int, int] | None:
    """The latest run snapshot at or before `frame`, as a replay base."""
    best = None
    for meta_path in (run_dir / "states").glob("*.json"):
        meta = json.loads(meta_path.read_text())
        if meta["frame"] <= frame and (best is None or meta["frame"] > best[0]["frame"]):
            best = (meta, meta_path)
    if best is None:
        return None
    meta, meta_path = best
    return meta_path.with_suffix(".state").read_bytes(), meta["frame"], meta["n_ops"]


def step_range(run_dir: Path, name: str) -> tuple[int, int]:
    """Frames a route item took in a run: from the snapshot before it to its own."""
    snaps = sorted((run_dir / "states").glob("*.json"))
    for i, p in enumerate(snaps):
        if p.stem.split("_", 1)[1] == name:
            end = json.loads(p.read_text())["frame"]
            start = json.loads(snaps[i - 1].read_text())["frame"] if i else 0
            return start, end
    raise KeyError(f"no snapshot for {name!r} in {run_dir}")
