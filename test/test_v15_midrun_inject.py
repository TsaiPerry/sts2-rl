"""v15 extension-exposure plan Task 1: --deck-inject-midrun / --deck-inject-midrun-prob.

Mid-run sibling of v14's reset-time deck_inject: on a floor advance, with
probability deck_inject_midrun_prob, append ONE dead-list package
(unupgraded) to the live deck. Env-side stochasticity only -- no action
forcing, no masks. Off by default (packages None / prob 0.0) -- zero extra
RNG draws, so a default env stays bit-identical (same zero-draw contract as
deck_inject / branch_prob).
"""
import json

import numpy as np

from sts2_rl.run_env import STS2RunEnv


def _mk_midrun_json(tmp_path):
    p = tmp_path / "midrun.json"
    p.write_text(json.dumps({"packages": [["vicious"]]}))
    return str(p)


def test_midrun_inject_appends_on_floor_advance(tmp_path):
    env = STS2RunEnv(deck_inject_midrun=_mk_midrun_json(tmp_path),
                      deck_inject_midrun_prob=1.0)
    env.reset(seed=3)
    base = len(env._run.deck)
    # drive until the first floor advance (mask-legal first actions)
    for _ in range(400):
        floor_before = env._run.total_floor
        legal = np.flatnonzero(env.action_masks())
        obs, r, term, trunc, info = env.step(int(legal[0]))
        if env._run.total_floor > floor_before:
            break
        if term or trunc:
            assert False, "episode ended before any floor advance"
    assert len(env._run.deck) > base
    assert any(type(c).__name__ == "ViciousCard" for c in env._run.deck)


def test_midrun_inject_off_draws_no_rng(tmp_path):
    # zero-draw contract: default env must be bit-identical with the flag off
    def rollout(**kw):
        env = STS2RunEnv(**kw)
        env.reset(seed=7)
        out = []
        for _ in range(60):
            legal = np.flatnonzero(env.action_masks())
            obs, r, *_, info = env.step(int(legal[0]))
            out.append((round(float(r), 6), info["floor"]))
        return out
    assert rollout() == rollout(deck_inject_midrun=_mk_midrun_json(tmp_path),
                                 deck_inject_midrun_prob=0.0)
