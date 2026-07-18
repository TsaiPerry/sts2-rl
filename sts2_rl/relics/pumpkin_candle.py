from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, RestSiteOption, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class PumpkinCandle(Relic):
    """PumpkinCandle.cs — pick up with 5 kindle; +1 max Energy while kindled;
    each combat burns 1 kindle (AfterCombatEnd). The KINDLE rest-site option
    re-lights it (+5, KindleRestSiteOption → Rekindle)."""

    id = "pumpkin_candle"
    name = "Pumpkin Candle"
    rarity = RelicRarity.ANCIENT

    KINDLE_AMOUNT = 5

    def __init__(self) -> None:
        super().__init__()
        self.kindle_count = 0

    def after_obtained(self, run) -> None:
        self.rekindle()

    def rekindle(self) -> None:
        self.kindle_count += self.KINDLE_AMOUNT

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        if self.kindle_count <= 0:
            return amount
        return amount + 1

    def after_combat_end(self, run, room_type) -> None:
        self.kindle_count = max(0, self.kindle_count - 1)

    def modify_rest_site_options(self, run, options) -> None:
        options.append(RestSiteOption("KINDLE", lambda run: self.rekindle()))
