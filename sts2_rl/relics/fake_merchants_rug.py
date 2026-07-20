from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FakeMerchantsRug(Relic):
    """FakeMerchantsRug.cs — a trophy with no hooks at all: the source model
    declares only its Event rarity. Dropped by the Fake Merchant fight (it is
    a combat reward, never stock you can buy)."""

    id = "fake_merchants_rug"
    name = "Fake Merchant's Rug"
    rarity = RelicRarity.EVENT
