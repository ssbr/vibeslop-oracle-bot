"""Room-level navigation: collision grid from RAM, A* for Link's position, ASCII rendering."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np

from . import ram
from .emu import Emu

_TILES = ram._DATA["tiles"]

# Link's tile-collision box relative to (yh, xh), inclusive. Measured by walking into walls.
BOX_Y = (-2, 6)
BOX_X = (-4, 3)
STEP = 4  # lattice spacing (px) for planning

TILETYPE = {v: k[9:] for k, v in ram.CONST.items() if k.startswith("TILETYPE_") and not k.startswith("TILETYPE_SS")}
HAZARDS = {"HOLE", "WARPHOLE", "WATER", "LAVA", "SEAWATER", "WHIRLPOOL"}
SWORD_SOURCES = {1, 2}  # BREAKABLETILESOURCE_SWORD_L1/L2


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

    def quarter_solid(self) -> np.ndarray:
        """(2h, 2w) bool: quarter-tile solidity from collision bytes alone."""
        q = np.zeros((2 * self.h, 2 * self.w), bool)
        for r in range(self.h):
            for c in range(self.w):
                v = int(self.collision[r, c])
                if v == 0:
                    continue
                if v >= 0x10:
                    q[2 * r:2 * r + 2, 2 * c:2 * c + 2] = True
                    continue
                q[2 * r, 2 * c] = bool(v & 8)
                q[2 * r, 2 * c + 1] = bool(v & 4)
                q[2 * r + 1, 2 * c] = bool(v & 2)
                q[2 * r + 1, 2 * c + 1] = bool(v & 1)
        return q


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
            elif t in breakable and v:
                k = "break:" + ",".join(map(str, breakable[t]))
            elif t in inter and v:
                k = "interact:" + str(inter[t] & 15)
            elif ttype == "STAIRS":
                k = "stairs"
            elif v == 0:
                k = "free"
            elif v == 0x0F or v >= 0x10:
                k = "solid"
            else:
                k = "partial"
            row.append(k)
        g.kind.append(row)
    return g


def blocked_pixels(g: Grid, allow: frozenset[str] = frozenset()) -> np.ndarray:
    """(16h, 16w) bool: pixels Link's box may not overlap."""
    q = g.quarter_solid()
    for r in range(g.h):
        for c in range(g.w):
            k = g.kind[r][c]
            if k.startswith("hazard:"):
                q[2 * r:2 * r + 2, 2 * c:2 * c + 2] = k[7:] not in allow
            elif k.startswith("break:") and passable_break(k, allow):
                q[2 * r:2 * r + 2, 2 * c:2 * c + 2] = False
            elif k == "warp" and "warp" not in allow:
                q[2 * r:2 * r + 2, 2 * c:2 * c + 2] = True
    return np.kron(q, np.ones((8, 8), bool))


def passable_break(kind: str, allow: frozenset[str]) -> bool:
    sources = {int(s) for s in kind[6:].split(",")}
    return ("sword" in allow and bool(sources & SWORD_SOURCES)) or ("bracelet" in allow and 0 in sources)


def link_positions(g: Grid, allow: frozenset[str] = frozenset(),
                   blockers: list[tuple[int, int, int, int]] = ()) -> np.ndarray:
    """(16h, 16w) bool: Link-center positions where his box overlaps no blocked pixel.
    `blockers` are solid objects (y, x, ry, rx): Link can't get within |dy| < ry and |dx| < rx of them,
    where ry/rx are the sums of both objects' collision radii (preventObjectHFromPassingObjectD)."""
    px = blocked_pixels(g, allow)
    H, W = px.shape
    pad = np.ones((H + 16, W + 16), bool)  # outside the room counts as blocked
    pad[8:8 + H, 8:8 + W] = px
    s = np.zeros((H + 17, W + 17), np.int32)
    s[1:, 1:] = pad.cumsum(0).cumsum(1)
    ys, xs = np.mgrid[0:H, 0:W]
    y0, y1 = ys + BOX_Y[0] + 8, ys + BOX_Y[1] + 8 + 1
    x0, x1 = xs + BOX_X[0] + 8, xs + BOX_X[1] + 8 + 1
    count = s[y1, x1] - s[y0, x1] - s[y1, x0] + s[y0, x0]
    ok = count == 0
    for by, bx, ry, rx in blockers:
        ok[max(0, by - ry + 1):max(0, by + ry), max(0, bx - rx + 1):max(0, bx + rx)] = False
    return ok


def path(g: Grid, start: tuple[int, int], goal, allow: frozenset[str] = frozenset(),
         avoid: list[tuple[int, int, int]] = (), blockers: list[tuple[int, int, int, int]] = ()) -> list[tuple[int, int]] | None:
    """A* over Link-center positions on a STEP lattice. `goal(y, x) -> bool` or a (y, x) target.
    `avoid` = [(y, x, radius)] areas with extra cost (enemies); `blockers` = solid NPC centers.
    Returns lattice waypoints after the start."""
    ok = link_positions(g, allow, blockers)
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
    starts = [p for p in starts if 0 <= p[0] < H and 0 <= p[1] < W and ok[p]] or [(sy, sx)]

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
        for dy, dx in ((-STEP, 0), (STEP, 0), (0, -STEP), (0, STEP), (-STEP, -STEP), (-STEP, STEP), (STEP, -STEP), (STEP, STEP)):
            n = (y + dy, x + dx)
            if not (0 <= n[0] < H and 0 <= n[1] < W and ok[n]):
                continue
            if dy and dx and not (ok[y + dy, x] and ok[y, x + dx]):
                continue
            nc = c + (math.sqrt(2) if dy and dx else 1.0) + extra(*n)
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
        ry, rx = o.rad_y + ly, o.rad_x + lx
        # Objects with enabled bit 7 (followers like Impa, effects like floating notes) aren't solid, and
        # neither is anything Link already overlaps.
        if o.visible and not o.enabled & 0x80 and not (abs(o.y - y) < ry and abs(o.x - x) < rx):
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
