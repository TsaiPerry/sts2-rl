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

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self._pending_block:
            from ..cmds import BlockCmd
            BlockCmd.apply(
                self.hooks, player, self._pending_block, props=ValueProp.UNPOWERED
            )
            self._pending_block = 0
