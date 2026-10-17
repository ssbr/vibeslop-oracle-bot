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
