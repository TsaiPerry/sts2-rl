"""Wave batch b01 -- ToughEnemies/DeadlyEnemies spot tests for 12 monsters.

One HP-range check (asc 8 vs asc 7) per monster with Tough HP, one
damage/count check (asc 9 vs asc 0) per monster with Deadly values. Mirrors
test_ascension.py's Chomper pattern (direct HookSystem/CombatState
construction, no full-combat execution)."""
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


def _combat(monster_cls, asc: int, seed: int = 0, **kwargs):
    enc = Encounter(id=f"test_{monster_cls.__name__.lower()}",
                     monster_classes=[monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc, **kwargs)


# ─── CeremonialBeast ────────────────────────────────────────────────────────

def test_ceremonial_beast_tough_hp():
    from sts2_rl.monsters.overgrowth.ceremonial_beast import CeremonialBeast
    cs0 = _combat(CeremonialBeast, 0)
    cs7 = _combat(CeremonialBeast, 7)
    cs8 = _combat(CeremonialBeast, 8)
    assert cs0.enemy.max_hp == 252
    assert cs7.enemy.max_hp == 252
    assert cs8.enemy.max_hp == 262


def test_ceremonial_beast_deadly_plow():
    from sts2_rl.monsters.overgrowth.ceremonial_beast import CeremonialBeast
    cs0 = _combat(CeremonialBeast, 0)
    cs9 = _combat(CeremonialBeast, 9)
    assert cs0.enemy.current_intent.buffs[0][1] == 150
    assert cs9.enemy.current_intent.buffs[0][1] == 160


# ─── CorpseSlug ─────────────────────────────────────────────────────────────

def test_corpse_slug_tough_hp():
    from sts2_rl.monsters.underdocks.corpse_slug import CorpseSlug
    seen8 = set()
    for seed in range(20):
        hp0 = _combat(CorpseSlug, 0, seed).enemy.max_hp
        hp7 = _combat(CorpseSlug, 7, seed).enemy.max_hp
        hp8 = _combat(CorpseSlug, 8, seed).enemy.max_hp
        assert 25 <= hp0 <= 27
        assert 25 <= hp7 <= 27
        assert 27 <= hp8 <= 29
        seen8.add(hp8)
    assert seen8 & {28, 29}


def test_corpse_slug_deadly_glomp():
    from sts2_rl.monsters.underdocks.corpse_slug import CorpseSlug
    cs0 = _combat(CorpseSlug, 0, starter_move_idx=1) if False else None
    from sts2_rl.monsters.base import Encounter as Enc
    enc = Enc(id="test_glomp", monster_classes=[])

    def make(asc):
        e = Enc(id="test_glomp", monster_classes=[])
        cs = CombatState(rng=random.Random(0), encounter=e, ascension=asc)
        slug = CorpseSlug(cs.hooks, random.Random(0), starter_move_idx=1)  # GLOMP first
        return slug

    slug0 = make(0)
    slug9 = make(9)
    assert slug0.machine.current.intent.damage == 8
    assert slug9.machine.current.intent.damage == 9


# ─── CrossbowRubyRaider ─────────────────────────────────────────────────────

def test_crossbow_raider_tough_hp():
    from sts2_rl.monsters.overgrowth.ruby_raiders import CrossbowRubyRaider
    cs0 = _combat(CrossbowRubyRaider, 0)
    cs7 = _combat(CrossbowRubyRaider, 7)
    cs8 = _combat(CrossbowRubyRaider, 8)
    assert 18 <= cs0.enemy.max_hp <= 21
    assert 18 <= cs7.enemy.max_hp <= 21
    assert 19 <= cs8.enemy.max_hp <= 22


def test_crossbow_raider_deadly_fire():
    from sts2_rl.monsters.overgrowth.ruby_raiders import CrossbowRubyRaider
    cs0 = _combat(CrossbowRubyRaider, 0)
    cs9 = _combat(CrossbowRubyRaider, 9)
    cs0.enemy._move_key = "FIRE"
    cs9.enemy._move_key = "FIRE"
    assert cs0.enemy.current_intent.damage == 14
    assert cs9.enemy.current_intent.damage == 16


# ─── Crusher ────────────────────────────────────────────────────────────────

def test_crusher_tough_hp():
    from sts2_rl.monsters.hive.kaiser_crab import Crusher
    cs0 = _combat(Crusher, 0)
    cs7 = _combat(Crusher, 7)
    cs8 = _combat(Crusher, 8)
    assert cs0.enemy.max_hp == 209
    assert cs7.enemy.max_hp == 209
    assert cs8.enemy.max_hp == 219


def test_crusher_deadly_thrash():
    from sts2_rl.monsters.hive.kaiser_crab import Crusher
    cs0 = _combat(Crusher, 0)
    cs9 = _combat(Crusher, 9)
    assert cs0.enemy.machine.current.intent.damage == 12
    assert cs9.enemy.machine.current.intent.damage == 14


# ─── CubexConstruct ─────────────────────────────────────────────────────────

def test_cubex_construct_tough_hp():
    from sts2_rl.monsters.overgrowth.cubex_construct import CubexConstruct
    cs0 = _combat(CubexConstruct, 0)
    cs7 = _combat(CubexConstruct, 7)
    cs8 = _combat(CubexConstruct, 8)
    assert cs0.enemy.max_hp == 65
    assert cs7.enemy.max_hp == 65
    assert cs8.enemy.max_hp == 70


def test_cubex_construct_deadly_rb():
    from sts2_rl.monsters.overgrowth.cubex_construct import CubexConstruct
    cs0 = _combat(CubexConstruct, 0)
    cs9 = _combat(CubexConstruct, 9)
    cs0.enemy._move_key = "RB"
    cs9.enemy._move_key = "RB"
    assert cs0.enemy.current_intent.damage == 7
    assert cs9.enemy.current_intent.damage == 8


# ─── DampCultist ────────────────────────────────────────────────────────────

def test_damp_cultist_tough_hp():
    from sts2_rl.monsters.underdocks.cultists import DampCultist
    cs0 = _combat(DampCultist, 0)
    cs7 = _combat(DampCultist, 7)
    cs8 = _combat(DampCultist, 8)
    assert 51 <= cs0.enemy.max_hp <= 53
    assert 51 <= cs7.enemy.max_hp <= 53
    assert 52 <= cs8.enemy.max_hp <= 54


def test_damp_cultist_deadly_dark_strike():
    from sts2_rl.monsters.underdocks.cultists import DampCultist
    cs0 = _combat(DampCultist, 0)
    cs9 = _combat(DampCultist, 9)
    assert cs0.enemy._dark_strike_dmg() == 1
    assert cs9.enemy._dark_strike_dmg() == 3


# ─── DecimillipedeSegment ───────────────────────────────────────────────────

def test_decimillipede_segment_tough_hp():
    from sts2_rl.monsters.hive.decimillipede import DecimillipedeSegment
    cs0 = _combat(DecimillipedeSegment, 0)
    cs7 = _combat(DecimillipedeSegment, 7)
    cs8 = _combat(DecimillipedeSegment, 8)
    assert 40 <= cs0.enemy.max_hp <= 46
    assert 40 <= cs7.enemy.max_hp <= 46
    assert 46 <= cs8.enemy.max_hp <= 52


def test_decimillipede_segment_deadly_writhe():
    from sts2_rl.monsters.hive.decimillipede import DecimillipedeSegment
    cs0 = _combat(DecimillipedeSegment, 0)
    cs9 = _combat(DecimillipedeSegment, 9)
    assert cs0.enemy.machine.current.intent.damage == 5
    assert cs9.enemy.machine.current.intent.damage == 6


# ─── DevotedSculptor ────────────────────────────────────────────────────────

def test_devoted_sculptor_tough_hp():
    from sts2_rl.monsters.glory.devoted_sculptor import DevotedSculptor
    cs0 = _combat(DevotedSculptor, 0)
    cs7 = _combat(DevotedSculptor, 7)
    cs8 = _combat(DevotedSculptor, 8)
    assert cs0.enemy.max_hp == 162
    assert cs7.enemy.max_hp == 162
    assert cs8.enemy.max_hp == 172


def test_devoted_sculptor_deadly_savage():
    from sts2_rl.monsters.glory.devoted_sculptor import DevotedSculptor
    cs0 = _combat(DevotedSculptor, 0)
    cs9 = _combat(DevotedSculptor, 9)
    assert cs0.enemy._savage_dmg() == 12
    assert cs9.enemy._savage_dmg() == 15


# ─── Entomancer ─────────────────────────────────────────────────────────────

def test_entomancer_tough_hp():
    from sts2_rl.monsters.hive.entomancer import Entomancer
    cs0 = _combat(Entomancer, 0)
    cs7 = _combat(Entomancer, 7)
    cs8 = _combat(Entomancer, 8)
    assert cs0.enemy.max_hp == 145
    assert cs7.enemy.max_hp == 145
    assert cs8.enemy.max_hp == 155


def test_entomancer_deadly_bees_hits():
    from sts2_rl.monsters.hive.entomancer import Entomancer
    cs0 = _combat(Entomancer, 0)
    cs9 = _combat(Entomancer, 9)
    assert cs0.enemy.machine.current.intent.hits == 7
    assert cs9.enemy.machine.current.intent.hits == 8


# ─── Exoskeleton ────────────────────────────────────────────────────────────

def test_exoskeleton_tough_hp():
    from sts2_rl.monsters.hive.exoskeleton import Exoskeleton
    cs0 = _combat(Exoskeleton, 0)
    cs7 = _combat(Exoskeleton, 7)
    cs8 = _combat(Exoskeleton, 8)
    assert 24 <= cs0.enemy.max_hp <= 28
    assert 24 <= cs7.enemy.max_hp <= 28
    assert 25 <= cs8.enemy.max_hp <= 29


def test_exoskeleton_deadly_mandibles():
    from sts2_rl.monsters.hive.exoskeleton import Exoskeleton
    cs0 = _combat(Exoskeleton, 0)
    cs9 = _combat(Exoskeleton, 9)
    assert cs0.enemy._mandibles_dmg() == 8
    assert cs9.enemy._mandibles_dmg() == 9


# ─── Fabricator ─────────────────────────────────────────────────────────────

def test_fabricator_tough_hp():
    from sts2_rl.monsters.glory.fabricator import Fabricator
    cs0 = _combat(Fabricator, 0)
    cs7 = _combat(Fabricator, 7)
    cs8 = _combat(Fabricator, 8)
    assert cs0.enemy.max_hp == 150
    assert cs7.enemy.max_hp == 150
    assert cs8.enemy.max_hp == 155


def test_fabricator_deadly_disintegrate():
    from sts2_rl.monsters.glory.fabricator import Fabricator
    cs0 = _combat(Fabricator, 0)
    cs9 = _combat(Fabricator, 9)
    assert cs0.enemy._disintegrate_dmg() == 11
    assert cs9.enemy._disintegrate_dmg() == 13


# ─── FakeMerchantMonster ────────────────────────────────────────────────────

def test_fake_merchant_tough_hp():
    from sts2_rl.monsters.fake_merchant import FakeMerchantMonster
    cs0 = _combat(FakeMerchantMonster, 0)
    cs7 = _combat(FakeMerchantMonster, 7)
    cs8 = _combat(FakeMerchantMonster, 8)
    assert cs0.enemy.max_hp == 165
    assert cs7.enemy.max_hp == 165
    assert cs8.enemy.max_hp == 175


def test_fake_merchant_deadly_swipe():
    from sts2_rl.monsters.fake_merchant import FakeMerchantMonster
    cs0 = _combat(FakeMerchantMonster, 0)
    cs9 = _combat(FakeMerchantMonster, 9)
    assert cs0.enemy.machine.current.intent.damage == 13
    assert cs9.enemy.machine.current.intent.damage == 15
