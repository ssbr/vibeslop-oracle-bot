"""PyBoy wrapper. Every input change and memory write goes through here and is logged."""

from __future__ import annotations

import hashlib
import io
import warnings
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="Using SDL2 binaries")
from pyboy import PyBoy  # noqa: E402

from .record import Log, Op

ROOT = Path(__file__).resolve().parent.parent
ROM = ROOT / "roms" / "oracle_of_ages.gbc"
SRAM_SIZE = 0x2000

# The game's joypad bit order (wKeysPressed): A=01 B=02 Select=04 Start=08 Right=10 Left=20 Up=40 Down=80.
BUTTONS = ("a", "b", "select", "start", "right", "left", "up", "down")
BIT = {name: 1 << i for i, name in enumerate(BUTTONS)}


def mask_of(buttons: str) -> int:
    """'a+up' -> mask. Empty string -> 0."""
    return sum(BIT[b] for b in buttons.split("+") if b)


class Emu:
    def __init__(self, log: Log | None = None, rom: Path = ROM, sram: bytes | None = None):
        """`sram` boots with an existing battery save (only for inspecting exported saves; replays always
        start from zeroed SRAM)."""
        self.rom = rom
        self.log = log if log is not None else Log.new(rom, version("pyboy"))
        self.pyboy = PyBoy(
            str(rom), window="null", sound_emulated=True, cgb=True,
            ram_file=io.BytesIO(sram if sram is not None else bytes(SRAM_SIZE)), log_level="ERROR",
        )
        self.frame = 0
        self.mask = 0
        self.rendered = False  # whether screen() reflects the current frame
        self.before_frame: list[Callable[[Emu], None]] = []
        self.after_frame: list[Callable[[Emu], None]] = []

    # --- input / writes (logged) ---

    def set_buttons(self, mask: int) -> None:
        if mask == self.mask:
            return
        self.log.add(self.frame, "J", f"{mask:02x}")
        self._apply_mask(mask)

    def _apply_mask(self, mask: int) -> None:
        for i, name in enumerate(BUTTONS):
            bit = 1 << i
            if (mask ^ self.mask) & bit:
                (self.pyboy.button_press if mask & bit else self.pyboy.button_release)(name)
        self.mask = mask

    def poke(self, addr: int, data: int | bytes, bank: int | None = None, tag: str = "dev") -> None:
        data = bytes([data]) if isinstance(data, int) else bytes(data)
        self.log.add(self.frame, "W", f"{'-' if bank is None else bank}:{addr:04x} {data.hex()} {tag}")
        self._write(addr, data, bank)

    def _write(self, addr: int, data: bytes, bank: int | None) -> None:
        check_bank(addr, bank)
        for i, b in enumerate(data):
            if bank is None:
                self.pyboy.memory[addr + i] = b
            else:
                self.pyboy.memory[bank, addr + i] = b

    def note(self, text: str) -> None:
        self.log.add(self.frame, "N", text)

    # --- stepping ---

    def step(self, n: int = 1, render: bool = False) -> None:
        """Emulate n frames. With render, the last frame is drawn so screen() is current."""
        for i in range(n):
            for hook in self.before_frame:
                hook(self)
            last = i == n - 1
            self.pyboy.tick(1, render and last, False)
            self.frame += 1
            self.rendered = render and last
            for hook in self.after_frame:
                hook(self)

    # --- reads ---

    def read(self, addr: int, n: int = 1, bank: int | None = None) -> bytes:
        check_bank(addr, bank)
        m = self.pyboy.memory
        return bytes(m[addr:addr + n] if bank is None else m[bank, addr:addr + n])

    def u8(self, addr: int, bank: int | None = None) -> int:
        check_bank(addr, bank)
        return self.pyboy.memory[addr] if bank is None else self.pyboy.memory[bank, addr]

    def sram(self) -> bytes:
        m = self.pyboy.memory
        # A banked slice ending exactly at 0xC000 raises in PyBoy 2.8.1, so read the last byte separately.
        return bytes(m[0, 0xA000:0xBFFF]) + bytes([m[0, 0xBFFF]])

    def mem_hash(self) -> str:
        """Hash of all game-visible RAM: WRAM banks 0-7, HRAM, VRAM banks 0-1, OAM, cartridge RAM."""
        m = self.pyboy.memory
        h = hashlib.blake2b(digest_size=12)
        h.update(bytes(m[0xC000:0xD000]))
        for bank in range(1, 8):
            h.update(bytes(m[bank, 0xD000:0xDFFF]) + bytes([m[bank, 0xDFFF]]))
        for bank in range(2):
            h.update(bytes(m[bank, 0x8000:0x9FFF]) + bytes([m[bank, 0x9FFF]]))
        h.update(bytes(m[0xFE00:0xFEA0]))
        h.update(bytes(m[0xFF80:0xFFFF]))
        h.update(self.sram())
        return h.hexdigest()

    def screen(self) -> np.ndarray:
        """Current frame as (144, 160, 3) RGB. Steps one rendered frame if the last frame wasn't drawn."""
        if not self.rendered:
            self.step(1, render=True)
        return self.pyboy.screen.ndarray[:, :, :3].copy()

    # --- states (caches; the log is the source of truth) ---

    def state(self) -> bytes:
        assert self.mask == 0, "states are only taken with all buttons released"
        buf = io.BytesIO()
        self.pyboy.save_state(buf)
        return buf.getvalue()

    def load(self, blob: bytes, frame: int, n_ops: int | None = None) -> None:
        """Restore a state taken at `frame`, when the log had `n_ops` ops (later ops are discarded;
        without n_ops, ops at or after `frame` are)."""
        self.pyboy.load_state(io.BytesIO(blob))
        for name in BUTTONS:  # joypad state is not part of PyBoy states
            self.pyboy.button_release(name)
        self.mask = 0
        self.frame = frame
        self.rendered = False
        if n_ops is None:
            self.log.truncate(frame)
        else:
            del self.log.ops[n_ops:]

    def close(self) -> None:
        self.pyboy.stop(save=False)


def replay(log: Log, until: int | None = None, on_op: Callable[[Emu, Op], None] | None = None) -> Emu:
    """Re-simulate a log from power-on. Stops at `until` (a frame) or at the end. Returns the emulator."""
    emu = Emu()
    for op in log.ops:
        if until is not None and op.frame >= until:
            break
        emu.step(op.frame - emu.frame)
        if op.op == "J":
            emu.set_buttons(int(op.args, 16))
        elif op.op == "W":
            where, data, tag = op.args.split(" ")
            bank, addr = where.split(":")
            emu.poke(int(addr, 16), bytes.fromhex(data), None if bank == "-" else int(bank), tag)
        elif op.op == "N":
            emu.note(op.args)
        elif op.op == "C":
            emu.log.add(emu.frame, "C", op.args)
        if on_op:
            on_op(emu, op)
    if until is not None:
        emu.step(until - emu.frame)
    return emu


def check_bank(addr: int, bank: int | None) -> None:
    if 0xD000 <= addr < 0xE000 and bank is None:
        raise ValueError(f"${addr:04x} is in switchable WRAM; pass an explicit bank")


def save_snapshot(e: Emu, path: Path) -> None:
    """Write `<path>.state`, `.log` and `.json`: everything needed to resume (and replay) from here."""
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".state").write_bytes(e.state())
    e.log.save(path.with_suffix(".log"))
    path.with_suffix(".json").write_text(json.dumps({"frame": e.frame, "n_ops": len(e.log.ops)}))


def load_snapshot(path: Path) -> Emu:
    import json

    meta = json.loads(path.with_suffix(".json").read_text())
    e = Emu(log=Log.load(path.with_suffix(".log")))
    e.load(path.with_suffix(".state").read_bytes(), meta["frame"], meta["n_ops"])
    return e
