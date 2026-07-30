"""`CardModel.CreateClone` is a MEMBERWISE copy (round 7).

`ClonePreservingMutability` -> `AbstractModel.MutableClone` (a memberwise copy)
-> `CardModel.DeepCloneFields` (CardModel.cs:1193-1216) -> `AfterCloned`
(:1218-1239). The sim rebuilt from the class and replayed upgrades instead, so
every per-instance edit that was not a printed number was dropped.

Queue entries: card/anger/OnPlay, card/dual_wield/OnPlay,
relic/burning_sticks/g2, relic/music_box/g1 (and relic/dollys_mirror/g1, whose
implementation warning was "do not add a sixth rebuild-from-id site").
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cards.base import create_clone


def _fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


def test_clone_carries_the_local_keyword_set():
    """`_keywords = GetKeywordsWithSources(KeywordSources.Local)`
    (CardModel.cs:1196-1200). Music Box applies Ethereal exactly that way, and
    its own doc comment names the relic."""
    card = make_card("strike")
    card.is_ethereal = True
    assert create_clone(card).is_ethereal is True


def test_clone_carries_the_local_energy_cost_modifiers():
    """`_energyCost = _energyCost?.Clone(this)` (CardModel.cs:1202) and
    `CardEnergyCost.Clone` copies `_localModifiers` (CardEnergyCost.cs:411-421)."""
    card = make_card("strike")
    card.set_cost_this_combat(0)
    assert create_clone(card).energy_cost == 0

    other = make_card("strike")
    other.set_free_this_turn()
    assert create_clone(other).energy_cost == 0


def test_clone_carries_base_replay_count():
    """Hidden Gem raises `CardModel.BaseReplayCount`; a memberwise copy keeps
    it."""
    card = make_card("strike")
    card.base_replay_count = 3
    assert create_clone(card).base_replay_count == 3


def test_clone_carries_the_accumulated_dynamic_vars():
    """`_dynamicVars = DynamicVars.Clone(this)` (CardModel.cs:1201) — the
    ACCUMULATED values, not the canonical ones. A grown Rampage clones grown."""
    cs = _fresh()
    card = make_card("rampage")
    for _ in range(2):
        card.on_play(cs._ctx(), target_idx=0)
    assert card._damage == 19
    assert create_clone(card)._damage == 19


def test_clone_clears_exhaust_on_next_play():
    """CardModel.cs:2178 — CreateClone's own tail."""
    card = make_card("strike")
    card.exhaust_on_next_play = True
    assert create_clone(card).exhaust_on_next_play is False


def test_clone_does_not_share_the_sources_enchantment_object():
    """`DeepCloneFields` re-attaches a `ClonePreservingMutability` copy
    (CardModel.cs:1204-1209), not the source's own object."""
    from sts2_rl.enchantments import make_enchantment
    card = make_card("strike")
    make_enchantment("spiral").attach(card)
    clone = create_clone(card)
    assert clone.enchantment is not None
    assert clone.enchantment is not card.enchantment
    assert clone.enchantment.id == card.enchantment.id


def test_clone_does_not_share_the_sources_affliction_object():
    from sts2_rl.afflictions import EntangledAffliction
    from sts2_rl.cmds import CardCmd
    card = make_card("strike")
    CardCmd.afflict(card, EntangledAffliction, 1)
    clone = create_clone(card)
    assert clone.affliction is not None
    assert clone.affliction is not card.affliction
    assert clone.affliction.card is clone


def test_clone_keeps_the_upgrade_level():
    card = make_card("strike")
    card.upgrade()
    clone = create_clone(card)
    assert clone.upgrade_level == 1
    assert clone._damage == card._damage


def test_clone_keeps_the_combat_back_reference():
    """`CardModel.CombatState` (CardModel.cs:1017-1028) resolves through
    `_owner`, and NEITHER `DeepCloneFields` (:1193-1216) nor `AfterCloned`
    (:1218-1239) touches `_owner` — AfterCloned nulls CurrentTarget,
    CurrentPlayIndex, DeckVersion, HasBeenRemovedFromState and the event
    handlers, and the owner is not among them. So a clone reaches the combat
    exactly as its source does, and so does the enchantment copy hanging off
    it (which in C# has no combat field at all: it reads `base.Card.Owner`)."""
    from sts2_rl.enchantments import make_enchantment
    cs = _fresh()
    card = make_card("strike")
    enchantment = make_enchantment("adroit")
    enchantment.amount = 3
    enchantment.attach(card)
    cs.player.hand.clear()
    cs.player.hand.append(card)
    card.combat = cs
    enchantment.combat = cs

    clone = create_clone(card)
    assert clone.combat is cs
    assert clone.enchantment.combat is cs

    # And the copy is playable: Adroit's OnPlay is the first enchantment effect
    # that needs the combat, and it used to raise AttributeError on a clone.
    cs.player.hand.clear()
    cs.player.hand.append(clone)
    before = cs.player.block
    assert cs.play_card(0, target_idx=0)
    assert cs.player.block == before + 3


def test_the_relic_and_card_copy_sites_all_carry_the_state():
    """The four ported sites this mechanism covers go through `create_clone`,
    so one fix closes them together. Burning Sticks and Music Box copy a card
    whose cost the potions/relics routinely cut."""
    from sts2_rl.cards.trash_heap_cards import _clone
    card = make_card("strike")
    card.set_cost_this_combat(0)
    card.base_replay_count = 2
    copy = _clone(card)
    assert copy.energy_cost == 0 and copy.base_replay_count == 2
