"""Dev helper: render a whole large room by moving Link (dev pokes, throwaway) so the camera visits each corner.

Usage: uv run python tools/roomshot.py <snapshot> <out.png>
"""

import sys
from pathlib import Path

from PIL import Image

from oracle_bot import ram
from oracle_bot.emu import load_snapshot


def main() -> int:
    e = load_snapshot(Path(sys.argv[1]).with_suffix(""))
    base = (e.state(), e.frame, len(e.log.ops))
    big = Image.new("RGB", (256, 192))
    for y, x in ((8, 8), (8, 232), (168, 8), (168, 232)):
        e.load(*base)
        for _ in range(120):  # hold Link there while the camera catches up
            ram.poke(e, "w1Link.yh", y, "dev")
            ram.poke(e, "w1Link.xh", x, "dev")
            e.step()
        cy, cx = ram.u8(e, "hCameraY"), ram.u8(e, "hCameraX")
        big.paste(Image.fromarray(e.screen()).crop((0, 16, 160, 144)), (cx, cy))
    big.resize((768, 576), Image.NEAREST).save(sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
