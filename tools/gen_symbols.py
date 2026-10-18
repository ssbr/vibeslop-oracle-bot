"""Generate oracle_bot/data/ages.json (and ages_text.json) from the oracles-disasm sources in vendor/oracles-disasm.

These files are derived from the disassembly and the game, so they aren't distributed: generate them locally from
a clone of https://github.com/Stewmath/oracles-disasm at commit 21c924afdc8a13225e849214479d5113da2ec226.

RAM label addresses are computed by laying out the RAMSECTIONs/ENUMs/STRUCTs like the assembler does (with
ROM_AGES defined), then cross-checked against the hand-written `; $xxxx` address comments in wram.s.
Constants come from `.define`s and `.enum`s in constants/.

Usage: uv run python tools/gen_symbols.py [--disasm vendor/oracles-disasm]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFINES = {"ROM_AGES", "REGION_US", "BUILD_VANILLA"}
# Labels whose wram.s comment is wrong (swapped/misnumbered in the disasm); the computed layout is authoritative.
KNOWN_BAD_COMMENTS = {"wcc72", "wcc73", "w7CharacterDisplayLength"}

SIZES = {"db": 1, "dw": 2, ".db": 0, ".dw": 0}
LABEL_RE = re.compile(r"^(\.?[A-Za-z_][\w.]*)(:?)\s*(.*)$")
ADDR_COMMENT_RE = re.compile(r";\s*\$([0-9a-fA-F]{4})\b")


def num(tok: str) -> int:
    tok = tok.strip()
    if tok.startswith("$"):
        return int(tok[1:], 16)
    if tok.lower().startswith("0x"):
        return int(tok, 16)
    if tok.startswith("%"):
        return int(tok[1:], 2)
    return int(tok)


class Layout:
    """Assembler-style layout of RAM sections, enums and structs."""

    def __init__(self, section_origins: dict[str, int], appendto: dict[str, str]):
        self.origins = section_origins
        self.appendto = appendto
        self.section_ends: dict[str, int] = {}
        self.labels: dict[str, tuple[int | None, int]] = {}  # name -> (bank, addr)
        self.structs: dict[str, dict[str, int]] = {}
        self.struct_sizes: dict[str, int] = {}
        self.defines: dict[str, int] = {}
        self.comments: dict[str, int] = {}  # label -> address from its comment (for cross-checking)

    def eval(self, expr: str) -> int | None:
        expr = expr.split(";")[0].strip()
        if not expr:
            return None

        def sub(m: re.Match) -> str:
            tok = m.group(0)
            if tok[0] == "$" or tok[0].isdigit() or tok[0] == "%":
                return str(num(tok))
            if tok in self.defines:
                return str(self.defines[tok])
            if tok in self.labels:
                return str(self.labels[tok][1])
            raise KeyError(tok)

        try:
            py = re.sub(r"\$[0-9a-fA-F]+|%[01]+|\b\d+\b|[A-Za-z_][\w.]*", sub, expr)
            py = py.replace("<", "0xff&").replace(">", "0xff&0x100**0//0x100*")  # rare; '<' = low byte
            if not re.fullmatch(r"[\d\s+\-*/()&x]+", py):
                return None
            return int(eval(py))  # noqa: S307 - digits and operators only
        except (KeyError, SyntaxError, ZeroDivisionError):
            return None

    def parse(self, text: str) -> None:
        cond: list[bool] = []
        block: str | None = None  # "section" | "enum" | "struct"
        name = ""
        bank: int | None = None
        addr = 0
        unions: list[list] = []  # [start, max_end, prefix]
        struct_fields: dict[str, int] = {}

        for raw in text.splitlines():
            line = raw.split(";", 1)[0].strip()
            low = line.lower()
            # conditionals
            if low.startswith(".ifdef") or low.startswith(".ifndef"):
                sym = line.split()[1]
                val = sym in DEFINES
                cond.append(val if low.startswith(".ifdef") else not val)
                continue
            if low.startswith(".if "):
                py = re.sub(r"defined\((\w+)\)", lambda m: str(m.group(1) in DEFINES), line[4:])
                py = py.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
                cond.append(bool(eval(py)))  # noqa: S307 - only True/False/and/or/not remain
                continue
            if low.startswith(".else"):
                cond[-1] = not cond[-1]
                continue
            if low.startswith(".endif"):
                cond.pop()
                continue
            if not all(cond) or not line:
                continue

            if low.startswith(".define"):
                m = re.match(r"\.define\s+([\w.]+)\s*,?\s*(.*)", line, re.I)
                if m:
                    val = self.eval(m.group(2))
                    if val is None:
                        c = ADDR_COMMENT_RE.search(raw)
                        val = int(c.group(1), 16) if c else None
                    if val is not None:
                        self.defines[m.group(1)] = val
                continue
            if low.startswith(".ramsection"):
                parts = line.split()
                block, name = "section", parts[1]
                bank = None
                if "BANK" in [p.upper() for p in parts]:
                    bank = int(parts[[p.upper() for p in parts].index("BANK") + 1])
                if name in self.appendto:
                    addr = self.section_ends[self.appendto[name]]
                elif name in self.origins:
                    addr = self.origins[name]
                else:
                    addr = 0xD000  # banked sections without an explicit origin start at the slot
                continue
            if low.startswith(".endst"):
                self.structs[name] = struct_fields
                self.struct_sizes[name] = addr
                self.defines[f"{name}.size"] = addr
                block = None
                continue
            if low == ".ends":
                self.section_ends[name] = addr
                block = None
                continue
            if low.startswith(".enum"):
                block = "enum"
                addr = self.eval(line.split()[1])
                bank = 1 if 0xD000 <= addr < 0xE000 else None  # the only RAM enums there are bank-1 objects
                continue
            if low.startswith(".ende"):
                block = None
                continue
            if low.startswith(".struct"):
                block, name, addr, struct_fields = "struct", line.split()[1], 0, {}
                continue
            if block is None:
                continue
            if low.startswith(".union"):
                parts = line.split()
                unions.append([addr, addr, parts[1] if len(parts) > 1 else None])
                continue
            if low.startswith(".nextu"):
                parts = line.split()
                u = unions[-1]
                u[1] = max(u[1], addr)
                u[2] = parts[1] if len(parts) > 1 else None
                addr = u[0]
                continue
            if low.startswith(".endu"):
                u = unions.pop()
                addr = max(u[1], addr)
                continue

            m = LABEL_RE.match(line)
            if not m:
                continue
            first, _colon, rest = m.groups()
            if first.lower() in SIZES or first.lower() in ("dsb", "dsw", "instanceof"):
                directive = line
            else:
                prefix = ".".join(u[2] for u in unions if u[2])
                label = f"{prefix}.{first}" if prefix else first
                if block == "struct":
                    struct_fields[label] = addr
                else:
                    self.labels[label] = (bank, addr)
                    c = ADDR_COMMENT_RE.search(raw)
                    if c and "-/$" not in raw:
                        self.comments[label] = int(c.group(1), 16)
                directive = rest
                if directive.lower().startswith("instanceof"):
                    sname = directive.split()[1]
                    for field, off in self.structs[sname].items():
                        if block == "struct":
                            struct_fields[f"{label}.{field}"] = addr + off
                        else:
                            self.labels[f"{label}.{field}"] = (bank, addr + off)
            addr += self.size_of(directive)

    def size_of(self, directive: str) -> int:
        parts = directive.split()
        if not parts:
            return 0
        op = parts[0].lower()
        if op in SIZES:
            return SIZES[op]
        if op == "dsb":
            return self.eval(parts[1])
        if op == "dsw":
            return 2 * self.eval(parts[1])
        if op == "instanceof":
            count = self.eval(parts[2]) if len(parts) > 2 else 1
            return self.struct_sizes[parts[1]] * count
        raise ValueError(f"unknown directive: {directive}")


def parse_mode_table(path: Path, consts: dict[str, int]) -> dict[int, list[list[int]]]:
    """Parse a tile-property table indexed by collision mode (wActiveCollisions 0-5): a `.dw`/`dbrel` list of
    labels, then `.db` rows per label (stacked labels share rows), each list ended by `.db $00`."""
    order: list[str] = []
    rows: dict[str, list[list[int]]] = {}
    pending: list[str] = []
    current: list[str] = []

    def val(tok: str) -> int:
        out = 0
        for part in tok.strip().rstrip(",").split("|"):
            out |= consts[part] if part in consts else num(part)
        return out

    for raw in path.read_text().splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"(?:\.dw|dbrel)\s+(@\w+)", line)
        if m and not current:
            order.append(m.group(1))
            continue
        m = re.match(r"(@\w+):$", line)
        if m:
            rows[m.group(1)] = []
            # A label in the middle of a list falls through: it shares the rest of that list.
            (current if current else pending).append(m.group(1))
            continue
        if line.startswith(".db") and (pending or current):
            if pending:
                current, pending = pending, []
            vals = [val(t) for t in re.split(r"[\s,]+", line[3:].strip()) if t]
            if vals == [0]:
                current = []
                continue
            for lbl in current:
                rows[lbl].append(vals)
        elif not line.startswith("."):
            current = []
    return {mode: rows.get(lbl, []) for mode, lbl in enumerate(order)}


def parse_tiles(d: Path, consts: dict[str, int]) -> dict:
    tp = d / "data" / "ages" / "tile_properties"
    sources = {}
    for line in (tp / "breakableTiles.s").read_text().splitlines():
        m = re.match(r"\s*m_BreakableTileData %([01]+) %([01]+) %([01]+)", line)
        if m:
            bits = "".join(m.groups())
            sources[len(sources)] = [i for i, b in enumerate(bits) if b == "1"]

    def simple(name: str) -> dict[int, dict[int, int]]:
        return {mode: {r[0]: r[1] for r in rs} for mode, rs in parse_mode_table(tp / name, consts).items()}

    breakable = {mode: {tile: sources[m] for tile, m in tiles.items()} for mode, tiles in simple("breakableTiles.s").items()}
    return {
        "types": simple("tileTypeMappings.s"),
        "cliffs": simple("cliffTiles.s"),
        "warps": simple("warpTiles.s"),
        "interactable": simple("interactableTiles.s"),
        "breakable": breakable,
    }


def write_text_table(d: Path, out: Path) -> None:
    """Text index (group << 8 | index, as in wTextIndex) -> text, from text/ages/text.yaml."""
    import yaml

    doc = yaml.safe_load((d / "text" / "ages" / "text.yaml").read_text(encoding="utf-8"))
    table = {}
    for group in doc["groups"]:
        for entry in group["data"]:
            indices = entry["index"] if isinstance(entry["index"], list) else [entry["index"]]
            for i in indices:
                table[f"{group['group'] << 8 | i:04x}"] = entry["text"]
    out.write_text(json.dumps(table, indent=0, ensure_ascii=False), encoding="utf-8")
    print(f"{len(table)} text entries -> {out.name}")


def parse_linkfile(path: Path) -> tuple[dict[str, int], dict[str, str]]:
    origins, appendto = {}, {}
    for line in path.read_text().splitlines():
        m = re.match(r"bank \d+ slot \$\w+ orga \$(\w+) (\w+)", line)
        if m:
            origins[m.group(2)] = int(m.group(1), 16)
        m = re.match(r"bank \d+ slot \$\w+ appendto (\w+) (\w+)", line)
        if m:
            appendto[m.group(2)] = m.group(1)
    return origins, appendto


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disasm", type=Path, default=ROOT / "vendor" / "oracles-disasm")
    ap.add_argument("--out", type=Path, default=ROOT / "oracle_bot" / "data" / "ages.json")
    args = ap.parse_args()
    d = args.disasm

    lay = Layout(*parse_linkfile(d / "linkfile_ages"))
    const_files = sorted((d / "constants" / "common").glob("*.s")) + sorted((d / "constants" / "ages").glob("*.s"))
    for f in [*const_files, d / "include" / "structs.s", d / "include" / "hram.s", d / "include" / "wram.s"]:
        lay.parse(f.read_text(encoding="utf-8", errors="replace"))

    # Enums in constants files land in `labels` with bank None; split them back out as constants.
    ram = {k: v for k, v in lay.labels.items() if v[1] >= 0xC000 and (k[0] in "wh" or "." in k)}
    consts = {k: v[1] for k, v in lay.labels.items() if k not in ram}
    for k, v in lay.defines.items():
        if k[0] in "wh" and (0xC000 <= v < 0xD000 or 0xFF80 <= v <= 0xFFFF):
            ram[k] = (None, v)  # RAM aliases such as wGameState = wThreadStateBuffer + $e
        elif not k.endswith(".size"):
            consts[k] = v

    write_text_table(d, args.out.with_name("ages_text.json"))

    bad = [(k, a, ram[k][1]) for k, a in lay.comments.items()
           if k in ram and ram[k][1] != a and k not in KNOWN_BAD_COMMENTS]
    checked = sum(1 for k in lay.comments if k in ram)
    print(f"{len(ram)} RAM labels, {len(consts)} constants, {len(lay.structs)} structs; "
          f"{checked} address comments checked, {len(bad)} mismatches")
    for k, want, got in bad[:20]:
        print(f"  {k}: comment ${want:04x}, computed ${got:04x}")

    treasure_lay = Layout({}, {})
    treasure_lay.parse((d / "constants" / "common" / "treasure.s").read_text())
    treasures = {k: v[1] for k, v in treasure_lay.labels.items() if k.startswith("TREASURE_")}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "source": "Stewmath/oracles-disasm (see tools/gen_symbols.py)",
        "ram": {k: [b, a] for k, (b, a) in sorted(ram.items(), key=lambda kv: (kv[1][0] or 0, kv[1][1]))},
        "structs": lay.structs,
        "treasures": treasures,
        "tiles": parse_tiles(d, consts),
        "const": dict(sorted(consts.items())),
    }, indent=0))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
