from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DreamCatcher(Relic):
    """When you rest at a rest site, you may also add a card to your deck.

    Source: DreamCatcher.cs — TryModifyRestSiteHealRewards. The sim has no rest
    sites, so this is a documented stub. Granted by the Trash Heap event."""

    id = "dream_catcher"
    name = "Dream Catcher"
    rarity = RelicRarity.EVENT
