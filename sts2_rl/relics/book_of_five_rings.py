from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic

@register_relic
class BookOfFiveRings(Relic):
    """BookOfFiveRings.cs — every 5th card added to your deck heals 20 HP
    (AfterCardChangedPiles filtered to PileType.Deck; CardsAdded is a
    [SavedProperty] run counter and the heal fires when
    `CardsAdded % Cards == 0`)."""

    id = "book_of_five_rings"
    name = "Book of Five Rings"
    rarity = RelicRarity.COMMON

    CARDS = 5     # CardsVar(5)
    HEAL = 20     # HealVar(20)

    def __init__(self) -> None:
        super().__init__()
        self.cards_added = 0

    def after_card_added_to_deck(self, run, card) -> None:
        if run.is_dead:
            return
        self.cards_added += 1
        if self.cards_added % self.CARDS == 0:
            run.heal(self.HEAL)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """BookOfFiveRings.cs:72-75: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
