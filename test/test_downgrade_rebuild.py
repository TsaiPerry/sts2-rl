"""`CardModel.DowngradeInternal` — the rebuild-from-canonical (round 7).

`creature_card_cmds/step52` owns the machinery; the eight card entries in this
family (card/aggression, card/apparition, card/hello_world, card/juggling and
card/wish on OnUpgrade; card/maul, card/rampage and card/thrash on
AfterDowngraded) all follow from it by binding rule 3.

The source is CardModel.cs:2134-2148, in order: `CurrentUpgradeLevel = 0`;
re-derive `_dynamicVars` from the canonical model; `EnergyCost.ResetForDowngrade`;
**`_keywords = cardModel.GetKeywordsWithSources(KeywordSources.Local).ToHashSet()`**;
`AfterDowngraded()`; `Enchantment?.ModifyCard()`. The sim re-ran `_init_vars`
instead, which rebuilds only what a card happens to set there — so a keyword an
`_on_upgrade` had written as an INSTANCE attribute shadowed the class default
and survived, and a card that accumulated damage into `_damage` lost it with no
`AfterDowngraded` to put it back.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, DamageCmd
from sts2_rl.cards import make_card
from sts2_rl.cards.base import _CARD_CLASSES
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS

# CardKeyword.cs — the whole enum, minus None. `is_playable` is Unplayable
# inverted.
_KEYWORD_ATTRS = ("exhausts", "is_ethereal", "innate", "is_playable",
                  "retain", "sly", "eternal")


def _fresh(cs: CombatState = None):
    return CombatState(rng=random.Random(0),
                       encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]))


# ══════════════════════════════════════════════════════════════════════════
# The keyword rebuild — the five sticky cards, then the whole pool
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("card_id,attr", [
    ("aggression", "innate"),
    ("apparition", "is_ethereal"),
    ("hello_world", "innate"),
    ("juggling", "innate"),
    ("wish", "retain"),
])
def test_upgrade_then_downgrade_restores_the_keyword(card_id, attr):
    card = make_card(card_id)
    printed = getattr(card, attr)
    card.upgrade()
    assert getattr(card, attr) != printed, "the upgrade must move the keyword"
    card.downgrade()
    assert getattr(card, attr) == printed


def test_no_card_in_the_pool_keeps_an_upgrade_keyword_after_downgrade():
    """The invariant `card_probes.py downgrade` measures, as a test. Five of
    203 cards failed it before round 7."""
    sticky = []
    for card_id in sorted(_CARD_CLASSES):
        card = make_card(card_id)
        if not card.is_upgradable:
            continue
        printed = {a: getattr(card, a) for a in _KEYWORD_ATTRS}
        card.upgrade()
        card.downgrade()
        for attr, want in printed.items():
            if getattr(card, attr) != want:
                sticky.append(f"{card_id}.{attr}: {want} -> {getattr(card, attr)}")
    assert sticky == []


def test_downgrade_goes_to_level_zero_not_down_one():
    """CardModel.cs:2137 is `CurrentUpgradeLevel = 0`, not a decrement. No
    ported card reaches level 2 yet, so this only bites the day one does."""
    card = make_card("strike")
    card.upgrade()
    card.downgrade()
    assert card.upgrade_level == 0


# ══════════════════════════════════════════════════════════════════════════
# AfterDowngraded — the three accumulating attacks
# ══════════════════════════════════════════════════════════════════════════

def test_rampage_keeps_the_damage_it_accumulated():
    """Rampage.cs:24-26 says why the private field exists: "Required so we can
    restore the extra damage amount after a downgrade (ie Magiknight)"."""
    cs = _fresh()
    card = make_card("rampage")
    card.upgrade()                                   # increase 5 -> 9
    for _ in range(3):
        card.on_play(cs._ctx(), target_idx=0)
    assert card._damage == 9 + 27
    card.downgrade()
    assert card._damage == 9 + 27


def test_maul_keeps_the_damage_its_plays_accumulated():
    cs = _fresh()
    card = make_card("maul")
    cs.player.hand.append(card)
    card.upgrade()                                   # damage 6, increase 2
    card.on_play(cs._ctx(), target_idx=0)
    card.on_play(cs._ctx(), target_idx=0)
    assert card._damage == 6 + 4
    card.downgrade()
    assert card._damage == 5 + 4


def test_thrash_keeps_the_damage_it_absorbed():
    cs = _fresh()
    card = make_card("thrash")
    victim = make_card("bludgeon")                   # 32 damage
    # The victim is the ONLY attack in hand, so the CombatCardSelection pick is
    # forced. Thrash itself is not in hand: a card mid-OnPlay sits in the Play
    # pile, so it cannot absorb itself.
    cs.player.hand.clear()
    cs.player.hand.append(victim)
    card.upgrade()                                   # damage 6
    card.on_play(cs._ctx(), target_idx=0)
    assert card._damage == 6 + 32
    card.downgrade()
    assert card._damage == 4 + 32


def test_an_accumulator_that_never_played_downgrades_to_printed():
    for card_id, printed in (("rampage", 9), ("maul", 5), ("thrash", 4)):
        card = make_card(card_id)
        card.upgrade()
        card.downgrade()
        assert card._damage == printed, card_id


# ══════════════════════════════════════════════════════════════════════════
# CardCmd.Downgrade's own guard
# ══════════════════════════════════════════════════════════════════════════

def test_card_cmd_downgrade_is_refused_while_the_combat_is_ending():
    """CardCmd.cs:212-223 wraps the whole verb in `if (!IsEnding)`, so a
    downgrade triggered by the killing blow does not land. Same family as
    creature_card_cmds guard G14."""
    from sts2_rl.cmds import CardCmd
    cs = CombatState(rng=random.Random(0),
                     encounter=Encounter("test", [LeafSlimeS]))
    card = make_card("strike")
    card.upgrade()
    DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
    assert cs.is_ending
    CardCmd.downgrade(cs.hooks, card)
    assert card.upgrade_level == 1


def test_card_cmd_downgrade_works_out_of_combat():
    """`IsEnding` opens with `if (!IsInProgress) return false`, so the two
    event callers (Reflections, Welcome to Wongo's) are unaffected."""
    from sts2_rl.cmds import CardCmd
    card = make_card("strike")
    card.upgrade()
    CardCmd.downgrade(None, card)
    assert card.upgrade_level == 0
