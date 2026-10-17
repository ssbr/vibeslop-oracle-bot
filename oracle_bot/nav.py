"""Room-level navigation: collision grid from RAM, A* for Link's position, ASCII rendering."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from collections import deque

import numpy as np

from . import ram
from .emu import Emu

_TILES = ram._DATA["tiles"]

# Link's wall checks relative to (yh, xh), inclusive pixel ranges (calculateAdjacentWallsBitset in
# object_code/common/specialObjects/link.s): moving vertically he needs columns x-3..x+2 clear over rows
# y-2..y+6; moving horizontally, rows y..y+5 clear over columns x-4..x+3.
V_BOX = ((-2, 6), (-3, 2))
H_BOX = ((0, 5), (-4, 3))
BOX_Y = (-2, 6)  # overall extent, for "which tiles does Link touch"
BOX_X = (-4, 3)
STEP = 4  # lattice spacing (px) for planning

TILETYPE = {v: k[9:] for k, v in ram.CONST.items() if k.startswith("TILETYPE_") and not k.startswith("TILETYPE_SS")}
HAZARDS = {"HOLE", "WARPHOLE", "WATER", "LAVA", "SEAWATER", "WHIRLPOOL"}
# Abilities -> BREAKABLETILESOURCE_* values they provide (constants/common/breakableTileSources.s).
BREAK_SOURCES = {"bracelet": {0}, "sword": {1}, "sword2": {1, 2}, "bombs": {4}, "shovel": {6}, "ember": {12}}


def table(name: str, mode: int) -> dict[int, int]:
    return {int(k): v for k, v in _TILES[name][str(mode)].items()}


@dataclass
class Grid:
    h: int  # metatile rows
    w: int
    mode: int  # wActiveCollisions
    collision: np.ndarray  # (h, w)
    tiles: np.ndarray  # (h, w) metatile ids
    kind: list[list[str]] = field(default_factory=list)  # per metatile: free/solid/partial/hazard:X/break/cliff/warp/...

    def pixel_solid(self) -> np.ndarray:
        """(16h, 16w) bool: solidity from collision bytes, at pixel resolution (as Link's collision sees it)."""
        px = np.zeros((16 * self.h, 16 * self.w), bool)
        for r in range(self.h):
            for c in range(self.w):
                px[16 * r:16 * r + 16, 16 * c:16 * c + 16] = tile_mask(int(self.collision[r, c]))
        return px


# Special collision values $10-$1f: an 8-bit mask over 2-pixel columns (values $10-$17) or rows ($18-$1f).
# This is the table Link's collision uses (@specialCollisions under checkTileCollision_allowHoles, bank0.s).
SPECIAL_MASKS = [0b00000000, 0b11000011, 0b00000011, 0b11000000, 0b00000000, 0b11000011, 0b11000011, 0b00000000,
                 0b00000000, 0b11000011, 0b00000011, 0b11000000, 0b11000000, 0b11000001, 0b11111111, 0b00000000]
_MASK_CACHE: dict[int, np.ndarray] = {}


def tile_mask(v: int) -> np.ndarray:
    """16x16 bool solidity of one metatile with collision value v."""
    m = _MASK_CACHE.get(v)
    if m is not None:
        return m
    m = np.zeros((16, 16), bool)
    if 0 < v < 0x10:  # quarter-tile bits: 8 = top-left, 4 = top-right, 2 = bottom-left, 1 = bottom-right
        m[:8, :8], m[:8, 8:], m[8:, :8], m[8:, 8:] = bool(v & 8), bool(v & 4), bool(v & 2), bool(v & 1)
    elif v >= 0x10:  # the game only looks at the low nibble: $ff (screen boundary) is free, $fe solid
        bits = SPECIAL_MASKS[v & 0x0F]
        solid = np.array([bool(bits & (1 << ((i >> 1) & 7))) for i in range(16)])
        if v & 0x0F < 8:
            m[:, solid] = True
        else:
            m[solid, :] = True
    _MASK_CACHE[v] = m
    return m


def grid(e: Emu) -> Grid:
    large = ram.u8(e, "wRoomIsLarge")
    h, w = (11, 15) if large else (8, 10)
    col = np.frombuffer(ram.read(e, "wRoomCollisions", 0xC0), np.uint8).reshape(12, 16)[:h, :w]
    lay = np.frombuffer(ram.read(e, "wRoomLayout", 0xC0), np.uint8).reshape(12, 16)[:h, :w]
    mode = ram.u8(e, "wActiveCollisions")
    g = Grid(h, w, mode, col.copy(), lay.copy())
    types, cliffs, warps = table("types", mode), table("cliffs", mode), table("warps", mode)
    inter, breakable = table("interactable", mode), table("breakable", mode)
    for r in range(h):
        row = []
        for c in range(w):
            t, v = int(lay[r, c]), int(col[r, c])
            ttype = TILETYPE.get(types.get(t, 0), "NORMAL")
            if t in warps:
                k = "warp"
            elif ttype in HAZARDS:
                k = "hazard:" + ttype.lower()
            elif t in cliffs:
                k = "cliff:" + "urdl"[cliffs[t] // 8]
            elif t in inter and v and inter[t] & 15 in (4, 5):  # chests and signs (A reads/opens them)
                k = "interact:" + str(inter[t] & 15)
            elif t in breakable and v:
                k = "break:" + ",".join(map(str, breakable[t]))
            elif t in inter and v:
                k = "interact:" + str(inter[t] & 15)
            elif ttype == "STAIRS":
                k = "stairs"
            elif v == 0:
                k = "free"
            elif v == 0x18:
                k = "stairs"
            elif 0x10 <= v < 0x20:
                k = "free" if not tile_mask(v).any() else "partial"
            elif v == 0x0F or v >= 0x20:
                k = "solid"
            else:
                k = "partial"
            row.append(k)
        g.kind.append(row)
    return g


def blocked_pixels(g: Grid, allow: frozenset[str] = frozenset(), unblock: frozenset[tuple[int, int]] = frozenset()) -> np.ndarray:
    """(16h, 16w) bool: pixels Link's box may not overlap. `unblock`: warp tiles to treat as floor (the one
    Link arrived on, which won't send him back until he has stepped off it)."""
    px = g.pixel_solid()
    for r in range(g.h):
        for c in range(g.w):
            k = g.kind[r][c]
            if (r, c) in unblock:
                continue
            tile = px[16 * r:16 * r + 16, 16 * c:16 * c + 16]
            if k.startswith("hazard:"):
                tile[:] = k[7:] not in allow
            elif k.startswith("break:") and passable_break(k, allow):
                tile[:] = False
            elif k == "warp" and "warp" not in allow:
                tile[:] = True
    return px


def break_sources(kind: str) -> set[int]:
    return {int(s) for s in kind[6:].split(",")}


def breaker(kind: str, allow: frozenset[str]) -> str | None:
    """The allowed ability that breaks this breakable tile kind, if any (sword preferred)."""
    sources = break_sources(kind)
    for ability in ("sword", "sword2", "shovel", "bracelet", "ember", "bombs"):
        if ability in allow and BREAK_SOURCES[ability] & sources:
            return ability
    return None


def passable_break(kind: str, allow: frozenset[str]) -> bool:
    return breaker(kind, allow) is not None


def _box_free(px: np.ndarray, box: tuple[tuple[int, int], tuple[int, int]]) -> np.ndarray:
    """Centers (y, x) where the pixel box (y+dy0..y+dy1, x+dx0..x+dx1) contains no blocked pixel."""
    (dy0, dy1), (dx0, dx1) = box
    H, W = px.shape
    pad = np.zeros((H + 16, W + 16), bool)  # outside the room is free (screen boundary): edge zones stop Link
    pad[8:8 + H, 8:8 + W] = px
    s = np.zeros((H + 17, W + 17), np.int32)
    s[1:, 1:] = pad.cumsum(0).cumsum(1)
    ys, xs = np.mgrid[0:H, 0:W]
    y0, y1 = ys + dy0 + 8, ys + dy1 + 8 + 1
    x0, x1 = xs + dx0 + 8, xs + dx1 + 8 + 1
    return (s[y1, x1] - s[y0, x1] - s[y1, x0] + s[y0, x0]) == 0


@dataclass
class Clearance:
    """Where Link can move, per axis (his wall checks differ for vertical and horizontal movement)."""

    h: np.ndarray  # (16h, 16w) bool: Link at (y, x) can move left/right
    v: np.ndarray  # can move up/down

    @property
    def ok(self) -> np.ndarray:
        return self.h | self.v

    def can_move(self, p: tuple[int, int], n: tuple[int, int]) -> bool:
        H, W = self.h.shape
        if not (0 <= n[0] < H and 0 <= n[1] < W):
            return False
        dy, dx = n[0] - p[0], n[1] - p[1]
        if dy and dx:
            return all(self.h[q] and self.v[q] for q in (p, n, (n[0], p[1]), (p[0], n[1])))
        grid = self.v if dy else self.h
        return bool(grid[p] and grid[n])


def region(cl: Clearance, start: tuple[int, int], air: Clearance | None = None) -> set[tuple[int, int]]:
    """Lattice nodes Link can walk to from `start` (snapped to the nearest free node); with `air` (see `hops`),
    also hopping gaps with the feather."""
    ok = cl.ok
    H, W = ok.shape
    sy, sx = (int(round(v / STEP) * STEP) for v in start)
    near = sorted((abs(dy) + abs(dx), (sy + dy, sx + dx)) for dy in range(-12, 13, STEP) for dx in range(-12, 13, STEP)
                  if 0 <= sy + dy < H and 0 <= sx + dx < W and ok[sy + dy, sx + dx])
    if not near:
        return set()
    seen = {near[0][1]}
    queue = deque(seen)
    while queue:
        y, x = queue.popleft()
        steps = [n for n in ((y - STEP, x), (y + STEP, x), (y, x - STEP), (y, x + STEP)) if cl.can_move((y, x), n)]
        if air is not None:
            steps += hops(cl, air, (y, x))
        for n in steps:
            if n not in seen:
                seen.add(n)
                queue.append(n)
    return seen


def clearance(g: Grid, allow: frozenset[str] = frozenset(), blockers: list[tuple[int, int, int, int]] = (),
              unblock: frozenset[tuple[int, int]] = frozenset()) -> Clearance:
    """`blockers` are solid objects (y, x, ry, rx): Link can't get within |dy| < ry and |dx| < rx of them,
    where ry/rx are the sums of both objects' collision radii (preventObjectHFromPassingObjectD)."""
    px = blocked_pixels(g, allow, unblock)
    c = Clearance(_box_free(px, H_BOX), _box_free(px, V_BOX))
    for by, bx, ry, rx in blockers:
        for m in (c.h, c.v):
            m[max(0, by - ry + 1):max(0, by + ry), max(0, bx - rx + 1):max(0, bx + rx)] = False
    return c


def edge_zone(direction: str, H: int, W: int):
    """Positions where moving toward `direction` scrolls to the next screen (bank1.s screen transitions:
    y <= 5 / x <= 5, or beyond wScreenTransitionBoundaryY/X = H-7 / W-6)."""
    return {"up": lambda y, x: y <= 5, "down": lambda y, x: y >= H - 6,
            "left": lambda y, x: x <= 5, "right": lambda y, x: x >= W - 5}[direction]


def exclude_edges(cl: Clearance, exits: frozenset[str]) -> None:
    """Keep the planner out of edge zones it isn't meant to leave through."""
    H, W = cl.h.shape
    for d in ("up", "down", "left", "right"):
        if d in exits:
            continue
        zone = {"up": (slice(0, 6), slice(None)), "down": (slice(H - 6, H), slice(None)),
                "left": (slice(None), slice(0, 6)), "right": (slice(None), slice(W - 5, W))}[d]
        cl.h[zone] = False
        cl.v[zone] = False


LEDGE_DIRS = {"u": (-1, 0), "d": (1, 0), "l": (0, -1), "r": (0, 1)}


def ledges(g: Grid, cl: Clearance) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """One-way jumps off cliff tiles: lattice node next to a cliff (facing its jump direction) -> nodes where
    Link can land past it. Jumping happens by walking into the cliff tile."""
    H, W = cl.ok.shape
    out: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for r in range(g.h):
        for c in range(g.w):
            k = g.kind[r][c]
            if not k.startswith("cliff:"):
                continue
            dy, dx = LEDGE_DIRS[k[6]]
            cy, cx = 16 * r + 8, 16 * c + 8  # tile center
            # Approach node: just before the tile, centered on it; landing: first free node past it.
            ay, ax = cy - dy * 16, cx - dx * 16
            ay, ax = ay - ay % STEP, ax - ax % STEP
            if not (0 <= ay < H and 0 <= ax < W and cl.ok[ay, ax]):
                continue
            for dist in range(12, 41, STEP):
                ly, lx = cy + dy * dist, cx + dx * dist
                ly, lx = ly - ly % STEP, lx - lx % STEP
                if not (0 <= ly < H and 0 <= lx < W):
                    break
                if cl.ok[ly, lx]:
                    out.setdefault((ay, ax), []).append((ly, lx))
                    break
    return out


MOVES = ((-STEP, 0), (STEP, 0), (0, -STEP), (0, STEP), (-STEP, -STEP), (-STEP, STEP), (STEP, -STEP), (STEP, STEP))
# Roc's Feather: a running jump carries Link ~31px (measured), over a one-tile hole or stretch of water.
HOP = 32
JUMPABLE = frozenset({"hole", "water", "seawater", "lava"})


def hops(cl: Clearance, air: Clearance, p: tuple[int, int]) -> list[tuple[int, int]]:
    """Feather jumps from lattice node `p`: straight 32px hops that clear a gap (`air` = clearance with the
    gaps' hazards counted as floor) and land on ground with a few pixels to spare."""
    H, W = cl.ok.shape
    y, x = p
    out = []
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        n = (y + dy * HOP, x + dx * HOP)
        short = (y + dy * (HOP - STEP), x + dx * (HOP - STEP))
        if not (0 <= n[0] < H and 0 <= n[1] < W and cl.ok[n] and cl.ok[short]):
            continue
        flight = [(y + dy * d, x + dx * d) for d in range(STEP, HOP, STEP)]
        if all(air.ok[q] for q in flight) and not all(cl.ok[q] for q in flight):
            out.append(n)
    return out


def hop_between(g: Grid, a: tuple[int, int], b: tuple[int, int]) -> bool:
    """The straight segment a -> b passes over a jumpable gap (so it's a feather hop, not a ledge)."""
    (ay, ax), (by, bx) = a, b
    n = max(abs(by - ay), abs(bx - ax)) // STEP
    for i in range(1, n):
        y, x = ay + (by - ay) * i // n, ax + (bx - ax) * i // n
        k = g.kind[y // 16][x // 16] if 0 <= y < g.h * 16 and 0 <= x < g.w * 16 else ""
        if k.startswith("hazard:") and k[7:] in JUMPABLE:
            return True
    return False


def path(g: Grid, start: tuple[int, int], goal, allow: frozenset[str] = frozenset(),
         avoid: list[tuple[int, int, int]] = (), blockers: list[tuple[int, int, int, int]] = (),
         exits: frozenset[str] = frozenset(), unblock: frozenset[tuple[int, int]] = frozenset()
         ) -> list[tuple[int, int]] | None:
    """A* over Link-center positions on a STEP lattice. `goal(y, x) -> bool` or a (y, x) target.
    `avoid` = [(y, x, radius)] areas with extra cost (enemies); `blockers` = solid NPC centers;
    `exits` = screen edges the path may enter (all others are avoided). Returns lattice waypoints."""
    cl = clearance(g, allow, blockers, unblock)
    exclude_edges(cl, exits)
    jumps = ledges(g, cl)
    air = clearance(g, allow | JUMPABLE, blockers, unblock) if "feather" in allow else None
    ok = cl.ok
    H, W = ok.shape
    if callable(goal):
        is_goal, target = goal, None
    else:
        target = goal
        is_goal = lambda y, x: abs(y - target[0]) < STEP and abs(x - target[1]) < STEP  # noqa: E731

    def snap(v: int) -> int:
        return int(round(v / STEP) * STEP)

    sy, sx = snap(start[0]), snap(start[1])
    starts = [(sy + dy, sx + dx) for dy in (0, -STEP, STEP) for dx in (0, -STEP, STEP)]
    starts = [p for p in starts if 0 <= p[0] < H and 0 <= p[1] < W and ok[p]]
    if not starts:
        # Link stands somewhere the planner considers blocked (on the warp he arrived through, against an
        # NPC...): start from the nearest free node instead.
        near = [(abs(dy) + abs(dx), (sy + dy, sx + dx)) for dy in range(-24, 25, STEP) for dx in range(-24, 25, STEP)
                if 0 <= sy + dy < H and 0 <= sx + dx < W and ok[sy + dy, sx + dx]]
        if not near:
            return None
        starts = [min(near)[1]]

    def h(y: int, x: int) -> float:
        if target is None:
            return 0.0
        dy, dx = abs(y - target[0]) / STEP, abs(x - target[1]) / STEP
        return max(dy, dx) + (math.sqrt(2) - 1) * min(dy, dx)

    def extra(y: int, x: int) -> float:
        return sum(4.0 for (ay, ax, rad) in avoid if abs(ay - y) < rad and abs(ax - x) < rad)

    frontier = [(h(*p), 0.0, p) for p in starts]
    heapq.heapify(frontier)
    came: dict[tuple[int, int], tuple[int, int] | None] = {p: None for p in starts}
    cost = {p: 0.0 for p in starts}
    while frontier:
        _, c, p = heapq.heappop(frontier)
        if c > cost[p]:
            continue
        if is_goal(*p):
            out = []
            while p is not None:
                out.append(p)
                p = came[p]
            return out[::-1]
        y, x = p
        steps = [((y + dy, x + dx), math.sqrt(2) if dy and dx else 1.0) for dy, dx in MOVES
                 if cl.can_move(p, (y + dy, x + dx))]
        steps += [(n, 6.0) for n in jumps.get(p, ())]
        if air is not None:
            steps += [(n, 12.0) for n in hops(cl, air, p)]
        for n, step_cost in steps:
            nc = c + step_cost + extra(*n)
            if nc < cost.get(n, math.inf):
                cost[n] = nc
                came[n] = p
                heapq.heappush(frontier, (nc + h(*n), nc, n))
    return None


ASCII = {"free": ".", "solid": "#", "partial": ":", "warp": "D", "stairs": "=", "cliff": "v"}


def blockers(e: Emu) -> list[tuple[int, int, int, int]]:
    """Visible interactions (NPCs, pushable rocks...) as (y, x, ry, rx) exclusion zones for Link's center."""
    ly, lx = ram.u8(e, "w1Link.collisionRadiusY"), ram.u8(e, "w1Link.collisionRadiusX")
    y, x = ram.link_px(e)
    out = []
    for o in ram.objects(e, "interaction"):
        cart = o.id == ram.CONST["INTERAC_MINECART"]
        if cart:  # no radius, but walking into a parked cart boards it
            o.rad_y = o.rad_x = 8
        ry, rx = o.rad_y + ly, o.rad_x + lx
        # Solid NPCs have collision radii (set by their script's initcollisions). Followers that persist
        # across screens (enabled & 3 == 3, like Impa) aren't solid, nor is anything Link already overlaps
        # (except a cart he's standing next to: stepping into it would board it).
        solid = o.visible and (o.rad_y or o.rad_x) and o.enabled & 3 != 3
        if solid and (cart or not (abs(o.y - y) < ry and abs(o.x - x) < rx)):
            out.append((o.y, o.x, ry, rx))
    return out


def ascii(e: Emu, g: Grid | None = None) -> str:
    g = g or grid(e)
    rows = []
    for r in range(g.h):
        line = []
        for c in range(g.w):
            k = g.kind[r][c]
            if k.startswith("hazard:"):
                ch = {"hole": "O", "water": "~", "seawater": "~", "lava": "%"}.get(k[7:], "!")
            elif k.startswith("cliff:"):
                ch = {"u": "^", "r": ">", "d": "v", "l": "<"}[k[6]]
            elif k.startswith("break:"):
                ch = "*"
            elif k.startswith("interact:"):
                ch = {"0": "P", "1": "K", "2": "K", "4": "C", "5": "S"}.get(k[9:], "I")
            else:
                ch = ASCII[k]
            line.append(ch)
        rows.append(line)
    for kind, ch in (("interaction", "N"), ("enemy", "E")):
        for o in ram.objects(e, kind):
            if not o.visible:
                continue
            r, c = o.y // 16, o.x // 16
            if 0 <= r < g.h and 0 <= c < g.w:
                rows[r][c] = ch
    ly, lx = ram.link_px(e)
    if 0 <= ly // 16 < g.h and 0 <= lx // 16 < g.w:
        rows[ly // 16][lx // 16] = "@"
    head = "   " + "".join(f"{c:x}" for c in range(g.w))
    return "\n".join([head] + [f"{r:x}  " + "".join(line) for r, line in enumerate(rows)])
