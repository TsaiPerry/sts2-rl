"""Schema v7's run.boss.ids / run.map.grid observation, and what is left of
the pre-v7 checkpoint-migration tooling.

T7 (OBS_SCHEMA.md phase 1) judgment call, made deliberately
and reported here rather than silently: the flat-`Box` -> `{"f", "i"}` `Dict`
rewrite (run_env.py's own module comment, RUN_OBS_SCHEMA_VERSION history)
states there is NO v6->v7 weight migration — a flat array and a two-leaf
Dict are different Gym space TYPES, not a reshape of the same array — so
`checkpoints.migrate_checkpoint` (v3->v4) and `migrate_checkpoint_actions`
(v5->v6) are now UNREACHABLE from any real caller: nothing produces a
schema 3-6 checkpoint anymore, and nothing downstream of v7 asks to migrate
INTO a flat-Box target again. Per CLAUDE.md Sec.3 the project keeps that
code in place rather than deleting it (checkpoints.py is T6's file, not
this lane's).

Verified empirically before deciding (see the T7 report for the exact
repro), both functions were, briefly, not merely unreachable but actively
BROKEN if called directly —

  - `migrate_checkpoint` imported `run_obs_segments` from `run_env` at the
    top of its body; phase 1 renamed that to `run_obs_segments_f`/`_i`, so
    EVERY call, for EVERY input, raised `ImportError` before any of its own
    validation ran.
  - `migrate_checkpoint_actions` hard-coded `assert RUN_OBS_SCHEMA_VERSION
    == 6`; phase 1 bumped that constant to 7 without updating the assert,
    so a WELL-FORMED v5 checkpoint (the one case this function exists to
    migrate) raised a bare `AssertionError` instead of completing the
    migration.
  - Both functions' own test fixtures (the old `_fabricate_v3`/`_fabricate_v5`
    helpers) additionally no longer type-checked against the current
    `make_model(spec, (f_dim, i_dim), n_actions)` contract, which expects a
    2-tuple, not the flat `sum(...)` int those fixtures built.

A follow-up lane (checkpoints.py owner) fixed the crash without resurrecting
the migration: each function's env-kind/schema/shape guards still run and
still behave exactly as designed for malformed input, but the one input each
function exists to handle (a well-formed v3 or v5 checkpoint) now ends in an
explicit `SystemExit` explaining the phase-1 bump left no schema to migrate
onto, instead of an `ImportError`/`AssertionError` a caller would have to go
read source to understand. `check_checkpoint`'s hint text was fixed to
match: it no longer tells a schema-3 or schema-5 holder to run
`migrate_ckpt.py` (which would now just hit the same honest refusal) — every
stale schema is told plainly to start over with `--fresh`.

Given all this, the fine-grained "restores weights / zeroes new columns /
bit-identical outputs" tests that used to live here are DELETED, not
rewritten — the property they protected (this migration is function-
preserving) belongs to a mechanism that is not just dead but non-functional,
and pinning it now would mean re-deriving the whole splice fixture against
an obs_dim contract it predates, to protect code nothing in the current tree
can reach. Kept instead: both functions' still-live guard rails (the part of
their contract that isn't broken), their new honest-failure message for
well-formed input, and — the property that actually matters post-v7 —
`checkpoints.check_checkpoint` refusing every pre-v7 schema with a clear
`SystemExit`, never a crash inside `load_state_dict`, widened from the old
suite's two hardcoded schemas (3, 5) to every schema this project has
shipped.

The map/boss sections below are unrelated to migration and survive close to
verbatim: `run.map.grid`/`run.map.meta` stayed float segments in v4 (OBS_
SCHEMA.md Sec.2.2 — topology, not a frozen vocabulary), so only the
obs-access idiom (the `{"f", "i"}` Dict plus `run_obs_layout()`'s named
slices, replacing the old flat array and `env.obs_slices()`) needed
updating.
"""
from __future__ import annotations

import random

import numpy as np
import pytest

from sts2_rl import run_env as RE
from sts2_rl.checkpoints import (
    ModelSpec,
    check_checkpoint,
    migrate_checkpoint,
    migrate_checkpoint_actions,
    model_obs_layout,
)
from sts2_rl.curriculum_env import STS2CurriculumRunEnv
from sts2_rl.rooms import _ACT_ROOMS_FACTORIES, act_rooms
from sts2_rl.run_env import (
    MAP_GRID_NODE,
    MAP_GRID_ROWS,
    N_ACTIONS,
    RUN_OBS_SCHEMA_VERSION,
    STS2RunEnv,
    run_obs_layout,
)

_HIDDEN = (32,)          # small trunk keeps the check_checkpoint tests fast


def _real_dims(spec: ModelSpec) -> tuple[int, int]:
    f_segs, i_segs = model_obs_layout(spec)
    return (sum(w for _, w in f_segs), sum(w for _, w in i_segs))


# ── check_checkpoint: the property that actually matters post-v7 ─────────


@pytest.mark.parametrize("schema", [2, 3, 4, 5, 6])
def test_check_checkpoint_refuses_every_pre_v7_schema_loudly(schema):
    """There is no v6->v7 weight migration, so EVERY schema stamped before
    v7 must dead-end in a clear, loud `SystemExit` — never a crash inside
    `load_state_dict`. The pre-v7 suite only pinned this for schemas 3 and
    5 (the two that used to have a real migration path); this widens it to
    every schema the project has shipped, since none of them can reach v7
    through any migration anymore."""
    spec = ModelSpec(env_kind="column", arch="mlp", hidden=_HIDDEN)
    obs_dim = _real_dims(spec)
    ckpt = {"env_kind": "column", "obs_schema": schema, "arch": "mlp",
            "obs_dim": obs_dim, "n_actions": N_ACTIONS, "hidden": _HIDDEN}
    with pytest.raises(SystemExit):
        check_checkpoint(ckpt, spec, obs_dim, N_ACTIONS)


def test_check_checkpoint_accepts_the_current_schema():
    """Sanity check for the parametrized refusal above: pin that it is
    keyed on the schema stamp specifically, not a fixture shape that would
    raise for any input at all."""
    spec = ModelSpec(env_kind="column", arch="mlp", hidden=_HIDDEN)
    obs_dim = _real_dims(spec)
    ckpt = {"env_kind": "column", "obs_schema": RUN_OBS_SCHEMA_VERSION, "arch": "mlp",
            "obs_dim": obs_dim, "n_actions": N_ACTIONS, "hidden": _HIDDEN}
    check_checkpoint(ckpt, spec, obs_dim, N_ACTIONS)   # must not raise


@pytest.mark.parametrize("schema", [3, 5])
def test_check_checkpoint_hint_no_longer_names_a_migration_tool(schema):
    """T7 follow-up: the hint used to tell a schema-3 or schema-5 holder to
    run `py migrate_ckpt.py ...` — a tool that (see below) now always
    fails. Promising it here would be actively wrong, so the message must
    not name migrate_ckpt.py, or any of the sts2_rl.checkpoints migration
    function names, and must say plainly that --fresh is the only path."""
    spec = ModelSpec(env_kind="column", arch="mlp", hidden=_HIDDEN)
    obs_dim = _real_dims(spec)
    ckpt = {"env_kind": "column", "obs_schema": schema, "arch": "mlp",
            "obs_dim": obs_dim, "n_actions": N_ACTIONS, "hidden": _HIDDEN}
    with pytest.raises(SystemExit) as exc_info:
        check_checkpoint(ckpt, spec, obs_dim, N_ACTIONS)
    message = str(exc_info.value)
    assert "migrate_ckpt.py" not in message
    assert "migrate_checkpoint" not in message
    assert "--fresh" in message
    assert str(schema) in message   # still names what was found, per T6's style


# ── migrate_checkpoint_actions: the AssertionError this lane found (see the
#    module docstring) was fixed in checkpoints.py (T6's file), and a later
#    fix-pass (review item 3) reordered it further: the honest "no migration
#    path" SystemExit now runs immediately after the env-kind/obs-schema
#    guards, ahead of any shape check on the checkpoint's own n_actions — so
#    a genuine v5 checkpoint gets the true reason, not a shape-mismatch
#    message computed from today's (not v5's) MAX_POTION_SLOTS ──


def test_migrate_checkpoint_actions_refuses_wrong_schema_and_env():
    """The env-kind and obs-schema guards both run BEFORE the unconditional
    "no migration path" `SystemExit` (checkpoints.py), so they still behave
    exactly as designed — bare dicts are enough, no fabricated
    checkpoint/model needed, since neither guard inspects "model"/"optim"."""
    with pytest.raises(SystemExit, match="schema 5"):
        migrate_checkpoint_actions({"env_kind": "column", "obs_schema": 4})
    with pytest.raises(SystemExit, match="run-scale"):
        migrate_checkpoint_actions({"env_kind": "combat", "obs_schema": 5})


def test_migrate_checkpoint_refuses_wrong_schema_and_env():
    """Same shape of guard as migrate_checkpoint_actions, for the v3 -> v4
    function: env-kind and obs-schema checks run before the function ever
    tries (and fails) to build anything, so malformed input still gets a
    specific message, not the stale `ImportError` this lane found and the
    checkpoints.py follow-up lane fixed."""
    with pytest.raises(SystemExit, match="schema 3"):
        migrate_checkpoint({"env_kind": "column", "obs_schema": 2})
    with pytest.raises(SystemExit, match="run-scale"):
        migrate_checkpoint({"env_kind": "combat", "obs_schema": 3})


def test_migrate_checkpoint_well_formed_input_fails_honestly():
    """The one case migrate_checkpoint exists to handle — a run-scale,
    schema-3 checkpoint — used to raise `ImportError: cannot import name
    'run_obs_segments'` (phase 1 renamed it to run_obs_segments_f/_i).
    Pin the fix: a `SystemExit` that says plainly there is no migration
    path, not an import crash a caller would have to go read source to
    understand."""
    ckpt = {"env_kind": "column", "obs_schema": 3}
    with pytest.raises(SystemExit) as exc_info:
        migrate_checkpoint(ckpt)
    message = str(exc_info.value)
    assert "unreachable" in message
    assert "--fresh" in message
    assert "ImportError" not in message


def test_migrate_checkpoint_actions_well_formed_input_fails_honestly():
    """The one case migrate_checkpoint_actions exists to handle — a
    run-scale, schema-5 checkpoint — used to raise a bare `AssertionError`
    from a stale `RUN_OBS_SCHEMA_VERSION == 6` check (the constant is 7
    now). Pin the fix: a `SystemExit` that says plainly there is no
    migration path. No `n_actions` in the fixture — the fix-pass reorder
    (review item 3) put the honest raise BEFORE any shape check on it, so
    the function no longer inspects it at all; the old fixture synthesized
    a fake "v5 width" via `N_ACTIONS - MAX_POTION_SLOTS`, which is today's
    formula (today's `MAX_POTION_SLOTS`), not the historical v5 one, so it
    never actually exercised a real v5 value."""
    ckpt = {"env_kind": "column", "obs_schema": 5}
    with pytest.raises(SystemExit) as exc_info:
        migrate_checkpoint_actions(ckpt)
    message = str(exc_info.value)
    assert "unreachable" in message
    assert "--fresh" in message


# ── the whole-map grid observation ───────────────────────────────────────


def _grid_view(env, obs):
    layout = run_obs_layout()
    f = obs["f"]
    grid = f[layout.f_slices["run.map.grid"]].reshape(
        MAP_GRID_ROWS, RE._MAP_WIDTH, MAP_GRID_NODE)
    meta = f[layout.f_slices["run.map.meta"]]
    return grid, meta


def _assert_grid_matches(env, obs):
    """The grid block must mirror run.map exactly, and the position bits must
    point at run.current_point — checked at any step of any run env."""
    run = env._run
    act_map = run.map
    grid, meta = _grid_view(env, obs)
    if act_map is None:
        assert not grid.any() and not meta.any()
        return
    expect = np.zeros_like(grid)
    for row in range(1, min(MAP_GRID_ROWS, act_map.map_length - 1) + 1):
        for point in act_map.points_in_row(row):
            cell = expect[row - 1, point.col]
            cell[0] = 1.0
            cell[1 + RE._POINT_TYPE_INDEX[point.point_type]] = 1.0
            for child in point.children:
                if child.row < act_map.map_length:
                    cell[1 + RE._N_POINT_TYPES + child.col] = 1.0
    cp = run.current_point
    expect_meta = np.zeros(2, dtype=np.float32)
    if cp is act_map.starting_point:
        expect_meta[0] = 1.0
    elif cp is not None and (cp is act_map.boss_point
                             or cp is act_map.second_boss_point):
        expect_meta[1] = 1.0
    elif cp is not None:
        expect[cp.row - 1, cp.col, MAP_GRID_NODE - 1] = 1.0
    np.testing.assert_array_equal(grid, expect)
    np.testing.assert_array_equal(meta, expect_meta)


@pytest.mark.parametrize("env_cls", [STS2CurriculumRunEnv, STS2RunEnv])
def test_grid_mirrors_the_map_throughout_a_run(env_cls):
    env = env_cls()
    obs, _ = env.reset(seed=11)
    _assert_grid_matches(env, obs)
    for _ in range(120):
        action = int(np.flatnonzero(env.action_masks())[0])
        obs, _, term, trunc, _ = env.step(action)
        if term or trunc:
            break
        _assert_grid_matches(env, obs)


def test_grid_is_written_outside_map_decisions():
    env = STS2CurriculumRunEnv()
    obs, info = env.reset(seed=3)
    assert info["phase"] != "map"                     # Neow event first
    grid, meta = _grid_view(env, obs)
    assert grid[..., 0].sum() == env._run.map.map_length - 1
    assert meta[0] == 1.0                             # standing at the Ancient
    # A column: every node in the center column, and full 1..N lookahead.
    assert set(np.flatnonzero(grid[..., 0].any(axis=0))) == {RE._MAP_WIDTH // 2}


# ── boss identity ────────────────────────────────────────────────────────


def test_every_boss_declares_vocab_known_monster_classes():
    for act in _ACT_ROOMS_FACTORIES:
        rooms = act_rooms(act)
        registry = rooms.encounters()
        for key in rooms.boss_keys:
            names = [getattr(cls, "__name__", "")
                     for cls in registry[key].monster_classes]
            assert names, f"{act}/{key} declares no monster classes"
            for n in names:
                assert n in RE.MONSTER_INDEX, f"{act}/{key}: {n} not in vocab"


def test_the_kin_declares_its_followers_and_priest():
    registry = act_rooms("overgrowth").encounters()
    names = [cls.__name__ for cls in registry["the_kin"].monster_classes]
    assert names == ["KinFollower", "KinFollower", "KinPriest"]


def test_boss_identity_is_visible_from_act_entry():
    env = STS2CurriculumRunEnv()
    obs, info = env.reset(seed=3)
    assert info["phase"] != "map"                     # known before any travel
    run = env._run
    layout = run_obs_layout()
    boss_ids = obs["i"][layout.i_slices["run.boss.ids"]]
    expected = {RE.MONSTER_INDEX[cls.__name__] + 1
                for cls in run.room_set.next_boss_encounter.monster_classes}
    assert {int(x) for x in boss_ids if x != 0} == expected
