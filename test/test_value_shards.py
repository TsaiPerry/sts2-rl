import numpy as np, json
from pathlib import Path
from tools.value_shards import returns_to_go, write_value_shard, load_value_set

def test_returns_to_go_discounts_backward():
    g = returns_to_go([1.0, 2.0, 3.0], gamma=0.5)
    # g2=3 ; g1=2+0.5*3=3.5 ; g0=1+0.5*3.5=2.75
    assert np.allclose(g, [2.75, 3.5, 3.0])

def test_returns_to_go_gamma_one_is_suffix_sum():
    assert np.allclose(returns_to_go([1, 1, 1, 1], 1.0), [4, 3, 2, 1])

def test_write_and_load_roundtrip(tmp_path):
    f = np.zeros((2, 3), np.float32); i = np.ones((2, 4), np.int64)
    g = np.array([1.5, -2.0], np.float64); c = np.array([True, False])
    d = tmp_path / "vt"; d.mkdir()
    write_value_shard(d / "shard-00000.npz", f, i, g, c)
    (d / "provenance.json").write_text(json.dumps({"obs_schema": 13}))
    vs = load_value_set(str(d))
    assert vs.f.shape == (2, 3) and vs.i.dtype == np.int32
    assert np.allclose(vs.g, [1.5, -2.0]) and vs.combat.tolist() == [True, False]
    assert vs.provenance["obs_schema"] == 13

def test_write_shard_rejects_ragged(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        write_value_shard(tmp_path / "s.npz", np.zeros((2, 3)), np.zeros((3, 4)),
                          np.zeros(2), np.zeros(2, bool))
