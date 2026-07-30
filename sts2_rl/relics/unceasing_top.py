from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..turn_phase import PlayerTurnPhase

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class UnceasingTop(Relic):
    """Whenever your hand is empty during your turn, draw 1 card.

    UnceasingTop.cs:16-23 — `AfterHandEmptied`, i.e. whatever
    `CombatManager.CheckForEmptyHand` decides is an empty hand. The sim used
    to hand-roll the condition on `on_card_played` because the card-play call
    site did not exist (turn_structure G16).
    """

    id = "unceasing_top"
    name = "Unceasing Top"
    rarity = RelicRarity.RARE

    #: UnceasingTop.IsValidPhase (:29-36) is `(uint)(phase - 2) <= 2u`, i.e.
    #: exactly {AutoPrePlay, Play, AutoPostPlay}. The relic's own remark
    #: (:25-28) says why: "Don't trigger before hand draw or after hand flush,
    #: because if a card is autoplayed during this time, the player's hand will
    #: always be empty, so Unceasing Top will always draw."
    _VALID_PHASES = (
        PlayerTurnPhase.AUTO_PRE_PLAY,
        PlayerTurnPhase.PLAY,
        PlayerTurnPhase.AUTO_POST_PLAY,
    )

    def on_hand_emptied(self, player: PlayerCombatState) -> None:
        if player is not self.player:
            return                       # `player == base.Owner` (:18)
        if player.turn_phase not in self._VALID_PHASES:
            return
        from ..cmds import DrawCmd
        DrawCmd.draw(self.player, 1)
