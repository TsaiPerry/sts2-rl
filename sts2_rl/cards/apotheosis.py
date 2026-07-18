from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ApotheosisCard(Card):
    """Apotheosis.cs — 2-cost Ancient Skill (Exhaust, Innate): upgrade ALL of
    your cards for the rest of combat (upgrade: costs 1). Granted by Jewelry
    Box."""

    id = "apotheosis"
    name = "Apotheosis"
    card_type = CardType.SKILL
    rarity = CardRarity.ANCIENT
    target_type = TargetType.SELF
    exhausts = True
    innate = True

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def _on_upgrade(self) -> None:
        self._energy_cost -= 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        for card in ctx.player.all_cards:
            if card is not self and card.is_upgradable:
                card.upgrade()
