"""Wave batch b08 -- ToughEnemies/DeadlyEnemies spot checks for WaterfallGiant,
Wriggler, and Zapbot (Task 4 monster-ascension port)."""
import random

from sts2_rl.combat import CombatState
from sts2_rl.hooks import HookSystem
from sts2_rl.monsters.base import Encounter
from sts2_rl.monsters.glory.fabricator import Zapbot
from sts2_rl.monsters.overgrowth.phrog_parasite import Wriggler
from sts2_rl.monsters.underdocks.waterfall_giant import WaterfallGiant


# ═════════════════════════════════════════════════════════════════════════
# WaterfallGiant (WaterfallGiant.cs)
# ═════════════════════════════════════════════════════════════════════════

def _giant_combat(asc: int, seed: int = 0):
    enc = Encounter(id="test_waterfall_giant", monster_classes=[WaterfallGiant])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_waterfall_giant_tough_hp():
    # WaterfallGiant.cs:68-70 -- MinInitialHp/MaxInitialHp both read
    # GetValueIfAscension(ToughEnemies, 250, 240); MaxInitialHp mirrors Min,
    # so the roll always lands exactly on the bound (240 base, 250 asc 8+).
    assert _giant_combat(0).enemy.max_hp == 240
    assert _giant_combat(7).enemy.max_hp == 240  # asc 7 < ToughEnemies(8)
    assert _giant_combat(8).enemy.max_hp == 250


def test_waterfall_giant_deadly_stomp_damage():
    # WaterfallGiant.cs:76 -- StompDamage reads GetValueIfAscension(
    # DeadlyEnemies, 16, 15). STOMP_MOVE is the first follow-up after the
    # opening PRESSURIZE, so end one turn to reach it.
    cs0 = _giant_combat(0)
    cs9 = _giant_combat(9)
    cs0.end_turn()  # PRESSURIZE_MOVE (no damage)
    cs9.end_turn()
    assert cs0.enemy.machine.current.intent.damage == 15
    assert cs9.enemy.machine.current.intent.damage == 16


# ═════════════════════════════════════════════════════════════════════════
# Wriggler (Wriggler.cs)
# ═════════════════════════════════════════════════════════════════════════

def _wriggler(asc: int) -> Wriggler:
    hooks = HookSystem()
    hooks.ascension = asc
    return Wriggler(hooks, random.Random(0), slot=1)


def test_wriggler_tough_hp():
    # Wriggler.cs:30-32 -- Min/MaxInitialHp read GetValueIfAscension(
    # ToughEnemies, 18/22, 17/21). Sweep seeds so asc-8's extra headroom
    # (18, 22) is actually exercised.
    seen_asc8 = set()
    for seed in range(30):
        hooks0 = HookSystem()
        hooks0.ascension = 0
        w0 = Wriggler(hooks0, random.Random(seed), slot=1)
        hooks7 = HookSystem()
        hooks7.ascension = 7
        w7 = Wriggler(hooks7, random.Random(seed), slot=1)
        hooks8 = HookSystem()
        hooks8.ascension = 8
        w8 = Wriggler(hooks8, random.Random(seed), slot=1)
        assert 17 <= w0.max_hp <= 21
        assert 17 <= w7.max_hp <= 21  # asc 7 < ToughEnemies(8)
        assert 18 <= w8.max_hp <= 22
        seen_asc8.add(w8.max_hp)
    assert seen_asc8 & {22}  # value unreachable under the asc-0 range


def test_wriggler_deadly_bite_damage():
    # Wriggler.cs:34 -- BiteDamage reads GetValueIfAscension(DeadlyEnemies,
    # 7, 6). slot=1 opens with NASTY_BITE.
    w0 = _wriggler(0)
    w9 = _wriggler(9)
    assert w0.current_intent.damage == 6
    assert w9.current_intent.damage == 7


# ═════════════════════════════════════════════════════════════════════════
# Zapbot (Zapbot.cs, ported inside monsters/glory/fabricator.py)
# ═════════════════════════════════════════════════════════════════════════

def _zapbot_combat(asc: int, seed: int = 0):
    enc = Encounter(id="test_zapbot", monster_classes=[Zapbot])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_zapbot_tough_hp():
    # Zapbot.cs:21-23 -- Min/MaxInitialHp read GetValueIfAscension(
    # ToughEnemies, 19/24, 18/23).
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _zapbot_combat(0, seed).enemy.max_hp
        hp7 = _zapbot_combat(7, seed).enemy.max_hp
        hp8 = _zapbot_combat(8, seed).enemy.max_hp
        assert 18 <= hp0 <= 23
        assert 18 <= hp7 <= 23  # asc 7 < ToughEnemies(8)
        assert 19 <= hp8 <= 24
        seen_asc8.add(hp8)
    assert seen_asc8 & {24}  # value unreachable under the asc-0 range


def test_zapbot_deadly_zap_damage():
    # Zapbot.cs:25 -- ZapDamage reads GetValueIfAscension(DeadlyEnemies,
    # 15, 14).
    cs0, cs9 = _zapbot_combat(0), _zapbot_combat(9)
    assert cs0.enemy.machine.current.intent.damage == 14
    assert cs9.enemy.machine.current.intent.damage == 15
