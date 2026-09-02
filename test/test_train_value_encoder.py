import torch, numpy as np
from pathlib import Path
from tools.value_shards import write_value_shard
from tools.train_value import train_value
from sts2_rl.checkpoints import load_agent
from sts2_rl.tensor_obs import TensorObs

CKPT = "runs/sts2_run_torch_v24_s27.pt"; OBS_DIM = (4736, 1533); NA = 253

def _tiny(tmp_path, seed):
    d = tmp_path / f"t{seed}"; d.mkdir(); rng = np.random.default_rng(seed)
    write_value_shard(d / "s.npz", rng.standard_normal((48, 4736)).astype(np.float16),
                      rng.integers(0, 3, (48, 1533)).astype(np.int32),
                      rng.standard_normal(48).astype(np.float32), np.ones(48, bool))
    (d / "provenance.json").write_text('{"obs_schema":13,"gamma":0.999}'); return str(d)

def test_encoder_mode_keeps_policy_and_makes_separate_encoder(tmp_path):
    m0, _ = load_agent(CKPT, env_kind="run", obs_dim=OBS_DIM, n_actions=NA)
    f = torch.zeros(1, 4736); i = torch.zeros(1, 1533, dtype=torch.long)
    mask = torch.ones(1, NA, dtype=torch.bool)
    before = m0.action_logits(TensorObs(f, i), mask).detach().clone()
    out = tmp_path / "vfit_enc.pt"
    train_value(targets=_tiny(tmp_path, 0), holdout=_tiny(tmp_path, 1),
                ckpt=CKPT, out=str(out), epochs=2, batch=24, device="cpu",
                train_encoder=True)
    ck = torch.load(str(out), map_location="cpu", weights_only=False)
    assert ck["shared_encoder"] is False
    assert any(k.startswith("critic_encoder.") for k in ck["model"])
    m1, _ = load_agent(str(out), env_kind="run", obs_dim=OBS_DIM, n_actions=NA)
    after = m1.action_logits(TensorObs(f, i), mask).detach()
    assert torch.equal(before, after)          # policy still byte-identical
