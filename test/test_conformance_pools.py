"""SP2 Task 8b — pool-completeness oracle (the Task-8 acceptance gate).

For every act in every run.save, the sim's pre-rolled pools must be able to
produce the game's drawn ids. This is a *membership* check (not order — draw
order is verified separately in 8e/8f):

  - events  : image(event_pool ∪ SHARED_EVENTS) == set(save.event_ids)  (exact:
              the event queue is the WHOLE pool shuffled, so every id appears).
  - normals : set(save.normal_encounter_ids) ⊆ image(weak ∪ normal)  (subset:
              only NumberOfWeakEncounters weak draws happen, so the weak pool
              need not be fully covered).
  - elites  : set(save.elite_encounter_ids)  ⊆ image(elite).
  - boss    : save.boss_id ∈ image(boss).

The events check FAILS until Task 8c completes SHARED_EVENTS (crystal_sphere +
war_historian_repy) — it is marked xfail(strict) here and un-marked in 8c.
Every floor_18 save already carries all three acts' rooms (the game generates
them up front), so one floor per seed exercises every act.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.ids import (
    ACT_SIM_NAME,
    encounter_game_id,
    event_game_id,
)
from sts2_rl.conformance.save import parse_save
from sts2_rl.events import SHARED_EVENTS
from sts2_rl.rooms import act_rooms

REC = Path(__file__).resolve().parents[1].parent / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(
    not REC.exists(), reason="RunReplays saves not present"
)

SEEDS = sorted(p.name for p in REC.iterdir()) if REC.exists() else []


def _acts(seed: str):
    """(act_id, sim_name, oracle_dict) for each act in the seed's floor_18 save."""
    o = parse_save(REC / seed / "floor_18" / "run.save")
    for act_id, enc in zip(o.acts, o.encounter_ids_by_act):
        yield act_id, ACT_SIM_NAME[act_id], enc


def test_ids_map_has_no_stale_keys():
    # Every encounter-map key belongs to some act's pool (guards typos/rot).
    pooled = set()
    for name in ("overgrowth", "underdocks", "hive", "glory"):
        r = act_rooms(name)
        pooled |= set(r.weak_keys + r.normal_keys + r.elite_keys + r.boss_keys)
    from sts2_rl.conformance.ids import ENCOUNTER_GAME_IDS

    assert set(ENCOUNTER_GAME_IDS) == pooled


@pytest.mark.parametrize("seed", SEEDS)
def test_pool_encounters_and_boss_cover_save(seed):
    for act_id, name, enc in _acts(seed):
        r = act_rooms(name)
        normal_img = {encounter_game_id(k) for k in r.weak_keys + r.normal_keys}
        elite_img = {encounter_game_id(k) for k in r.elite_keys}
        boss_img = {encounter_game_id(k) for k in r.boss_keys}
        assert set(enc["normal"]) <= normal_img, f"{seed} {act_id} normals"
        assert set(enc["elite"]) <= elite_img, f"{seed} {act_id} elites"
        assert enc["boss"] in boss_img, f"{seed} {act_id} boss"


@pytest.mark.parametrize("seed", SEEDS)
def test_pool_events_exact(seed):
    for act_id, name, enc in _acts(seed):
        r = act_rooms(name)
        event_img = {
            event_game_id(k) for k in tuple(r.event_pool) + tuple(SHARED_EVENTS)
        }
        assert event_img == set(enc["event"]), f"{seed} {act_id} events"
