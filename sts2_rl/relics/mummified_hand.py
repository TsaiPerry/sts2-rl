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
        rng = self.combat.combat_rng.card_selection
        hand = list(self.player.hand)
        # MummifiedHand.cs:32 — `list` is the cards whose PRINTED cost is > 0
        # (`GetWithModifiers(CostModifiers.None)`), which is the pool the relic
        # PREFERS; the tiers then narrow or widen from it.
        base_costing = [c for c in hand if c.costs_energy_before_modifiers()]

        # MummifiedHand.cs:33-45 is FOUR tiers, each an
        # `Rng.CombatCardSelection.NextItem(...)` tried only if the previous one
        # came back null. Two things were wrong in the port. (1) It filtered on
        # `c.energy_cost`, the LOCAL cost, where C# asks
        # `CostsEnergyOrStars(includeGlobalModifiers: true)` — the cost the
        # player would pay right now: with Corruption up, every Skill costs 0
        # globally and the sim still spent the free cost on a Defend where the
        # game frees the Bash. (2) It returned early instead of falling back, so
        # with a hand of nothing but 0-cost cards it picked nothing and skipped
        # the draw C# takes. `Rng.NextItem` on an EMPTY sequence takes no draw
        # (Rng.cs:255-265), so the game consumes exactly one NextInt, from the
        # first non-empty tier — which is why the tiers are written out rather
        # than collapsed into an `or` chain.
        for tier in ([c for c in base_costing if c.costs_energy(self.hooks)],
                     [c for c in hand if c.costs_energy(self.hooks)],
                     base_costing,
                     hand):
            if tier:
                rng.choice(tier).set_free_this_turn()
                return
