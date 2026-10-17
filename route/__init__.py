"""The route: segments in play order."""

from . import s00_intro, s01_shovel, s02_maku_road

SEGMENTS = [s00_intro.R, s01_shovel.R, s02_maku_road.R]
ITEMS = [item for seg in SEGMENTS for item in seg.items]
