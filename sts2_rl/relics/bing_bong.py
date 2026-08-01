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

    The source guards against runaway recursion with TWO independent
    defenses: this `CardsToSkip` set (consumed when its own
    AfterCardChangedPiles fires, so a clone never clones itself) AND the
    `clonedBy` argument `AfterCardChangedPiles(card, oldPileType, clonedBy)`
    carries — `clonedBy != null` blocks the clone outright, for ANY model's
    add, not just BingBong's own (BingBong.cs:25). The sim's
    `after_card_added_to_deck(self, run, card)` (relics/base.py:318) has no
    such argument, so this only reproduces the CardsToSkip half — relic/
    bing_bong/g1, DORMANT: re-verified 2026-07-31 (task 31), no other ported
    model ever sets a clonedBy-equivalent (the only non-null setter besides
    BingBong itself is Hoarder, a custom-run Modifier the sim doesn't have;
    Dolly's Mirror, the one other ported deck-cloner, doesn't set it either —
    DollysMirror.cs:22 passes no 4th argument). Threading an adder through the
    hook signature was judged not worth doing yet: it would touch every
    implementer of `after_card_added_to_deck` (book_of_five_rings.py,
    darkstone_periapt.py, lucky_fysh.py, this file) for zero observable
    effect today. One of the three dolls in the Doll Room event.
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
