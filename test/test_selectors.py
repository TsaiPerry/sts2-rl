"""Tests for sts2_rl/selectors.py — the scripted deterministic card selector.

scripted_card_selector is the training default plugged into
CombatState.card_selector by STS2FullCombatEnv (RL.md wiring option 2). It
must be a pure function of (purpose, candidates, count): no RNG, no state
reads, no mutation — so training sees no hidden stochasticity from
mid-resolution selection effects.

Run with:  py -m pytest test/test_selectors.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, make_card, scripted_card_selector
from sts2_rl.monsters import FUZZY_WURM_ENCOUNTER


# ── Purpose heuristics ────────────────────────────────────────────────────────


def test_upgrade_picks_highest_cost():
    strike, defend, bludgeon = make_card("strike"), make_card("defend"), make_card("bludgeon")
    assert scripted_card_selector("upgrade", [strike, defend, bludgeon], 1) == [bludgeon]


def test_upgrade_treats_x_cost_as_most_expensive():
    bludgeon, whirlwind = make_card("bludgeon"), make_card("whirlwind")
    assert scripted_card_selector("upgrade", [bludgeon, whirlwind], 1) == [whirlwind]


def test_upgrade_prefers_upgradable():
    bludgeon, strike = make_card("bludgeon"), make_card("strike")
    bludgeon.upgrade()                         # at max level → not upgradable
    assert scripted_card_selector("upgrade", [bludgeon, strike], 1) == [strike]


def test_exhaust_picks_status_and_curse_first():
    strike, wound, clumsy = make_card("strike"), make_card("wound"), make_card("clumsy")
    assert scripted_card_selector("exhaust", [strike, wound], 1) == [wound]
    assert scripted_card_selector("exhaust", [strike, wound, clumsy], 2) == [wound, clumsy]
    # No junk in hand → hand order.
    defend = make_card("defend")
    assert scripted_card_selector("exhaust", [strike, defend], 1) == [strike]


def test_to_draw_top_picks_cheapest_attack():
    defend, bludgeon, strike = make_card("defend"), make_card("bludgeon"), make_card("strike")
    assert scripted_card_selector("to_draw_top", [defend, bludgeon, strike], 1) == [strike]
    # No attack among candidates → cheapest card.
    assert scripted_card_selector("to_draw_top", [make_card("impervious"), defend], 1) == [defend]


def test_curse_of_knowledge_picks_least_crippling():
    # The Knowledge Demon's three pairs: Disintegration is offered first each
    # time; the heuristic dodges it except against Waste Away (−1 energy).
    dis = make_card("disintegration")
    assert scripted_card_selector(
        "curse_of_knowledge", [dis, make_card("mind_rot")], 1
    )[0].id == "mind_rot"
    assert scripted_card_selector(
        "curse_of_knowledge", [dis, make_card("sloth")], 1
    )[0].id == "sloth"
    assert scripted_card_selector(
        "curse_of_knowledge", [dis, make_card("waste_away")], 1
    )[0].id == "disintegration"


def test_unknown_purpose_keeps_offered_order():
    cards = [make_card("defend"), make_card("bludgeon"), make_card("strike")]
    assert scripted_card_selector("???", list(cards), 1) == [cards[0]]
    assert scripted_card_selector("???", list(cards), 2) == cards[:2]


def test_selector_is_pure():
    cards = [make_card("strike"), make_card("wound"), make_card("bludgeon")]
    before = list(cards)
    chosen = scripted_card_selector("exhaust", cards, 2)
    assert cards == before                     # candidate list not reordered
    assert all(c in before for c in chosen)
    assert len(set(map(id, chosen))) == len(chosen)


# ── Wiring ────────────────────────────────────────────────────────────────────


def test_combat_select_cards_routes_through_installed_selector():
    c = CombatState(rng=random.Random(0), encounter=FUZZY_WURM_ENCOUNTER)
    c.card_selector = scripted_card_selector
    strike, wound = make_card("strike"), make_card("wound")
    assert c.select_cards("exhaust", [strike, wound], 1) == [wound]


def test_env_installs_scripted_selector_by_default():
    from sts2_rl import STS2FullCombatEnv

    env = STS2FullCombatEnv()
    env.reset(seed=0)
    assert env._state.card_selector is scripted_card_selector
    # card_selector=None opts back into the engine's seeded-random default.
    env_random = STS2FullCombatEnv(card_selector=None)
    env_random.reset(seed=0)
    assert env_random._state.card_selector is None
