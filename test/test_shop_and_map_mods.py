"""Tests for the merchant shop (sts2_rl/shop.py) and the map-generation
modification pipeline (Spoils Map card + Golden Compass relic).

Run with:  python -m pytest test/test_shop_and_map_mods.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.actmap import MapPointType, SpoilsActMap, StandardMap, find_matching_segments
from sts2_rl.cards import make_card
from sts2_rl.relics import ALL_RELICS, RelicRarity, make_relic
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState
from sts2_rl.shop import MerchantInventory


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# Spoils map (hourglass) generation
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("seed", range(20))
def test_spoils_map_is_hourglass(seed):
    """Every root→boss path funnels through the single centered treasure."""
    m = SpoilsActMap(rng=random.Random(seed))
    treasures = [p for p in m.all_points() if p.point_type == MapPointType.TREASURE]
    assert len(treasures) == 1
    treasure = treasures[0]
    # The treasure sits on the standard treasure row, centered.
    assert treasure.row == m.row_count - 7
    assert treasure.col == m.column_count // 2
    # Reachability + convergence: everything is on an ancient→boss route and
    # all top-row nodes feed the boss.
    from sts2_rl.actmap import _find_all_paths

    for path in _find_all_paths(m.starting_point):
        assert treasure in path
    for p in m.all_points():
        node = p
        while node.children:
            node = next(iter(node.children))
        assert node is m.boss_point


@pytest.mark.parametrize("seed", range(20))
def test_spoils_map_deterministic_and_clean(seed):
    a = SpoilsActMap(rng=random.Random(seed))
    b = SpoilsActMap(rng=random.Random(seed))
    layout_a = [(p.col, p.row, p.point_type) for p in a.all_points()]
    layout_b = [(p.col, p.row, p.point_type) for p in b.all_points()]
    assert layout_a == layout_b
    # Pruning leaves no duplicate segments, same invariant as StandardMap.
    assert find_matching_segments(a.starting_point) == []


def test_spoils_map_forced_rows_and_counts():
    m = SpoilsActMap(rng=random.Random(3))
    for p in m.points_in_row(1):
        assert p.point_type == MapPointType.MONSTER
    for p in m.points_in_row(m.row_count - 1):
        assert p.point_type == MapPointType.REST_SITE
    counts: dict = {}
    for p in m.all_points():
        counts[p.point_type] = counts.get(p.point_type, 0) + 1
    assert counts.get(MapPointType.SHOP, 0) == m.counts.shops
    assert counts.get(MapPointType.ELITE, 0) == m.counts.elites
    assert counts.get(MapPointType.UNASSIGNED, 0) == 0


# ═════════════════════════════════════════════════════════════════════════
# Spoils Map card — the run-layer effect
# ═════════════════════════════════════════════════════════════════════════

def test_spoils_map_card_replaces_act2_map():
    run = fresh_run(5)
    spoils = make_card("spoils_map")
    run.add_card(spoils)
    run.start_act("underdocks", act_index=1)
    assert isinstance(run.map, SpoilsActMap)
    # The card recorded the treasure and attached its quest there.
    assert spoils.spoils_coord is not None
    treasure = run.map.get_point(*spoils.spoils_coord)
    assert spoils in treasure.quests


def test_spoils_map_card_inert_on_other_acts():
    run = fresh_run(5)
    run.add_card(make_card("spoils_map"))
    run.start_act("overgrowth", act_index=0)
    assert isinstance(run.map, StandardMap)
    assert not isinstance(run.map, SpoilsActMap)


def test_spoils_map_card_inert_when_not_in_deck():
    run = fresh_run(5)
    spoils = make_card("spoils_map")  # never added to the deck
    # Manually run the pipeline as if the card were a listener: it must not act.
    run.start_act("underdocks", act_index=1)
    assert not isinstance(run.map, SpoilsActMap)
    assert spoils.modify_generated_map(run, run.map, 1) is run.map


def test_spoils_map_quest_pays_600_and_removes_card():
    run = fresh_run(5)
    spoils = make_card("spoils_map")
    run.add_card(spoils)
    run.start_act("underdocks", act_index=1)
    gold_before = run.gold
    # March to the treasure (all paths converge there).
    walk = random.Random(1)
    treasure_res = None
    while run.current_point.point_type != MapPointType.TREASURE and not run.at_act_end:
        res = run.enter_point(walk.choice(run.travelable_points()))
        if res.room_type == RoomType.TREASURE:
            treasure_res = res
    assert run.current_point.point_type == MapPointType.TREASURE
    assert treasure_res is not None
    # 600 quest payout on top of the chest's own 42–52 gold (rewards.py).
    chest_gold = treasure_res.gold - 600
    assert 42 <= chest_gold <= 52
    assert run.gold - gold_before == 600 + chest_gold
    assert spoils not in run.deck
    # The quest was cleared off the point.
    assert spoils not in run.current_point.quests


# ═════════════════════════════════════════════════════════════════════════
# Golden Compass relic
# ═════════════════════════════════════════════════════════════════════════

def test_golden_compass_metadata():
    assert ALL_RELICS["golden_compass"].rarity == RelicRarity.ANCIENT


def test_golden_compass_forces_golden_path():
    run = fresh_run(7)
    run.act_index = 0
    run.add_relic(make_relic("golden_compass"))
    run.start_act("overgrowth", act_index=0)
    # Golden path: one node per row.
    rows = [run.map.points_in_row(r) for r in range(1, run.map.row_count)]
    assert all(len(row) == 1 for row in rows)


def test_golden_compass_unknowns_resolve_to_event():
    run = fresh_run(7)
    run.act_index = 0
    run.add_relic(make_relic("golden_compass"))
    run.start_act("overgrowth", act_index=0)
    walk = random.Random(1)
    unknown_results = []
    while not run.at_act_end:
        res = run.enter_point(walk.choice(run.travelable_points()))
        if res.map_point_type == MapPointType.UNKNOWN:
            unknown_results.append(res.room_type)
    assert unknown_results  # the golden path has "?" nodes
    assert all(rt == RoomType.EVENT for rt in unknown_results)


def test_golden_compass_only_affects_its_act():
    run = fresh_run(7)
    run.act_index = 0
    compass = make_relic("golden_compass")
    run.add_relic(compass)
    # A different act index: the compass leaves the map alone.
    assert compass.golden_path_act == 0
    run.start_act("underdocks", act_index=1)
    assert isinstance(run.map, StandardMap)
    rows = [run.map.points_in_row(r) for r in range(1, run.map.row_count)]
    assert any(len(row) > 1 for row in rows)  # not a single-column golden path


def test_golden_compass_mid_act_regenerates():
    run = fresh_run(7)
    run.start_act("overgrowth", act_index=0)
    run.enter_point(run.travelable_points()[0])  # advance one room
    run.add_relic(make_relic("golden_compass"))
    # Regenerated to the golden path and returned to the Ancient.
    assert run.current_point is run.map.starting_point
    rows = [run.map.points_in_row(r) for r in range(1, run.map.row_count)]
    assert all(len(row) == 1 for row in rows)
    assert run.map_history == []


def test_after_obtained_before_act_is_safe():
    """Obtaining the compass with no act in progress must not crash."""
    run = fresh_run(7)
    run.add_relic(make_relic("golden_compass"))  # regenerate_map is a no-op
    assert run.map is None


# ═════════════════════════════════════════════════════════════════════════
# Merchant shop
# ═════════════════════════════════════════════════════════════════════════

def make_shop(seed: int = 1) -> tuple[RunState, MerchantInventory]:
    run = fresh_run(seed)
    run.start_act("overgrowth")
    run.gold = 10_000
    return run, MerchantInventory.create(run)


def test_shop_stock_shape():
    _, inv = make_shop()
    assert len(inv.character_card_entries) == 5
    assert len(inv.colorless_card_entries) == 2
    assert len(inv.card_entries) == 7
    assert len(inv.relic_entries) == 3
    assert len(inv.potion_entries) == 3
    assert inv.card_removal_entry is not None
    # Exactly one card is On Sale (half price) — always a character slot.
    assert sum(e.on_sale for e in inv.character_card_entries) == 1
    assert not any(e.on_sale for e in inv.colorless_card_entries)
    assert all(e.is_stocked for e in inv.card_entries)


def test_toxic_egg_upgrades_the_merchants_skill_cards():
    # MerchantCardEntry.cs:92 runs Hook.ModifyMerchantCardCreationResults on
    # every stocked card, so an egg relic upgrades its type in the shop too —
    # the recording buys "Shrug It Off+" off a shelf the sim stocked plain.
    from sts2_rl.cards import CardType

    run = fresh_run(1)
    run.start_act("overgrowth")
    run.add_relic("toxic_egg")
    inv = MerchantInventory.create(run)
    skills = [e.card for e in inv.card_entries
              if e.card is not None and e.card.card_type == CardType.SKILL]
    assert skills, "shop always stocks skill slots"
    assert all(c.upgrade_level == 1 for c in skills)
    others = [e.card for e in inv.card_entries
              if e.card is not None and e.card.card_type != CardType.SKILL]
    assert all(c.upgrade_level == 0 for c in others)


def test_shop_card_types_match_slots():
    from sts2_rl.cards import CardType

    _, inv = make_shop()
    expected = [CardType.ATTACK, CardType.ATTACK, CardType.SKILL, CardType.SKILL, CardType.POWER]
    assert [e.card.card_type for e in inv.character_card_entries] == expected


def test_shop_on_sale_is_half_price():
    _, inv = make_shop(2)
    sale = next(e for e in inv.card_entries if e.on_sale)
    from sts2_rl.cards import CardRarity

    base = {CardRarity.RARE: 150, CardRarity.UNCOMMON: 75}.get(sale.card.rarity, 50)
    # Half of the (jittered) full price: within the ±5% jitter band, halved.
    assert base * 0.95 / 2 - 1 <= sale.cost <= base * 1.05 / 2 + 1


def test_shop_buy_card_costs_gold_and_adds_to_deck():
    run, inv = make_shop()
    entry = inv.card_entries[0]
    card, cost = entry.card, entry.cost
    deck_before, gold_before = len(run.deck), run.gold
    assert entry.purchase() is True
    assert len(run.deck) == deck_before + 1
    assert run.gold == gold_before - cost
    assert card in run.deck
    assert not entry.is_stocked
    assert entry.purchase() is False  # already sold


def test_shop_cannot_buy_without_gold():
    run, inv = make_shop()
    run.gold = 0
    entry = inv.card_entries[0]
    assert entry.purchase() is False
    assert not (entry.card is None)  # still stocked


def test_shop_relics_are_shop_legal_and_distinct():
    _, inv = make_shop(4)
    relics = [e.relic for e in inv.relic_entries if e.relic is not None]
    assert all(r.is_allowed_in_shops for r in relics)
    assert len({r.id for r in relics}) == len(relics)  # no duplicate stock
    # The third slot is a Shop-rarity relic.
    assert inv.relic_entries[2].relic.rarity == RelicRarity.SHOP


def test_shop_buy_relic():
    run, inv = make_shop(4)
    entry = inv.relic_entries[0]
    relic, cost = entry.relic, entry.cost
    gold_before = run.gold
    assert entry.purchase() is True
    assert relic in run.relics
    assert run.gold == gold_before - cost


def test_shop_potion_purchase_respects_belt():
    run, inv = make_shop()
    run.potions = []
    bought = 0
    for entry in inv.potion_entries:
        if entry.purchase():
            bought += 1
    # The belt holds 3 potions; all three purchases should fit.
    assert bought == 3
    assert len(run.potions) == 3


def test_shop_card_removal_price_climbs():
    run, inv = make_shop()
    assert inv.card_removal_entry.cost == 75
    deck_before = len(run.deck)
    assert inv.card_removal_entry.purchase() is True
    assert len(run.deck) == deck_before - 1
    assert run.card_shop_removals_used == 1
    assert not inv.card_removal_entry.is_stocked
    # A fresh shop this run charges more.
    inv2 = MerchantInventory.create(run)
    assert inv2.card_removal_entry.cost == 100


def test_shop_purchases_are_deterministic_per_seed():
    _, a = make_shop(9)
    _, b = make_shop(9)
    assert [e.card.id for e in a.card_entries] == [e.card.id for e in b.card_entries]
    assert [e.cost for e in a.card_entries] == [e.cost for e in b.card_entries]


def test_shop_room_resolves_via_enter_point():
    """Entering a Shop room yields a stocked MerchantInventory on resolution."""
    # Walk several acts/seeds until a Shop room is entered (shops are common
    # enough that a few walks always hit one), then assert the wiring.
    for seed in range(30):
        run = fresh_run(seed)
        run.start_act("overgrowth")
        run.gold = 500
        walk = random.Random(seed + 100)
        while not run.at_act_end:
            res = run.enter_point(walk.choice(run.travelable_points()))
            if res.room_type == RoomType.SHOP:
                assert isinstance(res.shop, MerchantInventory)
                assert res.shop.all_entries
                return
    pytest.fail("no shop room encountered in 30 walks")


def test_spoils_map_card_uses_the_dedicated_spoils_map_stream():
    """SpoilsActMap's ctor seeds its own transient stream —
    `_rng = new Rng(runState.Rng.Seed, "spoils_map")` (SpoilsActMap.cs:92) —
    exactly like StandardActMap.CreateFor's `act_{N}_map`. Building it off the
    shared run RNG instead makes a parity run's act-2 map (and every later
    room, reward and fight) nondeterministic, since that RNG is unseeded in the
    conformance harness."""
    def act2_layout() -> list:
        run = RunState(string_seed="933T39V18D")
        run.start_run(acts=["overgrowth", "hive", "glory"], ascension=0)
        run.add_card(make_card("spoils_map"))
        run.advance_act()
        assert isinstance(run.map, SpoilsActMap)
        return [(p.col, p.row, p.point_type) for p in run.map.all_points()]

    assert act2_layout() == act2_layout()
