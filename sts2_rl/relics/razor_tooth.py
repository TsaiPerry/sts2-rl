from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class RazorTooth(Relic):
    """Whenever you play an Attack or a Skill, Upgrade it (for the rest of the
    combat)."""

    id = "razor_tooth"
    name = "Razor Tooth"
    rarity = RelicRarity.RARE

    def on_card_played(self, card: Card) -> None:
        if card.card_type in (CardType.ATTACK, CardType.SKILL) and card.is_upgradable:
            card.upgrade()
