"""Wave b00 ascension spot tests (Task 4 monster-ascension port).

Mirrors test_ascension.py's Chomper harness: build a single-monster
CombatState at a given ascension and read `.enemy` directly. HP checks sweep
seeds where the asc-0/asc-8 ranges could otherwise coincidentally overlap;
damage/value checks call the monster's asc-aware helper method directly
(the pattern established by Chomper._clamp_dmg), checked at asc 0 and the
DeadlyEnemies (9) threshold.
"""
import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


def _combat(cls, asc: int, seed: int = 0):
    enc = Encounter(id="test_wave_b00", monster_classes=[cls])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


# ═════════════════════════════════════════════════════════════════════════
# Aeonglass (glory/aeonglass.py)
# ═════════════════════════════════════════════════════════════════════════

def test_aeonglass_tough_hp_degenerate():
    # Aeonglass.cs:28-30 -- MinInitialHp/MaxInitialHp both resolve to a fixed
    # 535 under ToughEnemies (asc 8+), vs. the base fixed 512.
    from sts2_rl.monsters.glory.aeonglass import Aeonglass
    assert _combat(Aeonglass, 7).enemy.max_hp == 512
    assert _combat(Aeonglass, 8).enemy.max_hp == 535


def test_aeonglass_deadly_values():
    from sts2_rl.monsters.glory.aeonglass import Aeonglass
    cs0 = _combat(Aeonglass, 0)
    cs9 = _combat(Aeonglass, 9)
    assert cs0.enemy._ebb_dmg() == 26 and cs9.enemy._ebb_dmg() == 32
    assert cs0.enemy._eye_lasers_dmg() == 11 and cs9.enemy._eye_lasers_dmg() == 12
    assert cs0.enemy._wither_amount() == 1 and cs9.enemy._wither_amount() == 2
    assert cs0.enemy._intensity_base_str() == 3 and cs9.enemy._intensity_base_str() == 4


# ═════════════════════════════════════════════════════════════════════════
# Axebot (glory/axebot.py)
# ═════════════════════════════════════════════════════════════════════════

def test_axebot_tough_hp():
    from sts2_rl.monsters.glory.axebot import Axebot
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _combat(Axebot, 0, seed).enemy.max_hp
        hp7 = _combat(Axebot, 7, seed).enemy.max_hp
        hp8 = _combat(Axebot, 8, seed).enemy.max_hp
        assert 70 <= hp0 <= 78
        assert 70 <= hp7 <= 78
        assert 76 <= hp8 <= 86
        seen_asc8.add(hp8)
    assert seen_asc8 & {79, 80, 81, 82, 83, 84, 85, 86}


def test_axebot_deadly_values():
    from sts2_rl.monsters.glory.axebot import Axebot
    cs0 = _combat(Axebot, 0)
    cs9 = _combat(Axebot, 9)
    assert cs0.enemy._boot_up_block() == 10 and cs9.enemy._boot_up_block() == 15
    assert cs0.enemy._boot_up_str_per_stock() == 3 and cs9.enemy._boot_up_str_per_stock() == 4
    assert cs0.enemy._one_two_dmg() == 9 and cs9.enemy._one_two_dmg() == 10
    assert cs0.enemy._hammer_dmg() == 12 and cs9.enemy._hammer_dmg() == 14


# ═════════════════════════════════════════════════════════════════════════
# Bowlbugs (hive/bowlbugs.py) -- BowlbugEgg, BowlbugNectar, BowlbugRock, BowlbugSilk
# ═════════════════════════════════════════════════════════════════════════

def test_bowlbug_rock_tough_hp_and_deadly_damage():
    from sts2_rl.monsters.hive.bowlbugs import BowlbugRock
    assert _combat(BowlbugRock, 7).enemy.max_hp in range(45, 49)
    hp8 = _combat(BowlbugRock, 8).enemy.max_hp
    assert 46 <= hp8 <= 49
    cs0, cs9 = _combat(BowlbugRock, 0), _combat(BowlbugRock, 9)
    assert cs0.enemy._headbutt_dmg() == 15 and cs9.enemy._headbutt_dmg() == 16


def test_bowlbug_egg_tough_hp_and_deadly_values():
    from sts2_rl.monsters.hive.bowlbugs import BowlbugEgg
    assert _combat(BowlbugEgg, 7).enemy.max_hp in range(21, 23)
    hp8 = _combat(BowlbugEgg, 8).enemy.max_hp
    assert 23 <= hp8 <= 24
    cs0, cs9 = _combat(BowlbugEgg, 0), _combat(BowlbugEgg, 9)
    assert cs0.enemy._bite_dmg() == 7 and cs9.enemy._bite_dmg() == 8
    assert cs0.enemy._protect_block() == 7 and cs9.enemy._protect_block() == 8


def test_bowlbug_silk_tough_hp_and_deadly_damage():
    from sts2_rl.monsters.hive.bowlbugs import BowlbugSilk
    assert _combat(BowlbugSilk, 7).enemy.max_hp in range(40, 44)
    hp8 = _combat(BowlbugSilk, 8).enemy.max_hp
    assert 41 <= hp8 <= 44
    cs0, cs9 = _combat(BowlbugSilk, 0), _combat(BowlbugSilk, 9)
    assert cs0.enemy._thrash_dmg() == 4 and cs9.enemy._thrash_dmg() == 5


def test_bowlbug_nectar_tough_hp_and_deadly_str():
    from sts2_rl.monsters.hive.bowlbugs import BowlbugNectar
    assert _combat(BowlbugNectar, 7).enemy.max_hp in range(35, 39)
    hp8 = _combat(BowlbugNectar, 8).enemy.max_hp
    assert 36 <= hp8 <= 39
    cs0, cs9 = _combat(BowlbugNectar, 0), _combat(BowlbugNectar, 9)
    assert cs0.enemy._buff_str() == 15 and cs9.enemy._buff_str() == 16


# ═════════════════════════════════════════════════════════════════════════
# Ruby Raiders (overgrowth/ruby_raiders.py) -- Assassin/Axe/Brute
# ═════════════════════════════════════════════════════════════════════════

def test_assassin_ruby_raider_tough_hp_and_deadly_damage():
    from sts2_rl.monsters.overgrowth.ruby_raiders import AssassinRubyRaider
    assert _combat(AssassinRubyRaider, 7).enemy.max_hp in range(18, 24)
    hp8 = _combat(AssassinRubyRaider, 8).enemy.max_hp
    assert 19 <= hp8 <= 24
    cs0, cs9 = _combat(AssassinRubyRaider, 0), _combat(AssassinRubyRaider, 9)
    assert cs0.enemy._killshot_dmg() == 10 and cs9.enemy._killshot_dmg() == 11


def test_axe_ruby_raider_tough_hp_and_deadly_values():
    from sts2_rl.monsters.overgrowth.ruby_raiders import AxeRubyRaider
    assert _combat(AxeRubyRaider, 7).enemy.max_hp in range(20, 23)
    hp8 = _combat(AxeRubyRaider, 8).enemy.max_hp
    assert 21 <= hp8 <= 23
    cs0, cs9 = _combat(AxeRubyRaider, 0), _combat(AxeRubyRaider, 9)
    assert cs0.enemy._swing_dmg() == 5 and cs9.enemy._swing_dmg() == 6
    assert cs0.enemy._swing_block() == 5 and cs9.enemy._swing_block() == 6
    assert cs0.enemy._big_swing_dmg() == 12 and cs9.enemy._big_swing_dmg() == 13


def test_brute_ruby_raider_tough_hp_and_deadly_damage():
    from sts2_rl.monsters.overgrowth.ruby_raiders import BruteRubyRaider
    assert _combat(BruteRubyRaider, 7).enemy.max_hp in range(30, 34)
    hp8 = _combat(BruteRubyRaider, 8).enemy.max_hp
    assert 31 <= hp8 <= 34
    cs0, cs9 = _combat(BruteRubyRaider, 0), _combat(BruteRubyRaider, 9)
    assert cs0.enemy._beat_dmg() == 7 and cs9.enemy._beat_dmg() == 8


# ═════════════════════════════════════════════════════════════════════════
# BygoneEffigy (overgrowth/bygone_effigy.py)
# ═════════════════════════════════════════════════════════════════════════

def test_bygone_effigy_tough_hp_degenerate_and_deadly_damage():
    from sts2_rl.monsters.overgrowth.bygone_effigy import BygoneEffigy
    assert _combat(BygoneEffigy, 7).enemy.max_hp == 127
    assert _combat(BygoneEffigy, 8).enemy.max_hp == 132
    cs0, cs9 = _combat(BygoneEffigy, 0), _combat(BygoneEffigy, 9)
    assert cs0.enemy._slash_dmg() == 13 and cs9.enemy._slash_dmg() == 15


# ═════════════════════════════════════════════════════════════════════════
# Byrdonis (overgrowth/byrdonis.py)
# ═════════════════════════════════════════════════════════════════════════

def test_byrdonis_tough_hp_degenerate_and_deadly_damage():
    from sts2_rl.monsters.overgrowth.byrdonis import Byrdonis
    assert _combat(Byrdonis, 7).enemy.max_hp in range(81, 85)
    assert _combat(Byrdonis, 8).enemy.max_hp == 90
    cs0, cs9 = _combat(Byrdonis, 0), _combat(Byrdonis, 9)
    assert cs0.enemy._peck_dmg() == 3 and cs9.enemy._peck_dmg() == 4
    assert cs0.enemy._swoop_dmg() == 17 and cs9.enemy._swoop_dmg() == 19


# ═════════════════════════════════════════════════════════════════════════
# CalcifiedCultist (underdocks/cultists.py)
# ═════════════════════════════════════════════════════════════════════════

def test_calcified_cultist_tough_hp_and_deadly_damage():
    from sts2_rl.monsters.underdocks.cultists import CalcifiedCultist
    assert _combat(CalcifiedCultist, 7).enemy.max_hp in range(38, 42)
    hp8 = _combat(CalcifiedCultist, 8).enemy.max_hp
    assert 39 <= hp8 <= 42
    cs0, cs9 = _combat(CalcifiedCultist, 0), _combat(CalcifiedCultist, 9)
    assert cs0.enemy._dark_strike_dmg() == 9 and cs9.enemy._dark_strike_dmg() == 11
