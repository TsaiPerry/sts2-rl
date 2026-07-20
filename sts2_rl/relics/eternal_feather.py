from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class EternalFeather(Relic):
    """EternalFeather.cs — AfterRoomEntered: on entering a rest site, heal
    3 HP for every 5 cards in the deck (floor division), automatically, with
    no player choice involved (not a RestSiteOption)."""

    id = "eternal_feather"
    name = "Eternal Feather"
    rarity = RelicRarity.UNCOMMON

    CARDS_PER_HEAL = 5
    HEAL_PER_GROUP = 3

    def after_room_entered(self, run, point, room_type) -> None:
        from ..rooms import RoomType
        if room_type != RoomType.REST_SITE:
            return
        groups = len(run.deck) // self.CARDS_PER_HEAL
        if groups:
            run.heal(self.HEAL_PER_GROUP * groups)
