"""RunDriver (sts2_rl/driver.py): the injectable-ask run loop, selector
adapters, and DecisionRequest legality."""
import random

import pytest

from sts2_rl.driver import (
    DecisionKind,
    DecisionRequest,
    RunDriver,
    play_random_run,
    random_asker,
)
from sts2_rl.events import make_event
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


def failing_asker(request):
    raise AssertionError(f"asker should not have been called: {request!r}")


# ═════════════════════════════════════════════════════════════════════════
# Whole-run smoke + determinism
# ═════════════════════════════════════════════════════════════════════════

def test_random_runs_complete():
    # A masked-random policy always reaches a terminal state (win or death)
    # without illegal actions (the driver raises on any).
    for seed in range(10):
        result = play_random_run(seed)
        assert result.victory or result.hp == 0
        assert result.floor >= 1
        assert result.decisions > 0


def test_random_run_deterministic_under_seed():
    a = play_random_run(42)
    b = play_random_run(42)
    assert a == b
    assert a != play_random_run(43)


def test_invincible_random_run_reaches_victory():
    # With effectively infinite HP, random play can clear all three ported
    # acts: exercises Neow, travel, events, shops, rests, rewards, advance_act
    # and the final-boss victory path end-to-end. HP alone doesn't guarantee a
    # win — several bosses kill outright regardless of HP (The Insatiable's
    # Sandpit via SandpitPower.AfterRemoved, etc.), so a run can end legally in
    # ANY act, not just the last. Sweep seeds for a victorious run; every run
    # must still terminate cleanly, and a victory can only happen in the final
    # act (Glory, act index 2).
    for seed in range(20):
        rng = random.Random(seed)
        run = RunState(rng=rng, max_hp=100000, hp=100000)
        result = RunDriver(run, random_asker(rng)).play()
        assert run.at_run_end                 # ended legally: dead or won
        assert 0 <= result.act_index <= 2     # somewhere in the 3-act arc
        if result.victory:
            assert result.act_index == 2      # a win means clearing Glory
            return
    pytest.fail("no invincible random run won in 20 seeds")


def test_driver_rejects_illegal_actions():
    rng = random.Random(0)
    run = fresh_run(0)

    def bad_asker(request):
        return max(request.legal_actions()) + 1

    driver = RunDriver(run, bad_asker)
    with pytest.raises(ValueError):
        driver.play()


# ═════════════════════════════════════════════════════════════════════════
# Selector adapters
# ═════════════════════════════════════════════════════════════════════════

def test_forced_choice_never_asks():
    run = fresh_run(1)
    RunDriver(run, failing_asker)
    # count >= len(candidates) on a mandatory purpose: no decision needed.
    card = run.upgradable_cards()[0]
    assert run.select_cards("upgrade", [card], 1) == [card]
    assert run.select_cards("upgrade", [card], 3) == [card]


def test_multi_pick_select_shrinks_candidates():
    run = fresh_run(2)
    seen = []

    def scripted(request):
        assert request.kind == DecisionKind.SELECT_CARDS
        seen.append((len(request.candidates), request.count_remaining))
        return 0

    RunDriver(run, scripted)
    candidates = run.deck[:4]
    picked = run.select_cards("remove", candidates, 2)
    assert len(picked) == 2 and picked[0] is not picked[1]
    assert seen == [(4, 2), (3, 1)]


def test_skippable_purpose_allows_declining():
    run = fresh_run(3)

    def skip_all(request):
        assert request.skippable
        return len(request.candidates)     # the skip index

    RunDriver(run, skip_all)
    assert run.select_cards("card_reward", run.deck[:3], 1) == []
    # Even a forced-looking offer (1 candidate) still asks when skippable.
    assert run.select_cards("obtain", run.deck[:1], 1) == []


def test_select_option_routes_through_ask():
    run = fresh_run(4)

    def pick_one(request):
        assert request.kind == DecisionKind.SELECT_OPTION
        assert request.purpose == "bundle"
        assert request.n_options == 2
        return 1

    RunDriver(run, pick_one)
    assert run.select_option("bundle", 2) == 1


# ═════════════════════════════════════════════════════════════════════════
# Room resolution paths
# ═════════════════════════════════════════════════════════════════════════

def test_event_combat_path():
    # Dense Vegetation: REST → FIGHT sets pending_encounter; the driver then
    # runs the fight with masked-random combat actions.
    rng = random.Random(5)
    run = RunState(rng=rng, max_hp=100000, hp=100000)
    combat_requests = []

    def scripted(request):
        if request.kind == DecisionKind.EVENT:
            keys = request.event.option_keys()
            for wanted in ("FIGHT", "REST"):
                if wanted in keys:
                    return keys.index(wanted)
            return request.legal_actions()[0]
        if request.kind == DecisionKind.COMBAT:
            combat_requests.append(request)
        return rng.choice(request.legal_actions())

    driver = RunDriver(run, scripted)
    driver._run_event(make_event("dense_vegetation", run))
    assert combat_requests, "the event fight never asked for combat actions"
    # Event fights carry no room type → no reward screen was generated.
    assert all(req.combat.room_type is None for req in combat_requests)


def test_shop_purchase_and_leave():
    from sts2_rl.shop import MerchantInventory

    run = fresh_run(6, gold=10_000)
    shop = MerchantInventory.create(run)
    bought = []

    def scripted(request):
        assert request.kind == DecisionKind.SHOP
        entries = request.shop.all_entries
        legal = request.legal_actions()
        buyable = [i for i in legal if i < len(entries)]
        if buyable and not bought:
            bought.append(buyable[0])
            return buyable[0]
        return len(entries)                # leave

    driver = RunDriver(run, scripted)
    gold_before = run.gold
    driver._run_shop(shop)
    assert bought and run.gold < gold_before


def test_rest_choices():
    run = fresh_run(7)
    run.hp = 40
    driver = RunDriver(run, lambda req: 0)     # heal
    driver._run_rest()
    assert run.hp == 64

    driver = RunDriver(run, lambda req: 1 if req.kind == DecisionKind.REST else 0)
    driver._run_rest()                          # smith (selector forced/asked)
    assert any(c.upgrade_level > 0 for c in run.deck)

    hp = run.hp
    driver = RunDriver(run, lambda req: 2)     # leave
    driver._run_rest()
    assert run.hp == hp


def test_dream_catcher_rest_heal_offers_card_reward():
    """DreamCatcher.cs TryModifyRestSiteHealRewards, wired through the rest
    decision flow: choosing HEAL at a rest site with Dream Catcher surfaces a
    skippable REWARD_CARD choice (same screen the driver uses for post-combat
    rewards), and taking a card adds it to the deck."""
    run = fresh_run(17)
    run.add_relic("dream_catcher")
    run.hp = 40
    kinds = []

    def scripted(request):
        kinds.append(request.kind)
        if request.kind == DecisionKind.REWARD_CARD:
            return 0                       # take the first card
        return 0 if request.kind == DecisionKind.REST else request.legal_actions()[0]

    driver = RunDriver(run, scripted)
    deck_before = len(run.deck)
    driver._run_rest()
    assert DecisionKind.REWARD_CARD in kinds
    assert len(run.deck) == deck_before + 1


def test_no_dream_catcher_no_reward_card_after_rest_heal():
    run = fresh_run(17)
    run.hp = 40
    kinds = []

    def scripted(request):
        kinds.append(request.kind)
        return 0 if request.kind == DecisionKind.REST else request.legal_actions()[0]

    driver = RunDriver(run, scripted)
    driver._run_rest()
    assert DecisionKind.REWARD_CARD not in kinds


def test_combat_rewards_offered_after_won_fight():
    from sts2_rl.monsters.overgrowth import ENCOUNTERS

    rng = random.Random(8)
    run = RunState(rng=rng, max_hp=100000, hp=100000)
    kinds = []

    def scripted(request):
        kinds.append(request.kind)
        if request.kind == DecisionKind.REWARD_CARD:
            return 0                       # take the first card
        if request.kind == DecisionKind.REWARD_POTION:
            return 0                       # take the potion
        return rng.choice(request.legal_actions())

    driver = RunDriver(run, scripted)
    deck_before = len(run.deck)
    gold_before = run.gold
    won = driver._run_combat(ENCOUNTERS["fuzzy_wurm_weak"], RoomType.MONSTER)
    assert won
    assert DecisionKind.REWARD_CARD in kinds
    assert len(run.deck) == deck_before + 1
    assert run.gold >= gold_before + 10    # monster gold 10–20


# ═════════════════════════════════════════════════════════════════════════
# DecisionRequest legality
# ═════════════════════════════════════════════════════════════════════════

def test_reward_potion_take_needs_free_slot():
    from sts2_rl.rewards import CombatRewards

    run = fresh_run(9)
    rewards = CombatRewards(room_type=RoomType.MONSTER, potion=run.random_potion())
    req = DecisionRequest(
        kind=DecisionKind.REWARD_POTION, run=run, rewards=rewards,
    )
    assert req.legal_actions() == [0, 1]
    run.potions = run.random_potions(run.max_potions)
    assert req.legal_actions() == [1]      # belt full: skip only


def test_event_request_masks_locked_options():
    from sts2_rl.events.base import Event, EventOption

    run = fresh_run(10)

    class TwoOptions(Event):
        id = "_test_two_options"
        name = "Test"

        def initial_options(self):
            return [
                EventOption("LOCKED", None),
                EventOption("OPEN", lambda: self._finish("DONE")),
            ]

    event = TwoOptions(run).begin()
    req = DecisionRequest(kind=DecisionKind.EVENT, run=run, event=event)
    assert req.legal_actions() == [1]


def test_combat_request_uses_shared_mask():
    from sts2_rl.full_env import combat_action_masks
    from sts2_rl.monsters.overgrowth import ENCOUNTERS

    run = fresh_run(11)
    combat = run.create_combat(ENCOUNTERS["fuzzy_wurm_weak"])
    req = DecisionRequest(kind=DecisionKind.COMBAT, run=run, combat=combat)
    expected = [int(i) for i in combat_action_masks(combat, run.max_potions).nonzero()[0]]
    assert req.legal_actions() == expected
    assert 0 in expected                   # end turn always legal
