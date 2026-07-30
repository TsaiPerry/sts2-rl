from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class IronClub(Relic):
    """IronClub.cs — every 6th card you play, draw 1 card (CardsVar(6); the
    counter is a SavedProperty, so it persists across combats)."""

    id = "iron_club"
    name = "Iron Club"
    rarity = RelicRarity.ANCIENT

    # IronClub.cs:38 — `CanonicalVars => ... new CardsVar(4)`, read by
    # DisplayAmount (:32), UpdateDisplay (:77) and the draw condition
    # `CardsPlayed % intValue == 0` (:88-89). There is no
    # AscensionHelper.GetValueIfAscension anywhere in the file, so 4 is the
    # pinned non-ascension value; the port had 6.
    CARDS = 4

    def __init__(self) -> None:
        super().__init__()
        self.cards_played = 0

    def on_card_played(self, card: "Card",
                       is_auto_play: bool = False) -> None:
        from ..cmds import DrawCmd

        self.cards_played += 1
        if self.cards_played % self.CARDS == 0:
            DrawCmd.draw(self.player, 1)
