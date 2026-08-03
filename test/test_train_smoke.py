"""PPO smoke tests: env -> TensorObs -> encoder -> tied action head -> PPO
update, driven through the REAL ``train_torch.main()`` entry point (T? brief
"the whole stack trains" task).

``train_torch.py`` has no separable ``train(args)`` function -- everything
lives under ``main()``, itself driven by ``parse_args()`` off ``sys.argv``.
Re-implementing the rollout/GAE/PPO-update math here would prove nothing
about the real integration (the whole point of this task), so these tests
instead monkeypatch ``sys.argv`` and drive ``main()`` itself at a miniature,
deterministic scale: exactly 1 PPO iteration, a handful of env steps, CPU,
one fixed seed -- matching the run env's known rare indefinite ``env.step()``
hang risk (owned by another workstream): no seed sweeps, no long rollouts,
no timeout wrappers, just small bounded step counts and a loud failure.

Two hooks make ``main()``'s internals observable without touching
``train_torch.py`` or any ``sts2_rl/*.py`` module:

  - ``checkpoints.make_model`` is wrapped to capture the constructed agent
    (``main()`` never returns it -- it's a procedure, not a function).
  - ``sts2_rl.vec_env.SerialVecEnv.step`` is wrapped to record every sampled
    action, so the run-env test can report which action-space blocks (play /
    potion / CHOICE / SELECT / belt-POTION) were actually exercised this
    seed.

Both hooks wrap the real callables and always delegate to them -- nothing
about the trained numbers is faked or short-circuited.
"""
from __future__ import annotations

import csv
import math

import numpy as np
import pytest
import torch

import train_torch
from sts2_rl import checkpoints
from sts2_rl import full_env as full_env_mod
from sts2_rl import vec_env as vec_env_mod


def _drive_main(monkeypatch, argv: list[str]) -> tuple[torch.nn.Module, list[int]]:
    """Run ``train_torch.main()`` under ``argv``, capturing the constructed
    agent and every action sampled during the rollout.

    Returns ``(agent, actions)`` where ``actions`` is a flat list of ints
    across every env-step of the run (env-major within a step, matching
    ``vec_env.SerialVecEnv.step``'s own array order).
    """
    captured: dict = {}
    real_make_model = checkpoints.make_model

    def spy_make_model(spec, obs_dim, n_actions):
        model = real_make_model(spec, obs_dim, n_actions)
        captured["model"] = model
        return model

    monkeypatch.setattr(checkpoints, "make_model", spy_make_model)

    actions: list[int] = []
    real_step = vec_env_mod.SerialVecEnv.step

    def spy_step(self, acts):
        actions.extend(int(a) for a in np.asarray(acts))
        return real_step(self, acts)

    monkeypatch.setattr(vec_env_mod.SerialVecEnv, "step", spy_step)
    monkeypatch.setattr("sys.argv", ["train_torch.py", *argv])

    train_torch.main()
    return captured["model"], actions


def _module_has_nonzero_grad(module: torch.nn.Module) -> bool:
    return any(
        p.grad is not None and torch.any(p.grad != 0)
        for p in module.parameters()
    )


def _read_last_csv_row(save_path: str) -> dict:
    with open(train_torch.csv_path(save_path), newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, f"no CSV rows written to {train_torch.csv_path(save_path)}"
    return rows[-1]


def _assert_finite_losses(save_path: str) -> dict:
    row = _read_last_csv_row(save_path)
    for key in ("pg", "v", "ent"):
        val = float(row[key])
        assert math.isfinite(val), f"{key} not finite: {row[key]!r}"
    return row


def _give_combat_envs_a_potion(monkeypatch) -> None:
    """Make every combat env this rollout builds start with one legal,
    non-automatic potion (``fire_potion``).

    A fresh ``STS2FullCombatEnv()`` (``vec_env.build_env``'s own call, with
    no ``potions`` kwarg) starts with an empty belt, so
    ``combat_action_masks`` masks the ENTIRE potion action block off, every
    step, for the whole rollout. ``EntitySetActorCritic.action_logits``
    masked_fills illegal logits to a constant before the categorical
    distribution is built, so a permanently-all-illegal block can never
    receive a gradient -- not because ``potion_head`` doesn't participate in
    the graph, but because the fixture never gives it anything legal to
    score. There is no ``--potions`` CLI flag on ``train_torch.py`` (and
    adding one is out of scope here -- no ``sts2_rl/*.py``/``train_torch.py``
    edits), so this monkeypatches ``sts2_rl.full_env.STS2FullCombatEnv`` to
    default ``potions=["fire_potion"]``. ``vec_env.build_env`` re-imports
    the name from the module at every call (``from sts2_rl.full_env import
    STS2FullCombatEnv`` is function-local), so patching the module
    attribute is enough -- no edit to vec_env.py itself.
    """
    real_cls = full_env_mod.STS2FullCombatEnv

    class _CombatEnvWithPotion(real_cls):
        def __init__(self, *a, **kw):
            kw.setdefault("potions", ["fire_potion"])
            super().__init__(*a, **kw)

    monkeypatch.setattr(full_env_mod, "STS2FullCombatEnv", _CombatEnvWithPotion)


# ── A.1 combat ───────────────────────────────────────────────────────────

def test_ppo_smoke_combat(tmp_path, monkeypatch):
    """One tiny PPO update on the real combat env/model/loop: 2 envs, 8
    rollout steps, 1 update epoch, CPU, fixed seed 0.

    Load-bearing assertion: every scored head (end-turn, play, potion, and
    at least one embedding table in the actor encoder) must show a nonzero
    gradient after the update -- proof every head actually participates in
    the PPO backward graph, not just that it exists. Combat's ActionLayout
    carries no positional ranges (brief: "skip that bit for combat"), pinned
    here as a fixture-sanity check rather than silently omitted.
    """
    _give_combat_envs_a_potion(monkeypatch)
    save = tmp_path / "ckpt_combat.pt"
    agent, actions = _drive_main(monkeypatch, [
        "--env", "combat", "--arch", "entset",
        "--n-envs", "2", "--n-steps", "8", "--timesteps", "16",
        "--epochs", "1", "--minibatches", "2",
        "--hidden", "32",
        "--device", "cpu", "--seed", "0",
        "--save", str(save), "--save-every", "100", "--keep-snapshots", "0",
    ])

    _assert_finite_losses(str(save))

    assert agent.action_layout.end_turn_index is not None
    assert agent.action_layout.play is not None
    assert agent.action_layout.potion_pairs is not None
    assert agent.action_layout.positional == (), (
        "fixture sanity: combat's action layout has no positional ranges -- "
        "if this ever changes the 'skip for combat' clause below needs "
        "revisiting too")

    assert _module_has_nonzero_grad(agent.end_turn_head), "end_turn_head got no gradient"
    assert _module_has_nonzero_grad(agent.play_head), "play_head got no gradient"
    assert _module_has_nonzero_grad(agent.potion_head), "potion_head got no gradient"
    assert any(
        _module_has_nonzero_grad(table)
        for table in agent.actor_encoder.tables.values()
    ), "no embedding table in the actor encoder got a gradient"

    assert len(actions) == 16, (
        f"expected 16 sampled actions (2 envs x 8 steps), got {len(actions)}")


# ── A.1b combat, --shared-encoder (R10) ────────────────────────────────────

def test_ppo_smoke_combat_shared_encoder(tmp_path, monkeypatch):
    """Same tiny PPO update as `test_ppo_smoke_combat`, but through the
    `--shared-encoder` CLI path -- the flag builds a real ONE-instance
    encoder graph, trains it (gradients still reach both heads AND the
    critic through the shared encoder), saves a checkpoint stamped
    `shared_encoder=True`, and that checkpoint reloads back into the same
    shared arm via `checkpoints.load_agent`. Not a repeat of
    `test_models.py`'s construction-level tests -- this is the actual
    `train_torch.main()` entry point end to end, the same integration
    coverage `test_ppo_smoke_combat` gives the default arm."""
    _give_combat_envs_a_potion(monkeypatch)
    save = tmp_path / "ckpt_combat_shared.pt"
    agent, actions = _drive_main(monkeypatch, [
        "--env", "combat", "--arch", "entset", "--shared-encoder",
        "--n-envs", "2", "--n-steps", "8", "--timesteps", "16",
        "--epochs", "1", "--minibatches", "2",
        "--hidden", "32",
        "--device", "cpu", "--seed", "0",
        "--save", str(save), "--save-every", "100", "--keep-snapshots", "0",
    ])

    assert agent.actor_encoder is agent.critic_encoder
    _assert_finite_losses(str(save))

    assert _module_has_nonzero_grad(agent.end_turn_head), "end_turn_head got no gradient"
    assert _module_has_nonzero_grad(agent.play_head), "play_head got no gradient"
    assert _module_has_nonzero_grad(agent.potion_head), "potion_head got no gradient"
    assert _module_has_nonzero_grad(agent.critic), "critic head got no gradient"
    assert any(
        _module_has_nonzero_grad(table)
        for table in agent.actor_encoder.tables.values()
    ), "no embedding table in the shared encoder got a gradient"

    assert len(actions) == 16, (
        f"expected 16 sampled actions (2 envs x 8 steps), got {len(actions)}")

    ckpt = torch.load(save, map_location="cpu", weights_only=False)
    assert ckpt["shared_encoder"] is True
    assert not any(k.startswith("critic_encoder.") for k in ckpt["model"]), (
        "a shared-arm checkpoint must not carry a separate critic_encoder.* "
        "state_dict entry")

    reloaded, reloaded_ckpt = checkpoints.load_agent(
        str(save), env_kind="combat", obs_dim=agent.obs_dim, n_actions=agent.n_actions)
    assert reloaded.actor_encoder is reloaded.critic_encoder
    assert reloaded_ckpt["shared_encoder"] is True


# ── A.2 run ──────────────────────────────────────────────────────────────

def test_ppo_smoke_run(tmp_path, monkeypatch):
    """One tiny PPO update on the real run env: 1 env, 16 (<=32) bounded
    steps, fixed seed 0, 1 update epoch.

    Same finiteness assertions as the combat test, plus: for whichever
    positional (CHOICE/SELECT/belt-POTION) blocks the rollout actually
    sampled an action from, that block's own head must show a nonzero
    gradient. Not forced -- which blocks fire depends on what decisions this
    seed's 16 steps happened to hit -- so the blocks exercised are printed
    for the record rather than asserted unconditionally.

    ``end_turn_head``/``play_head`` are also checked unconditionally (both
    are always legal or near-always legal -- end-turn every player-turn
    step, some hand card most steps -- so this costs nothing and adds
    integration coverage). ``potion_head`` is deliberately NOT checked here:
    unlike the combat test, a run episode starts with an empty belt and
    reaches combat only after several map/event steps, so within a
    16-step bounded rollout the potion block may legitimately never be
    legal even once -- asserting it unconditionally would make this test
    fixture-fragile for a reason that has nothing to do with the tied head.
    """
    save = tmp_path / "ckpt_run.pt"
    n_steps = 16
    agent, actions = _drive_main(monkeypatch, [
        "--env", "run", "--arch", "entset",
        "--n-envs", "1", "--n-steps", str(n_steps), "--timesteps", str(n_steps),
        "--epochs", "1", "--minibatches", "1",
        "--hidden", "32",
        "--device", "cpu", "--seed", "0",
        "--target-kl", "0",
        "--save", str(save), "--save-every", "100", "--keep-snapshots", "0",
    ])

    _assert_finite_losses(str(save))

    assert len(actions) == n_steps

    assert _module_has_nonzero_grad(agent.end_turn_head), "end_turn_head got no gradient"
    assert _module_has_nonzero_grad(agent.play_head), "play_head got no gradient"
    assert any(
        _module_has_nonzero_grad(table)
        for table in agent.actor_encoder.tables.values()
    ), "no embedding table in the actor encoder got a gradient"

    # layout.positional's bases/widths are already validated (tiling, no
    # gap/overlap) at model construction (models._validate_action_layout);
    # run_action_layout() fixes their declaration order to CHOICE, SELECT,
    # then belt-POTION, matching positional_heads' index order 1:1.
    layout = agent.action_layout
    named_positional = list(zip(("CHOICE", "SELECT", "POTION"), layout.positional))

    exercised: set[str] = set()
    for a in actions:
        for name, (base, width) in named_positional:
            if base <= a < base + width:
                exercised.add(name)

    print(
        f"run smoke: {len(actions)} actions sampled over seed 0; "
        f"positional blocks exercised: {sorted(exercised) or ['(none)']}"
    )

    for idx, (name, (_base, _width)) in enumerate(named_positional):
        if name in exercised:
            head = agent.positional_heads[idx]
            assert _module_has_nonzero_grad(head), (
                f"{name} head got no gradient despite being sampled this rollout")


# ── A.3 combat, --start-snapshots (phase-3 Task 3, R11) ────────────────────


def test_train_torch_start_snapshots_smoke(tmp_path, monkeypatch):
    """``train_torch.py --start-snapshots PATH`` drives real combat resets
    off a mid-run snapshot dataset (instead of synthetic starts) through the
    real ``train_torch.main()`` entry point, and records the path in the
    checkpoint payload's ``args`` the same way every other run flag is
    recorded (no refusal logic on a later mismatched resume).

    Two distinguishable snapshots (max_hp 41 vs 13) so "a snapshot start
    actually occurred" is checkable from a captured env attribute rather
    than merely "the run didn't crash" -- the smoke-test pattern this file
    already uses (``_give_combat_envs_a_potion``, the ``actions`` capture).
    """
    from sts2_rl.snapshots import CardSnap, Snapshot, encounter_registry, save_snapshots

    ids = list(encounter_registry())
    snap_a = Snapshot(
        deck=(CardSnap("strike", False, None, None),) * 5,
        relics=(), hp=41, max_hp=41, potion_slots=(),
        act=1, encounter_id=ids[0],
        provenance={"seed": "a", "floor": 1, "episode_decisions": 0},
    )
    snap_b = Snapshot(
        deck=(CardSnap("defend", False, None, None),) * 5,
        relics=(), hp=13, max_hp=13, potion_slots=(),
        act=1, encounter_id=ids[1],
        provenance={"seed": "b", "floor": 2, "episode_decisions": 0},
    )
    dataset_path = str(tmp_path / "train_snaps.jsonl")
    save_snapshots(dataset_path, [snap_a, snap_b])

    captured_max_hp: list[int] = []
    real_new_state = full_env_mod.STS2FullCombatEnv._new_state

    def spy_new_state(self, rng):
        state = real_new_state(self, rng)
        if self._snapshot_mode:
            captured_max_hp.append(state.player.max_hp)
        return state

    monkeypatch.setattr(full_env_mod.STS2FullCombatEnv, "_new_state", spy_new_state)

    save = tmp_path / "ckpt_snapshots.pt"
    agent, actions = _drive_main(monkeypatch, [
        "--env", "combat", "--arch", "entset",
        "--start-snapshots", dataset_path,
        "--n-envs", "2", "--n-steps", "8", "--timesteps", "16",
        "--epochs", "1", "--minibatches", "2",
        "--hidden", "32",
        "--device", "cpu", "--seed", "0",
        "--save", str(save), "--save-every", "100", "--keep-snapshots", "0",
    ])

    _assert_finite_losses(str(save))
    assert len(actions) == 16

    assert captured_max_hp, "no snapshot-mode reset observed during the rollout"
    assert set(captured_max_hp) <= {41, 13}, (
        f"snapshot resets produced an hp outside the dataset: {captured_max_hp}")

    ckpt = torch.load(save, map_location="cpu", weights_only=False)
    assert ckpt["start_snapshots"] == dataset_path


def test_start_snapshots_and_encounter_are_mutually_exclusive_on_the_cli(monkeypatch):
    monkeypatch.setattr("sys.argv", [
        "train_torch.py", "--env", "combat", "--encounter", "fuzzy_wurm_weak",
        "--start-snapshots", "dummy.jsonl",
    ])
    with pytest.raises(SystemExit):
        train_torch.parse_args()


def test_start_snapshots_refused_outside_combat_env(monkeypatch):
    monkeypatch.setattr("sys.argv", [
        "train_torch.py", "--env", "run", "--start-snapshots", "dummy.jsonl",
    ])
    with pytest.raises(SystemExit):
        train_torch.parse_args()


def test_start_snapshots_crosses_a_subprocvecenv_worker_boundary_as_a_path(tmp_path):
    """``EnvSpec.start_snapshots`` must be a plain, picklable PATH (never a
    live ``SnapshotDataset``, which would carry ``Card``/``Relic``
    instances across the pipe): 2 envs / 2 workers, each worker process
    loads the dataset itself from the path, and the reset obs reflects the
    snapshot's hp (17/41, a ratio no default combat-env start ever produces:
    a synthetic start is always full HP)."""
    from sts2_rl.full_env import combat_obs_layout
    from sts2_rl.snapshots import CardSnap, Snapshot, encounter_registry, save_snapshots
    from sts2_rl.vec_env import EnvSpec, SubprocVecEnv

    ids = list(encounter_registry())
    snap = Snapshot(
        deck=(CardSnap("strike", False, None, None),) * 5,
        relics=(), hp=17, max_hp=41, potion_slots=(),
        act=1, encounter_id=ids[0],
        provenance={"seed": "only", "floor": 1, "episode_decisions": 0},
    )
    dataset_path = str(tmp_path / "sub_snaps.jsonl")
    save_snapshots(dataset_path, [snap])

    spec = EnvSpec(kind="combat", start_snapshots=dataset_path)
    venv = SubprocVecEnv(spec, n_envs=2, n_workers=2)
    try:
        obs, masks = venv.reset([0, 1])
    finally:
        venv.close()

    layout = combat_obs_layout("hybrid")
    hp_ratio = obs.f[:, layout.f_slices["player.hp_ratio"]].reshape(-1)
    expected = 17 / 41
    assert np.allclose(hp_ratio, expected), (
        f"both workers' reset obs should reflect the snapshot's hp ratio "
        f"({expected!r}), got {hp_ratio!r}")

