from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class PaelsEye(Relic):
    """PaelsEye.cs — once per combat, ending your turn without having played
    any cards exhausts your hand and grants an extra player turn (the enemy
    side is skipped). ShouldTakeExtraTurn + BeforeSideTurnEndEarly (hand
    exhaust) + AfterTakingExtraTurn (mark used) — the sim folds the latter two
    into the on_extra_turn notification."""

    id = "paels_eye"
    name = "Pael's Eye"
    rarity = RelicRarity.ANCIENT

    def __init__(self) -> None:
        super().__init__()
        self.used_this_combat = False

    def reset_for_combat(self) -> None:
        # PaelsEye.AfterCombatEnd (:129-134).
        self.used_this_combat = False

    def _any_cards_played_this_turn(self) -> bool:
        """PaelsEye.AnyCardsPlayedThisTurn (PaelsEye.cs:149-156).

        Two clauses the sim's bare history scan had neither of:
        (1) on turn 1, merely HOLDING Whispering Earring counts as having
            played — which switches Pael's Eye off for that turn;
        (2) the history scan filters `&& !e.CardPlay.IsAutoPlay`, so auto-plays
            never count.
        The two omissions CANCEL in the common Whispering-Earring case (the
        Earring's own turn-1 auto-play made the sim answer True as well) and
        diverge everywhere else.
        """
        from ..history import CardPlayedEntry

        combat = self.combat
        if combat.turn == 1 and any(
            r.id == "whispering_earring" for r in getattr(combat, "relics", ())
        ):
            return True
        return any(
            e for e in combat.history.of_type(CardPlayedEntry, this_turn=True)
            if not e.is_auto_play
        )

    def should_take_extra_turn(self, player: PlayerCombatState) -> bool:
        return (
            not self.used_this_combat
            and not self._any_cards_played_this_turn()
        )

    def on_player_turn_end_early(self, player: PlayerCombatState) -> None:
        """PaelsEye.cs:118-128 is BeforeSideTurnEndEarly — the hand is exhausted
        in the EARLY pass of Hook.BeforeTurnEnd, i.e. before the flush, under
        the same predicate ShouldTakeExtraTurn uses.

        The sim used to fold this into `on_extra_turn` because it had no Early
        phase and evaluated ShouldTakeExtraTurn at the TOP of end_turn, so the
        exhaust happened before the hand was discarded by accident. With the
        predicate moved to its real position (turn_structure/G3) that fold no
        longer works, and the phase machinery (hook_dispatch/G3) now gives the
        exhaust its real home.
        """
        if self.used_this_combat or self._any_cards_played_this_turn():
            return
        from ..cmds import ExhaustCmd

        for card in list(player.hand):
            ExhaustCmd.exhaust(self.hooks, player, card)

    def on_extra_turn(self, player: PlayerCombatState) -> None:
        # PaelsEye.AfterTakingExtraTurn (:130-140) is bookkeeping only.
        self.used_this_combat = True
