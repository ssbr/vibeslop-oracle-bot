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
