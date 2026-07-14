"""Act 3 "Glory" enemies. Currently only the Battle Friend training dummies of
the Battleworn Dummy event; the Glory combat encounter roster is out of scope."""
from ..base import Encounter, Intent, Monster, MoveType

from .battle_friend import (
    BattleFriendV1,
    BattleFriendV2,
    BattleFriendV3,
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
)

__all__ = [
    "MoveType", "Intent", "Monster", "Encounter",
    "BattleFriendV1", "BattleFriendV2", "BattleFriendV3",
    "BATTLEWORN_DUMMY_SETTING_1",
    "BATTLEWORN_DUMMY_SETTING_2",
    "BATTLEWORN_DUMMY_SETTING_3",
]
