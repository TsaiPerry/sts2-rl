"""final_deck_histogram: the end-of-run deck census behind eval.py --deck-hist.

The exclusions (starter / colorless / curse / quest) and the kept-rarity set
are the whole contract, so each one gets its own assertion here rather than
being inferred from a full-run integration test.
"""
from types import SimpleNamespace

from sts2_rl.cards import make_card
from sts2_rl.characters import get_character
from sts2_rl.deck_stats import final_deck_histogram


def _run(*card_ids, character="ironclad"):
    """A RunState-shaped double: the classifier only reads .deck/.character."""
    return SimpleNamespace(
        deck=[make_card(cid) for cid in card_ids],
        character=get_character(character),
    )


def test_counts_kept_rarities_by_class_name():
    hist = final_deck_histogram(_run("anger", "anger", "inflame", "demon_form"))
    assert hist == {
        "common": {"AngerCard": 2},
        "uncommon": {"InflameCard": 1},
        "rare": {"DemonFormCard": 1},
    }


def test_upgraded_copies_fold_into_one_entry():
    run = _run("anger", "anger")
    run.deck[0].upgrade()
    hist = final_deck_histogram(run)
    assert hist == {"common": {"AngerCard": 2}}


def test_starter_cards_excluded():
    # Every id in the character's starting deck, plus one real card.
    hist = final_deck_histogram(_run("strike", "defend", "bash", "anger"))
    assert hist == {"common": {"AngerCard": 1}}


def test_colorless_curse_quest_and_off_rarity_excluded():
    # finesse is uncommon BUT colorless, so rarity alone would let it through.
    hist = final_deck_histogram(
        _run("finesse", "clumsy", "byrdonis_egg", "burn", "break", "anger"))
    assert hist == {"common": {"AngerCard": 1}}


def test_all_excluded_deck_is_empty_not_padded():
    # No empty-rarity keys: a rarity with nothing in it is omitted entirely.
    assert final_deck_histogram(_run("strike", "clumsy")) == {}


def test_empty_deck():
    assert final_deck_histogram(_run()) == {}
