from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class ForgottenSoul(Relic):
    """Whenever one of your cards is exhausted, deal 1 damage to a random enemy.

    Source: ForgottenSoul.cs — AfterCardExhausted (for a card owned by the
    player) deals DamageVar(1, Unpowered) to a random HittableEnemy. Granted by
    the Grave of the Forgotten event (Accept)."""

    id = "forgotten_soul"
    name = "Forgotten Soul"
    rarity = RelicRarity.EVENT

    DAMAGE = 1

    def on_card_exhausted(self, card: Card,
                          caused_by_ethereal: bool = False) -> None:
        if self.combat is None or self.combat.is_over:
            return
        living = self.living_enemies()
        if not living:
            return
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        # ForgottenSoul.cs: RunState.Rng.CombatTargets.NextItem(HittableEnemies).
        target = self.combat.combat_rng.targets.choice(living)
        DamageCmd.deal(
            self.hooks, target, self.DAMAGE,
            dealer=self.player, props=DamageProps.NON_CARD_UNPOWERED,
        )
        self._check_win()
