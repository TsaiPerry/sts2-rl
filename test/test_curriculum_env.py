"""STS2CurriculumRunEnv (sts2_rl/curriculum_env.py): column type-sequence
constraints, the single-column map shape, "?"-floors forced to Event,
floor-only reward accounting, layout parity with STS2RunEnv, and seeded
determinism."""
import random

import numpy as np
import pytest

from sts2_rl.actmap import MapPointType, OVERGROWTH_MAP
from sts2_rl.curriculum_env import (
    ColumnRunState,
    STS2CurriculumRunEnv,
    column_map,
    random_column_types,
)
from sts2_rl.rooms import RoomType
from sts2_rl.run_env import N_ACTIONS, run_obs_segments_f, run_obs_segments_i

_ENV = None


def shared_env():
    """Construction probes a CombatState, so share one env across tests."""
    global _ENV
    if _ENV is None:
        _ENV = STS2CurriculumRunEnv()
    return _ENV


def masked_random_episode(env, seed, max_steps=20_000):
    rng = np.random.default_rng(seed)
    obs, info = env.reset(seed=seed)
    trajectory = []
    for _ in range(max_steps):
        mask = env.action_masks()
        assert mask.shape == (env.n_actions,) and mask.any()
        action = int(rng.choice(np.flatnonzero(mask)))
        obs, reward, terminated, truncated, info = env.step(action)
        trajectory.append((action, round(float(reward), 6), info["phase"], info["floor"]))
        if terminated or truncated:
            return trajectory, info, obs
    pytest.fail("episode did not finish")


# ═════════════════════════════════════════════════════════════════════════
# Column sampling
# ═════════════════════════════════════════════════════════════════════════

_SPECIALS = {
    MapPointType.ELITE, MapPointType.REST_SITE,
    MapPointType.TREASURE, MapPointType.SHOP,
}


def test_column_types_respect_constraints():
    # StandardActMap's placement rules, projected onto a column of 16.
    for seed in range(50):
        types = random_column_types(random.Random(seed), n_rooms=16)
        assert len(types) == 16
        assert types[0] == MapPointType.MONSTER          # forced row 1
        assert types[-1] == MapPointType.REST_SITE       # forced pre-boss rest
        assert types[9] == MapPointType.TREASURE         # forced row n_rooms-6
        # Default weights give treasure ONLY the forced row, like the game.
        assert types.count(MapPointType.TREASURE) == 1
        for floor, t in enumerate(types, start=1):
            if floor < 6:                                # _valid_for_lower
                assert t not in (MapPointType.ELITE, MapPointType.REST_SITE), (
                    f"seed {seed}: {t.name} on early floor {floor}"
                )
            if floor >= 14 and floor != 16:              # _valid_for_upper
                assert t != MapPointType.REST_SITE, (
                    f"seed {seed}: rest in the top 3 rows (floor {floor})"
                )
        for a, b in zip(types, types[1:]):
            if a in _SPECIALS:
                assert a != b, f"seed {seed}: back-to-back {a.name}"


def test_column_types_vary_per_sample():
    rng = random.Random(0)
    samples = {random_column_types(rng) for _ in range(10)}
    assert len(samples) > 1


def test_column_types_follow_weights():
    # All-monster weights: every floor is a fight besides the forced
    # treasure row (floor 10 of 16) and the forced top rest.
    types = random_column_types(random.Random(1), room_weights={"monster": 1.0})
    assert all(
        t == MapPointType.MONSTER
        for i, t in enumerate(types[:-1]) if i != 9
    )
    # All-elite weights: elites everywhere they're legal, with the no-repeat
    # rule falling back to Monster between them and no elite before floor 6.
    types = random_column_types(random.Random(2), room_weights={"elite": 1.0})
    assert MapPointType.ELITE in types
    assert all(t == MapPointType.MONSTER for t in types[:5])
    for a, b in zip(types, types[1:]):
        assert not (a == b == MapPointType.ELITE)


def test_column_types_reject_bad_weights():
    with pytest.raises(ValueError):
        random_column_types(random.Random(0), room_weights={"bogus": 1.0})
    with pytest.raises(ValueError):
        random_column_types(random.Random(0), room_weights={"monster": 0.0})


def test_column_map_is_single_column():
    rng = random.Random(3)
    types = random_column_types(rng)
    m = column_map(rng, OVERGROWTH_MAP, types)
    assert m.map_length == len(types) + 1
    for row in range(1, m.map_length):
        points = list(m.points_in_row(row))
        assert len(points) == 1
        assert points[0].point_type == types[row - 1]
        # One child each: the next floor (the boss above the top row).
        child, = points[0].children
        expected = m.boss_point if row == m.map_length - 1 else next(
            iter(m.points_in_row(row + 1))
        )
        assert child is expected
    assert m.starting_point.children == {next(iter(m.points_in_row(1)))}


# ═════════════════════════════════════════════════════════════════════════
# ColumnRunState
# ═════════════════════════════════════════════════════════════════════════

def test_unknown_floors_resolve_to_events():
    # All-"?" columns: every non-forced floor must roll Event, whatever the
    # pity odds say (Golden Compass semantics).
    rs = ColumnRunState(rng=random.Random(4), room_weights={"event": 1.0})
    rs.start_act("overgrowth")
    while not rs.at_act_end:
        point = rs.travelable_points()[0]
        resolution = rs.enter_point(point)
        if resolution.map_point_type == MapPointType.UNKNOWN:
            assert resolution.room_type == RoomType.EVENT


def test_each_act_resamples_the_column():
    rs = ColumnRunState(rng=random.Random(5), column_rooms=16)
    first = [p.point_type for p in
             (next(iter(rs.start_act("overgrowth").points_in_row(r)))
              for r in range(1, 17))]
    second = [p.point_type for p in
              (next(iter(rs.start_act("hive").points_in_row(r)))
               for r in range(1, 17))]
    assert first != second


def test_default_column_length_follows_the_act():
    # column_rooms=None (the default) uses each act's real room count.
    rs = ColumnRunState(rng=random.Random(11))
    assert rs.start_act("overgrowth").map_length == OVERGROWTH_MAP.num_rooms + 1
    assert rs.start_act("hive").map_length == 14 + 1


# ═════════════════════════════════════════════════════════════════════════
# Branch annealing (branch_prob)
# ═════════════════════════════════════════════════════════════════════════

def column_types(act_map, n_rooms=16):
    return [next(iter(act_map.points_in_row(r))).point_type.name
            for r in range(1, n_rooms + 1)]


def is_branching(act_map) -> bool:
    """Real StandardMaps fork; a sampled column has exactly one point per row."""
    return any(len(list(act_map.points_in_row(r))) > 1
               for r in range(1, act_map.map_length))


# Captured from the pre-annealing column env. branch_prob=0.0 must draw no
# extra randomness, so stage 1 of the anneal is a bit-identical continuation
# of the column curriculum that has already been validated — not a variant
# that merely resembles it.
_SEED_21_COLUMN = [
    "MONSTER", "UNKNOWN", "MONSTER", "UNKNOWN", "MONSTER", "MONSTER",
    "REST_SITE", "MONSTER", "MONSTER", "TREASURE", "MONSTER", "MONSTER",
    "ELITE", "UNKNOWN", "MONSTER", "REST_SITE",
]


@pytest.mark.parametrize("kwargs", [{}, {"branch_prob": 0.0}])
def test_branch_prob_zero_leaves_the_rng_stream_untouched(kwargs):
    rs = ColumnRunState(rng=random.Random(21), column_rooms=16, **kwargs)
    assert column_types(rs.start_act("overgrowth")) == _SEED_21_COLUMN


def test_branch_prob_one_generates_real_branching_maps():
    rs = ColumnRunState(rng=random.Random(22), branch_prob=1.0)
    assert is_branching(rs.start_act("overgrowth"))


def test_branch_prob_one_restores_the_real_unknown_room_types():
    # "?" is pinned to Event on a column so the sampled combat count is the
    # actual one; a branching episode must use the game's real resolution.
    column = ColumnRunState(rng=random.Random(23), branch_prob=0.0)
    branching = ColumnRunState(rng=random.Random(23), branch_prob=1.0)
    column.start_act("overgrowth")
    branching.start_act("overgrowth")
    assert column._unknown_allowed_room_types(set()) == {RoomType.EVENT}
    assert branching._unknown_allowed_room_types(set()) != {RoomType.EVENT}


def test_regime_is_drawn_once_and_holds_for_every_act():
    # Per-episode granularity: all three acts share one regime, so an
    # episode return is never a blend of both map distributions.
    for seed in range(30):
        rs = ColumnRunState(rng=random.Random(seed), branch_prob=0.5)
        first = is_branching(rs.start_act("overgrowth"))
        for act in ("hive", "glory"):
            assert is_branching(rs.start_act(act)) is first, f"seed {seed}"


def test_branch_prob_mixes_the_two_regimes():
    branching = sum(
        is_branching(ColumnRunState(rng=random.Random(s), branch_prob=0.5)
                     .start_act("overgrowth"))
        for s in range(200)
    )
    assert 60 < branching < 140          # ~100 expected


def test_env_passes_branch_prob_through_to_the_run_state():
    env = STS2CurriculumRunEnv(branch_prob=1.0)
    env.reset(seed=12)
    assert isinstance(env._run, ColumnRunState)
    assert is_branching(env._run.map)


# ═════════════════════════════════════════════════════════════════════════
# Environment
# ═════════════════════════════════════════════════════════════════════════

def test_layout_matches_run_env():
    env = shared_env()
    # Same action space and named obs layout as STS2RunEnv — checkpoints
    # must move freely between the two (the phase-2 handoff).
    assert env.action_space.n == env.n_actions == N_ACTIONS
    segs_f = env.obs_segments_f()
    segs_i = env.obs_segments_i()
    n_run_f = len(run_obs_segments_f())
    n_run_i = len(run_obs_segments_i())
    assert segs_f[:n_run_f] == run_obs_segments_f()
    assert segs_i[:n_run_i] == run_obs_segments_i()
    assert segs_f[n_run_f:] and all(n.startswith("combat.") for n, _ in segs_f[n_run_f:])
    assert segs_i[n_run_i:] and all(n.startswith("combat.") for n, _ in segs_i[n_run_i:])
    env.reset(seed=0)
    assert isinstance(env._run, ColumnRunState)


def test_reward_is_floors_plus_win_bonus():
    env = shared_env()
    trajectory, info, _ = masked_random_episode(env, seed=6)
    floors = [floor for _, _, _, floor in trajectory]
    rewards = [r for _, r, _, _ in trajectory]
    # Every step's reward is exactly the floor delta, except the terminal
    # step of a won run, which adds reward_win (3.0).
    deltas = [b - a for a, b in zip([0] + floors, floors)]
    expected = [float(d) for d in deltas]
    if info["is_success"]:
        expected[-1] += 3.0
    assert rewards == pytest.approx(expected)
    assert sum(rewards) == pytest.approx(
        info["floor"] + (3.0 if info["is_success"] else 0.0)
    )


def test_map_decisions_have_one_option_but_still_surface():
    # A single column means every MAP decision has exactly one legal action —
    # but it must still surface as a step (the lookahead obs is trained here).
    from sts2_rl.driver import DecisionKind

    env = shared_env()
    rng = np.random.default_rng(7)
    env.reset(seed=7)
    seen_map = False
    for _ in range(2_000):
        request = env._request
        if request is None:
            break
        if request.kind == DecisionKind.MAP:
            seen_map = True
            assert len(request.legal_actions()) == 1
        mask = env.action_masks()
        _, _, term, trunc, _ = env.step(int(rng.choice(np.flatnonzero(mask))))
        if term or trunc:
            break
    assert seen_map


def test_seeded_episodes_are_deterministic():
    env = shared_env()
    t1, i1, _ = masked_random_episode(env, seed=8)
    t2, i2, _ = masked_random_episode(env, seed=8)
    assert t1 == t2
    assert i1["floor"] == i2["floor"] and i1["is_success"] == i2["is_success"]
    t3, _, _ = masked_random_episode(env, seed=9)
    assert t1 != t3
