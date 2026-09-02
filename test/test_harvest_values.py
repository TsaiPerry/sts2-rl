import numpy as np
from tools.harvest_values import harvest_values
from tools.value_shards import load_value_set

def test_harvest_one_episode_writes_finite_targets(tmp_path):
    out = tmp_path / "vt"
    summary = harvest_values(episodes=1, seed=0, out=str(out), gamma=0.99,
                             checkpoint=None, ascension=0, shard_size=256)
    vs = load_value_set(str(out))
    assert vs.f.shape[0] == summary["states"] > 0
    assert vs.f.shape[1] == 4736 and vs.i.shape[1] == 1533       # schema 13 dims
    assert np.isfinite(vs.g).all()
    assert vs.combat.dtype == np.bool_
    assert vs.provenance["gamma"] == 0.99 and vs.provenance["obs_schema"] == 13
    # at least some combat states in a real episode
    assert vs.combat.sum() > 0
