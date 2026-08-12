"""Ascension spot tests for wave batch b04 (Task 4 monster-ascension port).

One HP-range check (asc 8 vs asc 7) per monster that carries ToughEnemies
HP, and one damage/count check (asc 9 vs asc 0) per monster that carries a
DeadlyEnemies value. Mirrors the Chomper pattern in test_ascension.py.
"""
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


def _combat(cls, asc: int, seed: int = 0, **kwargs):
    enc = Encounter(id="test_x", monster_classes=[cls])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


# ─── MagiKnight ──────────────────────────────────────────────────────────

def test_magiknight_tough_hp():
    from sts2_rl.monsters.glory.knights import MagiKnight
    assert _combat(MagiKnight, 7).enemy.max_hp == 82
    assert _combat(MagiKnight, 8).enemy.max_hp == 89


def test_magiknight_deadly_spear():
    from sts2_rl.monsters.glory.knights import MagiKnight
    cs0 = _combat(MagiKnight, 0)
    cs9 = _combat(MagiKnight, 9)
    assert cs0.enemy._spear_dmg() == 10
    assert cs9.enemy._spear_dmg() == 11


# ─── Mawler ──────────────────────────────────────────────────────────────

def test_mawler_tough_hp():
    from sts2_rl.monsters.overgrowth.mawler import Mawler
    assert _combat(Mawler, 7).enemy.max_hp == 72
    assert _combat(Mawler, 8).enemy.max_hp == 76


def test_mawler_deadly_rip():
    from sts2_rl.monsters.overgrowth.mawler import Mawler
    assert _combat(Mawler, 0).enemy._rip_dmg() == 14
    assert _combat(Mawler, 9).enemy._rip_dmg() == 16


# ─── MechaKnight ─────────────────────────────────────────────────────────

def test_mechaknight_tough_hp():
    from sts2_rl.monsters.glory.mecha_knight import MechaKnight
    assert _combat(MechaKnight, 7).enemy.max_hp == 300
    assert _combat(MechaKnight, 8).enemy.max_hp == 320


def test_mechaknight_deadly_charge():
    from sts2_rl.monsters.glory.mecha_knight import MechaKnight
    assert _combat(MechaKnight, 0).enemy._charge_dmg() == 25
    assert _combat(MechaKnight, 9).enemy._charge_dmg() == 30


# ─── Myte ────────────────────────────────────────────────────────────────

def test_myte_tough_hp():
    from sts2_rl.monsters.hive.myte import Myte
    seen = set()
    for seed in range(20):
        hp7 = _combat(Myte, 7, seed).enemy.max_hp
        hp8 = _combat(Myte, 8, seed).enemy.max_hp
        assert 61 <= hp7 <= 67
        assert 64 <= hp8 <= 69
        seen.add(hp8)
    assert seen & {68, 69}


def test_myte_deadly_bite():
    from sts2_rl.monsters.hive.myte import Myte
    assert _combat(Myte, 0).enemy._bite_dmg() == 13
    assert _combat(Myte, 9).enemy._bite_dmg() == 15


# ─── Nibbit ──────────────────────────────────────────────────────────────

def test_nibbit_tough_hp():
    from sts2_rl.monsters.nibbit import Nibbit
    assert _combat(Nibbit, 7).enemy.max_hp in range(42, 47)
    assert _combat(Nibbit, 8).enemy.max_hp in range(44, 49)


def test_nibbit_deadly_butt():
    from sts2_rl.monsters.nibbit import Nibbit
    assert _combat(Nibbit, 0).enemy._butt_dmg() == 12
    assert _combat(Nibbit, 9).enemy._butt_dmg() == 13


# ─── Noisebot ────────────────────────────────────────────────────────────

def test_noisebot_tough_hp():
    from sts2_rl.monsters.glory.fabricator import Noisebot
    assert _combat(Noisebot, 7).enemy.max_hp in range(18, 24)
    assert _combat(Noisebot, 8).enemy.max_hp in range(19, 25)


# ─── Ovicopter ───────────────────────────────────────────────────────────

def test_ovicopter_tough_hp():
    from sts2_rl.monsters.hive.ovicopter import Ovicopter
    assert _combat(Ovicopter, 7).enemy.max_hp in range(124, 131)
    assert _combat(Ovicopter, 8).enemy.max_hp in range(126, 133)


def test_ovicopter_deadly_smash():
    from sts2_rl.monsters.hive.ovicopter import Ovicopter
    assert _combat(Ovicopter, 0).enemy._smash_dmg() == 16
    assert _combat(Ovicopter, 9).enemy._smash_dmg() == 17


# ─── OwlMagistrate ───────────────────────────────────────────────────────

def test_owlmagistrate_tough_hp():
    from sts2_rl.monsters.glory.owl_magistrate import OwlMagistrate
    assert _combat(OwlMagistrate, 7).enemy.max_hp == 231
    assert _combat(OwlMagistrate, 8).enemy.max_hp == 247


def test_owlmagistrate_deadly_verdict():
    from sts2_rl.monsters.glory.owl_magistrate import OwlMagistrate
    assert _combat(OwlMagistrate, 0).enemy._verdict_dmg() == 33
    assert _combat(OwlMagistrate, 9).enemy._verdict_dmg() == 36


# ─── Parafright ──────────────────────────────────────────────────────────

def test_parafright_deadly_slam():
    from sts2_rl.monsters.hive.the_obscura import Parafright
    cs0 = _combat(Parafright, 0)
    cs9 = _combat(Parafright, 9)
    assert cs0.enemy._slam_dmg() == 16
    assert cs9.enemy._slam_dmg() == 17


# ─── PhantasmalGardener ──────────────────────────────────────────────────

def test_phantasmal_gardener_tough_hp():
    from sts2_rl.monsters.underdocks.phantasmal_gardener import PhantasmalGardener
    assert _combat(PhantasmalGardener, 7).enemy.max_hp in range(26, 32)
    assert _combat(PhantasmalGardener, 8).enemy.max_hp in range(27, 33)


def test_phantasmal_gardener_deadly_enlarge():
    from sts2_rl.monsters.underdocks.phantasmal_gardener import PhantasmalGardener
    assert _combat(PhantasmalGardener, 0).enemy._enlarge_str() == 2
    assert _combat(PhantasmalGardener, 9).enemy._enlarge_str() == 3


# ─── PhrogParasite ───────────────────────────────────────────────────────

def test_phrog_parasite_tough_hp():
    from sts2_rl.monsters.overgrowth.phrog_parasite import PhrogParasite
    assert _combat(PhrogParasite, 7).enemy.max_hp in range(61, 65)
    assert _combat(PhrogParasite, 8).enemy.max_hp in range(66, 69)


def test_phrog_parasite_deadly_lash():
    from sts2_rl.monsters.overgrowth.phrog_parasite import PhrogParasite
    assert _combat(PhrogParasite, 0).enemy._lash_dmg() == 4
    assert _combat(PhrogParasite, 9).enemy._lash_dmg() == 5


# ─── PunchConstruct ──────────────────────────────────────────────────────

def test_punch_construct_tough_hp():
    from sts2_rl.monsters.underdocks.punch_construct import PunchConstruct
    assert _combat(PunchConstruct, 7).enemy.max_hp == 55
    assert _combat(PunchConstruct, 8).enemy.max_hp == 60


def test_punch_construct_deadly_strong_punch():
    from sts2_rl.monsters.underdocks.punch_construct import PunchConstruct
    assert _combat(PunchConstruct, 0).enemy._strong_punch_dmg() == 14
    assert _combat(PunchConstruct, 9).enemy._strong_punch_dmg() == 16
