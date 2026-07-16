from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MassiveScroll(Relic):
    """MassiveScroll.cs — multiplayer-only (IsAllowed: Players.Count > 1);
    never offerable in the single-player sim (documented stub)."""

    id = "massive_scroll"
    name = "Massive Scroll"
    rarity = RelicRarity.ANCIENT
    is_allowed_at_neow = False
