from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DecayCard(Card):
    """Curse — Unplayable; at the end of your turn, take 2 damage.

    Source: Decay.cs
      Cost -1 | Curse | Curse | TargetType.None | DamageVar(2, Unpowered | Move)
      Keywords: Unplayable; HasTurnEndInHandEffect
      OnTurnEndInHand: 2 damage (blockable, like Burn)
    """
    id = "decay"
    name = "Decay"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = -1
        self._damage = 2   # DamageVar(2m, Unpowered | Move), Decay.cs:15

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.player, self._damage, dealer=None, card=self)
