"""Neow (events/neow.py), the Ancient relic pool (relics/neow_relics.py), and
run/act sequencing (RunState.start_run/advance_act) vs the source:
Neow.cs, the 28 relic files in src/Core/Models/Relics, ActModel.cs."""
import random

import pytest

from sts2_rl.cards import CardRarity, make_card
from sts2_rl.combat import CombatState
from sts2_rl.events import make_event
from sts2_rl.events.neow import (
    CURSE_RELICS,
    POSITIVE_RELICS,
    neow_relic_pool,
)
from sts2_rl.monsters.overgrowth import ENCOUNTERS
from sts2_rl.relics import ALL_RELICS, make_relic
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


def neow_options(seed):
    run = fresh_run(seed)
    event = make_event("neow", run).begin()
    return run, event


# ═════════════════════════════════════════════════════════════════════════
# The Neow event
# ═════════════════════════════════════════════════════════════════════════

def test_neow_offers_two_positives_and_one_curse():
    for seed in range(40):
        _, event = neow_options(seed)
        keys = event.option_keys()
        assert len(keys) == 3
        assert keys[2] in CURSE_RELICS
        for key in keys[:2]:
            assert key not in CURSE_RELICS
            assert key in neow_relic_pool(fresh_run(0))


def test_neow_never_offers_sim_disallowed_relics():
    # Kaleidoscope (needs other characters' pools) and Massive Scroll
    # (multiplayer-only) mirror IsAllowedAtNeow == false here.
    for seed in range(60):
        _, event = neow_options(seed)
        assert "kaleidoscope" not in event.option_keys()
        assert "massive_scroll" not in event.option_keys()
    assert not ALL_RELICS["kaleidoscope"].is_allowed_at_neow
    assert not ALL_RELICS["massive_scroll"].is_allowed_at_neow


def test_neow_mutual_exclusions():
    pairs = {
        "cursed_pearl": "golden_pearl",
        "hefty_tablet": "arcane_scroll",
        "leafy_poultice": "new_leaf",
        "precarious_shears": "precise_scissors",
    }
    seen_curses = set()
    for seed in range(300):
        _, event = neow_options(seed)
        keys = event.option_keys()
        curse = keys[2]
        seen_curses.add(curse)
        if curse in pairs:
            assert pairs[curse] not in keys[:2]
    assert seen_curses == set(CURSE_RELICS)  # every curse can roll


def test_neow_choice_grants_relic_and_finishes():
    run, event = neow_options(3)
    key = event.option_keys()[0]
    assert event.choose(0)
    assert event.finished
    assert any(r.id == key for r in run.relics)


def test_neow_option_lists_match_source():
    assert len(POSITIVE_RELICS) == 14
    assert len(CURSE_RELICS) == 8
    # AllPossibleOptions = 8 curses + 14 positives + the 6 coin-flip relics,
    # minus the 2 sim-disallowed ones.
    assert len(neow_relic_pool(fresh_run(0))) == 8 + 14 + 6 - 2


# ═════════════════════════════════════════════════════════════════════════
# Pickup effects (AfterObtained)
# ═════════════════════════════════════════════════════════════════════════

def test_golden_pearl_and_nutritious_oyster():
    run = fresh_run(1)
    run.add_relic("golden_pearl")
    assert run.gold == 99 + 150
    run.add_relic("nutritious_oyster")
    assert run.max_hp == 91 and run.hp == 91


def test_cursed_pearl():
    run = fresh_run(1)
    run.add_relic("cursed_pearl")
    assert run.gold == 99 + 333
    assert any(c.id == "greed" for c in run.deck)


def test_neows_torment_adds_neows_fury():
    run = fresh_run(1)
    run.add_relic("neows_torment")
    assert any(c.id == "neows_fury" for c in run.deck)


def test_arcane_scroll_adds_unupgraded_rare():
    for seed in range(10):
        run = fresh_run(seed)
        run.add_relic("arcane_scroll")
        added = run.deck[-1]
        assert added.rarity == CardRarity.RARE
        assert added.upgrade_level == 0


def test_scroll_boxes_bundle():
    run = fresh_run(2)
    before = len(run.deck)
    run.add_relic("scroll_boxes")
    added = run.deck[before:]
    assert len(added) == 3
    rarities = sorted(c.rarity.value for c in added)
    assert rarities == ["common", "common", "uncommon"]
    assert len({c.id for c in added}) == 3


def test_phial_holster():
    run = fresh_run(3)
    run.add_relic("phial_holster")
    assert run.max_potions == 4
    assert len(run.potions) == 2
    assert len({p.id for p in run.potions}) == 2   # distinct


def test_large_capsule():
    run = fresh_run(4)
    before_deck = len(run.deck)
    run.add_relic("large_capsule")
    ids = [r.id for r in run.relics]
    assert len(ids) == 3  # the capsule + 2 grab-bag pulls
    added = run.deck[before_deck:]
    assert sorted(c.id for c in added) == ["defend", "strike"]


def test_leafy_poultice():
    run = fresh_run(5)
    run.add_relic("leafy_poultice")
    assert run.max_hp == 68 and run.hp == 68
    # One basic Strike and one basic Defend transformed away.
    assert sum(1 for c in run.deck if c.id == "strike") == 4
    assert sum(1 for c in run.deck if c.id == "defend") == 3
    assert len(run.deck) == 10


def test_precarious_shears():
    run = fresh_run(6)
    run.add_relic("precarious_shears")
    assert len(run.deck) == 8
    assert run.hp == 80 - 16


def test_precise_scissors_and_pomander():
    run = fresh_run(7)
    run.add_relic("precise_scissors")
    assert len(run.deck) == 9
    run.add_relic("pomander")
    assert sum(1 for c in run.deck if c.upgrade_level > 0) == 1


def test_neows_talisman_upgrades_last_strike_and_defend():
    run = fresh_run(8)
    run.add_relic("neows_talisman")
    strikes = [c for c in run.deck if c.id == "strike"]
    defends = [c for c in run.deck if c.id == "defend"]
    assert [c.upgrade_level for c in strikes] == [0, 0, 0, 0, 1]
    assert [c.upgrade_level for c in defends] == [0, 0, 0, 1]


def test_silken_tress_takes_all_gold_and_enchants_first_reward():
    run = fresh_run(9)
    run.add_relic("silken_tress")
    assert run.gold == 0
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    assert all(
        c.enchantment is not None and c.enchantment.id == "glam"
        for c in rewards.cards
    )
    # One-shot: the next reward is untouched.
    rewards2 = run.generate_combat_rewards(RoomType.MONSTER)
    assert all(c.enchantment is None for c in rewards2.cards)


def test_hefty_tablet():
    run = fresh_run(10)
    before = len(run.deck)
    run.add_relic("hefty_tablet")
    added = run.deck[before:]
    assert any(c.id == "injury" for c in added)
    picked = [c for c in added if c.id != "injury"]
    assert len(picked) == 1 and picked[0].rarity == CardRarity.RARE


def test_lost_coffer():
    run = fresh_run(11)
    before = len(run.deck)
    run.add_relic("lost_coffer")
    assert len(run.deck) == before + 1   # one card kept from the choice
    assert len(run.potions) == 1


def test_neows_bones():
    run = fresh_run(12)
    before = len(run.deck)
    run.add_relic("neows_bones")
    ids = [r.id for r in run.relics]
    assert len(ids) == 3                       # bones + 2 pool relics
    assert "neows_bones" in ids
    assert all(rid in neow_relic_pool(run) or rid == "neows_bones"
               for rid in ids if rid != "neows_bones" or True)
    curses = [c for c in run.deck[before:] if c.card_type.value == "curse"]
    assert len(curses) >= 1                    # plus a random curse


def test_lead_paperweight_fallback_pool_card():
    run = fresh_run(13)
    before = len(run.deck)
    run.add_relic("lead_paperweight")
    assert len(run.deck) == before + 1


# ═════════════════════════════════════════════════════════════════════════
# Hook-driven relics
# ═════════════════════════════════════════════════════════════════════════

def test_stone_humidifier_rest_heal():
    run = fresh_run(14)
    run.add_relic("stone_humidifier")
    run.hp = 40
    healed = run.rest_heal()
    assert healed == 24                        # 30% of 80
    assert run.max_hp == 85                    # +5 on heal
    run.rest_heal()
    assert run.max_hp == 90


def test_fishing_rod_every_third_monster_combat():
    run = fresh_run(15)
    run.add_relic("fishing_rod")
    enc = ENCOUNTERS["fuzzy_wurm_weak"]
    for i in range(1, 7):
        combat = run.create_combat(enc)
        run.finish_combat(combat, room_type=RoomType.MONSTER)
        upgraded = sum(1 for c in run.deck if c.upgrade_level > 0)
        assert upgraded == i // 3
    # Elite combats don't advance the counter.
    combat = run.create_combat(enc)
    run.finish_combat(combat, room_type=RoomType.ELITE)
    assert run.relics[0].combats_seen == 6


def test_winged_boots_free_travel():
    run = fresh_run(16)
    run.add_relic("winged_boots")
    boots = run.relics[0]
    run.start_act("overgrowth")
    used = 0
    while used < 3 and not run.at_act_end:
        children = set(run.current_point.children)
        options = run.travelable_points()
        free = [p for p in options if p not in children]
        assert set(options) >= children
        if free:
            run.enter_point(free[0])
            used += 1
            assert boots.times_used == used
        else:
            run.enter_point(options[0])
    assert boots.times_used == 3
    # Used up: back to children only.
    if not run.at_act_end:
        assert set(run.travelable_points()) == set(run.current_point.children)


def test_silver_crucible():
    run = fresh_run(17)
    run.add_relic("silver_crucible")
    crucible = run.relics[0]
    # First three card rewards arrive upgraded.
    for i in range(3):
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        assert all(
            c.upgrade_level > 0 for c in rewards.cards if c.is_upgradable or c.upgrade_level
        )
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    assert any(c.upgrade_level == 0 for c in rewards.cards)
    # First treasure room has no chest.
    crucible.treasure_rooms_entered = 1
    assert not crucible.should_generate_treasure(run)
    crucible.treasure_rooms_entered = 2
    assert crucible.should_generate_treasure(run)


def test_lava_rock_act1_boss_only_once():
    run = fresh_run(18)
    run.start_act("overgrowth", act_index=0)
    run.add_relic("lava_rock")
    rewards = run.generate_combat_rewards(RoomType.BOSS)
    assert len(rewards.relics) == 2            # the two extra pulls
    assert all(r in run.relics for r in rewards.relics)
    rewards2 = run.generate_combat_rewards(RoomType.BOSS)
    assert len(rewards2.relics) == 0           # one-shot


def test_booming_conch_elite_first_turn():
    conch = make_relic("booming_conch")
    combat = CombatState(
        rng=random.Random(0),
        encounter=ENCOUNTERS["fuzzy_wurm_weak"],
        relics=[conch],
        room_type=RoomType.ELITE,
    )
    assert len(combat.player.hand) == 7        # 5 + 2 on turn 1
    assert combat.player.energy == 4           # 3 + 1 on turn 1
    combat.end_turn()
    assert len(combat.player.hand) == 5
    assert combat.player.energy == 3


def test_booming_conch_inert_outside_elites():
    conch = make_relic("booming_conch")
    combat = CombatState(
        rng=random.Random(0),
        encounter=ENCOUNTERS["fuzzy_wurm_weak"],
        relics=[conch],
        room_type=RoomType.MONSTER,
    )
    assert len(combat.player.hand) == 5
    assert combat.player.energy == 3


def test_neows_fury_card():
    deck = [make_card("neows_fury")] + [make_card("strike") for _ in range(5)]
    combat = CombatState(
        starting_deck=deck,
        rng=random.Random(0),
        encounter=ENCOUNTERS["fuzzy_wurm_weak"],
    )
    fury = next(c for c in combat.player.hand if c.id == "neows_fury")
    enemy = combat.enemy
    hp_before = enemy.hp
    combat.player.discard_pile = [make_card("defend"), make_card("defend")]
    combat.play_card(combat.player.hand.index(fury))
    assert hp_before - enemy.hp == 10
    assert fury in combat.player.exhaust_pile  # Exhaust keyword
    assert len(combat.player.discard_pile) == 0  # both returned to hand


# ═════════════════════════════════════════════════════════════════════════
# Run / act sequencing
# ═════════════════════════════════════════════════════════════════════════

def test_start_run_rolls_act1_variant_over_full_arc():
    seen = set()
    for seed in range(20):
        run = fresh_run(seed)
        run.start_run()
        seen.add(run.act_list[0])
        # All acts are ported now, so the default is the full 1 → 2 → 3 arc.
        assert run.act_list[1:] == ["hive", "glory"]
        assert run.act_index == 0
    assert seen == {"overgrowth", "underdocks"}


def test_underdocks_is_an_act1(seed=0):
    # Fidelity correction: Underdocks.cs Index == 0 (the alternate Act 1),
    # not a parallel Act 2.
    run = fresh_run(seed)
    run.start_act("underdocks")
    assert run.act_index == 0


def test_advance_act_and_final_act_flags():
    run = fresh_run(1)
    run.start_run(acts=["overgrowth", "hive"])
    assert not run.is_final_act
    while not run.at_act_end:
        run.enter_point(run.rng.choice(run.travelable_points()))
    floor_after_act1 = run.total_floor
    assert floor_after_act1 > 0                # total_floor now auto-counts
    run.advance_act()
    assert run.act_config.name == "hive"
    assert run.act_index == 1 and run.is_final_act
    assert run.current_point is run.map.starting_point
    with pytest.raises(RuntimeError):
        run.advance_act()                      # already in the final act
    run.complete_run()
    assert run.victory and run.at_run_end


def test_is_final_act_walk_over_full_glory_arc():
    """A default full arc walked act-by-act: is_final_act is False through
    acts 1 and 2 and flips True only on Glory (the last act keys off
    len(act_list) - 1). Each advance_act carries no heal (RunManager.
    EnterNextAct) and stands back at the fresh Ancient."""
    run = fresh_run(3)
    run.start_run(acts=["overgrowth", "hive", "glory"])
    for idx, name in enumerate(["overgrowth", "hive", "glory"]):
        assert run.act_index == idx and run.act_config.name == name
        assert run.is_final_act == (name == "glory")
        assert run.current_point is run.map.starting_point
        if name == "glory":
            break
        while not run.at_act_end:
            run.enter_point(run.rng.choice(run.travelable_points()))
        hp_before = run.hp
        run.advance_act()
        assert run.hp == hp_before          # no heal on act transition
    assert run.is_final_act                 # ended on Glory
    with pytest.raises(RuntimeError):
        run.advance_act()                   # already in the final act
    assert run.generate_combat_rewards(RoomType.BOSS).is_empty


def test_final_act_boss_rewards_empty_via_start_run():
    run = fresh_run(2)
    run.start_run(acts=["overgrowth"])
    assert run.is_final_act
    assert run.generate_combat_rewards(RoomType.BOSS).is_empty


def test_start_run_requires_acts():
    with pytest.raises(ValueError):
        fresh_run(3).start_run(acts=[])
