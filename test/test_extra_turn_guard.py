"""`CombatManager.PlayersTakingExtraTurn` — the extra-turn flag content reads.

`_playersTakingExtraTurn` is cleared and refilled in SwitchFromPlayerToEnemySide
(CombatManager.cs:1360-1373) and is still non-empty when StartTurn runs (:435,
:439) and therefore when Hook.AfterSideTurnStart fires (:522). RampartPower.cs:23
refuses to grant its block on an extra turn because of it; the sim had no such
flag, so the power granted the block again.

Queue entries: power/rampart/g1, power/rampart/AfterSideTurnStart.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.glory.turret_operator import TurretOperator


def _living_shield_combat():
    from sts2_rl.monsters.glory import turret_operator as mod
    encounter = None
    for name in ("TURRET_OPERATOR_WEAK", "TURRET_OPERATOR"):
        encounter = getattr(mod, name, None)
        if encounter is not None:
            break
    assert encounter is not None, "the Living Shield / Turret Operator encounter"
    return CombatState(
        rng=random.Random(0),
        starting_deck=[make_card("strike") for _ in range(5)],
        encounter=encounter,
        relics=[make_relic("paels_eye")],
    )


def test_rampart_grants_block_on_an_ordinary_turn():
    """The control. RampartPower.cs:26-31 blocks every Turret Operator."""
    cs = _living_shield_combat()
    turrets = [e for e in cs.enemies if isinstance(e, TurretOperator)]
    assert turrets
    assert all(t.block > 0 for t in turrets)


def test_rampart_grants_no_block_on_an_extra_turn():
    """RampartPower.cs:23 — `PlayersTakingExtraTurn.Count > 0` -> return.

    Pael's Eye claims an extra turn when no card was played this turn
    (relics/paels_eye.py), so ending turn 1 with an untouched hand is the
    reachable witness the queue entry named."""
    cs = _living_shield_combat()
    turrets = [e for e in cs.enemies if isinstance(e, TurretOperator)]
    for t in turrets:
        t.block = 0
    cs.end_turn()                      # no card played -> extra turn
    assert cs.players_taking_extra_turn
    assert all(t.block == 0 for t in turrets)


def test_the_flag_is_cleared_before_an_ordinary_turn_starts():
    """`_playersTakingExtraTurn.Clear()` (CombatManager.cs:1363) runs on every
    side switch, so a normal turn never sees a stale flag."""
    cs = _living_shield_combat()
    cs.play_card(0, target_idx=0)      # spend a card so Pael's Eye stays quiet
    cs.end_turn()
    assert not cs.players_taking_extra_turn


def test_a_fresh_combat_has_no_extra_turn_flag():
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[make_card("strike") for _ in range(5)])
    assert cs.players_taking_extra_turn == []
