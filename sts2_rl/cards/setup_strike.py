from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SetupStrikeCard(Card):
    """Attack (Common, 1E) — deal 7 damage; gain 2 Strength until the end of
    your turn.

    Source: SetupStrike.cs
      Cost 1 | Attack | Common | TargetType.AnyEnemy | Tags: Strike
      OnPlay: DamageCmd.Attack(7), then PowerCmd.Apply<SetupStrikePower>(2)
        to SELF (SetupStrikePower : TemporaryStrengthPower)
      OnUpgrade: damage +2 (→ 9), strength +1 (→ 3)
    """
    id = "setup_strike"
    name = "Setup Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY
    tags = frozenset({"strike"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 7
        self._strength = 2

    def _on_upgrade(self) -> None:
        self._damage += 2
        self._strength += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import SetupStrikePower
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
        PowerCmd.apply(
            ctx.hooks, ctx.player, SetupStrikePower, self._strength, applier=ctx.player
        )
