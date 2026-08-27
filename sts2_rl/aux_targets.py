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


TURN_SCALE = 30.0


def hp_lost_next_turn(
    turn_col: np.ndarray,
    hp_col: np.ndarray,
    done_col: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """targets[t,e] = cumulative combat.player.hp_ratio DROPS from t until
    the first step whose (rounded) combat turn value differs — i.e. "HP I
    will lose before my next turn starts", the enemy phase + end-of-turn
    burn included. valid[t,e] requires an in-combat step (turn > 0) whose
    window closes in-buffer (boundary found, or the episode's done fence
    closes the segment — a death mid-window is a real, labelable outcome).

    Two deliberate wrinkles, do not "fix" them:
    * per-step drops are guarded by the NEXT step still being in combat —
      combat.player.hp_ratio reads 0.0 outside combat, so the victory
      transition would otherwise register as losing the player's whole bar;
    * turns >= 30 saturate in the obs encoding (full_env.py:1086), so two
      saturated turns produce no boundary and the window runs on to the
      combat's end. Rare, accepted.
    """
    N, E = turn_col.shape
    turns = np.rint(turn_col * TURN_SCALE).astype(np.int64)
    targets = np.zeros((N, E), dtype=np.float32)
    valid = np.zeros((N, E), dtype=bool)
    done = np.asarray(done_col, dtype=bool)
    for e in range(E):
        starts = np.flatnonzero(done[:, e])
        bounds = np.concatenate(([0], starts, [N]))
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            if hi <= lo:
                continue
            tk = turns[lo:hi, e]
            h = hp_col[lo:hi, e]
            drops = np.maximum(0.0, h[:-1] - h[1:])
            drops[tk[1:] == 0] = 0.0          # combat-end transition guard
            cum = np.concatenate(([0.0], np.cumsum(drops)))
            seg_end = hi - lo - 1
            closed = hi < N                    # done INSIDE the window
            for i in range(hi - lo):
                if tk[i] == 0:
                    continue                   # out-of-combat: invalid
                later = np.flatnonzero(tk[i + 1:] != tk[i])
                if later.size:
                    s = i + 1 + later[0]
                    targets[lo + i, e] = cum[s] - cum[i]
                    valid[lo + i, e] = True
                elif closed:
                    targets[lo + i, e] = cum[seg_end] - cum[i]
                    valid[lo + i, e] = True
    return targets, valid


def win_outcome(
    done_col: np.ndarray,
    success_col: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """targets[t,e] = the terminal outcome (1.0 win / 0.0 loss) of the
    episode step t belongs to; valid[t,e] only when that episode's closing
    done lands inside this rollout window. done[t]==1 marks obs t as the
    FIRST obs of a new episode and success[t] scores the episode that just
    ended (train_torch records both on the same index — see the succ_buf
    write). A segment still open at the buffer end is unlabeled, exactly
    like hp_lost_next_floors' open-window case."""
    N, E = done_col.shape
    done = np.asarray(done_col, dtype=bool)
    targets = np.zeros((N, E), dtype=np.float32)
    valid = np.zeros((N, E), dtype=bool)
    for e in range(E):
        starts = np.flatnonzero(done[:, e])
        bounds = np.concatenate(([0], starts, [N]))
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            if hi <= lo or hi >= N:
                continue                       # open segment: unlabeled
            targets[lo:hi, e] = success_col[hi, e]
            valid[lo:hi, e] = True
    return targets, valid
