"""Acceptance tests for the v7 run observation (OBS_SCHEMA.md; T5a of
OBS_SCHEMA.md).

Written BEFORE run_env.py's v7 rewrite (TDD) — every test here was confirmed
RED against the v6 (flat-Box) tree before a single line of the new encoder
was written (the whole module failed to even import, since T4's full_env.py
rewrite removed the flat-obs helpers v6's run_env.py depended on).

Style mirrors test/test_combat_obs_v4.py: build state directly (a bare
``RunState``, a hand-built ``DecisionRequest``), read the facts straight off
it, decode the observation, and assert the two agree — never just "shape
didn't change". Most tests bypass the greenlet/driver entirely: construct an
``STS2RunEnv``, surgically set ``env._run`` / ``env._request``, and call
``env._build_obs()`` directly — the same "surgery" pattern
test_combat_obs_v4.py uses for otherwise-unreachable states (e.g. a power
instance with amount exactly 0).
"""
from __future__ import annotations

import random
import warnings
from pathlib import Path

import numpy as np
import pytest

from sts2_rl import (
    RunState,
    make_card,
    make_potion,
    make_relic,
)
from sts2_rl.afflictions import RingingAffliction
from sts2_rl.cmds import CardCmd
from sts2_rl.enchantments import make_enchantment
from sts2_rl.driver import DecisionKind, DecisionRequest
from sts2_rl.full_env import (
    CARD_INDEX,
    MAX_OBS_ID as COMBAT_MAX_OBS_ID,
    MAX_POTION_ROWS,
    MAX_RELIC_ROWS,
    MONSTER_INDEX,
    POTION_INDEX,
    RELIC_INDEX,
    combat_obs_layout,
    combat_obs_segments_f,
    combat_obs_segments_i,
    build_combat_obs,
)
from sts2_rl.relic_obs import EXCLUDED_RELIC_STATE
from sts2_rl.rewards import CombatRewards
from sts2_rl.rooms import RoomType
from sts2_rl.run_env import (
    DECK_OVERFLOW_LOG_ENV,
    GOLD_LOG_COARSE_DENOM,
    GOLD_LOG_FINE_DENOM,
    MAX_BOSS_IDS,
    MAX_DECK_ROWS,
    MAX_POTION_SLOTS,
    MAX_SELECT_CANDIDATES,
    RUN_OBS_SCHEMA_VERSION,
    SHOP_CARD_SLOTS,
    SHOP_COST_LOG_DENOM,
    SHOP_POTION_SLOTS,
    SHOP_RELIC_SLOTS,
    REWARD_CARD_SLOTS,
    STS2RunEnv,
    PURPOSE_INDEX,
    EVENT_INDEX,
    _log1p_scale,
    _run_card_row,
    deck_overflow_log_path,
    run_obs_layout,
    run_obs_segments_f,
    run_obs_segments_i,
)
from sts2_rl.shop import MerchantInventory


# ── Fixtures / helpers ───────────────────────────────────────────────────

_HETEROGENEOUS_CARD_IDS = ["strike", "defend", "bash", "pommel_strike"]


def _heterogeneous_cards(n: int) -> list:
    """``n`` cards spanning several ids and upgrade levels, with at least one
    afflicted, one enchanted and one ``exhaust_on_next_play`` card whenever
    ``n`` is large enough — so a sort/shuffle test actually has heterogeneous
    input to discriminate (mirrors test_combat_obs_v4.py's
    ``_heterogeneous_pile``, which review flagged as the shape every
    non-leak test here must copy, not the vacuous "N identical Strikes"
    shape review found in the prior lane)."""
    cards = []
    for i in range(n):
        c = make_card(_HETEROGENEOUS_CARD_IDS[i % len(_HETEROGENEOUS_CARD_IDS)])
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


def _bare_run(**kwargs) -> RunState:
    """A RunState with no map/act rolled — fine for every block except
    run.boss / map / event-through-a-room, which need `start_run`."""
    return RunState(rng=random.Random(0), **kwargs)


def _env_with(run: RunState, request: DecisionRequest | None = None) -> STS2RunEnv:
    """An STS2RunEnv wired directly to `run`/`request`, bypassing the
    greenlet/driver — the same "surgery" pattern test_combat_obs_v4.py uses
    to reach otherwise-unreachable states. `_build_obs` only reads
    `self._run`/`self._request`/`self._map_grid_cache` (already None from
    __init__), so this is safe without ever calling reset()."""
    env = STS2RunEnv()
    env._run = run
    env._request = request
    return env


class _FakeOption:
    """A minimal EventOption-shaped double: `_build_obs` reads `.locked` and the
    four `.*_id` preview fields, and `events.base.EventOption.locked` is itself just
    `on_chosen is None` — this is the identical contract without needing a
    real registered Event's preconditions."""

    def __init__(self, locked: bool, card_id=None, relic_id=None,
                 relic_traded_id=None, potion_id=None) -> None:
        self.locked = locked
        self.card_id = card_id
        self.relic_id = relic_id
        self.relic_traded_id = relic_traded_id
        self.potion_id = potion_id


class _FakeEvent:
    """A minimal Event-shaped double (`_build_obs` reads only `.id`, `.page`,
    `.options`) — used so the event-block test doesn't depend on any real
    event's preconditions/RNG draws, exactly like test_combat_obs_v4.py's
    `probes.probe_dummy` stands in for a real Monster."""

    def __init__(self, id_: str, page: str, options: list) -> None:
        self.id = id_
        self.page = page
        self.options = options


def _select_request(run: RunState, candidates: list, *, purpose="from_draw",
                     skippable=False, count_remaining=1) -> DecisionRequest:
    return DecisionRequest(
        kind=DecisionKind.SELECT_CARDS, run=run, purpose=purpose,
        candidates=list(candidates), count_remaining=count_remaining,
        skippable=skippable,
    )


# ── 1. Layout self-consistency ───────────────────────────────────────────


def test_layout_self_consistency():
    layout = run_obs_layout()
    assert sum(w for _, w in run_obs_segments_f()) + sum(
        w for _, w in combat_obs_segments_f()) == layout.f_dim
    assert sum(w for _, w in run_obs_segments_i()) + sum(
        w for _, w in combat_obs_segments_i()) == layout.i_dim

    env = STS2RunEnv()
    space = env.observation_space
    assert space["f"].shape == (layout.f_dim,)
    assert space["i"].shape == (layout.i_dim,)
    assert space["f"].dtype == np.float32
    assert space["i"].dtype == np.int32

    obs, info = env.reset(seed=0)
    assert obs["f"].shape == (layout.f_dim,)
    assert obs["i"].shape == (layout.i_dim,)
    assert obs["f"].dtype == np.float32
    assert obs["i"].dtype == np.int32
    assert np.all(obs["f"] >= 0.0) and np.all(obs["f"] <= 1.0)
    assert np.all(obs["i"] >= 0) and np.all(obs["i"] <= space["i"].high[0])

    mask = env.action_masks()
    action = int(np.flatnonzero(mask)[0])
    obs2, *_ = env.step(action)
    assert np.all(obs2["f"] >= 0.0) and np.all(obs2["f"] <= 1.0)
    assert np.all(obs2["i"] >= 0) and np.all(obs2["i"] <= space["i"].high[0])


def test_run_max_obs_id_matches_combat_and_is_reported_not_assumed():
    """T5a brief §1: run_env's MAX_OBS_ID is computed independently of
    full_env's (the run observation touches events/purposes too) — this
    pins that they land on the SAME number (cards' capacity, 640 dominates
    both sets) rather than asserting that identity was a given."""
    from sts2_rl.run_env import MAX_OBS_ID as RUN_MAX_OBS_ID

    assert RUN_MAX_OBS_ID == COMBAT_MAX_OBS_ID == 640


def test_schema_version_is_13():
    """v9 (R3, 2026-08-02): the run observation embeds the combat block
    verbatim, so full_env's v6 bump (per-enemy intent history — new
    `enemy{e}.intent_history.f` segments) silently widened this env's f_dim
    too; this constant has to move whenever the embedded contract does, even
    when nothing in run_env.py's own layout code changed. Same defect shape
    as the v7->v8 bump (StatusIntent's card-count float) — bumped in the SAME
    change this time. See test_run_schema_version_matches_declared_dims
    below, which pins the (version, f_dim, i_dim) triple together so this
    can't recur silently.

    v10 (SpireBot schema audit, Task 4, 2026-08-04): pure version bump —
    the audit found zero DROP rows and no field additions in run v9 (nor in
    the embedded combat block's v6->v7 bump), so f_dim/i_dim are UNCHANGED
    from v9. See `test/test_obs_game_observable.py` for the audit's
    REDEFINE-row disposition (`phase`, `select.purpose.ids` — both
    documentation-only, no sim-code consequence).

    v11 (2026-08-07): `REWARD_CARD_SLOTS` 3 -> 4. Lasting Candy's appended
    Power option was being truncated out of an observation whose action stayed
    legal to pick, and the count also moves where SKIP sits in the mask — see
    the constant's comment in run_env.py and
    `test_reward_cards_block_shows_a_four_card_lasting_candy_offer`.

    v12 (task 3, v14 mechanics-exposure): follows full_env.OBS_SCHEMA_VERSION
    7 -> 8 in lockstep — the embedded combat hand.f block grew by 2 fields
    per hand row (f[29] glow_gold, f[30] block_preview_move).

    v13 (2026-08-26): new int block `event.options.cards.ids` — the card an event
    option previews, positionally aligned with `event.options`. The event block
    carried only (present, locked) per option, so nothing card-dependent could
    be learned: Slippery Bridge names the exact card it removes and the policy
    took that option at high probability whether the card was a Strike or its
    best pick. i_dim only (CHOICE_SLOTS ids); f_dim unchanged."""
    assert RUN_OBS_SCHEMA_VERSION == 13


def test_run_schema_version_matches_declared_dims():
    """Mechanical guard against the exact defect this project shipped once
    already (v7->v8): `full_env.OBS_SCHEMA_VERSION` moving widens `f_dim`
    HERE too, because this env splices `full_env`'s combat block into its
    own observation verbatim (`write_combat_obs(..., prefix="combat.")`) —
    so `RUN_OBS_SCHEMA_VERSION` has to move in the SAME change, not be
    discovered later, or "schema N" briefly names two different
    `(f_dim, i_dim)` contracts (an old checkpoint's and the live env's).

    Pins the version and BOTH widths as one triple, measured off the real
    layout rather than typed twice. Widening any embedded block — a new
    field in this module's own segments, or a change to full_env's combat
    block that rides in under the "combat." prefix — moves `f_dim`/`i_dim`
    while this literal stays put, so the test goes red; the only fix is to
    edit this pin AND bump `RUN_OBS_SCHEMA_VERSION` in the same change,
    which is exactly the deliberate, can't-miss-it coupling a schema-version
    gate exists to produce. Mutation-checked (run-schema-bump report,
    scratchpad): widening `full_env`'s `enemies.f` row by one more float
    without touching `RUN_OBS_SCHEMA_VERSION` turns this red."""
    layout = run_obs_layout()
    # v10 -> v11: `REWARD_CARD_SLOTS` 3 -> 4 adds one 4-wide row to EACH half
    # of `reward.cards` (4711 -> 4715, 1465 -> 1469). The preceding v10
    # amendment (+1/+1 for `reward.relic.f`/`reward.relic.ids`) is folded into
    # the 4711/1465 baseline these numbers move from.
    # v11 -> v12: full_env's hand.f row grows by 2 fields (f[29] glow_gold,
    # f[30] block_preview_move); MAX_HAND (10) x 2 = +20 f_dim, i_dim
    # unchanged (no new id columns): 4715 -> 4735, 1469 stays 1469.
    # v12 -> v13: `event.options.cards.ids` adds four 16-wide id blocks (cards,
    # relics, relics_traded, potions) on the INT half only — 1469 -> 1533; f_dim untouched at 4735.
    # v13: event.options.ids + run.ascension (v24 fold). run.ascension adds a
    # 1-wide float segment: 4735 -> 4736; i_dim unchanged at 1533.
    assert (RUN_OBS_SCHEMA_VERSION, layout.f_dim, layout.i_dim) == (13, 4736, 1533)

    # STS2CurriculumRunEnv is STS2RunEnv with a different map/reward factory
    # only (curriculum_env.py's own docstring) — same layout, same version.
    from sts2_rl.curriculum_env import STS2CurriculumRunEnv

    curriculum_env = STS2CurriculumRunEnv()
    curriculum_space = curriculum_env.observation_space
    assert curriculum_space["f"].shape == (layout.f_dim,)
    assert curriculum_space["i"].shape == (layout.i_dim,)


# ── 2. The combat block is spliced correctly ─────────────────────────────


def test_combat_block_is_pad_zero_outside_combat():
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    for name, _w in combat_obs_segments_i():
        sl = layout.i_slices[f"combat.{name}"]
        assert np.all(obs["i"][sl] == 0), f"combat.{name} not PAD outside combat"
    for name, _w in combat_obs_segments_f():
        sl = layout.f_slices[f"combat.{name}"]
        assert np.all(obs["f"][sl] == 0.0), f"combat.{name} not zero outside combat"


def test_combat_block_matches_build_combat_obs_when_live():
    run = _bare_run(deck=[make_card("strike") for _ in range(5)] + [make_card("defend") for _ in range(4)])
    from sts2_rl.monsters import INKLETS_NORMAL

    combat = run.create_combat(INKLETS_NORMAL, room_type=RoomType.MONSTER)
    env = _env_with(run, DecisionRequest(kind=DecisionKind.COMBAT, run=run, combat=combat))
    obs = env._build_obs()
    layout = run_obs_layout()
    plain = build_combat_obs(combat)

    for name, _w in combat_obs_segments_i():
        sl = layout.i_slices[f"combat.{name}"]
        clayout = combat_obs_layout()
        np.testing.assert_array_equal(obs["i"][sl], plain["i"][clayout.i_slices[name]])
    for name, _w in combat_obs_segments_f():
        sl = layout.f_slices[f"combat.{name}"]
        clayout = combat_obs_layout()
        np.testing.assert_array_equal(obs["f"][sl], plain["f"][clayout.f_slices[name]])


# ── 3. Content: deck multiset (R2) ────────────────────────────────────────


def test_deck_block_is_exact_multiset_with_r2_fields():
    deck = _heterogeneous_cards(6)
    run = _bare_run(deck=list(deck))
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.deck.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["run.deck.f"]].reshape(-1, 4)

    expected_ints = sorted(tuple(_run_card_row(c)[0]) for c in deck)
    got_ints = sorted(tuple(int(x) for x in row) for row in ids if row[0] != 0 or row[1] != 0)
    assert got_ints == expected_ints
    # Hygiene fix (review item 5): `fs` used to be bound and never asserted
    # on — the test's own name promises "with r2 fields", but nothing
    # checked the float half at all. Round-trip the float multiset too, the
    # same way the int multiset is checked above.
    expected_floats = sorted(
        tuple(round(v, 6) for v in _run_card_row(c)[1]) for c in deck)
    got_floats = sorted(
        tuple(round(float(x), 6) for x in frow)
        for irow, frow in zip(ids, fs) if irow[0] != 0 or irow[1] != 0)
    assert got_floats == expected_floats
    # pile_id is always PAD (0) for a run-side block — no pile concept exists
    # outside combat.
    for row in ids:
        if row[1] != 0:
            assert row[0] == 0, "run.deck pile_id must be PAD, never a real pile id"
    n_present = sum(1 for row in ids if row[1] != 0)
    assert n_present == len(deck)


# ── 4. Content: relics (R1) + in-combat gating ────────────────────────────


def test_relics_block_shows_relic_row_counters():
    girya = make_relic("girya")
    girya.times_lifted = 3
    lava = make_relic("lava_rock")
    lava.has_triggered = True
    run = _bare_run(relics=[girya, lava])
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.relics.ids"]]
    fs = obs["f"][layout.f_slices["run.relics.f"]].reshape(-1, 2)

    # Acquisition order (sort=False): girya at row 0, lava_rock at row 1.
    assert ids[0] == RELIC_INDEX["girya"] + 1
    assert fs[0][0] == pytest.approx(3 / 10.0)
    assert fs[0][1] == pytest.approx(0.0)
    assert ids[1] == RELIC_INDEX["lava_rock"] + 1
    assert fs[1][0] == pytest.approx(0.0)
    assert fs[1][1] == pytest.approx(1.0)


def test_relic_in_combat_only_counter_reads_zero_in_run_block():
    """R1 in-combat gating (test 5): get the fact from a real relic via
    relic_obs (kunai is one of the 10 in `_IN_COMBAT_ONLY_COUNTERS`), not by
    re-asserting the rule ourselves."""
    kunai = make_relic("kunai")
    kunai._attacks_this_turn = 2   # would show 2 % 3 = 2 IN combat
    run = _bare_run(relics=[kunai])
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    fs = obs["f"][layout.f_slices["run.relics.f"]].reshape(-1, 2)
    assert fs[0][0] == pytest.approx(0.0), "an in-combat-only counter must read 0 out of combat"


@pytest.mark.parametrize("relic_id", sorted(EXCLUDED_RELIC_STATE))
def test_excluded_relic_state_never_leaks_into_run_observation(relic_id):
    """R1 non-leak (test 6), run-side: unlike the combat version, NO relic
    here is exempted to a row-only check — there is no live combat for a
    damage/block hook to route beating_remnant/vambrace's excluded state
    into another field through, so the WHOLE observation must be unaffected
    by every excluded attribute."""

    def _mutate(value):
        if isinstance(value, bool):
            return not value
        if isinstance(value, int):
            return value + 1_000_000
        if isinstance(value, float):
            return value + 1_000_000.0
        if isinstance(value, str):
            return value + "_mutated_probe"
        if isinstance(value, list):
            return value + ["mutated_probe"]
        if isinstance(value, tuple):
            return value + ("mutated_probe",)
        if isinstance(value, dict):
            d = dict(value)
            d["mutated_probe"] = True
            return d
        return "mutated_probe"

    for attr in EXCLUDED_RELIC_STATE[relic_id]:
        relic = make_relic(relic_id)
        run = _bare_run(relics=[relic])
        env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
        before = env._build_obs()
        setattr(relic, attr, _mutate(getattr(relic, attr)))
        after = env._build_obs()
        np.testing.assert_array_equal(
            before["f"], after["f"], err_msg=f"{relic_id}.{attr} leaked into obs['f']")
        np.testing.assert_array_equal(
            before["i"], after["i"], err_msg=f"{relic_id}.{attr} leaked into obs['i']")


# ── 5. Content: potion belt by slot ───────────────────────────────────────


def test_potion_belt_by_slot_present_and_slot_exists_bits():
    potion = make_potion("fire_potion")
    run = _bare_run(potions=[None, potion, None])   # max_potions stays 3
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.potions.ids"]]
    fs = obs["f"][layout.f_slices["run.potions.f"]].reshape(-1, 2)

    assert ids[0] == 0 and fs[0][0] == 0.0 and fs[0][1] == 1.0     # empty, exists
    assert ids[1] == POTION_INDEX["fire_potion"] + 1
    assert fs[1][0] == 1.0 and fs[1][1] == 1.0                     # present, exists
    assert ids[2] == 0 and fs[2][0] == 0.0 and fs[2][1] == 1.0
    # Slot 3 doesn't exist on a 3-slot belt: PAD AND slot_exists == 0 — the
    # bit that distinguishes "empty but real slot" from "no such slot".
    assert ids[3] == 0 and fs[3][1] == 0.0


def test_potion_belt_grown_past_default_shows_new_slot_exists():
    """Task 0's whole point, from the run-observation side: a belt grown to
    4 slots (Phial Holster et al.) must show slot 3 as a REAL slot, not just
    an empty one."""
    run = _bare_run()
    run.add_potion_slots(1)
    assert run.max_potions == 4
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    fs = obs["f"][layout.f_slices["run.potions.f"]].reshape(-1, 2)
    assert fs[3][1] == 1.0, "slot 3 must read as an existing slot on a grown belt"


# ── 6. Content: act boss identity ─────────────────────────────────────────


def test_boss_ids_shows_every_monster_class_including_duplicates():
    run = RunState(rng=random.Random(0))
    run.start_run(acts=["overgrowth"])
    run.room_set.boss_key = "the_kin"     # KinFollower x2 + KinPriest — a
    # real duplicate-class boss (the max() the census in run_env.py cites).
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.boss.ids"]]

    expected = sorted([
        MONSTER_INDEX["KinFollower"] + 1,
        MONSTER_INDEX["KinFollower"] + 1,
        MONSTER_INDEX["KinPriest"] + 1,
    ])
    got = sorted(int(x) for x in ids if x != 0)
    assert got == expected
    assert len(got) == 3


# ── 7. Content: shop stock with prices ────────────────────────────────────


def test_shop_stock_ids_and_r6_prices():
    run = RunState(rng=random.Random(0))
    run.start_run(acts=["overgrowth"])
    inv = MerchantInventory.create(run)
    # Pin exact costs (bypassing the ±jitter) for a deterministic check.
    inv.character_card_entries[0]._cost = 173
    inv.relic_entries[0]._cost = 250
    inv.potion_entries[0]._cost = 60
    env = _env_with(run, DecisionRequest(kind=DecisionKind.SHOP, run=run, shop=inv))
    obs = env._build_obs()
    layout = run_obs_layout()

    card_ids = obs["i"][layout.i_slices["shop.cards.ids"]]
    card_f = obs["f"][layout.f_slices["shop.cards.f"]].reshape(-1, 4)
    entry0 = inv.character_card_entries[0]
    assert card_ids[0] == CARD_INDEX[entry0.card.id] + 1
    assert card_f[0][0] == pytest.approx(1.0)
    assert card_f[0][1] == pytest.approx(_log1p_scale(173, SHOP_COST_LOG_DENOM))
    assert card_f[0][2] == pytest.approx(1.0 if entry0.enough_gold else 0.0)

    relic_ids = obs["i"][layout.i_slices["shop.relics.ids"]]
    relic_f = obs["f"][layout.f_slices["shop.relics.f"]].reshape(-1, 3)
    r0 = inv.relic_entries[0]
    assert relic_ids[0] == RELIC_INDEX[r0.relic.id] + 1
    assert relic_f[0][1] == pytest.approx(_log1p_scale(250, SHOP_COST_LOG_DENOM))

    potion_ids = obs["i"][layout.i_slices["shop.potions.ids"]]
    potion_f = obs["f"][layout.f_slices["shop.potions.f"]].reshape(-1, 3)
    p0 = inv.potion_entries[0]
    assert potion_ids[0] == POTION_INDEX[p0.potion.id] + 1
    assert potion_f[0][1] == pytest.approx(_log1p_scale(60, SHOP_COST_LOG_DENOM))

    removal = inv.card_removal_entry
    removal._cost = 500
    obs2 = env._build_obs()
    rem_f = obs2["f"][layout.f_slices["shop.removal"]]
    assert rem_f[0] == pytest.approx(1.0)
    assert rem_f[1] == pytest.approx(_log1p_scale(500, SHOP_COST_LOG_DENOM))


# ── 8. Positional alignment ────────────────────────────────────────────────


def test_shop_unstocked_middle_slot_stays_at_its_own_index():
    run = RunState(rng=random.Random(0))
    run.start_run(acts=["overgrowth"])
    inv = MerchantInventory.create(run)
    assert len(inv.character_card_entries) >= 3
    before_ids = [e.card.id for e in inv.character_card_entries]
    inv.character_card_entries[2].card = None    # force slot 2 unstocked

    env = _env_with(run, DecisionRequest(kind=DecisionKind.SHOP, run=run, shop=inv))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["shop.cards.ids"]]
    f = obs["f"][layout.f_slices["shop.cards.f"]].reshape(-1, 4)

    assert ids[2] == 0 and f[2][0] == 0.0, "an unstocked slot must be an explicit PAD row"
    # Every OTHER slot keeps its own identity at its own index — nothing
    # slid down to fill the gap.
    for c in range(SHOP_CARD_SLOTS):
        if c == 2 or c >= len(before_ids):
            continue
        assert ids[c] == CARD_INDEX[before_ids[c]] + 1, f"slot {c} shifted"


def test_potion_belt_empty_slot_stays_at_its_own_index():
    potion = make_potion("fire_potion")
    run = _bare_run(potions=[None, None, potion])
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.potions.ids"]]
    assert ids[0] == 0 and ids[1] == 0
    assert ids[2] == POTION_INDEX["fire_potion"] + 1


# ── 9. Reward screen ────────────────────────────────────────────────────


def test_reward_cards_block_shows_all_three_with_r2_fields():
    cards = _heterogeneous_cards(3)
    rewards = CombatRewards(room_type=RoomType.MONSTER)
    rewards.cards = list(cards)
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["reward.cards.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["reward.cards.f"]].reshape(-1, 4)

    for c, card in enumerate(cards):
        assert ids[c][0] == 0, "reward pile_id must be PAD"
        assert ids[c][1] == CARD_INDEX[card.id] + 1
    assert fs[0][2] == pytest.approx(1 / 10.0)   # cards[0] afflicted amount 1


def test_reward_cards_block_shows_a_four_card_lasting_candy_offer():
    """A live screen can be 4 wide, not 3: Lasting Candy APPENDS one Power
    option to a post-encounter offer (`cards.extend(added)`,
    relics/lasting_candy.py). At the old cap of 3 the fourth card was
    truncated out of the observation while `legal_actions` still offered it —
    and skip moved from index 3 to index 4 underneath a policy that had no way
    to see why. Every slot must be present and carry its own id."""
    cards = _heterogeneous_cards(4)
    rewards = CombatRewards(room_type=RoomType.MONSTER)
    rewards.cards = list(cards)
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["reward.cards.ids"]].reshape(-1, 4)

    assert ids.shape[0] == REWARD_CARD_SLOTS >= 4
    for c, card in enumerate(cards):
        assert ids[c][1] == CARD_INDEX[card.id] + 1, (
            f"reward slot {c} lost its card — the block truncated a live offer")


def test_reward_card_slots_cover_every_option_appending_relic():
    """Canary on the cap's ONE assumption: `CARD_REWARD_COUNT` base options
    plus at most one appended by a relic.

    `Hook.TryModifyCardRewardOptions`' early (non-Late) pass is the seam a
    relic appends through, and Lasting Candy is the game's only implementer of
    it (LastingCandy.cs; see `create_reward_cards`' two-pass comment). If a
    second one is ever ported, the reward block may need to be wider than
    `CARD_REWARD_COUNT + 1` — fail here rather than silently truncating a live
    screen again."""
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.relics.base import Relic
    from sts2_rl.rewards import CARD_REWARD_COUNT

    appenders = sorted(
        rid for rid, cls in ALL_RELICS.items()
        if cls.modify_card_reward_options is not Relic.modify_card_reward_options
    )
    assert appenders == ["lasting_candy"], (
        f"new early-pass card-reward modifier(s) {appenders} — re-check how "
        f"many options they add and whether REWARD_CARD_SLOTS still covers it")
    assert REWARD_CARD_SLOTS >= CARD_REWARD_COUNT + 1


def test_reward_potion_block():
    potion = make_potion("fire_potion")
    rewards = CombatRewards(room_type=RoomType.MONSTER)
    rewards.potion = potion
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.REWARD_POTION, run=run, rewards=rewards, potion=potion))
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["i"][layout.i_slices["reward.potion.ids"]][0] == POTION_INDEX["fire_potion"] + 1
    assert obs["f"][layout.f_slices["reward.potion.f"]][0] == pytest.approx(1.0)


def test_reward_potion_block_visible_on_the_card_ask_too():
    """Game-parity fix: `unseeded_20260807_005254/decisions.jsonl` floor 2
    shows `reward.potion.f == 1` already on decision_index 0 (the card ask),
    one screen before the dedicated `REWARD_POTION` ask that used to be the
    only place this obs block lit up (`sim_89U.jsonl` had it backwards: 0
    then 1). The real screen shows every item still on offer — card, potion,
    relic — on EVERY reward decision of that floor, not just the ask whose
    own sub-kind matches the item. `CombatRewards` already models this: the
    card ask's `rewards` object (when there is exactly one card group, no
    Prayer-Wheel-style second group) IS the same object the potion ask later
    reads `.potion` off of, so populating `reward.potion.*` from `rewards`
    regardless of `request.kind` — instead of gating on
    `kind == REWARD_POTION` — is a same-data, wider-visibility fix, not a
    new data source."""
    cards = _heterogeneous_cards(2)
    potion = make_potion("fire_potion")
    rewards = CombatRewards(room_type=RoomType.MONSTER)
    rewards.cards = list(cards)
    rewards.potions = [potion]
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards))
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["i"][layout.i_slices["reward.potion.ids"]][0] == POTION_INDEX["fire_potion"] + 1
    assert obs["f"][layout.f_slices["reward.potion.f"]][0] == pytest.approx(1.0)


def test_reward_potion_block_absent_when_no_potion_on_offer():
    """No regression: a card-only reward screen must not fabricate a potion
    presence flag."""
    cards = _heterogeneous_cards(2)
    rewards = CombatRewards(room_type=RoomType.MONSTER)
    rewards.cards = list(cards)
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards))
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["i"][layout.i_slices["reward.potion.ids"]][0] == 0
    assert obs["f"][layout.f_slices["reward.potion.f"]][0] == pytest.approx(0.0)


def test_reward_relic_block():
    """Task B: DecisionKind.REWARD_RELIC's offered relic identity — width-1,
    mirroring `reward.potion` exactly (`RunState.offer_relic` always offers
    exactly one relic at a time, take-or-skip)."""
    relic = make_relic("kunai")
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.REWARD_RELIC, run=run, relic=relic))
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["i"][layout.i_slices["reward.relic.ids"]][0] == RELIC_INDEX["kunai"] + 1
    assert obs["f"][layout.f_slices["reward.relic.f"]][0] == pytest.approx(1.0)


def test_reward_relic_block_absent_outside_reward_relic_screen():
    """Zero-fill guarantee: a relic on `run.relics` (already owned) must not
    leak into `reward.relic.*` on an unrelated screen (§ task brief 3)."""
    relic = make_relic("kunai")
    run = _bare_run(relics=[relic])
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["i"][layout.i_slices["reward.relic.ids"]][0] == 0
    assert obs["f"][layout.f_slices["reward.relic.f"]][0] == pytest.approx(0.0)


# ── 10. Event identity ─────────────────────────────────────────────────────


def test_event_identity_and_options():
    event = _FakeEvent(
        "neow", "INITIAL",
        [_FakeOption(False), _FakeOption(True), _FakeOption(False)],
    )
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.EVENT, run=run, event=event))
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["f"][layout.f_slices["event.present"]][0] == pytest.approx(1.0)
    assert obs["i"][layout.i_slices["event.ids"]][0] == EVENT_INDEX["neow"] + 1
    opt = obs["f"][layout.f_slices["event.options"]]
    assert opt[0] == 1.0 and opt[1] == 0.0     # option 0: present, unlocked
    assert opt[2] == 1.0 and opt[3] == 1.0     # option 1: present, locked
    # No option previews a card here, so the whole id block stays PAD.
    assert not obs["i"][layout.i_slices["event.options.cards.ids"]].any()


def test_event_option_card_lands_in_the_matching_slot():
    """v13: an option that previews a specific card (the source's per-option
    `HoverTipFactory.FromCard` tip) exposes that card's vocab id, positionally
    aligned with `event.options`. Slippery Bridge is the motivating case: it
    names the exact card it would remove, and before this the policy saw only
    (present, locked) and could not tell a Strike from its best pick."""
    from sts2_rl.obs import oid

    event = _FakeEvent(
        "slippery_bridge", "INITIAL",
        [_FakeOption(False, card_id="bludgeon"), _FakeOption(False)],
    )
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.EVENT, run=run, event=event))
    ids = env._build_obs()["i"][run_obs_layout().i_slices["event.options.cards.ids"]]

    assert ids[0] == oid(CARD_INDEX["bludgeon"])   # OVERCOME previews the card
    assert ids[1] == 0                             # HOLD_ON previews none
    assert not ids[2:].any()                       # unused slots stay PAD


def test_event_option_relic_and_potion_previews_land_in_their_own_slices():
    """v13: the relic/potion halves of the option-preview block. Asserted
    together so a writer that filled the right VALUE into the wrong SLICE --
    relics vs relics_traded is the easy one to transpose, and they share the
    `relics` vocab so the ids would look plausible either way -- fails here."""
    from sts2_rl.obs import oid

    event = _FakeEvent(
        "relic_trader", "INITIAL",
        [_FakeOption(False, relic_id="kunai", relic_traded_id="anchor"),
         _FakeOption(False, potion_id="fire_potion")],
    )
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.EVENT, run=run, event=event))
    i = env._build_obs()["i"]
    layout = run_obs_layout()
    relics = i[layout.i_slices["event.options.relics.ids"]]
    traded = i[layout.i_slices["event.options.relics_traded.ids"]]
    potions = i[layout.i_slices["event.options.potions.ids"]]

    assert relics[0] == oid(RELIC_INDEX["kunai"])
    assert traded[0] == oid(RELIC_INDEX["anchor"])
    assert potions[1] == oid(POTION_INDEX["fire_potion"])

    # No bleed between slices or between option slots.
    assert relics[1] == 0 and traded[1] == 0 and potions[0] == 0
    assert not relics[2:].any() and not traded[2:].any() and not potions[2:].any()
    # The card slice stays PAD: no option here previews a card.
    assert not i[layout.i_slices["event.options.cards.ids"]].any()


def test_event_option_cards_are_absent_outside_an_event():
    """Zero-fill guarantee, matching the reward/shop blocks: the option-card
    ids must not survive onto an unrelated screen."""
    run = _bare_run()
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    ids = env._build_obs()["i"][run_obs_layout().i_slices["event.options.cards.ids"]]
    assert not ids.any()


def test_select_purpose_fallback_routes_to_the_real_unknown_bucket():
    """Bug fix pinned: an unrecognized purpose string must land on
    PURPOSE_INDEX["_unknown"] (whatever index the persisted vocab.json gives
    it — NOT necessarily the last one), not on the dead capacity-tail slot
    the pre-v7 one-hot's fallback (`N_PURPOSES - 1`) silently used."""
    run = _bare_run()
    request = _select_request(run, [make_card("strike")], purpose="totally_unrecognized_purpose_xyz")
    env = _env_with(run, request)
    obs = env._build_obs()
    layout = run_obs_layout()
    purpose_id = obs["i"][layout.i_slices["select.purpose.ids"]][0]
    assert purpose_id == PURPOSE_INDEX["_unknown"] + 1


# ── 11. R6 — log1p collisions + monotonicity ───────────────────────────────


def test_gold_1000_vs_1500_no_longer_collide():
    run1000 = _bare_run(gold=1000)
    run1500 = _bare_run(gold=1500)
    env = _env_with(run1000, DecisionRequest(kind=DecisionKind.MAP, run=run1000, points=[]))
    obs1000 = env._build_obs()
    env._run = run1500
    obs1500 = env._build_obs()
    layout = run_obs_layout()
    g1000 = obs1000["f"][layout.f_slices["run.gold"]]
    g1500 = obs1500["f"][layout.f_slices["run.gold"]]
    assert not np.array_equal(g1000, g1500), "1000g and 1500g must no longer collide (R6)"


def test_gold_encoding_is_monotonic():
    values = [0, 50, 300, 1000, 1500, 3000, 5000]
    fine = [_log1p_scale(v, GOLD_LOG_FINE_DENOM) for v in values]
    coarse = [_log1p_scale(v, GOLD_LOG_COARSE_DENOM) for v in values]
    assert fine == sorted(fine)
    assert coarse == sorted(coarse)
    assert all(0.0 <= x <= 1.0 for x in fine + coarse)


def test_removal_cost_500_vs_800_no_longer_collide():
    run = RunState(rng=random.Random(0))
    run.start_run(acts=["overgrowth"])
    inv = MerchantInventory.create(run)
    env = _env_with(run, DecisionRequest(kind=DecisionKind.SHOP, run=run, shop=inv))
    layout = run_obs_layout()

    inv.card_removal_entry._cost = 500
    obs500 = env._build_obs()
    inv.card_removal_entry._cost = 800
    obs800 = env._build_obs()
    r500 = obs500["f"][layout.f_slices["shop.removal"]]
    r800 = obs800["f"][layout.f_slices["shop.removal"]]
    assert not np.array_equal(r500, r800), "500g and 800g removal must no longer collide (R6)"


def test_shop_cost_encoding_is_monotonic():
    values = [0, 50, 175, 320, 500, 800, 2000]
    scaled = [_log1p_scale(v, SHOP_COST_LOG_DENOM) for v in values]
    assert scaled == sorted(scaled)
    assert all(0.0 <= x <= 1.0 for x in scaled)


def test_gold_realistic_band_resolves_without_plateau():
    """Review finding (item 2): the collision tests above only check TWO
    named points; the reviewer showed the fine channel actually SATURATES
    at its own denom (300, 500, 1000, 1500 and 3000 all used to read
    exactly 1.0 on the fine channel alone) — a fine channel that saturates
    that early has moved R6's original defect (`gold/100` saturating).
    This pins the real fix: the fine channel must no longer saturate at
    the bottom of a normally-shopping player's range, AND the coarse
    channel must resolve the WHOLE realistic band (0..3000g, the comment's
    own 'a few thousand, from a hoarding run' ceiling) with no interior
    plateau and no saturation at the top — headroom for a run that goes
    further still."""
    band = [0, 50, 150, 300, 500, 800, 1200, 1800, 2500, 3000]
    fine = [_log1p_scale(v, GOLD_LOG_FINE_DENOM) for v in band]
    coarse = [_log1p_scale(v, GOLD_LOG_COARSE_DENOM) for v in band]

    assert fine[band.index(300)] < 1.0, (
        "the fine gold channel must no longer saturate at 300g "
        "(the specific defect the review measured)"
    )
    assert all(a < b for a, b in zip(coarse, coarse[1:])), (
        f"coarse gold channel must be strictly increasing across the "
        f"realistic band with no plateau, got {coarse}"
    )
    assert coarse[-1] < 1.0, (
        "coarse gold channel must not saturate inside the realistic band "
        f"(0..3000g), got {coarse[-1]}"
    )
    vectors = list(zip(fine, coarse))
    assert len(set(vectors)) == len(vectors), f"gold (fine, coarse) collisions in {vectors}"


def test_shop_cost_realistic_band_spreads_more_than_the_old_defect():
    """Review finding (item 2): the reviewer measured the pre-fix shared
    shop/removal denom (2000) giving only 27% spread across the realistic
    item-price band (40-320g: card/relic/potion slot costs), all bunched
    in the upper half of [0,1] — the comment claimed this 'resolves the
    shopping-relevant range', which was not true. A single log1p denom
    cannot spread an ~8x price ratio across all of [0,1] while ALSO
    keeping the unbounded removal cost (75 + 25*removals_used) resolvable
    well past the 500-vs-800g pair the existing collision test targets —
    that is a hard mathematical tradeoff of sharing one denom, not a
    tuning mistake — but the shared denom can still do meaningfully better
    than 27% while keeping 800g comfortably short of saturation."""
    price_band = [40, 50, 100, 175, 250, 320]
    scaled = [_log1p_scale(v, SHOP_COST_LOG_DENOM) for v in price_band]
    assert all(a < b for a, b in zip(scaled, scaled[1:]))
    spread = max(scaled) - min(scaled)
    assert spread > 0.29, (
        f"realistic price-band spread only {spread:.3f}; the pre-fix "
        f"defect measured 0.271 — this must be a real improvement, not "
        f"a rounding difference"
    )
    # The unbounded removal cost must stay resolvable well past the named
    # collision pair, with headroom (not pinned to the ceiling at 800g).
    assert _log1p_scale(800, SHOP_COST_LOG_DENOM) < 1.0


# ── 12. Select-candidate non-leak + _sorted_candidate_order ────────────────


def test_select_candidates_shuffle_invariant():
    cards = _heterogeneous_cards(6)
    run = _bare_run()
    env = _env_with(run, _select_request(run, cards))
    obs1 = env._build_obs()

    for seed in (1, 2, 3):
        shuffled = list(cards)
        random.Random(seed).shuffle(shuffled)
        env._request = _select_request(run, shuffled)
        obs_n = env._build_obs()
        np.testing.assert_array_equal(obs1["f"], obs_n["f"])
        np.testing.assert_array_equal(obs1["i"], obs_n["i"])


def test_select_candidates_shuffle_invariant_past_overflow():
    cards = _heterogeneous_cards(MAX_SELECT_CANDIDATES + 10)
    run = _bare_run()
    env = _env_with(run, _select_request(run, cards))
    with pytest.warns(UserWarning, match="select.candidates"):
        obs1 = env._build_obs()
    layout = run_obs_layout()
    assert obs1["f"][layout.f_slices["select.candidates.overflow"]][0] == pytest.approx(1.0)

    for seed in (11, 12, 13):
        shuffled = list(cards)
        random.Random(seed).shuffle(shuffled)
        env._request = _select_request(run, shuffled)
        obs_n = env._build_obs()
        np.testing.assert_array_equal(obs1["f"], obs_n["f"])
        np.testing.assert_array_equal(obs1["i"], obs_n["i"])


def test_sorted_candidate_order_matches_the_rows_actually_written():
    cards = _heterogeneous_cards(8)
    run = _bare_run()
    request = _select_request(run, cards)
    env = _env_with(run, request)
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["select.candidates.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["select.candidates.f"]].reshape(-1, 4)

    order = env._sorted_candidate_order(request)
    assert len(order) == len(cards)
    assert sorted(order) == list(range(len(cards))), "must be a permutation of every candidate"
    for row, true_idx in enumerate(order):
        expected_ints, expected_floats = _run_card_row(cards[true_idx])
        assert list(int(x) for x in ids[row]) == expected_ints
        assert list(fs[row]) == pytest.approx(expected_floats)


def test_sorted_candidate_order_matches_the_rows_actually_written_past_cap():
    """Review finding (item 1): `_sorted_candidate_order` used to return ALL
    candidate indices, uncapped, while `write_rows` sorts then TRUNCATES to
    MAX_SELECT_CANDIDATES — so past the cap the helper described rows that
    do not exist. This is the exact observation/action seam the T5a/T5b
    split exists to protect: the next lane will build one mask bit per
    helper entry, so an uncapped helper would enable actions for candidate
    rows that are all-PAD in the policy's own observation.

    Regression fixture: MAX_SELECT_CANDIDATES + 10 candidates (past the
    cap, unlike the 8-candidate fixture above which cannot exercise this).
    `len(order)` must equal the number of rows ACTUALLY WRITTEN (== the
    cap, not len(cards)), and every entry must address a real row whose
    content matches what got written there."""
    cards = _heterogeneous_cards(MAX_SELECT_CANDIDATES + 10)
    run = _bare_run()
    request = _select_request(run, cards)
    env = _env_with(run, request)
    # No `pytest.warns` here: the overflow warning itself is already pinned
    # by test_select_candidates_shuffle_invariant_past_overflow, and
    # obs.py's overflow warning is a one-time-per-process latch keyed on the
    # segment name — asserting it here too would make this test's outcome
    # depend on run order (whichever "select.candidates" overflow test runs
    # first). This test is about the order/cap seam, not the warning.
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["select.candidates.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["select.candidates.f"]].reshape(-1, 4)
    n_written = sum(1 for row in ids if not np.all(row == 0))

    order = env._sorted_candidate_order(request)
    assert len(cards) > MAX_SELECT_CANDIDATES, "fixture must actually exceed the cap"
    assert n_written == MAX_SELECT_CANDIDATES, "sanity: the observation itself is capped"
    assert len(order) == n_written, (
        "_sorted_candidate_order must address exactly the rows that exist, "
        f"got {len(order)} entries for {n_written} written rows"
    )
    for row, true_idx in enumerate(order):
        expected_ints, expected_floats = _run_card_row(cards[true_idx])
        assert list(int(x) for x in ids[row]) == expected_ints
        assert list(fs[row]) == pytest.approx(expected_floats)


# ── 13. Overflow ─────────────────────────────────────────────────────────


def test_deck_overflow_truncates_without_raising():
    deck = _heterogeneous_cards(MAX_DECK_ROWS + 12)
    run = _bare_run(deck=list(deck))
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    with pytest.warns(UserWarning, match="run.deck"):
        obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["f"][layout.f_slices["run.deck.overflow"]][0] == pytest.approx(1.0)
    ids = obs["i"][layout.i_slices["run.deck.ids"]].reshape(-1, 4)
    assert len(ids) == MAX_DECK_ROWS


def test_deck_overflow_logs_deck_contents_to_file():
    deck = _heterogeneous_cards(MAX_DECK_ROWS + 12)
    run = _bare_run(deck=list(deck))
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    with pytest.warns(UserWarning, match="run.deck"):
        env._build_obs()

    path = Path(deck_overflow_log_path())
    assert path.exists(), "the warning must be accompanied by a deck dump"
    text = path.read_text(encoding="utf-8")
    assert f"{len(deck)} cards exceeds cap {MAX_DECK_ROWS}" in text
    # EVERY card, not just the surviving 96 — the point is to see what blew it.
    for i, card in enumerate(deck):
        assert f"[{i:3d}] {card.id} +{card.upgrade_level}" in text
    assert sum(1 for line in text.splitlines() if "] " in line) == len(deck)


def test_deck_overflow_log_is_written_once_per_process():
    deck = _heterogeneous_cards(MAX_DECK_ROWS + 12)
    run = _bare_run(deck=list(deck))
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    with pytest.warns(UserWarning, match="run.deck"):
        env._build_obs()
    first = Path(deck_overflow_log_path()).read_text(encoding="utf-8")
    for _ in range(3):
        env._build_obs()
    assert Path(deck_overflow_log_path()).read_text(encoding="utf-8") == first, (
        "a hot loop must not append a dump per step")


def test_deck_overflow_log_failure_does_not_break_obs(monkeypatch):
    monkeypatch.setenv(
        DECK_OVERFLOW_LOG_ENV, str(Path(deck_overflow_log_path()).parent / "no" / "such" / "dir" / "x.log"))
    deck = _heterogeneous_cards(MAX_DECK_ROWS + 12)
    run = _bare_run(deck=list(deck))
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    with pytest.warns(UserWarning):
        obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["f"][layout.f_slices["run.deck.overflow"]][0] == pytest.approx(1.0)


def test_deck_overflow_log_captures_relics():
    """The dump must show the relics alongside the deck — a relic like an
    egg is often WHY the deck blew the cap, and an out-of-vocab relic is
    invisible in the observation, so the log is the only place to see it."""
    deck = _heterogeneous_cards(MAX_DECK_ROWS + 12)
    relics = [make_relic("girya"), make_relic("lava_rock")]
    run = _bare_run(deck=list(deck), relics=relics)
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    with pytest.warns(UserWarning, match="run.deck"):
        env._build_obs()

    text = Path(deck_overflow_log_path()).read_text(encoding="utf-8")
    assert f"relics ({len(relics)}):" in text
    for relic in relics:
        assert f"relic {relic.id} " in text
    # Relic lines must not use the deck's "[idx] " format — the deck-line
    # count assertion in test_deck_overflow_log_logs_deck_contents_to_file
    # keys on "] ", and the two sections must stay distinguishable.
    relic_lines = [l for l in text.splitlines() if l.lstrip().startswith("relic ")]
    assert len(relic_lines) == len(relics)
    assert all("in_vocab=True" in l for l in relic_lines)


def test_relics_overflow_truncates_without_raising():
    relics = [make_relic("girya") for _ in range(MAX_RELIC_ROWS + 5)]
    run = _bare_run(relics=relics)
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    with pytest.warns(UserWarning, match="run.relics"):
        obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["f"][layout.f_slices["run.relics.overflow"]][0] == pytest.approx(1.0)


def test_potions_belt_overflow_truncates_without_raising():
    run = _bare_run()
    for _ in range(MAX_POTION_SLOTS + 2):
        run.add_potion_slots(1)
    assert run.max_potions > MAX_POTION_SLOTS
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    with pytest.warns(UserWarning, match="run.potions"):
        obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["f"][layout.f_slices["run.potions.overflow"]][0] == pytest.approx(1.0)


# ── 14. Task 0 sanity: MAX_POTION_SLOTS is sourced from full_env, not a
#         second independently-declared literal ───────────────────────────


def test_max_potion_slots_is_the_same_object_as_full_envs_ceiling():
    assert MAX_POTION_SLOTS is MAX_POTION_ROWS


# ── 15. Padding invariant guards (item 3): id==0 must always mean
#         all-zero floats too, never "id lookup missed but floats are live" ──


def test_deck_row_with_unresolvable_card_id_is_skipped_not_half_padded():
    """OBS_SCHEMA.md §2.1: a padded row is `id == 0` AND all-zero floats.
    `_run_card_row` writes `oid(CARD_INDEX.get(card.id))` for the id but
    computes its floats (upgrade/cost/affliction/exhaust) straight off the
    card object regardless of whether the id resolved — so an unresolvable
    id used to produce a row that is neither real nor PAD. Unreachable via
    a real Card (CARD_INDEX is built from the same registry every real
    card's id comes from), so this simulates the drift by overwriting
    `.id` on an otherwise-live card, exactly like the pre-v7 code's
    retired `if idx is not None` guard was written to defend against."""
    known = make_card("strike")
    unresolvable = make_card("defend")
    unresolvable.id = "totally_unknown_card_xyz"
    run = _bare_run(deck=[known, unresolvable])
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.deck.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["run.deck.f"]].reshape(-1, 4)

    n_present = sum(1 for row in ids if row[1] != 0)
    assert n_present == 1, "the unresolvable card must be skipped, not written half-padded"
    for i_row, f_row in zip(ids, fs):
        if i_row[1] == 0:   # card_id field PAD -> the WHOLE row must be PAD
            assert all(int(x) == 0 for x in i_row), i_row
            assert all(float(x) == 0.0 for x in f_row), f_row


def test_select_candidates_row_with_unresolvable_card_id_is_skipped():
    """Same guard, `select.candidates` — and it must stay in lockstep with
    `_sorted_candidate_order` (item 1's seam): a candidate that never
    becomes a row must never appear in the order helper's output either."""
    known = _heterogeneous_cards(3)
    unresolvable = make_card("bash")
    unresolvable.id = "totally_unknown_card_xyz"
    cards = known + [unresolvable]
    run = _bare_run()
    request = _select_request(run, cards)
    env = _env_with(run, request)
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["select.candidates.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["select.candidates.f"]].reshape(-1, 4)

    n_present = sum(1 for row in ids if row[1] != 0)
    assert n_present == len(known)
    for i_row, f_row in zip(ids, fs):
        if i_row[1] == 0:
            assert all(int(x) == 0 for x in i_row), i_row
            assert all(float(x) == 0.0 for x in f_row), f_row

    order = env._sorted_candidate_order(request)
    assert len(order) == len(known), "the unresolvable candidate must not appear in the order either"
    assert all(cards[i].id != "totally_unknown_card_xyz" for i in order)


def test_reward_card_row_with_unresolvable_id_is_a_true_pad_row_not_shifted():
    """`reward.cards` is POSITIONAL (the action space addresses a reward
    pick by slot index), so an unresolvable id must become a genuine PAD
    row IN PLACE — unlike the sorted blocks above, silently dropping it
    would shift every later slot's card into the wrong action index."""
    known = make_card("strike")
    unresolvable = make_card("defend")
    unresolvable.id = "totally_unknown_card_xyz"
    third = make_card("bash")
    cards = [known, unresolvable, third]
    run = _bare_run()

    class _FakeRewards:
        def __init__(self, cards):
            self.cards = cards
            self.potion = None

    request = DecisionRequest(
        kind=DecisionKind.REWARD_CARD, run=run, rewards=_FakeRewards(cards),
    )
    env = _env_with(run, request)
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["reward.cards.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["reward.cards.f"]].reshape(-1, 4)

    # Slot 1 (the unresolvable card) must be a TRUE pad row (positionally,
    # not dropped) — id AND floats all zero.
    assert all(int(x) == 0 for x in ids[1]), ids[1]
    assert all(float(x) == 0.0 for x in fs[1]), fs[1]
    # Slots 0 and 2 keep their real content, at their real positions —
    # the fix must not shift them.
    assert ids[0][1] == CARD_INDEX["strike"] + 1
    assert ids[2][1] == CARD_INDEX["bash"] + 1


def test_relic_row_with_unresolvable_vocab_id_is_skipped_not_half_padded(monkeypatch):
    """Same invariant for `run.relics`. Unlike the card case, `relic_row`
    itself keys off `relic.id` too, so mutating `.id` would make BOTH
    lookups fail together and never exercise the bug — this instead
    monkeypatches `run_env.RELIC_INDEX` (the frozen-vocab lookup) to drop
    one real, stateful relic, simulating a vocab/relic_obs registration
    drift: `relic_row` still returns live (counter, flag) state, but the
    id can no longer be resolved to a vocab index."""
    import sts2_rl.run_env as run_env_mod

    girya = make_relic("girya")
    girya.times_lifted = 3
    lava = make_relic("lava_rock")
    lava.has_triggered = True   # would show flag=1 if not for the drift
    monkeypatch.setattr(
        run_env_mod, "RELIC_INDEX",
        {k: v for k, v in run_env_mod.RELIC_INDEX.items() if k != "lava_rock"},
    )
    run = _bare_run(relics=[girya, lava])
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.relics.ids"]]
    fs = obs["f"][layout.f_slices["run.relics.f"]].reshape(-1, 2)

    n_present = sum(1 for x in ids if x != 0)
    assert n_present == 1, "the unresolvable relic must be skipped, not written half-padded"
    for i_val, f_row in zip(ids, fs):
        if i_val == 0:
            assert list(f_row) == [0.0, 0.0], "a PAD id relic row must carry all-zero floats"


def test_boss_row_with_unresolvable_monster_class_is_skipped_not_appended():
    """`run.boss` is the case the review called "the worst": appending a
    PAD row for an unrecognised monster class consumes one of only
    MAX_BOSS_IDS=4 slots and SHIFTS any later real id into a later row
    than it should occupy. `getattr(cls, "__name__", "")` is all
    `_build_obs` reads off each class, so a plain local class whose
    `__name__` matches a real registered monster name is enough to stand
    in for "resolvable" without depending on any particular boss's real
    roster; the middle class is deliberately unresolvable so a fix that
    merely happened to preserve order for a TAIL gap (as the un-shuffled
    real boss `the_kin` would) can't accidentally pass this test."""
    class KinFollower:
        pass

    class _UnresolvableMonster:
        pass

    class KinPriest:
        pass

    class _FakeEncounter:
        def __init__(self, monster_classes):
            self.monster_classes = monster_classes

    class _FakeRoomSet:
        def __init__(self, monster_classes):
            self.boss_key = "fake_boss"
            self.next_boss_encounter = _FakeEncounter(monster_classes)

    run = _bare_run()
    run.room_set = _FakeRoomSet([KinFollower, _UnresolvableMonster, KinPriest])
    env = _env_with(run, DecisionRequest(kind=DecisionKind.MAP, run=run, points=[]))
    obs = env._build_obs()
    layout = run_obs_layout()
    ids = obs["i"][layout.i_slices["run.boss.ids"]]

    got = [int(x) for x in ids if x != 0]
    assert len(got) == 2, "the unresolvable class must be skipped, not appended as PAD"
    assert got == sorted([MONSTER_INDEX["KinFollower"] + 1, MONSTER_INDEX["KinPriest"] + 1])
    # The two real rows must be a CONTIGUOUS prefix (rows 0, 1) — not
    # pushed apart by a skipped placeholder sitting between them.
    assert int(ids[0]) != 0 and int(ids[1]) != 0
