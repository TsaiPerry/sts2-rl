"""Ascension spot-tests for wave batch-07 (Task 4 monster-ascension port).

Twelve monsters: ThievingHopper, Toadpole, TorchHeadAmalgam, ToughEgg,
TrackerRubyRaider, Tunneler, TurretOperator, TwigSlimeM, TwigSlimeS,
TwoTailedRat, Vantom, VineShambler.

Pattern: one HP spot check (asc 7 stays base range, asc 8 moves to the
ToughEnemies range) and one damage/value spot check (asc 0 base vs asc 9
DeadlyEnemies) per monster, using direct CombatState construction --
mirrors test_ascension.py's Chomper tests.
"""
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


def _combat(cls, asc: int, seed: int = 0):
    enc = Encounter(id="test_wave_b07", monster_classes=[cls])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


# ─── ThievingHopper (Hive) ──────────────────────────────────────────────
def test_thieving_hopper_tough_hp():
    from sts2_rl.monsters.hive.thieving_hopper import ThievingHopper
    assert _combat(ThievingHopper, 7).enemy.max_hp == 79
    assert _combat(ThievingHopper, 8).enemy.max_hp == 84


def test_thieving_hopper_deadly_theft_damage():
    from sts2_rl.monsters.hive.thieving_hopper import ThievingHopper
    cs0 = _combat(ThievingHopper, 0)
    cs9 = _combat(ThievingHopper, 9)
    assert cs0.enemy.machine.current.intent.damage == 17
    assert cs9.enemy.machine.current.intent.damage == 19


# ─── Toadpole (Underdocks) ──────────────────────────────────────────────
def test_toadpole_tough_hp():
    from sts2_rl.monsters.underdocks.toadpole import Toadpole
    cs7 = _combat(Toadpole, 7)
    cs8 = _combat(Toadpole, 8)
    assert 21 <= cs7.enemy.max_hp <= 25
    assert 22 <= cs8.enemy.max_hp <= 26


def test_toadpole_deadly_whirl_damage():
    # The lone Toadpole starts as the "back" toad (is_front=False -> WHIRL).
    from sts2_rl.monsters.underdocks.toadpole import Toadpole
    cs0 = _combat(Toadpole, 0)
    cs9 = _combat(Toadpole, 9)
    assert cs0.enemy.machine.current.intent.damage == 7
    assert cs9.enemy.machine.current.intent.damage == 8


# ─── TorchHeadAmalgam (Glory) ───────────────────────────────────────────
def test_torch_head_amalgam_tough_hp():
    from sts2_rl.monsters.glory.queen import TorchHeadAmalgam
    assert _combat(TorchHeadAmalgam, 7).enemy.max_hp == 199
    assert _combat(TorchHeadAmalgam, 8).enemy.max_hp == 211


def test_torch_head_amalgam_deadly_tackle_damage():
    from sts2_rl.monsters.glory.queen import TorchHeadAmalgam
    cs0 = _combat(TorchHeadAmalgam, 0)
    cs9 = _combat(TorchHeadAmalgam, 9)
    assert cs0.enemy.machine.current.intent.damage == 18
    assert cs9.enemy.machine.current.intent.damage == 19


# ─── ToughEgg (Hive) ────────────────────────────────────────────────────
# ToughEgg is only ever constructed mid-combat (Ovicopter._lay_eggs, via
# CreatureCmd.add), where hooks.combat.current_side is already set. Building
# it as an Encounter's OWN starting roster hits CombatState.__init__'s
# ordering (create_monsters runs before current_side is assigned) -- an
# artifact of this direct-construction test harness, not a wave defect. Use
# a bare HookSystem (hooks.combat stays None, matching the `else 1` branch)
# instead of a full CombatState, per the wave brief's guidance for
# disproportionate combat setups.
def _tough_egg(asc: int):
    from sts2_rl.hooks import HookSystem
    from sts2_rl.monsters.hive.ovicopter import ToughEgg
    hooks = HookSystem()
    hooks.ascension = asc
    return ToughEgg(hooks, random.Random(0))


def test_tough_egg_tough_hp():
    egg7 = _tough_egg(7)
    egg8 = _tough_egg(8)
    assert 14 <= egg7.max_hp <= 18
    assert 15 <= egg8.max_hp <= 19


def test_tough_egg_deadly_nibble_damage():
    egg0 = _tough_egg(0)
    egg9 = _tough_egg(9)
    assert egg0._nibble_dmg() == 4
    assert egg9._nibble_dmg() == 5


# ─── TrackerRubyRaider (Overgrowth) ─────────────────────────────────────
def test_tracker_ruby_raider_tough_hp():
    from sts2_rl.monsters.overgrowth.ruby_raiders import TrackerRubyRaider
    cs7 = _combat(TrackerRubyRaider, 7)
    cs8 = _combat(TrackerRubyRaider, 8)
    assert 21 <= cs7.enemy.max_hp <= 25
    assert 22 <= cs8.enemy.max_hp <= 26


def test_tracker_ruby_raider_deadly_hounds_repeat():
    from sts2_rl.monsters.overgrowth.ruby_raiders import TrackerRubyRaider
    cs0 = _combat(TrackerRubyRaider, 0)
    cs9 = _combat(TrackerRubyRaider, 9)
    assert cs0.enemy._hounds_repeat() == 8
    assert cs9.enemy._hounds_repeat() == 9


# ─── Tunneler (Hive) ────────────────────────────────────────────────────
def test_tunneler_tough_hp():
    from sts2_rl.monsters.hive.tunneler import Tunneler
    assert _combat(Tunneler, 7).enemy.max_hp == 87
    assert _combat(Tunneler, 8).enemy.max_hp == 92


def test_tunneler_deadly_bite_damage():
    from sts2_rl.monsters.hive.tunneler import Tunneler
    cs0 = _combat(Tunneler, 0)
    cs9 = _combat(Tunneler, 9)
    assert cs0.enemy.machine.current.intent.damage == 13
    assert cs9.enemy.machine.current.intent.damage == 15


# ─── TurretOperator (Glory) ─────────────────────────────────────────────
def test_turret_operator_tough_hp():
    from sts2_rl.monsters.glory.turret_operator import TurretOperator
    assert _combat(TurretOperator, 7).enemy.max_hp == 41
    assert _combat(TurretOperator, 8).enemy.max_hp == 51


def test_turret_operator_deadly_fire_damage():
    from sts2_rl.monsters.glory.turret_operator import TurretOperator
    cs0 = _combat(TurretOperator, 0)
    cs9 = _combat(TurretOperator, 9)
    assert cs0.enemy.machine.current.intent.damage == 3
    assert cs9.enemy.machine.current.intent.damage == 4


# ─── TwigSlimeM (Overgrowth) ────────────────────────────────────────────
def test_twig_slime_m_tough_hp():
    from sts2_rl.monsters.overgrowth.slimes import TwigSlimeM
    cs7 = _combat(TwigSlimeM, 7)
    cs8 = _combat(TwigSlimeM, 8)
    assert 26 <= cs7.enemy.max_hp <= 28
    assert 27 <= cs8.enemy.max_hp <= 29


def test_twig_slime_m_deadly_clump_damage():
    # TwigSlimeM starts on STICKY_SHOT; end one turn to roll into
    # POKEY_POUNCE (seed 0 lands on it first try at both ascensions).
    from sts2_rl.monsters.overgrowth.slimes import TwigSlimeM
    cs0 = _combat(TwigSlimeM, 0, seed=0)
    cs9 = _combat(TwigSlimeM, 9, seed=0)
    cs0.end_turn()
    cs9.end_turn()
    assert cs0.enemy.current_intent.move_type.name == "ATTACK"
    assert cs0.enemy.current_intent.damage == 11
    assert cs9.enemy.current_intent.move_type.name == "ATTACK"
    assert cs9.enemy.current_intent.damage == 12


# ─── TwigSlimeS (Overgrowth) ────────────────────────────────────────────
def test_twig_slime_s_tough_hp():
    from sts2_rl.monsters.overgrowth.slimes import TwigSlimeS
    cs7 = _combat(TwigSlimeS, 7)
    cs8 = _combat(TwigSlimeS, 8)
    assert 7 <= cs7.enemy.max_hp <= 11
    assert 8 <= cs8.enemy.max_hp <= 12


def test_twig_slime_s_deadly_tackle_damage():
    from sts2_rl.monsters.overgrowth.slimes import TwigSlimeS
    cs0 = _combat(TwigSlimeS, 0)
    cs9 = _combat(TwigSlimeS, 9)
    assert cs0.enemy.current_intent.damage == 4
    assert cs9.enemy.current_intent.damage == 5


# ─── TwoTailedRat (Underdocks) ──────────────────────────────────────────
def test_two_tailed_rat_tough_hp():
    from sts2_rl.monsters.underdocks.two_tailed_rat import TwoTailedRat
    cs7 = _combat(TwoTailedRat, 7)
    cs8 = _combat(TwoTailedRat, 8)
    assert 17 <= cs7.enemy.max_hp <= 21
    assert 18 <= cs8.enemy.max_hp <= 22


def test_two_tailed_rat_deadly_damage_helpers():
    # The move actually rolled by the RandomBranchState is nondeterministic
    # by seed; assert the ascension-gated helpers directly (both are read at
    # both the telegraphed Intent and the executed attack -- see the class).
    from sts2_rl.monsters.underdocks.two_tailed_rat import TwoTailedRat
    cs0 = _combat(TwoTailedRat, 0)
    cs9 = _combat(TwoTailedRat, 9)
    assert cs0.enemy._scratch_dmg() == 8
    assert cs9.enemy._scratch_dmg() == 9
    assert cs0.enemy._disease_bite_dmg() == 6
    assert cs9.enemy._disease_bite_dmg() == 7


# ─── Vantom (Overgrowth boss) ───────────────────────────────────────────
def test_vantom_tough_hp():
    from sts2_rl.monsters.overgrowth.vantom import Vantom
    assert _combat(Vantom, 7).enemy.max_hp == 173
    assert _combat(Vantom, 8).enemy.max_hp == 183


def test_vantom_deadly_ink_blot_damage():
    from sts2_rl.monsters.overgrowth.vantom import Vantom
    cs0 = _combat(Vantom, 0)
    cs9 = _combat(Vantom, 9)
    assert cs0.enemy.current_intent.damage == 7
    assert cs9.enemy.current_intent.damage == 8


# ─── VineShambler (Overgrowth) ──────────────────────────────────────────
def test_vine_shambler_tough_hp():
    from sts2_rl.monsters.overgrowth.vine_shambler import VineShambler
    assert _combat(VineShambler, 7).enemy.max_hp == 61
    assert _combat(VineShambler, 8).enemy.max_hp == 64


def test_vine_shambler_deadly_swipe_damage():
    from sts2_rl.monsters.overgrowth.vine_shambler import VineShambler
    cs0 = _combat(VineShambler, 0)
    cs9 = _combat(VineShambler, 9)
    assert cs0.enemy.current_intent.damage == 6
    assert cs9.enemy.current_intent.damage == 7
