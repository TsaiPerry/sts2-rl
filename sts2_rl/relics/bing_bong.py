from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class BingBong(Relic):
    """BingBong.cs — whenever a card is added to your deck, add a copy of it
    too (the copy goes to the bottom of the deck).

    The source guards against runaway recursion with a `CardsToSkip` set: the
    clone it adds is registered there and consumed when its own
    AfterCardChangedPiles fires, so a clone never clones itself. One of the
    three dolls in the Doll Room event.
    """

    id = "bing_bong"
    name = "Bing Bong"
    rarity = RelicRarity.EVENT

    def __init__(self) -> None:
        super().__init__()
        self._cards_to_skip: set[int] = set()

    def after_card_added_to_deck(self, run, card: Card) -> None:
        # CardsToSkip.Remove(card) — true only for a card this relic cloned,
        # and consuming the entry lets a later genuine copy clone again.
        if id(card) in self._cards_to_skip:
            self._cards_to_skip.discard(id(card))
            return
        clone = copy.deepcopy(card)
        self._cards_to_skip.add(id(clone))
        run.add_card(clone)
