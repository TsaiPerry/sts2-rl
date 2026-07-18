from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class PrismaticGem(Relic):
    """PrismaticGem.cs — +1 max Energy (ModifyMaxEnergy). The other half —
    ModifyCardRewardCreationOptions unions every unlocked character's card pool
    into card rewards — needs multiple character colours, so it is a documented
    no-op in the single-character sim (like Colorful Philosophers)."""

    id = "prismatic_gem"
    name = "Prismatic Gem"
    rarity = RelicRarity.ANCIENT

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + 1
