"""
Tests for the Glory (Act 3) enemies and their powers (Paper Cuts, Stock,
Rampart, Galvanic, Soar, Possess Strength/Speed, Dampen, Hex, High Voltage,
Withering Presence, Chains of Binding, Adaptable, Painful Stabs, Nemesis).

Run with:  py -m pytest test/test_glory.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import make_card
from sts2_rl.monsters import Encounter, MoveType
from sts2_rl.monsters.glory import (
    Aeonglass,
    Axebot,
    DevotedSculptor,
    Fabricator,
    FrogKnight,
    GlobeHead,
    Guardbot,
    LivingShield,
    MagiKnight,
    MechaKnight,
    Noisebot,
    OwlMagistrate,
    Queen,
    ScrollOfBiting,
    SlimedBerserker,
    SoulNexus,
    SpectralKnight,
    Stabbot,
    TheForgotten,
    TheLost,
    TorchHeadAmalgam,
    TurretOperator,
    Zapbot,
    AEONGLASS_BOSS,
    AXEBOTS_NORMAL,
    CONSTRUCT_MENAGERIE_NORMAL,
    DEVOTED_SCULPTOR_WEAK,
    ENCOUNTERS,
    FABRICATOR_NORMAL,
    KNIGHTS_ELITE,
    QUEEN_BOSS,
    SCROLLS_OF_BITING_NORMAL,
    SCROLLS_OF_BITING_WEAK,
    TURRET_OPERATOR_WEAK,
)
from sts2_rl.valueprops import DamageProps


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh_with(monster_cls, seed: int = 0, deck=None) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc, starting_deck=deck)


def fresh_encounter(enc: Encounter, seed: int = 0, deck=None) -> CombatState:
    return CombatState(rng=random.Random(seed), encounter=enc, starting_deck=deck)


def kill(cs: CombatState, creature) -> None:
    DamageCmd.deal(cs.hooks, creature, 99999, props=DamageProps.NON_CARD_UNPOWERED)


def living(cs: CombatState):
    return [e for e in cs.enemies if not e.is_gone]


# ═════════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════════

def test_registry_has_all_18_encounters():
    assert len(ENCOUNTERS) == 18


# ═════════════════════════════════════════════════════════════════════════
# Devoted Sculptor
# ═════════════════════════════════════════════════════════════════════════

class TestDevotedSculptor:
    def test_hp(self):
        for seed in range(5):
            assert fresh_with(DevotedSculptor, seed).enemy.max_hp == 162

    def test_incantation_then_scaling_savage(self):
        cs = fresh_with(DevotedSculptor)
        assert cs.enemy.current_intent.move_type == MoveType.BUFF
        cs.end_turn()  # Forbidden Incantation -> Ritual 9 triggers at turn end
        assert cs.enemy.powers["strength"].amount == 9
        cs.end_turn()  # Savage 12 + 9 Strength = 21
        assert cs.player.hp == 80 - 21
        assert cs.enemy.powers["strength"].amount == 18


# ═════════════════════════════════════════════════════════════════════════
# Scrolls of Biting
# ═════════════════════════════════════════════════════════════════════════

class TestScrollsOfBiting:
    def test_hp_range(self):
        for seed in range(10):
            assert 30 <= fresh_with(ScrollOfBiting, seed).enemy.max_hp <= 37

    def test_encounter_counts(self):
        assert len(fresh_encounter(SCROLLS_OF_BITING_WEAK).enemies) == 3
        assert len(fresh_encounter(SCROLLS_OF_BITING_NORMAL).enemies) == 4

    def test_staggered_starting_moves(self):
        cs = fresh_encounter(SCROLLS_OF_BITING_WEAK)
        idxs = {e._starter_move_idx % 3 for e in cs.enemies}
        assert idxs == {0, 1, 2}

    def test_normal_fourth_scroll_starts_on_more_teeth(self):
        cs = fresh_encounter(SCROLLS_OF_BITING_NORMAL)
        assert cs.enemies[3]._starter_move_idx == 2

    def test_paper_cuts_costs_max_hp(self):
        # A scroll that opens on Chomp deals 14 (unblocked) and Paper Cuts 2
        # removes 2 max HP from the player.
        enc = Encounter("t", [lambda h, r: ScrollOfBiting(h, r, starter_move_idx=0)])
        cs = CombatState(rng=random.Random(0), encounter=enc)
        assert "paper_cuts" in cs.enemy.powers
        mhp = cs.player.max_hp
        cs.end_turn()  # Chomp 14 unblocked -> lose 2 max HP
        assert cs.player.max_hp == mhp - 2

    def test_more_teeth_grants_strength(self):
        enc = Encounter("t", [lambda h, r: ScrollOfBiting(h, r, starter_move_idx=2)])
        cs = CombatState(rng=random.Random(0), encounter=enc)
        assert cs.enemy.current_intent.move_type == MoveType.BUFF
        cs.end_turn()  # More Teeth
        assert cs.enemy.powers["strength"].amount == 2


# ═════════════════════════════════════════════════════════════════════════
# Turret Operator + Living Shield
# ═════════════════════════════════════════════════════════════════════════

class TestTurretOperator:
    def test_encounter(self):
        cs = fresh_encounter(TURRET_OPERATOR_WEAK)
        assert isinstance(cs.enemies[0], LivingShield)
        assert isinstance(cs.enemies[1], TurretOperator)

    def test_hp(self):
        assert fresh_with(LivingShield).enemy.max_hp == 55
        assert fresh_with(TurretOperator).enemy.max_hp == 41

    def test_rampart_shields_turret(self):
        cs = fresh_encounter(TURRET_OPERATOR_WEAK)
        turret = cs.enemies[1]
        assert turret.block == 25  # Rampart shields at the start of the player turn
        cs.end_turn()
        assert turret.block == 25  # re-shielded each player turn

    def test_turret_unload(self):
        cs = fresh_with(TurretOperator)
        assert cs.enemy.current_intent.total_damage == 15  # 3×5
        cs.end_turn()
        assert cs.player.hp == 80 - 15

    def test_living_shield_smashes_when_alone(self):
        cs = fresh_with(LivingShield)  # opens on Shield Slam, then Smash (alone)
        cs.end_turn()  # Shield Slam 6
        assert cs.player.hp == 80 - 6
        cs.end_turn()  # branch: no allies -> Smash 16 + enrage
        assert cs.player.hp == 80 - 6 - 16
        assert cs.enemy.powers["strength"].amount == 3


# ═════════════════════════════════════════════════════════════════════════
# Axebot
# ═════════════════════════════════════════════════════════════════════════

class TestAxebot:
    def test_hp(self):
        for seed in range(10):
            assert 70 <= fresh_with(Axebot, seed).enemy.max_hp <= 78

    def test_starts_with_stock(self):
        assert fresh_with(Axebot).enemy.powers["stock"].amount == 2

    def test_first_bot_opens_on_hammer(self):
        cs = fresh_with(Axebot)
        intent = cs.enemy.current_intent
        assert intent.move_type == MoveType.ATTACK and intent.damage == 12
        cs.end_turn()  # Hammer Uppercut: Weak 2 + Frail 2
        assert cs.player.powers["weak"].amount == 2
        assert cs.player.powers["frail"].amount == 2

    def test_stock_respawn_chain(self):
        cs = fresh_with(Axebot)
        kill(cs, cs.enemy)
        bot = living(cs)[0]
        assert bot.powers["stock"].amount == 1
        assert bot.current_intent.move_type == MoveType.DEFEND  # respawn boots up
        kill(cs, bot)
        bot = living(cs)[0]
        assert "stock" not in bot.powers  # stock 0 -> final bot
        kill(cs, bot)
        assert cs._all_enemies_dead()

    def test_respawn_bootup_scales_strength(self):
        cs = fresh_with(Axebot)
        kill(cs, cs.enemy)
        bot = living(cs)[0]  # stock 1
        cs.end_turn()  # Boot Up: 10 block + 3×(2-1)=3 Strength
        assert bot.powers["strength"].amount == 3
        assert bot.block == 10


# ═════════════════════════════════════════════════════════════════════════
# Construct Menagerie
# ═════════════════════════════════════════════════════════════════════════

def test_construct_menagerie_composition():
    cs = fresh_encounter(CONSTRUCT_MENAGERIE_NORMAL)
    names = [type(e).__name__ for e in cs.enemies]
    assert names == ["PunchConstruct", "CubexConstruct", "CubexConstruct"]


# ═════════════════════════════════════════════════════════════════════════
# Fabricator
# ═════════════════════════════════════════════════════════════════════════

class TestFabricator:
    def test_hp(self):
        assert fresh_with(Fabricator).enemy.max_hp == 150

    def test_summons_minions(self):
        cs = fresh_with(Fabricator)
        # Drive turns until the fabricator has fabricated at least once.
        for _ in range(3):
            cs.end_turn()
        bots = [e for e in cs.enemies if not isinstance(e, Fabricator)]
        assert bots, "expected summoned bots"
        assert all("minion" in b.powers for b in bots)

    def test_stops_fabricating_when_full(self):
        cs = fresh_with(Fabricator)
        for _ in range(12):
            if cs.is_over:
                break
            cs.end_turn()
            # Fabricate summons two bots at once, so the field can briefly reach
            # five before the Fabricator switches to Disintegrate.
            assert sum(1 for e in cs.enemies if not e.is_gone) <= 5

    def test_bot_kinds(self):
        for kind in (Guardbot, Noisebot, Stabbot, Zapbot):
            assert 16 <= fresh_with(kind).enemy.max_hp <= 23

    def test_zapbot_high_voltage(self):
        cs = fresh_with(Zapbot)
        assert "high_voltage" in cs.enemy.powers
        cs.end_turn()  # gains 2 Strength at end of its turn
        assert cs.enemy.powers["strength"].amount == 2


# ═════════════════════════════════════════════════════════════════════════
# Frog Knight
# ═════════════════════════════════════════════════════════════════════════

class TestFrogKnight:
    def test_hp_and_plating(self):
        cs = fresh_with(FrogKnight)
        assert cs.enemy.max_hp == 191
        assert cs.enemy.powers["plating"].amount == 15

    def test_opening_cycle(self):
        cs = fresh_with(FrogKnight)
        cs.end_turn()  # Tongue Lash 13 + Frail 2
        assert cs.player.hp == 80 - 13
        assert cs.player.powers["frail"].amount == 2
        cs.end_turn()  # Strike Down Evil 21
        assert cs.player.hp == 80 - 13 - 21

    def test_beetle_charge_below_half(self):
        cs = fresh_with(FrogKnight)
        cs.enemy.hp = 50  # below half of 191
        # Advance to a branch evaluation: For the Queen -> branch -> Beetle Charge
        intents = []
        for _ in range(6):
            intents.append(cs.enemy.current_intent.damage)
            cs.end_turn()
            if cs.enemy._has_beetle_charged:
                break
        assert cs.enemy._has_beetle_charged


# ═════════════════════════════════════════════════════════════════════════
# Globe Head
# ═════════════════════════════════════════════════════════════════════════

class TestGlobeHead:
    def test_hp_and_galvanic(self):
        cs = fresh_with(GlobeHead)
        assert cs.enemy.max_hp == 148
        assert "galvanic" in cs.enemy.powers

    def test_afflicts_power_cards(self):
        deck = [make_card("strike") for _ in range(4)] + [make_card("inflame")]
        cs = fresh_with(GlobeHead, deck=deck)
        powers = [c for c in cs.player.all_cards if c.card_type.name == "POWER"]
        assert powers and all(
            c.affliction is not None and c.affliction.id == "galvanized" for c in powers
        )

    def test_galvanized_card_zaps_player(self):
        deck = [make_card("inflame")] + [make_card("strike") for _ in range(4)]
        cs = fresh_with(GlobeHead, deck=deck, seed=2)
        inflame = next(c for c in cs.player.hand if c.id == "inflame")
        hp0 = cs.player.hp
        idx = cs.player.hand.index(inflame)
        cs.player.energy = 3
        cs.play_card(idx)
        assert cs.player.hp == hp0 - 6  # Galvanic 6

    def test_move_cycle(self):
        cs = fresh_with(GlobeHead)
        cs.end_turn()  # Shocking Slap 13 + Frail 2
        assert cs.player.hp == 80 - 13
        assert cs.player.powers["frail"].amount == 2
        cs.end_turn()  # Thunder Strike 6×3
        assert cs.player.hp == 80 - 13 - 18


# ═════════════════════════════════════════════════════════════════════════
# Owl Magistrate
# ═════════════════════════════════════════════════════════════════════════

class TestOwlMagistrate:
    def test_hp(self):
        assert fresh_with(OwlMagistrate).enemy.max_hp == 231

    def test_soar_halves_damage_then_verdict_removes_it(self):
        cs = fresh_with(OwlMagistrate)
        cs.end_turn()  # Scrutiny
        cs.end_turn()  # Peck
        cs.end_turn()  # Judicial Flight -> Soar
        owl = cs.enemy
        assert "soar" in owl.powers
        dealt = DamageCmd.deal(cs.hooks, owl, 20, dealer=cs.player, props=DamageProps.CARD)
        assert dealt == 10  # halved
        cs.end_turn()  # Verdict: 33 + Vulnerable 4, Soar removed
        assert "soar" not in owl.powers
        assert cs.player.powers["vulnerable"].amount == 4


# ═════════════════════════════════════════════════════════════════════════
# Slimed Berserker
# ═════════════════════════════════════════════════════════════════════════

class TestSlimedBerserker:
    def test_hp(self):
        assert fresh_with(SlimedBerserker).enemy.max_hp == 261

    def test_vomit_adds_slimed(self):
        cs = fresh_with(SlimedBerserker)
        cs.end_turn()  # Vomit Ichor: 10 Slimed added to combat
        slimed = [c for c in cs.player.all_cards if c.id == "slimed"]
        assert len(slimed) == 10

    def test_leeching_hug(self):
        cs = fresh_with(SlimedBerserker)
        cs.end_turn()  # Vomit
        cs.end_turn()  # Pummeling
        cs.end_turn()  # Leeching Hug: Weak 3 + gain 3 Strength
        assert cs.player.powers["weak"].amount == 3
        assert cs.enemy.powers["strength"].amount == 3


# ═════════════════════════════════════════════════════════════════════════
# The Lost & The Forgotten
# ═════════════════════════════════════════════════════════════════════════

class TestLostAndForgotten:
    def test_hp(self):
        cs = fresh_encounter(ENCOUNTERS["the_lost_and_forgotten"])
        assert isinstance(cs.enemies[0], TheLost) and cs.enemies[0].max_hp == 93
        assert isinstance(cs.enemies[1], TheForgotten) and cs.enemies[1].max_hp == 106

    def test_lost_steals_and_returns_strength(self):
        cs = fresh_with(TheLost)
        cs.end_turn()  # Debilitating Smog: player -2 Str, Lost +2 Str
        assert cs.player.powers["strength"].amount == -2
        assert cs.enemy.powers["strength"].amount == 2
        kill(cs, cs.enemy)
        s = cs.player.powers.get("strength")
        assert s is None or s.amount == 0  # Strength returned

    def test_forgotten_steals_dexterity_and_dread_scales(self):
        cs = fresh_with(TheForgotten)
        cs.end_turn()  # Miasma: player -2 Dex, self +2 Dex, gain 8 block
        assert cs.player.powers["dexterity"].amount == -2
        assert cs.enemy.powers["dexterity"].amount == 2
        # Dread telegraphs 13 + own Dexterity (2) = 15
        assert cs.enemy.current_intent.damage == 15
        kill(cs, cs.enemy)
        d = cs.player.powers.get("dexterity")
        assert d is None or d.amount == 0


# ═════════════════════════════════════════════════════════════════════════
# Knights (elite)
# ═════════════════════════════════════════════════════════════════════════

class TestKnights:
    def test_composition(self):
        cs = fresh_encounter(KNIGHTS_ELITE)
        names = [type(e).__name__ for e in cs.enemies]
        assert names == ["FlailKnight", "SpectralKnight", "MagiKnight"]

    def test_magi_knight_dampen_downgrades_then_restores(self):
        deck = [make_card("strike") for _ in range(4)]
        deck[0].upgrade()
        cs = fresh_with(MagiKnight, deck=deck)
        assert deck[0].upgrade_level == 1
        cs.end_turn()  # Power Shield
        cs.end_turn()  # Dampen -> downgrade the +1 card
        assert deck[0].upgrade_level == 0
        assert "dampen" in cs.player.powers
        kill(cs, cs.enemy)
        assert deck[0].upgrade_level == 1  # restored on death

    def test_spectral_knight_hex_makes_cards_ethereal(self):
        deck = [make_card("strike") for _ in range(4)]
        cs = fresh_with(SpectralKnight, deck=deck)
        cs.end_turn()  # Hex -> all player cards afflicted + Ethereal
        assert all(c.affliction and c.affliction.id == "hexed" for c in cs.player.all_cards)
        assert all(c.is_ethereal for c in cs.player.all_cards)
        kill(cs, cs.enemy)
        assert all(c.affliction is None for c in cs.player.all_cards)
        assert all(not c.is_ethereal for c in cs.player.all_cards)


# ═════════════════════════════════════════════════════════════════════════
# Mecha Knight (elite)
# ═════════════════════════════════════════════════════════════════════════

class TestMechaKnight:
    def test_hp_and_artifact(self):
        cs = fresh_with(MechaKnight)
        assert cs.enemy.max_hp == 300
        assert cs.enemy.powers["artifact"].amount == 3

    def test_charge_then_flamethrower(self):
        cs = fresh_with(MechaKnight)
        cs.end_turn()  # Charge 25
        assert cs.player.hp == 80 - 25
        cs.end_turn()  # Flamethrower: 4 Burn to hand
        assert sum(1 for c in cs.player.all_cards if c.id == "burn") == 4


# ═════════════════════════════════════════════════════════════════════════
# Soul Nexus (elite)
# ═════════════════════════════════════════════════════════════════════════

class TestSoulNexus:
    def test_hp(self):
        assert fresh_with(SoulNexus).enemy.max_hp == 234

    def test_opens_with_soul_burn(self):
        cs = fresh_with(SoulNexus)
        assert cs.enemy.current_intent.damage == 29
        cs.end_turn()
        assert cs.player.hp == 80 - 29

    def test_drain_life_debuffs(self):
        # Drive several turns; when Drain Life fires it applies Vulnerable + Weak.
        cs = fresh_with(SoulNexus)
        for _ in range(6):
            if cs.enemy.current_intent.has(MoveType.DEBUFF_STRONG):
                cs.end_turn()
                assert cs.player.powers["vulnerable"].amount >= 2
                assert cs.player.powers["weak"].amount >= 2
                return
            cs.end_turn()


# ═════════════════════════════════════════════════════════════════════════
# Aeonglass (boss)
# ═════════════════════════════════════════════════════════════════════════

class TestAeonglass:
    def test_hp_and_powers(self):
        cs = fresh_encounter(AEONGLASS_BOSS)
        assert cs.enemy.max_hp == 512
        assert "withering_presence" in cs.enemy.powers
        assert cs.enemy.powers["artifact"].amount == 3

    def test_ebb_gains_block(self):
        cs = fresh_encounter(AEONGLASS_BOSS)
        cs.end_turn()  # Ebb: 26 + 33 block
        assert cs.player.hp == 80 - 26
        assert cs.enemy.block == 33

    def test_increasing_intensity_adds_wither(self):
        cs = fresh_encounter(AEONGLASS_BOSS)
        cs.end_turn()  # Ebb
        cs.end_turn()  # Eye Lasers
        cs.end_turn()  # Increasing Intensity: +1 Wither, +3 Strength
        withers = [c for c in cs.player.all_cards if c.id == "wither"]
        assert len(withers) == 1
        assert cs.enemy.powers["strength"].amount == 3

    def test_withering_presence_adds_wither_every_six_plays(self):
        deck = [make_card("strike") for _ in range(12)]
        cs = fresh_encounter(AEONGLASS_BOSS, deck=deck, seed=1)
        played = 0
        for _turn in range(4):
            cs.player.energy = 20
            while cs.player.hand and played < 6:
                strike = next((c for c in cs.player.hand if c.id == "strike"), None)
                if strike is None:
                    break
                cs.play_card(cs.player.hand.index(strike))
                played += 1
            if played >= 6 or cs.is_over:
                break
            cs.end_turn()  # redraw a fresh hand
        assert any(c.id == "wither" for c in cs.player.all_cards)


# ═════════════════════════════════════════════════════════════════════════
# Queen (boss)
# ═════════════════════════════════════════════════════════════════════════

class TestQueen:
    def test_composition(self):
        cs = fresh_encounter(QUEEN_BOSS)
        assert isinstance(cs.enemies[0], TorchHeadAmalgam)
        assert isinstance(cs.enemies[1], Queen)
        assert cs.enemies[0].max_hp == 199 and cs.enemies[1].max_hp == 400

    def test_amalgam_is_minion(self):
        cs = fresh_encounter(QUEEN_BOSS)
        assert "minion" in cs.enemies[0].powers

    def test_puppet_strings_binds_and_you_are_mine(self):
        cs = fresh_encounter(QUEEN_BOSS)
        cs.end_turn()  # amalgam Tackle + Queen Puppet Strings (Chains of Binding)
        assert "chains_of_binding" in cs.player.powers
        cs.end_turn()  # You Are Mine: Frail/Weak/Vulnerable 99
        assert cs.player.powers["frail"].amount == 99
        assert cs.player.powers["weak"].amount == 99
        assert cs.player.powers["vulnerable"].amount == 99

    def test_amalgam_death_re_telegraphs_burn_bright_as_enrage(self):
        # Queen.cs:221-234 AfterDeath: the amalgam's death immediately replaces
        # a telegraphed Burn Bright with Enrage (SetMoveImmediate(EnragedState)
        # = NextMove = state + ForceCurrentState, MonsterModel.cs:420-432), so
        # the player never sees Burn Bright resolve as Enrage.
        cs = fresh_encounter(QUEEN_BOSS)
        queen = cs.enemies[1]
        cs.end_turn()  # PUPPET_STRINGS
        cs.end_turn()  # YOU_ARE_MINE -> branch telegraphs BURN_BRIGHT
        assert queen._current_move.id == "BURN_BRIGHT_FOR_ME_MOVE"
        log_before = list(queen.machine.state_log)
        kill(cs, cs.enemies[0])  # amalgam dies mid-player-turn
        assert queen._current_move.id == "ENRAGE_MOVE"
        assert queen.current_intent.move_type == MoveType.BUFF
        assert queen.current_intent.also == ()  # no DEFEND leg any more
        # ForceCurrentState does not log.
        assert list(queen.machine.state_log) == log_before
        cs.end_turn()  # ENRAGE: +2 Strength, no block
        assert queen.strength == 2
        assert queen.block == 0
        assert queen._current_move.id == "OFF_WITH_YOUR_HEAD_MOVE"

    def test_queen_switches_to_attacks_when_amalgam_dead(self):
        cs = fresh_encounter(QUEEN_BOSS)
        queen = cs.enemies[1]
        kill(cs, cs.enemies[0])  # kill the amalgam
        # Burn Bright branch now routes to Off With Your Head (an attack).
        for _ in range(6):
            cs.end_turn()
            if queen.current_intent.move_type == MoveType.ATTACK:
                return
        assert False, "Queen should attack once the amalgam is dead"


# ═════════════════════════════════════════════════════════════════════════
# Test Subject (boss)
# ═════════════════════════════════════════════════════════════════════════

class TestTestSubject:
    def test_hp_and_powers(self):
        cs = fresh_encounter(ENCOUNTERS["test_subject"])
        assert cs.enemy.max_hp == 100
        assert "adaptable" in cs.enemy.powers
        assert cs.enemy.powers["enrage"].amount == 2

    def test_three_phase_respawn(self):
        cs = fresh_encounter(ENCOUNTERS["test_subject"])
        ts = cs.enemy
        kill(cs, ts)
        assert ts.powers["adaptable"].is_reviving and not cs._all_enemies_dead()
        cs.end_turn()  # Respawn -> 200 HP, Painful Stabs
        assert ts.max_hp == 200 and "painful_stabs" in ts.powers
        kill(cs, ts)
        cs.end_turn()  # Respawn -> 300 HP, Nemesis, Adaptable removed
        assert ts.max_hp == 300 and "nemesis" in ts.powers and "adaptable" not in ts.powers
        # Nemesis grants Intangible every other turn; clear it so the killing
        # blow lands. With Adaptable gone, the third death is final.
        if "intangible" in ts.powers:
            PowerCmd.remove(cs.hooks, ts, "intangible")
        kill(cs, ts)
        assert cs._all_enemies_dead()

    def test_reviving_blocks_hits(self):
        cs = fresh_encounter(ENCOUNTERS["test_subject"])
        ts = cs.enemy
        kill(cs, ts)
        # while reviving, further damage is ignored
        dealt = DamageCmd.deal(cs.hooks, ts, 50, dealer=cs.player, props=DamageProps.CARD)
        assert dealt == 0
