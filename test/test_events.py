"""
Tests for the Act-1 (Overgrowth) event pool (sts2_rl/events/), the RunState
run layer (sts2_rl/run.py), the Sown/Slither enchantments, and the event
cards (Byrdonis Egg, Peck, Toric Toughness).

Run with:  py -m pytest test/test_events.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, RunState, make_event
from sts2_rl.cards import CardRarity, make_card
from sts2_rl.enchantments import SlitherEnchantment, SownEnchantment
from sts2_rl.events import ALL_EVENTS, OVERGROWTH_EVENTS, allowed_events
from sts2_rl.events.dense_vegetation import DENSE_VEGETATION_EVENT_ENCOUNTER
from sts2_rl.monsters import FUZZY_WURM_ENCOUNTER
from sts2_rl.monsters.base import MoveType
from sts2_rl.relics import ALL_RELICS, RelicRarity


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


def pick(*cards):
    """A card_selector that returns the given cards regardless of purpose."""
    wanted = list(cards)
    return lambda purpose, candidates, count: [c for c in wanted if c in candidates][:count]


# ── Registry / pool ────────────────────────────────────────────────────────


def test_overgrowth_pool_is_complete():
    # Overgrowth.cs AllEvents: exactly these 13 events, in this order.
    assert OVERGROWTH_EVENTS == (
        "aroma_of_chaos", "byrdonis_nest", "dense_vegetation",
        "jungle_maze_adventure", "luminous_choir", "morphic_grove",
        "sapphire_seed", "sunken_statue", "tablet_of_truth", "unrest_site",
        "wellspring", "whispering_hollow", "wood_carvings",
    )
    for event_id in OVERGROWTH_EVENTS:
        assert event_id in ALL_EVENTS
        assert ALL_EVENTS[event_id].id == event_id


def test_allowed_events_filters_gates():
    run = fresh_run()  # full HP, 99 gold
    allowed = allowed_events(run)
    # 99 gold < 149 (Luminous Choir) and < 100 (Morphic Grove); full HP
    # blocks Unrest Site (needs <= 70%).
    assert "luminous_choir" not in allowed
    assert "morphic_grove" not in allowed
    assert "unrest_site" not in allowed
    assert "wellspring" in allowed and "wood_carvings" in allowed


# ── RunState basics ────────────────────────────────────────────────────────


def test_run_state_starting_stats():
    run = fresh_run()
    assert (run.hp, run.max_hp, run.gold) == (80, 80, 99)
    ids = sorted(c.id for c in run.deck)
    assert ids == ["bash"] + ["defend"] * 4 + ["strike"] * 5


def test_gold_truncates_and_clamps():
    run = fresh_run()
    run.gain_gold(10.9)
    assert run.gold == 109  # (int)amount truncates
    run.lose_gold(1000)
    assert run.gold == 0    # never negative
    run.gain_gold(-5)
    assert run.gold == 0    # gains require amount > 0


def test_max_hp_changes():
    run = fresh_run()
    run.lose_hp(30)
    run.gain_max_hp(7)      # GainMaxHp heals the gained amount
    assert (run.hp, run.max_hp) == (57, 87)
    run.lose_max_hp(60)     # current HP clamps to the new max
    assert (run.hp, run.max_hp) == (27, 27)
    run.lose_max_hp(100)    # max HP floors at 1
    assert (run.hp, run.max_hp) == (1, 1)


def test_transform_replaces_in_place_with_pool_card():
    run = fresh_run()
    original = run.deck[3]
    replacement = run.transform_card(original)
    assert run.deck[3] is replacement
    assert replacement.id != original.id
    assert replacement.rarity in (
        CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE
    )


def test_relic_grab_bag_pull():
    run = fresh_run()
    bag_size = len(run.relic_grab_bag)
    expected = sum(
        1 for cls in ALL_RELICS.values()
        if cls.rarity in (RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE)
    )
    assert bag_size == expected > 0  # every bag-eligible relic, exactly once
    relic = run.pull_relic_from_front()
    assert relic is not None
    assert ALL_RELICS[relic.id].rarity in (
        RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE
    )
    assert len(run.relic_grab_bag) == bag_size - 1
    assert relic.id not in run.relic_grab_bag  # never seen again


def test_create_combat_carries_hp_and_isolates_deck():
    run = fresh_run(3)
    run.lose_hp(25)
    combat = run.create_combat(FUZZY_WURM_ENCOUNTER)
    assert combat.player.hp == 55 and combat.player.max_hp == 80
    # The combat deck is a deep copy: in-combat upgrades don't leak back.
    combat.player.hand[0].upgrade()
    assert all(c.upgrade_level == 0 for c in run.deck)
    combat.player.hp = 40
    run.finish_combat(combat)
    assert run.hp == 40


# ── Aroma of Chaos ─────────────────────────────────────────────────────────


def test_aroma_of_chaos_let_go_transforms():
    run = fresh_run(1)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("aroma_of_chaos", run).begin()
    assert event.option_keys() == ["LET_GO", "MAINTAIN_CONTROL"]
    assert event.choose("LET_GO")
    assert target not in run.deck and len(run.deck) == 10
    assert event.finished and event.page == "LET_GO"


def test_aroma_of_chaos_maintain_control_upgrades():
    run = fresh_run(1)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("aroma_of_chaos", run).begin()
    event.choose("MAINTAIN_CONTROL")
    assert target.upgrade_level == 1


# ── Byrdonis Nest ──────────────────────────────────────────────────────────


def test_byrdonis_nest_eat():
    run = fresh_run()
    run.lose_hp(10)
    event = make_event("byrdonis_nest", run).begin()
    event.choose("EAT")
    assert (run.hp, run.max_hp) == (77, 87)  # +7 max HP, heals 7


def test_byrdonis_nest_take_adds_egg_and_blocks_reentry():
    run = fresh_run()
    assert ALL_EVENTS["byrdonis_nest"].is_allowed(run)
    event = make_event("byrdonis_nest", run).begin()
    event.choose("TAKE")
    assert any(c.id == "byrdonis_egg" for c in run.deck)
    # HasEventPet: an egg in the deck blocks the event.
    assert not ALL_EVENTS["byrdonis_nest"].is_allowed(run)


def test_byrdonis_egg_is_unplayable_in_combat():
    deck = [make_card("strike") for _ in range(4)] + [make_card("byrdonis_egg")]
    combat = CombatState(starting_deck=deck, rng=random.Random(0))
    egg_idx = next(
        i for i, c in enumerate(combat.player.hand) if c.id == "byrdonis_egg"
    )
    assert egg_idx + 1 not in combat.valid_actions()
    assert not combat.play_card(egg_idx)


# ── Dense Vegetation ───────────────────────────────────────────────────────


def test_dense_vegetation_trudge_on():
    run = fresh_run(7)
    event = make_event("dense_vegetation", run).begin()
    assert 61 <= event.gold <= 99  # NextInt(61, 100)
    event.choose("TRUDGE_ON")
    assert run.hp == 72  # lose 8
    assert run.gold == 99 + event.gold


def test_dense_vegetation_rest_then_fight():
    run = fresh_run(7)
    run.lose_hp(40)
    event = make_event("dense_vegetation", run).begin()
    event.choose("REST")
    assert run.hp == 40 + 24  # rest-site heal: 30% of 80, truncated
    assert event.page == "REST" and event.option_keys() == ["FIGHT"]
    event.choose("FIGHT")
    assert event.finished
    assert event.pending_encounter is DENSE_VEGETATION_EVENT_ENCOUNTER
    combat = run.create_combat(event.pending_encounter)
    assert len(combat.enemies) == 4
    assert not any(e.stunned for e in combat.enemies)
    # Slots alternate opening moves: odd slots bite, even slots wriggle.
    intents = [e.current_intent.move_type for e in combat.enemies]
    assert intents == [MoveType.ATTACK, MoveType.BUFF, MoveType.ATTACK, MoveType.BUFF]


# ── Jungle Maze Adventure ──────────────────────────────────────────────────


def test_jungle_maze_solo_quest():
    run = fresh_run(11)
    event = make_event("jungle_maze_adventure", run).begin()
    event.choose("SOLO_QUEST")
    assert run.hp == 62  # lose 18
    assert 99 + 135 <= run.gold <= 99 + 164  # 150 ± 15, truncated


def test_jungle_maze_join_forces():
    run = fresh_run(11)
    event = make_event("jungle_maze_adventure", run).begin()
    event.choose("JOIN_FORCES")
    assert run.hp == 80
    assert 99 + 35 <= run.gold <= 99 + 64  # 50 ± 15, truncated


# ── Luminous Choir ─────────────────────────────────────────────────────────


def test_luminous_choir_gate_and_tribute():
    assert not ALL_EVENTS["luminous_choir"].is_allowed(fresh_run())  # 99 < 149
    run = fresh_run(2, gold=200)
    assert ALL_EVENTS["luminous_choir"].is_allowed(run)
    event = make_event("luminous_choir", run).begin()
    assert 100 <= event.gold_cost <= 149
    assert event.option_keys() == ["REACH_INTO_THE_FLESH", "OFFER_TRIBUTE"]
    event.choose("OFFER_TRIBUTE")
    assert run.gold == 200 - event.gold_cost
    assert len(run.relics) == 1


def test_luminous_choir_tribute_locked_when_unaffordable():
    run = fresh_run(2, gold=200)
    event = make_event("luminous_choir", run)
    event.calculate_vars()
    run.gold = event.gold_cost - 1  # drop below the rolled cost
    event._set_state("INITIAL", event.initial_options())
    assert event.option_keys() == ["REACH_INTO_THE_FLESH", "OFFER_TRIBUTE_LOCKED"]
    assert not event.choose("OFFER_TRIBUTE_LOCKED")
    assert not event.finished


def test_luminous_choir_reach_removes_two_adds_spore_mind():
    run = fresh_run(2, gold=200)
    targets = run.deck[:2]
    run.card_selector = pick(*targets)
    event = make_event("luminous_choir", run).begin()
    event.choose("REACH_INTO_THE_FLESH")
    assert all(t not in run.deck for t in targets)
    assert sum(1 for c in run.deck if c.id == "spore_mind") == 1
    assert len(run.deck) == 9  # 10 - 2 + 1


# ── Morphic Grove ──────────────────────────────────────────────────────────


def test_morphic_grove_group_takes_all_gold_and_transforms_two():
    assert not ALL_EVENTS["morphic_grove"].is_allowed(fresh_run())  # 99 < 100
    run = fresh_run(4, gold=150)
    targets = run.deck[:2]
    run.card_selector = pick(*targets)
    event = make_event("morphic_grove", run).begin()
    event.choose("GROUP")
    assert run.gold == 0
    assert all(t not in run.deck for t in targets)
    assert len(run.deck) == 10


def test_morphic_grove_loner():
    run = fresh_run(4, gold=150)
    event = make_event("morphic_grove", run).begin()
    event.choose("LONER")
    assert run.max_hp == 85


# ── Sapphire Seed ──────────────────────────────────────────────────────────


def test_sapphire_seed_eat_heals_and_upgrades():
    run = fresh_run(5)
    run.lose_hp(20)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("sapphire_seed", run).begin()
    event.choose("EAT")
    assert run.hp == 69  # +9
    assert target.upgrade_level == 1


def test_sapphire_seed_plant_attaches_sown():
    run = fresh_run(5)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("sapphire_seed", run).begin()
    event.choose("PLANT")
    assert isinstance(target.enchantment, SownEnchantment)


def test_sown_grants_energy_on_first_play_each_combat():
    strike = make_card("strike")
    SownEnchantment(amount=1).attach(strike)
    deck = [strike] + [make_card("defend") for _ in range(4)]
    combat = CombatState(starting_deck=deck, rng=random.Random(0))
    idx = combat.player.hand.index(strike)
    combat.play_card(idx)  # pay 1, Sown refunds 1
    assert combat.player.energy == 3
    # A second play the same combat gives nothing: replay it for free.
    combat.auto_play_card(strike)
    assert combat.player.energy == 3
    # A fresh combat resets the enchantment status.
    combat2 = CombatState(starting_deck=deck, rng=random.Random(1))
    idx2 = combat2.player.hand.index(strike)
    combat2.play_card(idx2)
    assert combat2.player.energy == 3


# ── Sunken Statue ──────────────────────────────────────────────────────────


def test_sunken_statue_grab_sword():
    run = fresh_run(6)
    event = make_event("sunken_statue", run).begin()
    event.choose("GRAB_SWORD")
    assert [r.id for r in run.relics] == ["sword_of_stone"]


def test_sunken_statue_dive():
    run = fresh_run(6)
    event = make_event("sunken_statue", run).begin()
    assert 101 <= event.gold <= 121  # 111 ± 10
    event.choose("DIVE_INTO_WATER")
    assert run.gold == 99 + event.gold
    assert run.hp == 73  # lose 7


# ── Tablet of Truth ────────────────────────────────────────────────────────


def test_tablet_of_truth_smash_heals_20():
    run = fresh_run(8)
    run.lose_hp(30)
    event = make_event("tablet_of_truth", run).begin()
    event.choose("SMASH")
    assert run.hp == 70


def test_tablet_of_truth_full_decipher_chain():
    run = fresh_run(8)
    event = make_event("tablet_of_truth", run).begin()
    assert event.option_keys() == ["DECIPHER", "SMASH"]
    event.choose("DECIPHER")  # cost 3
    assert run.max_hp == 77
    assert event.page == "DECIPHER_1"
    assert event.option_keys() == ["DECIPHER", "GIVE_UP"]
    assert sum(c.upgrade_level for c in run.deck) == 1  # 1 random upgrade
    event.choose("DECIPHER")  # cost 6
    assert run.max_hp == 71
    event.choose("DECIPHER")  # cost 12
    assert run.max_hp == 59
    event.choose("DECIPHER")  # cost 24
    assert run.max_hp == 35
    assert event.page == "DECIPHER_4"
    event.choose("DECIPHER")  # cost max_hp - 1 = 34
    assert (run.max_hp, run.hp) == (1, 1)
    assert not run.is_dead
    # The 5th decipher upgrades every remaining upgradable card.
    assert all(c.upgrade_level == 1 for c in run.deck if c.max_upgrade_level > 0)
    assert event.finished and event.page == "DECIPHER_5"


def test_tablet_of_truth_decipher_can_kill():
    run = fresh_run(8, max_hp=3, hp=3)
    event = make_event("tablet_of_truth", run).begin()
    event.choose("DECIPHER")  # cost 3 >= max HP 3 → 1 max HP, then killed
    assert run.max_hp == 1 and run.is_dead
    assert event.finished


def test_tablet_of_truth_give_up():
    run = fresh_run(8)
    event = make_event("tablet_of_truth", run).begin()
    event.choose("DECIPHER")
    event.choose("GIVE_UP")
    assert event.finished and event.page == "GIVE_UP"
    assert run.max_hp == 77


# ── Unrest Site ────────────────────────────────────────────────────────────


def test_unrest_site_gate():
    run = fresh_run()
    assert not ALL_EVENTS["unrest_site"].is_allowed(run)  # full HP
    run.lose_hp(24)  # 56 <= 0.7 * 80
    assert ALL_EVENTS["unrest_site"].is_allowed(run)


def test_unrest_site_rest_full_heal_plus_poor_sleep():
    run = fresh_run(9)
    run.lose_hp(40)
    event = make_event("unrest_site", run).begin()
    event.choose("REST")
    assert run.hp == 80
    assert sum(1 for c in run.deck if c.id == "poor_sleep") == 1


def test_unrest_site_kill_trades_max_hp_for_relic():
    run = fresh_run(9)
    run.lose_hp(40)
    event = make_event("unrest_site", run).begin()
    event.choose("KILL")
    assert run.max_hp == 72
    assert len(run.relics) == 1


# ── Wellspring ─────────────────────────────────────────────────────────────


def test_wellspring_bottle_gives_potion():
    run = fresh_run(10)
    event = make_event("wellspring", run).begin()
    event.choose("BOTTLE")
    assert len(run.potions) == 1


def test_wellspring_bathe_removes_card_adds_guilty():
    run = fresh_run(10)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("wellspring", run).begin()
    event.choose("BATHE")
    assert target not in run.deck
    assert sum(1 for c in run.deck if c.id == "guilty") == 1
    assert len(run.deck) == 10


# ── Whispering Hollow ──────────────────────────────────────────────────────


def test_whispering_hollow_gate():
    assert ALL_EVENTS["whispering_hollow"].is_allowed(fresh_run())  # 99 >= 44
    assert not ALL_EVENTS["whispering_hollow"].is_allowed(fresh_run(gold=43))


def test_whispering_hollow_gold_buys_two_potions():
    run = fresh_run(12)
    event = make_event("whispering_hollow", run).begin()
    assert 26 <= event.gold_cost <= 44  # 35 ± 9
    event.choose("GOLD")
    assert run.gold == 99 - event.gold_cost
    assert len(run.potions) == 2


def test_whispering_hollow_hug_transforms_and_hurts():
    run = fresh_run(12)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("whispering_hollow", run).begin()
    event.choose("HUG")
    assert target not in run.deck and len(run.deck) == 10
    assert run.hp == 71  # lose 9


# ── Wood Carvings ──────────────────────────────────────────────────────────


def test_wood_carvings_gate_needs_basic_card():
    assert ALL_EVENTS["wood_carvings"].is_allowed(fresh_run())
    run = fresh_run(deck=[make_card("bludgeon")])  # no Basic cards
    assert not ALL_EVENTS["wood_carvings"].is_allowed(run)


def test_wood_carvings_bird_transforms_basic_into_peck():
    run = fresh_run(13)
    target = run.deck[0]  # a Strike (Basic)
    run.card_selector = pick(target)
    event = make_event("wood_carvings", run).begin()
    assert event.option_keys() == ["BIRD", "SNAKE", "TORUS"]
    event.choose("BIRD")
    assert run.deck[0].id == "peck"


def test_wood_carvings_torus_transforms_basic_into_toric_toughness():
    run = fresh_run(13)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("wood_carvings", run).begin()
    event.choose("TORUS")
    assert run.deck[0].id == "toric_toughness"


def test_wood_carvings_snake_attaches_slither():
    run = fresh_run(13)
    target = run.deck[0]
    run.card_selector = pick(target)
    event = make_event("wood_carvings", run).begin()
    event.choose("SNAKE")
    assert isinstance(target.enchantment, SlitherEnchantment)


def test_wood_carvings_snake_locked_when_nothing_enchantable():
    # A deck of curses (unenchantable) plus a Basic card keeps the event
    # allowed but locks the Snake option.
    deck = [make_card("strike"), make_card("guilty"), make_card("poor_sleep")]
    strike = deck[0]
    run = fresh_run(13, deck=deck)
    SlitherEnchantment().attach(strike)  # the one candidate is taken
    event = make_event("wood_carvings", run).begin()
    assert event.option_keys() == ["BIRD", "SNAKE_LOCKED", "TORUS"]
    assert not event.choose("SNAKE_LOCKED")


# ── Enchantments and event cards in combat ─────────────────────────────────


def test_slither_randomizes_cost_when_drawn():
    bludgeon = make_card("bludgeon")  # cost 3
    SlitherEnchantment().attach(bludgeon)
    deck = [bludgeon] + [make_card("defend") for _ in range(4)]
    combat = CombatState(starting_deck=deck, rng=random.Random(0))
    assert bludgeon in combat.player.hand  # 5-card deck: everything is drawn
    assert 0 <= bludgeon.energy_cost <= 3
    # The override lasts the combat but not the next one.
    bludgeon.reset_combat_state()
    assert bludgeon.energy_cost == 3


def test_peck_hits_three_times():
    deck = [make_card("peck") for _ in range(5)]
    combat = CombatState(starting_deck=deck, rng=random.Random(0))
    enemy = combat.enemy
    hp_before = enemy.hp
    combat.play_card(0)
    assert enemy.hp == hp_before - 6  # 2 damage x 3 hits
    peck = make_card("peck")
    peck.upgrade()
    assert peck._hits == 4  # upgrade adds a hit


def test_toric_toughness_reblocks_after_clear():
    deck = [make_card("toric_toughness") for _ in range(5)]
    combat = CombatState(starting_deck=deck, rng=random.Random(0))
    combat.play_card(0)
    assert combat.player.block == 5
    power = combat.player.powers["toric_toughness"]
    assert power.amount == 2 and power.block == 5
    combat.end_turn()
    if not combat.is_over:
        # Block was cleared at turn start, then the power re-granted 5.
        assert combat.player.block == 5
        assert combat.player.powers["toric_toughness"].amount == 1
        combat.end_turn()
        if not combat.is_over:
            assert combat.player.block == 5
            assert "toric_toughness" not in combat.player.powers


# ── Full-pool smoke test ───────────────────────────────────────────────────


def test_every_event_every_option_runs_headlessly():
    """Drive every option (and every reachable page) of every event with a
    random selector, on a run that satisfies all gates."""
    for event_id in OVERGROWTH_EVENTS:
        cls = ALL_EVENTS[event_id]
        for first_choice in range(3):
            run = RunState(rng=random.Random(100 + first_choice), gold=500)
            run.lose_hp(40)  # satisfies Unrest Site's 70% gate
            assert cls.is_allowed(run), event_id
            event = make_event(event_id, run).begin()
            if first_choice >= len(event.options):
                continue
            guard = 0
            choice = first_choice
            while not event.finished and guard < 10:
                unlocked = [
                    i for i, o in enumerate(event.options) if not o.locked
                ]
                if not unlocked:
                    break
                idx = choice if choice in unlocked else unlocked[0]
                assert event.choose(idx)
                choice = 0
                guard += 1
            assert event.finished or guard == 10, event_id
