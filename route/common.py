"""Shared route context."""

from oracle_bot import config

CFG = config.load()

# Places more than one segment uses.
NAYRU_PORTAL = (40, 24)  # present 0:3a: time portal spot left of Nayru's door
LYNNA_PORTAL, LYNNA_PORTAL_STAND = (72, 88), (104, 88)  # past 1:48 (Lynna City), and where to play the harp
