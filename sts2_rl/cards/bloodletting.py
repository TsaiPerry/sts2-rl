from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BloodlettingCard(Card):
    """Skill (Common, 0E) — lose 3 HP; gain 2 energy.

    Source: Bloodletting.cs
      Cost 0 | Skill | Common | TargetType.Self
      OnPlay: CreatureCmd.Damage(self, 3, Unblockable|Unpowered|Move), then GainEnergy(2)
      OnUpgrade: energy +1 (→ 3)
    """
    id = "bloodletting"
    name = "Bloodletting"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._hp_loss = 3
        self._energy = 2

    def _on_upgrade(self) -> None:
        self._energy += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, EnergyCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(ctx.hooks, ctx.player, self._hp_loss, card=self, props=DamageProps.CARD_HP_LOSS)
        # Bloodletting.cs has no is_dead guard here -- C# unconditionally
        # awaits PlayerCmd.GainEnergy next. No divergence to reproduce:
        # EnergyCmd.gain's own is_ending bail (cmds.py, mirroring
        # PlayerCmd.GainEnergy's IsEnding bail, PlayerCmd.cs:31) already makes
        # this a no-op on a dying player -- see card/_is_dead_early_return
        # (Task 20) and test/test_is_dead_early_returns.py.
        EnergyCmd.gain(ctx.hooks, ctx.player, self._energy)
