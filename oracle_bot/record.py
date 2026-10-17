"""Replay log: the single source of truth for a run.

A log is a header plus ops `(frame, op, args)`. Ops at frame f are applied before frame f is emulated:
  J <mask>                       held buttons (game bit order) from this frame on
  W <bank>:<addr> <hex> <tag>    memory write (bank "-" = unbanked)
  C <name> <memhash>             checkpoint marker
  N <text>                       note (ignored by playback)
  E                              end of run
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

VERSION = 1


@dataclass
class Op:
    frame: int
    op: str
    args: str = ""

    def line(self) -> str:
        return f"{self.frame} {self.op} {self.args}".rstrip()


@dataclass
class Log:
    header: dict[str, str]
    ops: list[Op] = field(default_factory=list)

    @classmethod
    def new(cls, rom: Path, pyboy_version: str) -> Log:
        sha1 = hashlib.sha1(rom.read_bytes()).hexdigest()
        return cls({"rom_sha1": sha1, "pyboy": pyboy_version, "cgb": "1", "sound": "1", "sram": "zero8k"})

    def add(self, frame: int, op: str, args: str = "") -> None:
        assert not self.ops or frame >= self.ops[-1].frame, "log is append-only"
        self.ops.append(Op(frame, op, args))

    def truncate(self, frame: int) -> None:
        """Drop every op at or after `frame` (used when rewinding to a state saved at `frame`)."""
        while self.ops and self.ops[-1].frame >= frame:
            self.ops.pop()

    def end_frame(self) -> int:
        ends = [op.frame for op in self.ops if op.op == "E"]
        return ends[-1] if ends else (self.ops[-1].frame if self.ops else 0)

    def marks(self) -> list[Op]:
        return [op for op in self.ops if op.op == "C"]

    def has_dev_writes(self) -> bool:
        return any(op.op == "W" and op.args.endswith(" dev") for op in self.ops)

    def text(self) -> str:
        head = f"#obot-replay {VERSION} " + " ".join(f"{k}={v}" for k, v in self.header.items())
        return "\n".join([head, *(op.line() for op in self.ops)]) + "\n"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.text())
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> Log:
        lines = path.read_text().splitlines()
        magic, version, *pairs = lines[0].split()
        assert magic == "#obot-replay" and int(version) == VERSION, lines[0]
        log = cls(dict(p.split("=", 1) for p in pairs))
        for line in lines[1:]:
            frame, op, *rest = line.split(" ", 2)
            log.ops.append(Op(int(frame), op, rest[0] if rest else ""))
        return log
