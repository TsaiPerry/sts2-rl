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

    def after_preventing_block_clear(self, creature: Creature) -> None:
        # SturdyClamp.cs:31-46 caps the retained block from
        # AfterPreventingBlockClear, and opens
        # `if (this != preventer || creature != Owner.Creature) return` — the
        # hook is dispatched ONLY to the vetoing listener, so reaching this
        # body already means Sturdy Clamp was the preventer. The sim capped
        # from on_player_turn_start instead, with no preventer test at all, so
        # a Barricaded player's block was capped at 10 by a relic that had not
        # prevented anything.
        if creature is not self.player:
            return
        if creature.block > self.MAX_RETAINED:
            creature.block = self.MAX_RETAINED
