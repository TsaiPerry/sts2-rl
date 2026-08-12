"""Round-6 obs-parity fix: LeafSlimeS/LeafSlimeM/TwigSlimeM's STATUS_CARD
(GOOP/STICKY_SHOT) intents built ``Intent(MoveType.STATUS_CARD)`` with no
``status_count`` — one of the "THIRTEEN still leave it None" sites tracked by
``monster/_intent_count_lost`` (see ``sts2_rl/monsters/base.py``'s ``Intent``
docstring). ``full_env._enemy_floats`` field 24 (``status_count / 10.0``)
then read 0.0 for these three monsters where the game's own telemetry shows a
constant 0.1 (``status_count == 1``) / 0.2 (``LeafSlimeM``'s 2-card GOOP) —
confirmed against seed 89U21BV1TZ act 0 floor 4 (LeafSlimeS/TwigSlimeM enemy
rows both show a fixed 0.1 offset the sim's obs dump reports 0.0 for). Each
of these three monster's own move implementation already knows exactly how
many Slimed cards it deals (1 for LeafSlimeS/TwigSlimeM, 2 for LeafSlimeM),
so this fix only needs to pass that count into the ``Intent`` these three
sites already construct — it does not close the other ten still-open sites.
"""
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.base import MoveType
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeM, LeafSlimeS, TwigSlimeM


def _monster(cls, *, seed=0):
    encounter = Encounter(id=f"{cls.__name__}_status_count_test", monster_classes=[cls])
    combat = CombatState(rng=random.Random(seed), encounter=encounter)
    return combat.enemies[0]


def test_leaf_slime_s_goop_intent_carries_status_count():
    m = _monster(LeafSlimeS)
    # Force the GOOP branch regardless of the constructor's random roll.
    m._move_key = "GOOP"
    intent = m.current_intent
    assert intent.has(MoveType.STATUS_CARD)
    assert intent.status_count == 1


def test_leaf_slime_m_sticky_shot_intent_carries_status_count():
    m = _monster(LeafSlimeM)
    assert m._move_key == "STICKY_SHOT"
    intent = m.current_intent
    assert intent.has(MoveType.STATUS_CARD)
    assert intent.status_count == 2


def test_twig_slime_m_sticky_shot_intent_carries_status_count():
    m = _monster(TwigSlimeM)
    assert m._move_key == "STICKY_SHOT"
    intent = m.current_intent
    assert intent.has(MoveType.STATUS_CARD)
    assert intent.status_count == 1
