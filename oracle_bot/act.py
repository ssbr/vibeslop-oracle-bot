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


def settle(e: Emu, choices: Sequence[int] = (), max_frames: int = 60 * 60, quiet: int = 1) -> None:
    """Advance text/cutscenes until Link has been controllable for `quiet` consecutive frames. Option prompts
    consume `choices` in order; an option prompt with no choice left raises Stuck (blindly accepting the
    default is never safe)."""
    choices = list(choices)
    start = e.frame
    calm = 0
    while calm < quiet:
        if ram.controllable(e):
            calm += 1
            e.step()
            continue
        calm = 0
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


DIRS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def steer(dy: int, dx: int) -> str:
    """Buttons that move Link by (dy, dx)."""
    parts = []
    if dy:
        parts.append("down" if dy > 0 else "up")
    if dx:
        parts.append("right" if dx > 0 else "left")
    return "+".join(parts)


def walk_to(e: Emu, goal, allow: frozenset[str] = frozenset(), tol: int = 1, max_frames: int = 1800,
            settle_text: bool = True, leave_ok: bool = False) -> None:
    """Walk Link to `goal`: a (y, x) pixel target or a predicate goal(y, x). Plans with nav.path and follows
    the path closed-loop, replanning when progress stalls. Leaves buttons released."""
    from . import nav  # local import: nav imports ram, act is imported by menus

    target = None if callable(goal) else goal
    reached = goal if callable(goal) else (lambda y, x: abs(y - target[0]) <= tol and abs(x - target[1]) <= tol)
    start_room = ram.room(e)
    deadline = e.frame + max_frames
    plan: list[tuple[int, int]] = []
    last_pos, still = None, 0
    replans = 0
    try:
        while True:
            if e.frame > deadline:
                raise Stuck(f"walk_to {goal}: out of time at {ram.link_px(e)}")
            if not ram.controllable(e):
                e.set_buttons(0)
                if ram.text_active(e) and not settle_text:
                    raise Stuck("walk_to: text appeared")
                if ram.text_active(e):
                    settle(e)
                else:
                    e.step()
                continue
            if ram.room(e) != start_room:
                if leave_ok:
                    return
                raise Stuck(f"walk_to: left room {start_room} -> {ram.room(e)}")
            pos = ram.link_px(e)
            if reached(*pos):
                return
            if pos == last_pos:
                still += 1
            else:
                last_pos, still = pos, 0
            if not plan or still > 12:
                g = nav.grid(e)
                avoid = [(o.y, o.x, 12) for o in ram.objects(e, "enemy")]
                plan = nav.path(g, pos, goal, allow, avoid, nav.blockers(e)) or []
                if not plan:
                    raise Stuck(f"walk_to: no path from {pos} to {goal}\n{nav.ascii(e, g)}")
                replans += 1 if still > 12 else 0
                if replans > 6:
                    raise Stuck(f"walk_to: no progress at {pos}\n{nav.ascii(e, g)}")
                still = 0
            # drop reached waypoints; steer toward the next one (or the exact target at the end)
            while len(plan) > 1 and abs(plan[0][0] - pos[0]) <= 2 and abs(plan[0][1] - pos[1]) <= 2:
                plan.pop(0)
            wy, wx = plan[0]
            if len(plan) == 1 and target is not None:
                wy, wx = target
            e.set_buttons(_mask(steer(wy - pos[0], wx - pos[1])))
            e.step()
            if len(plan) == 1 and pos == (wy, wx) and target is None:
                plan = []
    finally:
        e.set_buttons(0)


def _mask(buttons: str) -> int:
    return mask_of(buttons)


def exit_room(e: Emu, direction: str, allow: frozenset[str] = frozenset(), expect: tuple[int, int] | None = None,
              max_frames: int = 1800) -> None:
    """Walk off the screen edge in `direction` and wait for the next room to become controllable."""
    from . import nav

    g = nav.grid(e)
    H, W = g.h * 16, g.w * 16
    near = {"up": lambda y, x: y <= 4, "down": lambda y, x: y >= H - 8,
            "left": lambda y, x: x <= 4, "right": lambda y, x: x >= W - 4}[direction]
    before = ram.room(e)
    walk_to(e, near, allow, max_frames=max_frames, leave_ok=True)
    if ram.room(e) == before:
        e.set_buttons(mask_of(direction))
        try:
            wait_until(e, lambda e: ram.room(e) != before, 120, f"room change going {direction}")
        finally:
            e.set_buttons(0)
    wait_until(e, ram.controllable, 300, "control after room change")
    if expect is not None and ram.room(e) != expect:
        raise Stuck(f"exit {direction}: expected room {expect}, got {ram.room(e)}")


def travel(e: Emu, *hops: int | str, allow: frozenset[str] = frozenset()) -> None:
    """Cross overworld screen edges. Each hop is a direction or an adjacent room index in the current group."""
    for hop in hops:
        group, rm = ram.room(e)
        if isinstance(hop, str):
            exit_room(e, hop, allow)
            continue
        delta = hop - rm
        direction = {-16: "up", 16: "down", -1: "left", 1: "right"}.get(delta)
        if direction is None:
            raise ValueError(f"room {hop:02x} isn't adjacent to {rm:02x}")
        exit_room(e, direction, allow, expect=(group, hop))


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
