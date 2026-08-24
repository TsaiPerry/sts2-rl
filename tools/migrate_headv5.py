"""One-shot migration: entset checkpoint, head_version 4 -> 5 (v22 discard
block). Old weights are copied VERBATIM — nothing changes shape — so the
migrated policy is bit-identical on every pre-existing action by
construction. Only the new run-layout discard pointer head
(``pointer_heads.2.*``) is fresh-initialized (PointerHead's own init:
output std 0.01 -> discard logits start near 0). Adam ``optim.state`` is
positional, so old entries are remapped BY PARAMETER NAME to their new
indices; the new params start with no Adam state (created lazily on first
step). Combat-scale checkpoints gain no params (their layout is unchanged
at version 5): for them this tool is a pure restamp."""
import argparse
import sys
from pathlib import Path

import torch

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def migrate(src, dst) -> None:
    ck = torch.load(src, map_location="cpu", weights_only=False)
    if ck.get("head_version", 1) != 4:
        sys.exit(f"expected head_version 4, got {ck.get('head_version', 1)}")
    if ck.get("arch") != "entset":
        sys.exit("this tool migrates entset checkpoints only")

    from sts2_rl.checkpoints import RUN_SCALE_ENVS, ModelSpec, make_model, model_obs_layout

    spec = ModelSpec(
        env_kind=ck["env_kind"], arch="entset",
        hidden=tuple(ck.get("hidden", (256, 256))),
        shared_encoder=ck.get("shared_encoder", False))
    f_segments, i_segments = model_obs_layout(spec)
    f_dim = sum(w for _, w in f_segments)
    i_dim = sum(w for _, w in i_segments)

    widen = 0
    if ck["env_kind"] in RUN_SCALE_ENVS:
        from sts2_rl.run_env import MAX_POTION_SLOTS
        widen = MAX_POTION_SLOTS
    n_actions_new = ck["n_actions"] + widen

    agent = make_model(spec, (f_dim, i_dim), n_actions_new)
    fresh = agent.state_dict()
    model = ck["model"]
    new_keys = [k for k in fresh if k not in model]
    for k in new_keys:
        assert k.startswith("pointer_heads."), (
            f"unexpected new key {k} — this tool only knows how to add the "
            f"v22 discard pointer head")
        model[k] = fresh[k]
    missing = [k for k in model if k not in fresh]
    assert not missing, f"source has keys today's model lacks: {missing[:5]}"

    optim = ck.get("optim")
    if optim and optim.get("state"):
        new_names = [n for n, _ in agent.named_parameters()]
        old_names = [n for n in new_names if n not in new_keys]
        # Old positional order == old_names' order (the new params are the
        # only registration change, and state_dict/named_parameters share
        # registration order).
        remap = {i: new_names.index(n) for i, n in enumerate(old_names)}
        optim["state"] = {remap[i]: s for i, s in optim["state"].items()}
        (group,) = optim["param_groups"]
        group["params"] = list(range(len(new_names)))

    ck["n_actions"] = n_actions_new
    ck["head_version"] = 5
    torch.save(ck, dst)
    print(f"migrated {src} -> {dst} (head_version 5, n_actions {n_actions_new}, "
          f"new keys: {new_keys})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    migrate(a.src, a.dst)
