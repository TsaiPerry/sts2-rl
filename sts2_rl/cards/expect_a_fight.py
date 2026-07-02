from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ExpectAFightCard(Card):
    """Skill (Uncommon, 2E) — gain 1 energy per Attack card in your hand; you
    cannot gain energy again this turn.

    Source: ExpectAFight.cs
      Cost 2 | Skill | Uncommon | TargetType.Self
      OnPlay: PlayerCmd.GainEnergy(0 + 1 × attacks in hand),
              then PowerCmd.Apply<NoEnergyGainPower>(1)
      OnUpgrade: cost -1 (→ 1)
    """
    id = "expect_a_fight"
    name = "Expect A Fight"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import EnergyCmd, PowerCmd
        from ..powers import NoEnergyGainPower
        attacks = sum(1 for c in ctx.player.hand if c.card_type == CardType.ATTACK)
        if attacks > 0:
            EnergyCmd.gain(ctx.hooks, ctx.player, attacks)
        PowerCmd.apply(ctx.hooks, ctx.player, NoEnergyGainPower, 1, applier=ctx.player)
