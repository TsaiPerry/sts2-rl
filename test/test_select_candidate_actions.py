"""R4 acceptance tests (T5b, prompts/entity-obs-schema.md): the SELECT_CARDS
action block must address the SAME per-candidate rows the v7 observation
writes, so two candidates sharing (card id, upgraded) but differing in
enchantment, affliction or cost modifier are independently selectable.

Before this lane's fix, `run_env._translate` decoded a SELECT_CARDS action as
a `(card id, upgraded)` pair and handed the driver the FIRST candidate that
matched — so a `nimble`-enchanted Defend among plain Defends (the seed-75
shape recorded in the progress ledger) collapsed onto the same action as the
plain ones, and the agent could never reach it. Written BEFORE the fix (TDD):
every test below was confirmed RED against the old pair-based
`_translate`/`action_masks`.

Style mirrors test/test_run_obs_v4.py: build a bare `RunState` + hand-built
`DecisionRequest`, wire it into an `STS2RunEnv` via the same "surgery"
pattern (set `env._run` / `env._request` directly, bypass the greenlet), and
read the facts straight off the request/observation rather than trusting a
second copy of the encoder.
"""
from __future__ import annotations

import random

import numpy as np
import pytest

from sts2_rl import RunState, make_card, make_potion
from sts2_rl.afflictions import RingingAffliction
from sts2_rl.cmds import CardCmd
from sts2_rl.driver import POTION_ACTION_BASE, DecisionKind, DecisionRequest
from sts2_rl.enchantments import make_enchantment
from sts2_rl.full_env import AFFLICTION_INDEX, CARD_INDEX, ENCHANTMENT_INDEX, _clip01
from sts2_rl.obs import PAD
from sts2_rl.player import PlayerCombatState
from sts2_rl.relics.alchemical_coffer import AlchemicalCoffer
from sts2_rl.relics.phial_holster import PhialHolster
from sts2_rl.relics.potion_belt import PotionBelt
from sts2_rl.run_env import (
    CHOICE_BASE,
    MAX_POTION_SLOTS,
    MAX_SELECT_CANDIDATES,
    N_ACTIONS,
    POTION_BASE,
    SELECT_BASE,
    STS2RunEnv,
    _run_card_row,
    run_obs_layout,
)


# ── Fixtures / helpers (mirrors test_run_obs_v4.py's) ────────────────────


def _bare_run(**kwargs) -> RunState:
    return RunState(rng=random.Random(0), **kwargs)


def _env_with(run: RunState, request: DecisionRequest) -> STS2RunEnv:
    """An STS2RunEnv wired directly to `run`/`request`, bypassing the
    greenlet/driver — `_build_obs`/`_translate`/`action_masks` only read
    `self._run`/`self._request`, so this is safe without calling reset()."""
    env = STS2RunEnv()
    env._run = run
    env._request = request
    return env


def _select_request(run: RunState, candidates: list, *, purpose="from_draw",
                     skippable=False, count_remaining=1) -> DecisionRequest:
    return DecisionRequest(
        kind=DecisionKind.SELECT_CARDS, run=run, purpose=purpose,
        candidates=list(candidates), count_remaining=count_remaining,
        skippable=skippable,
    )


def _heterogeneous_candidates(n: int) -> list:
    """`n` cards spanning several ids/upgrade levels, with at least one
    afflicted, one enchanted and one exhaust-on-next-play card whenever `n`
    is large enough (mirrors test_run_obs_v4.py's `_heterogeneous_cards` —
    review flagged all-identical fixtures as the shape that misses real
    bugs)."""
    ids = ["strike", "defend", "bash", "pommel_strike"]
    cards = []
    for i in range(n):
        c = make_card(ids[i % len(ids)])
        if i % 3 == 1:
            c.upgrade()
        cards.append(c)
    if len(cards) > 0:
        CardCmd.afflict(cards[0], RingingAffliction, 1)
    if len(cards) > 1:
        make_enchantment("sown").attach(cards[1])
    if len(cards) > 2:
        cards[2].exhaust_on_next_play = True
    return cards


def _candidates_with_real_ties() -> list:
    """Review item 4: `_heterogeneous_candidates` alone produces NO ties —
    every one of its rows differs by id, upgrade, affliction or enchantment,
    so it never exercises the sort's tie-breaking, which is the only
    fragile part of the shuffle-invariance property. R4 exists *because of*
    duplicate candidates that differ only in aux fields, so a test with no
    duplicates tests the one case R4 was never about.

    Three distinguishing cards (afflicted / upgraded+enchanted / exhaust-
    flagged, from `_heterogeneous_candidates(3)`) plus 4 plain Defends and 3
    plain Strikes — genuinely identical, tied rows, matching the shape the
    reviewer's own 400-permutation sweep used."""
    cards = _heterogeneous_candidates(3)
    cards += [make_card("defend") for _ in range(4)]
    cards += [make_card("strike") for _ in range(3)]
    return cards


# ── 1. The R4 defect, as a regression test ────────────────────────────────


def test_enchanted_duplicate_is_independently_selectable():
    """seed-75 shape: a nimble-enchanted Defend (index 2) among plain
    Defends. The old (card id, upgraded)-pair encoding could not distinguish
    it from the plain copies at all, and `_translate`'s "first match" search
    always resolved to index 0 regardless of which action was chosen."""
    plain_a = make_card("defend")
    plain_b = make_card("defend")
    nimble_defend = make_card("defend")
    make_enchantment("nimble").attach(nimble_defend)
    plain_c = make_card("defend")
    cards = [plain_a, plain_b, nimble_defend, plain_c]

    run = _bare_run()
    request = _select_request(run, cards)
    env = _env_with(run, request)

    mask = env.action_masks()
    select_bits = mask[SELECT_BASE:SELECT_BASE + MAX_SELECT_CANDIDATES]
    assert int(select_bits.sum()) == len(cards), (
        "one mask bit per addressable candidate — the enchanted copy must "
        "get its own bit, not collapse onto the plain Defends' bit"
    )

    # Fix-pass correction (review item 5): `order.index(2)` followed by
    # `_translate(SELECT_BASE + order.index(2)) == 2` is a tautology —
    # `_translate` computes that SAME `order` internally, so this passed for
    # any order at all, correct or not, and could never fail. Assert
    # something that CAN fail instead: index 2 (the enchanted Defend) must
    # actually be among the candidates some legal action reaches.
    reachable = {env._translate(SELECT_BASE + i, request) for i in range(len(cards))}
    assert 2 in reachable, (
        "an action must exist that resolves to the enchanted Defend "
        "specifically, not just to *a* Defend"
    )


# ── 2. Round trip ──────────────────────────────────────────────────────────


def test_round_trip_every_legal_action_is_distinct_and_valid():
    cards = _heterogeneous_candidates(10) + [make_card("defend"), make_card("defend")]
    run = _bare_run()
    request = _select_request(run, cards)
    env = _env_with(run, request)
    mask = env.action_masks()

    translated = []
    for i in range(MAX_SELECT_CANDIDATES):
        action = SELECT_BASE + i
        if not mask[action]:
            continue
        idx = env._translate(action, request)
        assert idx is not None
        assert 0 <= idx < len(cards)
        translated.append(idx)

    assert len(translated) == len(set(translated)), "every legal action must reach a distinct candidate"
    order = env._sorted_candidate_order(request)
    assert set(translated) == set(order), "every candidate within the cap must be reachable"


# ── 3. Observation/action agreement ─────────────────────────────────────────


def test_observation_row_matches_what_the_same_index_action_selects():
    """Candidate row i in the observation must describe exactly the card
    action `SELECT_BASE + i` selects. Verified against DIRECT reads of
    `request.candidates` (vocab lookups recomputed inline here), not by
    calling `_sorted_candidate_order` a second time on the test side — that
    would just check the helper agrees with itself."""
    cards = _heterogeneous_candidates(12)
    run = _bare_run()
    request = _select_request(run, cards)
    env = _env_with(run, request)
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["select.candidates.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["select.candidates.f"]].reshape(-1, 4)

    mask = env.action_masks()
    checked = 0
    for i in range(MAX_SELECT_CANDIDATES):
        action = SELECT_BASE + i
        if not mask[action]:
            continue
        true_idx = env._translate(action, request)
        assert true_idx is not None
        card = request.candidates[true_idx]

        # Fix-pass correction (review item 6): this used to check 5 of the
        # row's 8 fields, silently skipping ids[0] (pile_id) and — more
        # importantly — fs[1] (effective cost) and fs[2] (affliction
        # amount), both members of `card_instance_row`'s signature and
        # exactly the two fields R4 exists to distinguish (two candidates
        # differing only by cost modifier or affliction amount would not
        # have been caught). Check all 8.
        assert int(ids[i][0]) == PAD, "run-side rows carry no pile id"
        assert int(ids[i][1]) == CARD_INDEX[card.id] + 1
        expected_aff = PAD if card.affliction is None else AFFLICTION_INDEX[card.affliction.id] + 1
        expected_ench = PAD if card.enchantment is None else ENCHANTMENT_INDEX[card.enchantment.id] + 1
        assert int(ids[i][2]) == expected_aff
        assert int(ids[i][3]) == expected_ench

        assert fs[i][0] == pytest.approx(_clip01(card.upgrade_level / 5.0))
        assert fs[i][1] == pytest.approx(_clip01(card.energy_cost / 6.0))
        expected_aff_amount = (
            _clip01(card.affliction.amount / 10.0) if card.affliction is not None else 0.0
        )
        assert fs[i][2] == pytest.approx(expected_aff_amount)
        expected_exhaust = 1.0 if card.exhaust_on_next_play else 0.0
        assert fs[i][3] == pytest.approx(expected_exhaust)
        checked += 1
    assert checked == len(cards), "sanity: the fixture must actually be under the cap"


# ── 4. Shuffle invariance ────────────────────────────────────────────────


def test_shuffle_invariance_of_which_card_an_action_selects():
    """Permuting `request.candidates` must not change which ROW SIGNATURE a
    given action selects, even though it may change which raw index that
    card sits at, and (on a genuine tie) which specific object of several
    interchangeable ones it lands on.

    Fix-pass correction (review item 4): the fixture now contains real ties
    (`_candidates_with_real_ties` — several identical plain Defends/Strikes
    alongside the distinguishing cards), and the per-action assertion
    checks ROW EQUALITY (the selected card's full 8-field row signature)
    rather than object identity. Identity is the wrong tool here: with tied
    rows, two cards ARE genuinely interchangeable — nothing observes which
    physical object action X lands on, only what its row looks like — so an
    identity assertion fails on every shuffle that swaps tied objects around
    (254 times across 50 permutations of this exact shape, per the
    reviewer's sweep) for a reason that has nothing to do with the mapping
    being broken. Row-equality is the strongest assertion that is still
    actually true of this contract."""
    cards = _candidates_with_real_ties()
    run = _bare_run()
    base_request = _select_request(run, cards)
    base_env = _env_with(run, base_request)
    base_mask = base_env.action_masks()

    row_by_action = {}
    for i in range(MAX_SELECT_CANDIDATES):
        action = SELECT_BASE + i
        if not base_mask[action]:
            continue
        idx = base_env._translate(action, base_request)
        row_by_action[action] = _run_card_row(cards[idx])

    for seed in (1, 2, 3):
        shuffled = list(cards)
        random.Random(seed).shuffle(shuffled)
        req = _select_request(run, shuffled)
        env = _env_with(run, req)
        mask = env.action_masks()
        np.testing.assert_array_equal(mask, base_mask)
        for action, expected_row in row_by_action.items():
            idx = env._translate(action, req)
            assert _run_card_row(shuffled[idx]) == expected_row, (
                f"action {action} must select a card with the SAME row "
                "signature after shuffling, even if a tie means it's a "
                "different (but interchangeable) object"
            )


# ── 5. Skip ──────────────────────────────────────────────────────────────


def test_skip_present_iff_skippable():
    cards = [make_card("strike")]
    run = _bare_run()

    skip_request = _select_request(run, cards, skippable=True)
    skip_env = _env_with(run, skip_request)
    mask = skip_env.action_masks()
    assert mask[CHOICE_BASE]
    assert skip_env._translate(CHOICE_BASE, skip_request) == len(cards)

    no_skip_request = _select_request(run, cards, skippable=False)
    no_skip_env = _env_with(run, no_skip_request)
    mask2 = no_skip_env.action_masks()
    assert not mask2[CHOICE_BASE]
    assert no_skip_env._translate(CHOICE_BASE, no_skip_request) is None


# ── 6. Overflow ──────────────────────────────────────────────────────────


def test_overflow_masks_exactly_the_cap_and_never_raises():
    cards = _heterogeneous_candidates(MAX_SELECT_CANDIDATES + 20)
    run = _bare_run()
    request = _select_request(run, cards)
    env = _env_with(run, request)

    mask = env.action_masks()   # must not raise / assert
    assert mask.shape == (N_ACTIONS,)
    select_bits = mask[SELECT_BASE:SELECT_BASE + MAX_SELECT_CANDIDATES]
    assert int(select_bits.sum()) == MAX_SELECT_CANDIDATES
    assert mask.any()

    order = env._sorted_candidate_order(request)
    assert len(order) == MAX_SELECT_CANDIDATES

    # No `pytest.warns` here (deliberately, matching
    # test_run_obs_v4.py's `..._past_cap` test's own note): obs.py's
    # overflow warning is a one-time-per-process latch keyed on the segment
    # name, so asserting it fires HERE would make this test's outcome depend
    # on whether some other "select.candidates" overflow test already ran
    # first in the same process and already consumed the one-time warning.
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["f"][layout.f_slices["select.candidates.overflow"]][0] == pytest.approx(1.0)


# ── Task A: the potion-belt IndexError crash ────────────────────────────


def test_potion_belt_grown_past_the_old_cap_does_not_crash_action_masks():
    """Task A regression: a single COMMON relic (Potion Belt, +2 slots) on
    top of the base 3 already exceeds the pre-fix `MAX_POTION_SLOTS` (4).
    The reviewer reproduced an `IndexError` in `action_masks()` from exactly
    this shape (a 5-slot belt holding 5 AnyTime potions on a non-combat
    decision) — `mask[POTION_BASE + (answer - POTION_ACTION_BASE)]` indexed
    past the end of a mask sized `POTION_BASE + MAX_POTION_SLOTS`.
    `SELECT_OPTION` (rather than `MAP`) is the vehicle purely so the fixture
    doesn't also need a real map point — the belt-crossing behaviour under
    test is identical for every non-combat decision kind."""
    run = _bare_run()
    run.add_potion_slots(2)   # Potion Belt
    assert run.max_potions == 5
    for _ in range(5):
        assert run.add_potion(make_potion("blood_potion"))   # AnyTime usage
    assert all(p is not None for p in run.potions)

    request = DecisionRequest(kind=DecisionKind.SELECT_OPTION, run=run, n_options=2)
    env = _env_with(run, request)

    mask = env.action_masks()   # must not raise IndexError
    assert mask.shape == (N_ACTIONS,)
    for slot in range(5):
        assert mask[POTION_BASE + slot], f"slot {slot}'s AnyTime potion action must be legal"


def test_potion_belt_grown_past_the_new_cap_does_not_crash_action_masks():
    """Review item 2: Task A moved `MAX_POTION_SLOTS` from 4 to 10 (the true
    worst case) but did not touch the mechanism — `action_masks()`'s potion
    branch still writes one mask cell per ACTUAL belt slot
    `request.potion_actions()` yields, uncapped:

        for answer in request.potion_actions():
            mask[POTION_BASE + (answer - POTION_ACTION_BASE)] = True

    so an 11-slot belt (one slot past the new cap — `add_potion_slots(8)` on
    top of the base 3) reproduces the exact same class of `IndexError` the
    old 5-slot case did, just at a higher threshold. Twenty lines below, the
    SELECT branch already treats overflow as something to bound and signal
    (via the observation's `select.candidates.overflow`) rather than crash
    on; this pins the potion branch agreeing with that policy: no raise, and
    the mask still has something legal in it."""
    run = _bare_run()
    run.add_potion_slots(8)
    assert run.max_potions == MAX_POTION_SLOTS + 1 == 11
    for _ in range(11):
        assert run.add_potion(make_potion("blood_potion"))   # AnyTime usage
    assert all(p is not None for p in run.potions)

    request = DecisionRequest(kind=DecisionKind.SELECT_OPTION, run=run, n_options=2)
    env = _env_with(run, request)

    mask = env.action_masks()   # must not raise IndexError
    assert mask.shape == (N_ACTIONS,)
    assert mask.any()
    for slot in range(MAX_POTION_SLOTS):
        assert mask[POTION_BASE + slot], f"slot {slot}'s AnyTime potion action must be legal"


# ── Review item 3: the new potion boundary is pinned, not just witnessed ──


def test_max_potion_slots_is_base_plus_every_belt_growing_relic():
    """Review item 3: every existing potion-cap test (this file's own
    `test_potion_belt_grown_past_the_old_cap_...`,
    `test_any_time_potion_action.py:159`, both `test_combat_obs_v4.py`
    potion-overflow tests) is written *relative to* `MAX_POTION_SLOTS`
    itself, so all of them stay green even if that constant regresses — the
    reviewer demonstrated this directly: setting `MAX_POTION_ROWS = 6`
    leaves every one of those tests passing while a real Alchemical Coffer +
    Potion Belt run crashes exactly as before.

    Pin the DERIVATION instead, computed from the three belt-growing
    relics' own `POTION_SLOTS` class attributes and
    `PlayerCombatState.MAX_POTIONS` — not a bare literal 10, which would
    just move the magic number into this test — so this fails the moment
    `MAX_POTION_SLOTS` drifts from the true worst case again, regardless of
    what any other test asserts."""
    expected = (
        PlayerCombatState.MAX_POTIONS
        + PhialHolster.POTION_SLOTS
        + PotionBelt.POTION_SLOTS
        + AlchemicalCoffer.POTION_SLOTS
    )
    assert MAX_POTION_SLOTS == expected


def test_full_potion_belt_from_real_relics_end_to_end():
    """Review item 3's second half: exercise a REAL 10-slot belt — grown by
    the three actual belt-growing relics via `run.add_relic`, not a bare
    `add_potion_slots` numeric call — end to end: the `run.potions`
    observation rows, `action_masks`' potion bits, and `_translate`'s decode
    must all agree at the true worst-case cap."""
    run = _bare_run()
    run.add_relic("phial_holster")
    run.add_relic("potion_belt")
    run.add_relic("alchemical_coffer")
    assert run.max_potions == MAX_POTION_SLOTS == 10

    # Force every slot to hold a known AnyTime potion, deterministic
    # regardless of what the relics' own random-fill pickup effects left.
    for slot in range(run.max_potions):
        run.potions[slot] = make_potion("blood_potion")

    request = DecisionRequest(kind=DecisionKind.SELECT_OPTION, run=run, n_options=2)
    env = _env_with(run, request)

    obs = env._build_obs()
    layout = run_obs_layout()
    pids = obs["i"][layout.i_slices["run.potions.ids"]]
    assert len(pids) == MAX_POTION_SLOTS
    assert all(int(pid) != PAD for pid in pids), (
        "every one of the 10 real belt-grown slots must be an observed row"
    )

    mask = env.action_masks()
    for slot in range(MAX_POTION_SLOTS):
        assert mask[POTION_BASE + slot], f"slot {slot} must be a legal potion action"
        assert env._translate(POTION_BASE + slot, request) == POTION_ACTION_BASE + slot
