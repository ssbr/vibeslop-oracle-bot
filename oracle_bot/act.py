"""Low-level action primitives. All of them drive the emulator closed-loop and raise Stuck on failure."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from . import ram
from .emu import Emu, mask_of


class Stuck(Exception):
    pass


def tap(e: Emu, buttons: str, hold: int = 2, after: int = 4) -> None:
    e.set_buttons(mask_of(buttons))
    e.step(hold)
    e.set_buttons(0)
    e.step(after)


def hold(e: Emu, buttons: str, frames: int) -> None:
    e.set_buttons(mask_of(buttons))
    e.step(frames)
    e.set_buttons(0)


def wait_until(e: Emu, pred: Callable[[Emu], bool], max_frames: int, what: str = "condition") -> int:
    """Step (holding whatever is held) until pred(e). Returns frames waited."""
    for n in range(max_frames):
        if pred(e):
            return n
        e.step()
    if pred(e):
        return max_frames
    raise Stuck(f"timed out after {max_frames} frames waiting for {what}")


def settle(e: Emu, choices: Sequence[int] = (), max_frames: int = 60 * 60) -> None:
    """Advance text/cutscenes until Link is controllable. Option prompts consume `choices` in order;
    an option prompt with no choice left raises Stuck (blindly accepting the default is never safe)."""
    choices = list(choices)
    start = e.frame
    while not ram.controllable(e):
        if e.frame - start > max_frames:
            raise Stuck(f"settle: not controllable after {max_frames} frames\n{ram.summary(e)}")
        if ram.option_prompt(e) and text_done(e):
            if not choices:
                raise Stuck(f"settle: unexpected option prompt (text {ram.u8(e, 'wTextIndex'):02x})")
            choose_option(e, choices.pop(0))
        elif ram.text_active(e):
            tap(e, "a", hold=1, after=3)
        else:
            e.step()
    if choices:
        raise Stuck(f"settle: {len(choices)} unused choices")


def text_done(e: Emu) -> bool:
    """The current textbox has finished printing (waiting for input)."""
    return ram.u8(e, "w7TextStatus") & 0x80 != 0 or ram.option_prompt(e)


def choose_option(e: Emu, index: int) -> None:
    for _ in range(8):
        cur = ram.u8(e, "wSelectedTextOption")
        if cur == index:
            break
        tap(e, "right" if cur < index else "left", hold=1, after=4)
    else:
        raise Stuck(f"could not select option {index}")
    tap(e, "a", hold=1, after=4)
