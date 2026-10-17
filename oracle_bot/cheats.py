"""Cheats as logged RAM writes, applied once per frame by policy.

Writes happen only during normal gameplay and only when they change a value, so they show up in the replay
log as occasional `W ... cheat` ops (e.g. after Link takes damage).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ram
from .emu import Emu

SEEDS = ("EMBER", "SCENT", "PEGASUS", "GALE", "MYSTERY")
SATCHEL_CAPACITY = {1: 20, 2: 50, 3: 99}


@dataclass
class Cheats:
    health: bool = True
    ammo: bool = True
    suspended: bool = False

    def __call__(self, e: Emu) -> None:
        if self.suspended or not gameplay(e):
            return
        if self.health:
            hp, hmax = ram.health(e)
            if 0 < hp < hmax:
                ram.poke(e, "wLinkHealth", hmax, "cheat")
        if self.ammo:
            refill_ammo(e)


def gameplay(e: Emu) -> bool:
    return (ram.u8(e, "wGameState") == 2 and ram.u8(e, "wCutsceneIndex") == 1 and not ram.menu_open(e)
            and ram.u8(e, "wLinkDeathTrigger") == 0)


def refill_ammo(e: Emu) -> None:
    if ram.has(e, "SEED_SATCHEL") or ram.has(e, "SHOOTER"):
        cap = SATCHEL_CAPACITY.get(ram.u8(e, "wSeedSatchelLevel"), 20)
        for i, seed in enumerate(SEEDS):
            if ram.has(e, f"{seed}_SEEDS") and ram.bcd(ram.read(e, "wNumEmberSeeds", 1, off=i)) < cap:
                ram.poke(e, "wNumEmberSeeds", ram.to_bcd(cap, 1), "cheat", off=i)
    if ram.has(e, "BOMBS"):
        cap = ram.u8(e, "wMaxBombs")
        if ram.u8(e, "wNumBombs") < cap:
            ram.poke(e, "wNumBombs", cap, "cheat")


def ensure_rupees(e: Emu, n: int) -> None:
    """Top up rupees to at least n (logged), e.g. right before a purchase."""
    if ram.rupees(e) < n:
        ram.poke(e, "wNumRupees", ram.to_bcd(n, 2), "rupees")


def sanity(e: Emu) -> list[str]:
    """Problems that would make an exported save look corrupted."""
    problems = []
    hp, hmax = ram.health(e)
    if not 0 < hp <= hmax:
        problems.append(f"health {hp}/{hmax}")
    cap = SATCHEL_CAPACITY.get(ram.u8(e, "wSeedSatchelLevel"), 20)
    for i, seed in enumerate(SEEDS):
        n = ram.bcd(ram.read(e, "wNumEmberSeeds", 1, off=i))
        if n > cap:
            problems.append(f"{seed} seeds {n} > {cap}")
    if ram.u8(e, "wNumBombs") > ram.u8(e, "wMaxBombs"):
        problems.append("bombs over capacity")
    return problems
