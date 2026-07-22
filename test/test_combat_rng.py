from __future__ import annotations

import random

from sts2_rl.combat_rng import CombatRng
from sts2_rl.rng import RunRngSet

_ACCESSORS = ("shuffle", "monster_ai", "card_gen", "card_selection",
              "targets", "energy", "potion_gen")


def test_legacy_returns_the_same_random_for_every_accessor():
    r = random.Random(0)
    cr = CombatRng.legacy(r)
    for name in _ACCESSORS:
        assert getattr(cr, name) is r


def test_parity_routes_each_accessor_to_its_stream():
    rs = RunRngSet("89U21BV1TZ")
    cr = CombatRng.parity(rs)
    # each accessor is a GameRandomAdapter over the matching game stream
    assert cr.shuffle.rng is rs.shuffle
    assert cr.monster_ai.rng is rs.monster_ai
    assert cr.card_gen.rng is rs.combat_card_generation
    assert cr.card_selection.rng is rs.combat_card_selection
    assert cr.targets.rng is rs.combat_targets
    assert cr.energy.rng is rs.combat_energy_costs
    assert cr.potion_gen.rng is rs.combat_potion_generation


def test_parity_accessors_are_stable_objects():
    cr = CombatRng.parity(RunRngSet("89U21BV1TZ"))
    assert cr.shuffle is cr.shuffle  # property caches, not a fresh adapter each read


def test_combatstate_builds_legacy_combat_rng_by_default():
    import random
    from sts2_rl.combat import CombatState
    c = CombatState(rng=random.Random(0))
    assert c.combat_rng.shuffle is c._rng


def test_combatstate_parity_uses_run_streams():
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    rs = RunRngSet("89U21BV1TZ")
    c = CombatState(rng_set=rs)
    assert c.combat_rng.shuffle.rng is rs.shuffle


def test_parity_combat_start_draws_from_shuffle_stream():
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    rs = RunRngSet("89U21BV1TZ")
    before = rs.shuffle.counter
    CombatState(rng_set=rs)  # constructs player -> initial shuffle
    assert rs.shuffle.counter > before  # the initial deck shuffle drew from Shuffle


def test_legacy_shuffle_sequence_unchanged():
    import random
    from sts2_rl.combat import CombatState
    # A fixed-seed legacy combat draws the SAME opening hand as a bare
    # random.Random(0).shuffle of the deck would — i.e. nothing rerouted.
    c = CombatState(rng=random.Random(1234))
    assert c.combat_rng.shuffle is c._rng  # still the shared Random
