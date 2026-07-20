from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class SneckoEye(Relic):
    """SneckoEye.cs — draw 2 extra cards each turn, but you are Confused for
    the whole combat (every drawn card's cost becomes a random 0-3). Offered
    by the Darv shrine."""

    id = "snecko_eye"
    name = "Snecko Eye"
    rarity = RelicRarity.ANCIENT

    CARDS = 2

    def on_combat_start(self) -> None:
        from ..cmds import PowerCmd
        from ..powers import ConfusedPower

        PowerCmd.apply(
            self.hooks, self.combat.player, ConfusedPower, 1,
            applier=self.combat.player,
        )

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        return count + self.CARDS
