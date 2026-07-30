"""The Fake Merchant shared event (FakeMerchant.cs), his nine knock-off
relics, and the fight a Foul Potion starts (FakeMerchantMonster.cs /
FakeMerchantEventEncounter.cs). Plan:
docs/superpowers/plans/2026-07-19-shared-events.md."""
import random

from sts2_rl.cards import make_card
from sts2_rl.cmds import PowerCmd
from sts2_rl.combat import CombatState
from sts2_rl.events import ALL_EVENTS, make_event
from sts2_rl.monsters import FAKE_MERCHANT_EVENT_ENCOUNTER
from sts2_rl.monsters.overgrowth import ENCOUNTERS
from sts2_rl.potions import make_potion
from sts2_rl.relics import make_relic
from sts2_rl.run import RunState

WURM = ENCOUNTERS["fuzzy_wurm_weak"]

STOCK = {"fake_anchor", "fake_blood_vial", "fake_happy_flower",
         "fake_lees_waffle", "fake_mango", "fake_orichalcum",
         "fake_snecko_eye", "fake_strike_dummy", "fake_venerable_tea_set"}


def hive_run(seed=0, gold=300):
    run = RunState(rng=random.Random(seed))
    run.start_run(acts=["overgrowth", "hive"])
    run.advance_act()
    run.gold = gold
    return run


def build(deck=None, seed=0, relics=(), encounter=WURM):
    return CombatState(
        starting_deck=deck, rng=random.Random(seed), encounter=encounter,
        relics=list(relics),
    )


# ═════════════════════════════════════════════════════════════════════════
# The stall
# ═════════════════════════════════════════════════════════════════════════

def test_gate_needs_act2_plus_gold_or_a_foul_potion():
    gate = ALL_EVENTS["fake_merchant"].is_allowed

    act1 = RunState(rng=random.Random(1))
    act1.start_run(acts=["overgrowth"])
    act1.gold = 500
    assert not gate(act1)                       # act 1 never

    poor = hive_run(1, gold=99)
    assert not gate(poor)
    poor.add_potion(make_potion("foul_potion"))
    assert gate(poor)                           # a Foul Potion suffices

    rich = hive_run(2, gold=100)
    assert gate(rich)


def test_stall_shows_six_of_the_nine_knock_offs():
    run = hive_run(3)
    event = make_event("fake_merchant", run).begin()
    offered = [k for k in event.option_keys() if k in STOCK]
    assert len(offered) == 6
    assert len(set(offered)) == 6               # never duplicated
    assert event.option_keys()[-1] == "LEAVE"


def test_buying_charges_the_jittered_price_and_keeps_the_stall_open():
    """MOVED 2026-07-29 (round 7, event/fake_merchant/g3): this asserted a flat
    50 (`gold == 250` from 300). MerchantRelicEntry.CalcCost
    (MerchantRelicEntry.cs:42-45) is `Round(MerchantCost *
    Shops.NextFloat(0.85f, 1.15f))` — one Shops draw per stocked entry — and
    `FakeMerchant.relicCost = 50` is a dead constant. 50 is still the BASE (every
    knock-off declares `MerchantCost => 50`), so the price is 43..58."""
    run = hive_run(4)
    event = make_event("fake_merchant", run).begin()
    first = event.option_keys()[0]
    price = event.price_of(next(r for r in event.stock if r.id == first))
    assert 43 <= price <= 58
    assert event.choose(first)
    assert run.gold == 300 - price
    assert [r.id for r in run.relics] == ["burning_blood", first]
    assert not event.finished                   # still shopping
    assert first not in event.option_keys()     # sold out of that one
    assert len([k for k in event.option_keys() if k in STOCK]) == 5


def test_knock_offs_cost_fifty_not_their_rarity_price():
    assert make_relic("fake_anchor").merchant_cost == 50
    # The Rug has no override — it is loot, never stock.
    assert make_relic("fake_merchants_rug").merchant_cost > 1000


def test_stall_locks_stock_when_broke():
    """MOVED 2026-07-29 (round 7, event/fake_merchant/g3): this asserted the two
    buys landed on exactly `gold == 0` from a flat 2x50. The prices are jittered
    per entry (MerchantRelicEntry.cs:42-45), so what the test is really about —
    everything you cannot afford is locked — is asserted directly."""
    run = hive_run(5, gold=100)
    event = make_event("fake_merchant", run).begin()
    assert event.choose(event.option_keys()[0])
    assert event.choose(event.option_keys()[0])
    assert run.gold < min(event.price_of(r) for r in event.stock)
    assert all(k.endswith("_LOCKED")
               for k in event.option_keys() if k not in ("LEAVE",))


def test_leave_ends_without_a_fight():
    run = hive_run(6)
    event = make_event("fake_merchant", run).begin()
    assert event.choose("LEAVE")
    assert event.finished
    assert event.pending_encounter is None


# ═════════════════════════════════════════════════════════════════════════
# Throwing the Foul Potion
# ═════════════════════════════════════════════════════════════════════════

def test_throwing_starts_the_fight_and_queues_the_loot():
    run = hive_run(7)
    run.add_potion(make_potion("foul_potion"))
    event = make_event("fake_merchant", run).begin()
    bought = event.option_keys()[0]
    assert event.choose(bought)                  # buy one first
    assert event.choose("THROW_POTION")
    assert event.finished
    assert run.held_potions == []                # the potion is spent (slot nulled, not compacted)
    assert event.pending_encounter is FAKE_MERCHANT_EVENT_ENCOUNTER
    loot = [e.relic.id for e in event.pending_reward_extras]
    assert loot[0] == "fake_merchants_rug"
    # ... plus every relic still on the shelf (6 stocked - 1 bought).
    assert len(loot) == 6
    assert bought not in loot[1:]


def test_no_throw_option_without_a_foul_potion():
    run = hive_run(8)
    event = make_event("fake_merchant", run).begin()
    assert "THROW_POTION" not in event.option_keys()


# ═════════════════════════════════════════════════════════════════════════
# The fight
# ═════════════════════════════════════════════════════════════════════════

def test_merchant_monster_stats_and_opening_move():
    combat = build(seed=9, encounter=FAKE_MERCHANT_EVENT_ENCOUNTER)
    merchant = combat.enemy
    assert merchant.hp == merchant.max_hp == 165
    # Opens on SWIPE (13).
    assert merchant.current_intent.damage == 13
    assert merchant.current_intent.hits == 1


def test_merchant_encounter_pays_a_flat_300_gold():
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType

    run = hive_run(10, gold=0)
    for _ in range(5):
        rewards = generate_combat_rewards(
            run, RoomType.MONSTER, encounter=FAKE_MERCHANT_EVENT_ENCOUNTER)
        assert rewards.gold == 300           # MinGoldReward == MaxGoldReward


def test_ordinary_encounters_still_use_the_room_range():
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType

    run = hive_run(11, gold=0)
    rewards = generate_combat_rewards(run, RoomType.MONSTER, encounter=WURM)
    assert 10 <= rewards.gold <= 20


def test_merchant_moves_cover_the_whole_state_machine():
    seen = set()
    for seed in range(25):
        combat = build(seed=seed, encounter=FAKE_MERCHANT_EVENT_ENCOUNTER)
        combat.player.max_hp = combat.player.hp = 9999
        merchant = combat.enemy
        merchant.hp = 9999
        for _ in range(8):
            seen.add(merchant._current_move.id)
            combat.end_turn()
    assert {"SWIPE_MOVE", "SPEW_COINS_MOVE", "THROW_RELIC_MOVE",
            "ENRAGE_MOVE"} <= seen


def test_merchant_never_repeats_a_move_back_to_back():
    for seed in range(15):
        combat = build(seed=seed, encounter=FAKE_MERCHANT_EVENT_ENCOUNTER)
        combat.player.max_hp = combat.player.hp = 9999
        merchant = combat.enemy
        merchant.hp = 9999
        previous = merchant._current_move.id
        for _ in range(8):
            combat.end_turn()
            current = merchant._current_move.id
            assert current != previous       # every branch is CANNOT_REPEAT
            previous = current


def test_throw_relic_is_followed_by_an_attack_not_enrage():
    """THROW_RELIC's follow-up is RAND_ATTACK_MOVE, which has no Enrage."""
    checked = 0
    for seed in range(40):
        combat = build(seed=seed, encounter=FAKE_MERCHANT_EVENT_ENCOUNTER)
        combat.player.max_hp = combat.player.hp = 9999
        merchant = combat.enemy
        merchant.hp = 9999
        for _ in range(8):
            was_throw = merchant._current_move.id == "THROW_RELIC_MOVE"
            combat.end_turn()
            if was_throw:
                assert merchant._current_move.id != "ENRAGE_MOVE"
                checked += 1
    assert checked          # the case actually occurred


# ═════════════════════════════════════════════════════════════════════════
# The knock-off relics
# ═════════════════════════════════════════════════════════════════════════

def test_fake_anchor_blocks_four():
    combat = build(seed=12, relics=[make_relic("fake_anchor")])
    assert combat.player.block == 4


def test_fake_blood_vial_heals_one():
    # The heal fires at combat setup, so enter combat already damaged: a run
    # combat carries the run's current HP in.
    run = hive_run(13)
    run.hp = 40
    plain = run.create_combat(WURM)
    assert plain.player.hp == 40

    run2 = hive_run(13)
    run2.hp = 40
    run2.add_relic(make_relic("fake_blood_vial"))
    healed = run2.create_combat(WURM)
    assert healed.player.hp == 41          # the real Blood Vial heals 2


def test_fake_happy_flower_every_five_turns():
    relic = make_relic("fake_happy_flower")
    combat = build(deck=[make_card("defend") for _ in range(20)], seed=14,
                   relics=[relic])
    combat.enemy.hp = 9999
    combat.player.max_hp = combat.player.hp = 9999
    assert relic.turns_seen == 1
    for _ in range(3):
        combat.end_turn()
    assert relic.turns_seen == 4
    energy_before = combat.player.energy
    combat.end_turn()                       # 5th turn: the payout
    assert relic.turns_seen == 0
    assert combat.player.energy == energy_before + 1


def test_fake_lees_waffle_heals_ten_percent():
    run = hive_run(15)
    run.hp = 40
    run.add_relic("fake_lees_waffle")
    assert run.hp == 48                     # 40 + 10% of 80


def test_fake_mango_gives_three_max_hp():
    run = hive_run(16)
    before = run.max_hp
    run.add_relic("fake_mango")
    assert run.max_hp == before + 3


def test_fake_orichalcum_blocks_three_when_bare():
    """The block lands at turn end and is spent on the enemy's attack, so
    measure it as damage NOT taken versus the same seeded fight without it."""
    def hp_after_a_turn(relics):
        combat = build(deck=[make_card("strike") for _ in range(10)], seed=17,
                       relics=relics)
        combat.player.block = 0
        combat.end_turn()
        return combat.player.hp

    bare = hp_after_a_turn([])
    shielded = hp_after_a_turn([make_relic("fake_orichalcum")])
    assert shielded - bare == 3            # the real Orichalcum gives 6


def test_fake_orichalcum_is_suppressed_by_platings_earlier_grant():
    """FakeOrichalcum.cs:40-46 spells the phase contract out: the `Block > 0`
    snapshot is `BeforeSideTurnEndVeryEarly` "because it needs to check the
    player's block before PlatingPower triggers (otherwise, PlatingPower will
    prevent this relic's block gain), and PlatingPower in turn needs to run
    early so it can give you block before you take damage from another
    end-of-turn effect."

    So the two are ordered, not lucky: Fake Orichalcum snapshots in
    `_very_early`, Plating grants in `_early` (PlatingPower.cs:61), Fake
    Orichalcum grants in the plain pass (:60) only if the snapshot saw 0. With
    Plating on the player the relic still fires -- it decided before Plating
    moved -- and the player ends the turn with BOTH grants. turn_structure G12.
    """
    from sts2_rl.powers import PlatingPower

    def block_at_turn_end(relics, plating):
        combat = build(deck=[make_card("strike") for _ in range(10)], seed=17,
                       relics=relics)
        combat.player.block = 0
        if plating:
            PowerCmd.apply(combat.hooks, combat.player, PlatingPower, 5,
                           applier=combat.player)
        seen = []

        class Probe:
            # after_player_turn_end is Hook.AfterTurnEnd, the first slot after
            # every BeforeTurnEnd phase has run.
            def after_player_turn_end(self, player):
                seen.append(player.block)

        combat.hooks.register(Probe())
        combat.end_turn()
        return seen[0]

    assert block_at_turn_end([], plating=True) == 5
    assert block_at_turn_end([make_relic("fake_orichalcum")],
                             plating=True) == 8
    assert block_at_turn_end([make_relic("fake_orichalcum")],
                             plating=False) == 3


def test_fake_snecko_eye_confuses_without_extra_draw():
    plain = build(deck=[make_card("strike") for _ in range(12)], seed=18)
    fake = build(deck=[make_card("strike") for _ in range(12)], seed=18,
                 relics=[make_relic("fake_snecko_eye")])
    assert len(fake.player.hand) == len(plain.player.hand)   # NO extra cards
    assert "confused" in fake.player.powers
    assert len({c.energy_cost for c in fake.player.hand}) > 1


def test_fake_strike_dummy_adds_one():
    strike = make_card("strike")
    combat = build(deck=[strike] + [make_card("defend") for _ in range(4)],
                   seed=19, relics=[make_relic("fake_strike_dummy")])
    enemy = combat.enemy
    hp = enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 7               # base 6 + 1


def test_fake_venerable_tea_set_gives_one_energy_after_a_rest():
    rested = make_relic("fake_venerable_tea_set")
    rested._pending = True
    combat = build(seed=20, relics=[rested])
    assert combat.player.energy == 4        # 3 + 1

    unrested = build(seed=20, relics=[make_relic("fake_venerable_tea_set")])
    assert unrested.player.energy == 3


def test_fake_merchants_rug_is_an_inert_trophy():
    rug = make_relic("fake_merchants_rug")
    assert rug.rarity.value == "event"
    # No hooks at all, exactly like the source model.
    assert not any(
        hasattr(rug, h) for h in
        ("on_combat_start", "on_player_turn_started", "modify_damage_additive")
    )
