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


def target_stats(tgt_idx, tgt_p) -> dict:
    """Per-record SHARPNESS of the searched targets — no checkpoint involved.

    Reads the raw `(n, k)` shard arrays (search_worker's `tgt_idx`/`tgt_p`,
    float16 with the −1 pad on BOTH), not a DistillSet, so `--targets-only`
    can measure a shard set without loading a model. `tgt_idx >= 0` is the
    validity mask; pads carry −1 in `tgt_p`, which would be nonsense mass and
    a nan under `log`, so they are dropped before either statistic.

      * ``gap``     top1 − top2 target mass. A record with a single candidate
                    (mass-cap collapse) has no second and scores 1.0.
      * ``entropy`` Shannon entropy (nats) over the valid candidate mass only
                    — the ~3-candidate neighbourhood the v26 diagnosis
                    measured at ~0.958 nats under T=1.0.
    """
    idx = np.asarray(tgt_idx)
    p = np.asarray(tgt_p, dtype=np.float64)
    if idx.shape != p.shape:
        raise ValueError(f"target_stats: tgt_idx {idx.shape} and tgt_p "
                         f"{p.shape} must have the same (n, k) shape")
    valid = idx >= 0
    p = np.where(valid, p, 0.0)
    n_valid = valid.sum(axis=1)

    srt = np.sort(p, axis=1)[:, ::-1]          # descending, pads now 0.0
    top1 = srt[:, 0]
    top2 = srt[:, 1] if srt.shape[1] > 1 else np.zeros_like(top1)
    gap = top1 - top2

    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(p > 0.0, -p * np.log(np.where(p > 0.0, p, 1.0)), 0.0)
    return {"gap": gap, "entropy": terms.sum(axis=1), "n_valid": n_valid}


def target_stats_from_dir(distill_dir) -> dict:
    """`target_stats` over every shard of a shard set, concatenated in the
    contract's shard order (`search_worker.shard_paths`)."""
    from tools import search_worker

    parts = [target_stats(s["tgt_idx"], s["tgt_p"])
             for s in search_worker.iter_shards(distill_dir)]
    if not parts:
        raise ValueError(f"target_stats_from_dir: no shards under {distill_dir}")
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


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
    ap.add_argument("ckpts", nargs="*",
                    help="checkpoints; the FIRST is the flip reference "
                         "(not used, and not required, with --targets-only)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--targets-only", action="store_true",
                    help="measure the TARGETS' sharpness (median top1-top2 "
                         "mass gap, median entropy) and exit — no checkpoint "
                         "is loaded. Used by the v27 temperature calibration.")
    args = ap.parse_args()

    if args.targets_only:
        st = target_stats_from_dir(args.distill_dir)
        prov = {}
        prov_path = os.path.join(args.distill_dir, "provenance.json")
        if os.path.exists(prov_path):
            prov = json.loads(open(prov_path, encoding="utf-8-sig").read())
        summary = {
            "distill_dir": args.distill_dir,
            "temperature": prov.get("temperature"),
            "records": int(len(st["gap"])),
            "provenance_records": prov.get("records"),
            "median_gap": float(np.median(st["gap"])),
            "median_entropy": float(np.median(st["entropy"])),
            "mean_gap": float(st["gap"].mean()),
            "mean_entropy": float(st["entropy"].mean()),
            "median_n_valid": float(np.median(st["n_valid"])),
            "n_single_candidate": int((st["n_valid"] == 1).sum()),
        }
        multi = st["n_valid"] > 1
        if multi.any():
            summary["median_gap_multi"] = float(np.median(st["gap"][multi]))
            summary["median_entropy_multi"] = float(
                np.median(st["entropy"][multi]))
        for key, val in summary.items():
            print(f"{key:<24} {val}")
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2)
            print(f"\nwrote {args.json_out}")
        return

    if not args.ckpts:
        raise SystemExit("distill_diag: at least one checkpoint is required "
                         "(or pass --targets-only)")

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
