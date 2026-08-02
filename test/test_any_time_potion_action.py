"""`PotionUsage.AnyTime` outside combat, as a first-class *decision*.

The engine half of this landed on 2026-07-27 (`RunState.use_potion`) and the
conformance half on 2026-07-28 (`ReplayRunner._use_map_potion`), but nothing on
the RL side could reach either: the run env exposed a potion action only inside
its combat block, so a trained policy could never drink Blood Potion, Entropic
Brew, Foul Potion or Fruit Juice on the map. This file pins the third half —
`potion/_any_time_usage`.

Source: `NPotionPopup.RefreshButtons` (NPotionPopup.cs:322-325) enables the Use
button for an AnyTime potion with **no** screen predicate at all — the combat
predicate (`IsInProgress && CurrentSide == Side && IsAlive &&
!InACardSelectScreen && !PlayerActionsDisabled`) is the `else if` arm that only
CombatOnly potions fall into. `Enter` (NPotionPopup.cs:128-130) says the same on
first open. So the belt is live on the map, in a shop, at a rest site, mid-event
and inside a card-select screen alike, and drinking does not dismiss the screen
you opened it from.
"""
from __future__ import annotations

import random

import numpy as np
import pytest

from sts2_rl.driver import (
    POTION_ACTION_BASE,
    DecisionKind,
    DecisionRequest,
    RunDriver,
)
from sts2_rl.potions import make_potion
from sts2_rl.run import RunState
from sts2_rl.run_env import (
    MAX_POTION_SLOTS,
    MAX_SELECT_CANDIDATES,
    N_ACTIONS,
    POTION_BASE,
    SELECT_BASE,
    STS2RunEnv,
)


def _run_with(potion_ids):
    run = RunState(rng=random.Random(0))
    run.start_run()
    for slot, pid in enumerate(potion_ids):
        run.potions[slot] = None if pid is None else make_potion(pid)
    return run


# ═════════════════════════════════════════════════════════════════════════
# The decision seam
# ═════════════════════════════════════════════════════════════════════════

def test_an_out_of_combat_decision_offers_every_any_time_potion():
    run = _run_with(["fire_potion", "fruit_juice", "blood_potion"])
    req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()] * 3)
    legal = req.legal_actions()
    # The map's own options are untouched and keep index 0..n-1.
    assert legal[:3] == [0, 1, 2]
    # Fruit Juice (slot 1) and Blood Potion (slot 2) are AnyTime; Fire Potion
    # (slot 0) is CombatOnly and the popup disables its button here.
    assert legal[3:] == [POTION_ACTION_BASE + 1, POTION_ACTION_BASE + 2]


def test_the_belt_action_index_is_the_slot_not_a_rank():
    """The belt is never compacted (`Player.DiscardPotionInternal`), so the
    action must name the SLOT — a rank over the non-empty slots would drink the
    wrong potion after any earlier slot empties."""
    run = _run_with([None, None, "foul_potion"])
    req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()])
    assert POTION_ACTION_BASE + 2 in req.legal_actions()
    assert POTION_ACTION_BASE + 0 not in req.legal_actions()


@pytest.mark.parametrize("kind,extra", [
    (DecisionKind.EVENT, {}),
    (DecisionKind.REST, {"rest_options": []}),
    (DecisionKind.SELECT_OPTION, {"n_options": 2}),
])
def test_every_out_of_combat_screen_offers_the_belt(kind, extra):
    """AnyTime has no screen predicate — not the map screen specifically."""
    run = _run_with(["fruit_juice"])
    req = DecisionRequest(kind=kind, run=run, **extra)
    if kind is DecisionKind.EVENT:
        req.event = _StubEvent()
    assert POTION_ACTION_BASE + 0 in req.legal_actions()


class _StubEvent:
    class _Opt:
        locked = False
    options = [_Opt(), _Opt()]


def test_a_live_combat_offers_no_belt_action():
    """In combat the belt is the combat block's own potion actions
    (`full_env.combat_action_count`), which target enemies and run the full
    `OnUseWrapper`. Offering the out-of-combat entry point there would skip the
    wrapper's combat steps, so it is masked off."""
    run = _run_with(["fruit_juice"])
    req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()])
    req.in_combat = True
    assert req.legal_actions() == [0]


def test_the_driver_drinks_and_re_asks_the_same_decision():
    """`NPotionPopup` is an overlay: drinking resolves the potion and leaves you
    on the screen underneath, still owing it an answer."""
    run = _run_with(["fruit_juice"])
    before = run.max_hp
    seen: list[DecisionKind] = []
    answers = [POTION_ACTION_BASE + 0, 1]

    def asker(request):
        seen.append(request.kind)
        return answers.pop(0)

    driver = RunDriver(run, asker)
    req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()] * 2)
    assert driver._ask(req) == 1              # the map answer, not the potion
    assert seen == [DecisionKind.MAP, DecisionKind.MAP]   # same screen twice
    assert run.max_hp == before + 5           # FruitJuice.cs
    assert run.potions[0] is None             # RemoveBeforeUse
    # Both asks count: each is a real decision the policy made.
    assert driver.decisions == 2


def test_a_drunk_potion_stops_being_offered():
    run = _run_with(["fruit_juice"])
    answers = [POTION_ACTION_BASE + 0, POTION_ACTION_BASE + 0]

    driver = RunDriver(run, lambda r: answers.pop(0))
    req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()])
    with pytest.raises(ValueError, match="illegal action"):
        driver._ask(req)


# ═════════════════════════════════════════════════════════════════════════
# The run env's action block
# ═════════════════════════════════════════════════════════════════════════

_ENV = None


def _env():
    global _ENV
    if _ENV is None:
        _ENV = STS2RunEnv()
    return _ENV


def test_the_potion_block_is_its_own_action_range():
    # T5b (R4): the select block is now MAX_SELECT_CANDIDATES-wide (a
    # candidate-index block), not 2*N_CARDS (the old (card id, upgraded)
    # pair block).
    assert POTION_BASE == SELECT_BASE + MAX_SELECT_CANDIDATES
    assert N_ACTIONS == POTION_BASE + MAX_POTION_SLOTS
    assert _env().action_space.n == N_ACTIONS


def test_the_env_masks_and_translates_the_potion_block():
    env = _env()
    env.reset(seed=3)
    run = env._run
    request = env._request
    for slot in range(len(run.potions)):
        run.potions[slot] = None
    run.potions[2] = make_potion("blood_potion")

    mask = env.action_masks()
    assert mask[POTION_BASE + 2]
    assert not mask[POTION_BASE + 0]
    assert not mask[POTION_BASE + 1]
    assert env._translate(POTION_BASE + 2, request) == POTION_ACTION_BASE + 2
    assert env._translate(POTION_BASE + 0, request) is None


def test_the_env_can_actually_drink_one_mid_episode():
    env = _env()
    env.reset(seed=11)
    run = env._run
    for slot in range(len(run.potions)):
        run.potions[slot] = None
    run.potions[0] = make_potion("fruit_juice")
    before = run.max_hp
    phase_before = env._request.kind

    assert env.action_masks()[POTION_BASE]
    env.step(POTION_BASE)
    assert run.max_hp == before + 5
    assert run.potions[0] is None
    # Still owing the same screen an answer, and its block is masked again.
    assert env._request.kind is phase_before
    assert not env.action_masks()[POTION_BASE]


def test_a_masked_random_episode_still_finishes_with_the_new_block():
    env = STS2RunEnv()
    rng = np.random.default_rng(7)
    env.reset(seed=7)
    for _ in range(20_000):
        mask = env.action_masks()
        assert mask.shape == (env.n_actions,) and mask.any()
        _, _, terminated, truncated, _ = env.step(int(rng.choice(np.flatnonzero(mask))))
        if terminated or truncated:
            return
    pytest.fail("episode did not finish")
