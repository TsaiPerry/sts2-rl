from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..creatures import Creature


@register_card
class RegretCard(Card):
    """Curse — Unplayable; at the end of your turn, lose 1 HP per card in
    your hand.

    Source: Regret.cs
      Cost -1 | Curse | Curse | TargetType.None
      Keywords: Unplayable; HasTurnEndInHandEffect
      BeforeSideTurnEnd: snapshots the hand size (Regret counts itself).
      OnTurnEndInHand: that many damage, Unblockable | Unpowered | Move.
    """
    id = "regret"
    name = "Regret"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards_in_hand = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_player_turn_end(self, player: Creature) -> None:
        # BeforeSideTurnEnd: the hand is still intact here (turn-end-in-hand
        # processing removes cards one by one, so the count is taken early).
        if self.combat is not None and self in self.combat.player.hand:
            self._cards_in_hand = len(self.combat.player.hand)

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(
            ctx.hooks,
            ctx.player,
            self._cards_in_hand,
            card=self,
            props=DamageProps.CARD_HP_LOSS,
        )
        self._cards_in_hand = 0
