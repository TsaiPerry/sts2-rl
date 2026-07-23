from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class JeweledMask(Relic):
    """JeweledMask.cs — on turn 1 (BeforeHandDraw), a random Power card in
    your draw pile is moved to your hand and costs 0 this turn."""

    id = "jeweled_mask"
    name = "Jeweled Mask"
    rarity = RelicRarity.ANCIENT

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn != 1:
            return
        from ..cards import CardType

        powers = [
            c for c in player.draw_pile if c.card_type == CardType.POWER
        ]
        if not powers:
            return
        # JeweledMask.cs: RunState.Rng.CombatCardSelection.NextItem(powers).
        card = self.combat.combat_rng.card_selection.choice(powers)
        card.set_free_this_turn()
        player.draw_pile.remove(card)
        player.hand.append(card)
