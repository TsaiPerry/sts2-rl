from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature
    from ..player import PlayerCombatState


@register_relic
class SelfFormingClay(Relic):
    """Whenever you lose HP in combat, gain 3 Block at the start of your next
    turn (accumulates per HP-loss event, mirrors SelfFormingClayPower)."""

    id = "self_forming_clay"
    name = "Self-Forming Clay"
    rarity = RelicRarity.UNCOMMON

    BLOCK = 3

    def __init__(self) -> None:
        super().__init__()
        self._pending_block = 0

    def reset_for_combat(self) -> None:
        # C# has no relic-side counter: SelfFormingClay.cs:29 applies a
        # SelfFormingClayPower and powers do not survive a combat, so the
        # pending Block cannot leak into the next fight. Clearing it here is
        # the sim's equivalent boundary.
        self._pending_block = 0

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp,
    ) -> None:
        if target is self.player and amount > 0:
            self._pending_block += self.BLOCK

    def on_block_cleared(self, target: Creature) -> None:
        # SelfFormingClayPower.AfterBlockCleared (SelfFormingClayPower.cs:19-25)
        # fires in the BLOCK-CLEAR pass — turn_structure step ~11, before the
        # energy reset, before ModifyHandDraw and before the whole
        # AfterPlayerTurnStart / AfterSideTurnStart region. The port used
        # `on_player_turn_started`, the LAST turn-start slot (step 23), so
        # anything that damages the player in between was banked and paid out the
        # SAME turn instead of the next one. Royal Poison damages its owner from
        # AfterPlayerTurnStart (RoyalPoison.cs:18, step 22), which is inside the
        # window: with the relics registered [royal_poison, self_forming_clay] the
        # sim opened turn 1 on 3 block where the game gives 0 in either order.
        if target is not self.player:
            return
        if self._pending_block:
            from ..cmds import BlockCmd
            BlockCmd.apply(
                self.hooks, target, self._pending_block, props=ValueProp.UNPOWERED
            )
            self._pending_block = 0
