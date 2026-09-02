"""Offline value-head regression: fit V(s) toward Monte-Carlo return-to-go on
the FROZEN v24_s27 policy, so cheap 1-ply search (reward + gamma*V) becomes
reliable (spec 2026-08-31-critic-value-fit-design). Head-only by default:
trains model.critic with everything else — including the shared actor_encoder —
frozen, so the policy is byte-identical. --train-encoder is the escalation lever
(Task 4)."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np, torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sts2_rl.checkpoints import load_agent
from sts2_rl.tensor_obs import TensorObs
from tools.value_shards import load_value_set

OBS_DIM = (4736, 1533); N_ACTIONS = 253


def build_unshared_from_shared(ckpt_path, device):
    """v24_s27 is shared_encoder=True; build the shared_encoder=False twin,
    load actor+heads verbatim, and warm-init critic_encoder from actor_encoder."""
    import torch
    from sts2_rl.checkpoints import spec_from_checkpoint, make_model
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    ck_unshared = dict(ck); ck_unshared["shared_encoder"] = False
    spec = spec_from_checkpoint(ck_unshared, "run", "hybrid")
    model = make_model(spec, OBS_DIM, N_ACTIONS).to(device)
    # load_model_state_lenient only tolerates missing keys under
    # FRESH_TAIL_PREFIXES ("aux_", "critic_q") -- critic_encoder.* isn't one
    # of those, so it would raise strict here. Overlay the checkpoint's
    # matching-shape keys onto the fresh model's own state dict by hand
    # (same pattern that helper uses internally): actor/heads load verbatim,
    # critic_encoder has no matching keys in ck["model"] so it stays fresh.
    own = model.state_dict()
    merged = dict(own)
    for k, v in ck["model"].items():
        if k in merged and merged[k].shape == v.shape:
            merged[k] = v
    model.load_state_dict(merged)                       # actor loads; critic_encoder fresh
    sd = model.state_dict()
    for n, p in model.named_parameters():
        if n.startswith("critic_encoder."):
            src = "actor_encoder." + n[len("critic_encoder."):]
            if src in sd and sd[src].shape == p.shape:
                p.data.copy_(sd[src])                   # warm init from actor encoder
    return model, ck


def freeze_for_value_fit(model, train_encoder: bool):
    for p in model.parameters():
        p.requires_grad_(False)
    names = []
    for n, p in model.named_parameters():
        if n.startswith("critic.") or (train_encoder and n.startswith("critic_encoder.")):
            p.requires_grad_(True); names.append(n)
    return names


def _batches(vs, combat_only, batch, device, shuffle=True, epoch=0):
    idx = np.flatnonzero(vs.combat) if combat_only else np.arange(len(vs.g))
    if shuffle:
        np.random.default_rng(epoch).shuffle(idx)
    for s in range(0, idx.size, batch):
        b = idx[s:s + batch]
        f = torch.as_tensor(vs.f[b].astype(np.float32), device=device)
        i = torch.as_tensor(vs.i[b].astype(np.int64), device=device)
        g = torch.as_tensor(vs.g[b].astype(np.float32), device=device)
        yield TensorObs(f, i), g


def train_value(*, targets, holdout, ckpt, out, epochs=10, lr=1e-3, batch=4096,
                device="cpu", train_encoder=False, combat_only=True,
                huber_beta=1.0):
    if train_encoder:
        model, ck = build_unshared_from_shared(ckpt, device)
    else:
        model, ck = load_agent(ckpt, env_kind="run", obs_dim=OBS_DIM,
                               n_actions=N_ACTIONS, device=device)
    trainable = freeze_for_value_fit(model, train_encoder)
    opt = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=lr)
    loss_fn = nn.SmoothL1Loss(beta=huber_beta)
    tr = load_value_set(targets); ho = load_value_set(holdout)
    for name, path, vs in (("targets", targets, tr), ("holdout", holdout, ho)):
        schema = vs.provenance.get("obs_schema")
        if schema != 13:
            raise ValueError(
                f"train_value: {name} shard set at {path!r} has obs_schema={schema!r}, "
                f"expected 13 -- refusing to train/grade against a mismatched obs contract")

    def holdout_loss():
        model.eval(); tot = k = 0.0
        with torch.no_grad():
            for obs, g in _batches(ho, combat_only, batch, device, shuffle=False):
                tot += float(loss_fn(model.get_value(obs), g)) * g.numel(); k += g.numel()
        return tot / max(k, 1)

    best = float("inf"); best_state = None; hist = []
    for ep in range(epochs):
        model.train()
        for obs, g in _batches(tr, combat_only, batch, device, epoch=ep):
            opt.zero_grad(); loss = loss_fn(model.get_value(obs), g)
            loss.backward(); opt.step()
        hl = holdout_loss(); hist.append(hl)
        if hl < best:
            best = hl
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        print(f"epoch {ep}  holdout_huber {hl:.5f}  (best {best:.5f})")

    payload = dict(ck)                       # copy every metadata key verbatim
    if train_encoder:
        payload["shared_encoder"] = False
    payload["model"] = best_state            # policy params identical, critic updated
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, out)
    prov = {"ckpt": ckpt, "targets": targets, "holdout": holdout,
            "trainable": trainable, "epochs": epochs, "lr": lr, "batch": batch,
            "combat_only": combat_only, "best_holdout_huber": best,
            "holdout_curve": hist, "train_encoder": train_encoder}
    Path(str(out) + ".vfit.json").write_text(json.dumps(prov, indent=2))
    print(json.dumps({k: prov[k] for k in ("best_holdout_huber", "trainable")}, default=str))
    return prov


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--holdout", required=True)
    ap.add_argument("--ckpt", default="runs/sts2_run_torch_v24_s27.pt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch", type=int, default=4096)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--combat-only", action="store_true", default=True)
    ap.add_argument("--all-states", dest="combat_only", action="store_false")
    ap.add_argument("--train-encoder", action="store_true")
    a = ap.parse_args(argv)
    train_value(targets=a.targets, holdout=a.holdout, ckpt=a.ckpt, out=a.out,
                epochs=a.epochs, lr=a.lr, batch=a.batch, device=a.device,
                combat_only=a.combat_only, train_encoder=a.train_encoder)


if __name__ == "__main__":
    raise SystemExit(main())
