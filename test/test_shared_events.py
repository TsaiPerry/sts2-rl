"""The shared (cross-act) event pool vs the source: ModelDb.AllSharedEvents
(src/Core/Models/ModelDb.cs:135) — 18 events appended to EVERY act's event
queue by ActModel.GenerateRooms. One section per event; sections are added
per wave as the port lands (plan: docs/superpowers/plans/
2026-07-19-shared-events.md)."""
import random

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
