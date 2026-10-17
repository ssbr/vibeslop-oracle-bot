"""The route: segments in play order."""

from . import s00_intro, s01_shovel, s02_maku_road, s03_graveyard, s04_d1, s05_harp

SEGMENTS = [s00_intro.R, s01_shovel.R, s02_maku_road.R, s03_graveyard.R, s04_d1.R, s05_harp.R]
ITEMS = [item for seg in SEGMENTS for item in seg.items]
