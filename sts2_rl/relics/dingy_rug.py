from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class DingyRug(Relic):
    """Card rewards can also contain Colorless cards — out-of-combat card
    reward modifier, stub."""

    id = "dingy_rug"
    name = "Dingy Rug"
    rarity = RelicRarity.SHOP
