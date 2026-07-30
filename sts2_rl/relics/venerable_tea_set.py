from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class VenerableTeaSet(Relic):
    """On the first turn of a combat that follows a Rest, gain 2 energy. The rest is
    latched by `after_room_entered`; the constructor argument survives only so a
    test can pre-arm the relic."""

    id = "venerable_tea_set"
    name = "Venerable Tea Set"
    rarity = RelicRarity.COMMON

    ENERGY = 2

    def __init__(self, rested: bool = False) -> None:
        super().__init__()
        self._pending = rested


    def after_room_entered(self, run, point, room_type) -> None:
        """VenerableTeaSet.cs — `AfterRoomEntered` latches on
        `room is RestSiteRoom`. The port used to take the latch as a
        CONSTRUCTOR argument, and `make_relic(id)` passes none, so `_pending`
        was False for the whole run and the spend half below could never fire.
        `relics/eternal_feather.py` is the sibling that already reads this hook
        with the same room test."""
        from ..rooms import RoomType

        if room_type == RoomType.REST_SITE:
            self._pending = True

    def on_energy_reset(self, player: PlayerCombatState) -> None:
        # Fires on the first energy reset of the combat (turn 1), once.
        if self._pending:
            self._pending = False
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, self.ENERGY)
