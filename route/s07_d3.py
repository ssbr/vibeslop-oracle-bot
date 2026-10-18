"""D2 -> D3: the doctor money for Bipin & Blossom's baby; Moosh, Cheval's grave (flippers, Cheval Rope); Rafton,
Ricky's gloves, Tingle's chart, Rafton's raft to Crescent Island; the Tokay item hunt (to be continued), Wild
Tokay."""

from oracle_bot import act, cheats, ram
from oracle_bot.config import DONATIONS
from oracle_bot.runner import Route

from .common import CFG, LYNNA_PORTAL, LYNNA_PORTAL_STAND, NAYRU_PORTAL

R = Route()
MISC_1 = ram.CONST["INTERAC_MISCELLANEOUS_1"]  # (subids 0a-0c: the bombs, rope and flippers lying about)


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
    act.collect(e, act.find(e, "interaction", MISC_1, 0x0C), "d", lambda e: ram.has(e, "FLIPPERS"))


@R.step(done=lambda e: ram.has(e, "CHEVAL_ROPE"),
        note="jump off the ledge into the channel, swim north into 5:b7 and back west along the north side of "
        "5:b6 to the rope's platform; back out by the entrance stairs, then lift the rock and hop the pit")
def cheval_rope(e):
    act.exit_room(e, "up")
    act.exit_room(e, "left", span=(48, 80))
    act.collect(e, act.find(e, "interaction", MISC_1, 0x0B), "r", lambda e: ram.has(e, "CHEVAL_ROPE"))
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
SHOP_ITEM = ram.CONST["INTERAC_TOKAY_SHOP_ITEM"]
SHOP_FEATHER, SHOP_BRACELET = 0, 1  # (shop item subids: Link swaps the shovel, feather and bracelet here)


def shop(e, item: int, times: int = 1) -> None:
    """In the Tokay trading hut (1:ad): pick the item, answering yes. With the feather or bracelet in hand,
    picking the other one first gives the shovel back; picking it again swaps the shovel for it."""
    act.travel_to(e, 0xAD)
    act.enter(e, (1, 5), "up")
    for _ in range(times):
        act.talk(e, SHOP_ITEM, item, choices=[0], sides="d", quiet=30)
    act.exit_room(e, "down")


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


@R.step(done=lambda e: ram.has(e, "BOMBS"),
        note="the hut swaps the shovel for the bracelet; the bombs are in the Cucco hut's walled-off back room "
        "(2:e3): round by 1:dd to 1:cd's west column, its stairs to cave 2:ce, push two mounds right, the far "
        "stairs; back out the same way, bombing 2:ce's cracked blocks (the mounds reset)")
def crescent_bombs(e):
    shop(e, SHOP_BRACELET)
    act.travel_to(e, 0xCD, at=(104, 24))
    act.enter(e, (1, 1), "up")
    act.push_tile(e, (6, 5), "right")
    act.push_tile(e, (5, 6), "right")
    act.enter(e, (1, 8), "up")
    act.collect(e, act.find(e, "interaction", MISC_1, 0x0A), "r", lambda e: ram.has(e, "BOMBS"))
    act.enter(e, (1, 6), "up")
    act.break_tile(e, (4, 5))
    act.break_tile(e, (4, 4))
    act.enter(e, (1, 1), "up")


@R.step(done=lambda e: ram.has(e, "FLIPPERS"),
        note="swap the bracelet back for the feather; bomb open 1:cb's cave (0,8): hop the water and bomb the "
        "cracked blocks to the Tokay with the flippers")
def crescent_flippers(e):
    shop(e, SHOP_FEATHER, times=2)
    act.travel_to(e, 0xCB, at=(40, 136))
    act.break_tile(e, (0, 8))
    act.enter(e, (0, 8), "up")
    act.talk(e, TOKAY, 0x09, sides="lrdu", quiet=30, allow=act.abilities(e) | {"bombs"})
    act.exit_room(e, "down")


# 7:05, the side-view water under 5:cc: down the west shaft, along the bottom, up the east pocket to its ladder.
UNDER_5CC = [(8, 24), (72, 24), (72, 72), (104, 72), (104, 24), (152, 24), (152, 200), (104, 200), (88, 184)]


@R.step(done=lambda e: ram.has(e, "SEED_SATCHEL"),
        note="swap back to the bracelet; in 5:cc lift the north-west rocks and dive (B) in the pool there; "
        "through 7:05 (swim, ladders) up into the north-east pocket, stairs to the central plateau (1:bc): "
        "the Tokay west in 1:bb has the satchel")
def crescent_satchel(e):
    shop(e, SHOP_BRACELET, times=2)
    act.travel_to(e, 0xCB, at=(40, 136))
    act.enter(e, (0, 8), "up")
    act.walk_to(e, (24, 40), tol=3)
    act.wait_until(e, lambda e: ram.u8(e, "wLinkSwimmingState") == 3, 60, "swimming")
    act.tap(e, "b", hold=2, after=4)  # dive
    act.wait_until(e, lambda e: ram.room(e)[0] == 7, 120, "dive")
    act.settle(e, quiet=30)
    act.steer_through(e, *UNDER_5CC, tol=4)
    act.hold_until(e, "up", lambda e: ram.link_px(e)[0] <= 57 and ram.u8(e, "wLinkSwimmingState") == 0, 120,
                   "up out of the pocket")
    act.hold_until(e, "left", lambda e: ram.link_px(e)[1] <= 106 and ram.u8(e, "wLinkInAir") == 0, 300,
                   "to the middle ladder")
    act.climb(e, 105, "up", lambda e: ram.link_px(e)[0] <= 26)
    act.hold_until(e, "right", lambda e: ram.link_px(e)[1] >= 215, 300, "to the exit ladder")
    act.climb(e, 216, "up", lambda e: ram.room(e)[0] != 7)
    act.settle(e, quiet=30)
    act.enter(e, (1, 12), "left")
    act.travel_to(e, 0xBB, at=(72, 104))
    act.talk(e, TOKAY, 0x0A, quiet=30)


@R.step(done=lambda e: ram.gflag(e, "BOUGHT_FEATHER_FROM_TOKAY"),
        note="off the plateau by jumping down 1:bc's south-west cliff into 1:cc; the hut sells the feather for "
        "10 mystery seeds")
def crescent_feather(e):
    act.exit_room(e, "right")
    act.walk_to(e, (100, 24), tol=2)
    act.hold_until(e, "down", lambda e: ram.room(e) != (1, 0xBC) and ram.controllable(e), 180, "off the cliff")
    act.settle(e, quiet=20)
    shop(e, SHOP_FEATHER)


def block_7_06(e) -> ram.Obj:
    return act.find(e, "interaction", ram.CONST["INTERAC_MOVING_SIDESCROLL_PLATFORM"], 0x0B)


def on_block(e) -> bool:
    b, (y, x) = block_7_06(e), ram.link_px(e)
    return ram.u8(e, "wLinkInAir") == 0 and ram.u8(e, "wLinkSwimmingState") == 0 and abs(x - b.x) <= 15 and y < b.y - 20


def jump_off_block(e) -> None:
    """From the sliding block: run to its east edge and jump for the first ledge (5,10)."""
    act.hold_until(e, "right", lambda e: ram.link_px(e)[1] >= block_7_06(e).x + 10, 40, "the block's edge")
    act.jump(e, "right")


def on_first_ledge(e) -> bool:
    y, x = ram.link_px(e)
    return ram.u8(e, "wLinkInAir") == 0 and ram.u8(e, "wLinkSwimmingState") == 0 and y <= 74 and 158 <= x <= 178


def step_off_ladder(e) -> None:
    e.set_buttons(act.mask_of("right"))
    e.step(40)
    e.set_buttons(0)


@R.step(done=lambda e: ram.has(e, "HARP"),
        note="the plateau with the harp Tokay (1:da west) is reached through cave 5:cd from 1:db: lift a pot, "
        "stairs down to side view 7:07, swim west into 7:06, up its ladder, onto the sliding block, feather "
        "up the ledges and back east along 7:07's top to its west ladder, up to 5:cd's west half, out; back by the "
        "one-way way 7:07 does go")
def crescent_harp(e):
    act.travel_to(e, 0xDB)
    act.fight(e)  # (Octoroks knock Link off the top edge)
    act.enter(e, (0, 1), "up")
    act.enter(e, (4, 9), "up")
    act.hold(e, "down", 90)  # down the ladder
    act.hold_until(e, "left", lambda e: ram.u8(e, "wLinkSwimmingState") != 0, 120, "into the water")
    act.steer_through(e, (120, 40), (120, 8), tol=3)
    act.hold_until(e, "left", lambda e: ram.room(e) == (7, 6), 120, "west into 7:06")
    act.settle(e, quiet=10)
    act.steer_through(e, (146, 200), (146, 24), (104, 24), tol=3)  # under the block, to the ladder
    act.hold_until(e, "up", lambda e: abs(ram.link_px(e)[0] - 60) <= 2, 120, "up the ladder")
    if not act.lookahead(e, step_off_ladder, on_block, 60, lambda e: True, max_frames=200):
        raise act.Stuck("couldn't step onto the sliding block")
    act.ready(e, "FEATHER")  # (equipping it mid run-up costs the jump its momentum)
    act.wait_until(e, lambda e: block_7_06(e).x >= 110, 400, "the block near its east end")
    if not act.lookahead(e, jump_off_block, on_first_ledge, 90, lambda e: block_7_06(e).x >= 110, max_frames=200):
        raise act.Stuck("couldn't jump from the block to the ledge")
    for _ in range(2):  # two more ledges up
        act.jump(e, "right")
    act.hold_until(e, "right", lambda e: ram.room(e) == (7, 7) and ram.controllable(e), 120, "east into 7:07")
    act.settle(e, quiet=5)
    act.hold_until(e, "right", lambda e: ram.link_px(e)[1] >= 40, 60, "the gap")
    act.jump(e, "right")
    act.hold_until(e, "right" if ram.link_px(e)[1] < 88 else "left", lambda e: abs(ram.link_px(e)[1] - 88) <= 1, 60,
                   "the ladder")
    act.climb(e, 88, "up", lambda e: ram.room(e)[0] != 7)
    act.settle(e, quiet=20)
    act.exit_room(e, "down", span=(48, 64))
    act.talk(e, TOKAY, 0x08, quiet=30)
    # Back the way 7:07 does go: its west ladder, down the gap into the water, east, up both ladders.
    act.enter(e, (0, 6), "up")
    act.enter(e, (4, 2), "up")
    act.hold_until(e, "down", lambda e: ram.u8(e, "wLinkInAir") == 0 and ram.link_px(e)[0] >= 40, 120, "down the ladder")
    act.hold_until(e, "left", lambda e: ram.u8(e, "wLinkSwimmingState") != 0, 200, "down the gap into the water")
    act.steer_through(e, (120, 56), (120, 168), (104, 168), tol=3)
    act.hold_until(e, "up", lambda e: ram.u8(e, "wLinkSwimmingState") == 0 and ram.u8(e, "wLinkInAir") == 0
                   and ram.link_px(e)[0] <= 74, 200, "up the east ladder")
    act.hold_until(e, "right", lambda e: ram.link_px(e)[1] >= 215, 200, "to the exit ladder")
    act.climb(e, 216, "up", lambda e: ram.room(e)[0] != 7)
    act.settle(e, quiet=20)
    act.exit_room(e, "down", span=(120, 144))


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
