from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MassiveScroll(Relic):
    """MassiveScroll.cs — multiplayer-only (IsAllowed: Players.Count > 1);
    never offerable in the single-player sim (documented stub)."""

    id = "massive_scroll"
    name = "Massive Scroll"
    rarity = RelicRarity.ANCIENT

    @classmethod
    def is_allowed(cls, run) -> bool:
        """MassiveScroll.cs:19-22 — `runState.Players.Count > 1`. The gate is
        IsAllowed, not IsAllowedAtNeow, so it keeps the relic out of every
        pool, not just Neow's. Always False in the single-player sim."""
        return False
