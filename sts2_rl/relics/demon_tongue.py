from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature
    from ..player import PlayerCombatState

@register_relic
class DemonTongue(Relic):
    """Once per turn, when you lose HP during your own turn, heal that much
    HP (Ironclad self-damage synergy)."""

    id = "demon_tongue"
    name = "Demon Tongue"
    rarity = RelicRarity.RARE

    def __init__(self) -> None:
        super().__init__()
        self._triggered_this_turn = False

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp,
    ) -> None:
        if (
            not self._triggered_this_turn
            and target is self.player
            and amount > 0
            and self.combat.current_side == "player"
        ):
            from ..cmds import CreatureCmd
            self._triggered_this_turn = True
            CreatureCmd.heal(self.hooks, self.player, amount)

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        self._triggered_this_turn = False
