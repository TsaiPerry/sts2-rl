from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class RingingTriangle(Relic):
    """On the first turn of combat, your hand is not discarded at end of turn
    (the whole hand is retained into turn 2)."""

    id = "ringing_triangle"
    name = "Ringing Triangle"
    rarity = RelicRarity.SHOP

    def should_flush_hand(self) -> bool:
        # Keep the hand only on turn 1 (mirrors ShouldFlush: TurnNumber > 1).
        return self.turn > 1
