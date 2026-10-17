"""Overworld room graph from surveyed collision maps, for travelling between screens.

data/world.json: {group: {room: {"edges": {dir: [[component, lo, hi], ...]}, "comp": [[y, x, component], ...]}}}
Edge spans are ranges of Link's x (up/down edges) or y (left/right edges) from which he can walk off that
edge; components are connected areas within the room (built by tools/survey.py with sword-breakables passable).
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
ALLOW = frozenset({"sword"})


def components(cl: nav.Clearance) -> dict[tuple[int, int], int]:
    """Label connected components of lattice nodes under Link's movement rules."""
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
                for dy, dx in ((-nav.STEP, 0), (nav.STEP, 0), (0, -nav.STEP), (0, nav.STEP)):
                    p = (y + dy, x + dx)
                    if p not in comp and cl.can_move((y, x), p):
                        comp[p] = n
                        queue.append(p)
            n += 1
    return comp


def describe_room(g: nav.Grid) -> dict:
    cl = nav.clearance(g, ALLOW)
    H, W = cl.ok.shape
    comp = components(cl)
    edges = {}
    for d in OPPOSITE:
        test = nav.edge_zone(d, H, W)
        spans: dict[int, list[int]] = {}
        for (y, x), c in comp.items():
            if test(y, x):
                spans.setdefault(c, []).append(x if d in ("up", "down") else y)
        edges[d] = [[c, min(v), max(v)] for c, v in sorted(spans.items())]
    # Keep one sample node per 8x8 cell: enough to tell which component Link is standing in.
    sample = [[y, x, c] for (y, x), c in comp.items() if y % 8 == 4 and x % 8 == 4]
    return {"edges": edges, "comp": sample}


_WORLD: dict | None = None


def world() -> dict:
    global _WORLD
    if _WORLD is None:
        _WORLD = json.loads(PATH.read_text()) if PATH.exists() else {}
    return _WORLD


def component_at(group: int, room: int, y: int, x: int) -> int | None:
    info = world().get(str(group), {}).get(str(room))
    if not info:
        return None
    best = min(info["comp"], key=lambda n: abs(n[0] - y) + abs(n[1] - x), default=None)
    return best[2] if best else None


def route(group: int, room: int, comp: int | None, target: int) -> list[tuple[str, int, int]] | None:
    """Shortest list of (direction, lo, hi) hops from (room, comp) to `target` room."""
    rooms = world().get(str(group), {})
    starts = [(room, comp)] if comp is not None else [(room, c) for c in {s[0] for d in rooms[str(room)]["edges"].values() for s in d}]
    prev: dict[tuple[int, int], tuple[tuple[int, int], tuple[str, int, int]] | None] = {s: None for s in starts}
    queue = deque(starts)
    while queue:
        r, c = queue.popleft()
        if r == target:
            hops = []
            node = (r, c)
            while prev[node] is not None:
                node, hop = prev[node]
                hops.append(hop)
            return hops[::-1]
        for d, spans in rooms.get(str(r), {"edges": {}})["edges"].items():
            nr = r + DELTA[d]
            if not 0 <= nr < 256 or (d in ("left", "right") and nr >> 4 != r >> 4) or str(nr) not in rooms:
                continue
            for sc, lo, hi in spans:
                if sc != c:
                    continue
                for nc, nlo, nhi in rooms[str(nr)]["edges"][OPPOSITE[d]]:
                    a, b = max(lo, nlo), min(hi, nhi)
                    if a <= b and (nr, nc) not in prev:
                        prev[(nr, nc)] = ((r, c), (d, a, b))
                        queue.append((nr, nc))
    return None


def plan_to(e: Emu, target: int) -> list[tuple[str, int, int]]:
    group, room = ram.room(e)
    y, x = ram.link_px(e)
    hops = route(group, room, component_at(group, room, y, x), target)
    if hops is None:
        raise KeyError(f"no surveyed route from {group}:{room:02x} to {group}:{target:02x}")
    return hops
