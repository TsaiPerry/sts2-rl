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
#
# R2 (round 13, event/the_future_of_potions/g15): the trade now rides
# `pending_rewards` (the mid-event OfferCustom channel brain_leech.py's Rip
# and trial.py's Nondescript Guilty already use) instead of a direct
# `run.select_cards` call, so `apply_reward_modifiers` runs on it and
# Driftwood's reroll (Driftwood.cs:14-25) / Pael's Wing's sacrifice land on
# this screen exactly like any other CardReward. That also means the screen
# is now drained through a real REWARD_CARD decision, which needs a driver
# attached — the old bare-RunState + `run.reward_offer_selector` shape below
# no longer applies to this event (it still applies to the six bare-potion
# events above, untouched by this task).


def test_the_future_of_potions_declined_screen_adds_no_card():
    """CardReward.CanSkip defaults true (CardReward.cs:95) and
    TheFutureOfPotions.cs never overrides it, so the whole screen — not just
    a single card — can be walked away from."""
    from sts2_rl.driver import DecisionKind, RunDriver

    run = parity_run()
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))
    kinds = []

    def decline_cards(request):
        kinds.append(request.kind)
        if request.kind == DecisionKind.REWARD_CARD:
            return len(request.rewards.cards)      # skip index
        return request.legal_actions()[0]

    driver = RunDriver(run, decline_cards)
    deck_before = len(run.deck)
    ev = make_event("the_future_of_potions", run)
    driver._run_event(ev)
    # PotionCmd.Discard runs before the offer (TheFutureOfPotions.cs:126-130)
    # — spent either way, taken or skipped.
    assert len(run.held_potions) == 1
    assert len(run.deck) == deck_before
    assert DecisionKind.REWARD_CARD in kinds


def test_the_future_of_potions_taken_screen_adds_one_upgraded_card():
    from sts2_rl.driver import DecisionKind, RunDriver

    run = parity_run()
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))

    def take_first(request):
        if request.kind == DecisionKind.REWARD_CARD:
            return 0
        return request.legal_actions()[0]

    driver = RunDriver(run, take_first)
    deck_before = len(run.deck)
    ev = make_event("the_future_of_potions", run)
    driver._run_event(ev)
    assert len(run.deck) == deck_before + 1
    assert run.deck[-1].upgrade_level == 1


def test_the_future_of_potions_driftwood_reroll_reaches_the_event():
    """RED before this fix: the screen went straight through
    `run.select_cards`, which never calls `apply_reward_modifiers` and has
    no reroll slot at all — Driftwood held or not, no REWARD_CARD decision
    was ever raised for this event, so `DecisionKind.REWARD_CARD in kinds`
    below was always False and a reroll was structurally impossible, not
    merely declined. GREEN after: the CardReward rides `pending_rewards`
    (like brain_leech's Rip / trial's Nondescript Guilty), so Driftwood's
    `TryModifyRewardsLate` (Driftwood.cs:14-25, no room check) sets
    `can_reroll` on it via `apply_reward_modifiers`, and the driver's
    `_offer_card_group` (driver.py:519-542) surfaces the reroll slot at
    index `len(cards)+1` (`DecisionRequest.own_actions`, driver.py:207-214).
    Also pins the addendum's second requirement: a reroll must REGENERATE
    the cards through the same `AfterGenerated`-upgrading path as the first
    draw (CardReward.cs:156-164's `_cards.Count <= 0` branch, reached by
    both Populate's first call and Reroll's `_cards.Clear()` + Populate —
    CardReward.cs:322-332), not leave the re-rolled card unupgraded."""
    from sts2_rl.driver import DecisionKind, RunDriver

    run = parity_run()
    run.add_relic("driftwood")
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))
    kinds = []
    rerolled = {"done": False}
    offers: list[list[str]] = []

    def scripted(request):
        kinds.append(request.kind)
        if request.kind == DecisionKind.REWARD_CARD:
            offers.append([c.id for c in request.rewards.cards])
            reroll_idx = len(request.rewards.cards) + 1
            if not rerolled["done"] and reroll_idx in request.legal_actions():
                rerolled["done"] = True
                return reroll_idx
            return 0                    # then take the (re-rolled) first card
        return request.legal_actions()[0]

    driver = RunDriver(run, scripted)
    deck_before = len(run.deck)
    ev = make_event("the_future_of_potions", run)
    driver._run_event(ev)

    assert DecisionKind.REWARD_CARD in kinds
    assert rerolled["done"], "Driftwood's reroll slot was never offered"
    assert len(run.deck) == deck_before + 1
    assert run.deck[-1].upgrade_level == 1, (
        "the re-rolled card must still come back upgraded — AfterGenerated "
        "re-fires from inside Populate on every reroll, not just the first "
        "draw"
    )
    # The reroll REGENERATES: `Reroll` clears `_cards` (CardReward.cs:330) and
    # re-enters Populate (:331), whose `_cards.Count <= 0` branch redraws
    # (:156-164). A reroll that merely cleared `CanReroll` without redrawing
    # would satisfy everything above, so pin the redraw itself.
    assert len(offers) == 2, offers
    assert offers[0] != offers[1], (
        f"the reroll did not regenerate the options: {offers}")
    assert run.deck[-1].id in offers[1], (
        "the taken card must come from the SECOND (re-rolled) offer")


def test_the_future_of_potions_not_rerollable_without_driftwood():
    from sts2_rl.driver import DecisionKind, RunDriver

    run = parity_run()
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))
    seen = []

    def scripted(request):
        if request.kind == DecisionKind.REWARD_CARD:
            n = len(request.rewards.cards)
            seen.append((n + 1) in request.legal_actions())
            return 0
        return request.legal_actions()[0]

    driver = RunDriver(run, scripted)
    ev = make_event("the_future_of_potions", run)
    driver._run_event(ev)
    assert seen
    assert not any(seen), "reroll slot offered with no Driftwood held"


# ── the_future_of_potions — the SCREEN'S CardCreationFlags ─────────────────
#
# `TheFutureOfPotions.cs:127` builds its options as
#   `CardCreationOptions.ForNonCombatWithUniformOdds(pool, predicate)
#        .WithFlags(NoRarityModification | NoCardPoolModifications)`
# and `new CardReward(options, 3, Owner)` (`:128`) then ORs `IsCardReward`
# onto them unconditionally (`CardReward.cs:114-115`). `WithFlags` is an OR
# (`CardCreationOptions.cs:212-216`) and the factory method itself already
# ORs `NoUpgradeRoll` (`CardCreationOptions.cs:159-162`), so the flag set the
# creation actually runs against is
#   NoUpgradeRoll | NoRarityModification | NoCardPoolModifications | IsCardReward.
# Three of those four are observable in the sim, and each gets a pin below.


def _potions_offer(*relic_ids: str):
    """Drive the trade on a bare RunState and return (run, event, relics).

    No driver needed: `_trade` leaves the whole screen on
    `event.pending_rewards`, which is the same thing `test_brain_leech_rip_
    costs_5_and_offers_colorless` (test_shared_events.py) inspects."""
    run = parity_run()
    relics = [run.add_relic(rid) for rid in relic_ids]
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))
    ev = make_event("the_future_of_potions", run)
    ev.begin()
    assert ev.choose("POTION_0")
    assert ev.pending_rewards is not None
    return run, ev, relics


def test_the_future_of_potions_offer_is_not_widened_by_dingy_rug():
    """`NoCardPoolModifications` keeps Dingy Rug's Colorless pool off this
    screen (`TheFutureOfPotions.cs:127` + `DingyRug.cs:19-22`, the FIRST
    guard, which returns the options untouched before the `IsCardReward`
    guard at `:23-26` is ever reached).

    RED before the flags passthrough: the sim set no flag but `IsCardReward`
    on this creation, so Dingy Rug fell through its inert first guard, passed
    its second, and appended `COLORLESS_POOL` — the offer became
    `['secret_technique','mangle','hand_of_greed']` where the no-relic offer
    is `['tear_asunder','conflagration','mangle']`. That is both a
    card-identity divergence and an RNG-ORDER one: the widened pool changes
    every `NextItem` on the Rewards stream for the rest of the run, so the
    identity assertion below is paired with an exact-equality assertion
    against the same-seed no-relic offer."""
    from sts2_rl.cards.pool import COLORLESS_POOL

    _, with_rug, _ = _potions_offer("dingy_rug")
    _, no_relic, _ = _potions_offer()

    offered = [c.id for c in with_rug.pending_rewards.cards]
    leaked = [cid for cid in offered if cid in COLORLESS_POOL]
    assert not leaked, (
        f"Colorless cards leaked onto a NoCardPoolModifications screen: "
        f"{leaked} (DingyRug.cs:19-22 must bail on the flag)")
    assert offered == [c.id for c in no_relic.pending_rewards.cards], (
        "Dingy Rug must not change this screen's pool at all — a widened "
        "pool re-orders every later Rewards draw")


def test_the_future_of_potions_offer_is_upgraded_twice_with_silver_crucible():
    """`IsCardReward` IS set here (`CardReward.cs:114-115`, unconditional for
    every `CardReward` including `TheFutureOfPotions.cs:128`'s), so Silver
    Crucible's late card-reward pass fires (`SilverCrucible.cs:104-107`
    declines only when the flag is absent) and spends one of its three
    charges in the companion event (`SilverCrucible.cs:121-129`).

    That `+1` lands INSIDE `CardFactory.CreateForReward`
    (`CardFactory.cs:104`) and `AfterGenerated`'s `+1`
    (`TheFutureOfPotions.cs:129`, body `:132-138`) lands after
    (`CardReward.cs:162`), so every offered card is at `+2`.

    RED before the `IsCardReward` fix: the hand-rolled `create_reward_cards`
    call passed no flags, so this relic bailed at its guard and the cards
    came back at `+1`."""
    run, ev, (crucible,) = _potions_offer("silver_crucible")
    cards = ev.pending_rewards.cards
    assert cards
    assert all(c.upgrade_level == 2 for c in cards), (
        [(c.id, c.upgrade_level) for c in cards])
    assert crucible.times_used == 1


def test_the_future_of_potions_offer_takes_no_upgrade_roll():
    """`ForNonCombatWithUniformOdds` ORs `NoUpgradeRoll` onto the options
    before `TheFutureOfPotions.cs:127` adds its own two
    (`CardCreationOptions.cs:159-162`, `WithFlags` = `Flags |= flag` at
    `:212-216`), and `CardFactory.cs:98-102` guards the ENTIRE
    `RollForUpgrade` call on it — including the `rng.NextFloat()` at
    `CardFactory.cs:290`. So this screen spends 3 Rewards draws (one
    `NextItem` per card), not 6, and its cards reach `AfterGenerated`
    (`TheFutureOfPotions.cs:129`) at +0 — the offer is +1 in every act.

    RED before the flags passthrough (executed, act 2, seed `UPGRADEROLL`):
    `draws=6` and `[('armaments',2),('havoc',2),('shrug_it_off',2)]` — the
    sim rolled the act-scaled upgrade the source suppresses, so a
    later-act trade offered +2 cards and re-ordered every subsequent draw on
    the Rewards stream."""
    run = parity_run("UPGRADEROLL")
    run.act_index = 2                       # act-scaled odds are 2 * 0.25
    run.add_potion(make_potion("attack_potion"))    # Common -> Common cards
    run.add_potion(make_potion("attack_potion"))
    ev = make_event("the_future_of_potions", run)
    ev.begin()
    before = run.rewards_rng.counter
    assert ev.choose("POTION_0")
    cards = ev.pending_rewards.cards
    assert len(cards) == 3
    assert run.rewards_rng.counter - before == 3, (
        "NoUpgradeRoll gives the RollForUpgrade draw back too "
        "(CardFactory.cs:98-102 wraps the whole call)")
    assert all(c.upgrade_level == 1 for c in cards), (
        [(c.id, c.upgrade_level) for c in cards])


def test_the_future_of_potions_offer_enchants_with_silken_tress():
    """Same flag, the other reader: `SilkenTress.cs:53-56` declines without
    `IsCardReward`, and with it enchants every enchantable option with Glam
    and returns true unconditionally (`SilkenTress.cs:72`) — so the one-shot
    is spent in `AfterModifyingCardRewardOptions` (`:75-83`) whether or not
    any card could actually take the enchantment.

    RED before the `IsCardReward` fix: `is_used` stayed False and no card
    was enchanted."""
    from sts2_rl.enchantments import GlamEnchantment

    run, ev, (tress,) = _potions_offer("silken_tress")
    cards = ev.pending_rewards.cards
    assert cards
    assert tress.is_used, "SilkenTress.cs:75-83 burns the one-shot"
    enchantable = [c for c in cards if c.enchantment is not None]
    assert enchantable, [c.id for c in cards]
    assert all(isinstance(c.enchantment, GlamEnchantment) for c in enchantable)


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


# ── R6: run.reward_offer_selector now falls back onto the driver's own,
# already-wired reward_selector for potion offers, so a REAL RunDriver
# (real play, and the conformance _ForceWinDriver) stops permanently
# auto-accepting even with no reward_offer_selector explicitly installed.
# Before this fix, `_accept_offer` never asked ANYTHING for a potion purpose
# unless a test manually set `run.reward_offer_selector` — a driver-driven
# run had no way to decline. Proven RED against the pre-fix code with an
# ad-hoc probe (a driver whose asker always tried to skip REWARD_POTION
# still ended up with the potion, and no REWARD_POTION decision was ever
# raised) before writing the fix in events/base.py::_accept_offer. ─────────


def test_drowning_beacon_declines_through_a_real_driver_with_no_explicit_selector():
    from sts2_rl.driver import DecisionKind, RunDriver

    run = parity_run()
    kinds = []

    def decline_potions(request):
        kinds.append(request.kind)
        legal = request.legal_actions()
        if request.kind == DecisionKind.REWARD_POTION and 1 in legal:
            return 1                      # skip
        return legal[0]

    driver = RunDriver(run, decline_potions)
    ev = make_event("drowning_beacon", run)
    driver._run_event(ev)
    assert DecisionKind.REWARD_POTION in kinds
    assert run.held_potions == []


def test_drowning_beacon_still_defaults_to_take_through_a_real_driver():
    """Regression guard: a driver whose policy always answers the first legal
    action still ends up with the potion — the fix changes WHETHER the
    player is asked, not what a take answer does."""
    from sts2_rl.driver import RunDriver

    run = parity_run()

    def take_everything(request):
        return request.legal_actions()[0]

    driver = RunDriver(run, take_everything)
    ev = make_event("drowning_beacon", run)
    driver._run_event(ev)
    assert [p.id for p in run.held_potions] == ["glowwater"]


def test_explicit_reward_offer_selector_still_overrides_the_driver_seam():
    """The finer-grained, explicitly-installed `reward_offer_selector` (the
    `decline()` helper above) still wins over the coarser `reward_selector`
    fallback even with a real driver attached — the two seams don't fight."""
    from sts2_rl.driver import RunDriver

    run = parity_run()
    seen = decline(run)

    def take_everything(request):
        return request.legal_actions()[0]

    driver = RunDriver(run, take_everything)
    ev = make_event("drowning_beacon", run)
    driver._run_event(ev)
    assert run.held_potions == []
    assert seen == ["potion"]


def test_the_future_of_potions_no_longer_uses_select_cards():
    """R2 (round 13): before this fix, `Event.offer_card_reward`'s downstream
    `run.select_cards("card_reward", ...)` was ALREADY skippable
    (driver.py's SKIPPABLE_PURPOSES / `_card_selector`), which is what made
    this event's decline path work pre-fix even though `_accept_offer` never
    asked anything for `purpose == "card_reward"` — see R6-report.md. That
    was C#'s real screen for taking/skipping, but it had no reroll or
    sacrifice slot, and `run.select_cards` never calls
    `apply_reward_modifiers`. This event's CardReward now rides
    `pending_rewards` -> REWARD_CARD instead (see the reroll pin above), so
    `SELECT_CARDS` should never appear for it any more — pinning the
    migration, not just the still-true "can decline" behavior (already
    covered by `test_the_future_of_potions_declined_screen_adds_no_card`)."""
    from sts2_rl.driver import DecisionKind, RunDriver

    run = parity_run()
    run.add_potion(make_potion("glowwater"))
    run.add_potion(make_potion("glowwater"))
    kinds = []

    def take_first(request):
        kinds.append(request.kind)
        if request.kind == DecisionKind.REWARD_CARD:
            return 0
        return request.legal_actions()[0]

    driver = RunDriver(run, take_first)
    ev = make_event("the_future_of_potions", run)
    driver._run_event(ev)
    assert DecisionKind.SELECT_CARDS not in kinds
    assert DecisionKind.REWARD_CARD in kinds
