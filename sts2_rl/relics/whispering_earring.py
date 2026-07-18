from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class WhisperingEarring(Relic):
    """WhisperingEarring.cs — +1 max Energy (EnergyVar(1)); on turn 1 it
    AUTO-PLAYS your playable cards one after another (first playable in hand,
    up to 13) until none remains, the combat ends, or the turn changes."""

    id = "whispering_earring"
    name = "Whispering Earring"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1
    MAX_CARDS = 13

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn != 1:
            return
        combat = self.combat
        start_turn = self.turn
        # The source loop SPENDS resources (card.SpendResources() before each
        # AutoPlay), so cards play through the normal cost path and stop when
        # nothing is affordable. (The game tags these plays IsAutoPlay for
        # per-turn card counters; the sim's on_card_played carries no auto
        # flag — a known divergence shared with Havoc-style auto-plays.)
        for _ in range(self.MAX_CARDS):
            if combat.is_over or self.turn != start_turn:
                break
            playable = [a for a in combat.valid_actions() if a != 0]
            if not playable:
                break
            combat.play_card(playable[0] - 1)
