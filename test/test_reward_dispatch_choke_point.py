"""R10 -- consolidate the reward-modifier dispatch onto one idempotent choke
point mirroring `RewardsSet.GenerateWithoutOffering` (RewardsSet.cs:125-147).

C# funnels every reward screen -- combat, treasure, rest-site heal, and any
`RewardsCmd.OfferCustom` caller (relic pickups, events) -- through exactly
one call to `Hook.ModifyRewards` (Hook.cs:1981-1999), because
`GenerateWithoutOffering` is guarded idempotent by `_isGenerated`
(RewardsSet.cs:41, 127-130, set at :146) and `Offer()` (RewardsSet.cs:153-196)
calls it again at :159 no matter how the set was built. Whichever of the two
call paths runs first does the real work; the other is a harmless repeat.

The sim instead called `apply_reward_modifiers(run, rewards)`
(sts2_rl/rewards.py) by hand at each of 6 construction sites
(rewards.py:698,761; run.py:1419; relics/glass_eye.py:78;
events/brain_leech.py:89; events/trial.py:118). Round 12 (Task 32) found and
fixed two sites that had forgotten the call and recorded the structural
trap: "the next event ported this way can reintroduce the same bug"
(GAP-QUEUE.md, event/3C section; audit/records/event/brain_leech.json and
trial.json's G-new entries).

This file pins the fix: `CombatRewards.generated` (mirroring `_isGenerated`)
makes `apply_reward_modifiers` a no-op on a set it has already processed, and
`driver._offer_rewards` / `RunState.offer_rewards` now call it too --
mirroring `Offer()`'s repeat call -- so a FUTURE construction site that
forgets the explicit call still gets dispatched exactly once, automatically,
at offer time.

Sections:
  A. `apply_reward_modifiers` idempotency (the core fix) -- RED before the
     `generated` flag exists: calling it twice on the same set doubles every
     effect.
  B. The offer-time backstop closes the round-12 trap for a screen nobody
     explicitly generated.
  C. Regression proof: each of the 6 real construction sites still dispatches
     exactly once end-to-end through the real driver pipeline once the
     backstop is wired (not RED-first -- before the backstop exists there is
     nothing to double-fire; these guard against the wiring introducing a
     NEW double-dispatch, and stay green throughout).
  D. The treasure-room hole (run.py's TREASURE branch): C#'s
     `TreasureRoom.DoExtraRewardsIfNeeded` (TreasureRoom.cs:75-97) dispatches
     `Hook.ModifyRewards` over an empty, Room=Treasure `RewardsSet` that the
     chest's own direct gold+relic grant never touches
     (`OneOffSynchronizer.DoTreasureRoomRewards`, no RewardsSet at all). The
     sim had no dispatch call for a treasure room whatsoever. Dormant with
     today's relic roster (enumerated in D1) but wired now so a future
     Room-sensitive (or room-ungated) relic has a screen to land on.

Run with:  py -m pytest test/test_reward_dispatch_choke_point.py -v
"""
from __future__ import annotations

import random

from sts2_rl import make_event
from sts2_rl.driver import RunDriver
from sts2_rl.relics.base import Relic
from sts2_rl.rewards import CombatRewards, apply_reward_modifiers
from sts2_rl.rooms import MapPointType, RoomType
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


def _skip_asker(request):
    """Always answers the last legal action -- skip on a REWARD_* screen,
    with no potion belt and no Driftwood/Pael's Wing installed, that's
    exactly `legal_actions()[-1]`."""
    return request.legal_actions()[-1]


class _CountingRelic(Relic):
    """A minimal, test-only, room-ungated `TryModifyRewards` implementer
    (same shape as Driftwood/Pael's Wing in the C#: no room check at all) --
    counts how many times its hook actually ran, which is a stronger pin
    than checking totals: a doubled dispatch that happens to produce the
    same VALUE (e.g. because the hook is idempotent itself) would still slip
    past a totals-only assertion."""

    id = "test_counting_relic"
    name = "Counting Relic (test-only)"

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def modify_combat_rewards(self, run, rewards) -> None:
        self.calls += 1


# ════════════════════════════════════════════════════════════════════════
# A. apply_reward_modifiers must be idempotent per CombatRewards instance
#    (mirrors RewardsSet._isGenerated, RewardsSet.cs:127-130/146)
# ════════════════════════════════════════════════════════════════════════

def test_apply_reward_modifiers_does_not_double_fire_amethyst_aubergine():
    run = fresh_run(1)
    run.add_relic("amethyst_aubergine")
    gold_before = run.gold
    rewards = CombatRewards(room_type=RoomType.MONSTER, room=RoomType.MONSTER)

    apply_reward_modifiers(run, rewards)
    apply_reward_modifiers(run, rewards)          # simulates a second dispatch

    assert rewards.gold == 15, (
        "AmethystAubergine's +15 must apply exactly ONCE per screen -- got "
        f"{rewards.gold}, i.e. it fired twice"
    )
    assert run.gold == gold_before + 15


def test_apply_reward_modifiers_does_not_double_pull_black_star_relic():
    run = fresh_run(2)
    run.add_relic("black_star")
    rewards = CombatRewards(room_type=RoomType.ELITE, room=RoomType.ELITE)

    apply_reward_modifiers(run, rewards)
    apply_reward_modifiers(run, rewards)

    assert len(rewards.relics) == 1, (
        "Black Star's extra relic pull must happen exactly once -- a second "
        "dispatch on the same set pulled a second relic from the bag"
    )


def test_apply_reward_modifiers_does_not_double_add_prayer_wheel_group():
    run = fresh_run(3)
    run.add_relic("prayer_wheel")
    rewards = CombatRewards(room_type=RoomType.MONSTER, room=RoomType.MONSTER)

    apply_reward_modifiers(run, rewards)
    apply_reward_modifiers(run, rewards)

    assert len(rewards.card_rewards) == 1, (
        "Prayer Wheel adds exactly one extra CardReward group per screen -- "
        f"got {len(rewards.card_rewards)} groups after two dispatches"
    )
    assert rewards.card_rewards[0].populated and rewards.card_rewards[0].cards


def test_second_dispatch_never_even_runs_the_relic_loop():
    counter = _CountingRelic()
    run = fresh_run(4)
    run.relics.append(counter)
    rewards = CombatRewards(room_type=RoomType.MONSTER, room=RoomType.MONSTER)

    apply_reward_modifiers(run, rewards)
    apply_reward_modifiers(run, rewards)
    apply_reward_modifiers(run, rewards)

    assert counter.calls == 1


# ════════════════════════════════════════════════════════════════════════
# B. Offer-time backstop: driver._offer_rewards / RunState.offer_rewards
#    dispatch a screen nobody explicitly generated -- closing the round-12
#    T32 trap (GAP-QUEUE.md event/3C: "the next event ported this way can
#    reintroduce the same bug").
# ════════════════════════════════════════════════════════════════════════

def test_driver_offer_rewards_backstop_dispatches_an_ungenerated_screen():
    run = fresh_run(5)
    run.add_relic("amethyst_aubergine")
    gold_before = run.gold
    # Built directly, the way a construction site does -- deliberately
    # WITHOUT calling apply_reward_modifiers first, simulating a future site
    # that forgot to.
    rewards = CombatRewards(room_type=RoomType.MONSTER, room=RoomType.MONSTER)

    driver = RunDriver(run, ask=_skip_asker)
    driver._offer_rewards(rewards)

    assert rewards.gold == 15, (
        "driver._offer_rewards must dispatch apply_reward_modifiers as a "
        "backstop for a screen nobody generated yet"
    )
    assert run.gold == gold_before + 15


def test_run_offer_rewards_backstop_dispatches_an_ungenerated_screen():
    """Same backstop, the OTHER entry point: RunState.offer_rewards's own
    selectorless fallback loop (bare RunState, no driver installed)."""
    run = fresh_run(6)
    run.add_relic("amethyst_aubergine")
    gold_before = run.gold
    rewards = CombatRewards(room_type=RoomType.MONSTER, room=RoomType.MONSTER)

    run.offer_rewards(rewards)                    # no run.rewards_offerer

    assert rewards.gold == 15
    assert run.gold == gold_before + 15


def test_glass_eye_construction_call_plus_offer_backstop_still_fires_once():
    """Glass Eye already calls apply_reward_modifiers explicitly at its
    construction site (relics/glass_eye.py:78) before handing the set to
    run.offer_rewards -- the shape every real site takes now. The backstop
    inside offer_rewards must be a harmless no-op on top of it."""
    counter = _CountingRelic()
    run = fresh_run(7)
    run.add_relic("glass_eye")
    run.relics.append(counter)
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]

    glass_eye = next(r for r in run.relics if r.id == "glass_eye")
    glass_eye.after_obtained(run)   # apply_reward_modifiers, then offer_rewards

    assert counter.calls == 1, (
        "Glass Eye's own explicit dispatch plus offer_rewards's backstop "
        f"must add up to ONE relic-hook call, not {counter.calls}"
    )


# ════════════════════════════════════════════════════════════════════════
# C. Regression proof: each of the 6 real construction sites still
#    dispatches exactly once end-to-end after the backstop is wired.
# ════════════════════════════════════════════════════════════════════════

def test_site_rewards_py_761_normal_combat_path_fires_once():
    counter = _CountingRelic()
    run = fresh_run(20)
    run.relics.append(counter)

    rewards = run.generate_combat_rewards(RoomType.MONSTER)   # site #1 fires
    driver = RunDriver(run, ask=_skip_asker)
    driver._offer_rewards(rewards)                            # backstop

    assert counter.calls == 1


def test_site_rewards_py_698_final_act_boss_path_fires_once():
    counter = _CountingRelic()
    run = fresh_run(21)
    run.relics.append(counter)
    run.start_act("overgrowth", is_final_act=True)

    rewards = run.generate_combat_rewards(RoomType.BOSS)      # site #2 fires
    assert rewards.is_empty
    driver = RunDriver(run, ask=_skip_asker)
    driver._offer_rewards(rewards)                            # backstop

    assert counter.calls == 1


def test_site_run_py_1419_rest_heal_rewards_fires_once():
    counter = _CountingRelic()
    run = fresh_run(22)
    run.relics.append(counter)

    rewards = run.rest_heal_rewards()                         # site #3 fires
    driver = RunDriver(run, ask=_skip_asker)
    driver._offer_rewards(rewards)                            # backstop

    assert counter.calls == 1


def test_site_glass_eye_after_obtained_fires_once():
    counter = _CountingRelic()
    run = fresh_run(23)
    run.add_relic("glass_eye")
    run.relics.append(counter)
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]

    glass_eye = next(r for r in run.relics if r.id == "glass_eye")
    glass_eye.after_obtained(run)                              # site #4 fires
    # after_obtained already calls run.offer_rewards (with its own backstop)
    # internally -- nothing left to double-call from here.

    assert counter.calls == 1


def test_site_brain_leech_rip_fires_once():
    counter = _CountingRelic()
    run = fresh_run(24)
    run.relics.append(counter)

    ev = make_event("brain_leech", run).begin()
    ev.choose("RIP")                                          # site #5 fires
    driver = RunDriver(run, ask=_skip_asker)
    driver._offer_rewards(ev.pending_rewards)                 # backstop

    assert counter.calls == 1


def test_site_trial_nondescript_guilty_fires_once():
    counter = _CountingRelic()
    run = fresh_run(25)
    run.relics.append(counter)

    ev = make_event("trial", run).begin()

    class _Fixed:
        def randrange(self, _n):
            return 2                                          # -> NONDESCRIPT

    ev.rng = _Fixed()
    ev.choose("ACCEPT")
    ev.choose("GUILTY")                                       # site #6 fires
    driver = RunDriver(run, ask=_skip_asker)
    driver._offer_rewards(ev.pending_rewards)                 # backstop

    assert counter.calls == 1


# ════════════════════════════════════════════════════════════════════════
# D. The treasure-room hole: C#'s TreasureRoom.DoExtraRewardsIfNeeded
#    (TreasureRoom.cs:75-97) dispatches Hook.ModifyRewards over an empty,
#    Room=Treasure RewardsSet that the chest's own direct gold+relic grant
#    (OneOffSynchronizer.DoTreasureRoomRewards, no RewardsSet at all) never
#    touches. The sim had no dispatch call for a treasure room at all.
# ════════════════════════════════════════════════════════════════════════

def _walk_to_treasure(run: RunState, seed: int = 1):
    """March a started act to its treasure node, mirroring
    test_shop_and_map_mods.py::test_spoils_map_quest_pays_600's walk."""
    walk = random.Random(seed)
    while run.current_point.point_type != MapPointType.TREASURE and not run.at_act_end:
        res = run.enter_point(walk.choice(run.travelable_points()))
        if res.room_type == RoomType.TREASURE:
            return res
    raise AssertionError("walk did not reach a treasure node")


def test_treasure_room_reward_dispatch_is_dormant_with_todays_roster():
    """D1 -- the enumeration. Every ported TryModifyRewards[Late] /
    TryModifyCardRewardAlternatives implementer (amethyst_aubergine,
    black_star, driftwood, lava_rock, prayer_wheel, white_star,
    wongos_mystery_ticket, paels_wing -- the complete set found by
    `grep -rl "def modify_combat_rewards" sts2_rl/relics`) is room-gated to
    Monster/Elite/Boss, gated to a specific one of those, or only touches
    EXISTING rewards.card_rewards groups. A treasure room's extra-rewards
    set starts and stays empty (GenerateRewardsFor returns [] for a
    TreasureRoom, RewardsSet.cs:213-219), so none of them produces anything
    observable here today -- executed, not just read."""
    run = fresh_run(30)
    for rid in (
        "amethyst_aubergine", "black_star", "driftwood", "lava_rock",
        "prayer_wheel", "white_star", "wongos_mystery_ticket", "paels_wing",
    ):
        run.add_relic(rid)
    run.start_act("overgrowth")
    gold_before = run.gold

    res = _walk_to_treasure(run, seed=1)

    assert run.pending_treasure_extra_rewards is None, (
        "no ported relic reacts to Room==Treasure today -- the extra-"
        "rewards set must come back empty and unstashed"
    )
    assert res.gold >= 42            # the chest's own direct grant still ran
    assert run.gold > gold_before


def test_treasure_room_extra_rewards_reach_a_future_relic_and_get_offered():
    """D2 -- proves the wiring, not just its absence: a hypothetical future
    relic gated on Room==Treasure (the shape C# supports and today's roster
    doesn't use) gets a real screen, and the driver offers it exactly once."""

    class _TreasureCardRelic(Relic):
        id = "test_treasure_card_relic"
        name = "Treasure Card Relic (test-only)"

        def modify_combat_rewards(self, run, rewards) -> None:
            from sts2_rl.cards import make_card
            from sts2_rl.rewards import CardRewardGroup

            if rewards.room != RoomType.TREASURE:
                return
            rewards.card_rewards.append(CardRewardGroup(
                cards=[make_card("strike")], room_type=RoomType.MONSTER,
                populated=True,
            ))

    run = fresh_run(31)
    run.relics.append(_TreasureCardRelic())
    run.start_act("overgrowth")

    _walk_to_treasure(run, seed=1)

    extra = run.pending_treasure_extra_rewards
    assert extra is not None and extra.card_rewards, (
        "a Room==Treasure-gated relic's CardReward must reach the pending "
        "treasure extra-rewards channel"
    )

    driver = RunDriver(run, ask=_skip_asker)
    offered = []

    def _spy_ask(request):
        offered.append(request.kind)
        return request.legal_actions()[-1]

    driver._ask_fn = _spy_ask
    driver._offer_treasure_extra_rewards()

    from sts2_rl.driver import DecisionKind

    assert DecisionKind.REWARD_CARD in offered
    assert run.pending_treasure_extra_rewards is None      # consumed once
