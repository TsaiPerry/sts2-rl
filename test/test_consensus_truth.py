import numpy as np
from pathlib import Path
from tools.search_worker import write_shard
from tools.consensus_truth import build_consensus, grade

def _mk(dir, winners, f_seed=7):
    """Write a 1-shard estimator dir: each decision has 3 candidates [10,11,12];
    tgt_p peaks on the given winner index so winner_and_gap recovers it."""
    d = Path(dir); d.mkdir(parents=True)
    n = len(winners)
    f = np.tile(np.arange(4).astype(np.float16), (n, 1)) + f_seed
    i = np.zeros((n, 2), np.int32)
    mask = np.ones((n, 3), bool)
    tgt_idx = np.tile(np.array([10, 11, 12], np.int32), (n, 1))
    tgt_p = np.full((n, 3), 0.05, np.float16)
    for r, w in enumerate(winners):
        tgt_p[r, w] = 0.90
    write_shard(d / "shard-00000.npz", f, i, mask, tgt_idx, tgt_p)
    (d / "provenance.json").write_text('{"m":64,"rollout_steps":120,"records":%d,"stats":{}}' % n)
    return str(d)

def test_consensus_majority_and_grade(tmp_path):
    # decision 0: all agree winner 0 (stable); decision 1: split 2-1 winner 1 (stable);
    # decision 2: all different (not stable)
    g1 = _mk(tmp_path/"g1", [0, 1, 0]); g2 = _mk(tmp_path/"g2", [0, 1, 1])
    g3 = _mk(tmp_path/"g3", [0, 1, 2])
    cons = build_consensus([g1, g2, g3])
    assert cons["stable"].tolist() == [True, True, False]
    est_good = _mk(tmp_path/"eg", [0, 1, 0])         # matches consensus on stable
    r = grade(est_good, [g1, g2, g3], tau=0.0)
    assert r["n_stable_decisive"] == 2 and r["agree"] == 2 and r["rate"] == 1.0
    est_bad = _mk(tmp_path/"eb", [2, 2, 2])
    assert grade(est_bad, [g1, g2, g3], tau=0.0)["rate"] == 0.0

def test_grade_rejects_misaligned_estimator(tmp_path):
    # estimator drawn from a different bank/seed (f_seed differs) must be rejected,
    # not silently graded against mismatched rows.
    g1 = _mk(tmp_path/"g1", [0, 1, 0]); g2 = _mk(tmp_path/"g2", [0, 1, 1])
    g3 = _mk(tmp_path/"g3", [0, 1, 2])
    est_misaligned = _mk(tmp_path/"em", [0, 1, 0], f_seed=99)
    try:
        grade(est_misaligned, [g1, g2, g3], tau=0.0)
        assert False, "expected ValueError for misaligned estimator"
    except ValueError as e:
        assert "not record-aligned" in str(e)
