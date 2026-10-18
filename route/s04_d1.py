"""D1 Spirit's Grave (dungeon 1, group 4 rooms $10-$25) through the Eternal Spirit.

Layout (one floor):     10 .  .  11
                        .  .  12 13      13 boss, 11 essence
                        .  .  14 15 16
                        .  17 18 19 1a   18 Giant Ghini
                        .  1b .  1c 1d 1e
                        .  1f .  .  20 21   20 colored cube
                        .  22 23 24 25      24 entrance
Optional chests (map, compass, rings, gasha seed, 30 rupees) are skipped.
"""

from oracle_bot import act, bosses, ram
from oracle_bot.runner import Route

from .common import item_taken

R = Route()

D1 = 1


@R.step(done=lambda e: ram.dungeon(e) == D1 or ram.essences(e) >= 1)
def enter_d1(e):
    act.enter(e, (2, 6), "up")


@R.step(done=item_taken(4, 0x1E), note="25 Zols; 20 cube rolled up 3x between the torches (blue) opens both "
        "doors; 1e the Ghini drops a key")
def d1_ghini_key(e):
    act.exit_room(e, "right")
    act.fight(e)
    act.push_tile(e, (4, 10), "right")
    act.exit_room(e, "up")
    act.roll_cube(e, "up", 3)
    act.exit_room(e, "right")
    act.fight(e)
    act.exit_room(e, "up")
    act.fight(e)
    act.wait_until(e, lambda e: any(o.id == act.INTERAC_TREASURE for o in ram.objects(e, "interaction")), 300,
                   "key to drop")
    act.pickup(e)


@R.step(done=item_taken(4, 0x1A), note="1d: block aside, key door north; 1a: block aside, chest")
def d1_chest_key(e):
    act.exit_room(e, "left")
    act.push_tile(e, (5, 7), "left")
    act.unlock(e, (0, 7), "up")
    act.exit_room(e, "up")
    act.fight(e)  # (Keese knock Link off the push)
    act.push_tile(e, (4, 9), "right")
    act.open_chest(e, (2, 12))


@R.step(done=item_taken(4, 0x16), note="19: open the maze; 16: blocks, both buttons, ride the platform to the chest")
def d1_platform_key(e):
    act.exit_room(e, "left")
    act.push_tile(e, (7, 6), "down")
    act.push_tile(e, (7, 7), "right")
    act.exit_room(e, "right", span=(28, 47))  # into 1a's top-left corner
    act.exit_room(e, "up")
    act.push_tile(e, (8, 7), "up")
    act.push_tile(e, (8, 6), "left")
    act.push_tile(e, (8, 8), "right")
    act.push_tile(e, (7, 6), "up")
    act.push_tile(e, (7, 8), "up")
    act.walk_to(e, (2 * 16 + 6, 2 * 16 + 8))  # left button: chest
    act.walk_to(e, (2 * 16 + 6, 12 * 16 + 8))  # right button: moving platform
    act.wait_until(e, lambda e: ram.u8(e, "wRoomLayout", 1 * 16 + 7) == ram.CONST["TILEINDEX_CHEST"], 120,
                   "chest to appear")
    act.ride_platform(e, (100, 88), (52, 120))
    act.open_chest(e, (1, 7))
    act.ride_platform(e, (52, 120), (100, 88))


@R.step(done=lambda e: ram.room(e) == (4, 0x18) and not act.foes_in_room(e),
        note="15: ride the vertical platform west; 14: key door south; 18: Giant Ghini")
def d1_giant_ghini(e):
    act.travel(e, "down", "left")
    act.exit_room(e, "up")
    act.ride_platform(e, (136, 72), (120, 24), axis="y")
    act.exit_room(e, "left")
    act.unlock(e, (10, 7), "down")
    act.exit_room(e, "down")
    act.fight(e)


@R.step(done=lambda e: ram.has(e, "BRACELET"), note="17 Moblins + key door; 1b blocks; 1f; light 1b's torches; "
        "the bracelet is in a sidescrolling room")
def d1_bracelet(e):
    act.exit_room(e, "left")
    act.fight(e)
    act.unlock(e, (10, 3), "down")
    act.exit_room(e, "down")
    act.push_tile(e, (8, 2), "down")
    act.push_tile(e, (8, 4), "down")
    act.push_tile(e, (8, 3), "right")
    act.exit_room(e, "down")
    act.fight(e)
    act.exit_room(e, "up", span=(140, 230))  # 1b's torch half
    act.fight(e)
    act.burn(e, (1, 10))
    act.burn(e, (1, 12))
    act.enter(e, (2, 11), "down")
    y = lambda e: ram.link_px(e)[0]  # noqa: E731
    x = lambda e: ram.link_px(e)[1]  # noqa: E731
    act.hold_until(e, "down", lambda e: y(e) >= 130, what="down the left ladder")
    act.hold_until(e, "right", lambda e: x(e) >= 199, what="along the bottom")
    act.hold_until(e, "up", lambda e: y(e) <= 90, what="up the right ladder")
    act.hold_until(e, "left", lambda e: ram.has(e, "BRACELET") or ram.text_active(e), what="to the bracelet")
    act.settle(e, quiet=30)
    act.hold_until(e, "right", lambda e: x(e) >= 199, what="back to the right ladder")
    act.hold_until(e, "down", lambda e: y(e) >= 130, what="down the right ladder")
    act.hold_until(e, "left", lambda e: x(e) <= 41, what="along the bottom")
    before = ram.room(e)
    act.hold_until(e, "up", lambda e: ram.room(e) != before, what="up and out")
    act.settle(e, quiet=30)


@R.step(done=lambda e: ram.u8(e, "wDungeonBossKeys") & (1 << D1), note="22: pot onto the button; 23: chest")
def d1_boss_key(e):
    act.exit_room(e, "down", span=(140, 230))
    act.exit_room(e, "down", span=(16, 90))  # lifting pots out of the way
    act.push_tile(e, (5, 9), "right")
    act.push_tile(e, (5, 10), "right")
    act.exit_room(e, "right")
    act.fight(e)
    act.open_chest(e, (1, 6))


@R.step(done=lambda e: ram.essences(e) >= 1, note="miniboss warp in the entrance; 12 Wallmasters (don't linger); "
        "Pumpkin Head")
def d1_boss(e):
    act.exit_room(e, "right")
    before = ram.room(e)
    act.walk_to(e, (88, 120), leave_ok=True, stop_on_scene=True)  # warp to the miniboss room
    act.wait_until(e, lambda e: ram.room(e) != before, 300, "warp")
    act.settle(e, quiet=30)
    act.travel(e, "up", "up")
    act.unlock(e, (7, 14), "right")
    before = ram.room(e)
    act.hold_until(e, "right", lambda e: ram.room(e) != before, 120, "through the boss door")
    act.settle(e, quiet=30)
    bosses.pumpkin_head(e)
    act.wait_until(e, lambda e: any(o.id == act.INTERAC_TREASURE for o in ram.objects(e, "interaction")), 600,
                   "heart container")
    act.pickup(e)
    act.exit_room(e, "up")
    act.walk_to(e, lambda y, x: abs(y - 52) <= 4 and abs(x - 120) <= 3, stop_on_scene=True)
    if ram.controllable(e):
        act.hold(e, "up", 30)
    act.play_until(e, lambda e: ram.essences(e) >= 1, what="Eternal Spirit")
    act.settle(e, quiet=120)


R.mark("04_after_d1", release=True, expect=lambda e: ram.essences(e) == 1)
