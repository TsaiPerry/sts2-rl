"""v14 mechanics-exposure plan Task 5: --deck-inject / --deck-inject-prob.

Copies the deck_random_prob/_randomize_deck reset-time pattern: with
probability deck_inject_prob an episode's starting deck gets one randomly
chosen inject "package" (1+ card ids meant to be played together, e.g. a
synergy pair) appended whole, so the policy is never taught a card is dead
by seeing it alone. Off by default (packages None / prob 0.0) -- zero extra
RNG draws, so a default env stays bit-identical.
"""
import argparse
import json

from sts2_rl.run import build_starting_deck
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.vec_env import EnvSpec, build_env

STARTER_DECK_SIZE = len(build_starting_deck())


def _pkg_file(tmp_path, packages):
    p = tmp_path / "inject.json"
    p.write_text(json.dumps({"packages": packages}))
    return str(p)


def test_default_bit_identical():
    env = build_env(EnvSpec(kind="run"))
    assert env._deck_inject_packages is None
    assert env._deck_inject_prob == 0.0


def test_envspec_threads_to_env(tmp_path):
    f = _pkg_file(tmp_path, [["thunderclap"]])
    env = build_env(EnvSpec(kind="run", deck_inject=f, deck_inject_prob=0.5))
    assert env._deck_inject_packages == [["thunderclap"]]
    assert env._deck_inject_prob == 0.5


def test_prob_one_injects_whole_package(tmp_path):
    f = _pkg_file(tmp_path, [["rupture", "bloodletting"]])
    env = STS2RunEnv(deck_inject=f, deck_inject_prob=1.0)
    env.reset(seed=7)
    ids = [c.id for c in env._run.deck]
    assert ids.count("rupture") == 1 and ids.count("bloodletting") == 1
    assert len(ids) == STARTER_DECK_SIZE + 2


def test_prob_zero_never_injects(tmp_path):
    f = _pkg_file(tmp_path, [["rupture"]])
    env = STS2RunEnv(deck_inject=f, deck_inject_prob=0.0)
    env.reset(seed=7)
    assert all(c.id != "rupture" for c in env._run.deck)


def test_cli_threads_to_envspec(tmp_path):
    import train_torch
    f = _pkg_file(tmp_path, [["thunderclap"]])
    ns = argparse.Namespace(env="run", acts=None, card_obs="hybrid",
                            encounter=None, enemy_hp_reward=0.0,
                            win_hp_bonus=0.0, branch_prob=0.0,
                            deck_inject=f, deck_inject_prob=0.5)
    spec = train_torch.env_spec(ns)
    assert spec.deck_inject == f and spec.deck_inject_prob == 0.5
