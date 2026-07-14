from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class RoyalPoison(Relic):
    """At the start of your first turn each combat, lose 4 HP.

    Source: RoyalPoison.cs — AfterPlayerTurnStart on turn 1 deals DamageVar(4,
    Unblockable | Unpowered) to the owner. Granted by the Round Tea Party event
    (Enjoy Tea)."""

    id = "royal_poison"
    name = "Royal Poison"
    rarity = RelicRarity.EVENT

    DAMAGE = 4

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn != 1:
            return
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(
            self.hooks, player, self.DAMAGE, props=DamageProps.NON_CARD_HP_LOSS
        )
