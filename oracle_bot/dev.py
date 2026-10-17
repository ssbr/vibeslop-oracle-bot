"""Helpers for interactive route development: named dev states, inspection dumps."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from . import nav, ram
from .emu import ROOT, Emu

DEV = ROOT / "runs" / "dev"


def save(e: Emu, name: str) -> Path:
    """Save state + log so work can resume from here (log is kept so the run stays replayable)."""
    DEV.mkdir(parents=True, exist_ok=True)
    (DEV / f"{name}.state").write_bytes(e.state())
    e.log.save(DEV / f"{name}.log")
    (DEV / f"{name}.json").write_text(json.dumps({"frame": e.frame}))
    return DEV / f"{name}.state"


def load(name: str) -> Emu:
    from .record import Log

    log = Log.load(DEV / f"{name}.log")
    e = Emu(log=log)
    e.load((DEV / f"{name}.state").read_bytes(), json.loads((DEV / f"{name}.json").read_text())["frame"])
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
