from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class LastingCandy(Relic):
    """Every other combat, a card reward is replaced with a Power card — a
    card-reward modifier that runs between combats, so this is a no-op stub."""

    id = "lasting_candy"
    name = "Lasting Candy"
    rarity = RelicRarity.UNCOMMON

    @classmethod
    def is_allowed(cls, run) -> bool:
        """LastingCandy.cs:80-98 — the pool's only MULTI-clause IsAllowed. Its
        tail is IsBeforeAct3TreasureChest, so the relic leaves the pools from
        floor 41. Its head (`p.Character is Ironclad && p.UnlockState
        .NumberOfRuns == 0`) vetoes the relic on a profile's very first
        Ironclad run and is unported on purpose: the sim has no profile /
        UnlockState model at all, so it behaves as a veteran profile always."""
        return is_before_act3_treasure_chest(run)
