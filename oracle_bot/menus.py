"""Menu drivers: title / file creation, name entry, save menu."""

from __future__ import annotations

from . import ram
from .act import Stuck, tap, wait_until
from .emu import Emu

# Name-entry grid as the cursor sees it ($CBBC: row in the high nibble, column in the low nibble).
# Row 5 is the ◄ ► OK row; START jumps straight to OK.
NAME_GRID = ["ABCDEFabcdef", "GHIJKLghijkl", "MNOPQRmnopqr", "STUVWXstuvwx", "YZ    yz    "]


def name_cursor(e: Emu) -> tuple[int, int]:
    v = ram.u8(e, "wFileSelect.cursorPos")
    return v >> 4, v & 15


def enter_name(e: Emu, text: str) -> None:
    """Type `text` on a name-entry screen (cursor at the start) and confirm with OK."""
    if not 1 <= len(text) <= 5:
        raise ValueError(f"names are 1-5 characters: {text!r}")
    for ch in text:
        row = next((i for i, r in enumerate(NAME_GRID) if ch in r and ch != " "), None)
        if row is None:
            raise ValueError(f"character {ch!r} isn't on the name-entry grid")
        target = (row, NAME_GRID[row].index(ch))
        for _ in range(30):
            r, c = name_cursor(e)
            if (r, c) == target:
                break
            tap(e, "down" if r < target[0] else "up" if r > target[0] else "right" if c < target[1] else "left",
                after=6)
        else:
            raise Stuck(f"name cursor stuck at {name_cursor(e)}")
        typed = ram.u8(e, "wFileSelect.textInputCursorPos")
        tap(e, "a", after=6)
        if ram.u8(e, "wFileSelect.textInputCursorPos") == typed:
            raise Stuck(f"typing {ch!r} had no effect")
    tap(e, "start", after=20)  # cursor to OK
    tap(e, "a", after=30)


def new_game(e: Emu, name: str, message_speed: int = 3) -> None:
    """From power-on: skip the intro, create file 1 named `name` and start playing."""
    e.step(400)
    tap(e, "start", after=120)  # intro -> title
    tap(e, "start", after=120)  # title -> file select
    if ram.u8(e, "wFileSelect.mode") != 1:
        raise Stuck("expected file select")
    tap(e, "a", after=90)  # file 1 -> new game / secrets / game link
    tap(e, "a", after=90)  # NEW GAME -> name entry
    enter_name(e, name)
    wait_until(e, lambda e: ram.name(e) == name, 120, "name stored")
    tap(e, "a", after=90)  # pick file 1 -> message speed
    for _ in range(8):  # message speed cursor: 1..5 left to right (default 3)
        cur = ram.u8(e, "wTextSpeed") + 1
        if cur == message_speed:
            break
        tap(e, "right" if cur < message_speed else "left", after=8)
    tap(e, "a", after=10)
    wait_until(e, lambda e: ram.u8(e, "wGameState") == 2, 600, "game start")
