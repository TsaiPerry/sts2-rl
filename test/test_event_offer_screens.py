"""
Event reward payouts wrapped in `RewardsCmd.OfferCustom` are TAKE-OR-SKIP
screens, not unconditional grants (audit gap `event/EV-4`).

`DrowningBeacon.cs:39-46` is the worked example: BottleOption builds a
`PotionReward` and hands it to `RewardsCmd.OfferCustom`, which is a screen the
player can walk away from — a belt slot they did not have to spend. The source
distinguishes the two kinds of screen deliberately: `BrainLeech.cs:67-70` sets
`Cancelable = false` on its grid pick while its RIP branch at
`BrainLeech.cs:58` uses plain (cancelable) `OfferCustom`.

Seven ported events took the payout unconditionally: drowning_beacon,
endless_conveyor, potion_courier, the_future_of_potions, the_legends_were_true,
wellspring and whispering_hollow.

Run with:  py -m pytest test/test_event_offer_screens.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import RunState, make_event
from sts2_rl.potions import make_potion


def decline(run: RunState) -> list[str]:
    """Install a reward-offer selector that skips every screen, and return the
    list it records the offered screens into."""
    seen: list[str] = []

    def selector(purpose, payload):
        seen.append(purpose)
        return False

    run.reward_offer_selector = selector
    return seen


def parity_run(seed: str = "OFFERSCREEN", **kwargs) -> RunState:
    return RunState(rng=random.Random(0), string_seed=seed, **kwargs)


# ── drowning_beacon (the worked example) ─────────────────────────────────────


def test_drowning_beacon_bottle_is_taken_by_default():
    run = parity_run()
    make_event("drowning_beacon", run).begin().choose("BOTTLE")
    assert [p.id for p in run.held_potions] == ["glowwater"]


def test_drowning_beacon_bottle_can_be_declined():
    run = parity_run()
    seen = decline(run)
    make_event("drowning_beacon", run).begin().choose("BOTTLE")
    assert run.held_potions == []
    assert seen == ["potion"]


# ── wellspring / the_legends_were_true — the potion is ROLLED either way ─────


def test_wellspring_declined_offer_still_burns_its_rewards_draw():
    """`PlayerRng.Rewards.NextItem(items)` runs BEFORE OfferCustom
    (Wellspring.cs:32-38), so declining does not give the draw back."""
    run = parity_run()
    decline(run)
    before = run.rewards_rng.counter
    make_event("wellspring", run).begin().choose("BOTTLE")
    assert run.held_potions == []
    assert run.rewards_rng.counter == before + 1


def test_the_legends_were_true_declined_offer_still_costs_the_hp():
    """CreatureCmd.Damage lands before the offer (TheLegendsWereTrue.cs:51-59)."""
    run = parity_run()
    decline(run)
    hp_before = run.hp
    make_event("the_legends_were_true", run).begin().choose("SLOWLY_FIND_AN_EXIT")
    assert run.hp == hp_before - 8
    assert run.held_potions == []


# ── potion_courier — ONE screen, three independent PotionRewards ─────────────


def test_potion_courier_grab_potions_offers_three_separate_rewards():
    run = parity_run()
    seen = decline(run)
    make_event("potion_courier", run).begin().choose("GRAB_POTIONS")
    assert run.held_potions == []
    assert seen == ["potion", "potion", "potion"]


def test_potion_courier_ransack_can_be_declined():
    run = parity_run()
    decline(run)
    make_event("potion_courier", run).begin().choose("RANSACK")
    assert run.held_potions == []


# ── whispering_hollow — the gold is spent before the screen opens ───────────


def test_whispering_hollow_declined_offer_still_costs_the_gold():
    run = parity_run(gold=200)
    seen = decline(run)
    ev = make_event("whispering_hollow", run).begin()
    cost = ev.gold_cost
    ev.choose("GOLD")
    assert run.gold == 200 - cost
    assert run.held_potions == []
    assert seen == ["potion", "potion"]


# ── endless_conveyor — the Suspicious Condiment dish ────────────────────────


def test_endless_conveyor_condiment_offer_can_be_declined():
    run = parity_run(gold=400)
    decline(run)
    ev = make_event("endless_conveyor", run).begin()
    ev._suspicious_condiment()
    assert run.held_potions == []


# ── the_future_of_potions — a CardReward screen, skippable as a whole ───────


def test_the_future_of_potions_declined_screen_adds_no_card():
    run = parity_run()
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))
    seen = decline(run)
    deck_before = len(run.deck)
    ev = make_event("the_future_of_potions", run).begin()
    ev.choose("POTION_0")
    # PotionCmd.Discard runs before the offer (TheFutureOfPotions.cs:126-130).
    assert len(run.held_potions) == 1
    assert len(run.deck) == deck_before
    assert seen == ["card_reward"]


def test_the_future_of_potions_taken_screen_adds_one_upgraded_card():
    run = parity_run()
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))
    deck_before = len(run.deck)
    ev = make_event("the_future_of_potions", run).begin()
    ev.choose("POTION_0")
    assert len(run.deck) == deck_before + 1
    assert run.deck[-1].upgrade_level == 1


# ── the default (no selector installed) keeps every payout ──────────────────


@pytest.mark.parametrize("event_id,path", [
    ("drowning_beacon", ["BOTTLE"]),
    ("wellspring", ["BOTTLE"]),
    ("potion_courier", ["RANSACK"]),
])
def test_offers_are_taken_when_no_selector_is_installed(event_id, path):
    run = parity_run()
    ev = make_event(event_id, run).begin()
    for step in path:
        ev.choose(step)
    assert len(run.held_potions) == 1
