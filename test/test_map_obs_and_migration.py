"""Schema v4's run.boss.identity / run.map.grid observation and the
v3 → v4 checkpoint migration.

The migration tests fabricate a "v3" checkpoint by inverse-splicing (deleting
the v4 columns from) a freshly built v4 model, so they need no saved fixture
and no old code path: migrating it back must restore the exact weights with
zeros in the new columns, and — the property that actually matters — the
migrated model's outputs must be bit-identical and independent of the new
feature ranges. A wrong offset in either splice space fails both checks.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from sts2_rl import run_env as RE
from sts2_rl.checkpoints import (
    ModelSpec,
    _V4_NEW_SEGMENTS,
    _new_column_blocks,
    _segment_out_width,
    check_checkpoint,
    make_model,
    migrate_checkpoint,
    model_obs_segments,
)
from sts2_rl.curriculum_env import STS2CurriculumRunEnv
from sts2_rl.rooms import _ACT_ROOMS_FACTORIES, act_rooms
from sts2_rl.run_env import (
    MAP_GRID_NODE,
    MAP_GRID_ROWS,
    N_ACTIONS,
    STS2RunEnv,
    run_obs_segments,
)

_HIDDEN = (32,)          # small trunks keep the migration tests fast


# ── helpers ──────────────────────────────────────────────────────────────

def _keep_mask(n_new_cols: int, blocks: list[tuple[int, int]]) -> torch.Tensor:
    """Boolean mask over the NEW column space: True = pre-existing column."""
    keep = torch.ones(n_new_cols, dtype=torch.bool)
    shift = 0
    for pos, width in blocks:
        keep[pos + shift:pos + shift + width] = False
        shift += width
    return keep


def _fabricate_v3(arch: str) -> tuple[dict, int]:
    """A synthetic v3 checkpoint: a v4 model with the new columns deleted
    from both trunks' first layers and their Adam moments. Returns it with
    the v4 obs_dim it should migrate back to."""
    spec = ModelSpec(env_kind="column", arch=arch, hidden=_HIDDEN)
    segments = model_obs_segments(spec)
    obs_dim = sum(w for _, w in segments)
    torch.manual_seed(7)
    model = make_model(spec, obs_dim, N_ACTIONS)

    width_fn = _segment_out_width if arch == "entity" else (lambda n, w: w)
    blocks = _new_column_blocks(run_obs_segments(), width_fn)
    # The obs_dim stamp is always flat-obs floats, whatever the arch.
    added = sum(w for n, w in run_obs_segments() if n in _V4_NEW_SEGMENTS)

    # Populate realistic Adam moments with one update.
    optim = torch.optim.Adam(model.parameters())
    obs = torch.rand(4, obs_dim)
    mask = torch.ones(4, N_ACTIONS, dtype=torch.bool)
    _, logp, ent, val = model.get_action_and_value(obs, mask)
    (logp.sum() + ent.sum() + val.sum()).backward()
    optim.step()

    state = {k: v.clone() for k, v in model.state_dict().items()}
    ostate = optim.state_dict()
    names = [n for n, _ in model.named_parameters()]
    for key in ("actor.0.weight", "critic.0.weight"):
        keep = _keep_mask(state[key].shape[1], blocks)
        state[key] = state[key][:, keep]
        pstate = ostate["state"][names.index(key)]
        for moment in ("exp_avg", "exp_avg_sq"):
            pstate[moment] = pstate[moment][:, keep]
    # A real v3 checkpoint's Adam state is keyed by the V3 parameter order,
    # which differs for the entity arch (the monsters table used to be
    # created later in the segment walk). Re-key so migration must remap.
    if arch == "entity":
        from sts2_rl.models import EntityActorCritic
        old_segments = [(n, w) for n, w in segments
                        if n not in _V4_NEW_SEGMENTS]
        old_names = [n for n, _ in
                     EntityActorCritic(old_segments, N_ACTIONS,
                                       hidden=_HIDDEN).named_parameters()]
        assert old_names != names       # the reorder this guards against
        ostate["state"] = {
            old_idx: ostate["state"][names.index(name)]
            for old_idx, name in enumerate(old_names)
            if names.index(name) in ostate["state"]
        }

    ckpt = {
        "model": state, "optim": ostate, "iteration": 5, "global_step": 999,
        "best_score": 1.5, "obs_dim": obs_dim - added, "n_actions": N_ACTIONS,
        "hidden": _HIDDEN, "arch": arch, "obs_schema": 3, "env_kind": "column",
    }
    return ckpt, obs_dim


# ── migration ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arch", ["mlp", "entity"])
def test_migration_restores_weights_and_zeroes_new_columns(arch):
    v3, obs_dim = _fabricate_v3(arch)
    old_actor = v3["model"]["actor.0.weight"].clone()
    migrated = migrate_checkpoint(v3)

    assert migrated["obs_schema"] == 4
    assert migrated["obs_dim"] == obs_dim
    assert migrated["iteration"] == 5 and migrated["global_step"] == 999
    assert v3["obs_schema"] == 3                     # input not mutated

    width_fn = _segment_out_width if arch == "entity" else (lambda n, w: w)
    blocks = _new_column_blocks(run_obs_segments(), width_fn)
    new_w = migrated["model"]["actor.0.weight"]
    keep = _keep_mask(new_w.shape[1], blocks)
    assert torch.equal(new_w[:, keep], old_actor)
    assert (new_w[:, ~keep] == 0).all()
    for moment in ("exp_avg", "exp_avg_sq"):
        for key in ("actor.0.weight", "critic.0.weight"):
            names = [n for n, _ in
                     make_model(ModelSpec("column", arch=arch, hidden=_HIDDEN),
                                obs_dim, N_ACTIONS).named_parameters()]
            m = migrated["optim"]["state"][names.index(key)][moment]
            assert m.shape == migrated["model"][key].shape
            assert (m[:, ~keep] == 0).all()


@pytest.mark.parametrize("arch", ["mlp", "entity"])
def test_migrated_model_ignores_the_new_features(arch):
    """The output must be bit-identical no matter what the v4 segments hold —
    the definition of function preservation, and a detector for any offset
    error in either splice space."""
    v3, obs_dim = _fabricate_v3(arch)
    migrated = migrate_checkpoint(v3)
    spec = ModelSpec(env_kind="column", arch=arch, hidden=_HIDDEN)
    model = make_model(spec, obs_dim, N_ACTIONS)
    model.load_state_dict(migrated["model"])
    model.eval()

    torch.manual_seed(1)
    obs = torch.rand(8, obs_dim)
    scrambled = obs.clone()
    off = 0
    for name, width in run_obs_segments():
        if name in _V4_NEW_SEGMENTS:
            scrambled[:, off:off + width] = torch.rand(8, width)
        off += width
    mask = torch.ones(8, N_ACTIONS, dtype=torch.bool)
    with torch.no_grad():
        assert torch.equal(model.action_logits(obs, mask),
                           model.action_logits(scrambled, mask))
        assert torch.equal(model.get_value(obs), model.get_value(scrambled))


@pytest.mark.parametrize("arch", ["mlp", "entity"])
def test_migrated_optimizer_state_loads_and_steps(arch):
    v3, obs_dim = _fabricate_v3(arch)
    migrated = migrate_checkpoint(v3)
    model = make_model(ModelSpec("column", arch=arch, hidden=_HIDDEN),
                       obs_dim, N_ACTIONS)
    model.load_state_dict(migrated["model"])
    optim = torch.optim.Adam(model.parameters())
    optim.load_state_dict(migrated["optim"])
    _, logp, ent, val = model.get_action_and_value(
        torch.rand(2, obs_dim), torch.ones(2, N_ACTIONS, dtype=torch.bool))
    (logp.sum() + ent.sum() + val.sum()).backward()
    optim.step()                                     # no shape complaints


def test_migration_refuses_wrong_schema_and_env():
    v3, _ = _fabricate_v3("mlp")
    with pytest.raises(SystemExit, match="schema 3"):
        migrate_checkpoint({**v3, "obs_schema": 2})
    with pytest.raises(SystemExit, match="run-scale"):
        migrate_checkpoint({**v3, "env_kind": "combat"})


def test_check_checkpoint_points_v3_users_at_the_migration():
    v3, obs_dim = _fabricate_v3("mlp")
    spec = ModelSpec(env_kind="column", arch="mlp", hidden=_HIDDEN)
    with pytest.raises(SystemExit, match="migrate_ckpt.py"):
        check_checkpoint(v3, spec, obs_dim, N_ACTIONS)


# ── the whole-map grid observation ───────────────────────────────────────

def _grid_view(env, obs):
    sl = env.obs_slices()
    return obs[sl["run.map.grid"]].reshape(MAP_GRID_ROWS, RE._MAP_WIDTH,
                                           MAP_GRID_NODE), obs[sl["run.map.meta"]]


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
    sl = env.obs_slices()
    boss = obs[sl["run.boss.identity"]]
    expected = {RE.MONSTER_INDEX[cls.__name__]
                for cls in run.room_set.next_boss_encounter.monster_classes}
    assert set(np.flatnonzero(boss)) == expected
