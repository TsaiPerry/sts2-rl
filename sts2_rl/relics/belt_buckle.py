from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature

@register_relic
class BeltBuckle(Relic):
    """While you have no potions, you have 2 Dexterity."""

    id = "belt_buckle"
    name = "Belt Buckle"
    rarity = RelicRarity.SHOP

    def __init__(self) -> None:
        super().__init__()
        self._applied = False

    def _apply_if_potionless(self) -> None:
        if not self._applied and not self.player.potions:
            from ..cmds import PowerCmd
            from ..powers import DexterityPower
            self._applied = True
            PowerCmd.apply(self.hooks, self.player, DexterityPower, 2)

    def on_combat_start(self) -> None:
        self._apply_if_potionless()

    def on_potion_used(self, potion, target: Creature | None) -> None:
        self._apply_if_potionless()
