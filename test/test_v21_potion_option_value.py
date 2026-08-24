"""v21 potion opportunity-value term (spec 2026-08-22-v21-potion-option-value-design.md)."""
from types import SimpleNamespace

import pytest

from sts2_rl.actmap import MapPoint, MapPointType
from sts2_rl.rooms import RoomType


def _chain(*types):
    """A straight path of MapPoints rows 0..n with the given point types;
    returns the list (index = row)."""
    pts = [MapPoint(3, r) for r in range(len(types))]
    for p, t in zip(pts, types):
        p.point_type = t
    for a, b in zip(pts, pts[1:]):
        a.add_child(b)
    return pts


def _run(point, room=RoomType.MONSTER):
    return SimpleNamespace(current_point=point, current_room_type=room)


def test_elites_ahead_counts_transitive_children_excluding_current():
    from sts2_rl.run_env import elites_ahead

    pts = _chain(MapPointType.ELITE, MapPointType.MONSTER, MapPointType.ELITE,
                 MapPointType.MONSTER, MapPointType.ELITE)
    assert elites_ahead(_run(pts[0])) == 2      # the current ELITE is not "ahead"
    assert elites_ahead(_run(pts[2])) == 1
    assert elites_ahead(_run(pts[4])) == 0


def test_elites_ahead_dedupes_converging_paths():
    from sts2_rl.run_env import elites_ahead

    a, b, c, e = MapPoint(1, 0), MapPoint(0, 1), MapPoint(2, 1), MapPoint(1, 2)
    e.point_type = MapPointType.ELITE
    a.add_child(b); a.add_child(c); b.add_child(e); c.add_child(e)
    assert elites_ahead(_run(a)) == 1


def test_elites_ahead_none_point_is_zero():
    from sts2_rl.run_env import elites_ahead
    assert elites_ahead(_run(None)) == 0


def test_potion_option_value_arithmetic():
    from sts2_rl.run_env import POTION_OPTION_V_REF, potion_option_value

    assert POTION_OPTION_V_REF == 3
    pts = _chain(MapPointType.MONSTER, MapPointType.ELITE, MapPointType.ELITE,
                 MapPointType.MONSTER, MapPointType.BOSS)
    # whole act ahead: 2 elites + boss = 3 -> 1.0
    assert potion_option_value(_run(pts[0])) == pytest.approx(1.0)
    # inside the first elite: 1 elite + boss -> 2/3 (current not counted)
    assert potion_option_value(_run(pts[1], RoomType.ELITE)) == pytest.approx(2 / 3)
    # at the boss: boss_ahead = 0 -> 0
    assert potion_option_value(_run(pts[4], RoomType.BOSS)) == pytest.approx(0.0)


def test_potion_option_value_caps_at_one():
    from sts2_rl.run_env import potion_option_value
    pts = _chain(*([MapPointType.MONSTER] + [MapPointType.ELITE] * 5))
    assert potion_option_value(_run(pts[0])) == pytest.approx(1.0)


# ── Task 2: the reward clause ────────────────────────────────────────────

import numpy as np

from sts2_rl.driver import DecisionKind, DecisionRequest, POTION_ACTION_BASE
from sts2_rl.run_env import COMBAT_POTION_BASE, STS2RunEnv
from test_v8_rewards import (               # the v8 step()-level harness
    _add_potion, _combat_request_with_player, _remove_potion, _seed_potion)


def _stub_obs(env):
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}


def test_default_kwargs_inert_for_option_value():
    env = STS2RunEnv()
    assert env._potion_option_value == 0.0
    assert env._potion_option_expiry is False


def test_belt_drink_pays_k_times_v(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.5)
    env = STS2RunEnv(potion_option_value=2.0)
    env.reset(seed=0)
    _seed_potion(env)
    _stub_obs(env)
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(-1.0)             # 2.0 * 0.5
    assert env._ep_potion_v_at_use == pytest.approx(0.5)


def test_in_combat_pair_drink_pays_k_times_v(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.25)
    env = STS2RunEnv(potion_option_value=2.0)
    env.reset(seed=0)
    _seed_potion(env)
    env._count_behavior = lambda request, answer: None
    env._request = _combat_request_with_player(env, RoomType.ELITE, hp=50, max_hp=100)
    env._translate = lambda action, request: int(action)
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(COMBAT_POTION_BASE)      # slot 0, enemy 0
    assert reward == pytest.approx(-0.5)
    assert env._ep_potion_v_at_use == pytest.approx(0.25)


def test_non_drink_actions_pay_nothing(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 1.0)
    env = STS2RunEnv(potion_option_value=2.0)
    env.reset(seed=0)
    _seed_potion(env)
    env._count_behavior = lambda request, answer: None
    env._request = _combat_request_with_player(env, RoomType.MONSTER, hp=50, max_hp=100)
    env._translate = lambda action, request: int(action)
    env._switch = lambda answer: None
    _, reward, *_ = env.step(1)                       # a card play
    assert reward == pytest.approx(0.0)
    # a belt LOSS that is not a drink (event discard) pays nothing either
    env._translate = lambda action, request: 0
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(0.0)
    assert env._ep_potion_v_at_use == pytest.approx(0.0)


def _force_end(env, victory: bool):
    """Make the next step() terminate with the given outcome (mirrors the
    harness used by test_v8_rewards/test_v9_rewards' death-expiry tests:
    `self._result is not None` drives `terminated`, `.victory` gates the
    loss-only clauses, and `_info()`/the win branch of step() also read
    `.hp`/`.max_hp`/`.decisions` off it)."""
    env._result = SimpleNamespace(
        victory=victory, hp=0, max_hp=env._run.max_hp, decisions=1)


def test_expiry_charges_held_potions_on_death_only(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.5)
    for victory, expected in ((False, -2.0), (True, 0.0)):
        env = STS2RunEnv(potion_option_value=2.0, potion_option_expiry=True,
                          reward_win=0.0)             # isolate the term under test
        env.reset(seed=0)
        _seed_potion(env); _seed_potion(env)          # two held potions
        _stub_obs(env)
        env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
        env._translate = lambda action, request: 0
        env._count_behavior = lambda request, answer: None
        env._switch = lambda answer, env=env, victory=victory: _force_end(env, victory)
        _, reward, terminated, *_ = env.step(0)
        assert terminated
        assert reward == pytest.approx(expected)      # 2 potions * 2.0 * 0.5 on a loss


def test_expiry_off_by_default_charges_nothing_on_death(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.5)
    env = STS2RunEnv(potion_option_value=2.0)         # expiry False
    env.reset(seed=0)
    _seed_potion(env)
    _stub_obs(env)
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _force_end(env, False)
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(0.0)


def test_info_carries_potion_v_at_use(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    monkeypatch.setattr(run_env_mod, "potion_option_value", lambda run: 0.75)
    env = STS2RunEnv(potion_option_value=1.0)
    env.reset(seed=0)
    _seed_potion(env)
    _stub_obs(env)
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    def _drink_then_die(answer):
        _remove_potion(env); _force_end(env, False)
    env._switch = _drink_then_die
    _, _, terminated, _, info = env.step(0)
    assert terminated
    assert info["ep_potion_v_at_use"] == pytest.approx(0.75)


def _belt_with(env, potion):
    run = env._run
    run.potions[run.potions.index(None)] = potion
    env._belt_base = sum(1 for p in run.potions if p is not None)


def test_heal_potion_at_full_hp_counts_wasted():
    from sts2_rl.potions import BloodPotion
    env = STS2RunEnv()
    env.reset(seed=0)
    _belt_with(env, BloodPotion())
    _stub_obs(env)
    env._run.hp, env._run.max_hp = 100, 100
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)      # heal lands nowhere
    env.step(0)
    assert env._ep_potions_wasted == 1


def test_heal_potion_at_low_hp_not_wasted():
    from sts2_rl.potions import BloodPotion
    env = STS2RunEnv()
    env.reset(seed=0)
    _belt_with(env, BloodPotion())
    _stub_obs(env)
    env._run.hp, env._run.max_hp = 40, 100
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    def _drink(answer):
        _remove_potion(env); env._run.hp = 60                # +20 of a 20 heal
    env._switch = _drink
    env.step(0)
    assert env._ep_potions_wasted == 0


def test_block_potion_with_no_incoming_counts_wasted(monkeypatch):
    import sts2_rl.run_env as run_env_mod
    from sts2_rl.potions import BlockPotion
    monkeypatch.setattr(run_env_mod, "preview_total_incoming", lambda combat: 0)
    env = STS2RunEnv()
    env.reset(seed=0)
    _belt_with(env, BlockPotion())
    env._count_behavior = lambda request, answer: None
    req = _combat_request_with_player(env, RoomType.MONSTER, hp=50, max_hp=100)
    req.combat.player.potions = env._run.potions          # the live combat belt
    env._request = req
    env._translate = lambda action, request: int(action)
    env._switch = lambda answer: _remove_potion(env)
    env.step(COMBAT_POTION_BASE)
    assert env._ep_potions_wasted == 1
    monkeypatch.setattr(run_env_mod, "preview_total_incoming", lambda combat: 12)
    _belt_with(env, BlockPotion())
    env._request = req
    env.step(COMBAT_POTION_BASE)
    assert env._ep_potions_wasted == 1                     # incoming > 0: not wasted


def test_offensive_potion_never_wasted():
    from sts2_rl.potions import FirePotion
    env = STS2RunEnv()
    env.reset(seed=0)
    _belt_with(env, FirePotion())
    env._count_behavior = lambda request, answer: None
    req = _combat_request_with_player(env, RoomType.MONSTER, hp=50, max_hp=100)
    req.combat.player.potions = env._run.potions
    env._request = req
    env._translate = lambda action, request: int(action)
    env._switch = lambda answer: _remove_potion(env)
    env.step(COMBAT_POTION_BASE)
    assert env._ep_potions_wasted == 0


def test_shop_potion_buy_is_counted():
    from sts2_rl.shop import MerchantPotionEntry
    env = STS2RunEnv()
    env.reset(seed=0)
    class _PotionEntry(MerchantPotionEntry):   # isinstance-true stub, no ctor work
        def __init__(self): pass
        is_stocked = True
        enough_gold = True
    shop = SimpleNamespace(all_entries=[_PotionEntry(), SimpleNamespace(is_stocked=True)])
    req = DecisionRequest(kind=DecisionKind.SHOP, run=env._run, shop=shop)
    env._count_behavior(req, 0)          # buys the potion entry
    env._count_behavior(req, 1)          # a non-potion entry
    env._count_behavior(req, 2)          # leave
    assert env._ep_potions_bought == 1

    from test_v8_rewards import _add_potion
    while env._run.has_open_potion_slot:
        _add_potion(env)
    env._count_behavior(req, 0)          # belt full: purchase would be refused
    assert env._ep_potions_bought == 1


def test_potion_reward_skip_vs_forced_decline():
    env = STS2RunEnv()
    env.reset(seed=0)
    req = DecisionRequest(kind=DecisionKind.REWARD_POTION, run=env._run)
    assert env._run.has_open_potion_slot
    env._count_behavior(req, 1)                        # voluntary skip
    env._count_behavior(req, 0)                        # take: not counted
    while env._run.has_open_potion_slot:
        _add_potion(env)
    env._count_behavior(req, 1)                        # forced (belt full)
    assert env._ep_potion_rewards_skipped == 1
    assert env._ep_potion_rewards_forced == 1


def test_potion_relic_pick_counted_on_obtain():
    from sts2_rl.run_env import POTION_RELIC_IDS
    assert {"phial_holster", "alchemical_coffer", "potion_belt", "belt_buckle",
            "delicate_frond", "petrified_toad"} <= set(POTION_RELIC_IDS)
    env = STS2RunEnv()
    env.reset(seed=0)
    _stub_obs(env)
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: env._run.relics.append(SimpleNamespace(id="phial_holster"))
    env.step(0)
    env._switch = lambda answer: env._run.relics.append(SimpleNamespace(id="anchor"))
    env.step(0)
    assert env._ep_potion_relic_picks == 1
    assert env._ep_relics == 2


# ── Task 5: trainer plumbing (EnvSpec + train_torch.py CLI) ─────────────────

def test_envspec_threads_option_value_into_run_env():
    from sts2_rl.vec_env import EnvSpec, build_env
    spec = EnvSpec(kind="run", potion_option_value=0.5, potion_option_expiry=True)
    env = build_env(spec)
    assert env._potion_option_value == 0.5
    assert env._potion_option_expiry is True


def test_train_torch_flags_parse(monkeypatch):
    import sys
    import train_torch                      # parse_args() reads sys.argv (train_torch.py:149)
    monkeypatch.setattr(sys, "argv", ["train_torch.py", "--env", "run",
                                      "--potion-option-value", "0.5", "--potion-option-expiry"])
    args = train_torch.parse_args()
    assert args.potion_option_value == 0.5 and args.potion_option_expiry is True


def test_report_v21_properties_and_csv(tmp_path):
    import csv
    from sts2_rl.evaluation import EPISODE_CSV_FIELDS, RunEvalReport, write_run_csv
    rep = RunEvalReport(
        episodes=2, floors=(10, 20), acts=(0, 1), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(5, 5),
        seeds=(1, 2), returns=(0.0, 0.0),
        potions_used=(2, 2), potions_used_elite=(1, 0), potions_used_boss=(0, 1),
        potion_v_at_use=(1.0, 0.5), potions_wasted=(1, 0), potions_bought=(1, 0),
        potion_rewards_skipped=(0, 1), potion_rewards_forced=(2, 0),
        potion_relic_picks=(0, 1))
    assert rep.mean_potion_v_at_use == pytest.approx(1.5 / 4)
    assert rep.potions_wasted_rate == pytest.approx(1 / 4)
    assert rep.mean_potions_bought == pytest.approx(0.5)
    assert rep.mean_potion_rewards_skipped == pytest.approx(0.5)
    assert rep.mean_potion_rewards_forced == pytest.approx(1.0)
    assert rep.mean_potion_relic_picks == pytest.approx(0.5)
    assert rep.potion_elite_share == pytest.approx(0.5)
    # v22 appended "potions_discarded" at the very end; this slice checks the
    # v21 block that precedes it.
    assert EPISODE_CSV_FIELDS[-7:-1] == ("potion_v_at_use", "potions_wasted", "potions_bought",
                                         "potion_rewards_skipped", "potion_rewards_forced",
                                         "potion_relic_picks")
    ep_path, _ = write_run_csv(str(tmp_path / "out"), [("p", rep)])
    rows = list(csv.DictReader(open(ep_path, newline="")))
    assert rows[0]["potion_v_at_use"] == "1.0" and rows[1]["potions_wasted"] == "0"
    assert rows[0]["potion_rewards_forced"] == "2"


def test_evaluate_run_collects_v21_info_keys():
    """A one-episode evaluate_run on the real env must fill the new tuples
    (zeros are fine; presence is the contract)."""
    import random
    from sts2_rl.evaluation import evaluate_run
    from sts2_rl.run_env import STS2RunEnv, masked_random_run_policy
    # evaluate_run(policy, *, episodes, seed, env) — evaluation.py:636
    rep = evaluate_run(masked_random_run_policy(random.Random(0)), episodes=1, seed=0,
                       env=STS2RunEnv())
    assert len(rep.potion_v_at_use) == 1
    assert len(rep.potions_wasted) == 1
    assert len(rep.potions_bought) == 1
    assert len(rep.potion_rewards_skipped) == 1
    assert len(rep.potion_rewards_forced) == 1
    assert len(rep.potion_relic_picks) == 1


# ── Task 5b: checkpoint provenance stamping ─────────────────────────────

def test_checkpoint_payload_stamps_v21_flags(tmp_path):
    """Mirrors the v20 boss_hp_loss_penalty/drill_* precedent: the reward
    flags a checkpoint trained under must ride along in the payload."""
    from argparse import Namespace

    import torch

    import train_torch
    from sts2_rl.models import MaskedActorCritic

    def make_pair(hidden=(8,), obs_dim=6, n_actions=4):
        model = MaskedActorCritic(obs_dim, n_actions, hidden=hidden)
        return model, torch.optim.Adam(model.parameters())

    def combat_args(**over):
        args = Namespace(
            env="combat", arch="mlp", card_obs="hybrid", hidden=[8],
            save=str(tmp_path / "ckpt.pt"),
            n_envs=train_torch.DEFAULT_N_ENVS, n_steps=train_torch.DEFAULT_N_STEPS,
        )
        for k, v in over.items():
            setattr(args, k, v)
        return args

    model, optimizer = make_pair()

    args = combat_args(potion_option_value=0.5, potion_option_expiry=True)
    payload = train_torch.checkpoint_payload(model, optimizer, 1, args, 0, 0.0)
    assert payload["potion_option_value"] == 0.5
    assert payload["potion_option_expiry"] is True

    # defaults when the flags are absent from the Namespace (getattr fallback)
    args2 = combat_args()
    payload2 = train_torch.checkpoint_payload(model, optimizer, 1, args2, 0, 0.0)
    assert payload2["potion_option_value"] == 0.0 and payload2["potion_option_expiry"] is False
