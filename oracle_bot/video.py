"""Video clips re-rendered from replay logs. Runs are deterministic, so any stretch of one can be watched later
without slowing the bot down while it plays.

MP4 needs ffmpeg on PATH; without it clips are written as GIFs (every other frame).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .emu import replay
from .record import Log

FPS = 59.7275  # Game Boy frame rate
STRIP = 12  # caption strip height under the screen, in Game Boy pixels


class ClipWriter:
    """Writes finished frames (already scaled and captioned) at the Game Boy frame rate."""

    def __init__(self, out: Path, width: int, height: int):
        self.ffmpeg = shutil.which("ffmpeg")
        self.out = out.with_suffix(".mp4" if self.ffmpeg else ".gif")
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.frames: list[Image.Image] = []
        self.count = 0
        self.proc = None
        if self.ffmpeg:
            self.proc = subprocess.Popen(
                [self.ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 "-s", f"{width}x{height}", "-r", f"{FPS}", "-i", "-",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(self.out)],
                stdin=subprocess.PIPE)

    def add(self, rgb: np.ndarray) -> None:
        self.count += 1
        if self.proc:
            self.proc.stdin.write(np.ascontiguousarray(rgb, dtype=np.uint8).tobytes())
        elif self.count % 2:
            self.frames.append(Image.fromarray(rgb))

    def close(self) -> Path:
        if self.proc:
            self.proc.stdin.close()
            self.proc.wait()
        elif self.frames:
            self.frames[0].save(self.out, save_all=True, append_images=self.frames[1:], duration=33, loop=0)
        return self.out


@cache
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def compose(screen: np.ndarray, scale: int, caption: str | None) -> np.ndarray:
    """The screen scaled up (nearest neighbour), with an optional caption strip underneath."""
    big = screen.repeat(scale, 0).repeat(scale, 1)
    if caption is None:
        return big
    strip = Image.new("RGB", (big.shape[1], STRIP * scale), (20, 20, 24))
    ImageDraw.Draw(strip).text((3 * scale, 2 * scale), caption, fill=(235, 235, 235), font=_font(8 * scale))
    return np.vstack([big, np.asarray(strip)])


def render(log: Log, start: int, end: int, out: Path, base: tuple[bytes, int, int] | None = None, speed: int = 1,
           scale: int = 3, caption=None, chapters: list[tuple[int, str]] = ()) -> Path:
    """Render frames [start, end) of `log` to `out`, `speed` times faster (each video frame blends a game frame
    with the next, so sprites the game flickers between frames don't vanish). `caption(frame)` -> text for a strip
    under the screen; `chapters` = [(game frame, title)] are added as MP4 chapters. `base` = (state, frame,
    n_ops) to replay from (a snapshot taken while recording this log) instead of from power-on."""
    height = 144 + (STRIP if caption else 0)
    writer = ClipWriter(out, 160 * scale, height * scale)
    held: list[np.ndarray] = []

    def on_frame(e) -> None:
        phase = (e.frame - start) % speed
        if speed > 1 and phase > 1:
            return
        held.append(e.screen())
        if speed > 1 and len(held) < 2:
            return
        screen = held[0] if len(held) == 1 else ((held[0].astype(np.uint16) + held[1]) // 2).astype(np.uint8)
        held.clear()
        writer.add(compose(screen, scale, caption(e.frame) if caption else None))

    try:
        replay(log, until=end, base=base, frames_from=start, on_frame=on_frame)
    finally:
        path = writer.close()
    if chapters and writer.ffmpeg:
        add_chapters(path, [((f - start) / speed / FPS, title) for f, title in chapters if start <= f < end])
    return path


def add_chapters(path: Path, chapters: list[tuple[float, str]]) -> None:
    """Mux chapter marks (video seconds, title) into an MP4 in place."""
    meta = [";FFMETADATA1"]
    for i, (t, title) in enumerate(chapters):
        stop = chapters[i + 1][0] if i + 1 < len(chapters) else t + 3600
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(t * 1000)}", f"END={int(stop * 1000)}",
                 f"title={title}"]
    meta_path, tmp = path.with_suffix(".chapters.txt"), path.with_suffix(".tmp.mp4")
    meta_path.write_text("\n".join(meta) + "\n", newline="\n")
    subprocess.run([shutil.which("ffmpeg"), "-y", "-loglevel", "error", "-i", str(path), "-i", str(meta_path),
                    "-map_metadata", "1", "-map_chapters", "1", "-codec", "copy", str(tmp)], check=True)
    tmp.replace(path)
    meta_path.unlink()


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


def step_frames(run_dir: Path) -> list[tuple[str, int, int]]:
    """(route item name, first frame, end frame) for each item a run's snapshots record, in order."""
    out, start = [], 0
    for p in sorted((run_dir / "states").glob("*.json")):
        end = json.loads(p.read_text())["frame"]
        out.append((p.stem.split("_", 1)[1], start, end))
        start = end
    return out


def step_range(run_dir: Path, first: str, last: str | None = None) -> tuple[int, int]:
    """Frames route items `first` through `last` (default: just `first`) took in a run."""
    steps = {name: (start, end) for name, start, end in step_frames(run_dir)}
    for name in (first, last or first):
        if name not in steps:
            raise KeyError(f"no snapshot for {name!r} in {run_dir}")
    return steps[first][0], steps[last or first][1]


def game_time(frame: int) -> str:
    s = int(frame / FPS)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def step_captions(run_dir: Path):
    """caption(frame) -> "game time  step name", and the steps as chapters, for a run."""
    steps = [(name.replace("_", " "), start, end) for name, start, end in step_frames(run_dir) if end > start]

    def caption(frame: int) -> str:
        name = next((n for n, s, e in steps if s <= frame < e), steps[-1][0] if steps else "")
        return f"{game_time(frame)}   {name}"

    return caption, [(start, f"{game_time(start)} {name}") for name, start, _ in steps]
