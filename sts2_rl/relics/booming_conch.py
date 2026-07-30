from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class BoomingConch(Relic):
    """BoomingConch.cs — in Elite combats, draw 2 extra cards and gain 1
    energy on your first turn."""

    id = "booming_conch"
    name = "Booming Conch"
    rarity = RelicRarity.ANCIENT
    CARDS = 2
    ENERGY = 1

    def _in_elite_first_turn(self) -> bool:
        from ..rooms import RoomType

        return (
            self.combat is not None
            and self.combat.room_type == RoomType.ELITE
            and self.turn <= 1
        )

    def modify_hand_draw(self, player, count: int) -> int:
        if self._in_elite_first_turn():
            return count + self.CARDS
        return count

    def after_side_turn_start(self, player) -> None:
        # AfterSideTurnStart, turn 1 only: +1 energy (fires post-energy-reset).
        if self._in_elite_first_turn():
            player.energy += self.ENERGY
