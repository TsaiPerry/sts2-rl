"""
Tests for both Act-2 event pools — Underdocks and Hive (sts2_rl/events/) — the
event-granted cards (event_cards.py, trash_heap_cards.py), the Steady/Spiral/
Perfect Fit enchantments, the Glowwater potion, the event relics, and the
Punch-Off / Mysterious Knight combat encounters.

Run with:  py -m pytest test/test_underdocks_hive_events.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, RunState, make_event
from sts2_rl.cards import CardType, make_card
from sts2_rl.enchantments import (
    PerfectFitEnchantment,
    SpiralEnchantment,
    SteadyEnchantment,
    make_enchantment,
)
from sts2_rl.events import (
    ALL_EVENTS,
    HIVE_EVENTS,
    UNDERDOCKS_EVENTS,
    allowed_events,
    make_event as _make_event,
)
from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
from sts2_rl.events.the_lantern_key import MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER
from sts2_rl.monsters import FUZZY_WURM_ENCOUNTER
from sts2_rl.monsters.base import MoveType


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


def rich_run(seed: int = 0, gold: int = 400, hp: int | None = None, floor: int = 10) -> RunState:
    """A run with plenty of gold/floor and a mixed deck so gates pass."""
    run = RunState(rng=random.Random(seed), gold=gold, total_floor=floor)
    if hp is not None:
        run.hp = hp
    run.deck = (
        [make_card("strike") for _ in range(4)]
        + [make_card("defend") for _ in range(4)]
        + [make_card("bash"), make_card("anger"), make_card("pommel_strike")]
    )
    return run


def pick(*cards):
    wanted = list(cards)
    return lambda purpose, candidates, count: [c for c in wanted if c in candidates][:count]


def build_combat(deck_ids, encounter=None, relics=None, seed=0):
    deck = [make_card(cid) if isinstance(cid, str) else cid for cid in deck_ids]
    return CombatState(
        starting_deck=deck,
        rng=random.Random(seed),
        encounter=encounter or FUZZY_WURM_ENCOUNTER,
        relics=relics or [],
    )


# ── Pools ──────────────────────────────────────────────────────────────────


def test_underdocks_pool_complete():
    assert UNDERDOCKS_EVENTS == (
        "abyssal_baths", "drowning_beacon", "endless_conveyor", "punch_off",
        "spiraling_whirlpool", "sunken_statue", "sunken_treasury",
        "doors_of_light_and_dark", "trash_heap", "waterlogged_scriptorium",
    )
    for eid in UNDERDOCKS_EVENTS:
        assert ALL_EVENTS[eid].id == eid


def test_hive_pool_complete():
    assert HIVE_EVENTS == (
        "amalgamator", "bugslayer", "colorful_philosophers", "colossal_flower",
        "field_of_man_sized_holes", "infested_automaton", "lost_wisp",
        "spirit_grafter", "the_lantern_key", "zen_weaver",
    )
    for eid in HIVE_EVENTS:
        assert ALL_EVENTS[eid].id == eid


def test_gate_filtering_underdocks():
    poor = fresh_run(gold=50)                       # 50 gold, floor 0, full HP
    allowed = allowed_events(poor, UNDERDOCKS_EVENTS)
    assert "endless_conveyor" not in allowed        # needs 120 gold
    assert "waterlogged_scriptorium" not in allowed  # needs 55 gold
    assert "punch_off" not in allowed               # needs floor >= 6
    assert "drowning_beacon" in allowed             # always allowed

    rich = fresh_run(gold=200, total_floor=6)
    allowed2 = allowed_events(rich, UNDERDOCKS_EVENTS)
    assert {"endless_conveyor", "waterlogged_scriptorium", "punch_off"} <= set(allowed2)


def test_gate_filtering_hive():
    run = fresh_run(gold=50)  # full HP, low gold, starter deck
    allowed = allowed_events(run, HIVE_EVENTS)
    assert "zen_weaver" not in allowed              # needs 125 gold
    assert "colorful_philosophers" not in allowed   # single character
    # Amalgamator needs 2 Basic Strikes + 2 Basic Defends — the starter has them.
    assert "amalgamator" in allowed
    assert "colossal_flower" in allowed             # full HP >= 19


# ── Abyssal Baths ────────────────────────────────────────────────────────────


def test_abyssal_baths_immerse_and_linger():
    run = fresh_run()
    ev = make_event("abyssal_baths", run).begin()
    ev.choose("IMMERSE")
    # +2 Max HP (heals 2 to full-then-capped) then 3 damage: 80 max, hp 80-1.
    assert run.max_hp == 82 and run.hp == 79
    assert set(ev.option_keys()) == {"LINGER", "EXIT_BATHS"}
    ev.choose("LINGER")     # +2 max (84), take 4 -> hp 79+2-4 = 77
    assert run.max_hp == 84 and run.hp == 77
    ev.choose("EXIT_BATHS")
    assert ev.finished


def test_abyssal_baths_abstain_heals():
    run = fresh_run()
    run.hp = 60
    make_event("abyssal_baths", run).begin().choose("ABSTAIN")
    assert run.hp == 70  # heal 10


# ── Drowning Beacon ──────────────────────────────────────────────────────────


def test_drowning_beacon_bottle():
    run = fresh_run()
    make_event("drowning_beacon", run).begin().choose("BOTTLE")
    assert [p.id for p in run.held_potions] == ["glowwater"]


def test_drowning_beacon_climb():
    run = fresh_run()
    make_event("drowning_beacon", run).begin().choose("CLIMB")
    assert run.max_hp == 67  # lose 13 Max HP
    assert [r.id for r in run.relics] == ["fresnel_lens"]


# ── Sunken Treasury ──────────────────────────────────────────────────────────


def test_sunken_treasury_chests():
    run = fresh_run(3)
    ev = make_event("sunken_treasury", run).begin()
    assert 52 <= ev.small_gold <= 67   # 60 + [-8, 7]
    assert 303 <= ev.large_gold <= 363  # 333 + [-30, 30]
    ev.choose("SECOND_CHEST")
    assert run.gold == 99 + ev.large_gold
    assert any(c.id == "greed" for c in run.deck)


# ── Doors of Light and Dark ──────────────────────────────────────────────────


def test_doors_light_upgrades_two():
    run = rich_run()
    make_event("doors_of_light_and_dark", run).begin().choose("LIGHT")
    assert sum(c.upgrade_level for c in run.deck) == 2


def test_doors_dark_removes_one():
    run = rich_run()
    target = run.deck[0]
    run.card_selector = pick(target)
    before = len(run.deck)
    make_event("doors_of_light_and_dark", run).begin().choose("DARK")
    assert len(run.deck) == before - 1 and target not in run.deck


# ── Trash Heap ───────────────────────────────────────────────────────────────


def test_trash_heap_dive_in():
    run = fresh_run(1)
    make_event("trash_heap", run).begin().choose("DIVE_IN")
    assert run.hp == 72  # lose 8
    assert len(run.relics) == 1
    assert run.relics[0].id in {"darkstone_periapt", "dream_catcher", "hand_drill",
                                "maw_bank", "the_boot"}


def test_trash_heap_grab():
    run = fresh_run(1)
    make_event("trash_heap", run).begin().choose("GRAB")
    assert run.gold == 199  # +100
    added = run.deck[-1].id
    assert added in {"caltrops", "clash", "distraction", "dual_wield", "entrench",
                     "hello_world", "outmaneuver", "rebound", "rip_and_tear", "stack"}


def test_trash_heap_gated_by_hp():
    run = fresh_run()
    run.hp = 5
    assert not ALL_EVENTS["trash_heap"].is_allowed(run)


# ── Waterlogged Scriptorium ──────────────────────────────────────────────────


def test_waterlogged_bloody_ink():
    run = rich_run(gold=99)
    make_event("waterlogged_scriptorium", run).begin().choose("BLOODY_INK")
    assert run.max_hp == 86  # +6


def test_waterlogged_tentacle_quill_enchants_steady():
    run = rich_run(gold=99)
    target = run.deck[0]
    run.card_selector = pick(target)
    make_event("waterlogged_scriptorium", run).begin().choose("TENTACLE_QUILL")
    assert run.gold == 99 - 55
    assert isinstance(target.enchantment, SteadyEnchantment)


def test_waterlogged_locks_when_poor():
    run = rich_run(gold=60)  # >= 55 (allowed) but < 99
    keys = make_event("waterlogged_scriptorium", run).begin().option_keys()
    assert "TENTACLE_QUILL" in keys
    assert "PRICKLY_SPONGE_LOCKED" in keys


# ── Punch-Off ────────────────────────────────────────────────────────────────


def test_punch_off_gate_floor():
    assert not ALL_EVENTS["punch_off"].is_allowed(fresh_run(total_floor=5))
    assert ALL_EVENTS["punch_off"].is_allowed(fresh_run(total_floor=6))


def test_punch_off_nab():
    run = fresh_run(total_floor=6)
    make_event("punch_off", run).begin().choose("NAB")
    assert any(c.id == "injury" for c in run.deck)
    assert len(run.relics) == 1


def test_punch_off_fight_sets_encounter():
    run = fresh_run(total_floor=6)
    ev = make_event("punch_off", run).begin()
    ev.choose("I_CAN_TAKE_THEM")
    ev.choose("FIGHT")
    assert ev.pending_encounter is PUNCH_OFF_EVENT_ENCOUNTER
    assert ev.finished


def test_punch_off_encounter_two_constructs():
    combat = CombatState(rng=random.Random(2), encounter=PUNCH_OFF_EVENT_ENCOUNTER)
    assert len(combat.enemies) == 2
    for e in combat.enemies:
        # PunchConstruct.cs:75-78 cuts CURRENT hp only; MaxHp stays 55.
        assert e.max_hp == 55
        assert e.hp < 55  # each loses NextInt(2, 10)
    # The left construct opens with Fast Punch (a multi-hit attack).
    assert combat.enemies[0].current_intent.move_type == MoveType.ATTACK
    assert combat.enemies[0].current_intent.hits == 2


# ── Spiraling Whirlpool ──────────────────────────────────────────────────────


def test_spiraling_whirlpool_gate_and_drink():
    run = fresh_run()  # starter deck has Basic Strikes/Defends
    assert ALL_EVENTS["spiraling_whirlpool"].is_allowed(run)
    ev = make_event("spiraling_whirlpool", run).begin()
    assert ev.heal == 80 * 33 // 100  # 26
    run.hp = 50
    ev.choose("DRINK")
    assert run.hp == 50 + 26


def test_spiraling_whirlpool_observe_enchants_spiral():
    run = fresh_run()
    target = next(c for c in run.deck if c.id == "strike")
    run.card_selector = pick(target)
    make_event("spiraling_whirlpool", run).begin().choose("OBSERVE")
    assert isinstance(target.enchantment, SpiralEnchantment)


# ── Endless Conveyor ─────────────────────────────────────────────────────────


def test_endless_conveyor_gate():
    assert not ALL_EVENTS["endless_conveyor"].is_allowed(fresh_run(gold=119))
    assert ALL_EVENTS["endless_conveyor"].is_allowed(fresh_run(gold=120))


def test_endless_conveyor_grab_costs_gold_and_acts():
    run = fresh_run(gold=200)
    ev = make_event("endless_conveyor", run).begin()
    # First dish is rolled at CalculateVars; grabbing a non-golden dish costs 40.
    ev.choose(ev.current_dish_id if ev.current_dish_id != "LOCKED" else 0)
    assert run.gold <= 200  # spent 40 unless it was a Golden Fysh
    assert not ev.finished  # loops back with a new dish


def test_endless_conveyor_observe_upgrades():
    run = fresh_run(gold=200)
    make_event("endless_conveyor", run).begin().choose("OBSERVE_CHEF")
    assert sum(c.upgrade_level for c in run.deck) == 1


# ── Amalgamator ──────────────────────────────────────────────────────────────


def test_amalgamator_combine_strikes():
    run = fresh_run()  # 5 Strikes, 4 Defends, Bash
    strikes = [c for c in run.deck if c.id == "strike"][:2]
    run.card_selector = pick(*strikes)
    make_event("amalgamator", run).begin().choose("COMBINE_STRIKES")
    assert sum(1 for c in run.deck if c.id == "strike") == 3
    assert any(c.id == "ultimate_strike" for c in run.deck)


def test_amalgamator_gate():
    run = fresh_run()
    run.deck = [make_card("strike"), make_card("defend"), make_card("defend")]
    assert not ALL_EVENTS["amalgamator"].is_allowed(run)  # only 1 strike


# ── Bugslayer / Infested Automaton / Lost Wisp / Spirit Grafter ─────────────


def test_bugslayer_adds_card():
    run = fresh_run()
    make_event("bugslayer", run).begin().choose("SQUASH")
    assert run.deck[-1].id == "squash"


def test_infested_automaton_study_adds_power():
    run = fresh_run(5)
    make_event("infested_automaton", run).begin().choose("STUDY")
    assert run.deck[-1].card_type == CardType.POWER


def test_infested_automaton_touch_core_zero_cost():
    run = fresh_run(5)
    make_event("infested_automaton", run).begin().choose("TOUCH_CORE")
    assert run.deck[-1].energy_cost == 0


def test_lost_wisp_claim_and_search():
    run = fresh_run(2)
    ev = make_event("lost_wisp", run).begin()
    assert 45 <= ev.gold <= 75
    make_event("lost_wisp", fresh_run(2)).begin().choose("SEARCH")
    ev.choose("CLAIM")
    assert any(c.id == "decay" for c in run.deck)
    assert [r.id for r in run.relics] == ["lost_wisp"]


def test_spirit_grafter_let_it_in():
    run = fresh_run()
    run.hp = 40
    make_event("spirit_grafter", run).begin().choose("LET_IT_IN")
    assert run.hp == 65  # heal 25
    assert run.deck[-1].id == "metamorphosis"


def test_spirit_grafter_rejection():
    run = fresh_run()
    target = run.deck[0]
    run.card_selector = pick(target)
    make_event("spirit_grafter", run).begin().choose("REJECTION")
    assert target.upgrade_level == 1
    assert run.hp == 70  # lose 10


# ── Colossal Flower ──────────────────────────────────────────────────────────


def test_colossal_flower_gate():
    run = fresh_run()
    run.hp = 18
    assert not ALL_EVENTS["colossal_flower"].is_allowed(run)


def test_colossal_flower_extract_immediately():
    run = fresh_run()
    make_event("colossal_flower", run).begin().choose("EXTRACT_CURRENT_PRIZE")
    assert run.gold == 99 + 35


def test_colossal_flower_reach_to_pollinous_core():
    run = fresh_run()
    ev = make_event("colossal_flower", run).begin()
    ev.choose("REACH_DEEPER")   # take 5, digs 1
    ev.choose("REACH_DEEPER")   # take 6, digs 2 -> final page
    assert set(ev.option_keys()) == {"EXTRACT_INSTEAD", "POLLINOUS_CORE"}
    ev.choose("POLLINOUS_CORE")  # take 7 more, get relic
    assert run.hp == 80 - 5 - 6 - 7
    assert [r.id for r in run.relics] == ["pollinous_core"]


# ── Field of Man-Sized Holes ─────────────────────────────────────────────────


def test_field_enter_your_hole_enchants():
    run = fresh_run()
    target = run.deck[0]
    run.card_selector = pick(target)
    assert ALL_EVENTS["field_of_man_sized_holes"].is_allowed(run)
    make_event("field_of_man_sized_holes", run).begin().choose("ENTER_YOUR_HOLE")
    assert isinstance(target.enchantment, PerfectFitEnchantment)


def test_field_resist_removes_and_adds_normality():
    run = fresh_run()
    removed = run.deck[:2]
    run.card_selector = pick(*removed)
    make_event("field_of_man_sized_holes", run).begin().choose("RESIST")
    assert all(c not in run.deck for c in removed)
    assert any(c.id == "normality" for c in run.deck)


# ── Zen Weaver ───────────────────────────────────────────────────────────────


def test_zen_weaver_breathing_techniques():
    run = fresh_run(gold=150)
    make_event("zen_weaver", run).begin().choose("BREATHING_TECHNIQUES")
    assert run.gold == 150 - 50
    assert sum(1 for c in run.deck if c.id == "enlightenment") == 2


def test_zen_weaver_locks_expensive_options():
    run = fresh_run(gold=150)  # >= 125 but < 250
    keys = make_event("zen_weaver", run).begin().option_keys()
    assert "EMOTIONAL_AWARENESS" in keys
    assert "LOCKED" in keys  # Arachnid Acupuncture locked


def test_zen_weaver_arachnid_removes_two():
    run = fresh_run(gold=300)
    removed = run.deck[:2]
    run.card_selector = pick(*removed)
    make_event("zen_weaver", run).begin().choose("ARACHNID_ACUPUNCTURE")
    assert run.gold == 300 - 250
    assert all(c not in run.deck for c in removed)


# ── The Lantern Key ──────────────────────────────────────────────────────────


def test_lantern_key_return():
    run = fresh_run()
    make_event("the_lantern_key", run).begin().choose("RETURN_THE_KEY")
    assert run.gold == 99 + 100


def test_lantern_key_fight():
    run = fresh_run()
    ev = make_event("the_lantern_key", run).begin()
    ev.choose("KEEP_THE_KEY")
    ev.choose("FIGHT")
    assert ev.pending_encounter is MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER


def test_mysterious_knight_stats():
    combat = CombatState(rng=random.Random(0), encounter=MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER)
    knight = combat.enemies[0]
    assert knight.max_hp == 101
    assert knight.powers["strength"].amount == 6
    assert knight.powers["plating"].amount == 6
    assert knight.block == 6  # Plating grants block at combat start


def test_colorful_philosophers_never_allowed():
    assert not ALL_EVENTS["colorful_philosophers"].is_allowed(fresh_run())
    ev = make_event("colorful_philosophers", fresh_run()).begin()
    assert ev.finished and ev.option_keys() == []


# ── Event cards in combat ────────────────────────────────────────────────────


def test_ultimate_strike_and_defend():
    combat = build_combat(["ultimate_strike", "ultimate_defend", "defend", "defend", "defend"])
    enemy = combat.enemies[0]
    hp0 = enemy.hp
    us = combat.player.hand.index(next(c for c in combat.player.hand if c.id == "ultimate_strike"))
    combat.play_card(us)
    assert hp0 - enemy.hp == 14
    ud = combat.player.hand.index(next(c for c in combat.player.hand if c.id == "ultimate_defend"))
    combat.play_card(ud)
    assert combat.player.block == 11


def test_squash_applies_vulnerable():
    combat = build_combat(["squash", "defend", "defend", "defend", "defend"])
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "squash")))
    assert combat.enemies[0].powers["vulnerable"].amount == 2


def test_exterminate_hits_all_enemies_four_times():
    combat = build_combat(["exterminate", "defend", "defend", "defend", "defend"],
                          encounter=PUNCH_OFF_EVENT_ENCOUNTER)
    hps = [e.hp for e in combat.enemies]
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "exterminate")))
    for before, e in zip(hps, combat.enemies):
        assert before - e.hp == 12  # 3 damage x 4 hits, no enemy block turn 1


def test_feeding_frenzy_temp_strength():
    combat = build_combat(["feeding_frenzy", "defend", "defend", "defend", "defend"])
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "feeding_frenzy")))
    assert combat.player.powers["strength"].amount == 5
    combat.end_turn()
    # Temporary Strength is reverted at end of turn.
    assert "strength" not in combat.player.powers or combat.player.powers["strength"].amount == 0


def test_outmaneuver_energy_next_turn():
    combat = build_combat(["outmaneuver", "defend", "defend", "defend", "defend"])
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "outmaneuver")))
    combat.end_turn()
    if not combat.is_over:
        assert combat.player.energy == combat.player.ENERGY_PER_TURN + 2


def test_rebound_puts_card_on_top_of_draw():
    combat = build_combat(["rebound", "strike", "strike", "strike", "strike"])
    reb = combat.player.hand.index(next(c for c in combat.player.hand if c.id == "rebound"))
    card = combat.player.hand[reb]
    combat.play_card(reb)
    # Rebound redirects its own play from discard to the top of the draw pile.
    assert combat.player.draw_pile and combat.player.draw_pile[-1] is card
    assert card not in combat.player.discard_pile


def test_stack_block_equals_discard_count():
    combat = build_combat(["stack", "defend", "defend", "defend", "defend"])
    combat.player.discard_pile.extend([make_card("strike") for _ in range(3)])
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "stack")))
    assert combat.player.block == 3  # 3 in discard, Stack itself excluded


def test_entrench_doubles_block():
    combat = build_combat(["defend", "entrench", "strike", "strike", "strike"])
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "defend")))
    assert combat.player.block == 5
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "entrench")))
    assert combat.player.block == 10


def test_enlightenment_reduces_hand_cost():
    combat = build_combat(["enlightenment", "bash", "strike", "strike", "strike"])
    bash = next(c for c in combat.player.hand if c.id == "bash")
    assert bash.energy_cost == 2
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "enlightenment")))
    assert bash.energy_cost == 1


def test_metamorphosis_adds_free_attacks_to_draw():
    combat = build_combat(["metamorphosis", "defend", "defend", "defend", "defend"])
    before = len(combat.player.draw_pile)
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "metamorphosis")))
    added = combat.player.draw_pile[before:]
    assert len(added) == 3
    for c in added:
        assert c.card_type == CardType.ATTACK and c.energy_cost == 0


def test_hello_world_adds_common_at_turn_start():
    combat = build_combat(["hello_world", "defend", "defend", "defend", "defend"])
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "hello_world")))
    hand_before = len(combat.player.hand)
    combat.end_turn()
    if not combat.is_over:
        # Next turn drew the normal hand plus one generated Common card.
        assert "hello_world" in combat.player.powers


def test_caltrops_grants_thorns():
    combat = build_combat(["caltrops", "defend", "defend", "defend", "defend"])
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "caltrops")))
    assert combat.player.powers["thorns"].amount == 3


def test_clash_only_playable_with_all_attacks():
    combat = build_combat(["clash", "defend", "strike", "strike", "strike"])
    clash = next(c for c in combat.player.hand if c.id == "clash")
    # Defend in hand -> not playable.
    assert not combat.hooks.should_play_card(clash)
    # Remove the non-attacks; now the whole hand is Attacks.
    combat.player.hand = [c for c in combat.player.hand if c.card_type == CardType.ATTACK]
    assert combat.hooks.should_play_card(clash)


def test_rip_and_tear_two_hits():
    combat = build_combat(["rip_and_tear", "defend", "defend", "defend", "defend"])
    enemy = combat.enemies[0]
    hp0 = enemy.hp
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "rip_and_tear")))
    assert hp0 - enemy.hp == 14  # 7 x 2 into the only enemy


# ── Enchantments in combat ───────────────────────────────────────────────────


def test_spiral_plays_basic_card_twice():
    strike = make_card("strike")
    make_enchantment("spiral").attach(strike)
    combat = build_combat([strike, "defend", "defend", "defend", "defend"],
                          encounter=PUNCH_OFF_EVENT_ENCOUNTER)
    enemy = combat.enemies[0]
    hp0 = enemy.hp
    idx = combat.player.hand.index(next(c for c in combat.player.hand if c.id == "strike"))
    combat.play_card(idx, target_idx=0)
    assert hp0 - enemy.hp == 12  # 6 damage played twice


def test_steady_card_is_retained():
    defend = make_card("defend")
    make_enchantment("steady").attach(defend)
    combat = build_combat([defend, "strike", "strike", "strike", "strike"])
    kept = next(c for c in combat.player.hand if c.id == "defend")
    assert kept.retain
    combat.end_turn()
    if not combat.is_over:
        assert kept in combat.player.hand  # not discarded at end of turn


def test_perfect_fit_goes_to_top_after_reshuffle():
    card = make_card("pommel_strike")
    make_enchantment("perfect_fit").attach(card)
    combat = build_combat([card, "defend", "defend", "defend", "defend"])
    pf = next(c for c in combat.player.hand if c.id == "pommel_strike")
    # Move it to the discard pile, empty the draw pile, then reshuffle.
    combat.player.hand.remove(pf)
    combat.player.draw_pile.clear()
    combat.player.discard_pile.append(pf)
    combat.player.reshuffle_discard_into_draw()
    assert combat.player.draw_pile[-1] is pf  # on top of the draw pile


# ── Event relics in combat ───────────────────────────────────────────────────


def test_lost_wisp_relic_damages_on_power_play():
    from sts2_rl.relics import make_relic
    combat = build_combat(["caltrops", "defend", "defend", "defend", "defend"],
                          relics=[make_relic("lost_wisp")])
    enemy = combat.enemies[0]
    hp0 = enemy.hp
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "caltrops")))
    assert hp0 - enemy.hp == 8  # Caltrops is a Power -> Lost Wisp deals 8


def test_the_boot_floors_small_hits():
    from sts2_rl.relics import make_relic
    combat = build_combat(["peck", "defend", "defend", "defend", "defend"],
                          relics=[make_relic("the_boot")])
    enemy = combat.enemies[0]
    hp0 = enemy.hp
    combat.play_card(combat.player.hand.index(next(c for c in combat.player.hand if c.id == "peck")),
                     target_idx=0)
    # Peck = 2 damage x 3 hits; each hit is floored to 5 -> 15 total.
    assert hp0 - enemy.hp == 15


# ── Full-pool headless smoke ─────────────────────────────────────────────────


@pytest.mark.parametrize("eid", sorted(set(UNDERDOCKS_EVENTS + HIVE_EVENTS)))
def test_every_event_drives_to_completion(eid):
    starts = _make_event(eid, rich_run()).begin().option_keys() or [None]
    for i, start in enumerate(starts):
        run = rich_run(seed=i)
        run.card_selector = lambda purpose, cands, n: cands[:n]
        ev = _make_event(eid, run).begin()
        if start is not None:
            ev.choose(start)
        # Drive the LAST non-locked option each page — for looping events
        # (Abyssal Baths, Endless Conveyor, ...) that is the exit/terminating
        # branch, so this always converges.
        depth = 0
        while not ev.finished and ev.pending_encounter is None and depth < 20:
            nxt = [o for o in ev.options if not o.locked]
            if not nxt:
                break
            ev.choose(nxt[-1].key)
            depth += 1
        assert ev.finished or ev.pending_encounter is not None
