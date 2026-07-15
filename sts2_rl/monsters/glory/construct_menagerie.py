from __future__ import annotations

from ..base import Encounter
from ..overgrowth.cubex_construct import CubexConstruct
from ..underdocks.punch_construct import PunchConstruct

# ConstructMenagerieNormal.cs: one Punch Construct + two Cubex Constructs
# (both construct classes are already implemented for their Act-1/Act-2 fights).
CONSTRUCT_MENAGERIE_NORMAL = Encounter(
    id="construct_menagerie_normal",
    monster_classes=[PunchConstruct, CubexConstruct, CubexConstruct],
)
