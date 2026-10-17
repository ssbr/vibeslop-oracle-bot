"""The route: segments in play order."""

from . import s00_intro, s01_shovel

SEGMENTS = [s00_intro.R, s01_shovel.R]
ITEMS = [item for seg in SEGMENTS for item in seg.items]
