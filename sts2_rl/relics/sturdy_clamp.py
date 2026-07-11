from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature
    from ..player import PlayerCombatState


@register_relic
class SturdyClamp(Relic):
    """Your Block is not cleared at the start of your turn, but is reduced to at
    most 10 (mirrors ShouldClearBlock=false + capping to 10)."""

    id = "sturdy_clamp"
    name = "Sturdy Clamp"
    rarity = RelicRarity.RARE

    MAX_RETAINED = 10

    def should_clear_block(self, creature: Creature) -> bool:
        # Keep the player's block (enemies clear normally).
        return creature is not self.player

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        # Block clear was prevented above; cap the carried-over block at 10.
        if player.block > self.MAX_RETAINED:
            player.block = self.MAX_RETAINED
