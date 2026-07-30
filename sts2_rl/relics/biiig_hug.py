from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class BiiigHug(Relic):
    """BiiigHug.cs — upon pickup, choose 4 deck cards to REMOVE (CardsVar(4)).
    In combat, after every reshuffle a Soot is added to the draw pile
    (AfterShuffle → AddGeneratedCardToCombat, random position)."""

    id = "biiig_hug"
    name = "Biiig Hug"
    rarity = RelicRarity.ANCIENT

    CARDS = 4

    def after_obtained(self, run) -> None:
        candidates = run.removable_cards()
        for card in run.select_cards("remove", candidates, self.CARDS):
            run.remove_cards([card])   # CardPileCmd.RemoveFromDeck

    def on_shuffle(self, player: PlayerCombatState) -> None:
        from ..cards import make_card
        from ..cmds import CardPileCmd

        CardPileCmd.add_to_draw(self.hooks, player, make_card("soot"))
