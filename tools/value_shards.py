"""Value-target shard IO + Monte-Carlo return-to-go, for the critic value-fit
(spec 2026-08-31-critic-value-fit-design). A record is one visited run state:
    f  float16 (n, f_dim)   obs float block   (env _build_obs 'f')
    i  int32   (n, i_dim)   obs id block      (env _build_obs 'i')
    g  float32 (n,)         discounted return-to-go under the CURRENT policy
    combat bool (n,)        was a combat-block action legal at this state
Mirrors tools/search_worker.py's shard contract (uncompressed savez, filename
order is part of the contract, provenance JSON beside the shards)."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np

VALUE_KEYS = ("f", "i", "g", "combat")
_DTYPES = {"f": np.float16, "i": np.int32, "g": np.float32, "combat": np.bool_}


def returns_to_go(rewards, gamma: float) -> np.ndarray:
    r = np.asarray(rewards, dtype=np.float64)
    g = np.empty_like(r)
    acc = 0.0
    for t in range(r.size - 1, -1, -1):
        acc = r[t] + gamma * acc
        g[t] = acc
    return g


def write_value_shard(path, f, i, g, combat) -> Path:
    arrays = {"f": np.asarray(f), "i": np.asarray(i),
              "g": np.asarray(g), "combat": np.asarray(combat)}
    n = arrays["f"].shape[0]
    for k, a in arrays.items():
        if a.shape[0] != n:
            raise ValueError(f"write_value_shard: ragged shard — f has {n} "
                             f"records but {k} has {a.shape[0]}")
        arrays[k] = a.astype(_DTYPES[k], copy=False)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        np.savez(fh, **arrays)
    return path


def iter_value_shards(path):
    path = Path(path)
    shards = (sorted(p for p in path.iterdir() if p.suffix == ".npz")
              if path.is_dir() else [path])
    for shard in shards:
        with np.load(shard) as data:
            yield {k: np.asarray(data[k]) for k in VALUE_KEYS}


@dataclass
class ValueSet:
    f: np.ndarray
    i: np.ndarray
    g: np.ndarray
    combat: np.ndarray
    provenance: dict


def load_value_set(path) -> ValueSet:
    cols = {k: [] for k in VALUE_KEYS}
    for sh in iter_value_shards(path):
        for k in VALUE_KEYS:
            cols[k].append(sh[k])
    if not cols["f"]:
        raise SystemExit(f"{path}: no shards")
    prov = {}
    pj = Path(path) / "provenance.json"
    if pj.exists():
        prov = json.loads(pj.read_text())
    return ValueSet(*(np.concatenate(cols[k]) for k in VALUE_KEYS), provenance=prov)
