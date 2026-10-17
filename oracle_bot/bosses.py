"""Boss fights that need more than `act.fight`."""

from __future__ import annotations

from . import act, ram
from .emu import Emu

ENEMY_PUMPKIN_HEAD = ram.CONST["ENEMY_PUMPKIN_HEAD"]


def pumpkin_head(e: Emu, max_frames: int = 20000) -> None:
    """D1: slash the body until it falls apart, pick up the head while it's grabbable (state $12) and throw
    it, then slash the ghost; repeat until the ghost is gone (object_code/ages/enemies/pumpkinHead.s)."""

    def part(subid: int) -> ram.Obj | None:
        return next((o for o in ram.objects(e, "enemy") if o.id == ENEMY_PUMPKIN_HEAD and o.subid == subid), None)

    start = e.frame
    chase = act.Chase()
    while any(o.id == ENEMY_PUMPKIN_HEAD for o in ram.objects(e, "enemy")):
        if e.frame - start > max_frames:
            raise act.Stuck("Pumpkin Head still alive")
        if not ram.controllable(e):
            act.settle(e)
            continue
        body, ghost, head = part(1), part(2), part(3)
        if act.holding(e):
            act.tap(e, act.item_button(e, "BRACELET"), hold=2, after=20)  # throw the head
        elif head and head.state == 0x12:
            try:
                act.grab(e, head)
            except act.Stuck:
                e.step()
        elif ghost and ghost.visible:
            chase.attack(e, ghost)
        elif body and body.visible:
            chase.attack(e, body)
        else:
            e.step()


ENEMY_SWOOP = ram.CONST["ENEMY_SWOOP"]


def swoop(e: Emu, spot: tuple[int, int] = (152, 56), max_frames: int = 20000) -> None:
    """D2 miniboss: it stomps the tile Link stood on when its telegraph counter hit $0a, and stomps break the
    yellow floor. Wait on the blue border, step one tile along it once the stomp is locked in, then slash it
    while it's on the ground (object_code/ages/enemies/swoop.s)."""
    side = (spot[0], spot[1] + 20)
    start = e.frame
    while True:
        boss = next((o for o in ram.objects(e, "enemy") if o.id == ENEMY_SWOOP), None)
        if boss is None:
            return
        if e.frame - start > max_frames:
            raise act.Stuck("Swoop still alive")
        if not ram.controllable(e):
            act.settle(e)
            continue
        y, x = ram.link_px(e)
        sub = ram.field(e, boss, "substate")
        stomping = boss.state == 0x0B
        if stomping and sub >= 2 and boss.z == 0 and abs(boss.y - y) + abs(boss.x - x) <= 28:
            dy, dx = boss.y - y, boss.x - x
            act.slash(e, ("down" if dy > 0 else "up") if abs(dy) > abs(dx) else ("right" if dx > 0 else "left"))
            continue
        locked = stomping and (sub >= 1 or ram.field(e, boss, "counter1") < 0x0A)
        goal = side if locked else spot
        if abs(y - goal[0]) + abs(x - goal[1]) > 2:
            try:
                act.walk_to(e, goal, tol=1, max_frames=60)
            except act.Stuck:
                e.step()
        else:
            e.step()


def to_floor(e: Emu, floor_y: int = 150) -> None:
    """Sidescrolling arena: get Link down to the floor (below `floor_y`) from wherever he is: down a ladder
    (columns x 16-31 / 208-223), or walking toward the middle off ledges and platforms."""
    on_floor = lambda e: ram.link_px(e)[0] > floor_y and ram.u8(e, "wLinkInAir") == 0  # noqa: E731
    for _ in range(6):
        if on_floor(e):
            return
        y, x = ram.link_px(e)
        try:
            if x < 34 or x > 205:
                act.climb(e, 24 if x < 120 else 216, "down", on_floor, attempts=2, max_frames=200)
            else:
                act.hold_until(e, "right" if x < 120 else "left", on_floor, 120, "down to the floor")
        except act.Stuck:
            e.step(10)
    if not on_floor(e):
        raise act.Stuck(f"to_floor: still at {ram.link_px(e)}")


ENEMY_HEAD_THWOMP = ram.CONST["ENEMY_HEAD_THWOMP"]
INTERAC_CIRCULAR_PLATFORM = ram.CONST["INTERAC_CIRCULAR_SIDESCROLL_PLATFORM"]
RED_FACE = 6  # Enemy.direction: faces are 0 green, 2 blue, 4 purple, 6 red (odd = turning)


def head_thwomp(e: Emu, max_frames: int = 200000) -> None:
    """D2 boss (side view). Its head turns through four faces; a bomb dropped into the notch on top of its head
    ((80,120) +-12) makes it spin and settle on the face it showed when the bomb went in, and only the red face
    takes damage. Three platforms circle the head clockwise; ride one, hold a bomb overhead and throw it (it
    goes up and falls straight down) as the platform crosses above the notch, at a frame from which the bomb
    goes in on the red face (object_code/ages/enemies/headThwomp.s)."""

    def boss() -> ram.Obj | None:
        return next((o for o in ram.objects(e, "enemy") if o.id == ENEMY_HEAD_THWOMP), None)

    def platforms() -> list[ram.Obj]:
        return [o for o in ram.objects(e, "interaction") if o.id == INTERAC_CIRCULAR_PLATFORM]

    def riding() -> bool:
        y, x = ram.link_px(e)
        return ram.u8(e, "wLinkInAir") == 0 and any(abs(p.x - x) <= 13 and abs(p.y - 15 - y) <= 3 for p in platforms())

    def board() -> None:
        """Get to the right-hand middle ledge (via the low ledge and the right ladder), then jump left onto a
        platform coming down past it."""
        y, x = ram.link_px(e)
        on_ledge = lambda e: 176 <= ram.link_px(e)[1] < 208 and 85 <= ram.link_px(e)[0] <= 92  # noqa: E731
        if not on_ledge(e) and x < 208:
            to_floor(e)
            act.hold_until(e, "right", lambda e: ram.link_px(e)[1] >= 186, 300, "to the low ledge")
            act.jump(e, "right")
            act.hold_until(e, "right", lambda e: ram.link_px(e)[1] >= 214, 60, "to the right ladder")
        if not on_ledge(e):
            y = ram.link_px(e)[0]
            act.climb(e, 216, "up" if y > 89 else "down", lambda e: 87 <= ram.link_px(e)[0] <= 90)
            act.hold_until(e, "left", lambda e: ram.link_px(e)[1] <= 200 and ram.u8(e, "wLinkInAir") == 0, 60,
                           "onto the ledge")

        def takeoff(e: Emu) -> None:
            button = act.ready(e, "FEATHER")
            e.set_buttons(act.mask_of(f"{button}+left"))
            e.step(2)
            e.set_buttons(act.mask_of("left"))

        def landed(e: Emu) -> bool:
            if ram.u8(e, "wLinkInAir"):
                return False
            e.set_buttons(0)
            return riding()

        coming = lambda e: any(48 <= p.y <= 108 and p.x >= 150 for p in platforms())  # noqa: E731
        act.wait_until(e, coming, 600, "a platform coming down on the right")
        if not act.lookahead(e, takeoff, landed, 60, coming):
            e.step(30)

    start = e.frame
    act.hold_until(e, "up", lambda e: ram.link_px(e)[0] <= 155, 120, "into the arena")  # starts the fight
    while (b := boss()) is not None and b.health not in (0, 0xFF):
        if e.frame - start > max_frames:
            raise act.Stuck("Head Thwomp still alive")
        if not ram.controllable(e):
            act.settle(e)
            continue
        if not riding():
            if act.holding(e):
                act.tap(e, act.ready(e, "BOMB"), hold=3, after=20)  # get rid of it to climb
            board()
            continue
        if not act.holding(e):
            act.use(e, "BOMB", after=2)
            for _ in range(40):  # (if Link gets knocked off meanwhile, the loop starts over)
                if act.holding(e):
                    break
                e.step()
            continue
        health = b.health

        def throw(e: Emu) -> None:
            act.tap(e, act.ready(e, "BOMB"), hold=3, after=0)

        def red_hit(e: Emu) -> bool:
            o = boss()
            return o is not None and o.state == 0x0A and ram.field(e, o, "var31") == RED_FACE

        # The bomb comes down at Link's x; it goes in within 12px of x=120.
        over_notch = lambda e: ram.link_px(e)[0] < 30 and 108 <= ram.link_px(e)[1] <= 132  # noqa: E731
        if over_notch(e) and act.lookahead(e, throw, red_hit, 60, over_notch):
            act.wait_until(e, lambda e: boss() is None or boss().health != health, 1200, "the red face to take it")
        else:
            e.step()
