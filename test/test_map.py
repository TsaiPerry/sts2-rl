"""Tests for the act map layer: generation (sts2_rl/actmap.py — the
StandardActMap/MapPathPruning/MapPostProcessing port), room resolution
(sts2_rl/rooms.py — RoomSet/UnknownOdds), and RunState travel integration.

Run with:  python -m pytest test/test_map.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.actmap import (
    ACT_MAP_CONFIGS,
    GLORY_MAP,
    HIVE_MAP,
    AscensionLevel,
    MapPointType,
    OVERGROWTH_MAP,
    StandardMap,
    UNDERDOCKS_MAP,
    find_matching_segments,
    gaussian_int,
    golden_path_map,
)
from sts2_rl.rooms import (
    RoomSet,
    RoomType,
    UnknownOdds,
    act_rooms,
    build_room_type_blacklist,
    roll_room_type,
)
from sts2_rl.run import RunState

SEEDS = range(40)


def make_map(seed: int = 0, config=OVERGROWTH_MAP, **kwargs) -> StandardMap:
    return StandardMap(rng=random.Random(seed), config=config, **kwargs)


def edges(act_map: StandardMap) -> list[tuple]:
    result = []
    for point in act_map.all_points():
        for child in point.children:
            result.append((point, child))
    return result


# ═════════════════════════════════════════════════════════════════════════
# Generation: determinism and structure
# ═════════════════════════════════════════════════════════════════════════

def test_map_deterministic_per_seed():
    a, b = make_map(7), make_map(7)
    layout_a = [(p.col, p.row, p.point_type) for p in a.all_points()]
    layout_b = [(p.col, p.row, p.point_type) for p in b.all_points()]
    assert layout_a == layout_b
    edges_a = {((p.col, p.row), (c.col, c.row)) for p, c in edges(a)}
    edges_b = {((p.col, p.row), (c.col, c.row)) for p, c in edges(b)}
    assert edges_a == edges_b


def test_maps_vary_across_seeds():
    layouts = {
        tuple((p.col, p.row, p.point_type) for p in make_map(s).all_points())
        for s in range(5)
    }
    assert len(layouts) > 1


@pytest.mark.parametrize("seed", SEEDS)
def test_structure_invariants(seed):
    act_map = make_map(seed)
    points = list(act_map.all_points())
    assert points, "map has nodes"
    # Grid rows are 1..15; the ancient (row 0) and boss (row 16) live
    # outside the grid.
    assert all(1 <= p.row <= act_map.row_count - 1 for p in points)
    assert act_map.starting_point.point_type == MapPointType.ANCIENT
    assert act_map.boss_point.point_type == MapPointType.BOSS
    # Every edge climbs exactly one row; grid-to-grid edges shift at most
    # one column (post-processing must preserve this). Edges into the
    # boss are exempt: it sits at a fixed column outside the grid, so top
    # row nodes may connect to it from any column — same as the game.
    for parent, child in edges(act_map):
        assert child.row == parent.row + 1
        if child is not act_map.boss_point:
            assert abs(child.col - parent.col) <= 1
    # Top row feeds the boss; the ancient feeds row 1.
    for p in act_map.points_in_row(act_map.row_count - 1):
        assert act_map.boss_point in p.children
    for p in act_map.points_in_row(1):
        assert p in act_map.starting_point.children
    # Every node is on some ancient→boss route: reachable from the start
    # and able to reach the boss.
    reachable = set()
    frontier = [act_map.starting_point]
    while frontier:
        node = frontier.pop()
        if id(node) in reachable:
            continue
        reachable.add(id(node))
        frontier.extend(node.children)
    assert all(id(p) in reachable for p in points)
    for p in points:
        node = p
        while node.children:
            node = next(iter(node.children))
        assert node is act_map.boss_point


@pytest.mark.parametrize("seed", SEEDS)
def test_no_crossovers_before_post_processing(seed):
    # The X-crossover rejection applies during carving; post-processing
    # may move columns afterwards, so check a raw map.
    act_map = make_map(
        seed, enable_pruning=False, enable_post_processing=False
    )
    for parent, child in edges(act_map):
        if child is act_map.boss_point:
            continue
        delta = child.col - parent.col
        if delta == 0:
            continue
        neighbor = act_map.grid[child.col][parent.row]
        counterpart = act_map.grid[parent.col][child.row]
        if neighbor is not None and counterpart is not None:
            assert counterpart not in neighbor.children


# ═════════════════════════════════════════════════════════════════════════
# Point types: forced rows, legality rules, counts
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("seed", SEEDS)
def test_forced_rows(seed):
    act_map = make_map(seed)
    top = act_map.row_count - 1
    for p in act_map.points_in_row(top):
        assert p.point_type == MapPointType.REST_SITE
        assert not p.can_be_modified
    for p in act_map.points_in_row(act_map.row_count - 7):
        assert p.point_type == MapPointType.TREASURE
    for p in act_map.points_in_row(1):
        assert p.point_type == MapPointType.MONSTER


def test_warden_variant_replaces_treasure_row_with_elites():
    act_map = make_map(3, replace_treasure_with_elites=True)
    for p in act_map.points_in_row(act_map.row_count - 7):
        assert p.point_type == MapPointType.ELITE


@pytest.mark.parametrize("seed", SEEDS)
def test_placement_rules_hold(seed):
    act_map = make_map(seed)
    restricted = {
        MapPointType.ELITE,
        MapPointType.REST_SITE,
        MapPointType.TREASURE,
        MapPointType.SHOP,
    }
    sibling_restricted = {
        MapPointType.REST_SITE,
        MapPointType.UNKNOWN,
        MapPointType.ELITE,
        MapPointType.SHOP,
    }
    top = act_map.row_count - 1
    for p in act_map.all_points():
        # Lower map: no rests or elites below row 6.
        if p.row < 6:
            assert p.point_type not in (
                MapPointType.REST_SITE,
                MapPointType.ELITE,
            )
        # Upper map: no rests in the two rows under the forced rest row.
        if act_map.row_count - 3 <= p.row < top:
            assert p.point_type != MapPointType.REST_SITE
        # Elite/Rest/Treasure/Shop never neighbor their own type.
        if p.point_type in restricted:
            for child in p.children:
                assert child.point_type != p.point_type
        # A fork never offers two of the sibling-restricted types.
        # (Monster is also sibling-restricted at assignment time, but the
        # unassigned→Monster fill legitimately creates monster siblings.)
        if p.point_type in sibling_restricted:
            siblings = {
                s
                for parent in p.parents
                if parent is not act_map.starting_point
                for s in parent.children
                if s is not p
            }
            assert all(s.point_type != p.point_type for s in siblings)


@pytest.mark.parametrize("seed", SEEDS)
def test_point_type_counts_meet_targets(seed):
    act_map = make_map(seed)
    counts: dict[MapPointType, int] = {}
    for p in act_map.all_points():
        counts[p.point_type] = counts.get(p.point_type, 0) + 1
    # Shops/elites/rests/unknowns are queue-placed then repaired back up
    # to target after pruning.
    assert counts.get(MapPointType.SHOP, 0) == act_map.counts.shops
    assert counts.get(MapPointType.ELITE, 0) == act_map.counts.elites
    assert counts.get(MapPointType.UNKNOWN, 0) == act_map.counts.unknowns
    # Rests: the queue places `counts.rests` on top of the forced pre-boss
    # row, but the repair step counts forced rests toward the target — so
    # after pruning the total is only guaranteed to stay in this range
    # (RepairPointType counts all points of the type).
    forced_rests = len(act_map.points_in_row(act_map.row_count - 1))
    total_rests = counts.get(MapPointType.REST_SITE, 0)
    assert (
        act_map.counts.rests
        <= total_rests
        <= act_map.counts.rests + forced_rests
    )
    assert counts.get(MapPointType.UNASSIGNED, 0) == 0


@pytest.mark.parametrize("seed", SEEDS)
def test_no_duplicate_segments_after_pruning(seed):
    act_map = make_map(seed)
    assert find_matching_segments(act_map.starting_point) == []


@pytest.mark.parametrize(
    "config", [OVERGROWTH_MAP, UNDERDOCKS_MAP, HIVE_MAP, GLORY_MAP]
)
def test_all_act_configs_generate(config):
    act_map = make_map(11, config=config)
    assert act_map.row_count == config.num_rooms + 1
    for p in act_map.points_in_row(act_map.row_count - 7):
        assert p.point_type == MapPointType.TREASURE
    assert find_matching_segments(act_map.starting_point) == []


def test_count_rolls_match_source_ranges():
    rng = random.Random(0)
    for _ in range(200):
        assert 10 <= OVERGROWTH_MAP.roll_counts(rng).unknowns <= 14
        assert 6 <= OVERGROWTH_MAP.roll_counts(rng).rests <= 7
        assert 9 <= HIVE_MAP.roll_counts(rng).unknowns <= 13
        assert 6 <= HIVE_MAP.roll_counts(rng).rests <= 7
        assert 5 <= GLORY_MAP.roll_counts(rng).rests <= 6
        counts = UNDERDOCKS_MAP.roll_counts(rng)
        assert counts.shops == 3 and counts.elites == 5
    assert set(ACT_MAP_CONFIGS) == {
        "overgrowth", "underdocks", "hive", "glory",
    }


def test_gaussian_int_respects_bounds():
    rng = random.Random(1)
    values = {gaussian_int(rng, 12, 1, 10, 14) for _ in range(500)}
    assert values <= set(range(10, 15))
    assert 12 in values


def test_golden_path_map():
    act_map = golden_path_map(random.Random(0))
    rows = [act_map.points_in_row(r) for r in range(1, act_map.row_count)]
    assert all(len(row) == 1 for row in rows)
    types = [row[0].point_type for row in rows]
    assert types[0] == MapPointType.MONSTER
    assert types[-1] == MapPointType.REST_SITE
    assert types.count(MapPointType.TREASURE) == 2
    assert types.count(MapPointType.ELITE) == 2
    last = rows[-1][0]
    assert act_map.boss_point in last.children


# ═════════════════════════════════════════════════════════════════════════
# Unknown ("?") odds
# ═════════════════════════════════════════════════════════════════════════

class FixedRng:
    """random()-only stub returning scripted values."""

    def __init__(self, values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0)


def test_unknown_odds_base_and_pity():
    odds = UnknownOdds()
    assert odds.odds(RoomType.MONSTER) == pytest.approx(0.1)
    assert odds.odds(RoomType.TREASURE) == pytest.approx(0.02)
    assert odds.odds(RoomType.SHOP) == pytest.approx(0.03)
    assert odds.event_odds == pytest.approx(0.85)
    # High roll → Event; every non-event type gains its base odds.
    assert odds.roll(FixedRng([0.99])) == RoomType.EVENT
    assert odds.odds(RoomType.MONSTER) == pytest.approx(0.2)
    assert odds.odds(RoomType.TREASURE) == pytest.approx(0.04)
    assert odds.odds(RoomType.SHOP) == pytest.approx(0.06)
    # Roll under the monster odds → Monster; monster resets, others grow.
    assert odds.roll(FixedRng([0.15])) == RoomType.MONSTER
    assert odds.odds(RoomType.MONSTER) == pytest.approx(0.1)
    assert odds.odds(RoomType.TREASURE) == pytest.approx(0.06)
    assert odds.odds(RoomType.SHOP) == pytest.approx(0.09)
    odds.reset_to_base()
    assert odds.odds(RoomType.SHOP) == pytest.approx(0.03)


def test_unknown_odds_blacklist_suppresses_shop():
    odds = UnknownOdds()
    # Cumulative order is monster, treasure, shop: 0.13 would land on
    # shop, but the blacklist skips it → Event, and shop gains no pity.
    result = odds.roll(FixedRng([0.13]), blacklist={RoomType.SHOP})
    assert result == RoomType.EVENT
    assert odds.odds(RoomType.SHOP) == pytest.approx(0.03)


def test_blacklist_rules():
    class FakePoint:
        def __init__(self, point_type):
            self.point_type = point_type

    shop = FakePoint(MapPointType.SHOP)
    monster = FakePoint(MapPointType.MONSTER)
    assert build_room_type_blacklist([RoomType.SHOP], []) == {RoomType.SHOP}
    assert build_room_type_blacklist([], [shop, shop]) == {RoomType.SHOP}
    assert build_room_type_blacklist([], [shop, monster]) == set()
    assert build_room_type_blacklist([RoomType.MONSTER], [monster]) == set()


def test_roll_room_type_direct_mappings():
    odds = UnknownOdds()
    rng = random.Random(0)
    assert roll_room_type(MapPointType.MONSTER, odds, rng) == RoomType.MONSTER
    assert roll_room_type(MapPointType.ELITE, odds, rng) == RoomType.ELITE
    assert roll_room_type(MapPointType.BOSS, odds, rng) == RoomType.BOSS
    assert roll_room_type(MapPointType.SHOP, odds, rng) == RoomType.SHOP
    assert roll_room_type(MapPointType.TREASURE, odds, rng) == RoomType.TREASURE
    assert roll_room_type(MapPointType.REST_SITE, odds, rng) == RoomType.REST_SITE
    assert roll_room_type(MapPointType.ANCIENT, odds, rng) == RoomType.EVENT


# ═════════════════════════════════════════════════════════════════════════
# RoomSet: encounter ordering
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("act", ["overgrowth", "underdocks", "hive"])
@pytest.mark.parametrize("seed", range(10))
def test_room_set_ordering(act, seed):
    rooms = act_rooms(act)
    config = ACT_MAP_CONFIGS[act]
    room_set = RoomSet.generate(
        rooms,
        random.Random(seed),
        config.num_rooms,
        config.num_weak_encounters,
    )
    normals = room_set.normal_keys
    assert len(normals) == config.num_rooms
    # The first fights come from the weak pool, the rest from the regular
    # pool.
    for key in normals[: config.num_weak_encounters]:
        assert key in rooms.weak_keys
    for key in normals[config.num_weak_encounters:]:
        assert key in rooms.normal_keys
    # Never the same encounter back-to-back. The no-shared-tag rule is
    # best-effort in the source too (AddWithoutRepeatingTags falls back
    # to any draw when the bag can't avoid a repeat), so tag repeats are
    # merely rare, not impossible.
    def shares(a, b):
        return bool(set(rooms.tags.get(a, ())) & set(rooms.tags.get(b, ())))

    tag_repeats = 0
    for prev, cur in zip(normals, normals[1:]):
        assert cur != prev
        tag_repeats += shares(prev, cur)
    assert tag_repeats <= 2
    assert len(room_set.elite_keys) == RoomSet.MAX_ELITES
    for prev, cur in zip(room_set.elite_keys, room_set.elite_keys[1:]):
        assert cur != prev
    assert room_set.boss_key in rooms.boss_keys
    # Every key resolves in the act's registry.
    registry = room_set.registry
    for key in normals + room_set.elite_keys + [room_set.boss_key]:
        assert key in registry


def test_room_set_consumes_in_order():
    rooms = act_rooms("overgrowth")
    room_set = RoomSet.generate(rooms, random.Random(0), 15, 3)
    first = room_set.next_normal_encounter
    room_set.mark_visited(RoomType.MONSTER)
    second = room_set.next_normal_encounter
    assert first.id == room_set.registry[room_set.normal_keys[0]].id
    assert second.id == room_set.registry[room_set.normal_keys[1]].id


def test_glory_rooms_not_available():
    with pytest.raises(KeyError):
        act_rooms("glory")


# ═════════════════════════════════════════════════════════════════════════
# RunState travel integration
# ═════════════════════════════════════════════════════════════════════════

def test_start_act_and_first_moves():
    run = RunState(rng=random.Random(4))
    act_map = run.start_act("overgrowth")
    assert run.current_point is act_map.starting_point
    options = run.travelable_points()
    assert options and all(p.row == 1 for p in options)
    resolution = run.enter_point(options[0])
    assert resolution.room_type == RoomType.MONSTER
    assert resolution.encounter is not None
    assert run.room_set.normal_visited == 1
    assert run.map_history[-1][1] == RoomType.MONSTER


def test_enter_point_rejects_unreachable():
    run = RunState(rng=random.Random(4))
    run.start_act("overgrowth")
    with pytest.raises(ValueError):
        run.enter_point(run.map.boss_point)


@pytest.mark.parametrize("seed", range(15))
def test_full_walk_to_boss(seed):
    """Walk a whole act: rooms resolve, encounters come in order, the boss
    ends the act."""
    run = RunState(rng=random.Random(seed))
    act_map = run.start_act("overgrowth")
    walk_rng = random.Random(seed + 1000)
    monster_count = 0
    while run.current_point is not act_map.boss_point:
        target = walk_rng.choice(run.travelable_points())
        resolution = run.enter_point(target)
        assert resolution.room_type != RoomType.UNASSIGNED
        if resolution.room_type in (RoomType.MONSTER, RoomType.ELITE, RoomType.BOSS):
            assert resolution.encounter is not None
        if resolution.room_type == RoomType.MONSTER:
            monster_count += 1
        if resolution.room_type == RoomType.EVENT and resolution.event is not None:
            assert resolution.event.id in run.visited_event_ids
        if resolution.room_type == RoomType.REST_SITE:
            healed = run.rest_heal()
            assert healed >= 0
    assert run.map_history[-1][1] == RoomType.BOSS
    # The walk visited one point per floor: 15 grid rows + the boss.
    assert len(run.map_history) == act_map.row_count
    # Monster rooms consumed the normal-encounter queue in order.
    assert run.room_set.normal_visited == monster_count


def test_first_monster_fight_is_weak():
    run = RunState(rng=random.Random(9))
    run.start_act("overgrowth")
    first = run.enter_point(run.travelable_points()[0])
    assert first.room_type == RoomType.MONSTER
    weak_ids = {
        act_rooms("overgrowth").encounters()[k].id
        for k in act_rooms("overgrowth").weak_keys
    }
    assert first.encounter.id in weak_ids


def test_treasure_grants_grab_bag_relic():
    run = RunState(rng=random.Random(2))
    act_map = run.start_act("overgrowth")
    # March straight up until the forced treasure row.
    walk_rng = random.Random(0)
    while run.current_point.row < act_map.row_count - 7 - 1:
        run.enter_point(walk_rng.choice(run.travelable_points()))
    relics_before = len(run.relics)
    resolution = run.enter_point(walk_rng.choice(run.travelable_points()))
    assert resolution.room_type == RoomType.TREASURE
    assert resolution.relic is not None
    assert len(run.relics) == relics_before + 1


def test_map_combat_round_trip():
    """A resolved monster encounter plugs straight into create_combat."""
    run = RunState(rng=random.Random(12))
    run.start_act("overgrowth")
    resolution = run.enter_point(run.travelable_points()[0])
    combat = run.create_combat(resolution.encounter)
    assert combat.enemies and all(e.hp > 0 for e in combat.enemies)


def test_start_act_glory_map_only():
    """Glory's map config exists but its rooms don't — start_act says so."""
    run = RunState(rng=random.Random(0))
    with pytest.raises(KeyError):
        run.start_act("glory")


# ═════════════════════════════════════════════════════════════════════════
# Ascension: SwarmingElites (Asc 1) and DoubleBoss (Asc 10)
# ═════════════════════════════════════════════════════════════════════════

def test_ascension_level_thresholds():
    # AscensionManager.HasLevel is `level >= threshold` (cumulative).
    assert AscensionLevel.SWARMING_ELITES == 1
    assert AscensionLevel.DOUBLE_BOSS == 10


@pytest.mark.parametrize("ascension", [1, 5, 9, 10])
@pytest.mark.parametrize("seed", range(15))
def test_swarming_elites_count(ascension, seed):
    """SwarmingElites (Asc 1+): round(5 * 1.6) = 8 elites instead of 5."""
    act_map = make_map(seed, ascension=ascension)
    assert act_map.counts.elites == 8
    placed = sum(
        1 for p in act_map.all_points() if p.point_type == MapPointType.ELITE
    )
    assert placed == 8


@pytest.mark.parametrize("seed", range(10))
def test_no_swarming_elites_below_asc_1(seed):
    act_map = make_map(seed, ascension=0)
    assert act_map.counts.elites == 5
    placed = sum(
        1 for p in act_map.all_points() if p.point_type == MapPointType.ELITE
    )
    assert placed == 5


def test_swarming_elites_still_prunes_clean():
    act_map = make_map(3, ascension=1)
    assert find_matching_segments(act_map.starting_point) == []


def test_explicit_counts_override_ignores_ascension():
    """An explicit counts override wins outright (the BigGameHunter path);
    ascension does not re-bump its elites."""
    from sts2_rl.actmap import MapPointTypeCounts

    override = MapPointTypeCounts(unknowns=12, rests=6, elites=3)
    act_map = make_map(0, ascension=10, counts=override)
    assert act_map.counts.elites == 3


@pytest.mark.parametrize("seed", range(15))
def test_double_boss_map_structure(seed):
    """DoubleBoss (Asc 10, final act): a second boss one row past the
    first, reachable only through it."""
    act_map = StandardMap(
        rng=random.Random(seed), config=OVERGROWTH_MAP, has_second_boss=True
    )
    second = act_map.second_boss_point
    assert second is not None
    assert second.point_type == MapPointType.BOSS
    assert second.row == act_map.boss_point.row + 1
    # The first boss is the only way in; the second boss ends the act.
    assert act_map.boss_point.children == {second}
    assert second.parents == {act_map.boss_point}
    assert second.children == set()
    # get_point resolves it.
    assert act_map.get_point(second.col, second.row) is second
    # Pruning still terminates at the first boss (paths never descend past
    # a BOSS node), so the map is clean.
    assert find_matching_segments(act_map.starting_point) == []


def test_no_second_boss_without_double_boss():
    act_map = make_map(0)
    assert act_map.second_boss_point is None


def test_start_act_double_boss_requires_final_act():
    # DoubleBoss only applies to the final act (RunManager adds the second
    # boss to the last act only).
    run = RunState(rng=random.Random(1))
    run.start_act("overgrowth", ascension=10, is_final_act=False)
    assert run.map.second_boss_point is None
    assert run.room_set.second_boss_key is None
    run.start_act("overgrowth", ascension=9, is_final_act=True)
    assert run.map.second_boss_point is None


def test_double_boss_room_set_draws_two_bosses():
    rooms = act_rooms("overgrowth")
    room_set = RoomSet.generate(
        rooms, random.Random(0), 15, 3, has_second_boss=True
    )
    assert room_set.second_boss_key is not None
    assert room_set.second_boss_key != room_set.boss_key
    # NextBossEncounter yields the first boss, then the second.
    assert room_set.next_boss_encounter.id == rooms.encounters()[room_set.boss_key].id
    room_set.mark_visited(RoomType.BOSS)
    assert (
        room_set.next_boss_encounter.id
        == rooms.encounters()[room_set.second_boss_key].id
    )


@pytest.mark.parametrize("seed", range(10))
def test_double_boss_full_walk(seed):
    """A full DoubleBoss walk fights two distinct bosses and ends on the
    second boss node."""
    run = RunState(rng=random.Random(seed))
    run.start_act("overgrowth", ascension=10, is_final_act=True)
    walk_rng = random.Random(seed + 500)
    bosses = []
    while not run.at_act_end:
        resolution = run.enter_point(walk_rng.choice(run.travelable_points()))
        if resolution.room_type == RoomType.BOSS:
            bosses.append(resolution.encounter.id)
    assert len(bosses) == 2
    assert bosses[0] != bosses[1]
    assert run.current_point is run.map.second_boss_point


def test_at_act_end_single_boss():
    run = RunState(rng=random.Random(3))
    run.start_act("overgrowth")
    walk_rng = random.Random(0)
    while not run.at_act_end:
        run.enter_point(walk_rng.choice(run.travelable_points()))
    assert run.current_point is run.map.boss_point
