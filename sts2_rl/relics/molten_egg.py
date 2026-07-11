from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MoltenEgg(Relic):
    """Attack cards added to your deck are Upgraded — an out-of-combat deck
    edit, so this is a no-op stub."""

    id = "molten_egg"
    name = "Molten Egg"
    rarity = RelicRarity.RARE
