"""M0 probe: emulator speed and determinism checks.

Runs a fixed pseudo-random input schedule from power-on and checks that
  - two continuous runs produce identical memory hashes,
  - rendering every frame doesn't change emulation,
  - replaying the recorded log reproduces the run,
  - saving a state and resuming it in a fresh emulator is exact.
"""

import random
import sys
import time

from PIL import Image

from oracle_bot.emu import ROOT, Emu, replay

FRAMES = 8000
HASH_EVERY = 25
RESUME_AT = (2000, 4000, 6000)


def schedule(seed: int = 1) -> dict[int, int]:
    rng = random.Random(seed)
    out, f = {}, 0
    while f < FRAMES:
        f += rng.randint(4, 40)
        out[f] = rng.choice([0, 0x01, 0x01, 0x08, 0x10, 0x20, 0x40, 0x80, 0x41, 0x02])
    for f in RESUME_AT:  # states are only taken with buttons released
        out[f] = 0
        out.pop(f + 1, None)
    return out


def run(inputs: dict[int, int], emu: Emu | None = None, start: int = 0, render: bool = False,
        states: dict[int, bytes] | None = None) -> dict[int, str]:
    emu = emu or Emu()
    hashes = {}
    for f in range(start, FRAMES):
        if f in inputs:
            emu.set_buttons(inputs[f])
        if states is not None and f in RESUME_AT:
            states[f] = emu.state()
        if f % HASH_EVERY == 0:
            hashes[f] = emu.mem_hash()
        emu.step(1, render=render)
    hashes[FRAMES] = emu.mem_hash()
    emu.log.add(emu.frame, "E")
    run.last = emu
    return hashes


def compare(name: str, a: dict[int, str], b: dict[int, str]) -> bool:
    bad = [f for f in sorted(b) if a.get(f) != b[f]]
    print(f"{name}: {'PASS' if not bad else f'FAIL (first divergence at frame {bad[0]})'}")
    return not bad


def main() -> int:
    inputs = schedule()
    ok = True

    emu = Emu()
    t = time.perf_counter()
    emu.step(FRAMES)
    dt = time.perf_counter() - t
    print(f"headless, no render: {FRAMES / dt:.0f} fps")
    emu = Emu()
    t = time.perf_counter()
    emu.step(2000, render=False)
    for _ in range(2000):
        emu.step(1, render=True)
    print(f"render every frame: {2000 / (time.perf_counter() - t - 2000 / (FRAMES / dt)):.0f} fps")

    states: dict[int, bytes] = {}
    base = run(inputs, states=states)
    log = run.last.log
    ok &= compare("continuous x2", base, run(inputs))
    ok &= compare("render invariance", base, run(inputs, render=True))

    replayed = replay(log)
    ok &= compare("log replay", {FRAMES: base[FRAMES]}, {FRAMES: replayed.mem_hash()})

    for f in RESUME_AT:
        emu = Emu()
        emu.load(states[f], f)
        resumed = run(inputs, emu=emu, start=f)
        ok &= compare(f"state resume @{f}", {k: v for k, v in base.items() if k >= f}, resumed)

    Image.fromarray(replayed.screen()).resize((480, 432), Image.NEAREST).save(ROOT / "runs" / "probe.png")
    print(f"frames: {FRAMES}, screenshot: runs/probe.png")
    return 0 if ok else 1


if __name__ == "__main__":
    (ROOT / "runs").mkdir(exist_ok=True)
    sys.exit(main())
