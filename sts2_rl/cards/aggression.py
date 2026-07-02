from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class AggressionCard(Card):
    """Power (Rare, 1E) — at the start of your turn, return a random Attack
    from your discard pile to your hand and upgrade it.

    Source: Aggression.cs
      Cost 1 | Power | Rare | TargetType.Self
      OnPlay: PowerCmd.Apply<AggressionPower>(1)
      OnUpgrade: AddKeyword(Innate)
    """
    id = "aggression"
    name = "Aggression"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self.innate = True

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import AggressionPower
        PowerCmd.apply(ctx.hooks, ctx.player, AggressionPower, 1, applier=ctx.player)
