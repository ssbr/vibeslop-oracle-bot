"""Overworld room graph from surveyed collision maps, for travelling between screens.

data/world.json: {group: {room: [tier, ...]}} with one entry per ability tier (TIERS), each
{"edges": {dir: [[component, lo, hi], ...]}, "comp": [[y, x, component], ...]}.
Edge spans are ranges of Link's x (up/down edges) or y (left/right edges) from which he can walk off that
edge; components are connected areas within the room given that tier's abilities (built by tools/survey.py).
Ledges and warps aren't edges here: routes handle those explicitly.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np

from . import nav, ram
from .emu import Emu

PATH = Path(__file__).parent / "data" / "world.json"
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
DELTA = {"up": -16, "down": 16, "left": -1, "right": 1}
# Ability sets the graph is computed for, in the order Link gets them. Routing uses the largest tier Link has.
TIERS = [frozenset({"sword"}), frozenset({"sword", "shovel"}), frozenset({"sword", "shovel", "ember"}),
         frozenset({"sword", "shovel", "ember", "bracelet"}),
         frozenset({"sword", "shovel", "ember", "bracelet", "feather"})]


def components(cl: nav.Clearance, hops: dict | None = None) -> dict[tuple[int, int], int]:
    """Label connected components of lattice nodes under Link's movement rules (plus feather `hops`, see
    nav.hop_table)."""
    ok = cl.ok
    H, W = ok.shape
    comp: dict[tuple[int, int], int] = {}
    n = 0
    for y0 in range(0, H, nav.STEP):
        for x0 in range(0, W, nav.STEP):
            if not ok[y0, x0] or (y0, x0) in comp:
                continue
            comp[(y0, x0)] = n
            queue = deque([(y0, x0)])
            while queue:
                y, x = queue.popleft()
                steps = [(y + dy, x + dx) for dy, dx in ((-nav.STEP, 0), (nav.STEP, 0), (0, -nav.STEP), (0, nav.STEP))
                         if cl.can_move((y, x), (y + dy, x + dx))]
                if hops is not None:
                    steps += nav.hops(hops, (y, x))  # (hops are two-way: there's always one back)
                for p in steps:
                    if p not in comp:
                        comp[p] = n
                        queue.append(p)
            n += 1
    return comp


def describe_room(g: nav.Grid, tiers: range | None = None, old: list[dict] | None = None) -> list[dict]:
    """All tiers' descriptions; with `tiers`, only those are (re)computed and the rest kept from `old`."""
    tiers = range(len(TIERS)) if tiers is None else tiers
    old = old or []
    return [describe_tier(g, TIERS[i]) if i in tiers or i >= len(old) else old[i] for i in range(len(TIERS))]


def describe_tier(g: nav.Grid, allow: frozenset[str]) -> dict:
    cl = nav.clearance(g, allow)
    H, W = cl.ok.shape
    hops = nav.hop_table(cl, nav.clearance(g, allow | nav.JUMPABLE)) if "feather" in allow else None
    comp = components(cl, hops)
    edges = {}
    for d in OPPOSITE:
        test = nav.edge_zone(d, H, W)
        spans: dict[int, list[int]] = {}
        for (y, x), c in comp.items():
            if test(y, x):
                spans.setdefault(c, []).append(x if d in ("up", "down") else y)
        edges[d] = [[c, min(v), max(v)] for c, v in sorted(spans.items())]
    jumps = sorted({(comp[a], comp[b]) for a, bs in nav.ledges(g, cl).items() for b in bs
                    if a in comp and b in comp and comp[a] != comp[b]})
    # Keep one sample node per tile: enough to tell which component Link is standing in.
    sample = [[y, x, c] for (y, x), c in comp.items() if y % 16 == 8 and x % 16 == 8]
    return {"edges": edges, "comp": sample, "ledges": [list(j) for j in jumps]}


_WORLD: dict | None = None


def world() -> dict:
    global _WORLD
    if _WORLD is None:
        _WORLD = json.loads(PATH.read_text()) if PATH.exists() else {}
    return _WORLD


def tier_for(allow: frozenset[str]) -> int:
    return max(i for i, t in enumerate(TIERS) if t <= allow | {"sword"})


def tiers_to_try(allow: frozenset[str]) -> list[int]:
    """The surveyed tier Link fully qualifies for, then (the tiers are nested, but items can be lost again:
    Crescent Island's thieves, the Tokay trading hut) the smallest one covering everything he can do, which
    may route through something he can't do any more (travel_to bans such hops and replans)."""
    exact = tier_for(allow)
    covering = next(i for i, t in enumerate(TIERS) if t >= allow & TIERS[-1])
    return [exact] if covering <= exact else [exact, covering]


def rooms_for(group: int, tier: int) -> dict[str, dict]:
    return {r: tiers[tier] for r, tiers in world().get(str(group), {}).items()}


def components_near(rooms: dict[str, dict], room: int, y: int, x: int, reach: int = 24) -> list[int]:
    """Components of `room` with a sample node near (y, x), nearest first. Link can stand where no sample is
    (doorways, between tiles), so the nearest one alone can be an isolated scrap."""
    info = rooms.get(str(room))
    if not info:
        return []
    out = []
    for n in sorted(info["comp"], key=lambda n: abs(n[0] - y) + abs(n[1] - x)):
        if out and abs(n[0] - y) + abs(n[1] - x) > reach:
            break
        if n[2] not in out:
            out.append(n[2])
    return out


def component_at(rooms: dict[str, dict], room: int, y: int, x: int) -> int | None:
    near = components_near(rooms, room, y, x)
    return near[0] if near else None


# Fairies' Woods (present): until GLOBALFLAG_FOREST_UNSCRAMBLED, leaving these rooms goes where this table
# says (screenTransitionForestScrambler, code/bank1.s), indexed [room][up, right, down, left]; 0 = normal.
_SCRAMBLER = [0x00, 0x71, 0x90, 0x00, 0x00, 0x82, 0x91, 0x80, 0x00, 0x00, 0x92, 0x82,
              0x72, 0x82, 0x80, 0x00, 0x80, 0x82, 0x82, 0x71, 0x70, 0x71, 0x82, 0x71,
              0x81, 0x92, 0x00, 0x00, 0x72, 0x91, 0x00, 0x92, 0x82, 0x00, 0x00, 0x92]
FOREST_SCRAMBLE = {(room, d): _SCRAMBLER[i * 4 + j]
                   for i, room in enumerate((0x70, 0x71, 0x72, 0x80, 0x81, 0x82, 0x90, 0x91, 0x92))
                   for j, d in enumerate(("up", "right", "down", "left")) if _SCRAMBLER[i * 4 + j]}


def neighbor(r: int, d: str, scramble: dict[tuple[int, int], int] | None = None) -> int | None:
    """The room reached by leaving room `r` toward `d` (None: off the map)."""
    if scramble and (r, d) in scramble:
        return scramble[(r, d)]
    nr = r + DELTA[d]
    if not 0 <= nr < 256 or (d in ("left", "right") and nr >> 4 != r >> 4):
        return None
    return nr


def route(rooms: dict[str, dict], room: int, comp: int | None, target: int,
          scramble: dict[tuple[int, int], int] | None = None, target_comp: int | None = None,
          banned: frozenset[tuple[int, str, int, int]] = frozenset()) -> list[tuple[str, int, int, int]] | None:
    """Shortest list of (direction, lo, hi, next room) hops from (room, comp) to `target` room (to its
    component `target_comp`, if given), avoiding `banned` (room, direction, lo, hi) hops."""
    starts = [(room, comp)] if comp is not None else [(room, c) for c in {s[0] for d in rooms[str(room)]["edges"].values() for s in d}]
    prev: dict[tuple[int, int], tuple[tuple[int, int], tuple[str, int, int, int]] | None] = {s: None for s in starts}
    queue = deque(starts)
    while queue:
        r, c = queue.popleft()
        if r == target and target_comp in (None, c):
            hops = []
            node = (r, c)
            while prev[node] is not None:
                node, hop = prev[node]
                hops.append(hop)
            return hops[::-1]
        info = rooms.get(str(r), {"edges": {}})
        for a, b in info.get("ledges", ()):
            if a == c and (r, b) not in prev:
                prev[(r, b)] = ((r, c), ("ledge", b, b, r))
                queue.append((r, b))
        for d, spans in info["edges"].items():
            nr = neighbor(r, d, scramble)
            if nr is None or str(nr) not in rooms:
                continue
            for sc, lo, hi in spans:
                if sc != c:
                    continue
                for nc, nlo, nhi in rooms[str(nr)]["edges"][OPPOSITE[d]]:
                    a, b = max(lo, nlo), min(hi, nhi)
                    if a <= b and (nr, nc) not in prev and (r, d, a, b) not in banned:
                        prev[(nr, nc)] = ((r, c), (d, a, b, nr))
                        queue.append((nr, nc))
    return None


def plan_to(e: Emu, target: int, allow: frozenset[str], at: tuple[int, int] | None = None,
            banned: frozenset[tuple[int, str, int, int]] = frozenset()) -> list[tuple[str, int, int, int]]:
    """Hops to room `target` (to the part of it containing pixel `at`, if given); [] if already there.
    `banned` hops (room, direction, lo, hi) turned out impassable (the surveys show the world as it was then:
    a gate open since may still be shut)."""
    group, room = ram.room(e)
    y, x = ram.link_px(e)
    scramble = FOREST_SCRAMBLE if group == 0 and not ram.gflag(e, "FOREST_UNSCRAMBLED") else None
    for tier in tiers_to_try(allow):
        rooms = rooms_for(group, tier)
        target_comp = component_at(rooms, target, *at) if at else None
        for comp in components_near(rooms, room, y, x) or [None]:
            hops = route(rooms, room, comp, target, scramble, target_comp, banned)
            if hops is not None:
                return hops
    raise KeyError(f"no surveyed route from {group}:{room:02x} to {group}:{target:02x}")
