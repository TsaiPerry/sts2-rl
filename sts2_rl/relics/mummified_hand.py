from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class MummifiedHand(Relic):
    """Whenever you play a Power card, a random card in your hand costs 0 for
    the rest of the turn. (The game prefers a card that costs energy/stars;
    the sim has no stars, so it picks a random energy-costing card.)"""

    id = "mummified_hand"
    name = "Mummified Hand"
    rarity = RelicRarity.RARE

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type != CardType.POWER:
            return
        candidates = [c for c in self.player.hand if c.energy_cost > 0]
        if not candidates:
            return
        # MummifiedHand.cs: RunState.Rng.CombatCardSelection.NextItem(...).
        self.combat.combat_rng.card_selection.choice(candidates).set_free_this_turn()
