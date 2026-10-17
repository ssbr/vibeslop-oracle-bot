"""D1 -> D2: Fairies' Woods hide-and-seek, the present D2 entrance caves in, naming Bipin & Blossom's baby, the
Harp of Ages in Nayru's cellar, the portal to the past, Mystery Seeds, the Wooden Shield, Ambi's bombs, and bombing
the Wing Dungeon open (Deku Forest, 1:83)."""

from oracle_bot import act, cheats, menus, ram
from oracle_bot.runner import Route

from .common import CFG

R = Route()

# Where the three fairies hide: (present room, tile). Each is revealed by breaking the tile.
FAIRY_SPOTS = ((0x81, (2, 5)), (0x80, (5, 4)), (0x91, (3, 2)))  # rock (bracelet), bush, bush
D2_DOOR = (2, 5)  # bombable cave door in 1:83 (TILEINDEX $d1)
MENU_KID_NAME = 7  # wOpenedMenuType of Blossom's name entry
GOT_AMBIS_BOMBS = "0b"  # GLOBALFLAG_0b: the palace guards then let Link pass freely


@R.step(done=lambda e: ram.gflag(e, "FOREST_UNSCRAMBLED"),
        note="the game starts on re-entering 0:82 (south loops back while the woods are scrambled); each fairy "
        "hides under a tile in a neighbouring screen; winning unscrambles the woods")
def fairy_hide_and_seek(e):
    act.travel_to(e, 0x82)
    act.exit_room(e, "down", expect=(0, 0x82))
    act.settle(e, quiet=60)
    for room, tile in FAIRY_SPOTS:
        act.travel_to(e, room)
        act.break_tile(e, tile)
        act.settle(e, quiet=60)


@R.step(done=lambda e: ram.room_flag(e, 0, 0x83, 0x80), note="lifting the stone by it caves in the present D2 entrance")
def d2_entrance_collapses(e):
    act.travel_to(e, 0x83)
    act.break_tile(e, (4, 3))
    act.play_until(e, lambda e: ram.room_flag(e, 0, 0x83, 0x80) and ram.controllable(e), what="D2 collapse")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.u8(e, "wc6e2") & 1, note="Lynna City 0:47, left door: Blossom asks for the baby's name")
def name_child(e):
    act.travel_to(e, 0x47)
    act.enter(e, (2, 5), "up")
    act.approach(e, act.find(e, "interaction", ram.CONST["INTERAC_BLOSSOM"]))
    act.tap(e, "a", hold=1, after=4)
    act.play_until(e, lambda e: ram.u8(e, "wOpenedMenuType") == MENU_KID_NAME, what="name entry")
    e.step(60)  # fade-in
    menus.enter_name(e, CFG.child_name)
    act.play_until(e, lambda e: ram.u8(e, "wc6e2") & 1 and ram.controllable(e), choices=[0], what="name confirmed")
    act.settle(e, quiet=30)
    act.exit_room(e, "down")


@R.step(done=lambda e: ram.has(e, "TUNE_OF_ECHOES"),
        note="Nayru's house (0:3a): Impa, push the statue left, stairs to a hidden room (3:9f) and the cellar (3:ae)")
def harp_of_ages(e):
    act.travel_to(e, 0x3A)
    act.enter(e, (2, 3), "up")
    act.talk(e, ram.CONST["INTERAC_IMPA_NPC"], 0, quiet=30)
    act.push_tile(e, (3, 2), "left")
    act.settle(e, quiet=30)
    act.enter(e, (2, 2), "up")
    act.enter(e, (1, 1), "left")
    act.pickup(e)
    act.play_until(e, lambda e: ram.has(e, "TUNE_OF_ECHOES") and ram.controllable(e), what="harp and tune")
    act.settle(e, quiet=60)


@R.step(done=ram.is_past, note="back outside, the Tune of Echoes opens the portal spot left of Nayru's door")
def portal_to_past(e):
    act.enter(e, (1, 1), "left")  # up to the hidden room
    act.enter(e, (2, 2), "down")  # Link arrives on these stairs: step off and back on
    act.exit_room(e, "down", expect=(0, 0x3A))
    act.settle(e, quiet=60)
    act.play_harp(e)
    act.walk_to(e, (40, 24), leave_ok=True, stop_on_scene=True)
    act.wait_until(e, ram.is_past, 300, "time warp")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.has(e, "MYSTERY_SEEDS"),
        note="the Mystery tree (1:80) is walled off: cave under 1:71 (5:b5), its south path to 5:b4, stairs up into "
        "the east half of 1:70; a sword hit drops the seeds")
def mystery_seeds(e):
    act.travel_to(e, 0x71, at=(56, 40))
    act.enter(e, (2, 2), "up")
    act.exit_room(e, "left", span=(130, 156))
    act.enter(e, (8, 11), "up")
    act.travel_to(e, 0x80, at=(56, 80))
    act.walk_to(e, (70, 80))
    act.slash(e, "up")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.has(e, "SHIELD"),
        note="back down, around the cave to 5:b4's north stairs: a scrub in 1:70's west half sells it for 10 rupees")
def wooden_shield(e):
    act.travel_to(e, 0x70, at=(40, 120))
    act.enter(e, (2, 7), "up")
    act.exit_room(e, "right", span=(130, 156))
    act.exit_room(e, "left", span=(16, 56))
    act.enter(e, (2, 2), "up")
    cheats.ensure_rupees(e, 10)
    act.talk(e, ram.CONST["INTERAC_BUSINESS_SCRUB"], 0x06, choices=[0], quiet=30)


@R.step(done=lambda e: ram.has(e, "BOMBS"),
        note="out through 5:b5's north strip; holding Mystery Seeds, Link gets escorted to Ambi (by a soldier in the "
        "forest or the gate guards in 1:46), who takes them for 10 bombs")
def ambis_bombs(e):
    act.enter(e, (2, 2), "up")
    act.exit_room(e, "right", span=(16, 56))
    act.enter(e, (2, 11), "up")
    act.travel_to(e, 0x46)  # escorted to Ambi on the way (in the forest, or by the guards at the gate)
    act.play_until(e, lambda e: ram.has(e, "BOMBS") and ram.gflag(e, GOT_AMBIS_BOMBS) and ram.controllable(e),
                   what="escort to Ambi")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.room(e) == (1, 0x83) and ram.u8(e, "wRoomLayout", D2_DOOR[0] * 16 + D2_DOOR[1]) != 0xD1,
        note="bomb the cave door in the middle of Deku Forest")
def bomb_wing_dungeon(e):
    act.travel_to(e, 0x83)
    act.break_tile(e, D2_DOOR)
    act.walk_to(e, (72, 88))  # checkpoint spot in front of the door


R.mark("05_before_d2", release=True,
       expect=lambda e: ram.essences(e) == 1 and ram.has(e, "BOMBS") and ram.u8(e, "wc6e2") & 1)
