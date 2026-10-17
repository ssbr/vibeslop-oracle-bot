"""Command line: `obot <command>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from .emu import ROOT, Emu, load_snapshot, replay
from .record import Log, validate_sav


def cmd_steps(args) -> int:
    from route import ITEMS
    from .runner import Mark

    for i, it in enumerate(ITEMS):
        kind = "MARK" if isinstance(it, Mark) else "step"
        extra = " (release)" if isinstance(it, Mark) and it.release else (f"  # {it.note}" if getattr(it, "note", "") else "")
        print(f"{i:03d} {kind} {it.name}{extra}")
    return 0


def cmd_run(args) -> int:
    from route import ITEMS
    from route.common import CFG
    from .runner import Failed, Runner

    runner = Runner(ITEMS, ROOT / "runs" / args.run, CFG, interactive=args.interactive)
    try:
        e = runner.run(args.start, args.stop)
    except Failed as err:
        print(f"FAILED: {err}")
        return 1
    print(f"done at frame {e.frame}; log: runs/{args.run}/replay.log")
    return 0


def cmd_inspect(args) -> int:
    from . import nav, ram

    path = Path(args.snapshot)
    e = load_snapshot(path.with_suffix(""))
    print(ram.summary(e))
    print(nav.ascii(e))
    png = path.with_suffix(".png")
    Image.fromarray(e.screen()).resize((320, 288), Image.NEAREST).save(png)
    print(f"screenshot: {png}")
    return 0


def cmd_verify(args) -> int:
    log = Log.load(Path(args.log))
    marks = log.marks()
    bad = []

    def check(e: Emu, op) -> None:
        if op.op == "C":
            name, want = op.args.split()
            got = e.mem_hash()
            ok = got == want
            print(f"  {name:28s} frame {op.frame:8d}  {'PASS' if ok else 'FAIL'}")
            if not ok:
                bad.append(name)

    print(f"replaying {len(log.ops)} ops, {len(marks)} checkpoints, {log.end_frame()} frames")
    e = replay(log, on_op=check)
    if log.has_dev_writes():
        print("note: log contains dev writes (not promotable)")
    print("VERIFY " + ("FAILED: " + ", ".join(bad) if bad else "PASSED") + f" (frame {e.frame})")
    return 1 if bad else 0


def cmd_boot_sav(args) -> int:
    from . import menus, ram

    sram = Path(args.sav).read_bytes()
    problems = validate_sav(sram)
    print("save slot 1:", "valid" if not problems else problems)
    e = Emu(sram=sram)
    menus.load_game(e)
    print(ram.summary(e))
    png = Path(args.sav).with_name("boot.png")
    Image.fromarray(e.screen()).resize((320, 288), Image.NEAREST).save(png)
    print(f"screenshot: {png}")
    return 0


def cmd_promote(args) -> int:
    from .runner import promote

    run_dir = ROOT / "runs" / args.run
    log = Log.load(run_dir / "replay.log")
    if log.has_dev_writes():
        print("refusing: run contains dev writes")
        return 1
    promote(run_dir, ROOT / "checkpoints")
    print("promoted to checkpoints/ (run `obot verify checkpoints/replay.log` to re-check)")
    return 0


def cmd_video(args) -> int:
    from . import video

    run_dir = ROOT / "runs" / args.run
    log = Log.load(run_dir / "replay.log")
    if args.step:
        start, end = video.step_range(run_dir, args.step)
    else:
        start, end = args.start, args.end
    end = min(end, start + int(args.max_seconds * video.FPS))  # keep clips watchable
    out = Path(args.out) if args.out else run_dir / "clips" / f"{args.step or start}_{start}-{end}"
    path = video.render(log, start, end, out, base=video.nearest_state(run_dir, start))
    print(f"{path}  (frames {start}-{end}, {(end - start) / video.FPS:.0f} s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    ap = argparse.ArgumentParser(prog="obot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("steps", help="list route steps and marks")
    p = sub.add_parser("run", help="run the route (resumes from the snapshot before --from)")
    p.add_argument("--run", default="main", help="run directory under runs/")
    p.add_argument("--from", dest="start", help="first step to execute")
    p.add_argument("--to", dest="stop", help="last step to execute")
    p.add_argument("--interactive", action="store_true", help="allow human takeover")
    p = sub.add_parser("inspect", help="summary, ASCII map and screenshot of a snapshot")
    p.add_argument("snapshot", help="path to a .state (with .log/.json next to it)")
    p = sub.add_parser("verify", help="replay a log from power-on and check checkpoint hashes")
    p.add_argument("log")
    p = sub.add_parser("boot-sav", help="boot an exported .sav and show where it loads")
    p.add_argument("sav")
    p = sub.add_parser("promote", help="copy a run's checkpoints into checkpoints/")
    p.add_argument("--run", default="main")
    p = sub.add_parser("video", help="render a stretch of a run's replay to MP4 (GIF without ffmpeg)")
    p.add_argument("--run", default="main")
    p.add_argument("--step", help="a route step (or mark) name: the frames it took")
    p.add_argument("--from", dest="start", type=int, default=0, help="first frame")
    p.add_argument("--to", dest="end", type=int, default=0, help="end frame")
    p.add_argument("--max-seconds", type=float, default=300, help="cut clips longer than this")
    p.add_argument("-o", "--out", help="output path (default runs/<run>/clips/...)")
    args = ap.parse_args(argv)
    return {"steps": cmd_steps, "run": cmd_run, "inspect": cmd_inspect, "verify": cmd_verify,
            "boot-sav": cmd_boot_sav, "promote": cmd_promote, "video": cmd_video}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
