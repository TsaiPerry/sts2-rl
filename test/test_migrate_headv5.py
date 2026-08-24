"""head_version 4 -> 5 migration (v22): old weights verbatim, fresh
pointer_heads.2.*, Adam state remapped BY NAME to new positional indices,
n_actions/head_version restamped. Old-action logits must be structurally
independent of the new params."""
import torch

from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout
from sts2_rl.run_env import MAX_POTION_SLOTS, N_ACTIONS, STS2RunEnv
from sts2_rl.tensor_obs import TensorObs
from tools.migrate_headv5 import migrate


def _fake_v4_ckpt(tmp_path):
    """A checkpoint as v18_s21 would look: today's model MINUS the discard
    head, n_actions 3 narrower, stamped head_version 4."""
    spec = ModelSpec(env_kind="run", arch="entset", hidden=(256, 256),
                     shared_encoder=True)
    f_seg, i_seg = model_obs_layout(spec)
    dims = (sum(w for _, w in f_seg), sum(w for _, w in i_seg))
    agent = make_model(spec, dims, N_ACTIONS)
    state = {k: v for k, v in agent.state_dict().items()
             if not k.startswith("pointer_heads.2.")}
    names = [n for n, _ in agent.named_parameters()
             if not n.startswith("pointer_heads.2.")]
    optim = {"state": {i: {"exp_avg": torch.zeros(1), "step": torch.tensor(1.0)}
                       for i in range(len(names))},
             "param_groups": [{"params": list(range(len(names))), "lr": 3e-4}]}
    ck = {"model": state, "optim": optim, "n_actions": N_ACTIONS - MAX_POTION_SLOTS,
          "obs_dim": dims, "hidden": (256, 256), "arch": "entset",
          "head_version": 4, "shared_encoder": True, "obs_schema": 12,
          "env_kind": "run", "iteration": 7, "global_step": 123}
    src = tmp_path / "v4.pt"
    torch.save(ck, src)
    return src, dims, agent


def test_migrated_ckpt_loads_and_is_restamped(tmp_path):
    src, dims, agent = _fake_v4_ckpt(tmp_path)
    dst = tmp_path / "v5.pt"
    migrate(str(src), str(dst))
    ck = torch.load(dst, map_location="cpu", weights_only=False)
    assert ck["head_version"] == 5 and ck["n_actions"] == N_ACTIONS
    agent.load_state_dict(ck["model"])          # strict load succeeds


def test_old_logits_independent_of_discard_head(tmp_path):
    src, dims, _ = _fake_v4_ckpt(tmp_path)
    dst = tmp_path / "v5.pt"
    migrate(str(src), str(dst))
    ck = torch.load(dst, map_location="cpu", weights_only=False)
    spec = ModelSpec(env_kind="run", arch="entset", hidden=(256, 256),
                     shared_encoder=True)
    agent = make_model(spec, dims, N_ACTIONS)
    agent.load_state_dict(ck["model"]); agent.eval()

    # Real env obs + all-legal mask (matches test_tied_head_run.py's
    # convention: EntitySetActorCritic.action_logits requires both a
    # TensorObs and a mask -- there is no bare `agent(obs)`/single-arg
    # `action_logits` entry point).
    env = STS2RunEnv()
    obs, _info = env.reset(seed=0)
    tobs = TensorObs.from_dict(obs, device="cpu")[None]
    mask = torch.ones(1, N_ACTIONS, dtype=torch.bool)

    with torch.no_grad():
        before = agent.action_logits(tobs, mask)
        for p in agent.pointer_heads[2].parameters():
            p.add_(torch.randn_like(p))         # scramble the new head
        after = agent.action_logits(tobs, mask)
    old = N_ACTIONS - MAX_POTION_SLOTS
    assert torch.equal(before[..., :old], after[..., :old])
    assert not torch.equal(before[..., old:], after[..., old:])


def test_adam_state_remapped_by_name(tmp_path):
    src, dims, agent = _fake_v4_ckpt(tmp_path)
    dst = tmp_path / "v5.pt"
    migrate(str(src), str(dst))
    ck = torch.load(dst, map_location="cpu", weights_only=False)
    new_names = [n for n, _ in agent.named_parameters()]
    old_names = [n for n in new_names if not n.startswith("pointer_heads.2.")]
    # every old param's state moved to its NEW index; new params have none
    assert set(ck["optim"]["state"]) == {new_names.index(n) for n in old_names}
    assert ck["optim"]["param_groups"][0]["params"] == list(range(len(new_names)))
