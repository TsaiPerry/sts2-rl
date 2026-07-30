from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class FakeVenerableTeaSet(Relic):
    """FakeVenerableTeaSet.cs — on the first turn of a combat that follows a
    Rest, gain 1 energy (the real Venerable Tea Set gives 2). The rest is
    latched by `after_room_entered`; the constructor argument survives only so
    a test can pre-arm the relic. Fake Merchant knock-off, 50 gold."""

    id = "fake_venerable_tea_set"
    name = "Fake Venerable Tea Set"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    ENERGY = 1

    def __init__(self, rested: bool = False) -> None:
        super().__init__()
        self._pending = rested


    def after_room_entered(self, run, point, room_type) -> None:
        """FakeVenerableTeaSet.cs:43-51 — `AfterRoomEntered` latches on
        `room is RestSiteRoom`. The port used to take the latch as a
        CONSTRUCTOR argument, and `make_relic(id)` passes none, so `_pending`
        was False for the whole run and the spend half below could never fire.
        `relics/eternal_feather.py` is the sibling that already reads this hook
        with the same room test."""
        from ..rooms import RoomType

        if room_type == RoomType.REST_SITE:
            self._pending = True

    def on_energy_reset(self, player: PlayerCombatState) -> None:
        if self._pending:
            self._pending = False
            from ..cmds import EnergyCmd

            EnergyCmd.gain(self.hooks, player, self.ENERGY)
