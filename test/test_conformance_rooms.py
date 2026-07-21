"""SP2 Task 8e — encounter-pool order + RoomSet grab-model parity.

The game keeps each act's encounters in one alphabetical-by-class list
(``ActModel.GenerateAllEncounters``) and derives the weak / regular / elite /
boss pools by filtering it on ``RoomType``/``IsWeak``. ``ActModel.GenerateRooms``
then draws them with ``GrabBag.GrabAndRemove``'s reject-and-redraw (avoiding the
previous pick's encounter and shared ``EncounterTag``) and rolls boss + ancient
with ``NextItem`` — all on the ``UpFront`` stream, in that exact order.

This pins the pool **order** and the **grab model** (draw values *and* count) by
replaying ``RunManager.GenerateRooms`` on a parity ``RunState``'s ``UpFront``:
the shared-ancient shuffle + per-act subset rolls, then each act's
``RoomSet.generate``. For every recorded seed the resulting
normal/elite/event/boss/ancient lists reproduce the run.save exactly. The full
production wiring (start_run generating every act up front, and the final
``UpFront`` counter) is Task 8f; here the sequence lives in the test harness.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.actmap import ACT_MAP_CONFIGS
from sts2_rl.conformance.ids import (
    ACT_SIM_NAME,
    encounter_game_id,
    event_game_id,
)
from sts2_rl.conformance.save import parse_save
from sts2_rl.driver import SHARED_ANCIENTS
from sts2_rl.rooms import RoomSet, act_rooms
from sts2_rl.run import RunState

REC = Path(__file__).resolve().parents[1].parent / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(
    not REC.exists(), reason="RunReplays saves not present"
)

SEEDS = sorted(p.name for p in REC.iterdir()) if REC.exists() else []

# Each act's AllAncients (Models/Acts/*.cs). Act-1 acts (Overgrowth/Underdocks)
# roll Neow; the shared ancient (darv) is layered on later acts by the subset.
ACT_ALL_ANCIENTS: dict[str, tuple[str, ...]] = {
    "overgrowth": ("neow",),
    "underdocks": ("neow",),
    "hive": ("orobas", "pael", "tezcatara"),
    "glory": ("nonupeipe", "tanx", "vakuu"),
}


def _generate_run_rooms(run: RunState, act_names: list[str]) -> list[RoomSet]:
    """RunManager.GenerateRooms on the parity ``UpFront`` stream: shuffle the
    shared ancients, hand each act after the first a random prefix, then
    generate every act's rooms in order."""
    up = run.rng_set.up_front
    remaining = list(SHARED_ANCIENTS)
    up.shuffle(remaining)
    subsets: dict[str, tuple[str, ...]] = {}
    for name in act_names[1:]:
        take = up.next_int(len(remaining) + 1)
        subsets[name] = tuple(remaining[:take])
        remaining = remaining[take:]
    room_sets = []
    for name in act_names:
        cfg = ACT_MAP_CONFIGS[name]
        ancient_pool = (*ACT_ALL_ANCIENTS[name], *subsets.get(name, ()))
        room_sets.append(RoomSet.generate(
            act_rooms(name), up, cfg.num_rooms, cfg.num_weak_encounters,
            ancient_pool=ancient_pool,
        ))
    return room_sets


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_rooms_match_save(seed):
    """Every act's pre-rolled room lists reproduce the run.save."""
    o = parse_save(REC / seed / "floor_18" / "run.save")
    act_names = [ACT_SIM_NAME[a] for a in o.acts]
    room_sets = _generate_run_rooms(RunState(string_seed=seed), act_names)
    for i, rs in enumerate(room_sets):
        exp = o.encounter_ids_by_act[i]
        assert [encounter_game_id(k) for k in rs.normal_keys] == exp["normal"]
        assert [encounter_game_id(k) for k in rs.elite_keys] == exp["elite"]
        assert [event_game_id(k) for k in rs.event_ids] == exp["event"]
        assert encounter_game_id(rs.boss_key) == exp["boss"]
        assert event_game_id(rs.ancient_key) == exp["ancient"]


def test_overgrowth_pools_in_game_encounter_order():
    """Guard the reorder: Overgrowth weak/normal follow AllEncounters
    (alphabetical-by-class), not the first-run discovery-swap order."""
    rooms = act_rooms("overgrowth")
    assert rooms.weak_keys == (
        "fuzzy_wurm_weak", "nibbits_weak", "shrinker_beetle_weak",
        "slimes_weak",
    )
    assert rooms.normal_keys == (
        "cubex_construct", "flyconid", "fogmog", "inklets_normal",
        "mawler_normal", "nibbits_normal", "overgrowth_crawlers",
        "ruby_raiders", "slimes_normal", "slithering_strangler",
        "snapping_jaxfruit", "vine_shambler",
    )


def test_legacy_random_path_unchanged():
    """A legacy ``random.Random`` keeps the single-choice model: rooms fill to
    length, no ancient is rolled (the driver does that), and the parity-only
    ``ancient_key`` stays absent."""
    import random

    cfg = ACT_MAP_CONFIGS["overgrowth"]
    rs = RoomSet.generate(
        act_rooms("overgrowth"), random.Random(1234),
        cfg.num_rooms, cfg.num_weak_encounters,
    )
    assert len(rs.normal_keys) == cfg.num_rooms
    assert len(rs.elite_keys) == RoomSet.MAX_ELITES
    assert rs.boss_key in act_rooms("overgrowth").boss_keys
    assert rs.ancient_key is None
