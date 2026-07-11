from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LavaLamp(Relic):
    """If you take no damage during a combat, its card rewards are Upgraded —
    a card-reward modifier applied after combat, so this is a no-op stub."""

    id = "lava_lamp"
    name = "Lava Lamp"
    rarity = RelicRarity.SHOP
