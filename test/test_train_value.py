import copy, torch, numpy as np
from pathlib import Path
from tools.value_shards import write_value_shard
from tools.train_value import freeze_for_value_fit, train_value
from sts2_rl.checkpoints import load_agent

CKPT = "runs/sts2_run_torch_v24_s27.pt"
OBS_DIM = (4736, 1533); NA = 253

def _tiny_targets(tmp_path, n=64, seed=0):
    rng = np.random.default_rng(seed)
    d = tmp_path / f"t{seed}"; d.mkdir()
    f = rng.standard_normal((n, 4736)).astype(np.float16)
    i = rng.integers(0, 3, (n, 1533)).astype(np.int32)
    g = rng.standard_normal(n).astype(np.float32)
    c = np.ones(n, bool)
    write_value_shard(d / "shard-00000.npz", f, i, g, c)
    (d / "provenance.json").write_text('{"obs_schema":13,"gamma":0.999}')
    return str(d)

def test_freeze_trains_only_critic_head():
    model, _ = load_agent(CKPT, env_kind="run", obs_dim=OBS_DIM, n_actions=NA)
    names = freeze_for_value_fit(model, train_encoder=False)
    assert names and all(n.startswith("critic.") for n in names)
    trainable = {n for n, p in model.named_parameters() if p.requires_grad}
    assert trainable == set(names)

def test_policy_byte_identical_after_fit(tmp_path):
    # a fixed obs -> action logits must be unchanged after value training
    model0, _ = load_agent(CKPT, env_kind="run", obs_dim=OBS_DIM, n_actions=NA)
    from sts2_rl.tensor_obs import TensorObs
    f = torch.zeros(1, 4736); i = torch.zeros(1, 1533, dtype=torch.long)
    mask = torch.ones(1, NA, dtype=torch.bool)
    before = model0.action_logits(TensorObs(f, i), mask).detach().clone()
    out = tmp_path / "vfit.pt"
    train_value(targets=_tiny_targets(tmp_path, seed=0),
                holdout=_tiny_targets(tmp_path, seed=1),
                ckpt=CKPT, out=str(out), epochs=2, batch=32, device="cpu")
    model1, _ = load_agent(str(out), env_kind="run", obs_dim=OBS_DIM, n_actions=NA)
    after = model1.action_logits(TensorObs(f, i), mask).detach()
    assert torch.equal(before, after)          # policy untouched

def test_value_head_actually_moved(tmp_path):
    model0, _ = load_agent(CKPT, env_kind="run", obs_dim=OBS_DIM, n_actions=NA)
    w0 = copy.deepcopy(model0.critic.state_dict())
    out = tmp_path / "vfit.pt"
    train_value(targets=_tiny_targets(tmp_path, seed=0),
                holdout=_tiny_targets(tmp_path, seed=1),
                ckpt=CKPT, out=str(out), epochs=3, batch=32, device="cpu")
    model1, _ = load_agent(str(out), env_kind="run", obs_dim=OBS_DIM, n_actions=NA)
    moved = any(not torch.equal(w0[k], model1.critic.state_dict()[k]) for k in w0)
    assert moved
