"""Low-level action primitives. All of them drive the emulator closed-loop and raise Stuck on failure."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from . import nav, ram, world
from .emu import Emu, mask_of


class Stuck(Exception):
    pass


def tap(e: Emu, buttons: str, hold: int = 2, after: int = 4) -> None:
    e.set_buttons(mask_of(buttons))
    e.step(hold)
    e.set_buttons(0)
    e.step(after)


def hold(e: Emu, buttons: str, frames: int) -> None:
    e.set_buttons(mask_of(buttons))
    e.step(frames)
    e.set_buttons(0)


def wait_until(e: Emu, pred: Callable[[Emu], bool], max_frames: int, what: str = "condition") -> int:
    """Step (holding whatever is held) until pred(e). Returns frames waited."""
    for n in range(max_frames):
        if pred(e):
            return n
        e.step()
    if pred(e):
        return max_frames
    raise Stuck(f"timed out after {max_frames} frames waiting for {what}")


def settle(e: Emu, choices: Sequence[int] = (), max_frames: int = 60 * 60 * 5, quiet: int = 1) -> None:
    """Advance text/cutscenes until Link has been controllable for `quiet` consecutive frames. Option prompts
    consume `choices` in order; an option prompt with no choice left raises Stuck (blindly accepting the
    default is never safe)."""
    choices = list(choices)
    start = e.frame
    calm = 0
    while calm < quiet:
        if ram.u8(e, "wLinkDeathTrigger") or ram.u8(e, "w1Link.state") == ram.CONST["LINK_STATE_DYING"]:
            raise Stuck("Link died")
        if ram.controllable(e):
            calm += 1
            e.step()
            continue
        calm = 0
        if e.frame - start > max_frames:
            raise Stuck(f"settle: not controllable after {max_frames} frames\n{ram.summary(e)}")
        if ram.option_prompt(e) and text_done(e):
            if not choices:
                raise Stuck(f"settle: unexpected option prompt (text {ram.u8(e, 'wTextIndex'):02x})")
            choose_option(e, choices.pop(0))
        elif ram.text_active(e):
            tap(e, "a", hold=1, after=3)
        else:
            e.step()
    if choices:
        raise Stuck(f"settle: {len(choices)} unused choices")


DIRS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def steer(dy: int, dx: int) -> str:
    """Buttons that move Link by (dy, dx)."""
    parts = []
    if dy:
        parts.append("down" if dy > 0 else "up")
    if dx:
        parts.append("right" if dx > 0 else "left")
    return "+".join(parts)


def abilities(e: Emu) -> frozenset[str]:
    """What Link can currently get past: used as the default `allow` for navigation."""
    out = set()
    if ram.has(e, "SWORD"):
        out.add("sword2" if ram.u8(e, "wSwordLevel") >= 2 else "sword")
    if ram.has(e, "BRACELET"):
        out.add("bracelet")
    if ram.has(e, "SHOVEL"):
        out.add("shovel")
    if ram.has(e, "SEED_SATCHEL") and ram.has(e, "EMBER_SEEDS") and ram.u8(e, "wNumEmberSeeds"):
        out.add("ember")
    return frozenset(out)


def equip(e: Emu, item: str, button: str = "a") -> None:
    """Put ITEM_* `item` on `button` by swapping it with the inventory slot holding it (a logged RAM write;
    the saved bytes are the same as equipping through the menu)."""
    want = ram.CONST["ITEM_" + item]
    var = {"a": "wInventoryA", "b": "wInventoryB"}[button]
    if ram.u8(e, var) == want:
        return
    other = {"a": "wInventoryB", "b": "wInventoryA"}[button]
    if ram.u8(e, other) == want:  # on the other button: swap the two buttons
        ram.poke(e, other, ram.u8(e, var), "equip")
    else:
        storage = ram.read(e, "wInventoryStorage", 16)
        if want not in storage:
            raise Stuck(f"{item} isn't in the inventory")
        ram.poke(e, "wInventoryStorage", ram.u8(e, var), "equip", off=storage.index(want))
    ram.poke(e, var, want, "equip")
    ram.poke(e, "wStatusBarNeedsRefresh", ram.u8(e, "wStatusBarNeedsRefresh") | 1, "equip")
    e.step(2)


def item_button(e: Emu, item: str) -> str | None:
    """'a' or 'b' if the ITEM_* `item` is equipped there."""
    b, a = ram.equipped(e)
    want = ram.CONST["ITEM_" + item]
    return "b" if b == want else "a" if a == want else None


def use(e: Emu, item: str, direction: str | None = None, after: int = 14) -> None:
    """Face `direction` (if given) and use ITEM_* `item` (equipping it on A if it isn't on a button)."""
    button = item_button(e, item)
    if button is None:
        equip(e, item, "a")
        button = "a"
    if direction:
        face(e, direction)
    tap(e, button, hold=2, after=after)


def slash(e: Emu, direction: str) -> None:
    use(e, "SWORD", direction)


def box_tiles(y: int, x: int) -> set[tuple[int, int]]:
    """Metatiles overlapped by Link's tile-collision box at (y, x)."""

    return {(r, c) for r in range((y + nav.BOX_Y[0]) // 16, (y + nav.BOX_Y[1]) // 16 + 1)
            for c in range((x + nav.BOX_X[0]) // 16, (x + nav.BOX_X[1]) // 16 + 1)}


def break_first_obstacle(e: Emu, g, plan: list[tuple[int, int]], allow: frozenset[str]) -> bool:
    """`plan` crosses breakable tiles: break the first one along it that can be reached, return True (caller
    replans). Tiles the path touches at the same time are tried nearest-first."""
    tried = set()
    errors = []
    for i, (y, x) in enumerate(plan):
        hits = sorted((abs(r * 16 + 8 - y) + abs(c * 16 + 8 - x), (r, c)) for r, c in box_tiles(y, x)
                      if 0 <= r < g.h and 0 <= c < g.w and (r, c) not in tried
                      and g.kind[r][c].startswith("break:") and nav.breaker(g.kind[r][c], allow))
        for _, (r, c) in hits:
            tried.add((r, c))
            how = nav.breaker(g.kind[r][c], allow)
            before = ram.read(e, "wRoomLayout", 0xC0)
            try:
                if how in ("sword", "sword2"):
                    direction = strike_at(e, (r, c), "SWORD", SWORD_OFFSETS, allow - BREAKERS)
                elif how == "shovel":
                    direction = strike_at(e, (r, c), "SHOVEL", SHOVEL_OFFSETS, allow - BREAKERS, after=24)
                elif how == "ember":
                    select_seeds(e, "EMBER")
                    direction = strike_at(e, (r, c), "SEED_SATCHEL", SEED_OFFSETS, allow - BREAKERS, after=4,
                                          wait=wait_seeds_done)
                else:
                    raise Stuck(f"breaking tiles with {how} isn't implemented")
            except Stuck as err:
                errors.append(f"{(r, c)}: {str(err).splitlines()[0]}")
                continue
            e.step(10)
            if ram.read(e, "wRoomLayout", 0xC0) == before:
                raise Stuck(f"couldn't break tile {(r, c)} ({g.kind[r][c]}) with {how} facing {direction}")
            return True
        if len(tried) >= 4:
            break
    if errors:
        raise Stuck("couldn't break anything on the path: " + "; ".join(errors))
    return False


# Where items hit tiles relative to Link, by facing direction: the shovel's dig point
# (itemParents/shovelParent.s) and the end of a sword slash (items/commonCode2.s, tryBreakTileWithSword).
SHOVEL_OFFSETS = {"up": (-8, 0), "right": (4, 6), "down": (7, 0), "left": (4, -7)}
SWORD_OFFSETS = {"up": (-14, 0), "right": (0, 13), "down": (13, 0), "left": (0, -14)}
# A satchel seed is thrown forward and bursts on whatever it hits: standing right next to a tile works.
SEED_OFFSETS = {"up": (-12, 0), "right": (0, 10), "down": (11, 0), "left": (0, -11)}
SEEDS = ("EMBER", "SCENT", "PEGASUS", "GALE", "MYSTERY")


def select_seeds(e: Emu, seed: str) -> None:
    """Choose which seeds the satchel uses (a logged write, like picking them in the menu)."""
    index = SEEDS.index(seed)
    if ram.u8(e, "wSatchelSelectedSeeds") != index:
        ram.poke(e, "wSatchelSelectedSeeds", index, "equip")


def strike_at(e: Emu, tile: tuple[int, int], item: str, offsets: dict[str, tuple[int, int]],
              allow: frozenset[str] | None = None, after: int = 14,
              wait: Callable[[Emu], None] | None = None) -> str:
    """Stand where using `item` hits metatile `tile`, use it until the tile changes, and return the facing
    direction used. Spots lined up with the tile's center are preferred; `wait` runs after each use (e.g. for
    an ember to burn out) before checking the tile."""
    r, c = tile
    g = nav.grid(e)
    ok = nav.clearance(g, frozenset(allow or ()) - BREAKERS, nav.blockers(e)).ok
    y0, x0 = ram.link_px(e)
    spots = []
    for d, (oy, ox) in offsets.items():
        for y in range(16 * r - oy, 16 * r - oy + 16):
            for x in range(16 * c - ox, 16 * c - ox + 16):
                if 0 <= y < ok.shape[0] and 0 <= x < ok.shape[1] and ok[y, x]:
                    # Off-center along the axis perpendicular to the throw/swing makes misses likelier.
                    off = abs(x + ox - (16 * c + 8)) if d in ("up", "down") else abs(y + oy - (16 * r + 8))
                    spots.append((abs(y - y0) + abs(x - x0) + 8 * off, d, y, x))
    before = ram.u8(e, "wRoomLayout", r * 16 + c)
    errors = []
    for _, d, y, x in sorted(spots)[:6]:
        try:
            walk_to(e, (y, x), allow, tol=0)
        except Stuck as err:
            errors.append(f"{d}: {str(err).splitlines()[0]}")
            continue
        use(e, item, d, after=after)
        if wait:
            wait(e)
        e.step(6)
        if ram.u8(e, "wRoomLayout", r * 16 + c) != before:
            return d
        errors.append(f"{d} from {(y, x)}: no effect")
    raise Stuck(f"couldn't hit {tile} with {item}: {errors}")


BREAKERS = frozenset({"sword", "sword2", "bracelet", "shovel", "ember"})


def walk_to(e: Emu, goal, allow: frozenset[str] | None = None, tol: int = 1, max_frames: int = 1800,
            settle_text: bool = True, leave_ok: bool = False, stop_on_scene: bool = False,
            exits: frozenset[str] = frozenset()) -> None:
    """Walk Link to `goal`: a (y, x) pixel target or a predicate goal(y, x). Plans with nav.path and follows
    the path closed-loop, replanning when progress stalls. Leaves buttons released.
    stop_on_scene: return as soon as a scripted scene takes control (the walk was only meant to trigger it)."""

    allow = abilities(e) if allow is None else allow
    target = None if callable(goal) else goal
    reached = goal if callable(goal) else (lambda y, x: abs(y - target[0]) <= tol and abs(x - target[1]) <= tol)
    start_room = ram.room(e)
    deadline = e.frame + max_frames
    plan: list[tuple[int, int]] = []
    # Stall detection: Link can jitter in place against an NPC, so compare against where he was a while ago.
    anchor, anchor_frame = None, e.frame
    replans = 0
    no_path_waits = 0
    try:
        while True:
            if e.frame > deadline:
                raise Stuck(f"walk_to {goal}: out of time at {ram.link_px(e)}")
            if not ram.controllable(e):
                e.set_buttons(0)
                if stop_on_scene:
                    return
                if ram.text_active(e) and not settle_text:
                    raise Stuck("walk_to: text appeared")
                if ram.text_active(e):
                    settle(e)
                else:
                    e.step()
                continue
            if ram.room(e) != start_room:
                if leave_ok:
                    return
                raise Stuck(f"walk_to: left room {start_room} -> {ram.room(e)}")
            pos = ram.link_px(e)
            if reached(*pos):
                return
            if anchor is None or abs(pos[0] - anchor[0]) + abs(pos[1] - anchor[1]) >= 4:
                anchor, anchor_frame = pos, e.frame
            stalled = e.frame - anchor_frame > 16
            if not plan or stalled:
                g = nav.grid(e)
                avoid = [(o.y, o.x, 12) for o in ram.objects(e, "enemy")]
                plan = route_plan(e, g, pos, goal, allow, avoid, exits)
                if plan and allow & BREAKERS and break_first_obstacle(e, g, plan, allow):
                    plan = []
                    deadline = e.frame + max_frames  # breaking something is progress
                    continue
                if not plan:
                    # Doors may still be opening (or NPCs moving): give the room a moment before giving up.
                    if no_path_waits < 4:
                        no_path_waits += 1
                        e.step(30)
                        continue
                    raise Stuck(f"walk_to: no path from {pos} to {goal}\n{nav.ascii(e, g)}")
                if stalled:
                    replans += 1
                    anchor, anchor_frame = pos, e.frame
                if replans > 6:
                    raise Stuck(f"walk_to: no progress at {pos}\n{nav.ascii(e, g)}")
            # drop reached waypoints; steer toward the next one (or the exact target at the end)
            while len(plan) > 1 and abs(plan[0][0] - pos[0]) <= 2 and abs(plan[0][1] - pos[1]) <= 2:
                plan.pop(0)
            wy, wx = plan[0]
            if len(plan) == 1 and target is not None:
                wy, wx = target
            dy, dx = wy - pos[0], wx - pos[1]
            if max(abs(dy), abs(dx)) > 2 * nav.STEP + 2:  # a ledge jump: walk straight into the cliff
                dy, dx = (dy, 0) if abs(dy) > abs(dx) else (0, dx)
            e.set_buttons(_mask(steer(dy, dx)))
            e.step()
            if len(plan) == 1 and pos == (wy, wx) and target is None:
                plan = []
    finally:
        e.set_buttons(0)


def route_plan(e: Emu, g, pos, goal, allow: frozenset[str], avoid, exits: frozenset[str]) -> list[tuple[int, int]]:
    """Prefer a path that breaks nothing; NPCs move (and some follow Link), so if they wall him in, plan
    without them."""

    for a in (allow - BREAKERS, allow):
        for blockers in (nav.blockers(e), ()):
            plan = nav.path(g, pos, goal, a, avoid, blockers, exits)
            if plan:
                return plan
    return []


def _mask(buttons: str) -> int:
    return mask_of(buttons)


def exit_room(e: Emu, direction: str, allow: frozenset[str] | None = None, expect: tuple[int, int] | None = None,
              max_frames: int = 1800, span: tuple[int, int] | None = None) -> None:
    """Walk off the screen edge in `direction` and wait for the next room to become controllable.
    `span` limits where along the edge to leave (x range for up/down, y range for left/right)."""

    g = nav.grid(e)
    edge = nav.edge_zone(direction, g.h * 16, g.w * 16)
    lo, hi = span or (0, 255)
    along = 1 if direction in ("up", "down") else 0

    def near(y: int, x: int) -> bool:
        return edge(y, x) and lo <= (y, x)[along] <= hi

    before = ram.room(e)
    walk_to(e, near, allow, max_frames=max_frames, leave_ok=True, exits=frozenset({direction}))
    if ram.room(e) == before:
        e.set_buttons(mask_of(direction))
        try:
            wait_until(e, lambda e: ram.room(e) != before, 120, f"room change going {direction}")
        finally:
            e.set_buttons(0)
    settle(e)
    if expect is not None and ram.room(e) != expect:
        raise Stuck(f"exit {direction}: expected room {expect}, got {ram.room(e)}")


def travel_to(e: Emu, room: int, allow: frozenset[str] | None = None) -> None:
    """Walk across overworld screens to `room` (same group), routing over the surveyed room graph."""

    allow = abilities(e) if allow is None else allow
    hops = world.plan_to(e, room, allow)
    for i, (direction, lo, hi) in enumerate(hops):
        group, rm = ram.room(e)
        if direction == "ledge":
            # Jump down into component `lo` of this room: walk toward the next exit; the planner takes the ledge.
            continue
        exit_room(e, direction, allow, expect=(group, rm + world.DELTA[direction]), span=(lo, hi))


def travel(e: Emu, *hops: int | str, allow: frozenset[str] | None = None) -> None:
    """Cross overworld screen edges. Each hop is a direction or an adjacent room index in the current group."""
    for hop in hops:
        group, rm = ram.room(e)
        if isinstance(hop, str):
            exit_room(e, hop, allow)
            continue
        delta = hop - rm
        direction = {-16: "up", 16: "down", -1: "left", 1: "right"}.get(delta)
        if direction is None:
            raise ValueError(f"room {hop:02x} isn't adjacent to {rm:02x}")
        exit_room(e, direction, allow, expect=(group, hop))


def enter(e: Emu, tile: tuple[int, int], direction: str = "up", max_frames: int = 600) -> None:
    """Walk into the warp (door, stairs, cave) at metatile `tile` moving in `direction`, and wait until the
    destination room is controllable."""
    r, c = tile
    dy, dx = DIRS[direction]
    # Stand on the tile before the door, centered on the door's axis.
    ty, tx = (r - dy) * 16 + 8 - 2, (c - dx) * 16 + 8
    before = ram.room(e)
    walk_to(e, lambda y, x: abs(y - ty) <= 4 and abs(x - tx) <= 2 if dy else abs(y - ty) <= 2 and abs(x - tx) <= 4,
            leave_ok=True)
    if ram.room(e) == before:
        e.set_buttons(mask_of(direction))
        try:
            wait_until(e, lambda e: ram.room(e) != before, max_frames, f"warp at {tile}")
        finally:
            e.set_buttons(0)
    settle(e)


def find(e: Emu, kind: str, obj_id: int, subid: int | None = None) -> ram.Obj:
    objs = [o for o in ram.objects(e, kind) if o.id == obj_id and (subid is None or o.subid == subid)]
    if not objs:
        raise Stuck(f"no {kind} {obj_id:02x}:{subid} in room {ram.room(e)}")
    return objs[0]


def face(e: Emu, direction: str) -> None:
    """Turn Link without (meaningfully) moving: a 1-frame tap."""
    tap(e, direction, hold=1, after=2)


def approach(e: Emu, obj: ram.Obj, sides: str = "durl", allow: frozenset[str] | None = None) -> str:
    """Walk next to `obj` on one of `sides` (d = below it, u = above, l = left, r = right) and face it.
    Returns the side Link ended up on."""
    ly, lx = ram.u8(e, "w1Link.collisionRadiusY"), ram.u8(e, "w1Link.collisionRadiusX")
    # Radii are 0 until an NPC's script runs initcollisions (a frame or two after the room loads); 6 is usual.
    ory, orx = obj.rad_y or 6, obj.rad_x or 6
    ry, rx = ory + ly, orx + lx
    oy, ox = obj.y, obj.x
    # In contact with the object's collision box (Link can't get closer than ry/rx), lined up with it on the
    # other axis so the A button check hits it.
    ay, ax = max(ory - 1, 3), max(orx - 1, 3)
    spots = {
        "d": (lambda y, x: oy + ry - 3 <= y <= oy + ry + 1 and abs(x - ox) <= ax, "up"),
        "u": (lambda y, x: oy - ry - 1 <= y <= oy - ry + 3 and abs(x - ox) <= ax, "down"),
        "l": (lambda y, x: abs(y - oy) <= ay and ox - rx - 1 <= x <= ox - rx + 3, "right"),
        "r": (lambda y, x: abs(y - oy) <= ay and ox + rx - 3 <= x <= ox + rx + 1, "left"),
    }
    errors = []
    for side in sides:
        goal, facing = spots[side]
        try:
            walk_to(e, goal, allow)
        except Stuck as err:
            errors.append(f"{side}: {str(err).splitlines()[0]}")
            continue
        face(e, facing)
        return side
    raise Stuck(f"can't reach {obj}: " + "; ".join(errors))


def talk(e: Emu, obj_id: int, subid: int | None = None, choices: Sequence[int] = (), sides: str = "durl",
         quiet: int = 1) -> None:
    """Talk to an interaction (NPC) and advance its text, answering prompts with `choices`."""
    approach(e, find(e, "interaction", obj_id, subid), sides)
    tap(e, "a", hold=1, after=4)
    wait_until(e, lambda e: not ram.controllable(e), 30, "NPC to respond")
    settle(e, choices, quiet=quiet)


def play_until(e: Emu, pred: Callable[[Emu], bool], max_frames: int = 60 * 60 * 5, choices: Sequence[int] = (),
               what: str = "scene") -> None:
    """Let a scripted scene play (advancing text, answering prompts with `choices`) until pred(e)."""
    choices = list(choices)
    start = e.frame
    while not pred(e):
        if e.frame - start > max_frames:
            raise Stuck(f"play_until {what}: timed out\n{ram.summary(e)}")
        if ram.option_prompt(e) and text_done(e):
            if not choices:
                raise Stuck(f"play_until {what}: unexpected option prompt TX_{ram.text_index(e):04x}")
            choose_option(e, choices.pop(0))
        elif ram.text_active(e):
            tap(e, "a", hold=1, after=3)
        else:
            e.step()


OPPOSITE = {"up": "d", "down": "u", "left": "r", "right": "l"}


def push_object(e: Emu, obj_id: int, direction: str, max_frames: int = 120) -> None:
    """Push an interaction (e.g. a stone) one step in `direction`."""
    obj = find(e, "interaction", obj_id)
    approach(e, obj, OPPOSITE[direction])
    y0, x0 = obj.y, obj.x
    e.set_buttons(mask_of(direction))
    try:
        wait_until(e, lambda e: (lambda o: abs(o.y - y0) + abs(o.x - x0) >= 12)(find(e, "interaction", obj_id)),
                   max_frames, f"push {obj_id:02x} {direction}")
    finally:
        e.set_buttons(0)


def text_done(e: Emu) -> bool:
    """The current textbox has finished printing (waiting for input)."""
    return ram.u8(e, "w7TextStatus") & 0x80 != 0 or ram.option_prompt(e)


def choose_option(e: Emu, index: int) -> None:
    """Answer the open option prompt (0 = first option, e.g. Yes)."""
    # The prompt ignores input until it's fully shown, which is when the cursor gets a position.
    wait_until(e, lambda e: ram.u8(e, "w7SelectedTextPosition") != 0, 600, "option prompt to be ready")
    for _ in range(8):
        cur = ram.u8(e, "w7SelectedTextOption")
        if cur == index:
            break
        tap(e, "right" if cur < index else "left", hold=2, after=8)
    else:
        raise Stuck(f"could not select option {index}")
    tap(e, "a", hold=2, after=8)


# Where Link stands to push a block at metatile (r, c) in each direction: touching it, centered on it.
def push_spot(r: int, c: int, direction: str) -> tuple[int, int]:
    return {"up": (16 * r + 18, 16 * c + 8), "down": (16 * r - 7, 16 * c + 8),
            "right": (16 * r + 5, 16 * c - 4), "left": (16 * r + 5, 16 * c + 20)}[direction]


def push_tile(e: Emu, tile: tuple[int, int], direction: str, max_frames: int = 90) -> None:
    """Push the block at metatile `tile` one step in `direction` and wait for it to land."""
    r, c = tile
    walk_to(e, push_spot(r, c, direction), tol=1)

    def sliding(e: Emu) -> bool:
        return any(o.id == INTERAC_PUSHBLOCK for o in ram.objects(e, "interaction"))

    # The block becomes an INTERAC_PUSHBLOCK while it slides; keep pushing until it has landed (letting go
    # early cancels the push).
    e.set_buttons(mask_of(direction))
    try:
        wait_until(e, sliding, max_frames, f"block at {tile} to move {direction}")
        wait_until(e, lambda e: not sliding(e), 120, f"block from {tile} to land")
    finally:
        e.set_buttons(0)
    settle(e)


INTERAC_PUSHBLOCK = 0x14


def fight(e: Emu, max_frames: int = 60 * 60, done: Callable[[Emu], bool] | None = None) -> None:
    """Attack the nearest enemy with the sword until none remain (or `done`)."""
    done = done or (lambda e: not [o for o in ram.objects(e, "enemy") if o.visible])
    start = e.frame
    while not done(e):
        if e.frame - start > max_frames:
            raise Stuck(f"fight: enemies remain after {max_frames} frames: {ram.objects(e, 'enemy')}")
        if not ram.controllable(e):
            settle(e)
            continue
        y, x = ram.link_px(e)
        foes = [o for o in ram.objects(e, "enemy") if o.visible]
        if not foes:
            e.step()
            continue
        foe = min(foes, key=lambda o: abs(o.y - y) + abs(o.x - x))
        dy, dx = foe.y - y, foe.x - x
        if abs(dy) + abs(dx) <= 18 and min(abs(dy), abs(dx)) <= 8:
            slash(e, ("down" if dy > 0 else "up") if abs(dy) > abs(dx) else ("right" if dx > 0 else "left"))
            continue
        # Line up with the enemy on whichever axis is closer, then close in.
        try:
            walk_to(e, lambda py, px, foe=foe: abs(py - foe.y) + abs(px - foe.x) <= 16
                    and min(abs(py - foe.y), abs(px - foe.x)) <= 6, max_frames=40)
        except Stuck:
            e.step(4)


def open_chest(e: Emu, tile: tuple[int, int], max_frames: int = 600) -> None:
    """Open the chest at metatile `tile` from below and collect its contents."""
    r, c = tile
    before = ram.read(e, "wRoomLayout", 0xC0)[r * 16 + c]
    walk_to(e, (16 * r + 18, 16 * c + 8), tol=1)
    face(e, "up")
    tap(e, "a", hold=2, after=10)
    wait_until(e, lambda e: ram.read(e, "wRoomLayout", 0xC0)[r * 16 + c] != before or ram.text_active(e),
               max_frames, f"chest at {tile} to open")
    settle(e, quiet=30)


def unlock(e: Emu, tile: tuple[int, int], direction: str, max_frames: int = 120) -> None:
    """Walk into the key door / key block at `tile` (moving `direction`) until it opens."""
    r, c = tile
    before = ram.u8(e, "wRoomLayout", r * 16 + c)
    walk_to(e, push_spot(r, c, direction), tol=1)
    e.set_buttons(mask_of(direction))
    try:
        wait_until(e, lambda e: ram.u8(e, "wRoomLayout", r * 16 + c) != before, max_frames, f"door at {tile} to open")
    finally:
        e.set_buttons(0)
    settle(e, quiet=20)


INTERAC_TREASURE = 0x60


def pickup(e: Emu, obj_id: int = INTERAC_TREASURE, max_frames: int = 600) -> None:
    """Walk onto an item lying on the ground (an interaction) and collect it."""
    obj = find(e, "interaction", obj_id)
    walk_to(e, (obj.y, obj.x), tol=3, stop_on_scene=True, max_frames=max_frames)
    settle(e, quiet=30)


def burn(e: Emu, tile: tuple[int, int]) -> None:
    """Burn the tree/bush (or light the torch) at metatile `tile` with an Ember Seed from the satchel."""
    select_seeds(e, "EMBER")
    strike_at(e, tile, "SEED_SATCHEL", SEED_OFFSETS, after=4, wait=wait_seeds_done)
    settle(e)


def wait_seeds_done(e: Emu, max_frames: int = 300) -> None:
    """Wait until no seed items (ITEM_EMBER_SEED..ITEM_MYSTERY_SEED) are active: embers break tiles when
    they finish burning."""
    lo, hi = ram.CONST["ITEM_EMBER_SEED"], ram.CONST["ITEM_MYSTERY_SEED"]
    wait_until(e, lambda e: not any(lo <= o.id <= hi for o in ram.objects(e, "item")), max_frames, "seed to burn out")
