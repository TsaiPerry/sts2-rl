"""v10 aux-head targets (spec 2026-08-13-aux-hp-head-gae-lambda-design).

Computed post-rollout from the stored observation buffers alone: the rollout
keeps no per-step info dicts, and both scalars are already obs slots
(run.floor = total_floor/50 clipped at its write site run_env.py:1322,
run.hp_ratio = hp/max_hp clipped). done[t]==1 marks obs t as the FIRST obs
of a new episode (the vec env auto-resets into the same buffer slot), so no
window may cross a done flag - the next episode's floors/HP would leak in.
"""
from __future__ import annotations

import numpy as np

FLOOR_SCALE = 50.0


def hp_lost_next_floors(
    floor_col: np.ndarray,
    hp_col: np.ndarray,
    done_col: np.ndarray,
    horizon_floors: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """targets[t,e] = cumulative hp_ratio DROPS from t until the first step
    whose floor advanced >= horizon_floors, or the episode's last in-window
    step, whichever comes first. valid[t,e] is False only when the rollout
    window ends before either stopping point. The lethal blow itself is not
    observable (the done slot already holds the next episode's obs), so
    death labels undercount the final hit - accepted, documented in spec."""
    N, E = floor_col.shape
    floors = np.rint(floor_col * FLOOR_SCALE).astype(np.int64)
    targets = np.zeros((N, E), dtype=np.float32)
    valid = np.zeros((N, E), dtype=bool)
    done = np.asarray(done_col, dtype=bool)
    for e in range(E):
        starts = np.flatnonzero(done[:, e])
        bounds = np.concatenate(([0], starts, [N]))
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            if hi <= lo:
                continue
            f = floors[lo:hi, e]
            h = hp_col[lo:hi, e]
            drops = np.maximum(0.0, h[:-1] - h[1:])
            cum = np.concatenate(([0.0], np.cumsum(drops)))
            # floors are nondecreasing within an episode, so the first index
            # at +horizon is a searchsorted per segment, vectorized over i.
            stop = np.searchsorted(f, f + horizon_floors, side="left")
            seg_end = hi - lo - 1
            closed = hi < N   # segment ended by a done INSIDE the window
            for i in range(hi - lo):
                s = stop[i]
                if s <= seg_end:
                    targets[lo + i, e] = cum[s] - cum[i]
                    valid[lo + i, e] = True
                elif closed:
                    targets[lo + i, e] = cum[seg_end] - cum[i]
                    valid[lo + i, e] = True
    return targets, valid
