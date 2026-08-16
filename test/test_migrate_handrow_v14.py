"""Migration = output-identical: spliced zero columns make the new model
ignore f[29]/f[30], so logits match the pre-bump policy exactly."""
from __future__ import annotations

import torch

from sts2_rl.checkpoints import ModelSpec, model_obs_layout
from sts2_rl.full_env import MAX_HAND, N_CARD_FEATURES
from sts2_rl.models import EntitySetActorCritic, run_action_layout
from sts2_rl.run_env import STS2RunEnv, run_obs_layout
from sts2_rl.tensor_obs import TensorObs
from tools.migrate_handrow_v14 import migrate, splice_zero_columns

HAND_BLOCK_INDEX = 15   # combat.hand.ids -- see task-4 discovery (Step 1/5)
HAND_KEY = "actor_encoder._blocks.15.weight"


def test_splice_zero_columns_positions_and_values():
    w = torch.arange(12.0).reshape(3, 4)          # [out=3, in=4]
    out = splice_zero_columns(w, insert_at=4, width=2)
    assert out.shape == (3, 6)
    assert torch.equal(out[:, :4], w)
    assert torch.equal(out[:, 4:], torch.zeros(3, 2))


def _build_run_agent():
    from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS

    f_segments, i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    model = EntitySetActorCritic(
        f_segments, i_segments, RUN_N_ACTIONS, run_action_layout(),
        hidden=(32,), shared_encoder=True)
    return model, f_segments, i_segments


def test_migrated_model_ignores_new_fields(tmp_path):
    # Build a fresh schema-12 entset agent, save it, hand-shrink its hand
    # projection back to the 29-wide shape (the "old checkpoint"), migrate,
    # reload, and assert logits are invariant to f[29]/f[30] noise.
    model, _f_segments, _i_segments = _build_run_agent()
    old_key = HAND_KEY
    old_w = model.state_dict()[old_key]
    old_row_in = old_w.shape[1]           # current (schema-12) row width: embeds + 31 floats
    old_row_in_shrunk = old_row_in - 2    # the "old" (schema-11) 29-float row width

    state = model.state_dict()
    optimizer = torch.optim.Adam(model.parameters())
    # Populate optim.state with a fake step so migrate()'s Adam-splice path
    # is exercised too.
    for p in model.parameters():
        p.grad = torch.zeros_like(p)
    optimizer.step()

    param_names = [n for n, _ in model.named_parameters()]
    idx = param_names.index(old_key)
    opt_state = optimizer.state_dict()
    # optimizer.state_dict()'s "state" is keyed by a running counter that
    # matches param_groups order, which matches named_parameters() order
    # for a freshly constructed Adam over model.parameters().
    pstate = opt_state["state"][idx]
    for moment in ("exp_avg", "exp_avg_sq"):
        pstate[moment] = pstate[moment][:, :old_row_in_shrunk].clone()

    shrunk_model_sd = dict(state)
    shrunk_model_sd[old_key] = old_w[:, :old_row_in_shrunk].clone()

    old_ckpt = dict(
        model=shrunk_model_sd,
        optim=opt_state,
        iteration=1, global_step=1, obs_dim=model.obs_dim, n_actions=model.n_actions,
        hidden=list(model.hidden), arch="entset", head_version=4, shared_encoder=True,
        obs_schema=11, env_kind="run", ascension=0, n_envs=1, n_steps=1,
        start_snapshots=0,
    )
    torch.save(old_ckpt, tmp_path / "old.pt")

    migrate(tmp_path / "old.pt", tmp_path / "new.pt")
    ck = torch.load(tmp_path / "new.pt", map_location="cpu", weights_only=False)
    assert ck["obs_schema"] == 12
    assert ck["obs_dim"] == model.obs_dim   # must match the CURRENT (schema-12) layout
    assert ck["model"][old_key].shape == old_w.shape
    assert torch.equal(ck["model"][old_key][:, :old_row_in_shrunk], old_w[:, :old_row_in_shrunk])
    assert torch.equal(ck["model"][old_key][:, old_row_in_shrunk:], torch.zeros(32, 2))

    new_model, _f, _i = _build_run_agent()
    new_model.load_state_dict(ck["model"])
    new_model.eval()

    env = STS2RunEnv()
    obs, _info = env.reset(seed=0)
    mask = env.action_masks()
    tobs = TensorObs.from_dict(obs, device="cpu")[None]
    maskt = torch.as_tensor(mask, dtype=torch.bool).unsqueeze(0)

    layout = run_obs_layout()
    hand_sl = layout.f_slices["combat.hand.f"]

    f = tobs.f.clone()
    g = torch.Generator().manual_seed(0)
    for h in range(MAX_HAND):
        base = hand_sl.start + h * N_CARD_FEATURES
        f[..., base + 29] = torch.rand((), generator=g).item()
        f[..., base + 30] = torch.rand((), generator=g).item()
    tobs_rand = TensorObs(f=f, i=tobs.i)

    with torch.no_grad():
        logits = new_model.action_logits(tobs, maskt)
        logits_rand = new_model.action_logits(tobs_rand, maskt)
    assert torch.equal(logits, logits_rand)
