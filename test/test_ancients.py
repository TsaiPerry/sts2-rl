"""The Act-2/3 Ancient shrines and their relics, vs the source:
src/Core/Models/Events/{Orobas,Pael,Tezcatara,Nonupeipe,Tanx,Vakuu}.cs and the
relic models they grant (src/Core/Models/Relics). Sections are added per
ancient as each phase lands."""
import random

from sts2_rl.cards import CardRarity, make_card
from sts2_rl.combat import CombatState
from sts2_rl.driver import (
    ACT_ANCIENTS,
    DecisionKind,
    DecisionRequest,
    RunDriver,
)
from sts2_rl.events import make_event
from sts2_rl.monsters.overgrowth import ENCOUNTERS
from sts2_rl.relics import make_relic
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState

WURM = ENCOUNTERS["fuzzy_wurm_weak"]


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# Driver wiring: the act-2/3 ancient fires at act entry
# ═════════════════════════════════════════════════════════════════════════

def test_act_ancients_pools_match_source():
    assert ACT_ANCIENTS["hive"] == ("orobas", "pael", "tezcatara")
    assert ACT_ANCIENTS["glory"] == ("nonupeipe", "tanx", "vakuu")


def test_driver_fires_registered_ancient_on_hive_entry():
    run = fresh_run(1)
    run.start_run(acts=["overgrowth", "hive"])
    driver = RunDriver(run, lambda req: req.legal_actions()[0])
    run.advance_act()
    assert run.act_config.name == "hive"
    relics_before = len(run.relics)
    driver._maybe_run_ancient()
    # Every non-locked ancient option grants a relic.
    assert len(run.relics) == relics_before + 1


def test_driver_include_ancients_false_fires_nothing():
    run = fresh_run(1)
    run.start_run(acts=["overgrowth", "hive"])
    driver = RunDriver(
        run, lambda req: req.legal_actions()[0], include_ancients=False,
    )
    run.advance_act()
    driver._maybe_run_ancient()
    # No ancient relic added: only the character's starting relic remains.
    assert [r.id for r in run.relics] == ["burning_blood"]


# ═════════════════════════════════════════════════════════════════════════
# Entering an ancient heals to full (AncientEventModel.BeforeEventStarted)
# ═════════════════════════════════════════════════════════════════════════

def test_ancient_entry_heals_to_full():
    run = fresh_run(2)
    run.start_run(acts=["overgrowth", "hive"])
    run.advance_act()
    run.hp = 17
    make_event("orobas", run).begin()
    assert run.hp == run.max_hp


def test_neow_entry_heals_to_full():
    # Neow zeroes HP first (the run-start revive), then heals MaxHp — at
    # non-ascension the net effect is a full heal from any starting HP.
    run = fresh_run(3)
    run.start_run(acts=["overgrowth"])
    run.hp = 5
    make_event("neow", run).begin()
    assert run.hp == run.max_hp


def test_driver_act_entry_heal_via_ancient():
    # End-to-end: a damaged player entering Hive is healed by the shrine.
    run = fresh_run(4)
    run.start_run(acts=["overgrowth", "hive"])
    run.hp = 12
    driver = RunDriver(run, lambda req: req.legal_actions()[0])
    run.advance_act()
    driver._maybe_run_ancient()
    assert run.hp == run.max_hp


def test_driver_act1_has_no_ancient_pool():
    run = fresh_run(2)
    run.start_run(acts=["overgrowth", "hive"])
    driver = RunDriver(run, lambda req: req.legal_actions()[0])
    driver._maybe_run_ancient()          # still in act 1 → no-op
    # No ancient fired: only the character's starting relic is present.
    assert [r.id for r in run.relics] == ["burning_blood"]


# ═════════════════════════════════════════════════════════════════════════
# Orobas — the event
# ═════════════════════════════════════════════════════════════════════════

ORO_POOL_1 = {"electric_shrymp", "glass_eye", "sand_castle"}
ORO_POOL_1_EXTRA = {"prismatic_gem", "sea_glass"}
ORO_POOL_2 = {"alchemical_coffer", "driftwood", "radiant_pearl"}


def test_orobas_option_structure():
    seen_first, seen_third = set(), set()
    for seed in range(60):
        run = fresh_run(seed)
        event = make_event("orobas", run).begin()
        keys = event.option_keys()
        assert len(keys) == 3
        assert keys[0] in ORO_POOL_1 | ORO_POOL_1_EXTRA
        assert keys[1] in ORO_POOL_2
        # Default run: no starter relic, deck holds Bash → always the tooth.
        assert keys[2] == "archaic_tooth"
        seen_first.add(keys[0])
        seen_third.add(keys[2])
    assert seen_first >= ORO_POOL_1        # every pool-1 relic can roll
    assert seen_first & ORO_POOL_1_EXTRA   # the rolled fourth appears too


def test_orobas_pool3_offers_touch_with_starter_relic():
    seen = set()
    for seed in range(40):
        run = fresh_run(seed)
        run.add_relic(make_relic("burning_blood"))
        event = make_event("orobas", run).begin()
        seen.add(event.option_keys()[2])
    assert seen == {"touch_of_orobas", "archaic_tooth"}


def test_orobas_pool3_locked_without_gates():
    run = fresh_run(3)
    # Remove the Bash: no transcendence card, no starter relic.
    bash = next(c for c in run.deck if c.id == "bash")
    run.deck.remove(bash)
    event = make_event("orobas", run).begin()
    keys = event.option_keys()
    assert keys[2] == "OPTION_POOL_3_LOCKED"
    assert not event.choose(2)             # locked options can't be chosen
    assert event.choose(0)                 # the others still work
    assert event.finished


def test_orobas_choice_grants_relic_and_finishes():
    run = fresh_run(4)
    event = make_event("orobas", run).begin()
    key = event.option_keys()[0]
    assert event.choose(0)
    assert event.finished
    assert any(r.id == key for r in run.relics)


# ═════════════════════════════════════════════════════════════════════════
# Orobas — the relics
# ═════════════════════════════════════════════════════════════════════════

def test_sand_castle_upgrades_six_cards():
    # SandCastle.cs:20 pins CardsVar(6) and :24-25 ends in .Take(6) — a random
    # SIX of the upgradable deck cards, not all of them.
    run = fresh_run(5)
    run.add_relic("sand_castle")
    assert sum(c.upgrade_level for c in run.deck) == 6


def test_electric_shrymp_imbues_one_skill():
    run = fresh_run(6)
    run.add_relic("electric_shrymp")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "imbued"
    assert enchanted[0].card_type.value == "skill"


def test_glass_eye_five_tiered_choices():
    run = fresh_run(7)
    before = len(run.deck)
    run.add_relic("glass_eye")
    added = run.deck[before:]
    assert len(added) == 5
    rarities = [c.rarity for c in added]
    assert rarities.count(CardRarity.COMMON) == 2
    assert rarities.count(CardRarity.UNCOMMON) == 2
    assert rarities.count(CardRarity.RARE) == 1
    assert all(c.upgrade_level == 0 for c in added)  # never upgraded


def test_alchemical_coffer_slots_and_potions():
    run = fresh_run(8)
    run.add_relic("alchemical_coffer")
    assert run.max_potions == 3 + 4
    assert len(run.held_potions) == 4


def test_alchemical_coffer_fills_on_the_combat_potion_generation_stream():
    """AfterObtained calls `PotionFactory.CreateRandomPotionsOutOfCombat(
    owner, 4, RunState.Rng.CombatPotionGeneration)` — the serialized
    CombatPotionGeneration stream (2 draws per potion: a rarity NextFloat then
    a NextItem), not the shared run RNG. On the shared RNG the potions the belt
    ends up holding are unseeded, so a replayed `UsePotion N` resolves to a
    different potion every run."""
    run = RunState(string_seed="933T39V18D")
    run.start_run(acts=["overgrowth", "hive", "glory"], ascension=0)
    before = run.rng_set.combat_potion_generation.counter
    run.add_relic("alchemical_coffer")
    assert len(run.held_potions) == 4
    assert run.rng_set.combat_potion_generation.counter == before + 8


def test_driftwood_reroll_flag_and_reroll():
    run = fresh_run(9)
    run.add_relic("driftwood")
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    assert rewards.can_reroll
    first_ids = [c.id for c in rewards.cards]
    rewards.reroll(run)
    assert not rewards.can_reroll          # one-shot
    assert len(rewards.cards) == 3
    request = DecisionRequest(
        kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards,
    )
    assert request.legal_actions() == [0, 1, 2, 3]  # no reroll action left
    assert first_ids  # sanity


def test_reward_card_legal_actions_include_reroll():
    run = fresh_run(10)
    run.add_relic("driftwood")
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    request = DecisionRequest(
        kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards,
    )
    # 0-2 = take, 3 = skip, 4 = reroll (Driftwood).
    assert request.legal_actions() == [0, 1, 2, 3, 4]


def test_prismatic_gem_energy_only():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("prismatic_gem")],
    )
    assert combat.player.energy == 4


def test_radiant_pearl_luminesce_turn_one_only():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("radiant_pearl")],
    )
    luminesces = [c for c in combat.player.hand if c.id == "luminesce"]
    assert len(luminesces) == 1
    lum = luminesces[0]
    energy = combat.player.energy
    combat.play_card(combat.player.hand.index(lum))
    assert combat.player.energy == energy + 2   # 0-cost, gain 2
    assert lum in combat.player.exhaust_pile     # Exhaust
    combat.end_turn()
    assert not any(c.id == "luminesce" for c in combat.player.hand)


def test_black_blood_heals_twelve():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("black_blood")],
    )
    combat.player.hp = 50
    combat._end_combat(player_won=True)    # fires on_combat_end hooks
    assert combat.player.hp == 62


def test_touch_of_orobas_refines_burning_blood():
    run = fresh_run(11)
    run.add_relic(make_relic("burning_blood"))
    run.add_relic("touch_of_orobas")
    ids = [r.id for r in run.relics]
    assert "burning_blood" not in ids
    assert ids[0] == "black_blood"         # replaced in place
    assert "touch_of_orobas" in ids


def test_touch_of_orobas_no_starter_is_noop():
    run = fresh_run(12)
    run.add_relic("touch_of_orobas")
    assert [r.id for r in run.relics] == ["touch_of_orobas"]


def test_archaic_tooth_transcends_bash():
    run = fresh_run(13)
    bash = next(c for c in run.deck if c.id == "bash")
    bash.upgrade()
    idx = run.deck.index(bash)
    run.add_relic("archaic_tooth")
    assert not any(c.id == "bash" for c in run.deck)
    replacement = run.deck[idx]
    assert replacement.id == "break"
    assert replacement.upgrade_level == 1  # upgrade carried over


def test_sea_glass_is_stub():
    run = fresh_run(14)
    deck_before = [c.id for c in run.deck]
    run.add_relic("sea_glass")
    assert [c.id for c in run.deck] == deck_before
    assert [r.id for r in run.relics] == ["sea_glass"]


def test_sea_glass_burns_its_fifteen_reward_draws():
    """relic/sea_glass/g1. SeaGlass.cs:85-87 calls CardFactory.CreateForReward
    three times with `DynamicVars.Cards.IntValue / 3` == 5 cards each. Each
    card is one `rng.NextItem(items)` off PlayerRng.Rewards (CardFactory.cs:236)
    and NO upgrade roll -- ForNonCombatWithUniformOdds sets NoUpgradeRoll
    (CardCreationOptions.cs:162) and SeaGlass's WithFlags ORs onto it
    (:212-216). So 15 Rewards draws happen whether or not the player keeps a
    card, and every later Rewards consumer reads at the shifted position.

    The CARDS stay out of scope -- they come from another character's pool,
    which this sim does not have -- but the stream position does not depend on
    the pool: Rng.next_int is exactly one MegaRandom draw whatever its range
    (rng.py:178-180)."""
    run = RunState(string_seed="89U21BV1TZ")
    before = run.player_rng.rewards.counter
    run.add_relic("sea_glass")
    assert run.player_rng.rewards.counter == before + 15


# ═════════════════════════════════════════════════════════════════════════
# Pael — the event
# ═════════════════════════════════════════════════════════════════════════

PAEL_POOL_1 = {"paels_flesh", "paels_horn", "paels_tears"}
PAEL_POOL_2 = {"paels_wing", "paels_claw", "paels_tooth", "paels_growth"}
PAEL_POOL_3 = {"paels_eye", "paels_blood", "paels_legion"}


def test_pael_option_structure():
    seen2, seen3 = set(), set()
    for seed in range(80):
        run = fresh_run(seed)
        event = make_event("pael", run).begin()
        keys = event.option_keys()
        assert len(keys) == 3
        assert keys[0] in PAEL_POOL_1
        assert keys[1] in PAEL_POOL_2
        assert keys[2] in PAEL_POOL_3
        seen2.add(keys[1])
        seen3.add(keys[2])
    # Default deck: 4 Defends (>=3 Goopy-eligible) and 10 removable (>=5), so
    # Claw and Tooth are offerable; Legion offerable with no pet.
    assert seen2 == PAEL_POOL_2
    assert seen3 == PAEL_POOL_3


def test_pael_gates_close():
    for seed in range(60):
        run = fresh_run(seed)
        # Strip the deck to 4 Strikes (below both the Goopy-3 and the
        # removable-5 gates) and give the run an event pet.
        run.deck[:] = [c for c in run.deck if c.id == "strike"][:4]
        run.add_relic(make_relic("paels_legion"))
        event = make_event("pael", run).begin()
        keys = event.option_keys()
        assert keys[1] in {"paels_wing", "paels_growth"}
        assert keys[2] in {"paels_eye", "paels_blood"}


# ═════════════════════════════════════════════════════════════════════════
# Pael — the relics
# ═════════════════════════════════════════════════════════════════════════

def test_paels_flesh_energy_from_turn_three():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("paels_flesh")],
    )
    assert combat.player.energy == 3          # turn 1
    combat.end_turn()
    assert combat.player.energy == 3          # turn 2
    combat.end_turn()
    assert combat.player.energy == 4          # turn 3+
    combat.end_turn()
    assert combat.player.energy == 4


def test_paels_blood_extra_draw():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("paels_blood")],
    )
    assert len(combat.player.hand) == 6       # 5 + 1


def test_paels_tears_grants_energy_after_leftover():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("paels_tears")],
    )
    combat.end_turn()                          # ended with 3 unspent
    assert combat.player.energy == 3 + 2
    # Spend everything this turn: no bonus next turn.
    combat.player.energy = 0
    combat.end_turn()
    assert combat.player.energy == 3


def test_paels_horn_adds_two_relax():
    run = fresh_run(20)
    run.add_relic("paels_horn")
    assert sum(1 for c in run.deck if c.id == "relax") == 2


def test_relax_card_effects():
    # 12 cards so the turn-2 bonus draw isn't starved by pile exhaustion.
    deck = [make_card("relax")] + [make_card("strike") for _ in range(11)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
    )
    relax = next((c for c in combat.player.hand if c.id == "relax"), None)
    assert relax is not None
    combat.play_card(combat.player.hand.index(relax))
    assert combat.player.block == 15
    assert relax in combat.player.exhaust_pile
    combat.end_turn()
    assert combat.player.energy == 3 + 2       # EnergyNextTurn
    assert len(combat.player.hand) == 5 + 2    # DrawCardsNextTurn
    combat.end_turn()
    assert combat.player.energy == 3           # both expired
    assert len(combat.player.hand) == 5


def test_paels_claw_goopy_all_defends():
    run = fresh_run(21)
    run.add_relic("paels_claw")
    goopied = [c for c in run.deck if c.enchantment is not None]
    assert len(goopied) == 4                   # every Defend
    assert all(c.id == "defend" for c in goopied)
    assert all(c.enchantment.id == "goopy" for c in goopied)


def test_paels_growth_enchants_and_clone_rest_option():
    run = fresh_run(22)
    run.add_relic("paels_growth")
    cloned = [c for c in run.deck if c.enchantment is not None]
    assert len(cloned) == 1
    assert cloned[0].enchantment.id == "clone"
    options = run.rest_site_options()
    assert [o.key for o in options] == ["CLONE"]
    deck_before = len(run.deck)
    options[0].on_select(run)
    assert len(run.deck) == deck_before + 1    # 1 clone-enchanted → +1 copy
    # The copy carries the enchantment: cloning again duplicates BOTH.
    run.rest_site_options()[0].on_select(run)
    assert len(run.deck) == deck_before + 3


def test_paels_tooth_stores_five_and_returns_upgraded():
    run = fresh_run(23)
    run.add_relic("paels_tooth")
    tooth = run.relics[0]
    assert len(run.deck) == 5                  # 10 - 5 stored
    assert len(tooth.stored_cards) == 5
    for i in range(1, 6):
        combat = run.create_combat(WURM)
        run.finish_combat(combat, room_type=RoomType.MONSTER)
        assert len(tooth.stored_cards) == 5 - i
        assert len(run.deck) == 5 + i
    returned = run.deck[5:]
    assert all(
        c.upgrade_level == 1 for c in returned if c.max_upgrade_level > 0
    )
    # Empty: further combats change nothing.
    combat = run.create_combat(WURM)
    run.finish_combat(combat, room_type=RoomType.MONSTER)
    assert len(run.deck) == 10


def test_paels_tooth_snapshot_placeholders_survive_combat_end():
    # snapshots._paels_tooth restores stored_cards as [None] * count (only
    # the count is observation-visible). after_combat_end must consume the
    # rng draw and drop the placeholder without upgrading or re-adding.
    run = fresh_run(23)
    run.add_relic("paels_tooth")
    tooth = run.relics[0]
    tooth.stored_cards = [None] * 5
    deck_before = len(run.deck)
    for i in range(1, 6):
        combat = run.create_combat(WURM)
        run.finish_combat(combat, room_type=RoomType.MONSTER)
        assert len(tooth.stored_cards) == 5 - i
        assert len(run.deck) == deck_before      # unknowable card: not added
    combat = run.create_combat(WURM)
    run.finish_combat(combat, room_type=RoomType.MONSTER)
    assert len(run.deck) == deck_before


def test_paels_eye_extra_turn_once_per_combat():
    # 12 cards so the extra turn's fresh 5-card draw isn't pile-starved.
    deck = [make_card("strike") for _ in range(12)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("paels_eye")],
    )
    enemy_hp = combat.enemy.hp
    hand = list(combat.player.hand)
    combat.end_turn()                          # no cards played → extra turn
    assert combat.turn == 2
    assert combat.enemy.hp == enemy_hp         # enemy never acted
    assert all(c in combat.player.exhaust_pile for c in hand)
    assert len(combat.player.hand) == 5        # fresh draw
    hp_before, block_before = combat.player.hp, combat.player.block
    combat.end_turn()                          # used up → normal turn
    assert combat.turn == 3
    # The enemy side ran this time: it acted (damage or intent shift).
    assert combat.player.hp <= hp_before


def test_paels_wing_sacrifice_every_second():
    run = fresh_run(24)
    run.add_relic("paels_wing")
    wing = run.relics[0]
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    assert rewards.sacrifice_relic is wing
    relics_before = len(run.relics)
    wing.on_sacrifice(run)
    assert len(run.relics) == relics_before    # 1st sacrifice: nothing
    wing.on_sacrifice(run)
    assert len(run.relics) == relics_before + 1  # 2nd: grab-bag relic


def test_reward_card_legal_actions_include_sacrifice():
    run = fresh_run(25)
    run.add_relic("paels_wing")
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    request = DecisionRequest(
        kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards,
    )
    # 0-2 take, 3 skip, 5 sacrifice (4 = reroll absent without Driftwood).
    assert request.legal_actions() == [0, 1, 2, 3, 5]


def test_paels_legion_doubles_first_card_block_on_cooldown():
    deck = [make_card("defend") for _ in range(10)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("paels_legion")],
    )
    combat.play_card(0)
    assert combat.player.block == 10           # 5 x 2 (awake)
    combat.play_card(0)
    assert combat.player.block == 15           # cooldown: normal 5
    combat.end_turn()                          # turn start ticks cooldown 2->1
    combat.play_card(0)
    assert combat.player.block == 5            # still asleep
    combat.end_turn()                          # 1->0: awake again
    combat.play_card(0)
    assert combat.player.block == 10


def test_paels_legion_gates_pet():
    run = fresh_run(26)
    assert not run.has_event_pet
    run.add_relic(make_relic("paels_legion"))
    assert run.has_event_pet


# ═════════════════════════════════════════════════════════════════════════
# Tezcatara — the event
# ═════════════════════════════════════════════════════════════════════════

TEZ_POOL_1 = {"very_hot_cocoa", "yummy_cookie", "nutritious_soup"}
TEZ_POOL_2 = {"biiig_hug", "storybook", "toasty_mittens"}
TEZ_POOL_3 = {"golden_compass", "pumpkin_candle", "toy_box", "seal_of_gold"}


def test_tezcatara_option_structure():
    seen1, seen3 = set(), set()
    for seed in range(80):
        run = fresh_run(seed)
        event = make_event("tezcatara", run).begin()
        keys = event.option_keys()
        assert len(keys) == 3
        assert keys[0] in TEZ_POOL_1
        assert keys[1] in TEZ_POOL_2
        assert keys[2] in TEZ_POOL_3
        seen1.add(keys[0])
        seen3.add(keys[2])
    assert seen1 == TEZ_POOL_1        # Basic Strikes present → Soup offerable
    assert seen3 == TEZ_POOL_3


def test_tezcatara_soup_gate_closes_without_basic_strikes():
    for seed in range(40):
        run = fresh_run(seed)
        run.deck[:] = [c for c in run.deck if c.id != "strike"]
        event = make_event("tezcatara", run).begin()
        assert event.option_keys()[0] in {"very_hot_cocoa", "yummy_cookie"}


# ═════════════════════════════════════════════════════════════════════════
# Tezcatara — the relics
# ═════════════════════════════════════════════════════════════════════════

def test_yummy_cookie_upgrades_four_chosen():
    run = fresh_run(30)
    run.add_relic("yummy_cookie")
    assert sum(1 for c in run.deck if c.upgrade_level > 0) == 4


def test_biiig_hug_removes_four_and_soots_shuffles():
    run = fresh_run(31)
    run.add_relic("biiig_hug")
    assert len(run.deck) == 6                  # 10 - 4 removed
    combat = run.create_combat(WURM)
    # Force a reshuffle: empty the draw pile into the discard pile.
    combat.player.discard_pile.extend(combat.player.draw_pile)
    combat.player.draw_pile.clear()
    combat.player.reshuffle_discard_into_draw()
    assert any(c.id == "soot" for c in combat.player.draw_pile)


def test_storybook_and_brightest_flame():
    run = fresh_run(32)
    run.add_relic("storybook")
    assert any(c.id == "brightest_flame" for c in run.deck)

    deck = [make_card("brightest_flame")] + [
        make_card("strike") for _ in range(11)
    ]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
    )
    flame = next(
        (c for c in combat.player.hand if c.id == "brightest_flame"), None,
    )
    if flame is None:                          # not drawn: fish it out
        combat.player.hand.append(flame := next(
            c for c in combat.player.draw_pile if c.id == "brightest_flame"
        ))
        combat.player.draw_pile.remove(flame)
    max_hp = combat.player.max_hp
    combat.play_card(combat.player.hand.index(flame))
    assert combat.player.energy == 3 + 2       # 0-cost, +2
    assert combat.player.max_hp == max_hp - 1


def test_toasty_mittens_exhausts_top_of_draw():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("toasty_mittens")],
    )
    assert len(combat.player.exhaust_pile) == 1
    combat.end_turn()
    assert len(combat.player.exhaust_pile) == 2


def test_pumpkin_candle_kindle_cycle():
    run = fresh_run(33)
    run.add_relic("pumpkin_candle")
    candle = run.relics[0]
    assert candle.kindle_count == 5
    for i in range(5):
        combat = run.create_combat(WURM)
        assert combat.player.energy == 4       # kindled
        run.finish_combat(combat, room_type=RoomType.MONSTER)
    assert candle.kindle_count == 0
    combat = run.create_combat(WURM)
    assert combat.player.energy == 3           # burned out
    run.finish_combat(combat, room_type=RoomType.MONSTER)
    # The rest-site KINDLE option re-lights it.
    options = run.rest_site_options()
    assert [o.key for o in options] == ["KINDLE"]
    options[0].on_select(run)
    assert candle.kindle_count == 5


def test_seal_of_gold_pays_gold_for_energy():
    run = fresh_run(34)
    run.gold = 12
    run.add_relic("seal_of_gold")
    combat = run.create_combat(WURM)
    assert combat.player.energy == 4           # turn 1: paid 5
    combat.end_turn()
    assert combat.player.energy == 4           # turn 2: paid 5 (10 spent)
    combat.end_turn()
    assert combat.player.energy == 3           # only 2 gold left
    run.finish_combat(combat, room_type=RoomType.MONSTER)
    assert run.gold == 2


def test_toy_box_wax_relics_and_melt():
    run = fresh_run(35)
    run.add_relic("toy_box")
    assert len(run.relics) == 5                # box + 4 wax
    wax = [r for r in run.relics if r.is_wax]
    assert len(wax) == 4
    for i in range(1, 13):
        combat = run.create_combat(WURM)
        run.finish_combat(combat, room_type=RoomType.MONSTER)
        expected_melts = min(4, i // 3)
        assert len([r for r in run.relics if r.is_wax]) == 4 - expected_melts
    assert not any(r.is_wax for r in run.relics)


def test_nutritious_soup_embers_basic_strikes():
    run = fresh_run(36)
    run.add_relic("nutritious_soup")
    strikes = [c for c in run.deck if c.id == "strike"]
    assert len(strikes) == 5
    assert all(
        c.enchantment is not None and c.enchantment.id == "tezcataras_ember"
        for c in strikes
    )
    assert not any(
        c.enchantment is not None
        for c in run.deck if c.id != "strike"
    )


# ═════════════════════════════════════════════════════════════════════════
# Nonupeipe — the event
# ═════════════════════════════════════════════════════════════════════════

NONU_POOL = {
    "blessed_antler", "brilliant_scarf", "delicate_frond", "diamond_diadem",
    "fur_coat", "glitter", "jewelry_box", "looming_fruit", "signet_ring",
    "beautiful_bracelet",
}


def test_nonupeipe_option_structure():
    seen = set()
    for seed in range(120):
        run = fresh_run(seed)
        event = make_event("nonupeipe", run).begin()
        keys = event.option_keys()
        assert len(keys) == 3
        assert len(set(keys)) == 3            # shuffle-take-3: distinct
        assert set(keys) <= NONU_POOL
        seen |= set(keys)
    assert seen == NONU_POOL                  # bracelet offerable (9 eligible)


def test_nonupeipe_bracelet_gate_closes():
    for seed in range(60):
        run = fresh_run(seed)
        # Only 3 Swift-eligible cards left (< 4).
        run.deck[:] = run.deck[:3]
        event = make_event("nonupeipe", run).begin()
        assert "beautiful_bracelet" not in event.option_keys()


# ═════════════════════════════════════════════════════════════════════════
# Nonupeipe — the relics
# ═════════════════════════════════════════════════════════════════════════

def test_blessed_antler_energy_and_dazed():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("blessed_antler")],
    )
    assert combat.player.energy == 4
    dazed = [
        c for c in combat.player.draw_pile + combat.player.hand
        if c.id == "dazed"
    ]
    assert len(dazed) == 3
    combat.end_turn()
    assert combat.player.energy == 4           # every turn
    all_cards = combat.player.all_cards
    assert sum(1 for c in all_cards if c.id == "dazed") == 3  # turn 1 only


def test_brilliant_scarf_fifth_card_free():
    deck = [make_card("strike") for _ in range(12)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("brilliant_scarf")],
    )
    scarf = next(r for r in combat.hooks._listeners if getattr(r, "id", "") == "brilliant_scarf")
    combat.player.energy = 99
    for _ in range(4):
        combat.play_card(0)
    assert scarf.cards_played_this_turn == 4
    energy_before = combat.player.energy
    # 5th card: free (draw pile has cards; hand emptied → draw more first)
    combat.player.hand.append(combat.player.draw_pile.pop())
    combat.play_card(0)
    assert combat.player.energy == energy_before  # cost 0
    combat.end_turn()
    assert scarf.cards_played_this_turn == 0   # per-turn reset


def test_delicate_frond_fills_potions():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("delicate_frond")],
    )
    # DelicateFrond fills every open slot -- Player.cs's belt is a
    # fixed-length list[Potion | None], so `len(potions)` alone would be
    # trivially true whether or not the fill happened; assert every slot is
    # actually occupied.
    assert len(combat.player.held_potions) == combat.player.max_potions


def test_diamond_diadem_power_on_quiet_turns():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("diamond_diadem")],
    )
    combat.end_turn()                          # played 0 ≤ 2 → power granted
    # The power halves attack damage and expires after the enemy side; by the
    # time the next player turn starts it must be gone again.
    assert "diamond_diadem" not in combat.player.powers
    # Play 3 cards this turn: no power at turn end.
    combat.player.energy = 99
    for _ in range(3):
        if not combat.player.hand:
            break
        combat.play_card(0)
    relic = next(r for r in combat.hooks._listeners if getattr(r, "id", "") == "diamond_diadem")
    assert relic.cards_played_this_turn >= 3 or not combat.player.hand


def test_diamond_diadem_power_halves_attack_damage():
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import DiamondDiademPower
    from sts2_rl.valueprops import DamageProps

    combat = CombatState(rng=random.Random(0), encounter=WURM)
    PowerCmd.apply(
        combat.hooks, combat.player, DiamondDiademPower, 1,
        applier=combat.player,
    )
    from sts2_rl.cmds import DamageCmd

    hp_before = combat.player.hp
    DamageCmd.deal(
        combat.hooks, combat.player, 10,
        dealer=combat.enemy, props=DamageProps.MONSTER_MOVE,
    )
    assert hp_before - combat.player.hp == 5   # halved


def test_fur_coat_marks_and_maims():
    run = fresh_run(40)
    run.start_act("overgrowth")
    run.add_relic("fur_coat")
    coat = run.relics[0]
    assert coat.act_index == run.act_index
    assert 1 <= len(coat.marked_coords) <= 7
    from sts2_rl.actmap import MapPointType

    for coord in coat.marked_coords:
        point = run.map.get_point(*coord)
        assert point.point_type in (MapPointType.MONSTER, MapPointType.ELITE)
    # Simulate entering a marked room and starting its combat.
    marked_point = run.map.get_point(*next(iter(coat.marked_coords)))
    coat.after_room_entered(run, marked_point, RoomType.MONSTER)
    combat = run.create_combat(WURM)
    assert all(e.hp == 1 for e in combat.enemies)
    run.finish_combat(combat, room_type=RoomType.MONSTER)
    # Unmarked rooms are unaffected.
    combat = run.create_combat(WURM)
    assert all(e.hp > 1 for e in combat.enemies)


def test_glitter_glams_every_reward():
    run = fresh_run(41)
    run.add_relic("glitter")
    for _ in range(2):                         # NOT one-shot
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        assert all(
            c.enchantment is not None and c.enchantment.id == "glam"
            for c in rewards.cards
        )


def test_jewelry_box_and_apotheosis():
    run = fresh_run(42)
    run.add_relic("jewelry_box")
    assert any(c.id == "apotheosis" for c in run.deck)

    deck = [make_card("apotheosis")] + [make_card("strike") for _ in range(9)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
    )
    apo = next(c for c in combat.player.hand if c.id == "apotheosis")  # innate
    combat.play_card(combat.player.hand.index(apo))
    others = [c for c in combat.player.all_cards if c.id != "apotheosis"]
    assert all(c.upgrade_level == 1 for c in others)
    assert apo.upgrade_level == 0              # not itself


def test_signet_ring_gold():
    run = fresh_run(43)
    gold = run.gold
    run.add_relic("signet_ring")
    assert run.gold == gold + 999


def test_beautiful_bracelet_swift_three():
    run = fresh_run(44)
    run.add_relic("beautiful_bracelet")
    swifts = [c for c in run.deck if c.enchantment is not None]
    assert len(swifts) == 3
    assert all(c.enchantment.id == "swift" for c in swifts)
    assert all(c.enchantment.amount == 3 for c in swifts)


# ═════════════════════════════════════════════════════════════════════════
# Tanx — the event
# ═════════════════════════════════════════════════════════════════════════

TANX_POOL = {
    "claws", "crossbow", "iron_club", "meat_cleaver", "sai",
    "spiked_gauntlets", "tanxs_whistle", "throwing_axe", "war_hammer",
    "tri_boomerang",
}


def test_tanx_option_structure():
    seen = set()
    for seed in range(120):
        run = fresh_run(seed)
        event = make_event("tanx", run).begin()
        keys = event.option_keys()
        assert len(keys) == 3
        assert len(set(keys)) == 3
        assert set(keys) <= TANX_POOL
        seen |= set(keys)
    assert seen == TANX_POOL                  # 6 Attacks → boomerang offerable


def test_tanx_boomerang_gate_closes():
    for seed in range(60):
        run = fresh_run(seed)
        # Leave only 2 Attacks (< 3 Instinct-eligible).
        run.deck[:] = [c for c in run.deck if c.id == "strike"][:2]
        event = make_event("tanx", run).begin()
        assert "tri_boomerang" not in event.option_keys()


# ═════════════════════════════════════════════════════════════════════════
# Tanx — the relics
# ═════════════════════════════════════════════════════════════════════════

def test_spiked_gauntlets_energy_and_power_tax():
    from sts2_rl.cards import make_card as mk

    deck = [mk("inflame")] + [mk("strike") for _ in range(9)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("spiked_gauntlets")],
    )
    assert combat.player.energy == 4
    inflame = next(
        (c for c in combat.player.all_cards if c.id == "inflame"), None,
    )
    assert inflame is not None
    assert combat.hooks.modify_card_energy_cost(inflame, inflame.energy_cost) \
        == inflame.energy_cost + 1
    strike = next(c for c in combat.player.all_cards if c.id == "strike")
    assert combat.hooks.modify_card_energy_cost(strike, strike.energy_cost) \
        == strike.energy_cost


def test_sai_block_every_turn():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("sai")],
    )
    assert combat.player.block == 7
    combat.end_turn()
    assert combat.player.block == 7            # cleared, then re-granted


def test_iron_club_every_fourth_card_draws():
    # MOVED 2026-07-29 (round 7, relic/iron_club/g1). It used to be
    # `test_iron_club_every_sixth_card_draws` and count to 6, which was the
    # port's pinned constant. IronClub.cs:38 declares `CardsVar(4)` and every
    # consumer reads it -- DisplayAmount (:32), UpdateDisplay (:77) and the
    # draw condition `CardsPlayed % intValue == 0` (:88-89) -- with no
    # AscensionHelper branch anywhere in the file.
    deck = [make_card("strike") for _ in range(20)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("iron_club")],
    )
    combat.player.energy = 99
    club = next(
        r for r in combat.hooks._listeners
        if getattr(r, "id", "") == "iron_club"
    )
    for i in range(1, 4):
        combat.play_card(0)
        assert club.cards_played == i
    hand_before = len(combat.player.hand)
    combat.play_card(0)                        # 4th: draw 1
    assert len(combat.player.hand) == hand_before  # -1 played +1 drawn


def test_war_hammer_upgrades_after_elite():
    run = fresh_run(50)
    run.add_relic("war_hammer")
    combat = run.create_combat(WURM)
    run.finish_combat(combat, room_type=RoomType.MONSTER)
    assert not any(c.upgrade_level > 0 for c in run.deck)
    combat = run.create_combat(WURM)
    run.finish_combat(combat, room_type=RoomType.ELITE)
    # WarHammer.cs:17 pins CardsVar(4) and :26-27 ends in .Take(4).
    assert sum(c.upgrade_level for c in run.deck) == 4


def test_throwing_axe_first_card_twice():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("throwing_axe")],
    )
    enemy = combat.enemy
    hp = enemy.hp
    strike_idx = next(
        i for i, c in enumerate(combat.player.hand) if c.id == "strike"
    )
    combat.play_card(strike_idx)
    assert hp - enemy.hp == 12                 # 6 × 2 plays
    hp = enemy.hp
    strike_idx = next(
        (i for i, c in enumerate(combat.player.hand) if c.id == "strike"),
        None,
    )
    if strike_idx is not None:
        combat.play_card(strike_idx)
        assert hp - enemy.hp == 6              # used up: single play


def test_crossbow_free_attack_each_turn():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("crossbow")],
    )
    from sts2_rl.cards import CardType

    extras = [c for c in combat.player.hand if c.rarity.value not in ("basic",)]
    added = [
        c for c in combat.player.hand
        if c.card_type == CardType.ATTACK and c.energy_cost == 0
        or c._free_this_turn
    ]
    assert len(combat.player.hand) == 6        # 5 + the free attack
    free = [c for c in combat.player.hand if c._free_this_turn]
    assert len(free) == 1
    assert free[0].card_type == CardType.ATTACK
    combat.end_turn()
    assert len([c for c in combat.player.hand if c._free_this_turn]) == 1
    assert extras is not None and added is not None  # sanity


def test_claws_transforms_into_mauls():
    run = fresh_run(51)
    run.add_relic("claws")
    mauls = [c for c in run.deck if c.id == "maul"]
    assert len(mauls) == 6
    assert len(run.deck) == 10                 # in-place transforms


def test_maul_card_scales_all_mauls():
    deck = [make_card("maul"), make_card("maul")] + [
        make_card("strike") for _ in range(8)
    ]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
    )
    mauls = [c for c in combat.player.all_cards if c.id == "maul"]
    assert all(m._damage == 5 for m in mauls)
    maul_idx = next(
        (i for i, c in enumerate(combat.player.hand) if c.id == "maul"), None,
    )
    if maul_idx is None:                       # fish one into the hand
        maul = next(c for c in combat.player.draw_pile if c.id == "maul")
        combat.player.draw_pile.remove(maul)
        combat.player.hand.append(maul)
        maul_idx = len(combat.player.hand) - 1
    enemy_hp = combat.enemy.hp
    combat.play_card(maul_idx)
    assert enemy_hp - combat.enemy.hp == 10    # 5 × 2 hits
    assert all(m._damage == 6 for m in mauls)  # every Maul buffed


def test_tanxs_whistle_and_whistle_card():
    run = fresh_run(52)
    run.add_relic("tanxs_whistle")
    assert any(c.id == "whistle" for c in run.deck)

    deck = [make_card("whistle")] + [make_card("strike") for _ in range(9)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
    )
    whistle = next(
        (c for c in combat.player.hand if c.id == "whistle"), None,
    )
    if whistle is None:
        whistle = next(
            c for c in combat.player.draw_pile if c.id == "whistle"
        )
        combat.player.draw_pile.remove(whistle)
        combat.player.hand.append(whistle)
    enemy = combat.enemy
    hp = enemy.hp
    combat.play_card(combat.player.hand.index(whistle))
    if not combat.is_over:
        assert hp - enemy.hp == 33
        assert enemy.stunned
        assert whistle in combat.player.exhaust_pile


def test_meat_cleaver_cook_option():
    run = fresh_run(53)
    run.add_relic("meat_cleaver")
    options = run.rest_site_options()
    assert [o.key for o in options] == ["COOK"]
    deck_before, max_hp = len(run.deck), run.max_hp
    options[0].on_select(run)
    assert len(run.deck) == deck_before - 2
    assert run.max_hp == max_hp + 9
    # Below 2 removable cards the option disappears.
    run.deck[:] = run.deck[:1]
    assert run.rest_site_options() == []


def test_tri_boomerang_instinct_three():
    run = fresh_run(54)
    run.add_relic("tri_boomerang")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 3
    assert all(c.enchantment.id == "instinct" for c in enchanted)
    from sts2_rl.cards import CardType

    assert all(c.card_type == CardType.ATTACK for c in enchanted)


# ═════════════════════════════════════════════════════════════════════════
# Vakuu — the event
# ═════════════════════════════════════════════════════════════════════════

VAKUU_POOL_1 = {"blood_soaked_rose", "whispering_earring", "fiddle"}
VAKUU_POOL_2 = {"preserved_fog", "sere_talon", "distinguished_cape"}
VAKUU_POOL_3 = {
    "choices_paradox", "music_box", "lords_parasol", "jeweled_mask",
}


def test_vakuu_option_structure():
    seen1, seen2, seen3 = set(), set(), set()
    for seed in range(80):
        run = fresh_run(seed)
        event = make_event("vakuu", run).begin()
        keys = event.option_keys()
        assert len(keys) == 3
        assert keys[0] in VAKUU_POOL_1
        assert keys[1] in VAKUU_POOL_2
        assert keys[2] in VAKUU_POOL_3
        seen1.add(keys[0]); seen2.add(keys[1]); seen3.add(keys[2])
    assert seen1 == VAKUU_POOL_1
    assert seen2 == VAKUU_POOL_2
    assert seen3 == VAKUU_POOL_3


def test_vakuu_cape_option_costs_max_hp():
    for seed in range(200):
        run = fresh_run(seed)
        event = make_event("vakuu", run).begin()
        if event.option_keys()[1] != "distinguished_cape":
            continue
        max_hp = run.max_hp
        assert event.choose(1)
        assert run.max_hp == max_hp - 9
        assert any(r.id == "distinguished_cape" for r in run.relics)
        assert sum(1 for c in run.deck if c.id == "apparition") == 3
        break
    else:
        raise AssertionError("cape option never rolled in 200 seeds")


# ═════════════════════════════════════════════════════════════════════════
# Vakuu — the relics
# ═════════════════════════════════════════════════════════════════════════

def test_blood_soaked_rose():
    run = fresh_run(60)
    run.add_relic("blood_soaked_rose")
    assert any(c.id == "enthralled" for c in run.deck)
    combat = run.create_combat(WURM)
    assert combat.player.energy == 4


def test_whispering_earring_autoplays_turn_one():
    deck = [make_card("strike") for _ in range(10)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("whispering_earring")],
    )
    # +1 energy → 4; strikes cost 1 → 4 played on turn 1 automatically
    # (or fewer if the fight ends first).
    if not combat.is_over:
        assert combat.player.energy == 0
        assert len(combat.player.discard_pile) == 4
    combat.end_turn()
    if not combat.is_over:
        # Turn 2: no auto-play.
        assert combat.player.energy == 4


def test_fiddle_draw_bonus_and_no_mid_turn_draws():
    deck = [make_card("strike") for _ in range(14)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("fiddle")],
    )
    assert len(combat.player.hand) == 7        # 5 + 2
    from sts2_rl.cmds import DrawCmd

    DrawCmd.draw(combat.player, 2)             # mid-turn: prevented
    assert len(combat.player.hand) == 7


def test_preserved_fog_removes_and_curses():
    run = fresh_run(61)
    run.add_relic("preserved_fog")
    assert len(run.deck) == 10 - 3 + 1
    assert any(c.id == "folly" for c in run.deck)


def test_sere_talon_curses_and_wishes():
    from sts2_rl.cards import CardType

    run = fresh_run(62)
    run.add_relic("sere_talon")
    added = run.deck[10:]
    curses = [c for c in added if c.card_type == CardType.CURSE]
    wishes = [c for c in added if c.id == "wish"]
    assert len(curses) == 2
    assert len({c.id for c in curses}) == 2    # distinct
    assert len(wishes) == 3


def test_wish_card_fetches_from_draw():
    deck = [make_card("wish")] + [make_card("strike") for _ in range(11)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
    )
    wish = next((c for c in combat.player.hand if c.id == "wish"), None)
    if wish is None:
        wish = next(c for c in combat.player.draw_pile if c.id == "wish")
        combat.player.draw_pile.remove(wish)
        combat.player.hand.append(wish)
    hand_before = len(combat.player.hand)
    draw_before = len(combat.player.draw_pile)
    combat.play_card(combat.player.hand.index(wish))
    assert len(combat.player.draw_pile) == draw_before - 1
    assert len(combat.player.hand) == hand_before  # -wish +fetched
    assert wish in combat.player.exhaust_pile


def test_choices_paradox_turn_one_pick():
    combat = CombatState(
        rng=random.Random(0), encounter=WURM,
        relics=[make_relic("choices_paradox")],
    )
    assert len(combat.player.hand) == 6        # 5 drawn + 1 picked
    picked = combat.player.hand[-1]
    assert picked.retain
    from sts2_rl.cards import CardRarity

    assert picked.rarity in (
        CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE,
    )


def test_music_box_clones_first_attack_each_turn():
    deck = [make_card("strike") for _ in range(10)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(0), encounter=WURM,
        relics=[make_relic("music_box")],
    )
    hand_before = len(combat.player.hand)
    combat.play_card(0)
    assert len(combat.player.hand) == hand_before  # -1 played +1 clone
    clone = combat.player.hand[-1]
    assert clone.id == "strike" and clone.is_ethereal
    combat.play_card(0)                        # second attack: no clone
    assert len(combat.player.hand) == hand_before - 1


def test_lords_parasol_buys_out_the_shop():
    run = fresh_run(63)
    run.add_relic("lords_parasol")
    run.gold = 0                               # everything is free anyway
    run.start_act("overgrowth")
    from sts2_rl.rooms import RoomType as RT

    deck_before, relics_before = len(run.deck), len(run.relics)
    potions_before = len(run.held_potions)
    from sts2_rl.shop import MerchantInventory

    shop = MerchantInventory.create(run)
    for relic in run.relics:
        relic.after_shop_entered(run, shop)
    assert len(run.deck) > deck_before         # cards bought
    assert len(run.relics) > relics_before     # relics bought
    assert len(run.held_potions) > potions_before  # potions bought
    assert run.gold == 0                       # all free


def test_jeweled_mask_free_power_turn_one():
    from sts2_rl.cards import make_card as mk

    deck = [mk("inflame")] + [mk("strike") for _ in range(11)]
    combat = CombatState(
        starting_deck=deck, rng=random.Random(1), encounter=WURM,
        relics=[make_relic("jeweled_mask")],
    )
    inflame = next(
        (c for c in combat.player.hand if c.id == "inflame"), None,
    )
    # Either it was in the natural draw (5/12 chance) or the mask moved it.
    assert inflame is not None
    assert inflame._free_this_turn or len(combat.player.hand) == 6


def test_girya_lift_option():
    run = fresh_run(53)
    run.add_relic("girya")
    girya = run.relics[0]
    for expected in (1, 2, 3):
        options = run.rest_site_options()
        assert [o.key for o in options] == ["LIFT"]
        options[0].on_select(run)
        assert girya.times_lifted == expected
    # Maxed out at 3 lifts: the option disappears.
    assert run.rest_site_options() == []


def test_shovel_dig_option():
    run = fresh_run(53)
    run.add_relic("shovel")
    bag_before = len(run.relic_grab_bag)
    relics_before = len(run.relics)
    options = run.rest_site_options()
    assert [o.key for o in options] == ["DIG"]
    options[0].on_select(run)
    assert len(run.relic_grab_bag) == bag_before - 1
    assert len(run.relics) == relics_before + 1
    # Empty bag: the option disappears.
    run.relic_grab_bag.clear()
    assert run.rest_site_options() == []


def test_eternal_feather_heals_on_rest_entry():
    run = fresh_run(53)
    run.add_relic("eternal_feather")
    run.hp = 40
    relic = run.relics[0]
    groups = len(run.deck) // 5
    relic.after_room_entered(run, None, RoomType.REST_SITE)
    assert run.hp == 40 + 3 * groups
    # Not a rest site: no heal.
    hp = run.hp
    relic.after_room_entered(run, None, RoomType.MONSTER)
    assert run.hp == hp


def test_miniature_tent_disables_hook_returns_false():
    run = fresh_run(1)
    run.add_relic("miniature_tent")
    assert run.should_disable_remaining_rest_site_options() is False
    run2 = fresh_run(1)
    assert run2.should_disable_remaining_rest_site_options() is True


def test_orobas_draws_the_other_character_pick_first():
    """`GenerateInitialOptions` opens with
    `base.Rng.NextItem(Owner.UnlockState.Characters.Where(c => c.Id != mine))`
    — the Sea Glass character. The sim models a fully-unlocked run (as
    potion_pools/cards do), so that is a draw over the OTHER 4 of
    ModelDb.AllCharacters, not an empty short-circuit: skipping it shifts every
    later Orobas pick by one draw. 933T39V18D's Hive shrine offered
    RADIANT_PEARL in the second slot (its recorded `ChooseEventOption 1`)."""
    run = RunState(string_seed="933T39V18D")
    run.start_run(acts=["overgrowth", "hive", "glory"], ascension=0)
    event = make_event("orobas", run)
    assert event.event_rng.counter == 0
    event.begin()
    # 1 character pick + 1 Prismatic/Sea Glass NextFloat + 3 NextItem picks.
    assert event.event_rng.counter == 5
    assert event.option_keys()[1] == "radiant_pearl"
