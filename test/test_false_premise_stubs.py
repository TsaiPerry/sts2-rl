"""Ports whose stated premise about the sim was false (round 7).

PROMPT.md bug class 12: a port that does nothing usually justifies itself with
a claim about the sim, so CHECK THE CLAIM. Every claim checked here was false —
"the sim doesn't model the persistent deck", "the sim has no map", "no gold
system", "no enchantments in the sim", "whether you rested is injected via the
constructor", and White Star's "a second CardReward has no field to live in".

Queue entries: card/guilty/AfterCombatEnd,
card/lantern_key/ModifyUnknownMapPointRoomTypes,
relic/juzu_bracelet/ModifyUnknownMapPointRoomTypes, relic/dragon_fruit/g1,
relic/fake_venerable_tea_set/g1, relic/venerable_tea_set/g1,
relic/dollys_mirror/g1, relic/gnarled_hammer/g1, relic/kifuda/g1,
relic/white_star/g1 and /g3.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ══════════════════════════════════════════════════════════════════════════
# card/guilty — "the persistent deck, which the sim doesn't model"
# ══════════════════════════════════════════════════════════════════════════

def test_guilty_removes_itself_from_the_deck_after_five_combats():
    """Guilty.cs:45-56 — AfterCombatEnd bumps CombatsSeen while the card is in
    the Deck pile and, at 5, `CardPileCmd.RemoveFromDeck(this)`."""
    run = fresh_run()
    guilty = run.add_card(make_card("guilty"))
    combat = CombatState(rng=random.Random(0))
    for i in range(4):
        run.finish_combat(combat, RoomType.MONSTER)
        assert guilty in run.deck, f"gone after {i + 1} combats"
        assert guilty.combats_seen == i + 1
    run.finish_combat(combat, RoomType.MONSTER)
    assert guilty not in run.deck


def test_guilty_counts_only_while_it_is_in_the_deck():
    """`pile != null && pile.Type == PileType.Deck` — the run's deck is the
    only pile the sim's run-level pass walks, so a removed Guilty stops."""
    run = fresh_run()
    guilty = run.add_card(make_card("guilty"))
    run.finish_combat(CombatState(rng=random.Random(0)), RoomType.MONSTER)
    run.remove_cards([guilty])
    run.finish_combat(CombatState(rng=random.Random(0)), RoomType.MONSTER)
    assert guilty.combats_seen == 1


# ══════════════════════════════════════════════════════════════════════════
# The two ModifyUnknownMapPointRoomTypes stubs — "the sim has no map"
# ══════════════════════════════════════════════════════════════════════════

def test_juzu_bracelet_removes_monster_from_the_unknown_pool():
    """JuzuBracelet.cs:17-27 copies the set and removes RoomType.Monster."""
    run = fresh_run()
    before = run._unknown_allowed_room_types([])
    assert RoomType.MONSTER in before
    run.add_relic("juzu_bracelet")
    after = run._unknown_allowed_room_types([])
    assert RoomType.MONSTER not in after
    assert after == before - {RoomType.MONSTER}


def test_lantern_key_forces_events_in_act_three_only():
    """LanternKey.cs:21-28 — `if (2 != CurrentActIndex) return roomTypes;`
    then `new HashSet<RoomType> { RoomType.Event }`. Act index 2 is Glory."""
    run = fresh_run()
    run.add_card(make_card("lantern_key"))
    plain = fresh_run()._unknown_allowed_room_types([])
    run.act_index = 0
    assert run._unknown_allowed_room_types([]) == plain
    run.act_index = 2
    assert run._unknown_allowed_room_types([]) == {RoomType.EVENT}


# ══════════════════════════════════════════════════════════════════════════
# relic/dragon_fruit — "no gold system"
# ══════════════════════════════════════════════════════════════════════════

def test_dragon_fruit_grants_max_hp_on_every_gold_gain():
    """DragonFruit.cs:22-29 — AfterGoldGained, MaxHpVar(1)."""
    run = fresh_run()
    run.add_relic("dragon_fruit")
    before = run.max_hp
    run.gain_gold(25)
    assert run.max_hp == before + 1
    run.gain_gold(10)
    assert run.max_hp == before + 2


def test_dragon_fruit_sees_the_new_balance():
    """`AfterGoldGained` fires AFTER `player.Gold += amount`
    (PlayerCmd.cs:168-169)."""
    run = fresh_run()
    seen = []
    relic = run.add_relic("dragon_fruit")
    original = type(relic).after_gold_gained

    def spy(self, r, amount):
        seen.append((r.gold, amount))
        original(self, r, amount)

    type(relic).after_gold_gained = spy
    try:
        start = run.gold
        run.gain_gold(25)
    finally:
        type(relic).after_gold_gained = original
    assert seen == [(start + 25, 25)]


def test_dragon_fruit_is_behind_the_positive_amount_bail():
    """PlayerCmd.cs:146-149 bails on `!(amount > 0)` BEFORE the hook, so a
    gain Ectoplasm zeroed pays no Max HP — an anti-synergy, not a combo."""
    run = fresh_run()
    run.add_relic("ectoplasm")
    run.add_relic("dragon_fruit")
    before = (run.gold, run.max_hp)
    run.gain_gold(25)
    assert (run.gold, run.max_hp) == before


# ══════════════════════════════════════════════════════════════════════════
# The two tea sets — frozen constructor state
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("relic_id,energy", [
    ("venerable_tea_set", 5),
    ("fake_venerable_tea_set", 4),
])
def test_tea_set_latches_on_a_rest_site(relic_id, energy):
    """FakeVenerableTeaSet.cs:43-51 latches from AfterRoomEntered when
    `room is RestSiteRoom`; the real one is the same shape at 2 energy."""
    run = fresh_run()
    relic = run.add_relic(relic_id)
    assert relic._pending is False
    relic.after_room_entered(run, None, RoomType.REST_SITE)
    assert relic._pending is True
    cs = CombatState(rng=random.Random(0), relics=[relic])
    assert cs.player.energy == energy
    assert relic._pending is False


@pytest.mark.parametrize("relic_id", ["venerable_tea_set",
                                      "fake_venerable_tea_set"])
def test_tea_set_ignores_other_rooms(relic_id):
    run = fresh_run()
    relic = run.add_relic(relic_id)
    for room in (RoomType.MONSTER, RoomType.SHOP, RoomType.TREASURE,
                 RoomType.EVENT, RoomType.ELITE):
        relic.after_room_entered(run, None, room)
    assert relic._pending is False


# ══════════════════════════════════════════════════════════════════════════
# The three AfterObtained deck effects
# ══════════════════════════════════════════════════════════════════════════

def _take_first(count):
    return lambda purpose, candidates, n: candidates[:min(n, count)]


def test_dollys_mirror_duplicates_a_deck_card():
    """DollysMirror.cs:16-24 — one non-Quest pick, `RunState.CloneCard`, add
    to PileType.Deck."""
    run = fresh_run()
    run.card_selector = _take_first(1)
    before = len(run.deck)
    source = run.deck[0]
    run.add_relic("dollys_mirror")
    assert len(run.deck) == before + 1
    assert run.deck[-1].id == source.id
    assert run.deck[-1] is not source


def test_dollys_mirror_clones_rather_than_rebuilds():
    """The implementation warning on the entry: the C# call is
    `RunState.CloneCard` -> `ClonePreservingMutability`, so the copy carries
    the source's enchantment. Deck cards do carry them out of combat."""
    from sts2_rl.enchantments import make_enchantment
    run = fresh_run()
    make_enchantment("sharp").attach(run.deck[0])
    run.card_selector = _take_first(1)
    run.add_relic("dollys_mirror")
    assert run.deck[-1].enchantment is not None
    assert run.deck[-1].enchantment.id == "sharp"


def test_dollys_mirror_offers_every_non_quest_card():
    """`Filter(c) => c.Type != CardType.Quest` (DollysMirror.cs:26-29) — NOT
    `removable_cards`, which would refuse an Eternal card the game allows."""
    from sts2_rl.cards import CardType
    run = fresh_run()
    run.deck[0].eternal = True
    run.add_card(make_card("lantern_key"))
    offered = []
    run.card_selector = lambda purpose, candidates, n: (
        offered.extend(candidates) or candidates[:1])
    run.add_relic("dollys_mirror")
    assert run.deck[0] in offered
    assert not any(c.card_type == CardType.QUEST for c in offered)


@pytest.mark.parametrize("relic_id,enchant_id,amount", [
    ("gnarled_hammer", "sharp", 3),
    ("kifuda", "adroit", 3),
])
def test_pickup_enchants_three_deck_cards(relic_id, enchant_id, amount):
    """GnarledHammer.cs:28-40 and Kifuda.cs:24-37 — CardsVar 3, a
    non-cancelable 0..3 enchant screen, then Enchant at 3."""
    run = fresh_run()
    run.card_selector = _take_first(3)
    run.add_relic(relic_id)
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 3
    assert all(c.enchantment.id == enchant_id for c in enchanted)
    assert all(c.enchantment.amount == amount for c in enchanted)


def test_adroit_grants_block_when_its_card_is_played():
    """Adroit.cs — OnPlay: `CreatureCmd.GainBlock(DynamicVars.Block)`, and
    RecalculateValues sets `Block.BaseValue = Amount`."""
    from sts2_rl.enchantments import make_enchantment
    card = make_card("strike")
    enchantment = make_enchantment("adroit")
    enchantment.amount = 3
    enchantment.attach(card)
    cs = CombatState(starting_deck=[card] + [make_card("defend") for _ in range(4)],
                     rng=random.Random(0))
    before = cs.player.block
    assert cs.play_card(cs.player.hand.index(card), target_idx=0)
    assert cs.player.block == before + 3


# ══════════════════════════════════════════════════════════════════════════
# relic/white_star — the second card group
# ══════════════════════════════════════════════════════════════════════════

def test_white_star_adds_a_boss_odds_card_group_to_an_elite():
    """WhiteStar.cs:19-28 — `new CardReward(CardCreationOptions.ForRoom(owner,
    RoomType.Boss), 3)` on an Elite screen. `ForRoom(Boss)` selects
    CardRarityOddsType.BossEncounter (CardCreationOptions.cs:122-129), which
    rewards.py maps to (1.0, 0.0, 0.0) — three RARE cards."""
    from sts2_rl.cards.base import CardRarity
    run = fresh_run()
    run.add_relic("white_star")
    rewards = run.generate_combat_rewards(RoomType.ELITE)
    assert len(rewards.card_rewards) == 2
    extra = rewards.card_rewards[1]
    assert extra.room_type == RoomType.BOSS
    assert len(extra.cards) == 3
    assert all(c.rarity == CardRarity.RARE for c in extra.cards)


def test_white_star_leaves_a_monster_room_alone():
    run = fresh_run()
    run.add_relic("white_star")
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    assert len(rewards.card_rewards) == 1
