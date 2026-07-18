from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class WishCard(Card):
    """Wish.cs — 0-cost Ancient Skill (Exhaust): choose a card from your DRAW
    pile and put it into your hand (upgrade: gains Retain). Granted by Sere
    Talon."""

    id = "wish"
    name = "Wish"
    card_type = CardType.SKILL
    rarity = CardRarity.ANCIENT
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def _on_upgrade(self) -> None:
        self.retain = True

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        player = ctx.player
        if not player.draw_pile:
            return
        chosen = ctx.combat.select_cards(
            "wish", list(player.draw_pile), 1,
        )
        for card in chosen:
            player.draw_pile.remove(card)
            player.hand.append(card)
