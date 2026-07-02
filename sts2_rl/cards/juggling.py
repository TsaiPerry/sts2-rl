from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class JugglingCard(Card):
    """Power (Uncommon, 1E) — whenever you play your 3rd Attack in a turn, add
    a copy of it to your hand.

    Source: Juggling.cs
      Cost 1 | Power | Uncommon | TargetType.Self
      OnPlay: PowerCmd.Apply<JugglingPower>(1)
      OnUpgrade: AddKeyword(Innate)
    """
    id = "juggling"
    name = "Juggling"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self.innate = True

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import JugglingPower
        PowerCmd.apply(ctx.hooks, ctx.player, JugglingPower, 1, applier=ctx.player)
