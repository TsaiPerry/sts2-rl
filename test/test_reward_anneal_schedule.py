import pytest
from train_torch import reward_anneal_weight


def w(it, warm, final=0.0, start=0, n=100):
    return reward_anneal_weight(it, start, n, warm, final)


def test_weight_is_one_through_critic_warmup():
    # Elites stay at full weight for the whole warmup (no stale-jump at unfreeze).
    assert w(0, warm=4) == 1.0
    assert w(3, warm=4) == 1.0


def test_weight_anneals_one_to_final_after_warmup():
    # First post-warmup iteration starts the descent from 1.0...
    assert w(4, warm=4) == pytest.approx(1.0, abs=1e-6)
    # ...the last iteration reaches `final`.
    assert w(99, warm=4, final=0.0) == pytest.approx(0.0, abs=1e-6)
    # Monotone non-increasing across the anneal span.
    vals = [w(it, warm=4) for it in range(4, 100)]
    assert all(b <= a + 1e-9 for a, b in zip(vals, vals[1:]))


def test_weight_respects_nonzero_final():
    assert w(99, warm=0, final=0.25) == pytest.approx(0.25, abs=1e-6)


def test_zero_warmup_starts_annealing_immediately():
    assert w(0, warm=0) == pytest.approx(1.0, abs=1e-6)
    assert w(99, warm=0, final=0.0) == pytest.approx(0.0, abs=1e-6)
