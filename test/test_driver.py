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
    # Event fights are real Monster combat rooms (see
    # test_event_fight_gives_normal_monster_rewards for the reward screen).
    assert all(req.combat.room_type is RoomType.MONSTER for req in combat_requests)


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


def test_special_card_rewards_offered_as_take_or_skip():
    """A combat's pending extras (Thieving Hopper's returned card) surface as
    their own one-card REWARD_CARD offers: take adds to the deck, skip loses
    the card. Source: CombatRoom.ExtraRewards folded in by
    RewardsSet.WithRewardsFromRoom; SpecialCardReward.OnSelect."""
    from sts2_rl.cards import make_card
    from sts2_rl.rewards import CombatRewards

    for take, delta in ((True, 1), (False, 0)):
        run = fresh_run(11)
        special = make_card("strike")
        rewards = CombatRewards(
            room_type=RoomType.MONSTER, special_cards=[special],
        )
        offers = []

        def scripted(request):
            assert request.kind == DecisionKind.REWARD_CARD
            offers.append(list(request.rewards.cards))
            assert request.legal_actions() == [0, 1]  # take / skip
            return 0 if take else 1

        deck_before = len(run.deck)
        RunDriver(run, scripted)._offer_rewards(rewards)
        assert offers == [[special]]
        assert len(run.deck) == deck_before + delta
        assert (special in run.deck) is take


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


# ═════════════════════════════════════════════════════════════════════════
# Combat-event rewards (PunchOff.cs / TheLanternKey.cs / BattlewornDummy.cs)
# ═════════════════════════════════════════════════════════════════════════

def _event_fight_asker(event_path, log):
    """Walk event options by preferred key, play the first legal non-end-turn
    combat action, take/first-pick every other decision."""
    def ask(request):
        log.append(request)
        if request.kind == DecisionKind.EVENT:
            keys = request.event.option_keys()
            for wanted in event_path:
                if wanted in keys:
                    return keys.index(wanted)
            return request.legal_actions()[0]
        if request.kind == DecisionKind.COMBAT:
            legal = request.legal_actions()
            non_end = [a for a in legal if a != 0]
            return non_end[0] if non_end else 0
        return 0
    return ask


def test_event_fight_gives_normal_monster_rewards():
    # In the game every event fight is a real CombatRoom whose encounter has
    # RoomType.Monster (DenseVegetationEventEncounter.cs), so victory shows
    # the normal Monster reward screen (RewardsSet.cs GenerateRewardsFor).
    run = fresh_run(5, max_hp=100000, hp=100000)
    log = []
    driver = RunDriver(run, _event_fight_asker(("FIGHT", "REST"), log))
    gold_before = run.gold
    driver._run_event(make_event("dense_vegetation", run))
    combat_reqs = [r for r in log if r.kind == DecisionKind.COMBAT]
    assert combat_reqs, "the event fight never asked for combat actions"
    assert all(r.combat.room_type is RoomType.MONSTER for r in combat_reqs)
    assert any(r.kind == DecisionKind.REWARD_CARD for r in log)
    assert run.gold - gold_before >= 10  # Monster gold 10-20


def test_punch_off_fight_grants_relic_and_potion_extras():
    # PunchOff.cs Fight(): extras = RelicReward + PotionReward on top of the
    # normal Monster rewards (EnterCombatWithoutExitingEvent).
    run = fresh_run(7, max_hp=100000, hp=100000)
    log = []
    driver = RunDriver(run, _event_fight_asker(("I_CAN_TAKE_THEM", "FIGHT"), log))
    relics_before = len(run.relics)
    driver._run_event(make_event("punch_off", run))
    assert len(run.relics) == relics_before + 1  # RelicReward (grab bag)
    assert any(r.kind == DecisionKind.REWARD_POTION for r in log)
    assert any(r.kind == DecisionKind.REWARD_CARD for r in log)


def test_lantern_key_fight_offers_the_key_card():
    # TheLanternKey.cs Fight(): SpecialCardReward(LanternKey) — a one-card
    # take-or-skip offer; taking adds the card to the deck.
    run = fresh_run(3, max_hp=100000, hp=100000)
    log = []
    driver = RunDriver(run, _event_fight_asker(("KEEP_THE_KEY", "FIGHT"), log))
    driver._run_event(make_event("the_lantern_key", run))
    offers = [
        r for r in log
        if r.kind == DecisionKind.REWARD_CARD
        and r.rewards is not None and len(r.rewards.cards) == 1
        and r.rewards.cards[0].id == "lantern_key"
    ]
    assert offers, "the Lantern Key card was never offered"
    assert any(c.id == "lantern_key" for c in run.deck)


def test_battleworn_dummy_fight_rewards(monkeypatch):
    # BattlewornDummyEventEncounter.cs: ShouldGiveRewards=false — no normal
    # reward screen; BattlewornDummy.cs Resume grants the setting's reward
    # (Setting1: a take-or-skip potion offer) only on a timely kill.
    from sts2_rl.monsters.glory.battle_friend import BattleFriendV1
    monkeypatch.setattr(BattleFriendV1, "min_hp", 1)
    monkeypatch.setattr(BattleFriendV1, "max_hp", 1)
    run = fresh_run(2, max_hp=100000, hp=100000)
    log = []
    driver = RunDriver(run, _event_fight_asker(("SETTING_1",), log))
    gold_before = run.gold
    driver._run_event(make_event("battleworn_dummy", run))
    assert any(r.kind == DecisionKind.REWARD_POTION for r in log)
    assert len(run.potions) == 1  # asker takes the offer
    assert not any(r.kind == DecisionKind.REWARD_CARD for r in log)
    assert run.gold == gold_before  # no normal rewards for the dummy fight


def test_battleworn_dummy_resume_outcomes():
    # BattlewornDummy.cs Resume: Setting2 upgrades 2 random deck cards,
    # Setting3 obtains a grab-bag relic; a fled dummy (RanOutOfTime) grants
    # nothing.
    from sts2_rl.cmds import CreatureCmd, DamageCmd
    from sts2_rl.events import make_event

    # Setting 2 — two random upgrades
    run = fresh_run(11)
    event = make_event("battleworn_dummy", run).begin()
    event.choose("SETTING_2")
    combat = run.create_combat(event.pending_encounter, room_type=RoomType.MONSTER)
    DamageCmd.deal(combat.hooks, combat.enemies[0], 10000)
    offers = event.resume_after_combat(combat)
    assert offers == []
    assert sum(1 for c in run.deck if c.upgrade_level > 0) == 2

    # Setting 3 — grab-bag relic
    run = fresh_run(12)
    event = make_event("battleworn_dummy", run).begin()
    event.choose("SETTING_3")
    combat = run.create_combat(event.pending_encounter, room_type=RoomType.MONSTER)
    DamageCmd.deal(combat.hooks, combat.enemies[0], 10000)
    relics_before = len(run.relics)
    event.resume_after_combat(combat)
    assert len(run.relics) == relics_before + 1

    # Fled dummy — nothing
    run = fresh_run(13)
    event = make_event("battleworn_dummy", run).begin()
    event.choose("SETTING_2")
    combat = run.create_combat(event.pending_encounter, room_type=RoomType.MONSTER)
    CreatureCmd.escape(combat.hooks, combat.enemies[0])
    offers = event.resume_after_combat(combat)
    assert offers == []
    assert all(c.upgrade_level == 0 for c in run.deck)
