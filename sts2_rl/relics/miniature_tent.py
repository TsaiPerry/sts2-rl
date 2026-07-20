from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MiniatureTent(Relic):
    """MiniatureTent.cs — ShouldDisableRemainingRestSiteOptions returns
    False: a rest-site visit doesn't end after one action, so the player may
    keep choosing options (Heal, Smith, other relic/card options) until they
    explicitly Leave or run out."""

    id = "miniature_tent"
    name = "Miniature Tent"
    rarity = RelicRarity.SHOP

    def should_disable_remaining_rest_site_options(self, run) -> bool:
        return False
