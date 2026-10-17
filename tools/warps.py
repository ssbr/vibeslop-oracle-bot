"""Dev helper: list a map group's warp sources (doors, stairs, caves) and where they lead, from the disassembly.

Usage: uv run python tools/warps.py <group> [room-lo room-hi]   (rooms as hex)
Prints "<group>:<room> <where> -> <dest group>:<dest room> (dest pos ..)"; "any" means a whole-screen warp
(whichever warp tile Link touches), "tile YX" a specific metatile, "edgeN" a screen-edge corner warp.
"""

import re
import sys
from pathlib import Path

DATA = Path(__file__).parent.parent / "vendor" / "oracles-disasm" / "data" / "ages"


def destinations() -> dict[int, list[tuple[int, str]]]:
    """group -> [(room, dest pos), ...] indexed by warp destination index."""
    out: dict[int, list[tuple[int, str]]] = {}
    group = None
    for line in (DATA / "warpDestinations.s").read_text().splitlines():
        if m := re.match(r"group(\d)WarpDestTable:", line):
            group = int(m.group(1))
            out[group] = []
        elif (m := re.match(r"\s*m_WarpDest \$(\w+) (\S+)", line)) and group is not None:
            out[group].append((int(m.group(1), 16), m.group(2)))
    return out


def labelled_blocks() -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    label = None
    for line in (DATA / "warpSources.s").read_text().splitlines():
        if m := re.match(r"^(\w+):", line):
            label = m.group(1)
            blocks[label] = []
        elif label:
            blocks[label].append(line.strip())
    return blocks


def warps(group: int):
    dests, blocks = destinations(), labelled_blocks()
    for line in blocks[f"group{group}WarpSources"]:
        if m := re.match(r"m_StandardWarp \$(\w) \$(\w\w) \$(\w\w) \$(\w) \$(\w)", line):
            corner = m.group(1)
            yield int(m.group(2), 16), "any" if corner == "0" else f"edge{corner}", int(m.group(3), 16), int(m.group(4), 16)
        elif m := re.match(r"m_PointerWarp\s+\$(\w\w) (\w+)", line):
            for entry in blocks[m.group(2)]:
                if mm := re.match(r"m_PositionWarp \$(\w\w) \$(\w\w) \$(\w) \$(\w)", entry):
                    yield int(m.group(1), 16), f"tile {mm.group(1)}", int(mm.group(2), 16), int(mm.group(3), 16)


def main() -> int:
    group = int(sys.argv[1])
    lo, hi = (int(a, 16) for a in sys.argv[2:4]) if len(sys.argv) >= 4 else (0, 0xFF)
    dests = destinations()
    for room, where, index, dgroup in warps(group):
        if lo <= room <= hi:
            droom, dpos = dests[dgroup][index]
            print(f"{group}:{room:02x} {where} -> {dgroup}:{droom:02x} (dest pos {dpos})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
