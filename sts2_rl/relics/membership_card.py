from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MembershipCard(Relic):
    """Shop prices are 50% off — an out-of-combat merchant effect, so this is
    a no-op stub."""

    id = "membership_card"
    name = "Membership Card"
    rarity = RelicRarity.SHOP
