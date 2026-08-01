from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ShameCard(Card):
    """Curse — Unplayable; at the end of your turn, gain 1 Frail.

    Source: Shame.cs
      Cost -1 | Curse | Curse | TargetType.None | DynamicVar("Frail", 1)
      Keywords: Unplayable; HasTurnEndInHandEffect
      OnTurnEndInHand: apply 1 Frail to owner. The game then sets
      SkipNextDurationTick when the Frail is new, but PowerCmd.Apply already
      does that for every debuff landing on the player (mirrored by the sim's
      PowerCmd.apply), so no extra handling is needed.
    """
    id = "shame"
    name = "Shame"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = -1
        self._frail = 1     # DynamicVar("Frail", 1m), Shame.cs:22

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import PowerCmd
        from ..powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, self._frail)
