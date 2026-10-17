"""Sword -> Lynna City -> Maku Path (present) -> Ralph's portal -> Black Tower Shovel -> Maku Road entrance."""

from oracle_bot import act, ram
from oracle_bot.runner import Route

R = Route()

INTERAC_MAKU_TREE = 0x87
INTERAC_HARDHAT_WORKER = 0x58  # subid 2 guards the Black Tower path, subid 0 (var03 0) hands out the Shovel


@R.step(done=lambda e: ram.u8(e, "wMakuTreeState") >= 1,
        note="Lynna City, through the Maku Path door; the Maku Tree vanishes when Link arrives")
def maku_tree_vanishes(e):
    act.travel_to(e, 0x48)
    act.enter(e, (2, 1), "up")  # Maku Path door (present)
    act.travel(e, "up", "up", "up")
    act.enter(e, (0, 7), "up")  # stairs up to the Maku Tree's grove (0:38)
    act.play_until(e, lambda e: ram.u8(e, "wMakuTreeState") >= 1, what="Maku Tree disappears")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.is_past(e), note="east of the grove Ralph jumps into Veran's portal; follow him")
def follow_ralph(e):
    act.exit_room(e, "right", expect=(0, 0x39))
    act.play_until(e, lambda e: ram.gflag(e, "RALPH_ENTERED_PORTAL"), what="Ralph enters the portal")
    act.settle(e, quiet=30)
    act.walk_to(e, (40, 40), leave_ok=True, stop_on_scene=True)  # the portal, above the ledge
    act.wait_until(e, ram.is_past, 300, "time warp")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.has(e, "SHOVEL"), note="Black Tower: the worker at the gate moves aside after talking")
def get_shovel(e):
    act.travel_to(e, 0x86)
    act.talk(e, INTERAC_HARDHAT_WORKER, 0x02, quiet=60)
    act.travel_to(e, 0x76)
    act.enter(e, (4, 4), "up")  # tower doorway
    act.travel(e, "right", "up", "left")  # rubble blocks the direct way north
    act.talk(e, INTERAC_HARDHAT_WORKER, 0x00, quiet=60)


@R.step(done=lambda e: ram.room(e) == (1, 0x48) and not ram.room_flag(e, 1, 0x48, 0), note="dig back out and walk to the village entrance")
def to_maku_road(e):
    act.travel(e, "down", "down")  # digging through the rubble on the way out
    act.travel_to(e, 0x48)
    act.walk_to(e, (72, 24))  # digs the dirt in front of the Maku Road entrance at (2, 1)
    act.walk_to(e, (104, 72))  # checkpoint spot: a save made on the dug tiles respawns Link out of bounds


R.mark("01_before_maku_path", release=True, expect=lambda e: ram.room(e) == (1, 0x48))

