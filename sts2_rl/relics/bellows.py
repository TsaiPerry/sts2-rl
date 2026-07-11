from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class Bellows(Relic):
    """At the start of combat, Upgrade all cards in your hand (for the rest
    of the combat)."""

    id = "bellows"
    name = "Bellows"
    rarity = RelicRarity.RARE

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            for card in player.hand:
                if card.is_upgradable:
                    card.upgrade()
