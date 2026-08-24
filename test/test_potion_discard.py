"""Voluntary potion discard (v22 spec §A1): the belt's Discard button as an
answer namespace, mirroring the drink overlay. Out of combat only; gated on
can_remove_potions ONLY (no usage-class / custom-usability filter — game
parity: NPotionPopup gates Discard on CanRemovePotions alone)."""
from types import SimpleNamespace

from sts2_rl.driver import (
    DecisionKind, DecisionRequest, POTION_ACTION_BASE,
    POTION_DISCARD_ACTION_BASE)
from sts2_rl.run_env import STS2RunEnv


def _env_with_belt(pids):
    env = STS2RunEnv()
    env.reset(seed=0)
    run = env._run
    for i, pid in enumerate(pids):
        run.potions[i] = SimpleNamespace(id=pid, usage="combat_only")
    return env, run


def test_discard_actions_lists_every_held_potion_any_usage():
    env, run = _env_with_belt(["fire_potion", "blood_potion"])
    req = DecisionRequest(kind=DecisionKind.REST, run=run)
    assert req.discard_actions() == [
        POTION_DISCARD_ACTION_BASE + 0, POTION_DISCARD_ACTION_BASE + 1]


def test_discard_actions_empty_in_combat_and_when_belt_locked():
    env, run = _env_with_belt(["fire_potion"])
    req = DecisionRequest(kind=DecisionKind.REST, run=run)
    req.in_combat = True
    assert req.discard_actions() == []
    req2 = DecisionRequest(kind=DecisionKind.REST, run=run)
    req2.combat = object()
    assert req2.discard_actions() == []


def test_legal_actions_includes_discards():
    env, run = _env_with_belt(["fire_potion"])
    req = DecisionRequest(kind=DecisionKind.REST, run=run)
    assert POTION_DISCARD_ACTION_BASE + 0 in req.legal_actions()


def test_action_space_gains_tail_discard_block():
    from sts2_rl import run_env as re_
    assert re_.DISCARD_BASE == re_.POTION_BASE + re_.MAX_POTION_SLOTS
    assert re_.N_ACTIONS == re_.DISCARD_BASE + re_.MAX_POTION_SLOTS


def test_translate_and_mask_round_trip_discard():
    import numpy as np
    from sts2_rl.run_env import DISCARD_BASE
    env, run = _env_with_belt(["fire_potion"])
    req = DecisionRequest(kind=DecisionKind.REST, run=run)
    env._request = req
    mask = env.action_masks()
    assert mask[DISCARD_BASE + 0] and not mask[DISCARD_BASE + 1]
    assert env._translate(DISCARD_BASE + 0, req) == POTION_DISCARD_ACTION_BASE
    assert env._translate(DISCARD_BASE + 1, req) is None


def test_discard_step_records_discarded_not_used(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.75)
    env = STS2RunEnv()
    env.reset(seed=0)
    run = env._run
    run.potions[0] = SimpleNamespace(id="fire_potion")
    env._sync_potion_track(False)                 # track the pickup
    run.total_floor = 5
    env._build_obs = lambda: {"f": __import__("numpy").zeros(1, "float32"),
                              "i": __import__("numpy").zeros(1, "int32")}
    env._request = DecisionRequest(kind=DecisionKind.REST, run=run)
    env._translate = lambda a, r: POTION_DISCARD_ACTION_BASE + 0
    env._count_behavior = lambda r, a: None
    env._switch = lambda a: run.potions.__setitem__(0, None)
    env.step(0)
    (rec,) = env._ep_potion_holds
    assert rec["outcome"] == "discarded" and rec["id"] == "fire_potion"
    assert rec["v"] == 0.75
    assert env._ep_potions_discarded == 1
    assert env._ep_potions_used == 0              # NOT a drink
    assert env._drink_slot(env._request, POTION_DISCARD_ACTION_BASE) is None


def test_discard_pays_minus_k_and_churn_nets_zero(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    env = STS2RunEnv(potion_potential_scale=0.5)
    env.reset(seed=0)
    run = env._run
    run.potions[0] = SimpleNamespace(id="fire_potion")
    env._sync_potion_track(False)
    env._belt_base = 1
    env._build_obs = lambda: {"f": __import__("numpy").zeros(1, "float32"),
                              "i": __import__("numpy").zeros(1, "int32")}
    env._count_behavior = lambda r, a: None
    # discard: -k
    env._request = DecisionRequest(kind=DecisionKind.REST, run=run)
    env._translate = lambda a, r: POTION_DISCARD_ACTION_BASE + 0
    env._switch = lambda a: run.potions.__setitem__(0, None)
    _, r_discard, _, _, _ = env.step(0)
    # pickup: +k
    env._request = DecisionRequest(kind=DecisionKind.REST, run=run)
    env._translate = lambda a, r: 0
    env._switch = lambda a: run.potions.__setitem__(0, SimpleNamespace(id="blood_potion"))
    _, r_pickup, _, _, _ = env.step(0)
    assert r_discard == -0.5 and r_pickup == 0.5
    assert r_discard + r_pickup == 0.0            # churn exploit priced out


def test_run_layout_scores_discards_from_belt_rows():
    from sts2_rl.models import run_action_layout, ENTSET_HEAD_VERSION
    from sts2_rl.run_env import DISCARD_BASE, MAX_POTION_SLOTS, N_ACTIONS
    layout = run_action_layout()
    assert layout.n_actions == N_ACTIONS
    assert (DISCARD_BASE, MAX_POTION_SLOTS, "run.potions") in layout.pointer_blocks
    assert ENTSET_HEAD_VERSION == 5


def test_version4_checkpoint_refused():
    import pytest
    from sts2_rl import checkpoints, models

    spec = checkpoints.ModelSpec(env_kind="run", arch="entset")
    ck = {
        "env_kind": "run",
        "arch": "entset",
        "obs_schema": checkpoints.obs_schema_version(spec),
        "head_version": 4,
    }
    with pytest.raises(SystemExit, match="head_version"):
        checkpoints.check_checkpoint(ck, spec, obs_dim=(1, 1), n_actions=1)


def test_voluntary_skip_records_offer_context():
    env = STS2RunEnv()
    env.reset(seed=0)
    run = env._run
    run.potions[0] = SimpleNamespace(id="blood_potion")
    run.total_floor = 7
    req = DecisionRequest(kind=DecisionKind.REWARD_POTION, run=run,
                          potion=SimpleNamespace(id="fire_potion"))
    env._count_behavior(req, 1)
    assert env._ep_potion_skips == [
        {"offered": "fire_potion", "belt": ["blood_potion"], "floor": 7}]
    assert env._ep_potion_rewards_skipped == 1


def test_report_discard_and_skip_metrics():
    from sts2_rl.evaluation import RunEvalReport
    holds = (
        {"id": "fire_potion", "held": 2, "outcome": "discarded", "room": "none",
         "v": 0.5, "pickup_floor": 1, "floor": 3},
        {"id": "fire_potion", "held": 1, "outcome": "used", "room": "elite",
         "v": 0.5, "pickup_floor": 4, "floor": 5},
    )
    rep = RunEvalReport(
        episodes=2, floors=(9, 9), acts=(0, 0), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(5, 5),
        seeds=(1, 2), returns=(0.0, 0.0), potion_holds=holds,
        potions_discarded=(1, 0),
        potion_skips=(
            {"offered": "fire_potion", "belt": [], "floor": 2},
            {"offered": "block_potion", "belt": ["a", "b"], "floor": 6},
        ))
    assert rep.mean_potions_discarded == 0.5
    assert rep.potion_hold_table["fire_potion"]["discarded"] == 1
    assert rep.potion_skip_belt_histogram == {0: 1, 1: 0, 2: 1, 3: 0}
