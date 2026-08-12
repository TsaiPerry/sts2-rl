"""Ascension spot tests for wave batch b03 (Task 4 monster-ascension port).

One spot test per monster: HP range at asc 8 (asc 7 stays base) where the
monster has ToughEnemies HP, and one damage/count value at asc 9 (asc 0
stays base) where it has DeadlyEnemies values. Follows the Chomper pattern
in test/test_ascension.py.
"""
import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


def _combat(cls, asc: int, seed: int = 0, **kwargs):
    enc = Encounter(id="test_asc_b03", monster_classes=[cls])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


# ── HunterKiller ────────────────────────────────────────────────────────

def test_hunter_killer_tough_hp():
    from sts2_rl.monsters.hive.hunter_killer import HunterKiller
    assert _combat(HunterKiller, 0).enemy.max_hp == 121
    assert _combat(HunterKiller, 7).enemy.max_hp == 121
    assert _combat(HunterKiller, 8).enemy.max_hp == 126


def test_hunter_killer_deadly_bite():
    from sts2_rl.monsters.hive.hunter_killer import HunterKiller
    cs0 = _combat(HunterKiller, 0)
    cs9 = _combat(HunterKiller, 9)
    assert cs0.enemy._bite_dmg() == 17
    assert cs9.enemy._bite_dmg() == 19


# ── InfestedPrism ───────────────────────────────────────────────────────

def test_infested_prism_tough_hp():
    from sts2_rl.monsters.hive.infested_prism import InfestedPrism
    assert _combat(InfestedPrism, 0).enemy.max_hp == 161
    assert _combat(InfestedPrism, 7).enemy.max_hp == 161
    assert _combat(InfestedPrism, 8).enemy.max_hp == 171


def test_infested_prism_deadly_jab():
    from sts2_rl.monsters.hive.infested_prism import InfestedPrism
    cs0 = _combat(InfestedPrism, 0)
    cs9 = _combat(InfestedPrism, 9)
    assert cs0.enemy._jab_dmg() == 15
    assert cs9.enemy._jab_dmg() == 17


# ── Inklet ──────────────────────────────────────────────────────────────

def test_inklet_tough_hp():
    from sts2_rl.monsters.overgrowth.inklets import Inklet
    seen8 = set()
    for seed in range(20):
        hp0 = _combat(Inklet, 0, seed).enemy.max_hp
        hp7 = _combat(Inklet, 7, seed).enemy.max_hp
        hp8 = _combat(Inklet, 8, seed).enemy.max_hp
        assert 11 <= hp0 <= 17
        assert 11 <= hp7 <= 17
        assert 12 <= hp8 <= 18
        seen8.add(hp8)
    assert seen8  # sanity


def test_inklet_deadly_jab():
    from sts2_rl.monsters.overgrowth.inklets import Inklet
    cs0 = _combat(Inklet, 0)
    cs9 = _combat(Inklet, 9)
    assert cs0.enemy._jab_dmg() == 3
    assert cs9.enemy._jab_dmg() == 4


# ── KinFollower / KinPriest ─────────────────────────────────────────────

def test_kin_follower_tough_hp():
    from sts2_rl.monsters.overgrowth.the_kin import KinFollower
    assert _combat(KinFollower, 0).enemy.max_hp in (58, 59)
    assert _combat(KinFollower, 7).enemy.max_hp in (58, 59)
    hp8 = _combat(KinFollower, 8).enemy.max_hp
    assert hp8 in (62, 63)


def test_kin_follower_deadly_dance_str():
    from sts2_rl.monsters.overgrowth.the_kin import KinFollower
    cs0 = _combat(KinFollower, 0)
    cs9 = _combat(KinFollower, 9)
    assert cs0.enemy._dance_str() == 2
    assert cs9.enemy._dance_str() == 3


def test_kin_priest_tough_hp():
    from sts2_rl.monsters.overgrowth.the_kin import KinPriest
    assert _combat(KinPriest, 0).enemy.max_hp == 190
    assert _combat(KinPriest, 7).enemy.max_hp == 190
    assert _combat(KinPriest, 8).enemy.max_hp == 199


def test_kin_priest_deadly_orb_frailty():
    from sts2_rl.monsters.overgrowth.the_kin import KinPriest
    cs0 = _combat(KinPriest, 0)
    cs9 = _combat(KinPriest, 9)
    assert cs0.enemy._orb_frailty_dmg() == 8
    assert cs9.enemy._orb_frailty_dmg() == 9


# ── KnowledgeDemon ──────────────────────────────────────────────────────

def test_knowledge_demon_tough_hp():
    from sts2_rl.monsters.hive.knowledge_demon import KnowledgeDemon
    assert _combat(KnowledgeDemon, 0).enemy.max_hp == 379
    assert _combat(KnowledgeDemon, 7).enemy.max_hp == 379
    assert _combat(KnowledgeDemon, 8).enemy.max_hp == 399


def test_knowledge_demon_deadly_slap():
    from sts2_rl.monsters.hive.knowledge_demon import KnowledgeDemon
    cs0 = _combat(KnowledgeDemon, 0)
    cs9 = _combat(KnowledgeDemon, 9)
    assert cs0.enemy._slap_dmg() == 17
    assert cs9.enemy._slap_dmg() == 18


# ── LagavulinMatriarch ──────────────────────────────────────────────────

def test_lagavulin_matriarch_tough_hp():
    from sts2_rl.monsters.underdocks.lagavulin_matriarch import LagavulinMatriarch
    assert _combat(LagavulinMatriarch, 0).enemy.max_hp == 222
    assert _combat(LagavulinMatriarch, 7).enemy.max_hp == 222
    assert _combat(LagavulinMatriarch, 8).enemy.max_hp == 233


def test_lagavulin_matriarch_deadly_slash():
    from sts2_rl.monsters.underdocks.lagavulin_matriarch import LagavulinMatriarch
    cs0 = _combat(LagavulinMatriarch, 0)
    cs9 = _combat(LagavulinMatriarch, 9)
    assert cs0.enemy._slash_dmg() == 19
    assert cs9.enemy._slash_dmg() == 21


# ── LeafSlimeM / LeafSlimeS ─────────────────────────────────────────────

def test_leaf_slime_m_tough_hp():
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeM
    assert 32 <= _combat(LeafSlimeM, 0).enemy.max_hp <= 35
    assert 32 <= _combat(LeafSlimeM, 7).enemy.max_hp <= 35
    assert 33 <= _combat(LeafSlimeM, 8).enemy.max_hp <= 36


def test_leaf_slime_m_deadly_clump():
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeM
    cs0 = _combat(LeafSlimeM, 0)
    cs9 = _combat(LeafSlimeM, 9)
    assert cs0.enemy._clump_dmg() == 8
    assert cs9.enemy._clump_dmg() == 9


def test_leaf_slime_s_tough_hp():
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
    assert 11 <= _combat(LeafSlimeS, 0).enemy.max_hp <= 15
    assert 11 <= _combat(LeafSlimeS, 7).enemy.max_hp <= 15
    assert 12 <= _combat(LeafSlimeS, 8).enemy.max_hp <= 16


def test_leaf_slime_s_deadly_tackle():
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
    cs0 = _combat(LeafSlimeS, 0)
    cs9 = _combat(LeafSlimeS, 9)
    assert cs0.enemy._tackle_dmg() == 3
    assert cs9.enemy._tackle_dmg() == 4


# ── LivingFog ───────────────────────────────────────────────────────────

def test_living_fog_tough_hp():
    from sts2_rl.monsters.underdocks.living_fog import LivingFog
    assert _combat(LivingFog, 0).enemy.max_hp == 80
    assert _combat(LivingFog, 7).enemy.max_hp == 80
    assert _combat(LivingFog, 8).enemy.max_hp == 82


def test_living_fog_deadly_advanced_gas():
    from sts2_rl.monsters.underdocks.living_fog import LivingFog
    cs0 = _combat(LivingFog, 0)
    cs9 = _combat(LivingFog, 9)
    assert cs0.enemy._advanced_gas_dmg() == 8
    assert cs9.enemy._advanced_gas_dmg() == 9


# ── LivingShield ────────────────────────────────────────────────────────

def test_living_shield_tough_hp():
    from sts2_rl.monsters.glory.turret_operator import LivingShield
    assert _combat(LivingShield, 0).enemy.max_hp == 55
    assert _combat(LivingShield, 7).enemy.max_hp == 55
    assert _combat(LivingShield, 8).enemy.max_hp == 65


def test_living_shield_deadly_smash():
    from sts2_rl.monsters.glory.turret_operator import LivingShield
    cs0 = _combat(LivingShield, 0)
    cs9 = _combat(LivingShield, 9)
    assert cs0.enemy._smash_dmg() == 16
    assert cs9.enemy._smash_dmg() == 18


# ── LouseProgenitor ─────────────────────────────────────────────────────

def test_louse_progenitor_tough_hp():
    from sts2_rl.monsters.hive.louse_progenitor import LouseProgenitor
    assert 134 <= _combat(LouseProgenitor, 0).enemy.max_hp <= 136
    assert 134 <= _combat(LouseProgenitor, 7).enemy.max_hp <= 136
    assert 138 <= _combat(LouseProgenitor, 8).enemy.max_hp <= 141


def test_louse_progenitor_deadly_web():
    from sts2_rl.monsters.hive.louse_progenitor import LouseProgenitor
    cs0 = _combat(LouseProgenitor, 0)
    cs9 = _combat(LouseProgenitor, 9)
    assert cs0.enemy._web_dmg() == 9
    assert cs9.enemy._web_dmg() == 10
