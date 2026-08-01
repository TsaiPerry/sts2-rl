from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DoubtCard(Card):
    """Curse — Unplayable; at the end of your turn, gain 1 Weak.

    Source: Doubt.cs
      Cost -1 | Curse | Curse | TargetType.None | PowerVar<WeakPower>(1)
      Keywords: Unplayable; HasTurnEndInHandEffect
      OnTurnEndInHand: apply 1 Weak to owner. The game then sets
      SkipNextDurationTick when the Weak is new, but PowerCmd.Apply already
      does that for every debuff landing on the player (mirrored by the sim's
      PowerCmd.apply), so no extra handling is needed.
    """
    id = "doubt"
    name = "Doubt"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = -1
        self._weak = 1      # PowerVar<WeakPower>(1m), Doubt.cs:20

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import PowerCmd
        from ..powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, self._weak)
