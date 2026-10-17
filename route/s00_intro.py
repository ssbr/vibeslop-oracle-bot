"""New game through the Forest of Time intro: Impa, the ▲ stone, Nayru, the Wooden Sword."""

from oracle_bot import act, menus, ram
from oracle_bot.runner import Route

from .common import CFG

R = Route()

INTERAC_IMPA = 0x31
INTERAC_TRIFORCE_STONE = 0x34
INTERAC_NAYRU = 0x36
ANIMALS = (0x39, 0x3C, 0x4B, 0x4C)  # monkey, boy, rabbit, bird: each sets a bit the bear waits for
INTERAC_BEAR = 0x5D


@R.step(done=lambda e: ram.u8(e, "wGameState") == 2 and ram.name(e) == CFG.file_name)
def new_game(e):
    menus.new_game(e, CFG.file_name, CFG.message_speed)
    act.settle(e)


@R.step(done=lambda e: ram.room_flag(e, 0, 0x6A, 0x40), note="Impa is attacked by fake octoroks; walking near starts it")
def meet_impa(e):
    act.travel(e, 0x7A, 0x6A)
    act.walk_to(e, (72, 72), stop_on_scene=True)
    act.play_until(e, lambda e: ram.room_flag(e, 0, 0x6A, 0x40), what="octoroks flee")
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.room_flags(e, 0, 0x59) & 0xC0, note="Impa asks Link to push the ▲ stone (direction is cosmetic)")
def push_triforce_stone(e):
    act.travel(e, 0x5A, 0x59)
    act.walk_to(e, (60, 56), stop_on_scene=True)
    act.play_until(e, lambda e: e.u8(0xCFD0) == 4, what="Impa gives up on the stone")
    act.settle(e, quiet=30)
    act.push_object(e, INTERAC_TRIFORCE_STONE, CFG.stone_push)
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.room_flag(e, 0, 0x39, 0x80), note="the bear moves once all animals have been talked to")
def move_bear(e):
    act.travel(e, 0x49, 0x39)
    for animal in (*ANIMALS, INTERAC_BEAR):
        act.talk(e, animal, quiet=30)
    act.settle(e, quiet=60)


@R.step(done=lambda e: ram.has(e, "SWORD") and ram.gflag(e, "INTRO_DONE"),
        note="Nayru sings, Veran possesses her; Impa hands over the Wooden Sword")
def get_sword(e):
    act.walk_to(e, lambda y, x: y <= 48 and 96 <= x <= 120, stop_on_scene=True)
    act.play_until(e, lambda e: ram.has(e, "SWORD"), what="Nayru cutscene")
    act.settle(e, quiet=60)
