from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class TauntCard(Card):
    """Skill (Uncommon, 1E) — gain 7 block; apply 1 Vulnerable to the target.

    Source: Taunt.cs
      Cost 1 | Skill | Uncommon | TargetType.AnyEnemy
      OnPlay: GainBlock(7) on self, then Vulnerable 1 to target
      OnUpgrade: block +1 (→ 8), Vulnerable +1 (→ 2)
    """
    id = "taunt"
    gains_block = True  # CardModel.GainsBlock
    name = "Taunt"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 7
        self._vulnerable = 1

    def _on_upgrade(self) -> None:
        self._block += 1
        self._vulnerable += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import VulnerablePower
        target = ctx.resolve_target(target_idx)
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        # No liveness guard: C# applies this unconditionally and the only
        # gate is `Creature.CanReceivePowers` (Creature.cs:308-322), now
        # enforced inside PowerCmd.apply.
        PowerCmd.apply(ctx.hooks, target, VulnerablePower, self._vulnerable, applier=ctx.player)
