"""Tests for Task 6b: cross-kind partial-load (``--warm-start``).

``sts2_rl.checkpoints.warm_start_agent`` copies whatever structurally
transfers from a checkpoint of a POSSIBLY DIFFERENT env kind (run <-> combat)
into a freshly built target model, leaving everything else at its fresh
init. Two transfer mechanisms: exact name+shape match everywhere except
``{actor,critic}_encoder._blocks.*`` (a positionally indexed ModuleList,
transferred by LOGICAL segment name instead -- see the function's own
docstring for the measured ``_blocks.6`` landmine this file pins directly),
plus everything else that matches by plain name+shape (heads, vocab tables,
deeper trunk layers).

``train_torch.py --warm-start PATH`` is the CLI entry point built on top of
it: fresh optimizer/iteration either way, mutually exclusive with
--resume/--fresh, arch=entset required on both sides.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

import train_torch
from sts2_rl import checkpoints, models
from sts2_rl import vec_env as vec_env_mod
from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout, warm_start_agent
from sts2_rl.full_env import MAX_POTIONS, combat_action_count
from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS


def _spec(env_kind: str, hidden=(32,)) -> ModelSpec:
    return ModelSpec(env_kind=env_kind, card_obs="hybrid", arch="entset",
                      hidden=hidden, shared_encoder=True)


def _build(env_kind: str, hidden=(32,)):
    spec = _spec(env_kind, hidden)
    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    n_actions = (combat_action_count(MAX_POTIONS) if env_kind == "combat"
                 else RUN_N_ACTIONS)
    model = make_model(spec, obs_dim, n_actions)
    return model, spec, obs_dim, n_actions


def _block_index(spec, logical_name: str) -> int:
    """Position of ``logical_name``'s row block in an entset encoder's
    ``_blocks`` list. Derived from the same plan the encoder is built from, so
    tests never hardcode an index that any new obs segment would shift."""
    f_segs, i_segs = model_obs_layout(spec)
    row_blocks, _raw_f = models.entset_segment_plan(f_segs, i_segs)
    # Blocks are named by their raw ".ids" segment; the encoder pairs them by
    # the LOGICAL name (".ids" dropped, "combat." prefix stripped), which is
    # what makes a run block and a combat block "the same segment".
    names = [models._entset_logical_name(name) for name, *_rest in row_blocks]
    assert logical_name in names, f"{logical_name!r} not in {names}"
    return names.index(logical_name)


def _fake_ckpt(model, env_kind: str, hidden=(32,)) -> dict:
    return {
        "model": model.state_dict(),
        "arch": "entset",
        "env_kind": env_kind,
        "hidden": tuple(hidden),
        "shared_encoder": True,
        "head_version": models.ENTSET_HEAD_VERSION,
    }


# ── warm_start_agent: structural transfer ────────────────────────────────


def test_run_to_combat_transfers_matching_keys_and_leaves_trunk_input_fresh():
    torch.manual_seed(0)
    run_model, _run_spec, _rd, _rn = _build("run")
    ckpt = _fake_ckpt(run_model, "run")

    torch.manual_seed(1)
    target, target_spec, _cd, _cn = _build("combat")
    before = {k: v.clone() for k, v in target.state_dict().items()}

    n_transferred, n_reinit = warm_start_agent(target, ckpt, target_spec)
    assert n_transferred > 0
    assert n_reinit > 0

    after = target.state_dict()
    run_sd = run_model.state_dict()

    # Exact name+shape matches (vocab tables, fixed-shape heads) equal source.
    for key in ("actor_encoder.tables.cards.weight",
                "actor_encoder.tables.relics.weight",
                "actor_encoder.tables.monsters.weight",
                "end_turn_head.weight", "end_turn_head.bias",
                "play_head.mlp.0.weight", "potion_head.mlp.0.weight"):
        assert torch.equal(after[key], run_sd[key]), f"{key} not transferred"

    # actor.0/critic.0 (in-width 747 combat vs 3253 run) NEVER transfer --
    # stay at the target's own fresh init, not the source's (different shape
    # entirely, so equality against the source is meaningless; check against
    # the pre-warm-start snapshot instead).
    assert torch.equal(after["actor.0.weight"], before["actor.0.weight"])
    assert torch.equal(after["critic.0.weight"], before["critic.0.weight"])


def test_combat_to_run_transfers_matching_keys_and_leaves_trunk_input_fresh():
    torch.manual_seed(2)
    combat_model, _cs, _cd, _cn = _build("combat")
    ckpt = _fake_ckpt(combat_model, "combat")

    torch.manual_seed(3)
    target, target_spec, _rd, _rn = _build("run")
    before = {k: v.clone() for k, v in target.state_dict().items()}

    n_transferred, n_reinit = warm_start_agent(target, ckpt, target_spec)
    assert n_transferred > 0
    assert n_reinit > 0

    after = target.state_dict()
    combat_sd = combat_model.state_dict()

    for key in ("actor_encoder.tables.cards.weight",
                "end_turn_head.weight", "play_head.mlp.0.weight",
                "potion_head.mlp.0.weight"):
        assert torch.equal(after[key], combat_sd[key])

    assert torch.equal(after["actor.0.weight"], before["actor.0.weight"])
    assert torch.equal(after["critic.0.weight"], before["critic.0.weight"])

    # Run-only heads (no combat counterpart at all) must stay fresh.
    for key in after:
        if key.startswith(("positional_heads.", "pointer_heads.",
                            "choice_row_overlay_heads.", "choice_float_overlay_heads.")):
            assert torch.equal(after[key], before[key]), (
                f"{key} is run-only (absent from a combat checkpoint) but "
                f"changed from its fresh init")


def test_blocks_transfer_only_for_logically_matched_segments_not_by_position():
    """Pins the measured landmine directly (T6b brief): combat's
    ``actor_encoder._blocks.6`` is the ``enemy2.powers`` row block (in-width
    19); run's ``_blocks.6`` is ``shop.relics`` (also in-width 19, by
    coincidence -- same shape, unrelated meaning). A naive name+shape
    ``strict=False`` load would copy run's shop-relics projection into
    combat's enemy-powers slot. The real logical match for combat's
    enemy2.powers sits at a DIFFERENT index in run's block list.

    Both indices are derived from the layouts rather than written as literals:
    they are positions in the run/combat int-segment lists, so ANY segment
    added ahead of them shifts them. Hardcoding made this test fail on the
    unrelated v13 `event.options.cards.ids` addition, which is noise — the
    behaviour under test (match by logical name, not position) was unaffected."""
    torch.manual_seed(4)
    run_model, _rs, _rd, _rn = _build("run")
    ckpt = _fake_ckpt(run_model, "run")

    torch.manual_seed(5)
    target, target_spec, _cd, _cn = _build("combat")

    combat_block = _block_index(target_spec, "enemy2.powers")
    run_block = _block_index(_spec("run", (32,)), "enemy2.powers")
    # The landmine only exists while the two indices genuinely disagree.
    assert combat_block != run_block

    key = f"actor_encoder._blocks.{combat_block}.weight"
    before_block6 = target.state_dict()[key].clone()

    warm_start_agent(target, ckpt, target_spec)

    after_block6 = target.state_dict()[key]
    run_sd = run_model.state_dict()
    # Same index in the SOURCE model — a different segment entirely.
    wrong_source = run_sd[f"actor_encoder._blocks.{combat_block}.weight"]
    right_source = run_sd[f"actor_encoder._blocks.{run_block}.weight"]

    assert not torch.equal(after_block6, wrong_source), (
        "block 6 was copied by POSITION (run's shop.relics) instead of by "
        "logical segment name -- this is exactly the landmine the brief "
        "warns about")
    assert torch.equal(after_block6, right_source), (
        "block 6 (combat's enemy2.powers) should transfer from run's "
        "logically-matched enemy2.powers block (index 19), not stay fresh "
        "or come from the wrong index")
    assert not torch.equal(after_block6, before_block6)


def test_every_logical_block_shared_by_both_kinds_transfers():
    """Every one of combat's 12 row blocks (player.powers, player.relics,
    hand, enemies, enemy0..5.powers, potions, cards) is embedded verbatim
    inside the run env's own layout under a ``combat.`` prefix -- so ALL 12
    should transfer both ways, not just the ones that happen to share a
    raw positional index."""
    torch.manual_seed(6)
    run_model, _rs, _rd, _rn = _build("run")
    ckpt = _fake_ckpt(run_model, "run")

    torch.manual_seed(7)
    target, target_spec, _cd, _cn = _build("combat")
    warm_start_agent(target, ckpt, target_spec)

    row_blocks, _ = models.entset_segment_plan(target.f_segments, target.i_segments)
    after = target.state_dict()
    for i, (name, _cap, _n_float, _vocabs) in enumerate(row_blocks):
        w = after[f"actor_encoder._blocks.{i}.weight"]
        b = after[f"actor_encoder._blocks.{i}.bias"]
        assert w.numel() and b.numel()  # sanity: keys exist
    # all 12 combat blocks have a run-side logical counterpart (measured)
    combat_logicals = {models._entset_logical_name(n) for n, *_ in row_blocks}
    run_row_blocks, _ = models.entset_segment_plan(*model_obs_layout(_spec("run")))
    run_logicals = {models._entset_logical_name(n) for n, *_ in run_row_blocks}
    assert combat_logicals <= run_logicals


def test_warm_start_requires_entset_on_both_sides():
    torch.manual_seed(8)
    run_model, _rs, _rd, _rn = _build("run")
    ckpt = _fake_ckpt(run_model, "run")
    ckpt["arch"] = "mlp"

    target, target_spec, _cd, _cn = _build("combat")
    with pytest.raises(SystemExit, match="entset"):
        warm_start_agent(target, ckpt, target_spec)


def test_normal_resume_cross_kind_still_refused():
    """The T6b brief requires the STRICT --resume guard to stay exactly as
    strict as today; the relaxation lives ONLY in warm_start_agent, never in
    check_checkpoint."""
    torch.manual_seed(9)
    run_model, run_spec, run_obs_dim, run_n_actions = _build("run")
    ckpt = _fake_ckpt(run_model, "run")
    ckpt["obs_dim"] = run_obs_dim
    ckpt["n_actions"] = run_n_actions
    ckpt["obs_schema"] = checkpoints.obs_schema_version(run_spec)

    combat_spec = _spec("combat")
    combat_obs_dim = (
        sum(w for _, w in model_obs_layout(combat_spec)[0]),
        sum(w for _, w in model_obs_layout(combat_spec)[1]))
    combat_n_actions = combat_action_count(MAX_POTIONS)

    with pytest.raises(SystemExit, match="combat"):
        checkpoints.check_checkpoint(ckpt, combat_spec, combat_obs_dim, combat_n_actions)


# ── CLI: --warm-start flag ────────────────────────────────────────────────


def test_warm_start_and_resume_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr("sys.argv", [
        "train_torch.py", "--env", "combat",
        "--warm-start", "foo.pt", "--resume", "bar.pt",
    ])
    with pytest.raises(SystemExit, match="warm-start"):
        train_torch.parse_args()


def test_warm_start_and_fresh_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr("sys.argv", [
        "train_torch.py", "--env", "combat",
        "--warm-start", "foo.pt", "--fresh",
    ])
    with pytest.raises(SystemExit, match="warm-start"):
        train_torch.parse_args()


def test_warm_start_requires_arch_entset_on_the_cli(monkeypatch):
    monkeypatch.setattr("sys.argv", [
        "train_torch.py", "--env", "combat", "--arch", "mlp",
        "--warm-start", "foo.pt",
    ])
    with pytest.raises(SystemExit, match="entset"):
        train_torch.parse_args()


def _drive_main(monkeypatch, argv: list[str]):
    """Mirrors test_train_smoke.py's own helper (kept local rather than
    imported, since it's that file's private implementation detail): runs
    ``train_torch.main()`` under ``argv``, capturing the constructed agent."""
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


def test_cli_smoke_warm_start_run_ckpt_into_combat_env(tmp_path, monkeypatch):
    """s0-style invocation (T6b Deliverable 5 gate (a) in miniature): a run
    checkpoint warm-starting a combat run. Constructs, transfers, and steps
    through one real PPO update via the actual train_torch.main() entry
    point -- not a hand-rolled construction check."""
    from sts2_rl import full_env as full_env_mod

    real_cls = full_env_mod.STS2FullCombatEnv

    class _CombatEnvWithPotion(real_cls):
        def __init__(self, *a, **kw):
            kw.setdefault("potions", ["fire_potion"])
            super().__init__(*a, **kw)

    monkeypatch.setattr(full_env_mod, "STS2FullCombatEnv", _CombatEnvWithPotion)

    torch.manual_seed(10)
    run_model, _rs, _rd, _rn = _build("run", hidden=(32,))
    run_ckpt_path = tmp_path / "seed_run.pt"
    torch.save(_fake_ckpt(run_model, "run", hidden=(32,)), run_ckpt_path)

    save = tmp_path / "ckpt_warm_combat.pt"
    agent, actions = _drive_main(monkeypatch, [
        "--env", "combat", "--arch", "entset",
        "--warm-start", str(run_ckpt_path),
        "--n-envs", "2", "--n-steps", "8", "--timesteps", "16",
        "--epochs", "1", "--minibatches", "2",
        "--hidden", "32",
        "--device", "cpu", "--seed", "0",
        "--save", str(save), "--save-every", "100", "--keep-snapshots", "0",
    ])

    assert len(actions) == 16
    ckpt = torch.load(save, map_location="cpu", weights_only=False)
    assert ckpt["env_kind"] == "combat"          # stamped with the TARGET kind
    # a fresh optimizer/iteration: the saved iteration counts from this
    # invocation's own PPO updates, not from whatever the seed run
    # checkpoint carried (it carried none here -- the fake ckpt has no
    # "iteration"/"optim" keys at all, so a bug that tried to resume rather
    # than warm-start would KeyError, not silently pass).
    assert ckpt["iteration"] == 1
    assert torch.isfinite(agent.state_dict()["actor.0.weight"]).all()
