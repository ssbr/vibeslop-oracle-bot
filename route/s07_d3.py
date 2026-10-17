"""D2 -> D3: the doctor money for Bipin & Blossom's baby; Moosh, Cheval's grave (flippers, Cheval Rope); Rafton,
Ricky's gloves, Tingle's chart, Rafton's raft to Crescent Island; the Tokay item hunt (to be continued), Wild
Tokay."""

from oracle_bot import act, cheats, ram
from oracle_bot.config import DONATIONS
from oracle_bot.runner import Route

from .common import CFG, LYNNA_PORTAL, LYNNA_PORTAL_STAND, NAYRU_PORTAL

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
    act.time_portal(e, LYNNA_PORTAL, LYNNA_PORTAL_STAND)
    act.travel_to(e, 0x47)
    act.enter(e, (2, 5), "up")
    act.settle(e, quiet=30)
    cheats.ensure_rupees(e, CFG.donation)
    act.talk(e, ram.CONST["INTERAC_BLOSSOM"], choices=[0, DONATIONS.index(CFG.donation)], quiet=30)
    act.exit_room(e, "down")


@R.step(done=lambda e: ram.u8(e, "wMooshState") & 0x20,
        note="present Yoll Graveyard (0:6c): kill the three Ghinis harassing Moosh, then talk to him and he lets "
        "Link ride")
def rescue_moosh(e):
    act.travel_to(e, 0x6C)
    act.fight(e)
    act.settle(e, quiet=30)
    act.talk_companion(e)
    act.wait_until(e, lambda e: ram.u8(e, "wLinkObjectIndex") == 0xD1, 60, "riding Moosh")


# 0:5b, Cheval's grave: the tombstone at (2,2) is walled in by pits and other tombstones that Moosh is too big to
# squeeze between, so he floats over the pits around the right side and along the top. (walk-to point or None,
# float waypoints)
GRAVEYARD_FLOATS = [((88, 56), [(88, 88), (104, 88), (104, 104)]),
                    ((88, 120), [(56, 120), (56, 136), (24, 136)]),
                    (None, [(24, 88), (40, 88), (40, 72)])]


@R.step(done=lambda e: ram.has(e, "FLIPPERS"),
        note="ride Moosh to the tombstone, get off and push it; inside (group 5 dungeon 0e) north, east and down "
        "to the lever room (5:bf): hop the channels to the lever, pull it all the way and get up the stairs "
        "while the blocks are parted")
def chevals_grave(e):
    act.travel_to(e, 0x5B)
    for start, waypoints in GRAVEYARD_FLOATS:
        if start:
            act.walk_to(e, start)
        act.moosh_float(e, *waypoints)
    act.walk_to(e, (52, 40), tol=2)  # under the tombstone
    act.dismount(e)
    act.push_tile(e, (2, 2), "up")
    act.enter(e, (2, 2), "up")
    for direction in ("up", "right", "down"):
        act.exit_room(e, direction)
    act.pull_lever(e)
    act.walk_to(e, (40, 184))  # (126 frames at most; the blocks close in ~250)
    flippers = act.find(e, "interaction", ram.CONST["INTERAC_MISCELLANEOUS_1"], 0x0C)
    act.approach(e, flippers, "d")
    act.hold_until(e, "up", lambda e: ram.has(e, "FLIPPERS"), 60, "flippers")
    act.settle(e, quiet=30)


@R.step(done=lambda e: ram.has(e, "CHEVAL_ROPE"),
        note="jump off the ledge into the channel, swim north into 5:b7 and back west along the north side of "
        "5:b6 to the rope's platform; back out by the entrance stairs, then lift the rock and hop the pit")
def cheval_rope(e):
    act.exit_room(e, "up")
    act.exit_room(e, "left", span=(48, 80))
    rope = act.find(e, "interaction", ram.CONST["INTERAC_MISCELLANEOUS_1"], 0x0B)
    act.approach(e, rope, "r")
    act.hold_until(e, "left", lambda e: ram.has(e, "CHEVAL_ROPE"), 60, "Cheval Rope")
    act.settle(e, quiet=30)
    act.exit_room(e, "down")
    act.enter(e, (8, 10), "down")
    act.exit_room(e, "down")


@R.step(done=lambda e: ram.gflag(e, "GAVE_ROPE_TO_RAFTON"),
        note="to the past by Nayru's portal; Rafton is in the west house of 1:a7 and wants the rope for his raft "
        "(Ralph turns up on the way out)")
def rafton_rope(e):
    act.travel_to(e, 0x3A, at=(56, 24))
    act.time_portal(e, NAYRU_PORTAL, stand=(56, 24))
    act.travel_to(e, 0xA7)
    act.enter(e, (2, 4), "up")
    act.talk(e, ram.CONST["INTERAC_RAFTON"], choices=[0], quiet=30)
    act.exit_room(e, "down")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.has(e, "RICKY_GLOVES") or ram.u8(e, "wRickyState") & 0x20,
        note="back to the present by Lynna City's portal; Ricky (0:6a, there once Rafton has the rope) lost his "
        "gloves: after talking to him they're buried under the dirt at 0:98 (2,4)")
def rickys_gloves(e):
    act.travel_to(e, 0x48)
    act.time_portal(e, LYNNA_PORTAL, LYNNA_PORTAL_STAND)
    act.travel_to(e, 0x6A)
    act.talk_companion(e)
    act.travel_to(e, 0x98)
    act.break_tile(e, (2, 4))
    act.pickup(e)


@R.step(done=lambda e: ram.u8(e, "wRickyState") & 0x20, note="give Ricky his gloves and he lets Link ride")
def ricky(e):
    act.travel_to(e, 0x6A)
    act.talk_companion(e)
    act.wait_until(e, lambda e: ram.u8(e, "wLinkObjectIndex") == 0xD1, 60, "riding Ricky")


def ricky_hop(e, direction: str, there) -> None:
    """Hold `direction` until Ricky has hopped (up a cliff, over a hole) and landed where there(y, x)."""
    landed = lambda e: ram.u8(e, "w1Companion.state") == 5 and ram.u8(e, "w1Companion.zh") == 0  # noqa: E731
    act.hold_until(e, direction, lambda e: there(*ram.link_px(e)) and landed(e), 180, f"Ricky hopping {direction}")


@R.step(done=lambda e: ram.has(e, "ISLAND_CHART"),
        note="Tingle floats over a plateau in 0:79 that only Ricky gets onto: punch through 0:7a's bushes, hop up "
        "0:79's east cliff, down the gully into 0:89, over a hole and back up to the plateau's foot, hop up; on "
        "foot, a jump-slash pops the balloon, and Tingle gives his chart to a friend")
def island_chart(e):
    act.exit_room(e, "down")
    act.exit_room(e, "left")
    act.walk_to(e, (88, 128), tol=2)
    ricky_hop(e, "up", lambda y, x: y < 44)
    act.exit_room(e, "down", span=(80, 96))  # down the gully (column 5), not back off the cliff
    act.walk_to(e, (24, 72), tol=2)
    ricky_hop(e, "left", lambda y, x: x < 44)
    act.exit_room(e, "up")
    act.walk_to(e, (104, 32), tol=2)
    ricky_hop(e, "up", lambda y, x: y < 60)
    act.dismount(e)
    act.walk_to(e, (50, 40), tol=1)
    act.face(e, "right")
    feather, sword = act.ready(e, "FEATHER"), act.item_button(e, "SWORD")
    act.tap(e, feather, hold=2, after=6)
    act.tap(e, sword)
    tingle = ram.CONST["INTERAC_TINGLE"]
    act.wait_until(e, lambda e: act.find(e, "interaction", tingle).z == 0, 300, "Tingle to come down")
    act.talk(e, tingle, choices=[0], quiet=30)


@R.step(done=lambda e: ram.room_flag(e, 1, 0xA8, 0x40),
        note="off Tingle's plateau, to the past by Nayru's portal; with the chart Rafton has the raft ready (he "
        "goes through to his workshop, whose back door leads to it); sail round the rocks east of his house "
        "(1:a7 down, c7, c8, up b8) into 1:a8, where a storm wrecks the raft on Crescent Island (1:aa) and the "
        "Tokay take everything")
def raft_to_crescent(e):
    act.walk_to(e, (104, 24))  # (a jump down the cliff)
    act.travel_to(e, 0x3A, at=(56, 24))
    act.time_portal(e, NAYRU_PORTAL, stand=(56, 24))
    act.travel_to(e, 0xA7)
    act.enter(e, (2, 4), "up")
    act.exit_room(e, "right")
    act.exit_room(e, "down")
    act.walk_to(e, (72, 120))
    act.hold_until(e, "down", lambda e: ram.u8(e, "wLinkObjectIndex") == 0xD1, 90, "onto the raft")
    act.settle(e, quiet=20)
    act.exit_room(e, "down")
    act.exit_room(e, "down", span=(88, 140))  # east of the whirlpools
    act.exit_room(e, "right", span=(16, 48))
    act.exit_room(e, "up")
    act.exit_room(e, "up")
    act.settle(e, quiet=60)


TOKAY = ram.CONST["INTERAC_TOKAY"]
SPROUT = ram.CONST["ENEMY_VINE_SPROUT"]


@R.step(done=lambda e: ram.has(e, "SHOVEL"), note="1:cb: the Tokay south of the landing has the shovel")
def crescent_shovel(e):
    act.travel_to(e, 0xCB)
    act.talk(e, TOKAY, 0x07, quiet=30)


@R.step(done=lambda e: ram.has(e, "SWORD"),
        note="cave 5:ca under 1:bb's north-west corner: push the top-right mound aside and dig down to the Tokay "
        "with the sword (the lower mound would wall his pocket off)")
def crescent_sword(e):
    act.travel_to(e, 0xBB)
    act.enter(e, (0, 1), "up")
    act.push_tile(e, (2, 10), "left")
    act.talk(e, TOKAY, 0x06, sides="rd", quiet=30)
    act.exit_room(e, "down")


# Vine sprouts (enemy subids) that must stand where the present's vines up to the Scent Tree grow:
# (sprout, past room, target $YX, pushes). The third (4, in 1:da) starts in place.
VINES = [(2, 0xBA, 0x18, [("right", 2)]), (3, 0xCC, 0x11, [("up", 2), ("left", 4)])]


@R.step(done=lambda e: all(ram.vine_position(e, v) == pos for v, _, pos, _ in VINES),
        note="push the vine sprouts where the present's vines need them (code/ages/roomSpecificTileChanges.s)")
def vine_sprouts(e):
    for vine, room, pos, pushes in VINES:
        if ram.vine_position(e, vine) == pos:
            continue
        act.travel_to(e, room)
        for direction, times in pushes:
            for _ in range(times):
                act.push_object(e, SPROUT, direction, kind="enemy")
                act.wait_until(e, lambda e: (lambda o: o.y % 16 == 8 and o.x % 16 == 8)(act.find(e, "enemy", SPROUT)),
                               60, "the sprout to finish sliding")
