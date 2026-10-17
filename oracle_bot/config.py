"""User configuration (config.toml at the repo root)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass

from .emu import ROOT
from .menus import NAME_GRID

DONATIONS = (150, 50, 10, 1)


@dataclass(frozen=True)
class Config:
    file_name: str = "Link"
    child_name: str = "Pip"
    donation: int = 150  # doctor money for Bipin & Blossom's sick baby (stage 1)
    stone_push: str = "right"  # direction the ▲ rock gets pushed in the intro (cosmetic, permanent)
    message_speed: int = 3  # 1 (slow) .. 5 (fast); 3 is the game's default
    cheat_health: bool = True
    cheat_ammo: bool = True
    export_rupees: int | None = None  # rupee count to write before release saves (None = as played)

    def validate(self) -> None:
        for name in (self.file_name, self.child_name):
            if not 1 <= len(name) <= 5 or any(ch == " " or not any(ch in r for r in NAME_GRID) for ch in name):
                raise ValueError(f"names must be 1-5 characters from the name-entry grid: {name!r}")
        if self.donation not in DONATIONS:
            raise ValueError(f"donation must be one of {DONATIONS}")
        if self.stone_push not in ("left", "right"):
            raise ValueError("stone_push must be left or right")
        if not 1 <= self.message_speed <= 5:
            raise ValueError("message_speed must be 1-5")


def load() -> Config:
    path = ROOT / "config.toml"
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    flat = {**data.get("player", {}), **{f"cheat_{k}": v for k, v in data.get("cheats", {}).items()}}
    if "export_rupees" in data.get("export", {}):
        flat["export_rupees"] = data["export"]["export_rupees"]
    cfg = Config(**flat)
    cfg.validate()
    return cfg
