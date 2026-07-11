from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class FresnelLens(Relic):
    """Cards added to your deck are enchanted with Nimble — the sim has no
    enchantments or deck edits, stub."""

    id = "fresnel_lens"
    name = "Fresnel Lens"
    rarity = RelicRarity.EVENT
