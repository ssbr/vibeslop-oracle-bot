"""The route: segments in play order."""

from . import s00_intro

SEGMENTS = [s00_intro.R]
ITEMS = [item for seg in SEGMENTS for item in seg.items]
