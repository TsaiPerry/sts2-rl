"""Darv — the shared Ancient (Darv.cs) — its 12 relics, and the shared-ancient
partition RunManager.GenerateRooms performs across a run's acts. Plan:
docs/superpowers/plans/2026-07-19-shared-events.md."""
import random

from sts2_rl.cards import make_card
from sts2_rl.combat import CombatState
from sts2_rl.driver import SHARED_ANCIENTS, RunDriver
from sts2_rl.events import make_event
from sts2_rl.monsters.overgrowth import ENCOUNTERS
from sts2_rl.relics import make_relic
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState

WURM = ENCOUNTERS["fuzzy_wurm_weak"]

ALWAYS = {"astrolabe", "black_star", "calling_bell", "empty_cage",
          "pandoras_box", "runic_pyramid", "snecko_eye"}
ACT2_ONLY = {"ectoplasm", "sozu"}
ACT3_ONLY = {"philosophers_stone", "velvet_choker"}


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


def act_run(seed, acts, advances):
    run = fresh_run(seed)
    run.start_run(acts=acts)
    for _ in range(advances):
        run.advance_act()
    return run


def build(deck=None, seed=0, relics=()):
    return CombatState(
        starting_deck=deck, rng=random.Random(seed), encounter=WURM,
        relics=list(relics),
    )


# ═════════════════════════════════════════════════════════════════════════
# The shrine
# ═════════════════════════════════════════════════════════════════════════

def test_darv_always_offers_exactly_three():
    for seed in range(30):
        run = act_run(seed, ["overgrowth", "hive"], 1)
        assert len(make_event("darv", run).begin().option_keys()) == 3


def test_darv_act2_pool_excludes_act3_relics():
    seen = set()
    for seed in range(120):
        run = act_run(seed, ["overgrowth", "hive"], 1)
        seen |= set(make_event("darv", run).begin().option_keys())
    assert seen & ACT2_ONLY                 # the act-2 pair can appear
    assert not (seen & ACT3_ONLY)           # the act-3 pair never does
    assert ALWAYS <= seen                   # every always-set relic can roll
    assert "dusty_tome" in seen             # the coin-flip fourth


def test_darv_act3_pool_excludes_act2_relics():
    seen = set()
    for seed in range(120):
        run = act_run(seed, ["overgrowth", "hive", "glory"], 2)
        seen |= set(make_event("darv", run).begin().option_keys())
    assert seen & ACT3_ONLY
    assert not (seen & ACT2_ONLY)


def test_darv_choice_grants_the_relic():
    run = act_run(4, ["overgrowth", "hive"], 1)
    event = make_event("darv", run).begin()
    key = event.option_keys()[0]
    assert event.choose(0)
    assert event.finished
    assert any(r.id == key for r in run.relics)


def test_darv_heals_like_every_ancient():
    run = act_run(5, ["overgrowth", "hive"], 1)
    run.hp = 11
    make_event("darv", run).begin()
    assert run.hp == run.max_hp


# ═════════════════════════════════════════════════════════════════════════
# The shared-ancient partition (RunManager.GenerateRooms)
# ═════════════════════════════════════════════════════════════════════════

def test_shared_ancients_list_matches_source():
    assert SHARED_ANCIENTS == ("darv",)


def test_partition_gives_each_shared_ancient_to_at_most_one_act():
    for seed in range(40):
        run = fresh_run(seed)
        driver = RunDriver(run, lambda req: req.legal_actions()[0],
                           acts=["overgrowth", "hive", "glory"])
        run.start_run(acts=["overgrowth", "hive", "glory"])
        driver._roll_shared_ancients()
        subsets = driver._shared_ancient_subsets
        # Act 1 never gets a shared ancient (it always has Neow).
        assert "overgrowth" not in subsets
        allotted = [a for subset in subsets.values() for a in subset]
        assert len(allotted) == len(set(allotted))       # never duplicated
        assert set(allotted) <= set(SHARED_ANCIENTS)


def test_partition_sometimes_allots_darv_and_sometimes_not():
    got, missed = 0, 0
    for seed in range(40):
        run = fresh_run(seed)
        driver = RunDriver(run, lambda req: req.legal_actions()[0],
                           acts=["overgrowth", "hive"])
        run.start_run(acts=["overgrowth", "hive"])
        driver._roll_shared_ancients()
        if driver._shared_ancient_subsets.get("hive"):
            got += 1
        else:
            missed += 1
    assert got and missed          # both outcomes occur


DARV_RELICS = ALWAYS | ACT2_ONLY | ACT3_ONLY | {"dusty_tome"}


def test_darv_can_actually_fire_as_an_act_shrine():
    """The allotted act rolls its shrine from its own pool ∪ the subset, so
    Darv must be reachable through _maybe_run_ancient. Identified by the
    relic granted — driver-fired ancients don't record in visited_event_ids
    (they aren't event-queue rooms), same as Neow and the act shrines."""
    fired = 0
    for seed in range(60):
        run = fresh_run(seed)
        driver = RunDriver(run, lambda req: req.legal_actions()[0],
                           acts=["overgrowth", "hive"])
        run.start_run(acts=["overgrowth", "hive"])
        driver._roll_shared_ancients()
        run.advance_act()
        driver._maybe_run_ancient()
        if {r.id for r in run.relics} & DARV_RELICS:
            fired += 1
    assert fired          # ~12%: half the runs are allotted Darv, then it
                          # competes with Hive's own three shrines


# ═════════════════════════════════════════════════════════════════════════
# The relics
# ═════════════════════════════════════════════════════════════════════════

def test_astrolabe_transforms_three_and_upgrades_them():
    run = fresh_run(6)
    before = {id(c) for c in run.deck}
    run.add_relic("astrolabe")
    replaced = [c for c in run.deck if id(c) not in before]
    assert len(replaced) == 3
    assert all(c.upgrade_level == 1 for c in replaced)
    assert len(run.deck) == 10          # size unchanged


def test_empty_cage_removes_two():
    run = fresh_run(7)
    before = len(run.deck)
    run.add_relic("empty_cage")
    assert len(run.deck) == before - 2


def test_calling_bell_gives_curse_and_three_relics():
    run = fresh_run(8)
    run.add_relic("calling_bell")
    assert [c for c in run.deck if c.id == "curse_of_the_bell"]
    ids = {r.id for r in run.relics}
    assert {"anchor", "gremlin_horn", "mummified_hand"} <= ids


def test_pandoras_box_transforms_every_basic_strike_and_defend():
    run = fresh_run(9)
    run.add_relic("pandoras_box")
    # Starter deck is 5 Strike + 4 Defend + Bash; only Bash survives.
    assert not [c for c in run.deck if c.id in ("strike", "defend")]
    assert [c for c in run.deck if c.id == "bash"]
    assert len(run.deck) == 10


def test_black_star_adds_a_relic_to_elite_rewards_only():
    run = fresh_run(10)
    star = make_relic("black_star")
    run.add_relic(star)
    from sts2_rl.rewards import CombatRewards

    monster = CombatRewards(room_type=RoomType.MONSTER)
    star.modify_combat_rewards(run, monster)
    assert monster.relics == []

    elite = CombatRewards(room_type=RoomType.ELITE)
    star.modify_combat_rewards(run, elite)
    assert len(elite.relics) == 1


def test_runic_pyramid_keeps_the_hand():
    combat = build(deck=[make_card("strike") for _ in range(8)], seed=1,
                   relics=[make_relic("runic_pyramid")])
    held = list(combat.player.hand)
    assert held
    combat.end_turn()
    for card in held:
        assert card in combat.player.hand      # never discarded


def test_snecko_eye_draws_more_and_randomises_costs():
    plain = build(deck=[make_card("strike") for _ in range(12)], seed=2)
    snecko = build(deck=[make_card("strike") for _ in range(12)], seed=2,
                   relics=[make_relic("snecko_eye")])
    assert len(snecko.player.hand) == len(plain.player.hand) + 2
    assert "confused" in snecko.player.powers
    # Strike costs 1; Confused rerolls every draw into 0..3.
    costs = {c.energy_cost for c in snecko.player.hand}
    assert costs <= {0, 1, 2, 3}
    assert len(costs) > 1          # genuinely randomised, not all 1


def test_ectoplasm_gives_energy_but_no_gold():
    run = fresh_run(11)
    run.add_relic("ectoplasm")
    gold = run.gold
    run.gain_gold(100)
    assert run.gold == gold                       # ModifyGoldGained -> 0
    combat = build(seed=3, relics=[make_relic("ectoplasm")])
    assert combat.player.energy == 4              # 3 + 1


def test_sozu_gives_energy_but_refuses_potions():
    from sts2_rl.potions import make_potion

    run = fresh_run(12)
    run.add_relic("sozu")
    assert not run.add_potion(make_potion("fire_potion"))
    assert run.potions == []
    combat = build(seed=4, relics=[make_relic("sozu")])
    assert combat.player.energy == 4


def test_philosophers_stone_gives_energy_and_arms_enemies():
    combat = build(seed=5, relics=[make_relic("philosophers_stone")])
    assert combat.player.energy == 4
    assert combat.enemy.strength == 1


def play_until_blocked(combat, limit=12):
    """Play card 0 until the engine refuses, topping the hand up from the
    draw pile (a 5-card hand can't reach Velvet Choker's 6-card cap)."""
    from sts2_rl.cmds import DrawCmd

    played = 0
    while played < limit:
        if not combat.player.hand:
            DrawCmd.draw(combat.player, 3)
            if not combat.player.hand:
                break
        if not combat.play_card(0):
            break
        played += 1
    return played


def test_velvet_choker_gives_energy_and_caps_plays():
    combat = build(deck=[make_card("strike") for _ in range(20)], seed=6,
                   relics=[make_relic("velvet_choker")])
    assert combat.player.energy == 4
    combat.player.energy = 99
    assert play_until_blocked(combat) == 6      # CARDS_PER_TURN


def test_velvet_choker_resets_each_turn():
    choker = make_relic("velvet_choker")
    combat = build(deck=[make_card("strike") for _ in range(20)], seed=7,
                   relics=[choker])
    combat.player.energy = 99
    play_until_blocked(combat)
    assert choker.cards_played_this_turn == 6
    combat.end_turn()
    assert choker.cards_played_this_turn == 0


def test_dusty_tome_adds_an_upgraded_ancient_card():
    run = fresh_run(13)
    tome = make_relic("dusty_tome")
    tome.setup_for_player(run)
    assert tome.ancient_card in tome.candidates()
    run.add_relic(tome)
    added = [c for c in run.deck if c.id == tome.ancient_card]
    assert len(added) == 1
    assert added[0].upgrade_level == 1


def test_dusty_tome_excludes_transcendence_cards():
    # Break is Bash's transcendence upgrade (Archaic Tooth), so it is never
    # the Dusty Tome's card.
    assert "break" not in make_relic("dusty_tome").candidates()
