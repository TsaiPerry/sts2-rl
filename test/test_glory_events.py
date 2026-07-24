"""
Tests for the Act-3 "Glory" event pool (sts2_rl/events/) — Battleworn Dummy,
Grave of the Forgotten, Hungry for Mushrooms, Reflections, Round Tea Party,
Trial and Tinker Time — plus the content they grant: the Mad Science card, the
Souls enchantment, the Forgotten Soul / Royal Poison / Big / Fragrant Mushroom
relics, the Strangle / Curious / Improvement powers, and the Battle Friend dummy
encounters.

Run with:  py -m pytest test/test_glory_events.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, RunState, make_event
from sts2_rl.cards import CardType, make_card
from sts2_rl.cards.mad_science import MadScienceCard
from sts2_rl.cmds import ExhaustCmd
from sts2_rl.enchantments import SoulsEnchantment, make_enchantment
from sts2_rl.events import ALL_EVENTS, GLORY_EVENTS, allowed_events
from sts2_rl.monsters import FUZZY_WURM_ENCOUNTER
from sts2_rl.monsters.glory import (
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
)
from sts2_rl.relics import make_relic


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


def pick(*cards):
    wanted = list(cards)
    return lambda purpose, candidates, count: [c for c in wanted if c in candidates][:count]


def mad(card_type, rider="none"):
    return MadScienceCard().configure(card_type, rider)


def build_combat(deck_ids, encounter=None, relics=None, seed=0):
    deck = [make_card(cid) if isinstance(cid, str) else cid for cid in deck_ids]
    return CombatState(
        starting_deck=deck,
        rng=random.Random(seed),
        encounter=encounter or FUZZY_WURM_ENCOUNTER,
        relics=relics or [],
    )


def hand_index(combat, card_id):
    return combat.player.hand.index(next(c for c in combat.player.hand if c.id == card_id))


# ── Pool ────────────────────────────────────────────────────────────────────


def test_glory_pool_complete():
    assert GLORY_EVENTS == (
        "battleworn_dummy", "grave_of_the_forgotten", "hungry_for_mushrooms",
        "reflections", "round_tea_party", "trial", "tinker_time",
    )
    for eid in GLORY_EVENTS:
        assert ALL_EVENTS[eid].id == eid


def test_glory_gate_filtering():
    # Starter deck (no Exhaust card) blocks Grave of the Forgotten.
    run = fresh_run()
    allowed = allowed_events(run, GLORY_EVENTS)
    assert "grave_of_the_forgotten" not in allowed
    assert "round_tea_party" in allowed          # full HP >= 12
    assert "tinker_time" in allowed              # always allowed

    # An Exhaust card in the deck opens Grave of the Forgotten.
    run.add_card(make_card("offering"))
    assert "grave_of_the_forgotten" in allowed_events(run, GLORY_EVENTS)

    # Low HP blocks Round Tea Party.
    hurt = fresh_run()
    hurt.hp = 11
    assert "round_tea_party" not in allowed_events(hurt, GLORY_EVENTS)


# ── Battleworn Dummy ──────────────────────────────────────────────────────────


def test_battleworn_dummy_settings_pick_encounters():
    run = fresh_run()
    ev = make_event("battleworn_dummy", run).begin()
    assert ev.option_keys() == ["SETTING_1", "SETTING_2", "SETTING_3"]
    ev.choose("SETTING_2")
    assert ev.pending_encounter is BATTLEWORN_DUMMY_SETTING_2
    assert ev.finished


def test_battle_friend_hp_and_do_nothing():
    for enc, hp in (
        (BATTLEWORN_DUMMY_SETTING_1, 75),
        (BATTLEWORN_DUMMY_SETTING_2, 150),
        (BATTLEWORN_DUMMY_SETTING_3, 300),
    ):
        combat = build_combat(["strike"] * 5, encounter=enc)
        dummy = combat.enemies[0]
        assert dummy.max_hp == hp
        assert dummy.powers["battleworn_dummy_time_limit"].amount == 3


def test_battle_friend_flees_after_three_turns():
    combat = build_combat(["defend"] * 5, encounter=BATTLEWORN_DUMMY_SETTING_1)
    dummy = combat.enemies[0]
    for _ in range(3):
        combat.end_turn()
    assert dummy.is_gone and combat.is_over  # escaped, so the fight ends


def test_battle_friend_can_be_destroyed():
    combat = build_combat(["strike"] * 5, encounter=BATTLEWORN_DUMMY_SETTING_1)
    dummy = combat.enemies[0]
    dummy.hp = 6
    combat.play_card(hand_index(combat, "strike"), target_idx=0)
    combat.play_card(hand_index(combat, "strike"), target_idx=0)
    assert dummy.is_dead and combat.is_over


# ── Grave of the Forgotten ────────────────────────────────────────────────────


def test_grave_confront_adds_decay_and_souls():
    run = fresh_run()
    offering = run.add_card(make_card("offering"))
    run.card_selector = pick(offering)
    ev = make_event("grave_of_the_forgotten", run).begin()
    assert ev.option_keys() == ["CONFRONT", "ACCEPT"]
    ev.choose("CONFRONT")
    assert any(c.id == "decay" for c in run.deck)
    assert offering.exhausts is False              # Souls removed Exhaust
    assert isinstance(offering.enchantment, SoulsEnchantment)


def test_grave_confront_locked_without_exhaust_card():
    run = fresh_run()  # starter deck, no Exhaust card
    ev = make_event("grave_of_the_forgotten", run).begin()
    assert ev.option_keys() == ["CONFRONT_LOCKED", "ACCEPT"]
    assert not ev.choose("CONFRONT_LOCKED")


def test_grave_accept_grants_forgotten_soul():
    run = fresh_run()
    run.add_card(make_card("offering"))
    ev = make_event("grave_of_the_forgotten", run).begin()
    ev.choose("ACCEPT")
    assert any(r.id == "forgotten_soul" for r in run.relics)


# ── Hungry for Mushrooms ──────────────────────────────────────────────────────


def test_hungry_big_mushroom():
    run = fresh_run()
    max0 = run.max_hp
    ev = make_event("hungry_for_mushrooms", run).begin()
    assert ev.option_keys() == ["BIG_MUSHROOM", "FRAGRANT_MUSHROOM"]
    ev.choose("BIG_MUSHROOM")
    assert any(r.id == "big_mushroom" for r in run.relics)
    assert run.max_hp == max0 + 20


def test_hungry_fragrant_mushroom():
    run = fresh_run()
    run.deck = [make_card("strike"), make_card("defend"), make_card("bash")]
    hp0 = run.hp
    ev = make_event("hungry_for_mushrooms", run).begin()
    ev.choose("FRAGRANT_MUSHROOM")
    assert any(r.id == "fragrant_mushroom" for r in run.relics)
    assert run.hp == hp0 - 15
    assert sum(c.upgrade_level for c in run.deck) == 2  # 2 cards upgraded


# ── Reflections ───────────────────────────────────────────────────────────────


def test_reflections_touch_a_mirror():
    run = fresh_run()
    # 2 upgraded + several upgradable cards.
    up1, up2 = make_card("strike"), make_card("strike")
    up1.upgrade(); up2.upgrade()
    run.deck = [up1, up2] + [make_card("defend") for _ in range(5)]
    ev = make_event("reflections", run).begin()
    assert ev.option_keys() == ["TOUCH_A_MIRROR", "SHATTER"]
    ev.choose("TOUCH_A_MIRROR")
    # 2 downgrades then 4 upgrades across 7 cards → net 4 total upgrade levels.
    assert sum(c.upgrade_level for c in run.deck) == 4


def test_reflections_shatter_duplicates_deck_and_adds_curse():
    run = fresh_run()
    run.deck = [make_card("strike"), make_card("defend"), make_card("bash")]
    n0 = len(run.deck)
    ev = make_event("reflections", run).begin()
    ev.choose("SHATTER")
    assert len(run.deck) == 2 * n0 + 1            # duplicated + 1 Bad Luck
    assert sum(1 for c in run.deck if c.id == "bad_luck") == 1
    assert sum(1 for c in run.deck if c.id == "strike") == 2


# ── Round Tea Party ───────────────────────────────────────────────────────────


def test_round_tea_party_enjoy_tea():
    run = fresh_run()
    run.hp = 50
    ev = make_event("round_tea_party", run).begin()
    assert ev.option_keys() == ["ENJOY_TEA", "PICK_FIGHT"]
    ev.choose("ENJOY_TEA")
    assert any(r.id == "royal_poison" for r in run.relics)
    assert run.hp == run.max_hp                    # healed to full


def test_round_tea_party_pick_fight():
    run = fresh_run()
    hp0 = run.hp
    relics0 = len(run.relics)
    ev = make_event("round_tea_party", run).begin()
    ev.choose("PICK_FIGHT")
    assert ev.option_keys() == ["CONTINUE_FIGHT"]
    ev.choose("CONTINUE_FIGHT")
    assert run.hp == hp0 - 11
    assert len(run.relics) == relics0 + 1


# ── Trial ─────────────────────────────────────────────────────────────────────


def _trial_forced(run, roll):
    """Begin Trial and force the sub-trial roll to `roll` (0/1/2)."""
    ev = make_event("trial", run).begin()

    class _Fixed:
        def randrange(self, _n):
            return roll
    ev.rng = _Fixed()
    ev.choose("ACCEPT")
    return ev


def test_trial_reject_double_down_kills():
    run = fresh_run()
    ev = make_event("trial", run).begin()
    ev.choose("REJECT")
    assert ev.option_keys() == ["ACCEPT", "DOUBLE_DOWN"]
    ev.choose("DOUBLE_DOWN")
    assert run.is_dead and ev.finished


def test_trial_merchant():
    run = fresh_run()
    ev = _trial_forced(run, 0)
    assert ev.page == "MERCHANT"
    relics0 = len(run.relics)
    ev.choose("GUILTY")
    assert any(c.id == "regret" for c in run.deck)
    assert len(run.relics) == relics0 + 2
    assert ev.page == "MERCHANT_GUILTY"

    run = fresh_run()
    run.deck = [make_card("strike"), make_card("defend"), make_card("bash")]
    ev = _trial_forced(run, 0)
    ev.choose("INNOCENT")
    assert any(c.id == "shame" for c in run.deck)
    assert sum(c.upgrade_level for c in run.deck) == 2


def test_trial_noble():
    run = fresh_run()
    run.hp = 50
    _trial_forced(run, 1).choose("GUILTY")
    assert run.hp == 60                            # healed 10

    run = fresh_run()
    gold0 = run.gold
    ev = _trial_forced(run, 1)
    ev.choose("INNOCENT")
    assert any(c.id == "regret" for c in run.deck)
    assert run.gold == gold0 + 300


def test_trial_nondescript():
    run = fresh_run()
    _trial_forced(run, 2).choose("GUILTY")
    assert any(c.id == "doubt" for c in run.deck)

    run = fresh_run()
    run.deck = [make_card("strike"), make_card("defend"), make_card("bash")]
    ev = _trial_forced(run, 2)
    ev.choose("INNOCENT")
    assert sum(1 for c in run.deck if c.id == "doubt") == 1
    # 2 originals were transformed away (deck size unchanged: doubt + 3 cards).
    assert len(run.deck) == 4


# ── Tinker Time ───────────────────────────────────────────────────────────────


def test_tinker_time_builds_mad_science():
    run = fresh_run()
    ev = make_event("tinker_time", run).begin()
    assert ev.option_keys() == ["CHOOSE_CARD_TYPE"]
    ev.choose("CHOOSE_CARD_TYPE")
    # Two of the three card types are offered.
    assert len(ev.option_keys()) == 2
    assert set(ev.option_keys()) <= {"ATTACK", "SKILL", "POWER"}
    type_key = ev.option_keys()[0]
    ev.choose(type_key)
    # Two riders offered.
    assert len(ev.option_keys()) == 2
    ev.choose(ev.option_keys()[0])
    assert ev.finished
    made = [c for c in run.deck if c.id == "mad_science"]
    assert len(made) == 1
    assert made[0].card_type == CardType[type_key]


def test_tinker_time_offers_the_games_shuffled_types_and_riders():
    """TinkerTime.cs builds BOTH option screens with
    `<list>.TakeRandom(2, base.Rng)` == `UnstableShuffle(rng).Take(2)`
    (IEnumerableExtensions.cs:19) on the per-EVENT Rng (EventModel ctor: run
    seed + the event id's deterministic hash). That is a full Fisher-Yates of
    the 3-element list followed by the first two - a different draw count AND a
    different order from `rng.sample`, so a recording's `ChooseEventOption 0`
    otherwise lands on the wrong card type (933T39V18D floor_49 line 460 chose
    POWER; the sim was offering SKILL first, and the resulting Mad Science was
    a Skill - which the run's Toxic Egg then upgraded)."""
    from sts2_rl.events.tinker_time import _TYPE_KEYS, _TYPE_RIDERS
    from sts2_rl.rng import make_event_rng

    run = RunState(string_seed="933T39V18D")
    er = make_event_rng(run.rng_set.seed, "TINKER_TIME")

    want_types = list(_TYPE_RIDERS)                  # Attack, Skill, Power
    er.shuffle(want_types)
    ev = make_event("tinker_time", run).begin()
    ev.choose("CHOOSE_CARD_TYPE")
    assert ev.option_keys() == [_TYPE_KEYS[t] for t in want_types[:2]]

    chosen = want_types[0]
    want_riders = list(_TYPE_RIDERS[chosen])
    er.shuffle(want_riders)
    ev.choose(_TYPE_KEYS[chosen])
    assert ev.option_keys() == [r.upper() for r in want_riders[:2]]


# ── Mad Science card in combat ────────────────────────────────────────────────


def test_mad_science_attack_violence():
    combat = build_combat([mad(CardType.ATTACK, "violence"), "defend", "defend", "defend", "defend"])
    enemy = combat.enemies[0]
    hp0 = enemy.hp
    combat.play_card(hand_index(combat, "mad_science"), target_idx=0)
    assert hp0 - enemy.hp == 36                    # 12 x 3 hits


def test_mad_science_attack_sapping():
    combat = build_combat([mad(CardType.ATTACK, "sapping"), "defend", "defend", "defend", "defend"])
    enemy = combat.enemies[0]
    combat.play_card(hand_index(combat, "mad_science"), target_idx=0)
    assert enemy.powers["weak"].amount == 2
    assert enemy.powers["vulnerable"].amount == 2


def test_mad_science_attack_choking_strangle():
    combat = build_combat(
        [mad(CardType.ATTACK, "choking"), "strike", "defend", "defend", "defend"],
        encounter=BATTLEWORN_DUMMY_SETTING_3,
    )
    enemy = combat.enemies[0]
    combat.play_card(hand_index(combat, "mad_science"), target_idx=0)
    assert enemy.powers["strangle"].amount == 6
    # Strangle triggers on the next card played (Strike 6 + Strangle 6 = 12).
    hp0 = enemy.hp
    combat.play_card(hand_index(combat, "strike"), target_idx=0)
    assert hp0 - enemy.hp == 12
    # Strangle expires at the end of the enemy turn.
    combat.end_turn()
    assert "strangle" not in enemy.powers


def test_mad_science_skill_riders():
    # Energized: +8 block, +2 energy.
    combat = build_combat([mad(CardType.SKILL, "energized"), "defend", "defend", "defend", "defend"])
    e0 = combat.player.energy
    combat.play_card(hand_index(combat, "mad_science"))
    assert combat.player.block == 8
    assert combat.player.energy == e0 - 1 + 2       # spent 1 to play, gained 2

    # Wisdom: draw 3.
    combat = build_combat([mad(CardType.SKILL, "wisdom")] + ["strike"] * 8)
    hand0 = len(combat.player.hand)
    combat.play_card(hand_index(combat, "mad_science"))
    assert len(combat.player.hand) == (hand0 - 1) + 3


def test_mad_science_power_riders():
    # Expertise: Strength 2 + Dexterity 2.
    combat = build_combat([mad(CardType.POWER, "expertise"), "defend", "defend", "defend", "defend"])
    combat.play_card(hand_index(combat, "mad_science"))
    assert combat.player.powers["strength"].amount == 2
    assert combat.player.powers["dexterity"].amount == 2

    # Curious: Power cards cost 1 less.
    combat = build_combat([mad(CardType.POWER, "curious"), "inflame", "defend", "defend", "defend"])
    combat.play_card(hand_index(combat, "mad_science"))
    inflame = next(c for c in combat.player.hand if c.id == "inflame")
    assert combat.hooks.modify_card_energy_cost(inflame, inflame.energy_cost) == 0

    # Improvement: the power lands (its after-combat upgrade is a documented stub).
    combat = build_combat([mad(CardType.POWER, "improvement"), "defend", "defend", "defend", "defend"])
    combat.play_card(hand_index(combat, "mad_science"))
    assert "improvement" in combat.player.powers


def test_mad_science_upgrade_is_innate():
    card = mad(CardType.ATTACK, "violence")
    assert card.innate is False
    card.upgrade()
    assert card.innate is True
    card.downgrade()
    assert card.innate is False and card.tinker_type == CardType.ATTACK


# ── Relics & enchantment ──────────────────────────────────────────────────────


def test_forgotten_soul_damages_on_exhaust():
    combat = build_combat(["strike"] * 5, encounter=BATTLEWORN_DUMMY_SETTING_1,
                          relics=[make_relic("forgotten_soul")])
    enemy = combat.enemies[0]
    hp0 = enemy.hp
    ExhaustCmd.exhaust(combat.hooks, combat.player, combat.player.hand[0])
    assert hp0 - enemy.hp == 1


def test_royal_poison_first_turn_hp_loss():
    combat = build_combat(["defend"] * 5, relics=[make_relic("royal_poison")])
    assert combat.player.max_hp - combat.player.hp == 4


def test_big_mushroom_first_turn_draw_reduction():
    combat = build_combat(["strike"] * 10, relics=[make_relic("big_mushroom")])
    assert len(combat.player.hand) == combat.player.DRAW_PER_TURN - 2


def test_souls_enchantment_requires_and_removes_exhaust():
    assert not SoulsEnchantment.can_enchant(make_card("strike"))   # no Exhaust
    offering = make_card("offering")
    assert SoulsEnchantment.can_enchant(offering)
    make_enchantment("souls").attach(offering)
    assert offering.exhausts is False


# ── Deterministic full-pool smoke ─────────────────────────────────────────────


@pytest.mark.parametrize("eid", GLORY_EVENTS)
def test_every_glory_event_drives_to_completion(eid):
    for seed in range(12):
        run = RunState(rng=random.Random(seed), gold=400, total_floor=15)
        run.add_card(make_card("offering"))         # an Exhaust card for gates
        up = make_card("strike"); up.upgrade()
        run.add_card(up)                            # an upgraded card for Reflections
        ev = make_event(eid, run).begin()
        steps = 0
        while not ev.finished and ev.pending_encounter is None:
            keys = [o.key for o in ev.options if not o.locked]
            if not keys:
                break
            ev.choose(keys[-1])
            steps += 1
            assert steps < 20, f"{eid} did not terminate"
        assert ev.finished or ev.pending_encounter is not None
