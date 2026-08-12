"""Ascension spot-tests for wave batch-06 (Task 4 monster-ascension port).

Twelve monsters: SneakyGremlin, SoulFysh, SoulNexus, SpectralKnight,
SpinyToad, Stabbot, TerrorEel, TestSubject, TheForgotten, TheInsatiable,
TheLost, TheObscura.

All 12 were found already correctly ported (this wave was audit-only for
batch-06; no code changes). Pattern: one HP spot check (asc 7 stays base
range, asc 8 moves to the ToughEnemies range) and one damage/value spot
check (asc 0 base vs asc 9 DeadlyEnemies) per monster, using direct
CombatState construction -- mirrors test_ascension.py's Chomper tests.
"""
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


def _combat(cls, asc: int, seed: int = 0):
    enc = Encounter(id="test_wave_b06", monster_classes=[cls])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


# ─── SneakyGremlin (Underdocks) ─────────────────────────────────────────
def test_sneaky_gremlin_tough_hp():
    from sts2_rl.monsters.underdocks.gremlin_merc import SneakyGremlin
    cs7 = _combat(SneakyGremlin, 7)
    cs8 = _combat(SneakyGremlin, 8)
    assert 10 <= cs7.enemy.max_hp <= 14
    assert 11 <= cs8.enemy.max_hp <= 15


def test_sneaky_gremlin_deadly_tackle_damage():
    from sts2_rl.monsters.underdocks.gremlin_merc import SneakyGremlin
    cs0 = _combat(SneakyGremlin, 0)
    cs9 = _combat(SneakyGremlin, 9)
    assert cs0.enemy._tackle_dmg() == 9
    assert cs9.enemy._tackle_dmg() == 10


# ─── SoulFysh (Underdocks boss) ─────────────────────────────────────────
def test_soul_fysh_tough_hp():
    from sts2_rl.monsters.underdocks.soul_fysh import SoulFysh
    assert _combat(SoulFysh, 7).enemy.max_hp == 211
    assert _combat(SoulFysh, 8).enemy.max_hp == 221


def test_soul_fysh_deadly_de_gas_damage():
    from sts2_rl.monsters.underdocks.soul_fysh import SoulFysh
    cs0 = _combat(SoulFysh, 0)
    cs9 = _combat(SoulFysh, 9)
    assert cs0.enemy._de_gas_dmg() == 16
    assert cs9.enemy._de_gas_dmg() == 17


# ─── SoulNexus (Glory elite) ────────────────────────────────────────────
def test_soul_nexus_tough_hp():
    from sts2_rl.monsters.glory.soul_nexus import SoulNexus
    assert _combat(SoulNexus, 7).enemy.max_hp == 234
    assert _combat(SoulNexus, 8).enemy.max_hp == 254


def test_soul_nexus_deadly_soul_burn_damage():
    from sts2_rl.monsters.glory.soul_nexus import SoulNexus
    cs0 = _combat(SoulNexus, 0)
    cs9 = _combat(SoulNexus, 9)
    assert cs0.enemy.machine.current.intent.damage == 29
    assert cs9.enemy.machine.current.intent.damage == 31


# ─── SpectralKnight (Glory elite) ───────────────────────────────────────
def test_spectral_knight_tough_hp():
    from sts2_rl.monsters.glory.knights import SpectralKnight
    assert _combat(SpectralKnight, 7).enemy.max_hp == 93
    assert _combat(SpectralKnight, 8).enemy.max_hp == 97


def test_spectral_knight_deadly_soul_slash_damage():
    from sts2_rl.monsters.glory.knights import SpectralKnight
    cs0 = _combat(SpectralKnight, 0)
    cs9 = _combat(SpectralKnight, 9)
    assert cs0.enemy._soul_slash_dmg() == 15
    assert cs9.enemy._soul_slash_dmg() == 17


# ─── SpinyToad (Hive) ────────────────────────────────────────────────────
def test_spiny_toad_tough_hp():
    from sts2_rl.monsters.hive.spiny_toad import SpinyToad
    cs7 = _combat(SpinyToad, 7)
    cs8 = _combat(SpinyToad, 8)
    assert 116 <= cs7.enemy.max_hp <= 119
    assert 121 <= cs8.enemy.max_hp <= 124


def test_spiny_toad_deadly_lash_damage():
    from sts2_rl.monsters.hive.spiny_toad import SpinyToad
    cs0 = _combat(SpinyToad, 0)
    cs9 = _combat(SpinyToad, 9)
    assert cs0.enemy._lash_dmg() == 17
    assert cs9.enemy._lash_dmg() == 19


# ─── Stabbot (Glory) ─────────────────────────────────────────────────────
def test_stabbot_tough_hp():
    from sts2_rl.monsters.glory.fabricator import Stabbot
    cs7 = _combat(Stabbot, 7)
    cs8 = _combat(Stabbot, 8)
    assert 18 <= cs7.enemy.max_hp <= 23
    assert 19 <= cs8.enemy.max_hp <= 24


def test_stabbot_deadly_stab_damage():
    from sts2_rl.monsters.glory.fabricator import Stabbot
    cs0 = _combat(Stabbot, 0)
    cs9 = _combat(Stabbot, 9)
    assert cs0.enemy.machine.current.intent.damage == 11
    assert cs9.enemy.machine.current.intent.damage == 12


# ─── TerrorEel (Underdocks elite) ───────────────────────────────────────
def test_terror_eel_tough_hp():
    from sts2_rl.monsters.underdocks.terror_eel import TerrorEel
    assert _combat(TerrorEel, 7).enemy.max_hp == 140
    assert _combat(TerrorEel, 8).enemy.max_hp == 150


def test_terror_eel_deadly_crash_damage():
    from sts2_rl.monsters.underdocks.terror_eel import TerrorEel
    cs0 = _combat(TerrorEel, 0)
    cs9 = _combat(TerrorEel, 9)
    assert cs0.enemy.machine.current.intent.damage == 16
    assert cs9.enemy.machine.current.intent.damage == 18


# ─── TestSubject (Glory boss, 3-phase) ──────────────────────────────────
def test_test_subject_tough_hp():
    # First-form HP only; forms 2/3 are only reached via Revive (see the
    # value-helper check below).
    from sts2_rl.monsters.glory.test_subject import TestSubject
    assert _combat(TestSubject, 7).enemy.max_hp == 100
    assert _combat(TestSubject, 8).enemy.max_hp == 111


def test_test_subject_deadly_bite_damage_and_form_hp():
    from sts2_rl.monsters.glory.test_subject import TestSubject
    cs0 = _combat(TestSubject, 0)
    cs9 = _combat(TestSubject, 9)
    assert cs0.enemy.machine.current.intent.damage == 20
    assert cs9.enemy.machine.current.intent.damage == 22
    # Second/third form HP (ToughEnemies) -- read only at Revive.
    assert cs0.enemy._second_form_hp() == 200
    cs8 = _combat(TestSubject, 8)
    assert cs8.enemy._second_form_hp() == 212
    assert cs8.enemy._third_form_hp() == 313


# ─── TheForgotten (Glory) ────────────────────────────────────────────────
def test_the_forgotten_tough_hp():
    from sts2_rl.monsters.glory.the_lost_and_forgotten import TheForgotten
    assert _combat(TheForgotten, 7).enemy.max_hp == 106
    assert _combat(TheForgotten, 8).enemy.max_hp == 111


def test_the_forgotten_deadly_dread_damage():
    # DreadDamage = ascension-gated base + current Dexterity. MIASMA (the
    # first move) grants itself +2 Dexterity before DREAD is telegraphed, so
    # the expected total is the ascension-gated base plus that +2.
    from sts2_rl.monsters.glory.the_lost_and_forgotten import TheForgotten
    cs0 = _combat(TheForgotten, 0)
    cs9 = _combat(TheForgotten, 9)
    cs0.end_turn()  # MIASMA is first; end_turn rolls into DREAD
    cs9.end_turn()
    assert cs0.enemy.machine.current.intent.damage == 13 + 2
    assert cs9.enemy.machine.current.intent.damage == 15 + 2


# ─── TheInsatiable (Hive boss) ──────────────────────────────────────────
def test_the_insatiable_tough_hp():
    from sts2_rl.monsters.hive.the_insatiable import TheInsatiable
    assert _combat(TheInsatiable, 7).enemy.max_hp == 321
    assert _combat(TheInsatiable, 8).enemy.max_hp == 341


def test_the_insatiable_deadly_thrash_damage():
    from sts2_rl.monsters.hive.the_insatiable import TheInsatiable
    cs0 = _combat(TheInsatiable, 0)
    cs9 = _combat(TheInsatiable, 9)
    assert cs0.enemy._thrash_dmg() == 8
    assert cs9.enemy._thrash_dmg() == 9


# ─── TheLost (Glory) ─────────────────────────────────────────────────────
def test_the_lost_tough_hp():
    from sts2_rl.monsters.glory.the_lost_and_forgotten import TheLost
    assert _combat(TheLost, 7).enemy.max_hp == 93
    assert _combat(TheLost, 8).enemy.max_hp == 99


def test_the_lost_deadly_eye_lasers_damage():
    from sts2_rl.monsters.glory.the_lost_and_forgotten import TheLost
    cs0 = _combat(TheLost, 0)
    cs9 = _combat(TheLost, 9)
    assert cs0.enemy._lasers_dmg() == 4
    assert cs9.enemy._lasers_dmg() == 5


# ─── TheObscura (Hive) ───────────────────────────────────────────────────
def test_the_obscura_tough_hp():
    from sts2_rl.monsters.hive.the_obscura import TheObscura
    assert _combat(TheObscura, 7).enemy.max_hp == 123
    assert _combat(TheObscura, 8).enemy.max_hp == 129


def test_the_obscura_deadly_gaze_damage():
    from sts2_rl.monsters.hive.the_obscura import TheObscura
    cs0 = _combat(TheObscura, 0)
    cs9 = _combat(TheObscura, 9)
    assert cs0.enemy._gaze_dmg() == 10
    assert cs9.enemy._gaze_dmg() == 11
