from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class InfectionCard(Card):
    """Status — Unplayable; at the end of your turn, take 3 damage.

    Source: Infection.cs
      Cost -1 | Status | Status | TargetType.None | Unplayable
      DamageVar(3, Unpowered | Move); HasTurnEndInHandEffect
      OnTurnEndInHand: CreatureCmd.Damage(owner, 3)
    """
    id = "infection"
    name = "Infection"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.player, 3, dealer=None, card=self)
