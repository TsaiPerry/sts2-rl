from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WarHammer(Relic):
    """WarHammer.cs — after every Elite victory (AfterCombatVictory), upgrade
    ALL upgradable cards in the deck."""

    id = "war_hammer"
    name = "War Hammer"
    rarity = RelicRarity.ANCIENT

    def after_combat_end(self, run, room_type) -> None:
        from ..rooms import RoomType

        if room_type != RoomType.ELITE or run.is_dead:
            return
        for card in run.deck:
            if card.is_upgradable:
                card.upgrade()
