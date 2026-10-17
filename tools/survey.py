"""Dev-only map survey: warp a throwaway emulator to every room of a group and record what it looks like.

Usage: uv run python tools/survey.py <snapshot> <group> [--tiers N,M] [rooms...]   (rooms as hex, default all 256)
--tiers recomputes only those ability tiers (world.TIERS indices) and keeps the others: surveys show the world
as it is in the snapshot, so older tiers are best left as surveyed from snapshots of their time.
Writes runs/survey/g<group>.txt (ASCII map per room), g<group>_<room>.png screenshots, g<group>_map.png
(stitched overview), and updates oracle_bot/data/world.json (the room graph used by world.travel_to).
The snapshot must be in normal gameplay. Nothing here touches real runs: warps are `dev` writes.
"""

import json
import sys
from pathlib import Path

from PIL import Image

from oracle_bot import nav, ram, world
from oracle_bot.emu import ROOT, load_snapshot

OUT = ROOT / "runs" / "survey"


def warp(e, group: int, room: int, pos: int = 0x55) -> bool:
    ram.poke(e, "wWarpDestGroup", 0x80 | group, "dev")
    ram.poke(e, "wWarpDestRoom", room, "dev")
    ram.poke(e, "wWarpTransition", 0, "dev")
    ram.poke(e, "wWarpDestPos", pos, "dev")
    ram.poke(e, "wWarpTransition2", 1, "dev")
    for _ in range(300):
        e.step()
        if ram.room(e) == (group, room) and ram.u8(e, "wGameState") == 2 and ram.u8(e, "wScrollMode") & 0x0E == 0:
            e.step(30)
            return True
    return False


def main() -> int:
    args = sys.argv[1:]
    tiers = None
    if "--tiers" in args:
        i = args.index("--tiers")
        tiers = range(0) if not args[i + 1] else [int(t) for t in args[i + 1].split(",")]
        del args[i:i + 2]
    snap, group = Path(args[0]), int(args[1])
    rooms = [int(r, 16) for r in args[2:]] or list(range(256))
    OUT.mkdir(parents=True, exist_ok=True)
    base = load_snapshot(snap.with_suffix(""))
    state = (base.state(), base.frame, len(base.log.ops))
    graph = json.loads(world.PATH.read_text()) if world.PATH.exists() else {}
    described = graph.setdefault(str(group), {})
    lines = []
    for room in rooms:
        base.load(*state)
        if not warp(base, group, room):
            lines.append(f"== {group}:{room:02x} (warp failed)")
            continue
        g = nav.grid(base)
        if ram.u8(base, "wActiveCollisions") == 0:  # overworld screens only
            described[str(room)] = world.describe_room(g, tiers, described.get(str(room)))
        lines.append(f"== {group}:{room:02x}  tileset flags {ram.u8(base, 'wTilesetFlags'):02x}")
        lines.append(nav.ascii(base, g))
        Image.fromarray(base.screen()).save(OUT / f"g{group}_{room:02x}.png")
    (OUT / f"g{group}.txt").write_text("\n".join(lines), encoding="utf-8")
    world.PATH.write_text(json.dumps(graph, separators=(",", ":")))
    print(stitch(group))
    return 0


def stitch(group: int, scale: float = 0.5) -> Path:
    """Combine g<group>_<room>.png screenshots (play area only) into one overworld map image."""
    tiles = {int(p.stem.split("_")[1], 16): Image.open(p) for p in OUT.glob(f"g{group}_??.png")}
    rows = max(r >> 4 for r in tiles) + 1
    cols = max(r & 15 for r in tiles) + 1
    big = Image.new("RGB", (cols * 160, rows * 128))
    for room, img in tiles.items():
        big.paste(img.crop((0, 16, 160, 144)), ((room & 15) * 160, (room >> 4) * 128))
    big = big.resize((int(big.width * scale), int(big.height * scale)))
    path = OUT / f"g{group}_map.png"
    big.save(path)
    return path


if __name__ == "__main__":
    sys.exit(main())
