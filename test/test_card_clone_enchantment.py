"""Card clones carry their source's enchantment and affliction, and a
downgrade re-applies the enchantment's card modification.

Source: CardModel.CreateClone (CardModel.cs:2168) -> MutableClone ->
DeepCloneFields (CardModel.cs:1204-1215), which re-attaches a live copy of the
source's Enchantment (ClonePreservingMutability -> EnchantInternal at the
source's Amount) and does the same for the Affliction; and
CardModel.DowngradeInternal (CardModel.cs:2145), which re-runs
`Enchantment?.ModifyCard()` after re-deriving the card from its canonical
model. Gap queue entries 18 (enchantment/EG2) and 28
(creature_card_cmds/step52).
"""
import random

import pytest

from sts2_rl.afflictions import EntangledAffliction
from sts2_rl.cards import make_card
from sts2_rl.cards.base import create_clone
from sts2_rl.cards.trash_heap_cards import _clone
from sts2_rl.combat import CombatState
from sts2_rl.enchantments import _ENCHANTMENT_CLASSES, make_enchantment
from sts2_rl.monsters.overgrowth import ENCOUNTERS

WURM = ENCOUNTERS["fuzzy_wurm_weak"]


def build(deck, seed=0):
    return CombatState(starting_deck=deck, rng=random.Random(seed), encounter=WURM)


def enchant(eid, card, amount=1):
    enchantment = make_enchantment(eid)
    enchantment.amount = amount
    enchantment.attach(card)
    return enchantment


# ── CreateClone carries the enchantment ──────────────────────────────────
def test_clone_carries_the_enchantment():
    strike = make_card("strike")
    enchant("sharp", strike, 2)
    clone = _clone(strike)
    assert clone.enchantment is not None  # C#: EnchantInternal on the clone
    assert clone.enchantment.id == "sharp"
    assert clone.enchantment.amount == 2


def test_clone_gets_its_own_enchantment_instance():
    # ClonePreservingMutability makes a COPY: the source keeps its own, and
    # the copy's back-reference points at the clone.
    strike = make_card("strike")
    sharp = enchant("sharp", strike, 2)
    clone = create_clone(strike)
    assert clone.enchantment is not sharp
    assert clone.enchantment.card is clone
    assert strike.enchantment is sharp
    assert sharp.card is strike


def test_clone_carries_the_enchantment_status():
    # MemberwiseClone copies _status; DeepCloneFields only nulls _card.
    strike = make_card("strike")
    sown = enchant("sown", strike)
    sown.disabled = True
    assert create_clone(strike).enchantment.disabled


@pytest.mark.parametrize("eid", sorted(_ENCHANTMENT_CLASSES))
def test_every_enchantment_rides_along_on_a_clone(eid):
    # 17 enchantment ids, each attached to a card it can legally enchant.
    hosts = ["strike", "defend", "discovery", "anger"]
    cls = _ENCHANTMENT_CLASSES[eid]
    for host in hosts:
        card = make_card(host)
        if cls.can_enchant(card):
            enchant(eid, card)
            assert create_clone(card).enchantment.id == eid
            return
    raise AssertionError(f"no host card for {eid}")


def test_clone_carries_a_static_card_modification():
    # MOVED 2026-07-29 (round 7, creature_card_cmds/step52's clone sibling).
    # It used to read "the sim rebuilds the card from its class, so the copy
    # must RE-RUN the enchantment's modification". `create_clone` is a
    # memberwise copy now, so the modification is already in the copy and
    # `DeepCloneFields` uses `EnchantInternal` rather than the normal enchant
    # path -- EnchantmentModel.cs:350-353: "It is NOT called when a card is
    # cloned, because the enchantment's effects will already be reflected in
    # the card's values." Souls is the case that forces it: its CanEnchant
    # demands the Exhaust its own ModifyCard removes. The assertion below is
    # unchanged; only the route to it is.
    discovery = make_card("discovery")
    enchant("souls", discovery)
    assert not create_clone(discovery).exhausts  # C#: Souls came along


def test_clone_carries_the_affliction():
    # CardModel.cs:1210-1215 clones the Affliction the same way.
    strike = make_card("strike")
    from sts2_rl.cmds import CardCmd

    CardCmd.afflict(strike, EntangledAffliction, 2)
    clone = create_clone(strike)
    assert clone.affliction is not None
    assert clone.affliction is not strike.affliction
    assert clone.affliction.id == "entangled"
    assert clone.affliction.amount == 2
    assert clone.affliction.card is clone


def test_clone_keeps_the_upgrade_level():
    strike = make_card("strike")
    strike.upgrade()
    clone = create_clone(strike)
    assert clone.upgrade_level == 1
    assert clone.base_damage == strike.base_damage


# ── the four rebuild copy sites ──────────────────────────────────────────
def test_anger_copy_carries_the_enchantment():
    anger = make_card("anger")
    enchant("sharp", anger, 2)
    combat = build([anger] + [make_card("defend") for _ in range(4)])
    combat.play_card(combat.player.hand.index(anger))
    copy = combat.player.discard_pile[-1]
    assert copy.id == "anger"
    assert copy.enchantment is not None and copy.enchantment.id == "sharp"


def test_music_box_copy_carries_the_enchantment():
    from sts2_rl.relics import make_relic

    strike = make_card("strike")
    enchant("sharp", strike, 2)
    combat = CombatState(
        starting_deck=[strike] + [make_card("defend") for _ in range(9)],
        rng=random.Random(1), encounter=WURM,
        relics=[make_relic("music_box")],
    )
    combat.play_card(combat.player.hand.index(strike))
    copy = combat.player.hand[-1]
    assert copy.id == "strike" and copy.is_ethereal
    assert copy.enchantment is not None and copy.enchantment.id == "sharp"


def test_burning_sticks_copy_carries_the_enchantment():
    from sts2_rl.relics import make_relic

    skill = make_card("discovery")  # a Skill that exhausts itself
    enchant("steady", skill)
    combat = CombatState(
        starting_deck=[skill] + [make_card("defend") for _ in range(9)],
        rng=random.Random(2), encounter=WURM,
        relics=[make_relic("burning_sticks")],
    )
    sticks = combat.relics[0]
    sticks.on_card_exhausted(skill)
    copy = combat.player.hand[-1]
    assert copy.id == "discovery"
    assert copy.enchantment is not None and copy.enchantment.id == "steady"
    assert copy.retain  # Steady's ModifyCard ran on the copy


# ── DowngradeInternal re-runs Enchantment.ModifyCard ─────────────────────
def test_downgrade_reapplies_a_souls_enchantment():
    discovery = make_card("discovery")
    assert discovery.exhausts
    enchant("souls", discovery)
    discovery.upgrade()
    discovery.downgrade()
    assert not discovery.exhausts  # C#: Enchantment?.ModifyCard()


def test_downgrade_reapplies_steady_goopy_and_ember():
    defend = make_card("defend")
    enchant("goopy", defend)
    defend.upgrade()
    defend.downgrade()
    assert defend.exhausts

    strike = make_card("strike")
    enchant("steady", strike)
    strike.upgrade()
    strike.downgrade()
    assert strike.retain

    ember = make_card("strike")
    enchant("tezcataras_ember", ember)
    ember.upgrade()
    ember.downgrade()
    assert ember.energy_cost == 0
    assert ember.eternal


def test_downgrade_does_not_reset_the_enchantment_status():
    # ModifyCard runs OnEnchant; it does not touch Status.
    strike = make_card("strike")
    sown = enchant("sown", strike)
    sown.disabled = True
    strike.upgrade()
    strike.downgrade()
    assert sown.disabled
