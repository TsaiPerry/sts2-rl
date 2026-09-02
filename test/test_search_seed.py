import numpy as np
from tools.eval_search import (_salt_base, _rollout_seed_base, _decision_index,
                               ROLLOUT_BASE, SEARCH_SEED_STRIDE)

def test_search_seed0_is_backward_identical():
    # search_seed=0 (and the 3-arg call) must equal the pre-change derivation
    for f, d, m in [(0, 0, 8), (3, 5, 64), (17, 100, 128)]:
        assert _salt_base(f, d, m) == _decision_index(f, d) * m
        assert _salt_base(f, d, m, 0) == _decision_index(f, d) * m
        assert _rollout_seed_base(f, d, m) == ROLLOUT_BASE + _decision_index(f, d) * m
        assert _rollout_seed_base(f, d, m, 0) == ROLLOUT_BASE + _decision_index(f, d) * m

def test_search_seed_bands_are_disjoint():
    # over a realistic (fight, d) grid the m-sample salt ranges for two search
    # seeds never overlap, so independent gold runs never share a rollout draw
    m = 64
    def salts(ss):
        s = set()
        for f in range(60):
            for d in range(20):
                b = _salt_base(f, d, m, ss)
                s.update(range(b, b + m))          # the m per-decision samples
        return s
    s0, s1, s2 = salts(0), salts(1), salts(2)
    assert not (s0 & s1) and not (s0 & s2) and not (s1 & s2)
    def rolls(ss):
        s = set()
        for f in range(60):
            for d in range(20):
                b = _rollout_seed_base(f, d, m, ss)
                s.update(range(b, b + m))
        return s
    r0, r1 = rolls(0), rolls(1)
    assert not (r0 & r1)

def test_stride_exceeds_reachable_salt_range():
    # the search-seed band must sit above any decision_index*m a real run hits
    assert SEARCH_SEED_STRIDE > _decision_index(9999, 511) * 256
