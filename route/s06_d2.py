"""D2 Wing Dungeon (dungeon 2). Top-down rooms are group 4; the side views (group 6) share their room numbers.

1F:  .  34 35 .  .  36 37 38        34 Swoop (miniboss); 35's stairs lead down to B1
     39 3a 3b .  3c 3d 3e .
     .  .  3f 40 41 42 .  .         a minecart runs 40 -> 3f -> 3b -> 3a
     .  .  43 44 45 .  .  .         44 Spiked Beetles, 43 colored cube
     .  .  .  46 47 .  .  .         46 entrance; 47's stairs lead to the side views 29 -> 2a -> 48
     .  .  .  .  .  48 .  .
B1:  27 28 29 2a 2b                 2b Head Thwomp (boss); 27/28 side views (Roc's Feather in 28)
     .  2c 2d 2e 2f 30
     .  .  31 32 33
Optional chests (map) are skipped.
"""

from oracle_bot import act, bosses, ram
from oracle_bot.runner import Route

R = Route()

D2 = 2
INTERAC_SIDESCROLL_PLATFORM = ram.CONST["INTERAC_MOVING_SIDESCROLL_PLATFORM"]


def room_item_taken(room: int):
    return lambda e: ram.room_flag(e, 4, room, 0x20)


# --- side views: Link stands 7px above the surface he's on; moving platforms follow fixed scripts
# (data/ages/movingSidescrollPlatform.s) ---

def platform(e, subid: int) -> ram.Obj:
    return act.find(e, "interaction", INTERAC_SIDESCROLL_PLATFORM, subid)


def link_y(e) -> int:
    return ram.link_px(e)[0]


def link_x(e) -> int:
    return ram.link_px(e)[1]


def on_ground(e) -> bool:
    return ram.u8(e, "wLinkInAir") == 0


def leave_side_view(e, direction: str, max_frames: int = 300) -> None:
    before = ram.room(e)
    act.hold_until(e, direction, lambda e: ram.room(e) != before, max_frames, f"out {direction}")
    act.settle(e, quiet=10)


def cross_29_east(e):
    """Clear the Keese from the floor by the ladder (their bumps knock Link into the pit past the pillar, a dead
    end), back up and off the ladder's right side onto the pillar (top y=96), then platform 7 (rides x 136-168 at
    the pillar's height) over to the ledge, out east."""
    act.climb(e, 24, "down", lambda e: on_ground(e) and link_y(e) == 153)
    act.side_clear(e)
    act.climb(e, 24, "up", lambda e: link_y(e) <= 48)
    act.hold_until(e, "right", lambda e: link_x(e) >= 104 and on_ground(e) and link_y(e) == 89, what="onto the pillar")
    act.hold_until(e, "right", lambda e: link_x(e) >= 120, what="near the pillar's edge")
    act.side_wait(e, lambda e: platform(e, 7).x <= 137, 400, "platform 7 at the pillar")
    act.hold_until(e, "right", lambda e: link_x(e) >= platform(e, 7).x - 2, what="onto platform 7")
    act.side_wait(e, lambda e: platform(e, 7).x >= 167, 300, "ride to the ledge")
    leave_side_view(e, "right")


def cross_2a_east(e):
    """Platform 8 (rises to the left ledge's height) down to the floor, under the Thwomp, platform 9 up to the
    ladder out to 48."""
    act.side_clear(e)
    act.hold_until(e, "right", lambda e: link_x(e) >= 72, what="ledge edge")
    act.side_wait(e, lambda e: 100 <= platform(e, 8).y <= 112, 400, "platform 8 at the ledge")
    act.hold_until(e, "right", lambda e: link_x(e) >= 87, what="onto platform 8")
    act.side_wait(e, lambda e: platform(e, 8).y >= 150, 400, "platform 8 down")
    act.hold_until(e, "right", lambda e: link_x(e) >= 196, max_frames=400, what="under the Thwomp")
    act.side_wait(e, lambda e: platform(e, 9).y >= 150, 400, "platform 9 down")
    act.hold_until(e, "right", lambda e: link_x(e) >= 214, what="onto platform 9")
    act.side_wait(e, lambda e: platform(e, 9).y <= 74, 400, "platform 9 up")
    leave_side_view(e, "up", 200)


def cross_2a_west(e):
    """Down the ladder onto platform 9 and ride it to the floor (a Keese bumping Link off the ladder drops him
    onto the floor too), under the Thwomp, platform 8 up to the left ledge, out west."""
    act.side_wait(e, lambda e: platform(e, 9).y <= 73, 400, "platform 9 up")
    act.hold_until(e, "down", lambda e: on_ground(e) and link_y(e) >= 57, max_frames=200, what="down the ladder")
    act.wait_until(e, lambda e: on_ground(e) and link_y(e) == 137, 400, "down to the floor")
    act.hold_until(e, "left", lambda e: link_x(e) <= 100, max_frames=300, what="under the Thwomp")
    act.side_wait(e, lambda e: platform(e, 8).y >= 151, 400, "platform 8 down")
    act.hold_until(e, "left", lambda e: link_x(e) <= 90, what="onto platform 8")
    act.side_wait(e, lambda e: platform(e, 8).y <= 105, 400, "platform 8 up to the ledge")
    leave_side_view(e, "left", 200)


def cross_29_west(e):
    act.side_clear(e)
    act.hold_until(e, "left", lambda e: link_x(e) <= 182, what="ledge edge")
    act.side_wait(e, lambda e: platform(e, 7).x >= 167, 400, "platform 7 at the ledge")
    act.hold_until(e, "left", lambda e: link_x(e) <= platform(e, 7).x + 2, what="onto platform 7")
    act.side_wait(e, lambda e: platform(e, 7).x <= 137, 400, "platform 7 at the pillar")
    act.hold_until(e, "left", lambda e: link_x(e) <= 24 and on_ground(e) and link_y(e) > 140, max_frames=300,
                   what="off the pillar to the ladder")
    before = ram.room(e)
    act.climb(e, 24, "up", lambda e: ram.room(e) != before)
    act.settle(e, quiet=10)


@R.step(done=lambda e: ram.dungeon(e) == D2 or ram.essences(e) >= 2)
def enter_d2(e):
    act.enter(e, (2, 5), "up")


@R.step(done=room_item_taken(0x39),
        note="44: Spiked Beetles (shield flips them); 43: cube right 3, down, left, up, left 6 onto (3,5); "
        "3f: push the right block of the three up; 3b, 3a west; 39: Keese and Pig Warriors drop a key")
def d2_first_key(e):
    act.exit_room(e, "up")
    act.fight(e)
    act.exit_room(e, "left")
    for direction, times in (("right", 3), ("down", 1), ("left", 1), ("up", 1), ("left", 6)):
        act.roll_cube(e, direction, times)
    act.settle(e, quiet=30)
    act.exit_room(e, "up")
    act.push_tile(e, (8, 5), "up")
    act.travel(e, "up", "left", "left")
    act.fight(e)
    act.pickup(e)


@R.step(done=room_item_taken(0x48),
        note="back through 3f (from above its blocks only open as: (8,3) down, (8,5) down, (8,4) left); key door "
        "44->45; 45: bomb the south wall; 47's stairs to the side views; 48: Ropes guard a chest")
def d2_second_key(e):
    act.travel(e, "right", "right", "down")
    act.fight(e)  # Ropes knock Link off the push spots
    act.push_tile(e, (8, 3), "down")
    act.push_tile(e, (8, 5), "down")
    act.push_tile(e, (8, 4), "left")
    act.travel(e, "down", "right")
    act.unlock(e, (9, 14), "right")
    act.exit_room(e, "right")
    act.fight(e)
    act.break_tile(e, (10, 8))
    act.exit_room(e, "down")
    act.fight(e)
    act.enter(e, (5, 7), "down")
    cross_29_east(e)
    cross_2a_east(e)
    for _ in range(3):  # knockback can push Link back down the hole he came up through
        act.walk_to(e, (104, 136))
        act.fight(e)
        if ram.room(e) == (4, 0x48):
            break
        act.hold_until(e, "up", lambda e: ram.room(e) == (4, 0x48), max_frames=300, what="back up the ladder")
        act.settle(e, quiet=20)
    act.wait_until(e, lambda e: ram.u8(e, "wRoomLayout", 0x57) == ram.CONST["TILEINDEX_CHEST"], 200, "chest")
    act.open_chest(e, (5, 7))


@R.step(done=lambda e: ram.has(e, "COMPASS"),
        note="back through the side views; 45: with the enemies gone the lower block (a pushblock trigger) moves")
def d2_compass(e):
    act.enter(e, (3, 3), "up")
    cross_2a_west(e)
    cross_29_west(e)
    act.exit_room(e, "up")
    act.fight(e)
    act.push_tile(e, (5, 11), "left")
    act.open_chest(e, (1, 13))


@R.step(done=lambda e: ram.room_flag(e, 4, 0x34, 0x80),
        note="41: west key door; 40: the minecart rides to 3a's walled-off corner below Swoop")
def d2_swoop(e):
    act.exit_room(e, "up")
    act.fight(e)
    act.unlock(e, (7, 0), "left")
    act.exit_room(e, "left")
    act.ride_cart(e)
    act.exit_room(e, "up")
    act.settle(e, quiet=30)
    bosses.swoop(e)
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.has(e, "FEATHER"),
        note="35's north stairs to B1 2d; south to 31, east to 32, stairs to side view 27; along its floor under "
        "the Thwomp into 28")
def d2_feather(e):
    act.exit_room(e, "right", span=(40, 72))
    act.enter(e, (2, 3), "up")
    act.exit_room(e, "down")
    act.exit_room(e, "right")
    act.enter(e, (1, 7), "up")
    act.climb(e, 24, "up", lambda e: link_y(e) <= 121 and on_ground(e) and link_y(e) >= 115)
    leave_side_view(e, "right", 600)
    act.hold_until(e, "right", lambda e: ram.has(e, "FEATHER") or not ram.controllable(e), max_frames=200,
                   what="to the feather")
    act.settle(e, quiet=30)
