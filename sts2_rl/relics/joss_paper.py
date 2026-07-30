from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState

@register_relic
class JossPaper(Relic):
    """Every 5 cards you exhaust, draw 1 card. Exhausts caused by Ethereal
    are counted after the end-of-turn hand flush (mirrors the game's
    deferral so the drawn card is not immediately discarded; the sim uses
    card.is_ethereal as the caused-by-ethereal signal)."""

    id = "joss_paper"
    name = "Joss Paper"
    rarity = RelicRarity.UNCOMMON

    EXHAUST_AMOUNT = 5

    def __init__(self) -> None:
        super().__init__()
        self.cards_exhausted = 0
        self._ethereal_pending = 0

    def reset_for_combat(self) -> None:
        # JossPaper.AfterCombatEnd (:181-185) clears EtherealCount ONLY —
        # CardsExhausted is a [SavedProperty] (:60-76) and persists.
        self._ethereal_pending = 0

    def _draw_if_threshold_met(self) -> None:
        if self.cards_exhausted >= self.EXHAUST_AMOUNT:
            from ..cmds import DrawCmd
            DrawCmd.draw(self.player, self.cards_exhausted // self.EXHAUST_AMOUNT)
            self.cards_exhausted %= self.EXHAUST_AMOUNT

    def on_card_exhausted(self, card: Card,
                          caused_by_ethereal: bool = False) -> None:
        # JossPaper.cs:102-114 branches on the CAUSE parameter, not on the
        # card. `causedByEthereal: true` comes from exactly two turn-end sites
        # (CombatManager.cs:1240, CardModel.cs:1692), so an Ethereal card
        # exhausted mid-play-phase is credited AT ONCE — the sim read
        # `card.is_ethereal` and withheld it until the flush.
        if caused_by_ethereal:
            self._ethereal_pending += 1
            return
        self.cards_exhausted += 1
        self._draw_if_threshold_met()

    def after_player_turn_end(self, player: PlayerCombatState) -> None:
        # JossPaper.cs:116-124 — the deferred credit is `AfterSideTurnEnd`,
        # which Hook.AfterTurnEnd (Hook.cs:1267-1278) dispatches from
        # CombatManager.cs:1307, AFTER FlushPlayerHand. That is what the
        # relic's own comment (:71-75) asks for: "we want to give the resulting
        # cards to the player after the flush occurs". The sim hung it on
        # `on_hand_emptied` instead, a different hook that only happened to
        # fire from inside the flush (turn_structure G16).
        #
        # `participants.Contains(Owner.Creature)` (:118) is the player-side
        # test; `after_player_turn_end` IS the player side's leg of the hook.
        self.cards_exhausted += self._ethereal_pending
        self._ethereal_pending = 0
        self._draw_if_threshold_met()
