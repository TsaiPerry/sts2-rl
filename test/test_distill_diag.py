"""distill_diag's CE must be train_torch.distill_loss exactly (mean of the
per-record vector), and its flip/agreement logic must decode the -1 pad
convention the way DistillSet documents it."""
import numpy as np
import pytest
import torch

import train_torch
from tools import distill_diag


class StubAgent:
    """action_logits-only stand-in: per-record fixed logits, -inf at illegal
    actions, matching the masked-logits contract the real models honour.

    The logits are looked up by the record id the fixture writes into
    ``f[:, 0]`` rather than being returned as a whole fixed block, because a
    real model's logits are a FUNCTION OF THE OBS ROWS IT IS HANDED: the
    chunked path passes 2 rows at a time and must get those rows' logits.
    """

    def __init__(self, logits):
        self._logits = torch.as_tensor(logits, dtype=torch.float32)

    def action_logits(self, obs, mask):
        rows = obs.f[:, 0].to(torch.int64)
        out = self._logits[rows].clone()
        return out.masked_fill(~mask, float("-inf"))


def _tiny_set():
    # 3 records, 4 actions, k=2. Record 2 has a pad (-1) in slot 1.
    # f[:, 0] is the record id, the only thing StubAgent reads.
    f = np.zeros((3, 5), dtype=np.float32)
    f[:, 0] = np.arange(3, dtype=np.float32)
    i = np.zeros((3, 2), dtype=np.int64)
    mask = np.array([[1, 1, 1, 0],
                     [1, 1, 0, 1],
                     [1, 1, 0, 0]], dtype=bool)
    tgt_idx = np.array([[0, 2], [3, 1], [1, -1]], dtype=np.int64)
    tgt_p = np.array([[0.75, 0.25], [0.4, 0.6], [1.0, -1.0]], dtype=np.float32)
    return train_torch.DistillSet.from_arrays(f, i, mask, tgt_idx, tgt_p,
                                              device="cpu")


def _stub():
    return StubAgent(np.array([[2.0, 0.0, 1.0, -1.0],
                               [0.0, 3.0, 0.0, 1.0],
                               [0.5, 0.5, 9.0, 9.0]], dtype=np.float32))


def test_per_record_ce_mean_equals_distill_loss():
    dset, agent = _tiny_set(), _stub()
    rows = torch.arange(3)
    per = distill_diag.per_record_ce(agent, dset, rows)
    assert per.shape == (3,)
    ref = train_torch.distill_loss(agent, dset, rows)
    assert torch.allclose(per.mean(), ref, atol=0, rtol=0)


def test_target_argmax_never_picks_a_pad():
    dset = _tiny_set()
    tgt = distill_diag.target_argmax(dset)
    # record 0: p .75 on action 0; record 1: p .6 on action 1;
    # record 2: pad in slot 1 (p zeroed) -> action 1.
    assert tgt.tolist() == [0, 1, 1]


def test_masked_argmax_respects_record_mask():
    dset, agent = _tiny_set(), _stub()
    am = distill_diag.masked_argmax(agent, dset, torch.arange(3))
    # record 2's logits peak on actions 2/3 but its mask only allows {0, 1}.
    assert am.tolist() == [0, 1, 0] or am.tolist() == [0, 1, 1]
    assert am[2].item() in (0, 1)


def test_evaluate_chunking_matches_single_pass():
    dset, agent = _tiny_set(), _stub()
    whole = distill_diag.evaluate(agent, dset, device="cpu", chunk=1024)
    chunked = distill_diag.evaluate(agent, dset, device="cpu", chunk=2)
    assert np.allclose(whole["ce"], chunked["ce"])
    assert (whole["argmax"] == chunked["argmax"]).all()


def test_summarize_flip_subset():
    dset, agent = _tiny_set(), _stub()
    res = distill_diag.evaluate(agent, dset, device="cpu", chunk=1024)
    tgt = distill_diag.target_argmax(dset).numpy()
    # Pretend the reference argmax'd action 0 everywhere: records 1 and 2
    # (targets 1, 1) are flips, record 0 (target 0) is not.
    ref_argmax = np.zeros(3, dtype=np.int64)
    summary = distill_diag.summarize(res, tgt, ref_argmax)
    assert summary["n"] == 3
    assert summary["n_flip"] == 2
    assert 0.0 <= summary["agree"] <= 1.0
    assert summary["ce_flip"] >= 0.0
    # Pin the SUBSET, not just the shape: averaging over the non-flip records
    # or over all three would satisfy every assertion above.
    assert summary["ce_flip"] == pytest.approx(float(res["ce"][[1, 2]].mean()))
    assert summary["ce_flip"] != pytest.approx(float(res["ce"].mean()))
    expect_agree_flip = float((res["argmax"][[1, 2]] == np.array([1, 1])).mean())
    assert summary["agree_flip"] == pytest.approx(expect_agree_flip)
    assert summary["ce"] == pytest.approx(float(res["ce"].mean()))
    assert summary["agree"] == pytest.approx(
        float((res["argmax"] == tgt).mean()))
