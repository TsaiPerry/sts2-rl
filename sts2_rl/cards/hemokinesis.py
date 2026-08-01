from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class HemokinesisCard(Card):
    """Attack (Uncommon, 1E) — lose 2 HP; deal 15 damage.

    Source: Hemokinesis.cs
      Cost 1 | Attack | Uncommon | TargetType.AnyEnemy
      OnPlay: CreatureCmd.Damage(self, 2, Unblockable|Unpowered|Move), then Attack(15)
      OnUpgrade: damage +5 (→ 20)
    """
    id = "hemokinesis"
    name = "Hemokinesis"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 15
        self._hp_loss = 2

    def _on_upgrade(self) -> None:
        self._damage += 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(ctx.hooks, ctx.player, self._hp_loss, card=self, props=DamageProps.CARD_HP_LOSS)
        # Hemokinesis.cs has no is_dead guard here -- C# unconditionally
        # awaits the attack next. No divergence to reproduce: DamageCmd.deal's
        # own dealer.is_dead bail (mirroring AttackCommand.Execute's
        # Attacker.IsDead / IsOverOrEnding bails, AttackCommand.cs:520,528)
        # already makes the follow-up attack a no-op on a dying dealer -- see
        # card/_is_dead_early_return (Task 27) and
        # test/test_is_dead_early_returns.py.
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
