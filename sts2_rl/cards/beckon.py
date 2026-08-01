from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BeckonCard(Card):
    """Status (1E) — playable with no effect; at the end of your turn, if in
    hand, lose 6 HP.

    Source: Beckon.cs (created by Soul Fysh)
      Cost 1 | Status | Status | TargetType.None | HpLossVar(6)
      OnTurnEndInHand: 6 damage, Unblockable | Unpowered | Move
    """
    id = "beckon"
    name = "Beckon"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    max_upgrade_level = 0
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._hp_loss = 6       # HpLossVar(6m), Beckon.cs:17

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(
            ctx.hooks, ctx.player, self._hp_loss, card=self,
            props=DamageProps.CARD_HP_LOSS,
        )
