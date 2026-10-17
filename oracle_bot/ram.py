"""Named RAM access on top of Emu, using symbols generated from the disassembly (tools/gen_symbols.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .emu import Emu

_DATA = json.loads((Path(__file__).parent / "data" / "ages.json").read_text())
SYM: dict[str, tuple[int | None, int]] = {k: (v[0], v[1]) for k, v in _DATA["ram"].items()}
CONST: dict[str, int] = _DATA["const"]
STRUCT: dict[str, dict[str, int]] = _DATA["structs"]
TREASURES: dict[str, int] = _DATA["treasures"]
TEXT: dict[str, str] = json.loads((Path(__file__).parent / "data" / "ages_text.json").read_text(encoding="utf-8"))
OBJ = STRUCT["ObjectStruct"]

# Room-flag tables by active group: present/past overworld and their small rooms share a table, likewise
# large rooms and their sidescrolling views.
ROOM_FLAG_BASE = {0: 0xC700, 2: 0xC700, 1: 0xC800, 3: 0xC800, 4: 0xC900, 6: 0xC900, 5: 0xCA00, 7: 0xCA00}

# Object slots in WRAM bank 1: page $d0-$df, 4 objects of $40 bytes per page.
OBJECT_KINDS = {"item": 0x00, "interaction": 0x40, "enemy": 0x80, "part": 0xC0}


def u8(e: Emu, name: str, off: int = 0) -> int:
    bank, addr = SYM[name]
    return e.u8(addr + off, bank)


def read(e: Emu, name: str, n: int, off: int = 0) -> bytes:
    bank, addr = SYM[name]
    return e.read(addr + off, n, bank)


def poke(e: Emu, name: str, data: int | bytes, tag: str, off: int = 0) -> None:
    bank, addr = SYM[name]
    e.poke(addr + off, data, bank, tag)


def bcd(data: bytes) -> int:
    """Little-endian packed BCD -> int."""
    return sum(((b >> 4) * 10 + (b & 15)) * 100**i for i, b in enumerate(data))


def to_bcd(n: int, nbytes: int) -> bytes:
    return bytes(((n // 100**i % 100 // 10) << 4) | (n // 100**i % 10) for i in range(nbytes))


def const(name: str) -> int:
    return CONST[name]


def bit(e: Emu, name: str, index: int) -> bool:
    return bool(u8(e, name, index >> 3) & (1 << (index & 7)))


# --- location ---

def room(e: Emu) -> tuple[int, int]:
    return u8(e, "wActiveGroup"), u8(e, "wActiveRoom")


def link_px(e: Emu) -> tuple[int, int]:
    """Link's (y, x) in pixels, room coordinates."""
    return u8(e, "w1Link.yh"), u8(e, "w1Link.xh")


def link_tile(e: Emu) -> tuple[int, int]:
    y, x = link_px(e)
    return y >> 4, x >> 4


def dungeon(e: Emu) -> int:
    return u8(e, "wDungeonIndex")


def is_past(e: Emu) -> bool:
    return bool(u8(e, "wTilesetFlags") & 0x80)


# --- inventory and progress ---

def has(e: Emu, treasure: str) -> bool:
    if not treasure.startswith("TREASURE_"):
        treasure = "TREASURE_" + treasure
    return bit(e, "wObtainedTreasureFlags", CONST[treasure])


def gflag(e: Emu, flag: str) -> bool:
    if not flag.startswith("GLOBALFLAG_"):
        flag = "GLOBALFLAG_" + flag
    return bit(e, "wGlobalFlags", CONST[flag])


def room_flags(e: Emu, group: int, rm: int) -> int:
    return e.u8(ROOM_FLAG_BASE[group] + rm)


def room_flag(e: Emu, group: int, rm: int, mask: int) -> bool:
    return bool(room_flags(e, group, rm) & mask)


def essences(e: Emu) -> int:
    return bin(u8(e, "wEssencesObtained")).count("1")


def rupees(e: Emu) -> int:
    return bcd(read(e, "wNumRupees", 2))


def health(e: Emu) -> tuple[int, int]:
    """(current, max) in quarter hearts."""
    return u8(e, "wLinkHealth"), u8(e, "wLinkMaxHealth")


def equipped(e: Emu) -> tuple[int, int]:
    """(B item, A item) as ITEM_* ids."""
    return u8(e, "wInventoryB"), u8(e, "wInventoryA")


def name(e: Emu, var: str = "wLinkName") -> str:
    return read(e, var, 5).split(b"\0")[0].decode("latin-1")


# --- UI state ---

def text_active(e: Emu) -> bool:
    return u8(e, "wTextIsActive") != 0


def text_index(e: Emu) -> int:
    """Index of the most recently shown text (group << 8 | index), as in the TX_xxxx names."""
    lo, hi = read(e, "wTextIndex", 2)
    return hi << 8 | lo


def text(e: Emu) -> str:
    return TEXT.get(f"{text_index(e):04x}", "?")


def option_prompt(e: Emu) -> bool:
    return text_active(e) and u8(e, "wTextDisplayMode") == 1


def menu_open(e: Emu) -> bool:
    return u8(e, "wOpenedMenuType") != 0


def controllable(e: Emu) -> bool:
    """Link can be moved by the player right now."""
    return (
        u8(e, "wGameState") == 2
        and u8(e, "wCutsceneIndex") == 1
        and not text_active(e)
        and not menu_open(e)
        and u8(e, "wScrollMode") & 0x0E == 0
        and u8(e, "wPaletteThread_mode") == 0
        and u8(e, "wDisabledObjects") & 0x81 == 0
        and u8(e, "w1Link.state") == 1
        # Link's object becomes LINK_CUTSCENE during scripted scenes; riding an animal is still player control.
        and u8(e, "w1Link.id") in (CONST["SPECIALOBJECT_LINK"], CONST["SPECIALOBJECT_LINK_RIDING_ANIMAL"])
    )


# --- objects ---

@dataclass
class Obj:
    kind: str
    slot: int  # page $d0-$df
    id: int
    subid: int
    state: int
    y: int
    x: int
    health: int
    visible: bool
    rad_y: int
    rad_x: int
    enabled: int

    def __str__(self) -> str:
        vis = "" if self.visible else " hidden"
        return f"{self.kind}@{self.slot:02x} id={self.id:02x}:{self.subid:02x} st={self.state} y={self.y} x={self.x} hp={self.health}{vis}"


def objects(e: Emu, kind: str) -> list[Obj]:
    off = OBJECT_KINDS[kind]
    out = []
    for page in range(0xD0, 0xE0):
        base = (page << 8) + off
        raw = e.read(base, 0x40, bank=1)
        if raw[OBJ["enabled"]]:
            out.append(Obj(kind, page, raw[OBJ["id"]], raw[OBJ["subid"]], raw[OBJ["state"]],
                           raw[OBJ["yh"]], raw[OBJ["xh"]], raw[OBJ["health"]], bool(raw[OBJ["visible"]] & 0x80),
                           # Radii are 0 until an NPC's script runs initcollisions; 6 is the usual value.
                           raw[OBJ["collisionRadiusY"]] or 6, raw[OBJ["collisionRadiusX"]] or 6, raw[OBJ["enabled"]]))
    return out


def summary(e: Emu) -> str:
    g, r = room(e)
    y, x = link_px(e)
    hp, hmax = health(e)
    owned = [k[9:] for k, v in TREASURES.items() if v and bit(e, "wObtainedTreasureFlags", v)]
    lines = [
        f"frame {e.frame}  room {g}:{r:02x}  link y={y} x={x} dir={u8(e, 'w1Link.direction')} state={u8(e, 'w1Link.state')}"
        f"  dungeon={dungeon(e):02x} past={is_past(e)}",
        f"hearts {hp / 4:g}/{hmax / 4:g}  rupees {rupees(e)}  essences {essences(e)}  B/A={equipped(e)}",
        f"gamestate={u8(e, 'wGameState')} cutscene={u8(e, 'wCutsceneIndex')} text={u8(e, 'wTextIsActive')}"
        f" menu={u8(e, 'wOpenedMenuType')} scroll={u8(e, 'wScrollMode')} controllable={controllable(e)}",
        "owned: " + " ".join(owned),
    ]
    if text_active(e):
        lines.append(f"text TX_{text_index(e):04x}: " + text(e).replace("\n", " / "))
    for kind in ("interaction", "enemy"):
        objs = objects(e, kind)
        if objs:
            lines.append(f"{kind}s: " + "; ".join(map(str, objs)))
    return "\n".join(lines)
