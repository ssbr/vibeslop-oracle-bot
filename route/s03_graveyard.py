"""Seed Satchel -> Yoll Graveyard: the hidden grave's two lamps drop the Graveyard Key -> gate -> D1 entrance."""

from oracle_bot import act, ram
from oracle_bot.runner import Route

R = Route()


@R.step(done=lambda e: ram.has(e, "GRAVEYARD_KEY"),
        note="burn the bottom tree in 0:8d; light both lamps inside (wNumTorchesLit == 2) and the key drops")
def graveyard_key(e):
    act.travel_to(e, 0x8D)  # burning bushes on the way
    act.burn(e, (6, 1))
    act.enter(e, (6, 1), "down")
    act.burn(e, (3, 3))
    act.burn(e, (3, 11))
    act.wait_until(e, lambda e: any(o.id == act.INTERAC_TREASURE for o in ram.objects(e, "interaction")), 300,
                   "key to drop")
    act.pickup(e)
    act.enter(e, (9, 1), "down")


@R.step(done=lambda e: ram.room_flag(e, 0, 0x5C, 0x80), note="the gate north of the graveyard stairs")
def open_graveyard_gate(e):
    act.travel_to(e, 0x5C)
    act.unlock(e, (4, 4), "up")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.room(e) == (0, 0x8D) and ram.link_px(e)[0] < 80)
def to_spirits_grave(e):
    act.travel(e, 0x5D, 0x6D, 0x7D, 0x8D)
    act.walk_to(e, (72, 100))  # in front of the stairs up to the entrance


R.mark("03_before_d1", release=True)
