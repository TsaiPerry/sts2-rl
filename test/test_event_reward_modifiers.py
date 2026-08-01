"""Task 32 — the mid-event reward screens skip the reward-modifier dispatch.

`RewardsSet.GenerateWithoutOffering` (RewardsSet.cs:125-147) is the single
choke point every `RewardsSet` goes through — combat, rest-site, and any
`RewardsCmd.OfferCustom` caller alike (RewardsCmd.cs:47-50: `OfferCustom`
just builds `new RewardsSet(player).WithCustomRewards(rewards)` and calls
`.Offer()`, which starts with `GenerateWithoutOffering`). It runs
`Hook.ModifyRewards` (Hook.cs:1981-1999) — the plain-then-Late pass
Driftwood implements (Driftwood.cs:14-25) without checking `room`, so its
`CanReroll = true` lands on ANY CardReward, including a room-less custom
set.

Task 31 confirmed and fixed this for the rest-site path
(`RunState.rest_heal_rewards`, sts2_rl/run.py:1398-1420, which now calls
`apply_reward_modifiers` itself — see test_reward_dispatch_and_relic_stubs.py)
but two more sites build a `CombatRewards` directly and hand it to the
mid-event `pending_rewards` channel without ever calling
`apply_reward_modifiers`:

  - `sts2_rl/events/brain_leech.py::BrainLeech._rip` — BrainLeech.cs:51-61's
    `RewardsCmd.OfferCustom` for the Rip 3-card colourless choice. NOTE: C#
    calls `OfferCustom` once per `RewardCount` iteration (BrainLeech.cs:54-59)
    where the sim batches every group into ONE dispatch. Dormant today because
    `RewardCount` is hardcoded to 1; re-check if that ever becomes > 1.
  - `sts2_rl/events/trial.py::Trial._nondescript_guilty` — Trial.cs:177-187's
    `RewardsCmd.OfferCustom` for the Nondescript Guilty verdict. This is ONE
    call carrying a 2-item list (Trial.cs:185), not two calls, so the sim's
    single dispatch over both groups is the faithful shape.

So a player holding Driftwood who reaches either screen gets an ordinary,
non-rerollable CardReward where the game would offer a reroll. This file
pins the RED (both screens come back `can_reroll=False` today) and, after
the fix, the GREEN (both come back `can_reroll=True` with Driftwood held,
and stay `False` without it — the same before/after pin
test_reward_dispatch_and_relic_stubs.py used for the rest-site fix).

Run with:  py -m pytest test/test_event_reward_modifiers.py -v
"""
from __future__ import annotations

import random

from sts2_rl import make_event
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


def _trial_forced(run: RunState, roll: int):
    """Begin Trial and force the sub-trial roll to `roll` (0/1/2) — mirrors
    test_glory_events.py's `_trial_forced` helper."""
    ev = make_event("trial", run).begin()

    class _Fixed:
        def randrange(self, _n):
            return roll

    ev.rng = _Fixed()
    ev.choose("ACCEPT")
    return ev


# ── Brain Leech's Rip reward ─────────────────────────────────────────────


def test_brain_leech_rip_reward_is_rerollable_with_driftwood():
    run = fresh_run(1)
    run.add_relic("driftwood")

    ev = make_event("brain_leech", run).begin()
    ev.choose("RIP")

    assert ev.pending_rewards is not None
    assert ev.pending_rewards.card_rewards[0].cards
    assert ev.pending_rewards.can_reroll, (
        "Driftwood held + Brain Leech's Rip CardReward should be rerollable "
        "(RewardsSet.cs:136 fires Hook.ModifyRewards on every RewardsSet, "
        "including this mid-event custom one) — came back can_reroll=False"
    )


def test_brain_leech_rip_reward_not_rerollable_without_driftwood():
    run = fresh_run(1)

    ev = make_event("brain_leech", run).begin()
    ev.choose("RIP")

    assert ev.pending_rewards is not None
    assert ev.pending_rewards.card_rewards[0].cards
    assert not ev.pending_rewards.can_reroll


# ── Trial's Nondescript Guilty reward ────────────────────────────────────


def test_trial_nondescript_guilty_reward_is_rerollable_with_driftwood():
    run = fresh_run(2)
    run.add_relic("driftwood")

    ev = _trial_forced(run, 2)
    ev.choose("GUILTY")

    assert ev.pending_rewards is not None
    assert len(ev.pending_rewards.card_rewards) == 2
    assert all(g.cards for g in ev.pending_rewards.card_rewards)
    assert ev.pending_rewards.can_reroll, (
        "Driftwood held + Trial's Nondescript Guilty CardReward should be "
        "rerollable (RewardsSet.cs:136 fires Hook.ModifyRewards on every "
        "RewardsSet, including this mid-event custom one) — came back "
        "can_reroll=False"
    )
    # Driftwood's TryModifyRewardsLate (Driftwood.cs:20-23) sets CanReroll on
    # EVERY CardReward in the set, not just the first.
    assert all(g.can_reroll for g in ev.pending_rewards.card_rewards)


def test_trial_nondescript_guilty_reward_not_rerollable_without_driftwood():
    run = fresh_run(2)

    ev = _trial_forced(run, 2)
    ev.choose("GUILTY")

    assert ev.pending_rewards is not None
    assert len(ev.pending_rewards.card_rewards) == 2
    assert not ev.pending_rewards.can_reroll
    assert not any(g.can_reroll for g in ev.pending_rewards.card_rewards)


# ── Control: room-gated reward relics must stay OFF these room-less screens ─
#
# AmethystAubergine.cs:29-32 (`room == null` -> false) is the same room gate
# WongosMysteryTicket/BlackStar/LavaRock/Vintage use — the sim's
# `CombatRewards.room` stays `None` for a set built outside a room
# (rewards.py:565), exactly like `RewardsSet.Room` for `WithCustomRewards`
# (RewardsSet.cs:106-110). Dispatching `apply_reward_modifiers` on the two
# fixed mid-event screens must NOT let AmethystAubergine's +15 gold leak onto
# them the way Driftwood's reroll correctly does.
#
# CORRECTION (task reviewer, 2026-07-31): Midas does NOT belong in that list.
# `Midas.TryModifyRewardsLate` (Midas.cs:12-29) takes a `room` parameter and
# never reads it — it doubles every `GoldReward` unconditionally. So Driftwood
# is NOT "the only room-ungated hook"; Midas is ungated too. It is irrelevant
# HERE for a different reason: neither mid-event screen ever carries a
# `GoldReward` for it to touch. Anyone extending this reasoning to a new screen
# must check the reward SHAPES, not just the room gate.


def test_brain_leech_rip_reward_amethyst_aubergine_does_not_add_gold():
    run = fresh_run(1)
    run.add_relic("amethyst_aubergine")
    gold_before = run.gold

    ev = make_event("brain_leech", run).begin()
    ev.choose("RIP")

    assert ev.pending_rewards.gold == 0
    assert run.gold == gold_before


def test_trial_nondescript_guilty_reward_amethyst_aubergine_does_not_add_gold():
    run = fresh_run(2)
    run.add_relic("amethyst_aubergine")
    gold_before = run.gold

    ev = _trial_forced(run, 2)
    ev.choose("GUILTY")

    assert ev.pending_rewards.gold == 0
    assert run.gold == gold_before
