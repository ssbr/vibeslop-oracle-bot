"""D2 -> D3: the doctor money for Bipin & Blossom's baby, then Crescent Island (to be continued: Cheval, Moosh and
the flippers, Rafton's raft, Ricky's gloves, Tingle's chart, the Tokay item hunt, Wild Tokay)."""

from oracle_bot import act, cheats, ram
from oracle_bot.config import DONATIONS
from oracle_bot.runner import Route

from .common import CFG

R = Route()


@R.step(done=lambda e: ram.gflag(e, "TALKED_TO_CHEVAL"),
        note="Cheval lives on the past's south coast (1:79), on the far side of a strip of water in 1:89 that "
        "the feather hops")
def talk_to_cheval(e):
    act.travel_to(e, 0x79, at=(40, 120))
    act.enter(e, (1, 7), "up")
    act.talk(e, ram.CONST["INTERAC_CHEVAL"], quiet=30)
    act.exit_room(e, "down")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.u8(e, "wc6e2") & 2,
        note="the baby falls sick once Link has 2 essences and has walked 8 other screens since naming it; back "
        "to the present through past Lynna City's portal spot (the harp won't play on the spot itself); "
        "Blossom asks yes/no, then how much (config donation; rupees topped up)")
def doctor_donation(e):
    act.travel_to(e, 0x48)
    act.walk_to(e, (104, 88))
    act.play_harp(e)
    act.walk_to(e, (72, 88), leave_ok=True, stop_on_scene=True)
    act.wait_until(e, lambda e: not ram.is_past(e), 300, "time warp")
    act.settle(e, quiet=60)
    act.travel_to(e, 0x47)
    act.enter(e, (2, 5), "up")
    act.settle(e, quiet=30)
    cheats.ensure_rupees(e, CFG.donation)
    act.talk(e, ram.CONST["INTERAC_BLOSSOM"], choices=[0, DONATIONS.index(CFG.donation)], quiet=30)
    act.exit_room(e, "down")
