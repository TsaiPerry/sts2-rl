"""End-of-run deck census -- the data behind eval.py's ``--deck-hist``.

Kept deliberately out of ``run_env.py`` (already large) and out of
``evaluation.py`` (which imports no card content): this is the one place that
decides what counts as a "card the policy chose to run", and it is the file
that needs editing when a new character lands.
"""
from __future__ import annotations

from typing import Any

from .cards import CardRarity, CardType
from .cards.pool import COLORLESS_POOL

#: The rarities that get a histogram block. BASIC (the starting Strike/
#: Defend/Bash), ANCIENT, TOKEN, STATUS, EVENT, CURSE and QUEST are all
#: excluded: none of them is a card the policy picked out of a reward screen.
KEPT_RARITIES: tuple[CardRarity, ...] = (
    CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE,
)

_COLORLESS_IDS = frozenset(COLORLESS_POOL)


def final_deck_histogram(run: Any) -> dict[str, dict[str, int]]:
    """``{rarity value: {card class name: copies}}`` for a finished run's deck.

    Excludes starter cards (the character's own ``starting_deck`` ids --
    character-general, unlike a ``CardRarity.BASIC`` test), colorless cards,
    curses and quest cards, then keeps only ``KEPT_RARITIES``. That last
    filter would already catch curses and quests today; the explicit
    ``card_type`` check is kept because they are the *stated* exclusions and
    must not rest on a rarity coincidence.

    The card key is the Python class name, matching the ``card`` column of
    the offer/take ``.cards.csv``, so the two exports join. It is invariant
    under ``Card.upgrade()``, so upgraded and un-upgraded copies fold into one
    count.

    Returns plain nested dicts (rarity keys are ``CardRarity`` *values*), so
    the result crosses the vec-env ``info`` boundary like the existing
    ``ep_card_offer_ids`` counters. A rarity with no surviving cards is
    omitted rather than emitted empty.
    """
    # NOTE for future characters: this exclusion is by card id, not rarity.
    # For the Ironclad it is inert (its starters are all CardRarity.BASIC,
    # which KEPT_RARITIES would already drop), but a future character whose
    # starting deck contains a non-basic card that ALSO appears in that
    # character's reward pool would have reward-obtained copies of that card
    # silently excluded here. Re-check this when a new character is ported.
    starter_ids = frozenset(run.character.starting_deck)
    hist: dict[str, dict[str, int]] = {}
    for card in run.deck:
        if card.id in starter_ids or card.id in _COLORLESS_IDS:
            continue
        if card.card_type in (CardType.CURSE, CardType.QUEST):
            continue
        if card.rarity not in KEPT_RARITIES:
            continue
        bucket = hist.setdefault(card.rarity.value, {})
        name = type(card).__name__
        bucket[name] = bucket.get(name, 0) + 1
    return hist
