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

    def after_auto_pre_play_phase_entered_late(self, player: PlayerCombatState) -> None:
        # WhisperingEarring.cs:41 is AfterAutoPrePlayPhaseEntered LATE.
        if self.turn != 1:
            return
        combat = self.combat
        start_turn = self.turn
        # The source loop SPENDS resources and then AUTO-plays:
        # `await card.SpendResources(); await CardCmd.AutoPlay(choiceContext,
        # card, target, AutoPlayType.Default, skipXCapture: true)`
        # (WhisperingEarring.cs:78-80). So the cost path is the normal one --
        # the loop stops when nothing is affordable -- but the resulting
        # CardPlay carries IsAutoPlay, which the per-turn card counters read.
        # The sim used to call the MANUAL `play_card`, so Tuning Fork and every
        # other `is_auto_play` listener counted these as real plays.
        # WhisperingEarring.cs:58-69 breaks on THREE conditions, in this
        # order: IsOverOrEnding, IsPlayerReadyToEndTurn(player), and
        # TurnNumber != startTurn. The readiness break only became reachable
        # once the sim modelled the deferred end-turn transition
        # (turn_structure N1) — before that an end_turn during the setup
        # window had nowhere to be recorded.
        # WhisperingEarring.cs:54 wraps the whole loop in
        # `using (CardSelectCmd.PushSelector(new VakuuCardSelector()))`, and
        # VakuuCardSelector.GetSelectedCards is `options.Take(maxSelect)` in
        # row-major order — fully deterministic, and it takes NO RNG draw. The
        # port installed nothing, so `CombatState.select_cards` fell through to
        # `self._rng.sample(candidates, count)`: the wrong card was picked (the
        # Earring auto-playing Armaments upgraded a different card on every seed,
        # where the game always upgrades the FIRST option) AND the sim consumed
        # shared-rng draws the game does not consume at all. Eight ported cards
        # open a selection screen from OnPlay, so the pairing needs no second
        # relic. Restored on the way out so a real agent's selector is not lost.
        previous_selector = combat.card_selector
        combat.card_selector = (
            lambda purpose, candidates, count: list(candidates)[:count])
        try:
            self._auto_play_loop(combat, start_turn)
        finally:
            combat.card_selector = previous_selector

    def _auto_play_loop(self, combat, start_turn) -> None:
        for _ in range(self.MAX_CARDS):
            if combat.is_over_or_ending:
                break
            if combat.is_player_ready_to_end_turn:
                break
            if self.turn != start_turn:
                break
            playable = [a for a in combat.valid_actions() if a != 0]
            if not playable:
                break
            card = combat.player.hand[playable[0] - 1]
            # `card.SpendResources()` (CardModel.cs:1816-1829) — the energy is
            # paid here, and `CardCmd.AutoPlay` itself is free.
            cost = combat.hooks.modify_card_energy_cost(card, card.energy_cost)
            if card.energy_cost_x:
                cost = combat.player.energy
                card.captured_x = combat.hooks.modify_x_value(card, cost)
            combat.player.energy -= cost
            combat.hooks.on_energy_spent(card, cost)
            combat.auto_play_card(card)
