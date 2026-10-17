"""Helpers for interactive route development: named dev states, inspection dumps."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import nav, ram
from .emu import ROOT, Emu, load_snapshot, save_snapshot

DEV = ROOT / "runs" / "dev"


def save(e: Emu, name: str) -> Path:
    save_snapshot(e, DEV / name)
    return DEV / name


def load(name: str, cheat: bool = True) -> Emu:
    """Load a dev snapshot (from runs/dev, or a path to a run's state). Cheats are attached like in real runs."""
    from . import cheats

    path = Path(name)
    e = load_snapshot(path.with_suffix("") if path.suffix == ".state" or path.parent != Path(".") else DEV / name)
    if cheat:
        e.before_frame.append(cheats.Cheats())
    return e


def inspect(e: Emu, png: str | Path | None = "runs/dev/inspect.png", scale: int = 2) -> str:
    text = ram.summary(e) + "\n" + nav.ascii(e)
    if png:
        img = Image.fromarray(e.screen())
        img.resize((160 * scale, 144 * scale), Image.NEAREST).save(ROOT / png)
    return text


def sheet(frames: list, path: str | Path, cols: int = 4) -> None:
    imgs = [Image.fromarray(f) for f in frames]
    if not imgs:
        return
    out = Image.new("RGB", (160 * cols, 144 * ((len(imgs) + cols - 1) // cols)))
    for i, im in enumerate(imgs):
        out.paste(im, ((i % cols) * 160, (i // cols) * 144))
    out.save(ROOT / path)


def render_room(e: Emu, path: str | Path, scale: int = 2) -> None:
    """Whole-room image (large rooms are bigger than the screen): pans the camera in a scratch copy."""
    import numpy as np

    st = (e.state(), e.frame, len(e.log.ops))
    large = ram.u8(e, "wRoomIsLarge")
    H, W = (176, 240) if large else (128, 160)
    full = np.zeros((H, W, 3), np.uint8)
    for cy, cx in {(0, 0), (0, W - 160), (H - 128, 0), (H - 128, W - 160)}:
        e.load(*st)
        for _ in range(3):
            e.poke(0xFFAA, cy, None, "dev")
            e.poke(0xFFAC, cx, None, "dev")
            e.step(1, render=True)
        full[cy:cy + 128, cx:cx + 160] = e.screen()[16:144]
    e.load(*st)
    Image.fromarray(full).resize((W * scale, H * scale), Image.NEAREST).save(ROOT / path)
