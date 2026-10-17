"""Route execution: steps with done-predicates, a dev snapshot after every item, checkpoints at marks."""

from __future__ import annotations

import json
import shutil
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

from . import cheats, menus, nav, ram, video
from .act import Stuck, settle
from .config import Config
from .emu import Emu, load_snapshot, save_snapshot
from .record import Log, Op, validate_sav


@dataclass
class Step:
    name: str
    fn: Callable[[Emu], None]
    done: Callable[[Emu], bool] | None = None
    note: str = ""
    human: bool = False  # needs a human (boss etc.) until automated
    cheats: bool = True  # False suspends cheats during this step (e.g. while Tokays steal items)
    retries: int = 2


@dataclass
class Mark:
    name: str
    release: bool = False  # release checkpoint: in-game save + exported .sav
    expect: Callable[[Emu], bool] | None = None


@dataclass
class Route:
    """A segment of the route: steps run in definition order."""

    items: list[Step | Mark] = field(default_factory=list)
    cfg: Config | None = None

    def step(self, done: Callable[[Emu], bool] | None = None, note: str = "", human: bool = False,
             cheats: bool = True, retries: int = 2):
        def deco(fn: Callable[[Emu], None]):
            self.items.append(Step(fn.__name__, fn, done, note, human, cheats, retries))
            return fn
        return deco

    def mark(self, name: str, release: bool = False, expect: Callable[[Emu], bool] | None = None) -> None:
        self.items.append(Mark(name, release, expect))


class Failed(Exception):
    pass


class Runner:
    def __init__(self, items: list[Step | Mark], run_dir: Path, cfg: Config, interactive: bool = False):
        self.items = items
        self.run_dir = run_dir
        self.cfg = cfg
        self.interactive = interactive
        self.cheats = cheats.Cheats(cfg.cheat_health, cfg.cheat_ammo)
        names = [it.name for it in items]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate route item names: {dupes}")

    def index(self, name: str) -> int:
        for i, it in enumerate(self.items):
            if it.name == name:
                return i
        raise KeyError(f"no route item named {name!r}")

    def snap_path(self, i: int) -> Path:
        return self.run_dir / "states" / f"{i:03d}_{self.items[i].name}"

    def attach(self, e: Emu) -> Emu:
        e.before_frame.append(self.cheats)
        return e

    def start(self, start: str | None) -> tuple[Emu, int]:
        if start is None:
            return self.attach(Emu()), 0
        i = self.index(start)
        if i == 0:
            return self.attach(Emu()), 0
        snap = self.snap_path(i - 1)
        if not snap.with_suffix(".state").exists():
            raise Failed(f"no snapshot after {self.items[i - 1].name!r} in {self.run_dir}; run up to it first")
        return self.attach(load_snapshot(snap)), i

    def run(self, start: str | None = None, stop: str | None = None) -> Emu:
        e, i = self.start(start)
        last = self.index(stop) if stop else len(self.items) - 1
        while i <= last:
            item = self.items[i]
            print(f"[{i:03d}] {item.name}  (frame {e.frame})", flush=True)
            if isinstance(item, Mark):
                self.do_mark(e, item)
            else:
                self.do_step(e, item)
            save_snapshot(e, self.snap_path(i))
            i += 1
        final = Log(e.log.header, [*e.log.ops, Op(e.frame, "E")])
        final.save(self.run_dir / "replay.log")
        return e

    def do_step(self, e: Emu, step: Step) -> None:
        if step.done and step.done(e):
            e.note(f"skip {step.name} (already done)")
            return
        pre = (e.state(), e.frame, len(e.log.ops))
        for attempt in range(step.retries + 1):
            e.note(f"step {step.name}" + (f" attempt {attempt + 1}" if attempt else ""))
            self.cheats.suspended = not step.cheats
            try:
                if step.human:
                    raise Stuck("human step (not automated yet)")
                step.fn(e)
                if step.done and not step.done(e):
                    settle(e, quiet=30)
                    if not step.done(e):
                        raise Stuck(f"{step.name}: finished but done() is false")
                return
            except Stuck as err:
                self.stuck_bundle(e, step, err, attempt, pre)
                if attempt == step.retries:
                    raise Failed(f"step {step.name} failed: {str(err).splitlines()[0]}") from err
                # Emulation is deterministic: retry from the pre-step state after a short, different delay.
                e.load(*pre)
                e.step(13 * (attempt + 1))
            finally:
                self.cheats.suspended = False

    def stuck_bundle(self, e: Emu, step: Step, err: Exception, attempt: int,
                     pre: tuple[bytes, int, int]) -> None:
        d = self.run_dir / "stuck" / f"{step.name}_{attempt}"
        d.mkdir(parents=True, exist_ok=True)
        e.set_buttons(0)
        save_snapshot(e, d / "snap")
        # The last 15 seconds before getting stuck, re-rendered from the pre-step state.
        video.render(e.log, max(pre[1], e.frame - 900), e.frame, d / "clip", base=pre)
        Image.fromarray(e.screen()).resize((320, 288), Image.NEAREST).save(d / "screen.png")
        tail = "\n".join(op.line() for op in e.log.ops[-200:])
        (d / "inspect.txt").write_text(
            f"step {step.name} attempt {attempt}: {err}\n\n{traceback.format_exc()}\n{ram.summary(e)}\n"
            f"{nav.ascii(e)}\n\nlast ops:\n{tail}\n", encoding="utf-8")
        print(f"  STUCK ({attempt}): {str(err).splitlines()[0]}  -> {d}", flush=True)

    def do_mark(self, e: Emu, mark: Mark) -> None:
        e.set_buttons(0)
        if mark.expect and not mark.expect(e):
            raise Failed(f"mark {mark.name}: expectation failed\n{ram.summary(e)}")
        if mark.release:
            self.release_checkpoint(e, mark)
        e.log.add(e.frame, "C", f"{mark.name} {e.mem_hash()}")

    def release_checkpoint(self, e: Emu, mark: Mark) -> None:
        problems = cheats.sanity(e)
        if problems:
            raise Failed(f"mark {mark.name}: state looks wrong: {problems}")
        if self.cfg.export_rupees is not None:
            ram.poke(e, "wNumRupees", ram.to_bcd(self.cfg.export_rupees, 2), "rupees")
        # A loaded save resumes at wDeathRespawnBuffer (normally the last door Link used): point it here.
        g, r = ram.room(e)
        y, x = ram.link_px(e)
        respawn = bytes([g, r, ram.u8(e, "wRoomStateModifier"), ram.u8(e, "w1Link.direction"), y, x])
        ram.poke(e, "wDeathRespawnBuffer", respawn, "respawn")
        menus.save_game(e)
        sram = e.sram()
        sav_problems = validate_sav(sram) or boot_check(sram, (g, r), (y, x))
        if sav_problems:
            raise Failed(f"mark {mark.name}: exported save invalid: {sav_problems}")
        d = self.run_dir / "checkpoints" / mark.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "game.sav").write_bytes(sram)
        (d / "state.pyboy").write_bytes(e.state())
        Image.fromarray(e.screen()).resize((320, 288), Image.NEAREST).save(d / "screen.png")
        g, r = ram.room(e)
        hp, hmax = ram.health(e)
        meta = {
            "name": mark.name, "frame": e.frame, "n_ops": len(e.log.ops), "mem_hash": e.mem_hash(),
            "header": e.log.header, "config": asdict(self.cfg),
            "summary": {"room": f"{g}:{r:02x}", "hearts": f"{hp / 4:g}/{hmax / 4:g}", "essences": ram.essences(e),
                        "rupees": ram.rupees(e), "name": ram.name(e),
                        "items": [k[9:] for k, v in ram.TREASURES.items() if v and ram.has(e, k)]},
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2))
        e.log.save(d / "replay.log")
        print(f"  checkpoint -> {d}", flush=True)


def boot_check(sram: bytes, room: tuple[int, int], pos: tuple[int, int]) -> list[str]:
    """Load the exported save in a fresh emulator and check Link appears where the checkpoint was taken."""
    e = Emu(sram=sram)
    try:
        menus.load_game(e)
    except Stuck as err:
        return [f"boot: {err}"]
    finally:
        e.close()
    got_room, got_pos = ram.room(e), ram.link_px(e)
    if got_room != room or abs(got_pos[0] - pos[0]) + abs(got_pos[1] - pos[1]) > 4:
        return [f"boot: loads at {got_room} {got_pos}, expected {room} {pos}"]
    return []


def promote(run_dir: Path, dest: Path) -> None:
    """Copy a verified run's checkpoints and log into the canonical checkpoints/ directory."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run_dir / "checkpoints", dest)
    shutil.copy(run_dir / "replay.log", dest / "replay.log")
