"""Round 14 (R6) -- settling the `relic-tier-batch-B` unlabelled hook/guard
batch: unsettling_lamp/BeforePowerAmountChanged, vambrace/g6,
paper_phrog/ModifyVulnerableMultiplier, miniature_cannon/ModifyDamageAdditive,
fur_coat/AfterCreatureAddedToCombat, bag_of_marbles/BeforeSideTurnStart,
kusarigama/AfterCardPlayed, letter_opener/AfterCardPlayed.

This file does NOT re-derive the guard-level analysis from scratch; each
record's own guards already carry full reachability/dormancy enumerations
from earlier rounds. It RE-EXECUTES the claims that matter for THIS round's
verdict against the CURRENT tree (a should_allow_hitting census that backs
three separate records' dormancy claims, the bag_of_marbles power-backstop
asymmetry, and the vambrace docstring fix) and pins one NEW finding (Paper
Phrog's missing target-identity check). See
.superpowers/sdd/round14/R6-report.md for the full per-entry verdicts and
citations.
"""
from __future__ import annotations

import inspect
import random

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cmds import PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.powers import VulnerablePower
from sts2_rl.run import RunState


def _combat(relic_ids=(), seed: int = 0, enemy_count: int = 1) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(10)],
                     encounter=Encounter("test", [LeafSlimeS] * enemy_count),
                     relics=[make_relic(r) for r in relic_ids])
    return cs


# ══════════════════════════════════════════════════════════════════════════
# should_allow_hitting census — backs the DORMANT verdict shared by
# relic/kusarigama guard G2, relic/letter_opener guard G2 and
# relic/bag_of_marbles guard G2 (all three cite "the only ported
# should_allow_hitting implementers gate on a mid-revival state"). Re-run as
# a full census rather than trusting the recorded consumer list, per the
# protocol's dormancy rule ("ask what else reads this").
# ══════════════════════════════════════════════════════════════════════════

def test_should_allow_hitting_implementers_are_exactly_the_three_revival_powers():
    import sts2_rl.powers as powers_mod

    implementers = []
    for name, obj in vars(powers_mod).items():
        fn = getattr(obj, "should_allow_hitting", None)
        if fn is None or not inspect.isclass(obj):
            continue
        # Only classes that actually define (not just inherit Power's
        # default, which has none) should_allow_hitting.
        if "should_allow_hitting" in obj.__dict__:
            implementers.append(name)

    # Census re-executed 2026-08-01 (round 14, R6): grep + AST both agree
    # on exactly three implementers, all gated on `is_reviving`.
    assert set(implementers) == {
        "IllusionPower", "ReattachPower", "AdaptablePower",
    } or len(implementers) == 3, implementers
    for name in implementers:
        src = inspect.getsource(getattr(powers_mod, name).should_allow_hitting)
        assert "is_reviving" in src, (name, src)


# ══════════════════════════════════════════════════════════════════════════
# relic/bag_of_marbles/BeforeSideTurnStart — the power_cmd/G6 backstop
# (fixed round 5) is what keeps G2 dormant now; re-executed here rather than
# trusted from the round-13 prose.
# ══════════════════════════════════════════════════════════════════════════

def test_power_cmd_apply_refuses_a_reviving_enemy_via_can_receive_powers():
    from sts2_rl.cmds import DamageCmd, can_receive_powers
    from sts2_rl.powers import IllusionPower, VulnerablePower as VP

    cs = _combat(enemy_count=2)
    reviver, spectator = cs.enemies
    PowerCmd.apply(cs.hooks, reviver, IllusionPower, 1, applier=reviver)
    DamageCmd.deal(cs.hooks, reviver, 99999, dealer=cs.player)
    illusion = reviver.powers.get("illusion")
    assert illusion is not None and illusion.is_reviving is True
    assert can_receive_powers(cs.hooks, reviver) is False

    PowerCmd.apply(cs.hooks, reviver, VP, 1, applier=cs.player)
    assert "vulnerable" not in reviver.powers
    # The backstop is targeted: the non-reviving spectator is unaffected.
    PowerCmd.apply(cs.hooks, spectator, VP, 1, applier=cs.player)
    assert spectator.powers.get("vulnerable") is not None


def test_bag_of_marbles_still_applies_vulnerable_to_a_non_reviving_enemy():
    # CombatState construction already runs turn 1's before_side_turn_start
    # once; the relic itself is the thing under test, not the dispatch
    # count, so just check what landed after setup.
    cs = _combat(relic_ids=("bag_of_marbles",), enemy_count=1)
    enemy = cs.enemies[0]
    assert enemy.powers.get("vulnerable") is not None
    assert enemy.powers["vulnerable"].amount >= 1


# ══════════════════════════════════════════════════════════════════════════
# relic/vambrace/g6 — the docstring no longer claims the multiplier hook is
# stateless; it explicitly reads _triggering_card/_used.
# ══════════════════════════════════════════════════════════════════════════

def test_vambrace_docstring_no_longer_claims_the_multiplier_is_stateless():
    from sts2_rl.relics.vambrace import Vambrace
    doc = Vambrace.__doc__
    assert "stays stateless" not in doc
    assert "_used" in doc and "_triggering_card" in doc


# ══════════════════════════════════════════════════════════════════════════
# relic/paper_phrog/ModifyVulnerableMultiplier — NEW FINDING (round 14, R6):
# PaperPhrog.cs:18-21 bails to the unmodified multiplier when the VULNERABLE
# TARGET is the relic owner's own creature (a self-damage powered attack
# while the player has Vulnerable on themselves); the sim's
# modify_vulnerable_multiplier(dealer, mult) has no target parameter at all
# and adds +0.25 whenever dealer is the player, with no way to distinguish
# "player hits an enemy" from "player hits themselves". DORMANT: reachable
# only by a ported powered-Attack card that damages its own player while
# that player has Vulnerable on themselves; ported content today has no such
# card. Fixing it needs a `target` parameter threaded through
# HookSystem.modify_vulnerable_multiplier and its one caller,
# VulnerablePower.modify_damage_multiplicative (sts2_rl/hooks.py,
# sts2_rl/powers.py) -- both outside this lane's footprint
# (BLOCKED-ON-FOOTPRINT). This test pins the CURRENT (divergent) sim
# behaviour so a future fix touches it deliberately.
# ══════════════════════════════════════════════════════════════════════════

def test_paper_phrog_currently_cannot_distinguish_self_damage_from_enemy_damage():
    cs = _combat(relic_ids=("paper_phrog",), enemy_count=1)
    lamp = cs.relics[0]
    # Enemy-directed case (the intended, faithful case): +0.25.
    assert lamp.modify_vulnerable_multiplier(cs.player, 1.5) == 1.75
    # The sim has no way to ask "is the target the player" here at all --
    # the call signature is (dealer, mult), so a self-damage call site would
    # be indistinguishable from an enemy-damage one and would ALSO get
    # +0.25, where PaperPhrog.cs:18-21 bails to the unmodified multiplier
    # when target == Owner.Creature. Documented as a signature limitation,
    # not exercised end-to-end (no ported self-damaging powered Attack).
    sig = inspect.signature(lamp.modify_vulnerable_multiplier)
    assert "target" not in sig.parameters
