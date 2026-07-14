from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MawBank(Relic):
    """Whenever you climb to a new room, gain 12 Gold. Stops once you spend any
    gold at a shop.

    Source: MawBank.cs — AfterRoomEntered / AfterItemPurchased. Gold and the
    map/shop live outside combat, so this is a documented stub. Granted by the
    Trash Heap event."""

    id = "maw_bank"
    name = "Maw Bank"
    rarity = RelicRarity.EVENT
