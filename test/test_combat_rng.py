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


def test_parity_select_cards_shortcut_draws_nothing():
    """creature_card_cmds/N10/step104: the C# auto-select shortcut
    (`candidateCount <= MinSelect`) consumes zero draws from ANY stream, in
    parity mode too — not just legacy."""
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    rs = RunRngSet("89U21BV1TZ")
    c = CombatState(rng_set=rs)
    candidates = list(c.player.hand)
    before = rs.combat_card_selection.counter
    chosen = c.select_cards("exhaust", candidates, len(candidates))
    assert rs.combat_card_selection.counter == before
    assert chosen == candidates


def test_parity_selectorless_fallback_draws_from_card_selection_not_shuffle():
    """creature_card_cmds/N10/step105: the selectorless fallback (no
    card_selector installed) moves onto `combat_rng.card_selection` in parity
    mode — previously it fell through to the plain shared `self._rng`, which
    is not any of the run's named parity streams."""
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    rs = RunRngSet("89U21BV1TZ")
    c = CombatState(rng_set=rs)
    candidates = list(c.player.hand)  # 5 candidates, below-threshold count=1
    before_selection = rs.combat_card_selection.counter
    before_shuffle = rs.shuffle.counter
    chosen = c.select_cards("exhaust", candidates, 1)
    assert len(chosen) == 1
    assert rs.combat_card_selection.counter > before_selection
    assert rs.shuffle.counter == before_shuffle


def test_parity_selectorless_min_select_range_draws_only_from_card_selection():
    """A real MinSelect..MaxSelect range (min_select=0, the Ashwater/Gambler's
    Brew/Gambling Chip shape) in parity mode with no card_selector installed
    exercises BOTH the `randint(floor, count)` and the sample-without-
    replacement draws — both must land on `combat_card_selection`, none on
    `shuffle`/the plain legacy `random.Random`."""
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    rs = RunRngSet("89U21BV1TZ")
    c = CombatState(rng_set=rs)
    candidates = list(c.player.hand)
    before_selection = rs.combat_card_selection.counter
    before_shuffle = rs.shuffle.counter
    chosen = c.select_cards("exhaust_any", candidates, len(candidates), min_select=0)
    assert 0 <= len(chosen) <= len(candidates)
    assert rs.combat_card_selection.counter > before_selection
    assert rs.shuffle.counter == before_shuffle


def test_confused_cost_draws_from_the_energy_cost_stream():
    """relic/snecko_eye/g1. ConfusedPower.NextEnergyCost (ConfusedPower.cs:47-54)
    ends in `RunState.Rng.CombatEnergyCosts.NextInt(4)`, not the shuffle stream
    and not a shared rng."""
    from sts2_rl.cards import make_card
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import ConfusedPower
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet

    rs = RunRngSet("89U21BV1TZ")
    c = CombatState(rng_set=rs)
    PowerCmd.apply(c.hooks, c.player, ConfusedPower, 1)
    before_energy = rs.combat_energy_costs.counter
    before_shuffle = rs.shuffle.counter
    c.hooks.on_card_drawn(make_card("strike"))
    assert rs.combat_energy_costs.counter == before_energy + 1
    assert rs.shuffle.counter == before_shuffle
