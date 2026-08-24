"""Per-potion hold-duration metric (2026-08-23, Perry): how long each potion
instance is HELD between pickup and use / loss / episode end, in floors,
plus what it was used on. Eval-only (info key ``ep_potion_holds``), never
reward. Pooled by ``RunEvalReport.potion_hold_table`` and written by
``write_potions_csv``."""
from types import SimpleNamespace

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind, DecisionRequest, POTION_ACTION_BASE
from sts2_rl.rooms import RoomType
from sts2_rl.run_env import COMBAT_POTION_BASE, STS2RunEnv
from test_v8_rewards import _add_potion, _combat_request_with_player, _remove_potion


def _stub_obs(env):
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}


def _noop_step(env, mutate=lambda: None, floor=None):
    """One step() whose only effect is `mutate()` (run as the driver would),
    with the run standing on `floor` if given."""
    _stub_obs(env)
    if floor is not None:
        env._run.total_floor = floor
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: mutate()
    return env.step(0)


def _pickup(env, floor, pid="blood_potion"):
    def add():
        run = env._run
        run.potions[run.potions.index(None)] = SimpleNamespace(id=pid)
    return _noop_step(env, add, floor)


def test_pickup_then_belt_drink_records_used_with_hold_floors(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.5)
    env = STS2RunEnv()
    env.reset(seed=0)
    _pickup(env, floor=3)
    assert env._ep_potion_holds == []           # nothing resolved yet
    # drink it from the belt on floor 7
    _stub_obs(env)
    env._run.total_floor = 7
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    env.step(0)
    assert env._ep_potion_holds == [
        {"id": "blood_potion", "held": 4, "outcome": "used", "room": "none",
         "v": 0.5, "pickup_floor": 3, "floor": 7}]


def test_in_combat_pair_drink_records_room_and_v(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.25)
    env = STS2RunEnv()
    env.reset(seed=0)
    _pickup(env, floor=2, pid="fire_potion")
    env._run.total_floor = 5
    env._count_behavior = lambda request, answer: None
    req = _combat_request_with_player(env, RoomType.ELITE, hp=50, max_hp=100)
    req.combat.player.potions = env._run.potions
    env._request = req
    env._translate = lambda action, request: int(action)
    env._switch = lambda answer: _remove_potion(env)
    env.step(COMBAT_POTION_BASE)              # slot 0, enemy 0
    (rec,) = env._ep_potion_holds
    assert rec["id"] == "fire_potion" and rec["outcome"] == "used"
    assert rec["held"] == 3 and rec["room"] == "elite" and rec["v"] == 0.25


def test_in_combat_drink_is_not_retracked_before_the_belt_sync(monkeypatch):
    """Real combat shape: the combat belt is a separate LIST holding the SAME
    potion objects; an in-combat drink nulls the combat slot while
    run.potions still shows the object until finish_combat syncs it. The
    drink must be recorded once (used) and the object must neither be
    re-tracked as a new pickup nor reported 'lost' when the sync removes it."""
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.5)
    env = STS2RunEnv()
    env.reset(seed=0)
    _pickup(env, floor=2, pid="fire_potion")
    env._run.total_floor = 6
    env._count_behavior = lambda request, answer: None
    req = _combat_request_with_player(env, RoomType.MONSTER, hp=50, max_hp=100)
    combat_belt = list(env._run.potions)             # same objects, different list
    req.combat.player.potions = combat_belt
    env._request = req
    env._translate = lambda action, request: int(action)
    env._switch = lambda answer: combat_belt.__setitem__(0, None)   # run.potions untouched
    env.step(COMBAT_POTION_BASE)
    assert [r["outcome"] for r in env._ep_potion_holds] == ["used"]
    assert env._ep_potion_holds[0]["held"] == 4
    # finish_combat-style sync on a later step: the object leaves run.potions
    _noop_step(env, lambda: _remove_potion(env), floor=7)
    assert [r["outcome"] for r in env._ep_potion_holds] == ["used"]   # no 'lost', no re-pickup
    assert env._potion_track == {}


def test_untracked_in_combat_potion_drunk_records_zero_hold(monkeypatch):
    """A potion that never reached run.potions (e.g. created and drunk inside
    one combat) is still recorded, with held 0."""
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.0)
    env = STS2RunEnv()
    env.reset(seed=0)
    env._run.total_floor = 9
    env._count_behavior = lambda request, answer: None
    req = _combat_request_with_player(env, RoomType.MONSTER, hp=50, max_hp=100)
    req.combat.player.potions = [SimpleNamespace(id="swift_potion"), None, None]
    env._request = req
    env._translate = lambda action, request: int(action)
    env._switch = lambda answer: None
    env.step(COMBAT_POTION_BASE)
    (rec,) = env._ep_potion_holds
    assert rec == {"id": "swift_potion", "held": 0, "outcome": "used", "room": "normal",
                   "v": 0.0, "pickup_floor": 9, "floor": 9}


def test_non_drink_loss_records_lost():
    env = STS2RunEnv()
    env.reset(seed=0)
    _pickup(env, floor=1)
    _noop_step(env, lambda: _remove_potion(env), floor=4)   # event discard
    (rec,) = env._ep_potion_holds
    assert rec["outcome"] == "lost" and rec["held"] == 3 and rec["room"] == "none"


def test_held_at_episode_end_records_held_and_info_carries_list():
    env = STS2RunEnv()
    env.reset(seed=0)
    _pickup(env, floor=2)
    _pickup(env, floor=6, pid="block_potion")

    def die():
        env._result = SimpleNamespace(victory=False, hp=0, max_hp=80, decisions=3)
    _, _, terminated, _, info = _noop_step(env, die, floor=10)
    assert terminated
    recs = info["ep_potion_holds"]
    assert sorted((r["id"], r["held"], r["outcome"]) for r in recs) == [
        ("block_potion", 4, "held"), ("blood_potion", 8, "held")]


def test_reset_clears_tracker():
    env = STS2RunEnv()
    env.reset(seed=0)
    _pickup(env, floor=2)
    env.reset(seed=1)
    assert env._ep_potion_holds == [] and env._potion_track == {}


# ── report / CSV ────────────────────────────────────────────────────────────

def test_report_hold_table_and_csv(tmp_path):
    import csv

    from sts2_rl.evaluation import (
        POTIONS_CSV_FIELDS, RunEvalReport, write_potions_csv)

    holds = (
        {"id": "fire_potion", "held": 2, "outcome": "used", "room": "elite", "v": 0.5, "pickup_floor": 1, "floor": 3},
        {"id": "fire_potion", "held": 6, "outcome": "used", "room": "normal", "v": 1.0, "pickup_floor": 1, "floor": 7},
        {"id": "fire_potion", "held": 9, "outcome": "held", "room": "none", "v": None, "pickup_floor": 2, "floor": 11},
        {"id": "blood_potion", "held": 0, "outcome": "used", "room": "boss", "v": 0.0, "pickup_floor": 15, "floor": 15},
        {"id": "blood_potion", "held": 3, "outcome": "lost", "room": "none", "v": None, "pickup_floor": 4, "floor": 7},
    )
    rep = RunEvalReport(
        episodes=1, floors=(11,), acts=(0,), victories=(False,), truncations=(False,),
        hp_left=(0,), decisions=(5,), seeds=(1,), returns=(0.0,), potion_holds=holds)
    table = rep.potion_hold_table
    assert list(table) == ["fire_potion", "blood_potion"]          # most picked first
    fp = table["fire_potion"]
    assert fp["picked"] == 3 and fp["used"] == 2 and fp["held"] == 1 and fp["lost"] == 0
    assert fp["mean_hold_used"] == pytest.approx(4.0)
    assert fp["mean_hold_all"] == pytest.approx(17 / 3)
    assert fp["v_at_use"] == pytest.approx(0.75)
    assert fp["tier_share"] == pytest.approx(0.5)
    bp = table["blood_potion"]
    assert bp["used"] == 1 and bp["lost"] == 1 and bp["tier_share"] == pytest.approx(1.0)
    assert rep.mean_potion_hold_used == pytest.approx((2 + 6 + 0) / 3)
    assert rep.potion_hold_histogram == {"0": 1, "1": 0, "2-3": 2, "4-6": 1, "7+": 1}

    assert POTIONS_CSV_FIELDS == ("policy", "potion", "picked", "used", "held", "lost",
                                  "discarded", "mean_hold_used", "mean_hold_all",
                                  "v_at_use", "tier_share")
    path = tmp_path / "x.potions.csv"
    write_potions_csv(str(path), [("p", rep)])
    rows = list(csv.DictReader(open(path, newline="")))
    assert rows[0]["potion"] == "fire_potion" and rows[0]["picked"] == "3"
    assert rows[0]["discarded"] == "0"
    assert rows[1]["potion"] == "blood_potion" and rows[1]["lost"] == "1"


def test_evaluate_run_collects_potion_holds():
    import random

    from sts2_rl.evaluation import evaluate_run
    from sts2_rl.run_env import masked_random_run_policy
    rep = evaluate_run(masked_random_run_policy(random.Random(0)), episodes=1, seed=0,
                       env=STS2RunEnv())
    assert isinstance(rep.potion_holds, tuple)
    assert all({"id", "held", "outcome", "room", "v", "pickup_floor", "floor"} <= set(r) for r in rep.potion_holds)
