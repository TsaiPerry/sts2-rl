from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BadLuckCard(Card):
    """Curse — Unplayable, Eternal; at the end of your turn, lose 13 HP.

    Source: BadLuck.cs
      Cost -1 | Curse | Curse | TargetType.None | HpLossVar(13)
      Keywords: Eternal, Unplayable; HasTurnEndInHandEffect
      OnTurnEndInHand: 13 damage, Unblockable | Unpowered | Move
      CanBeGeneratedByModifiers = false
    """
    id = "bad_luck"
    name = "Bad Luck"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    eternal = True
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(
            ctx.hooks, ctx.player, 13, card=self, props=DamageProps.CARD_HP_LOSS
        )
