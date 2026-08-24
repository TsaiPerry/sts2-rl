"""v20 drill environment + boss-HP-loss term (plan
2026-08-19-v20-drill-env-plan.md, Tasks 3/3b/5).

Covers: pool bucketing/validation, the zero-rng-draw contract when drills
are off, drill-reset state fidelity at the obs-visible level (deck/relics/
hp/gold/potions/floor/act), boss-identity forcing for boss drills, the
no-floor-windfall property of the first drill step, drill episodes playing
to natural termination for every room type, and the boss-hp-loss penalty's
pay-once/won-and-lost/K=0-inert semantics.
"""
from __future__ import annotations

import json
import random

import numpy as np
import pytest

from sts2_rl.run_env import STS2RunEnv, masked_random_run_policy
from sts2_rl.snapshots import (
    SNAPSHOT_SCHEMA,
    CardSnap,
    RelicSnap,
    Snapshot,
    _snapshot_to_json,
    encounter_registry,
)


# â”€â”€ bank builders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _snap(encounter_id: str, room_type: str, act: int, floor: int, *,
          hp: int = 55, max_hp: int = 80, gold: int = 137,
          deck: "tuple[CardSnap, ...] | None" = None) -> Snapshot:
    return Snapshot(
        deck=deck if deck is not None else (
            CardSnap("strike", False, None, None, None),
            CardSnap("strike", True, None, None, None),
            CardSnap("defend", False, None, None, None),
            CardSnap("defend", False, None, None, None),
            CardSnap("bash", True, None, None, None),
        ),
        relics=(RelicSnap("burning_blood", 0), RelicSnap("girya", 2)),
        hp=hp,
        max_hp=max_hp,
        potion_slots=("fire_potion", None, None),
        act=act,
        encounter_id=encounter_id,
        gold=gold,
        floor=floor,
        room_type=room_type,
        provenance={"seed": 0, "ascension": 0, "episode_decisions": 3},
    )


def _write_bank(path, snaps) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"snapshot_schema": SNAPSHOT_SCHEMA}) + "\n")
        for s in snaps:
            fh.write(json.dumps(_snapshot_to_json(s)) + "\n")
    return str(path)


def _standard_bank(tmp_path):
    """One snapshot per v20 pool (+ an act-1 monster for room coverage)."""
    reg = encounter_registry()
    assert "vantom_boss" in reg and "queen_boss" in reg
    return _write_bank(tmp_path / "bank.jsonl", [
        _snap("vantom_boss", "BOSS", 0, 16),
        _snap("knowledge_demon_boss", "BOSS", 1, 33),
        _snap("queen_boss", "BOSS", 2, 50),
        _snap("bygone_effigy_elite", "ELITE", 0, 6),
        _snap("terror_eel_elite", "ELITE", 1, 22),
        _snap("decimillipede_elite", "ELITE", 2, 40),
        _snap("fuzzy_wurm_crawler", "MONSTER", 0, 2),
    ])


V20_POOLS = {"a1boss": 0.2, "a2boss": 0.2, "a3boss": 0.2,
             "a2elite": 0.2, "a3elite": 0.2}


def _drill_env(bank, *, prob=1.0, pools=None, weights=None, **kwargs):
    return STS2RunEnv(
        drill_snapshots=bank, drill_prob=prob,
        drill_pools=pools, drill_encounter_weights=weights, **kwargs)


def _play_out(env, seed, rng_seed=0, max_steps=100_000):
    """Play an episode with the masked-random policy to natural end.
    Returns (info, total_reward, first_info)."""
    policy = masked_random_run_policy(random.Random(rng_seed))
    obs, info = env.reset(seed=seed)
    first_info = dict(info)
    total = 0.0
    terminated = truncated = False
    while not (terminated or truncated):
        mask = env.action_masks()
        action = int(policy(env, obs, mask))
        obs, reward, terminated, truncated, info = env.step(action)
        total += float(reward)
    return info, total, first_info


# â”€â”€ construction validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_drill_prob_without_bank_raises():
    with pytest.raises(ValueError, match="drill_snapshots"):
        STS2RunEnv(drill_prob=0.5)


def test_named_empty_pool_raises(tmp_path):
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap("vantom_boss", "BOSS", 0, 16)])
    with pytest.raises(ValueError, match="a3elite"):
        _drill_env(bank, pools={"a1boss": 0.5, "a3elite": 0.5})


def test_v20_pools_all_covered_by_standard_bank(tmp_path):
    env = _drill_env(_standard_bank(tmp_path), pools=dict(V20_POOLS))
    keys = {k for k, _m, _s, _w in env._drill_pools}
    assert keys == set(V20_POOLS)


def test_schema1_bank_rejected(tmp_path):
    path = tmp_path / "old.jsonl"
    path.write_text(json.dumps({"snapshot_schema": 1}) + "\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot_schema 1"):
        STS2RunEnv(drill_snapshots=str(path), drill_prob=0.5)


# â”€â”€ zero-rng-draw contract â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_drills_off_is_byte_identical(tmp_path):
    """A bank loaded with drill_prob=0.0, and no bank at all, must produce
    the same episode stream (the deck_random_prob zero-draw precedent)."""
    def first_decisions(env):
        out = []
        for ep in range(3):
            obs, _ = env.reset(seed=ep)
            rng = random.Random(7)
            for _ in range(20):
                mask = env.action_masks()
                action = int(rng.choice(np.flatnonzero(mask)))
                out.append(action)
                obs, _r, term, trunc, _i = env.step(action)
                if term or trunc:
                    break
        return out

    plain = first_decisions(STS2RunEnv())
    with_bank = first_decisions(_drill_env(_standard_bank(tmp_path), prob=0.0))
    assert plain == with_bank


# â”€â”€ drill reset state fidelity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_boss_drill_state_matches_snapshot(tmp_path):
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap("vantom_boss", "BOSS", 0, 16)])
    env = _drill_env(bank, pools={"a1boss": 1.0})
    obs, info = env.reset(seed=0)
    run = env._run
    # First decision is inside the injected boss combat.
    assert env._request is not None and env._request.combat is not None
    assert env._request.combat.room_type.name == "BOSS"
    assert {type(e).__name__ for e in env._request.combat.enemies} == {"Vantom"}
    # Run state rebuilt from the snapshot.
    assert run.act_index == 0
    assert run.total_floor == 16 and info["floor"] == 16
    assert run.gold == 137
    assert run.max_hp == 80
    assert sorted(c.id for c in run.deck) == ["bash", "defend", "defend",
                                              "strike", "strike"]
    assert sum(c.upgrade_level for c in run.deck) == 2
    assert [r.id for r in run.relics] == ["burning_blood", "girya"]
    assert [p.id if p is not None else None for p in run.potions][0] == "fire_potion"
    # Boss identity forced: the map/obs boss is the snapshot's boss.
    assert run.room_set.registry[run.room_set.boss_key].id == "vantom_boss"
    assert run.current_point is run.map.boss_point


def test_act3_boss_drill_lands_in_act3(tmp_path):
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap("queen_boss", "BOSS", 2, 50)])
    env = _drill_env(bank, pools={"a3boss": 1.0})
    env.reset(seed=0)
    run = env._run
    assert run.act_index == 2
    assert run.total_floor == 50
    assert run.room_set.registry[run.room_set.boss_key].id == "queen_boss"


def test_elite_drill_positions_on_grid(tmp_path):
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap("terror_eel_elite", "ELITE", 1, 22)])
    env = _drill_env(bank, pools={"a2elite": 1.0})
    env.reset(seed=0)
    run = env._run
    assert run.act_index == 1
    assert run.total_floor == 22
    assert env._request.combat.room_type.name == "ELITE"
    # On the grid (not the Ancient, not the boss point).
    assert run.current_point is not run.map.boss_point
    assert run.current_point.row >= 1


def test_first_drill_step_pays_no_floor_windfall(tmp_path):
    """Starting at floor 16 must not pay 16 floors of reward on step 1."""
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap("vantom_boss", "BOSS", 0, 16)])
    env = _drill_env(bank, pools={"a1boss": 1.0},
                     floor_rewards_by_act=(1.0, 1.5, 2.0))
    obs, _ = env.reset(seed=0)
    mask = env.action_masks()
    action = int(np.flatnonzero(mask)[0])
    _obs, reward, _t, _tr, _i = env.step(action)
    # One in-combat step: no floor advance, so |reward| stays far below one
    # floor's worth x 16.
    assert abs(reward) < 5.0


# â”€â”€ drill episodes run to natural termination â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.mark.parametrize("encounter_id,room,act,floor,pool", [
    ("vantom_boss", "BOSS", 0, 16, "a1boss"),
    ("terror_eel_elite", "ELITE", 1, 22, "a2elite"),
    ("fuzzy_wurm_crawler", "MONSTER", 0, 2, "a1monster"),
])
def test_drill_episode_plays_to_natural_end(tmp_path, encounter_id, room,
                                            act, floor, pool):
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap(encounter_id, room, act, floor)])
    env = _drill_env(bank, pools={pool: 1.0})
    info, _total, first = _play_out(env, seed=0)
    # Ended (win or death), not stuck; started at the snapshot floor and
    # ended at or past it.
    assert "is_success" in info
    assert first["floor"] == floor
    assert info["floor"] >= floor


def test_boss_drill_win_advances_act(tmp_path):
    """A won act-1 boss drill must advance to act 2 (continue-to-end
    semantics, locked decision 2). Stacked deck so the random policy wins."""
    strong = tuple(CardSnap("bash", True, None, None, None) for _ in range(5))
    bank = _write_bank(
        tmp_path / "b.jsonl",
        [_snap("vantom_boss", "BOSS", 0, 16, hp=999, max_hp=999,
               deck=strong)])
    env = _drill_env(bank, pools={"a1boss": 1.0})
    info, _total, _first = _play_out(env, seed=0)
    # 999 HP vs the act-1 boss: the run must survive into act >= 1
    # (0-based), proving the post-boss advance_act path ran.
    assert info["act"] >= 1


# â”€â”€ boss-hp-loss penalty (Task 3b) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _boss_env(bank, k, **kwargs):
    return _drill_env(bank, pools={"a1boss": 1.0},
                      boss_hp_loss_penalty=k, **kwargs)


def test_boss_hp_lost_counter_and_penalty(tmp_path):
    """ep_boss_hp_lost tracks HP lost in the boss fight, and the K>0 return
    differs from K=0 by exactly K * lost / max_hp on the same trajectory."""
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap("vantom_boss", "BOSS", 0, 16, hp=80)])
    info0, total0, _ = _play_out(_boss_env(bank, 0.0), seed=0, rng_seed=3)
    info2, total2, _ = _play_out(_boss_env(bank, 2.0), seed=0, rng_seed=3)
    # Identical trajectory (same seeds, reward change doesn't touch rng).
    assert info0["floor"] == info2["floor"]
    assert info0["ep_boss_hp_lost"] == info2["ep_boss_hp_lost"]
    lost = info0["ep_boss_hp_lost"]
    assert lost > 0    # a random policy does not no-hit Vantom
    assert total0 - total2 == pytest.approx(2.0 * lost / 80, abs=1e-6)


def test_boss_hp_penalty_pays_on_loss_too(tmp_path):
    """A run that DIES in the boss fight still books its boss HP loss."""
    weak = (CardSnap("strike", False, None, None, None),)
    bank = _write_bank(
        tmp_path / "b.jsonl",
        [_snap("vantom_boss", "BOSS", 0, 16, hp=10, max_hp=10, deck=weak)])
    env = _boss_env(bank, 2.0)
    info, _total, _ = _play_out(env, seed=0)
    assert not info.get("is_success", False)
    assert info["ep_boss_hp_lost"] == 10   # entered at 10, died at 0


def test_non_boss_fights_never_book_boss_hp(tmp_path):
    bank = _write_bank(tmp_path / "b.jsonl",
                       [_snap("fuzzy_wurm_crawler", "MONSTER", 0, 2,
                              hp=10, max_hp=10,
                              deck=(CardSnap("strike", False, None, None,
                                             None),))])
    env = _drill_env(bank, pools={"a1monster": 1.0},
                     boss_hp_loss_penalty=2.0)
    info, _total, _ = _play_out(env, seed=0)
    if not info.get("is_success", False) and info["floor"] == 2:
        # Died in the monster fight: hp was lost, but never in a BOSS combat.
        assert info["ep_boss_hp_lost"] == 0


# â”€â”€ pool sampling statistics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_pool_masses_respected(tmp_path):
    bank = _standard_bank(tmp_path)
    env = _drill_env(bank, pools={"a1boss": 0.5, "a2elite": 0.5})
    counts = {"vantom_boss": 0, "terror_eel_elite": 0}
    for i in range(60):
        snap = env._sample_drill_snapshot()
        counts[snap.encounter_id] += 1
    # Both pools drawn from; a vanished pool means the mass walk is broken.
    assert counts["vantom_boss"] > 5
    assert counts["terror_eel_elite"] > 5


def test_encounter_weights_bias_within_pool(tmp_path):
    reg = encounter_registry()
    assert "ceremonial_beast_boss" in reg
    bank = _write_bank(tmp_path / "b.jsonl", [
        _snap("vantom_boss", "BOSS", 0, 16),
        _snap("ceremonial_beast_boss", "BOSS", 0, 16),
    ])
    env = _drill_env(bank, pools={"a1boss": 1.0},
                     weights={"vantom_boss": 20.0})
    counts = {"vantom_boss": 0, "ceremonial_beast_boss": 0}
    for _ in range(100):
        counts[env._sample_drill_snapshot().encounter_id] += 1
    assert counts["vantom_boss"] > counts["ceremonial_beast_boss"] * 3
