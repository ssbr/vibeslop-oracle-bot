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


def load(name: str) -> Emu:
    return load_snapshot(DEV / name)


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
