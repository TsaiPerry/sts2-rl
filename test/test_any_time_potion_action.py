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
    POTION_DISCARD_ACTION_BASE,
    DecisionKind,
    DecisionRequest,
    RunDriver,
)
from sts2_rl.potions import make_potion
from sts2_rl.run import RunState
from sts2_rl.run_env import (
    DISCARD_BASE,
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
    # (slot 0) is CombatOnly and the popup disables its button here. All three
    # held potions are discardable regardless of usage class (v22 §A1).
    assert legal[3:] == [
        POTION_ACTION_BASE + 1, POTION_ACTION_BASE + 2,
        POTION_DISCARD_ACTION_BASE + 0, POTION_DISCARD_ACTION_BASE + 1,
        POTION_DISCARD_ACTION_BASE + 2]


def test_the_belt_action_index_is_the_slot_not_a_rank():
    """The belt is never compacted (`Player.DiscardPotionInternal`), so the
    action must name the SLOT — a rank over the non-empty slots would drink the
    wrong potion after any earlier slot empties."""
    # Fruit Juice, not Foul Potion: this test is about SLOT indexing, and Foul
    # Potion's own usability check refuses outside a shop (see the test below),
    # which would make the assertion pass or fail for an unrelated reason.
    run = _run_with([None, None, "fruit_juice"])
    req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()])
    assert POTION_ACTION_BASE + 2 in req.legal_actions()
    assert POTION_ACTION_BASE + 0 not in req.legal_actions()


def test_a_potion_its_usability_check_refuses_is_not_offered():
    """`PassesCustomUsabilityCheck` DISABLES the Use button
    (NPotionPopup.cs:144-147), so the action must not be offered at all.

    `RunState.use_potion` already consulted the gate and returned False, but
    `potion_actions` did not — so the mask offered a slot the executor refused
    and `RunDriver._ask` tripped its own invariant (`assert drunk,
    "potion_actions offered a slot use_potion refused"`), killing the env
    worker and the training run with it.

    Foul Potion is the source's only override: usable in combat, at a shop
    whose stall still stands, and in the Fake Merchant event -- nowhere else.
    """
    run = _run_with(["foul_potion"])
    req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()])
    foul = run.potions[0]
    assert not foul.passes_custom_usability_check(run=run), (
        "fixture sanity: a plain map screen is not a shop")
    assert POTION_ACTION_BASE + 0 not in req.legal_actions()


def test_every_offered_belt_action_is_one_use_potion_accepts():
    """The invariant `RunDriver._ask` asserts, pinned directly rather than only
    as a crash: the mask is a promise, and every slot it offers must actually
    be drinkable. Covers each AnyTime potion, including the gated one."""
    from sts2_rl.potions import USAGE_ANY_TIME, ALL_POTIONS

    any_time = sorted(
        pid for pid, cls in ALL_POTIONS.items()
        if getattr(cls, "usage", None) == USAGE_ANY_TIME
    )
    assert "foul_potion" in any_time, "fixture sanity: the gated potion is AnyTime"

    for pid in any_time:
        run = _run_with([pid])
        req = DecisionRequest(kind=DecisionKind.MAP, run=run, points=[object()])
        for action in req.potion_actions():
            slot = action - POTION_ACTION_BASE
            assert run.use_potion(slot), (
                f"{pid}: potion_actions offered slot {slot} but use_potion "
                f"refused it -- RunDriver._ask would assert here")


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
    assert DISCARD_BASE == POTION_BASE + MAX_POTION_SLOTS
    assert N_ACTIONS == DISCARD_BASE + MAX_POTION_SLOTS
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


# ── potion/_belt_lock — the three events that disable the belt ─────────────


def _event_run(event_id: str, potion_ids):
    """A run standing in `event_id`'s room with `potion_ids` in the belt."""
    run = _run_with(potion_ids)
    from sts2_rl.events import make_event

    run.current_event = make_event(event_id, run).begin()
    return run


@pytest.mark.parametrize("event_id", [
    "the_future_of_potions",
    "ranwid_the_elder",
    "stone_of_all_time",
])
def test_the_belt_is_locked_while_a_belt_locking_event_is_open(event_id):
    """`Player.CanRemovePotions` — set False for exactly these three events
    (TheFutureOfPotions.cs:92, RanwidTheElder.cs:42, StoneOfAllTime.cs:66) and
    read by `NPotionPopup` to DISABLE the Use and Discard buttons
    (NPotionPopup.cs:139-142). So the belt is not usable while one is open.

    All three sim ports recorded this as "UI-only and not modeled". That was
    true when written -- there was no out-of-combat belt action at all -- and
    stopped being true when `potion_actions` landed. The guard is what stops a
    player from drinking a potion that the OPEN EVENT's own options refer to:
    The Future of Potions captures potion objects in its option closures, so
    drinking one mid-event left an option that traded a potion no longer held,
    and `RunState.discard_potion` raised `ValueError: ... is not in list`
    (killed a training run).
    """
    run = _event_run(event_id, ["blood_potion", "fruit_juice"])
    assert not run.can_remove_potions
    req = DecisionRequest(kind=DecisionKind.EVENT, run=run)
    req.event = run.current_event
    assert req.potion_actions() == []


def test_the_belt_unlocks_once_the_event_finishes():
    run = _event_run("stone_of_all_time", ["blood_potion"])
    assert not run.can_remove_potions
    run.current_event._finish("DONE")
    assert run.can_remove_potions
    req = DecisionRequest(kind=DecisionKind.EVENT, run=run)
    req.event = run.current_event
    assert POTION_ACTION_BASE + 0 in req.potion_actions()


def test_an_ordinary_event_leaves_the_belt_live():
    """The lock is those three events only -- every other event keeps the
    AnyTime belt available, which is the whole point of `potion_actions`."""
    run = _run_with(["blood_potion"])
    assert run.can_remove_potions
    req = DecisionRequest(kind=DecisionKind.EVENT, run=run)
    req.event = _StubEvent()
    assert POTION_ACTION_BASE + 0 in req.potion_actions()


def test_future_of_potions_options_cannot_go_stale():
    """The end-to-end shape of the training crash: with the belt locked, the
    potion an option captured is still held when that option is chosen."""
    run = _event_run("the_future_of_potions",
                     ["blood_potion", "fire_potion", "fruit_juice"])
    event = run.current_event
    req = DecisionRequest(kind=DecisionKind.EVENT, run=run)
    req.event = event
    # No belt action is offered, so the policy cannot empty a captured slot.
    assert req.potion_actions() == []
    assert [a for a in req.legal_actions() if a >= POTION_ACTION_BASE] == []
    # And the trade itself still works.
    assert event.choose(0)


# ── potion/_belt_resolves_screen — a drink that ends the screen ────────────


def test_a_drink_that_finishes_the_event_does_not_re_ask_an_empty_page():
    """Foul Potion drunk in the Fake Merchant event runs
    `FakeMerchant.FoulPotionThrown` (FoulPotion.cs:89-108), which blows up the
    stall and FINISHES the event -- there is no page left to answer.

    `_ask`'s re-ask loop assumes the belt is an overlay over a screen that
    still owes an answer, which is true for every other drink. Here it re-asked
    an event with no options left: `legal_actions() == []`, i.e. an all-False
    action mask, which a masked categorical turns into NaN. It now reports
    `NO_ANSWER` and `_run_event` stops.

    This is the one screen a drink can resolve -- SHOP keeps `leave` legal, and
    the three belt-locking events do not offer the belt at all.
    """
    from sts2_rl.driver import NO_ANSWER
    from sts2_rl.events import make_event

    run = _run_with(["foul_potion"])
    event = make_event("fake_merchant", run)
    run.current_event = event
    event.begin()

    req = DecisionRequest(kind=DecisionKind.EVENT, run=run, event=event)
    assert POTION_ACTION_BASE + 0 in req.legal_actions(), (
        "fixture sanity: Foul Potion IS drinkable in this event")

    asks = []

    def asker(request):
        asks.append(list(request.legal_actions()))
        return POTION_ACTION_BASE + 0

    driver = RunDriver(run, asker)
    assert driver._ask(req) == NO_ANSWER
    assert len(asks) == 1, "the resolved page must not be asked again"
    assert event.finished


def test_ask_refuses_a_decision_with_no_legal_actions():
    """The general guard behind that fix: `legal_actions` becomes the policy's
    action mask verbatim, so a decision with none is never a choice the policy
    can make. Fail loudly at the seam instead of shipping an all-False mask."""
    run = _run_with([])
    event = make_event_with_no_options(run)
    req = DecisionRequest(kind=DecisionKind.EVENT, run=run, event=event)
    assert req.legal_actions() == []

    driver = RunDriver(run, lambda r: 0)
    with pytest.raises(RuntimeError, match="NO legal actions"):
        driver._ask(req)


def make_event_with_no_options(run):
    class _Empty:
        options: list = []
        finished = True
    return _Empty()
