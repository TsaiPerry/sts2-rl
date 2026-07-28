from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PrayerWheel(Relic):
    """PrayerWheel.cs — a Monster room's rewards carry a SECOND card choice on
    the same Monster odds (`TryModifyRewards` adds
    `new CardReward(CardCreationOptions.ForRoom(player, RoomType.Monster), 3)`).

    STILL A NO-OP, and the reason is structural rather than "out of combat":
    `rewards.CombatRewards` models exactly ONE pick-one-of-N card group
    (`cards`) plus independent take-or-skip singles (`special_cards`), so a
    second CardReward group has no field to live in and no driver action to
    surface it. Same shape as White Star."""

    id = "prayer_wheel"
    name = "Prayer Wheel"
    rarity = RelicRarity.RARE
