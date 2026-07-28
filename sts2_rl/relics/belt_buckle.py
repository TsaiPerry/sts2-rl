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

    DEXTERITY = 2

    def __init__(self) -> None:
        super().__init__()
        self._applied = False

    def reset_for_combat(self) -> None:
        # BeltBuckle.BeforeCombatStart (:47-54) clears DexterityApplied before
        # re-applying, as does AfterCombatVictory (:87-92).
        self._applied = False

    def _apply_if_potionless(self) -> None:
        if not self._applied and not self.player.held_potions:
            from ..cmds import PowerCmd
            from ..powers import DexterityPower
            self._applied = True
            PowerCmd.apply(self.hooks, self.player, DexterityPower,
                           self.DEXTERITY)

    def _remove_if_carrying(self) -> None:
        # BeltBuckle.RemoveDexterity (:105-113) applies -BaseValue.
        if self._applied and self.player.held_potions:
            from ..cmds import PowerCmd
            from ..powers import DexterityPower
            self._applied = False
            PowerCmd.apply(self.hooks, self.player, DexterityPower,
                           -self.DEXTERITY)

    def on_combat_start(self) -> None:
        self._apply_if_potionless()

    def on_potion_used(self, potion, target: Creature | None) -> None:
        self._apply_if_potionless()

    def after_potion_procured(self, potion) -> None:
        # BeltBuckle.AfterPotionProcured (:63-70) — the half of "while you have
        # no potions" that enforces the *no*: gaining a potion mid-combat takes
        # the Dexterity straight back off.
        self._remove_if_carrying()
