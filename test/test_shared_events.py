"""The shared (cross-act) event pool vs the source: ModelDb.AllSharedEvents
(src/Core/Models/ModelDb.cs:135) — 18 events appended to EVERY act's event
queue by ActModel.GenerateRooms. One section per event; sections are added
per wave as the port lands (plan: docs/superpowers/plans/
2026-07-19-shared-events.md)."""
import random

from sts2_rl.cards import make_card
from sts2_rl.events import make_event
from sts2_rl.run import RunState


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


def hive_run(seed=0, **kwargs):
    """A run standing in act 2 (Hive) — the common shared-event act gate."""
    run = fresh_run(seed, **kwargs)
    run.start_run(acts=["overgrowth", "hive"])
    run.advance_act()
    return run


# ═════════════════════════════════════════════════════════════════════════
# Queue wiring: ActModel.GenerateRooms concats AllSharedEvents into EVERY
# act's event queue (ModelDb.cs:135, ActModel.cs:334)
# ═════════════════════════════════════════════════════════════════════════

def test_shared_pool_rides_every_act_queue():
    from sts2_rl.events import (
        GLORY_EVENTS, HIVE_EVENTS, OVERGROWTH_EVENTS, SHARED_EVENTS,
        UNDERDOCKS_EVENTS,
    )
    from sts2_rl.rooms import RoomSet, act_rooms

    for act, own in (
        ("overgrowth", OVERGROWTH_EVENTS), ("underdocks", UNDERDOCKS_EVENTS),
        ("hive", HIVE_EVENTS), ("glory", GLORY_EVENTS),
    ):
        room_set = RoomSet.generate(
            act_rooms(act), random.Random(0), num_rooms=15, num_weak=3)
        assert set(SHARED_EVENTS) <= set(room_set.event_ids)
        assert set(own) <= set(room_set.event_ids)
        # Concat, not replace: every id appears exactly once.
        assert len(room_set.event_ids) == len(own) + len(SHARED_EVENTS)


def test_shared_events_are_all_registered():
    from sts2_rl.events import ALL_EVENTS, SHARED_EVENTS

    assert set(SHARED_EVENTS) <= set(ALL_EVENTS)
    assert len(set(SHARED_EVENTS)) == len(SHARED_EVENTS)


def test_stocked_act2_run_makes_the_shared_pool_eligible():
    """End-to-end gate check: in a real act-2 position with gold, potions and
    tradable relics, every shared event is eligible except the act-1-only
    one — i.e. the pool really is live in a run, not just in the queue."""
    from sts2_rl.events import ALL_EVENTS, SHARED_EVENTS
    from sts2_rl.potions import make_potion
    from sts2_rl.relics import make_relic

    run = fresh_run(100)
    run.start_run(acts=["overgrowth", "hive"])
    run.advance_act()
    run.gold = 500
    run.total_floor = 20
    run.add_potion(make_potion("fire_potion"))
    run.add_potion(make_potion("block_potion"))
    for rid in ("anchor", "akabeko", "bag_of_marbles", "blood_vial", "kunai"):
        run.add_relic(make_relic(rid))

    eligible = {e for e in SHARED_EVENTS if ALL_EVENTS[e].is_allowed(run)}
    assert eligible == set(SHARED_EVENTS) - {"the_legends_were_true"}


def test_act_gated_shared_event_is_skipped_in_act1():
    """ensure_next_event_is_valid is what keeps an act-2-only shared event
    (Doll Room) out of an Act-1 queue."""
    from sts2_rl.rooms import RoomSet, act_rooms

    run = fresh_run(99)
    run.start_run(acts=["overgrowth"])
    room_set = RoomSet.generate(
        act_rooms("overgrowth"), random.Random(3), num_rooms=15, num_weak=3)
    # Force the queue head onto the act-2-only Doll Room.
    room_set.event_ids = ["doll_room"] + [
        e for e in room_set.event_ids if e != "doll_room"]
    room_set.events_visited = 0
    room_set.ensure_next_event_is_valid(run)
    assert room_set.next_event_id != "doll_room"


# ═════════════════════════════════════════════════════════════════════════
# This or That (ThisOrThat.cs)
# ═════════════════════════════════════════════════════════════════════════

def test_this_or_that_plain_trades_hp_for_gold():
    run = fresh_run(1)
    run.start_run(acts=["overgrowth"])
    hp0, gold0 = run.hp, run.gold
    event = make_event("this_or_that", run).begin()
    assert event.option_keys() == ["PLAIN", "ORNATE"]
    assert event.choose("PLAIN")
    assert run.hp == hp0 - 6
    # CalculateVars: gold = NextInt(41, 69) -> 41..68.
    assert 41 <= run.gold - gold0 <= 68
    assert event.finished


def test_this_or_that_ornate_gives_relic_and_clumsy():
    run = fresh_run(2)
    run.start_run(acts=["overgrowth"])
    deck0 = len(run.deck)
    event = make_event("this_or_that", run).begin()
    assert event.choose("ORNATE")
    assert len(run.relics) == 1
    assert [c for c in run.deck if c.id == "clumsy"]
    assert len(run.deck) == deck0 + 1


def test_this_or_that_gold_roll_is_seeded():
    gold = []
    for _ in range(2):
        run = fresh_run(7)
        run.start_run(acts=["overgrowth"])
        g0 = run.gold
        make_event("this_or_that", run).begin().choose("PLAIN")
        gold.append(run.gold - g0)
    assert gold[0] == gold[1]


# ═════════════════════════════════════════════════════════════════════════
# The Legends Were True (TheLegendsWereTrue.cs)
# ═════════════════════════════════════════════════════════════════════════

def test_legends_is_act1_only_and_needs_10_hp():
    run = fresh_run(1)
    run.start_run(acts=["overgrowth", "hive"])
    from sts2_rl.events import ALL_EVENTS

    assert ALL_EVENTS["the_legends_were_true"].is_allowed(run)
    run.hp = 9
    assert not ALL_EVENTS["the_legends_were_true"].is_allowed(run)
    run.hp = 50
    run.advance_act()
    assert not ALL_EVENTS["the_legends_were_true"].is_allowed(run)


def test_legends_nab_the_map_adds_spoils_map():
    run = fresh_run(1)
    run.start_run(acts=["overgrowth"])
    event = make_event("the_legends_were_true", run).begin()
    assert event.choose("NAB_THE_MAP")
    assert [c for c in run.deck if c.id == "spoils_map"]
    assert event.finished


def test_legends_exit_costs_8_hp_and_offers_a_potion():
    run = fresh_run(3)
    run.start_run(acts=["overgrowth"])
    hp0 = run.hp
    event = make_event("the_legends_were_true", run).begin()
    assert event.choose("SLOWLY_FIND_AN_EXIT")
    assert run.hp == hp0 - 8
    # Potion offers auto-keep when a slot is free (sim convention).
    assert len(run.potions) == 1


# ═════════════════════════════════════════════════════════════════════════
# Slippery Bridge (SlipperyBridge.cs)
# ═════════════════════════════════════════════════════════════════════════

def slippery_run(seed=4):
    run = fresh_run(seed)
    run.start_run(acts=["overgrowth"])
    run.total_floor = 7          # IsAllowed: TotalFloor > 6
    return run


def test_slippery_bridge_gate():
    from sts2_rl.events import ALL_EVENTS

    run = slippery_run()
    assert ALL_EVENTS["slippery_bridge"].is_allowed(run)
    run.total_floor = 6
    assert not ALL_EVENTS["slippery_bridge"].is_allowed(run)


def test_slippery_bridge_overcome_removes_the_shown_card():
    run = slippery_run()
    deck0 = len(run.deck)
    event = make_event("slippery_bridge", run).begin()
    shown = event.shown_card
    # The all-Basic starter deck empties the non-Basic first roll, so the
    # fallback (any removable card) applies — shown is a real deck card.
    assert shown in run.deck
    assert event.option_keys() == ["OVERCOME", "HOLD_ON_0"]
    assert event.choose("OVERCOME")
    assert len(run.deck) == deck0 - 1
    assert shown not in run.deck
    assert event.finished


def test_brain_leech_gate_is_acts_1_and_2():
    from sts2_rl.events import ALL_EVENTS

    run = fresh_run(1)
    run.start_run(acts=["overgrowth", "hive", "glory"])
    assert ALL_EVENTS["brain_leech"].is_allowed(run)
    run.advance_act()
    assert ALL_EVENTS["brain_leech"].is_allowed(run)
    run.advance_act()
    assert not ALL_EVENTS["brain_leech"].is_allowed(run)


def test_brain_leech_share_knowledge_adds_one_of_five():
    run = fresh_run(2)
    run.start_run(acts=["overgrowth"])
    deck0 = len(run.deck)
    event = make_event("brain_leech", run).begin()
    assert event.choose("SHARE_KNOWLEDGE")
    assert len(run.deck) == deck0 + 1
    assert run.hp == run.max_hp          # no damage on this path
    assert event.finished


def test_brain_leech_rip_costs_5_and_offers_colorless():
    from sts2_rl.cards.pool import COLORLESS_POOL

    run = fresh_run(3)
    run.start_run(acts=["overgrowth"])
    hp0, deck0 = run.hp, len(run.deck)
    event = make_event("brain_leech", run).begin()
    assert event.choose("RIP")
    assert run.hp == hp0 - 5
    assert len(run.deck) == deck0 + 1
    new = [c for c in run.deck if c.id in COLORLESS_POOL]
    assert len(new) == 1


def test_future_of_potions_gate_needs_two_potions():
    from sts2_rl.events import ALL_EVENTS
    from sts2_rl.potions import make_potion

    run = fresh_run(1)
    run.start_run(acts=["overgrowth"])
    assert not ALL_EVENTS["the_future_of_potions"].is_allowed(run)
    run.add_potion(make_potion("fire_potion"))
    run.add_potion(make_potion("block_potion"))
    assert ALL_EVENTS["the_future_of_potions"].is_allowed(run)


def test_future_of_potions_trades_potion_for_upgraded_card():
    from sts2_rl.potions import make_potion

    run = fresh_run(4)
    run.start_run(acts=["overgrowth"])
    run.add_potion(make_potion("fire_potion"))
    run.add_potion(make_potion("block_potion"))
    deck0 = len(run.deck)
    event = make_event("the_future_of_potions", run).begin()
    # One option per held potion (max 3), keyed POTION_0..n.
    assert event.option_keys() == ["POTION_0", "POTION_1"]
    assert event.choose("POTION_0")
    assert len(run.potions) == 1         # the traded potion is gone
    added = [c for c in run.deck if c.rarity.name == "COMMON"
             and c.upgrade_level > 0]
    assert len(run.deck) == deck0 + 1
    assert added                          # fire potion (common) -> common card
    assert event.finished


def test_room_full_of_cheese_gorge_picks_two_commons():
    run = fresh_run(5)
    run.start_run(acts=["overgrowth"])
    deck0 = len(run.deck)
    event = make_event("room_full_of_cheese", run).begin()
    assert event.choose("GORGE")
    assert len(run.deck) == deck0 + 2
    assert event.finished


def test_room_full_of_cheese_search_grants_chosen_cheese():
    run = fresh_run(6)
    run.start_run(acts=["overgrowth"])
    hp0 = run.hp
    event = make_event("room_full_of_cheese", run).begin()
    assert event.choose("SEARCH")
    assert run.hp == hp0 - 14
    assert [r for r in run.relics if r.id == "chosen_cheese"]


def test_chosen_cheese_gains_max_hp_after_combat():
    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.monsters.overgrowth import ENCOUNTERS
    from sts2_rl.relics import make_relic

    run = fresh_run(7)
    run.start_run(acts=["overgrowth"])
    run.add_relic(make_relic("chosen_cheese"))
    max0 = run.max_hp
    combat = run.create_combat(ENCOUNTERS["fuzzy_wurm_weak"])
    for enemy in list(combat.enemies):
        CreatureCmd.kill(combat.hooks, enemy)
    combat._end_combat(player_won=True)    # fires on_combat_end hooks
    run.finish_combat(combat)
    assert run.max_hp == max0 + 1


def test_ranwid_gate_and_trades():
    from sts2_rl.events import ALL_EVENTS
    from sts2_rl.potions import make_potion
    from sts2_rl.relics import make_relic

    run = hive_run(8)
    assert not ALL_EVENTS["ranwid_the_elder"].is_allowed(run)   # no relic/potion
    run.add_relic(make_relic("anchor"))                          # tradable Common
    run.add_potion(make_potion("fire_potion"))
    run.gain_gold(100)
    assert ALL_EVENTS["ranwid_the_elder"].is_allowed(run)

    relics0 = len(run.relics)
    event = make_event("ranwid_the_elder", run).begin()
    assert event.option_keys() == ["POTION", "GOLD", "RELIC"]
    gold0 = run.gold
    assert event.choose("GOLD")
    assert run.gold == gold0 - 100
    assert len(run.relics) == relics0 + 1


def test_ranwid_relic_trade_gives_two():
    from sts2_rl.potions import make_potion
    from sts2_rl.relics import make_relic

    run = hive_run(9)
    run.add_relic(make_relic("anchor"))
    run.add_potion(make_potion("fire_potion"))
    run.gain_gold(100)
    event = make_event("ranwid_the_elder", run).begin()
    assert event.choose("RELIC")
    # anchor traded away, two grab-bag relics in.
    assert not [r for r in run.relics if r.id == "anchor"]
    assert len(run.relics) == 2


def test_ranwid_starter_and_event_relics_not_tradable():
    from sts2_rl.relics import make_relic

    assert not make_relic("burning_blood").is_tradable      # Starter
    assert not make_relic("chosen_cheese").is_tradable      # Event
    assert not make_relic("strawberry").is_tradable         # pickup effect
    assert make_relic("anchor").is_tradable


def test_relic_trader_swaps_one_of_three():
    from sts2_rl.events import ALL_EVENTS
    from sts2_rl.relics import make_relic

    run = hive_run(10)
    for rid in ("anchor", "akabeko", "bag_of_marbles", "blood_vial", "kunai"):
        run.add_relic(make_relic(rid))
    assert ALL_EVENTS["relic_trader"].is_allowed(run)
    event = make_event("relic_trader", run).begin()
    assert event.option_keys() == ["TOP", "MIDDLE", "BOTTOM"]
    shown = list(event._owned)
    incoming = list(event._new)
    assert event.choose("MIDDLE")
    assert shown[1] not in run.relics
    assert incoming[1] in run.relics
    assert len(run.relics) == 5          # 5 - 1 + 1
    assert event.finished


def test_relic_trader_needs_five_tradables():
    from sts2_rl.events import ALL_EVENTS
    from sts2_rl.relics import make_relic

    run = hive_run(11)
    for rid in ("anchor", "akabeko", "bag_of_marbles", "blood_vial"):
        run.add_relic(make_relic(rid))
    assert not ALL_EVENTS["relic_trader"].is_allowed(run)


# ═════════════════════════════════════════════════════════════════════════
# Wave 2: the enchantment events
# ═════════════════════════════════════════════════════════════════════════

def test_self_help_book_offers_all_three_on_a_starter_deck():
    run = fresh_run(12)
    run.start_run(acts=["overgrowth"])
    run.add_card(make_card("inflame"))         # a Power, for READ_ENTIRE_BOOK
    event = make_event("self_help_book", run).begin()
    assert event.option_keys() == [
        "READ_THE_BACK", "READ_PASSAGE", "READ_ENTIRE_BOOK"]
    assert event.choose("READ_THE_BACK")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "sharp"
    assert enchanted[0].enchantment.amount == 2
    assert enchanted[0].card_type.name == "ATTACK"


def test_self_help_book_locks_power_option_without_powers():
    run = fresh_run(13)
    run.start_run(acts=["overgrowth"])
    # Starter deck has Attacks and Skills but no Power.
    event = make_event("self_help_book", run).begin()
    assert event.option_keys() == [
        "READ_THE_BACK", "READ_PASSAGE", "READ_ENTIRE_BOOK_LOCKED"]
    assert not event.choose("READ_ENTIRE_BOOK_LOCKED")


def test_self_help_book_nimble_targets_a_block_skill():
    run = fresh_run(14)
    run.start_run(acts=["overgrowth"])
    event = make_event("self_help_book", run).begin()
    assert event.choose("READ_PASSAGE")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "nimble"
    assert enchanted[0].gains_block       # Nimble requires GainsBlock


def test_stone_of_all_time_gate_is_act2_with_a_potion():
    from sts2_rl.events import ALL_EVENTS
    from sts2_rl.potions import make_potion

    run = hive_run(15)
    assert not ALL_EVENTS["stone_of_all_time"].is_allowed(run)   # no potion
    run.add_potion(make_potion("fire_potion"))
    assert ALL_EVENTS["stone_of_all_time"].is_allowed(run)

    act1 = fresh_run(15)
    act1.start_run(acts=["overgrowth"])
    act1.add_potion(make_potion("fire_potion"))
    assert not ALL_EVENTS["stone_of_all_time"].is_allowed(act1)


def test_stone_of_all_time_lift_trades_potion_for_max_hp():
    from sts2_rl.potions import make_potion

    run = hive_run(16)
    run.add_potion(make_potion("fire_potion"))
    max0, hp0 = run.max_hp, run.hp
    event = make_event("stone_of_all_time", run).begin()
    assert event.option_keys() == ["LIFT", "PUSH"]
    assert event.choose("LIFT")
    assert len(run.potions) == 0
    assert run.max_hp == max0 + 10
    assert run.hp == hp0 + 10          # GainMaxHp heals the same amount
    assert event.finished


def test_stone_of_all_time_push_enchants_vigorous_8():
    from sts2_rl.potions import make_potion

    run = hive_run(17)
    run.add_potion(make_potion("fire_potion"))
    hp0 = run.hp
    event = make_event("stone_of_all_time", run).begin()
    assert event.choose("PUSH")
    assert run.hp == hp0 - 6
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "vigorous"
    assert enchanted[0].enchantment.amount == 8


def test_symbiote_gate_and_approach_corrupts_an_attack():
    from sts2_rl.events import ALL_EVENTS

    act1 = fresh_run(18)
    act1.start_run(acts=["overgrowth"])
    assert not ALL_EVENTS["symbiote"].is_allowed(act1)

    run = hive_run(18)
    assert ALL_EVENTS["symbiote"].is_allowed(run)
    event = make_event("symbiote", run).begin()
    assert event.option_keys() == ["APPROACH", "KILL_WITH_FIRE"]
    assert event.choose("APPROACH")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "corrupted"
    assert enchanted[0].card_type.name == "ATTACK"


def test_symbiote_kill_with_fire_transforms_one_card():
    run = hive_run(19)
    before = sorted(c.id for c in run.deck)
    event = make_event("symbiote", run).begin()
    assert event.choose("KILL_WITH_FIRE")
    after = sorted(c.id for c in run.deck)
    assert len(after) == len(before)
    assert after != before             # exactly one card became something else
    assert event.finished


# ═════════════════════════════════════════════════════════════════════════
# Wave 3: Foul Potion / Potion Courier / Tea Master
# ═════════════════════════════════════════════════════════════════════════

def test_foul_potion_damages_everyone_including_you():
    import random as _random

    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.overgrowth import ENCOUNTERS
    from sts2_rl.potions import make_potion

    combat = CombatState(
        rng=_random.Random(0), encounter=ENCOUNTERS["fuzzy_wurm_weak"],
        potions=[make_potion("foul_potion")],
    )
    enemy = combat.enemy
    enemy_hp, player_hp = enemy.hp, combat.player.hp
    combat.use_potion(0)
    # CombatState.Creatures is every creature on every side.
    assert enemy_hp - enemy.hp == 12
    assert player_hp - combat.player.hp == 12


def test_foul_potion_is_not_a_random_reward():
    from sts2_rl.potions import ALL_POTIONS

    assert ALL_POTIONS["foul_potion"].rarity == "event"
    assert not ALL_POTIONS["foul_potion"].in_reward_pool


def test_potion_courier_gate_and_grab():
    from sts2_rl.events import ALL_EVENTS

    act1 = fresh_run(20)
    act1.start_run(acts=["overgrowth"])
    assert not ALL_EVENTS["potion_courier"].is_allowed(act1)

    run = hive_run(20)
    assert ALL_EVENTS["potion_courier"].is_allowed(run)
    event = make_event("potion_courier", run).begin()
    assert event.option_keys() == ["GRAB_POTIONS", "RANSACK"]
    assert event.choose("GRAB_POTIONS")
    # 3 offered, but the belt only holds MAX_POTIONS.
    assert [p.id for p in run.potions] == ["foul_potion"] * len(run.potions)
    assert len(run.potions) == 3


def test_potion_courier_ransack_finds_no_uncommon_yet():
    # Faithful port of a filter that matches nothing until Uncommon potions
    # are ported (the source's NextItem over an empty sequence -> null).
    run = hive_run(21)
    event = make_event("potion_courier", run).begin()
    assert event.choose("RANSACK")
    assert len(run.potions) == 0
    assert event.finished


def test_tea_master_gate_needs_150_gold_in_acts_1_2():
    from sts2_rl.events import ALL_EVENTS

    run = fresh_run(22)
    run.start_run(acts=["overgrowth", "hive", "glory"])
    run.gold = 149
    assert not ALL_EVENTS["tea_master"].is_allowed(run)
    run.gold = 150
    assert ALL_EVENTS["tea_master"].is_allowed(run)
    run.advance_act()
    assert ALL_EVENTS["tea_master"].is_allowed(run)
    run.advance_act()
    assert not ALL_EVENTS["tea_master"].is_allowed(run)   # act 3


def test_tea_master_purchases():
    run = fresh_run(23)
    run.start_run(acts=["overgrowth"])
    run.gold = 200
    event = make_event("tea_master", run).begin()
    assert event.option_keys() == [
        "BONE_TEA", "EMBER_TEA", "TEA_OF_DISCOURTESY"]
    assert event.choose("EMBER_TEA")
    assert run.gold == 50
    assert [r.id for r in run.relics] == ["ember_tea"]


def test_tea_master_free_option():
    run = fresh_run(24)
    run.start_run(acts=["overgrowth"])
    run.gold = 150
    event = make_event("tea_master", run).begin()
    assert event.choose("TEA_OF_DISCOURTESY")
    assert run.gold == 150
    assert [r.id for r in run.relics] == ["tea_of_discourtesy"]


def test_bone_tea_upgrades_opening_hand_once():
    import random as _random

    from sts2_rl.cards import make_card
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.overgrowth import ENCOUNTERS
    from sts2_rl.relics import make_relic

    tea = make_relic("bone_tea")
    deck = [make_card("strike") for _ in range(5)]
    combat = CombatState(
        starting_deck=deck, rng=_random.Random(0),
        encounter=ENCOUNTERS["fuzzy_wurm_weak"], relics=[tea],
    )
    assert all(c.upgrade_level == 1 for c in combat.player.hand)
    assert tea.is_used_up


def test_ember_tea_grants_strength_for_five_combats():
    import random as _random

    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.overgrowth import ENCOUNTERS
    from sts2_rl.relics import make_relic

    tea = make_relic("ember_tea")
    for expected_left in (4, 3, 2, 1, 0):
        combat = CombatState(
            rng=_random.Random(0), encounter=ENCOUNTERS["fuzzy_wurm_weak"],
            relics=[tea],
        )
        assert combat.player.strength == 2
        assert tea.combats_left == expected_left
    assert tea.is_used_up
    # Sixth combat: spent, no Strength.
    combat = CombatState(
        rng=_random.Random(0), encounter=ENCOUNTERS["fuzzy_wurm_weak"],
        relics=[tea],
    )
    assert combat.player.strength == 0


def test_tea_of_discourtesy_shuffles_two_dazed():
    import random as _random

    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.overgrowth import ENCOUNTERS
    from sts2_rl.relics import make_relic

    tea = make_relic("tea_of_discourtesy")
    combat = CombatState(
        rng=_random.Random(0), encounter=ENCOUNTERS["fuzzy_wurm_weak"],
        relics=[tea],
    )
    everywhere = combat.player.hand + combat.player.draw_pile
    assert sum(1 for c in everywhere if c.id == "dazed") == 2
    assert tea.is_used_up


# ═════════════════════════════════════════════════════════════════════════
# Wave 3c/3d: Doll Room and Welcome to Wongo's
# ═════════════════════════════════════════════════════════════════════════

DOLLS = {"daughter_of_the_wind", "mr_struggles", "bing_bong"}


def test_doll_room_is_act2_only():
    from sts2_rl.events import ALL_EVENTS

    act1 = fresh_run(25)
    act1.start_run(acts=["overgrowth"])
    assert not ALL_EVENTS["doll_room"].is_allowed(act1)
    assert ALL_EVENTS["doll_room"].is_allowed(hive_run(25))


def test_doll_room_random_is_free():
    run = hive_run(26)
    hp0 = run.hp
    event = make_event("doll_room", run).begin()
    assert event.option_keys() == ["RANDOM", "TAKE_SOME_TIME", "EXAMINE"]
    assert event.choose("RANDOM")
    assert run.hp == hp0
    assert len(run.relics) == 1 and run.relics[0].id in DOLLS
    assert event.finished


def test_doll_room_take_some_time_offers_two():
    run = hive_run(27)
    hp0 = run.hp
    event = make_event("doll_room", run).begin()
    assert event.choose("TAKE_SOME_TIME")
    assert run.hp == hp0 - 5
    assert not event.finished
    assert len(event.option_keys()) == 2
    assert set(event.option_keys()) <= DOLLS
    assert event.choose(event.option_keys()[0])
    assert run.relics[0].id in DOLLS
    assert event.finished


def test_doll_room_examine_offers_all_three():
    run = hive_run(28)
    hp0 = run.hp
    event = make_event("doll_room", run).begin()
    assert event.choose("EXAMINE")
    assert run.hp == hp0 - 15
    assert set(event.option_keys()) == DOLLS


def test_daughter_of_the_wind_blocks_on_attacks():
    import random as _random

    from sts2_rl.cards import make_card
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.overgrowth import ENCOUNTERS
    from sts2_rl.relics import make_relic

    deck = [make_card("strike"), make_card("defend")] + [
        make_card("strike") for _ in range(3)]
    combat = CombatState(
        starting_deck=deck, rng=_random.Random(0),
        encounter=ENCOUNTERS["fuzzy_wurm_weak"],
        relics=[make_relic("daughter_of_the_wind")],
    )
    strike = next(c for c in combat.player.hand if c.id == "strike")
    combat.play_card(combat.player.hand.index(strike))
    assert combat.player.block == 1
    defend = next(c for c in combat.player.hand if c.id == "defend")
    combat.play_card(combat.player.hand.index(defend))
    assert combat.player.block == 6      # 1 + 5, no second doll trigger


def test_mr_struggles_scales_with_turn_number():
    import random as _random

    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.overgrowth import ENCOUNTERS
    from sts2_rl.relics import make_relic

    combat = CombatState(
        rng=_random.Random(0), encounter=ENCOUNTERS["fuzzy_wurm_weak"],
        relics=[make_relic("mr_struggles")],
    )
    enemy = combat.enemy
    enemy.hp = 500          # survive long enough to watch the ramp
    assert combat.turn == 1
    for expected in (2, 3, 4):
        before = enemy.hp
        combat.end_turn()   # ... into turn `expected`
        assert combat.turn == expected
        assert before - enemy.hp == expected


def test_bing_bong_duplicates_added_cards_once():
    from sts2_rl.relics import make_relic

    run = hive_run(29)
    run.add_relic(make_relic("bing_bong"))
    deck0 = len(run.deck)
    run.add_card(make_card("inflame"))
    # The card plus exactly one clone — the clone must not clone itself.
    assert len(run.deck) == deck0 + 2
    assert sum(1 for c in run.deck if c.id == "inflame") == 2


def test_wongos_gate_and_purchases():
    from sts2_rl.events import ALL_EVENTS

    act1 = fresh_run(30)
    act1.start_run(acts=["overgrowth"])
    act1.gold = 500
    assert not ALL_EVENTS["welcome_to_wongos"].is_allowed(act1)

    run = hive_run(30)
    run.gold = 99
    assert not ALL_EVENTS["welcome_to_wongos"].is_allowed(run)
    run.gold = 500
    assert ALL_EVENTS["welcome_to_wongos"].is_allowed(run)

    event = make_event("welcome_to_wongos", run).begin()
    assert event.option_keys() == [
        "BARGAIN_BIN", "FEATURED_ITEM", "MYSTERY_BOX", "LEAVE"]
    assert event.choose("MYSTERY_BOX")
    assert run.gold == 200
    assert [r.id for r in run.relics] == ["wongos_mystery_ticket"]
    assert run.wongo_points == 8


def test_wongos_locks_unaffordable_options():
    run = hive_run(31)
    run.gold = 150
    event = make_event("welcome_to_wongos", run).begin()
    assert event.option_keys() == [
        "BARGAIN_BIN", "FEATURED_ITEM_LOCKED", "MYSTERY_BOX_LOCKED", "LEAVE"]


def test_wongos_leave_downgrades_an_upgraded_card():
    run = hive_run(32)
    run.gold = 150
    card = make_card("strike")
    card.upgrade()
    run.add_card(card)
    event = make_event("welcome_to_wongos", run).begin()
    assert event.choose("LEAVE")
    assert card.upgrade_level == 0
    assert event.finished


def test_wongos_mystery_ticket_pays_out_after_five_combats():
    from sts2_rl.rewards import CombatRewards
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType

    run = hive_run(33)
    ticket = make_relic("wongos_mystery_ticket")
    run.add_relic(ticket)
    rewards = CombatRewards(room_type=RoomType.MONSTER)
    ticket.modify_combat_rewards(run, rewards)
    assert rewards.relics == []          # not yet
    for _ in range(5):
        ticket.after_combat_end(run, RoomType.MONSTER)
    ticket.modify_combat_rewards(run, rewards)
    assert len(rewards.relics) == 3
    assert ticket.is_used_up
    # Spent: a later screen adds nothing.
    more = CombatRewards(room_type=RoomType.MONSTER)
    ticket.modify_combat_rewards(run, more)
    assert more.relics == []


def test_slippery_bridge_hold_on_escalates_and_rerolls():
    run = slippery_run(5)
    hp0 = run.hp
    event = make_event("slippery_bridge", run).begin()
    first = event.shown_card
    assert event.choose("HOLD_ON_0")
    assert run.hp == hp0 - 3            # 3 + 0 holds
    assert not event.finished
    second = event.shown_card
    # Reroll excludes the previously shown card's id (GetType in the source).
    assert second.id != first.id
    assert event.choose("HOLD_ON_1")
    assert run.hp == hp0 - 3 - 4        # 3 + 1 holds
    # Overcome still works after holds.
    assert event.choose("OVERCOME")
    assert event.finished
