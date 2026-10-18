"""Maku Road (past mini-dungeon, dungeon $0d) -> save the Maku Sprout -> Seed Satchel in the present.

Rooms (group 4): 0d entrance, 0c, 0a hub (key door west), 0b Gels, 08 key chest, 09 button puzzle,
06 Stalfos, 07 stairs up to the sprout.
"""

from oracle_bot import act, ram
from oracle_bot.runner import Route

R = Route()

INTERAC_MAKU_TREE = 0x87
MAKU_ROAD = 0x0D


def in_dungeon_room(room):
    return lambda e: ram.room(e) == (4, room)


@R.step(done=lambda e: ram.dungeon(e) == MAKU_ROAD)
def enter_maku_road(e):
    act.enter(e, (2, 1), "up")


@R.step(done=in_dungeon_room(0x08), note="0c: push the block up to open the north door; 0b: kill the Gels")
def maku_road_to_key_room(e):
    act.exit_room(e, "up")
    act.push_tile(e, (4, 7), "up")
    act.exit_room(e, "up")  # hub (0a)
    act.push_tile(e, (7, 7), "right")  # the block boxing in the hub's south entrance
    act.exit_room(e, "right")
    act.fight(e)
    act.exit_room(e, "up")


@R.step(done=lambda e: ram.room_flag(e, 4, 0x08, 0x20),
        note="08: fill the pit with the entrance block, clear the two blocks, press the top button; chest spawns")
def maku_road_small_key(e):
    act.push_tile(e, (8, 7), "up")  # into the pit above it
    act.push_tile(e, (4, 11), "up")
    act.push_tile(e, (4, 12), "right")
    act.walk_to(e, (1 * 16 + 6, 7 * 16 + 8))  # button: wActiveTriggers == 1 spawns the chest at (5, 7)
    act.wait_until(e, lambda e: ram.u8(e, "wRoomLayout", 5 * 16 + 7) == ram.CONST["TILEINDEX_CHEST"], 120, "chest to appear")
    act.open_chest(e, (5, 7))


@R.step(done=in_dungeon_room(0x06), note="09: push (3,6) left, (2,6) up, (2,4) left, then press the button")
def maku_road_button_room(e):
    act.travel(e, "down", "left")
    act.unlock(e, (5, 0), "left")
    act.exit_room(e, "left")
    act.push_tile(e, (3, 6), "left")
    act.push_tile(e, (2, 6), "up")
    act.push_tile(e, (2, 4), "left")
    act.walk_to(e, (1 * 16 + 6, 4 * 16 + 8))
    act.exit_room(e, "up")


@R.step(done=lambda e: ram.room(e) == (1, 0x38),
        note="06: a heart piece behind two one-way blocks (up, then left); the lone block becomes pushable once "
        "the Stalfos die")
def maku_road_exit(e):
    act.fight(e)
    act.push_tile(e, (5, 4), "up")
    act.push_tile(e, (5, 5), "left")
    act.pickup(e)
    act.wait_until(e, lambda e: ram.u8(e, "wRoomLayout", 7 * 16 + 10) == 0x1C, 300, "block to become pushable")
    act.push_tile(e, (7, 10), "up")
    act.exit_room(e, "right")
    act.enter(e, (1, 7), "up")  # stairs up to the Maku Sprout


@R.step(done=lambda e: ram.gflag(e, "MAKU_TREE_SAVED"), note="two Moblins attack the sprout")
def save_maku_sprout(e):
    act.walk_to(e, (72, 72), stop_on_scene=True)
    act.settle(e, quiet=30)
    act.fight(e)
    act.play_until(e, lambda e: ram.gflag(e, "MAKU_TREE_SAVED"), what="Maku Sprout thanks Link")
    act.settle(e, quiet=60)


R.mark("02_after_maku_path", release=True)


@R.step(done=lambda e: not ram.is_past(e), note="the time portal is just south of the sprout")
def back_to_present(e):
    act.exit_room(e, "down")
    act.walk_to(e, (72, 88), leave_ok=True, stop_on_scene=True)
    act.wait_until(e, lambda e: not ram.is_past(e), 300, "time warp")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.has(e, "SEED_SATCHEL"), note="the Maku Tree is back; she drops the Seed Satchel")
def get_seed_satchel(e):
    act.exit_room(e, "up")
    act.settle(e, quiet=60)
    act.talk(e, INTERAC_MAKU_TREE, choices=[1], quiet=30)  # "...again?" -> No
    act.pickup(e)
