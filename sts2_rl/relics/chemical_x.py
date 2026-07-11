from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class ChemicalX(Relic):
    """The X of X-cost cards is increased by 2 (the energy spent is
    unchanged)."""

    id = "chemical_x"
    name = "Chemical X"
    rarity = RelicRarity.SHOP

    def modify_x_value(self, card: Card, value: int) -> int:
        return value + 2
