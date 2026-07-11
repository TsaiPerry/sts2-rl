from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..combat import CombatState
    from ..player import PlayerCombatState

@register_relic
class GamblingChip(Relic):
    """At the start of combat, you may discard any number of cards, then
    draw that many. The choice goes through CombatState.select_cards with
    purpose "gambling_chip" (candidates = hand, count = hand size; the
    selector may return fewer — the scripted selector discards only
    Status/Curse cards, the default random selector mulligans the hand)."""

    id = "gambling_chip"
    name = "Gambling Chip"
    rarity = RelicRarity.RARE

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn > 1:
            return
        chosen = self.combat.select_cards(
            "gambling_chip", list(player.hand), len(player.hand)
        )
        if not chosen:
            return
        from ..cmds import DrawCmd
        for card in chosen:
            player.hand.remove(card)
            player.discard_pile.append(card)
            self.hooks.on_card_discarded(card)
        DrawCmd.draw(player, len(chosen))
