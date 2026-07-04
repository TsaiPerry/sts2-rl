from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ToxicCard(Card):
    """Status added by the Myte's TOXIC move.

    Source: Toxic.cs
      Cost 1 | Status | Status | TargetType.None | Exhaust
      Playing it does nothing (the play just gets rid of it, exhausting).
      If it is still in hand at end of turn: take 5 damage
      (ValueProp.Unpowered | Move — blockable, unmodified).
    """
    id = "toxic"
    name = "Toxic"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    max_upgrade_level = 0
    is_unpowered = True
    exhausts = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.player, 5, dealer=None, card=self)
