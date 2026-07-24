from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SwordBoomerangCard(Card):
    """Attack (Common, 1E) — deal 3 damage to a random enemy 3 times.

    Source: SwordBoomerang.cs
      Cost 1 | Attack | Common | TargetType.RandomEnemy
      Damage 3 × Repeat 3, each hit re-rolls a random living enemy
      OnUpgrade: repeat +1 (→ 4)
    """
    id = "sword_boomerang"
    name = "Sword Boomerang"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.RANDOM_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 3
        self._hits = 3

    def _on_upgrade(self) -> None:
        self._hits += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        # AttackCommand.cs:601-602 (TargetingRandomOpponents): one
        # Rng.CombatTargets.NextItem(validTargets) per hit, re-rolled each
        # time. Parity routes to that stream; legacy keeps the shared
        # random.Random pick.
        crng = ctx.combat.combat_rng
        for _ in range(self._hits):
            living = [e for e in ctx.enemies if not e.is_gone]
            if not living or ctx.player.is_dead:
                break
            if crng.is_parity:
                target = crng.targets.choice(living)
            else:
                target = ctx.combat._rng.choice(living)
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
