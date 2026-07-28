from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class WhiteStar(Relic):
    """WhiteStar.cs — an Elite's rewards carry a SECOND card choice, rolled on
    Boss odds (`TryModifyRewards` adds
    `new CardReward(CardCreationOptions.ForRoom(owner, RoomType.Boss), 3)`).

    STILL A NO-OP, and the reason is structural rather than "out of combat":
    `rewards.CombatRewards` models exactly ONE pick-one-of-N card group
    (`cards`) plus independent take-or-skip singles (`special_cards`). A second
    CardReward group has no field to live in and no driver action to surface
    it, so the missing piece is a `CombatRewards` shape change plus a driver
    seam, not a hook on this class. Same shape as Prayer Wheel."""

    id = "white_star"
    name = "White Star"
    rarity = RelicRarity.RARE

    @classmethod
    def is_allowed(cls, run) -> bool:
        """WhiteStar.cs:14-17: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
