from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Kaleidoscope(Relic):
    """Kaleidoscope.cs — obtain 2 cards from other characters' pools.

    IsAllowedAtNeow requires every character card pool unlocked; the
    single-character sim has only the Ironclad pool, so this can never be
    offered (documented stub, mirrors Colorful Philosophers)."""

    id = "kaleidoscope"
    name = "Kaleidoscope"
    rarity = RelicRarity.ANCIENT
    is_allowed_at_neow = False
