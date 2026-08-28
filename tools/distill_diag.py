"""distill_diag.py — v26 distillation diagnosis (spec 2026-08-28).

For each checkpoint given, measures against a distill shard directory:

  * masked CE toward the searched targets — SAME formula as
    train_torch.distill_loss (pinned by test_distill_diag.py), reported as
    the mean over all records and over FLIP records only;
  * argmax agreement — does the checkpoint's masked prior argmax equal the
    target's argmax? — again overall and flip-only.

A FLIP record is one where the target argmax differs from the REFERENCE
checkpoint's prior argmax; the reference is the FIRST checkpoint on the CLI
(by convention the generation seed, v24_s27). Flip records carry the actual
information content of the shard set — on non-flips the target just confirms
what the prior already argmax'd.

Read-only over checkpoints and shards. Run from the repo root:

    .venv\\Scripts\\python.exe tools\\distill_diag.py runs\\distill\\v26_batch1 \\
        runs\\sts2_run_torch_v24_s27.pt runs\\sts2_run_torch_v26_s28.pt \\
        --device cuda --json runs\\distill\\v26_batch1\\diag.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

# Run as a script (`python tools\distill_diag.py ...`), sys.path[0] is tools/,
# not the repo root, so train_torch/sts2_rl would not import. Same bootstrap
# every other CLI tool here uses (tools/search_worker.py, tools/eval_search.py).
_REPO = str(Path(__file__).resolve().parent.parent)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import train_torch
from sts2_rl.checkpoints import load_agent
from sts2_rl.tensor_obs import TensorObs


def per_record_ce(model, dset: "train_torch.DistillSet", rows) -> "torch.Tensor":
    """train_torch.distill_loss WITHOUT the final .mean() — per-record CE.

    Kept textually parallel to distill_loss and pinned equal-by-mean in
    test_distill_diag.py so the two can never drift.
    """
    obs = TensorObs(dset.f[rows], dset.i[rows])
    logp = torch.log_softmax(model.action_logits(obs, dset.mask[rows]), dim=-1)
    gathered = logp.gather(-1, dset.tgt_idx[rows])
    gathered = torch.where(dset.tgt_valid[rows], gathered,
                           torch.zeros_like(gathered))
    return -(dset.tgt_p[rows] * gathered).sum(-1)


def masked_argmax(model, dset: "train_torch.DistillSet", rows) -> "torch.Tensor":
    """Argmax of the checkpoint's prior over the RECORD's legality mask."""
    obs = TensorObs(dset.f[rows], dset.i[rows])
    return model.action_logits(obs, dset.mask[rows]).argmax(dim=-1)


def target_argmax(dset: "train_torch.DistillSet") -> "torch.Tensor":
    """The searched distribution's argmax action id per record.

    tgt_p is zeroed at every pad slot (DistillSet.from_arrays), and every
    record has at least one valid candidate with mass > 0, so the slot argmax
    never lands on padding.

    Caveat: the producer stores tgt_p as float16, so near-equal candidate
    probabilities collapse to the same value and this argmax then breaks the
    tie by SLOT ORDER (the prior's own mass order). The flip count recomputed
    from this is therefore the tool's OWN statistic, not the producer's --
    it lands a little under the search worker's recorded ``stats.flips``
    (1984 vs 1993 on v26_batch1), and the two must not be quoted as the same
    number.
    """
    slot = dset.tgt_p.argmax(dim=-1)
    return dset.tgt_idx.gather(-1, slot.unsqueeze(-1)).squeeze(-1)


def evaluate(model, dset: "train_torch.DistillSet", device: str,
             chunk: int = 1024) -> dict:
    """Full-set per-record CE + prior argmax, chunked, no_grad."""
    ces, ams = [], []
    with torch.no_grad():
        for start in range(0, len(dset), chunk):
            rows = torch.arange(start, min(start + chunk, len(dset)),
                                device=dset.f.device)
            ces.append(per_record_ce(model, dset, rows).cpu().numpy())
            ams.append(masked_argmax(model, dset, rows).cpu().numpy())
    return {"ce": np.concatenate(ces), "argmax": np.concatenate(ams)}


def summarize(res: dict, tgt_am: "np.ndarray", ref_am: "np.ndarray") -> dict:
    """Overall + flip-restricted means. flip = target argmax != REFERENCE
    checkpoint's prior argmax (ref_am is the first CLI checkpoint's)."""
    flip = tgt_am != ref_am
    agree = res["argmax"] == tgt_am
    out = {
        "n": int(len(tgt_am)),
        "n_flip": int(flip.sum()),
        "ce": float(res["ce"].mean()),
        "agree": float(agree.mean()),
    }
    if flip.any():
        out["ce_flip"] = float(res["ce"][flip].mean())
        out["agree_flip"] = float(agree[flip].mean())
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("distill_dir")
    ap.add_argument("ckpts", nargs="+",
                    help="checkpoints; the FIRST is the flip reference")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    prov_path = os.path.join(args.distill_dir, "provenance.json")
    prov = json.loads(open(prov_path, encoding="utf-8-sig").read())
    obs_dim = (int(prov["f_dim"]), int(prov["i_dim"]))
    n_actions = int(prov["n_actions"])

    dset = train_torch.load_distill_set(
        args.distill_dir, device=args.device, obs_dim=obs_dim,
        n_actions=n_actions, obs_schema=prov["obs_schema"],
        card_obs=prov["card_obs"])
    tgt_am = target_argmax(dset).cpu().numpy()
    print(f"{args.distill_dir}: {len(dset)} records, obs {obs_dim}, "
          f"n_actions {n_actions}, card_obs {prov['card_obs']}")

    results, ref_am = {}, None
    for path in args.ckpts:
        model, ckpt = load_agent(path, env_kind="run", obs_dim=obs_dim,
                                 n_actions=n_actions,
                                 card_obs=prov["card_obs"],
                                 device=args.device)
        if ckpt.get("obs_schema") != prov["obs_schema"]:
            raise SystemExit(
                f"{path}: checkpoint obs_schema {ckpt.get('obs_schema')} != "
                f"shard set's {prov['obs_schema']}")
        res = evaluate(model, dset, device=args.device)
        if ref_am is None:
            ref_am = res["argmax"]        # first ckpt = flip reference
        results[path] = summarize(res, tgt_am, ref_am)
        del model
        if args.device.startswith("cuda"):
            torch.cuda.empty_cache()

    hdr = f"{'checkpoint':<40} {'n':>6} {'n_flip':>6} {'ce':>8} {'agree':>7} {'ce_flip':>8} {'agr_flip':>8}"
    print()
    print(hdr)
    for path, s in results.items():
        print(f"{os.path.basename(path):<40} {s['n']:>6} {s['n_flip']:>6} "
              f"{s['ce']:>8.4f} {s['agree']:>7.3f} "
              f"{s.get('ce_flip', float('nan')):>8.4f} "
              f"{s.get('agree_flip', float('nan')):>8.3f}")

    if args.json_out:
        # "records" comes from len(dset), NOT prov["records"]: on a merged
        # shard set that provenance field is a per-part leftover (834 on
        # v26_batch1, whose merged set holds 5004) and echoing it here would
        # mislabel every number beside it.
        payload = {"distill_dir": args.distill_dir,
                   "reference": args.ckpts[0],
                   "records": len(dset),
                   "provenance": {k: prov.get(k) for k in
                                  ("obs_schema", "card_obs", "ckpt")},
                   "results": results}
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
