"""Task 9 — `creature_card_cmds/G12` + `/step34`: the run-side gold-gain hook
surface (`Hook.ModifyGoldGained` -> `Hook.AfterModifyingGoldGained` ->
`Hook.AfterGoldGained`, `PlayerCmd.cs:141-170`).

WITNESS RE-EXECUTION (see task-9-report.md): by the time this task ran, the
fix was ALREADY STAGED in this worktree — `RunState.gain_gold` (run.py:409-
425) already runs the `modify_gold_gained` chain, truncates, gates on the
MODIFIED amount, moves the balance, and only then dispatches
`after_gold_gained` to every relic; `Relic.after_gold_gained` already exists
on the base surface (relics/base.py:327-336); Dragon Fruit already implements
it (relics/dragon_fruit.py). `test/test_false_premise_stubs.py` already pins
Dragon Fruit's own three cases (grants +1 Max HP per gain, sees the new
balance, sits behind the positive-amount bail). This file adds the
MECHANISM-level coverage the brief also asked for and that file does not
carry: a no-relic gain, the two-full-passes ordering guarantee (not
interleaved per relic), dispatch to every relic present (not just one), the
pre-truncation vs. post-truncation bail boundary, a negative modified amount,
and gold LOSS never routing through this surface at all.
"""
from __future__ import annotations

import random

from sts2_rl.relics.base import Relic
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


class _GoldSpy(Relic):
    """A relic that logs every modify/after call it sees, tagged with its
    own name, into a list shared across every relic on the run."""

    id = "gold_spy"
    name = "Gold Spy"

    def __init__(self, tag: str, log: list, multiplier: float = 1.0):
        self.tag = tag
        self.log = log
        self.multiplier = multiplier
        self.seen_after: list[tuple] = []

    def modify_gold_gained(self, run, amount: float) -> float:
        self.log.append(f"{self.tag}.modify")
        return amount * self.multiplier

    def after_gold_gained(self, run, amount: int) -> None:
        self.log.append(f"{self.tag}.after")
        self.seen_after.append((run.gold, amount))


# ══════════════════════════════════════════════════════════════════════════
# Baseline — a gain with no relics at all is unaffected
# ══════════════════════════════════════════════════════════════════════════

def test_no_relic_gain_moves_gold_by_the_full_amount():
    """No relics registered: `gain_gold` still truncates and adds, matching
    `PlayerCmd.GainGold` with an empty listener set — the hook surface being
    added must not change the no-relic case."""
    run = fresh_run()
    before = run.gold
    run.gain_gold(25)
    assert run.gold == before + 25


# ══════════════════════════════════════════════════════════════════════════
# The two full passes: ModifyGoldGained completes entirely before
# AfterGoldGained starts (PlayerCmd.cs:144 vs. :169) — not interleaved
# per-relic, and registration order is preserved within each pass.
# ══════════════════════════════════════════════════════════════════════════

def test_modify_pass_completes_before_the_after_pass_begins():
    log: list[str] = []
    run = fresh_run()
    r1 = _GoldSpy("r1", log)
    r2 = _GoldSpy("r2", log)
    run.relics.append(r1)
    run.relics.append(r2)
    run.gain_gold(10)
    assert log == ["r1.modify", "r2.modify", "r1.after", "r2.after"]


def test_after_gold_gained_dispatches_to_every_relic_present():
    """The after-pass is a full walk, not a first-listener-wins dispatch:
    Dragon Fruit and an unrelated after-listener both fire on one gain."""
    log: list[str] = []
    run = fresh_run()
    run.add_relic("dragon_fruit")
    spy = _GoldSpy("spy", log)
    run.relics.append(spy)
    before_max_hp = run.max_hp
    run.gain_gold(25)
    assert run.max_hp == before_max_hp + 1
    assert spy.seen_after == [(run.gold, 25)]


# ══════════════════════════════════════════════════════════════════════════
# What the after-pass sees: the amount is the MODIFIED, TRUNCATED figure,
# and the balance has already moved (PlayerCmd.cs:168-169).
# ══════════════════════════════════════════════════════════════════════════

def test_after_gold_gained_sees_the_modified_truncated_amount():
    log: list[str] = []
    run = fresh_run()
    doubler = _GoldSpy("doubler", log, multiplier=2.0)
    spy = _GoldSpy("spy", log)
    run.relics.append(doubler)
    run.relics.append(spy)
    start = run.gold
    run.gain_gold(10)  # doubled to 20 before the balance moves
    assert run.gold == start + 20
    assert spy.seen_after == [(start + 20, 20)]


# ══════════════════════════════════════════════════════════════════════════
# The bail (`if (!(amount > 0m)) return;`, PlayerCmd.cs:146-149) tests the
# amount BEFORE truncation, not after — so a fractional gain that truncates
# to 0 gold still clears the bail and still dispatches AfterGoldGained.
# ══════════════════════════════════════════════════════════════════════════

def test_bail_tests_the_pre_truncation_amount():
    log: list[str] = []
    run = fresh_run()
    spy = _GoldSpy("spy", log)
    run.relics.append(spy)
    start = run.gold
    run.gain_gold(0.5)  # int(0.5) == 0, but 0.5 > 0 clears the bail
    assert run.gold == start  # no gold actually moved
    assert spy.seen_after == [(start, 0)]  # but the hook still fired


def test_zero_modified_amount_fires_nothing():
    log: list[str] = []
    run = fresh_run()
    spy = _GoldSpy("spy", log)
    run.relics.append(spy)
    run.gain_gold(0)
    assert spy.seen_after == []


def test_negative_modified_amount_fires_nothing():
    """No shipped relic drives `modify_gold_gained` negative, but the bail
    itself (`amount > 0m`) must reject it exactly like zero — this pins the
    guard's shape, independent of any particular relic reaching it."""
    log: list[str] = []
    run = fresh_run()
    spy = _GoldSpy("spy", log)
    run.relics.append(spy)
    before = run.gold
    run.gain_gold(-5)
    assert run.gold == before
    assert spy.seen_after == []


# ══════════════════════════════════════════════════════════════════════════
# Gold LOSS is a wholly separate command with no hook surface at all
# (`PlayerCmd.LoseGold`, contrast with `GainGold` — no `Hook.*` call in it).
# ══════════════════════════════════════════════════════════════════════════

def test_gold_loss_never_dispatches_after_gold_gained():
    run = fresh_run()
    run.add_relic("dragon_fruit")
    before_max_hp = run.max_hp
    run.gold = 50
    run.lose_gold(10)
    assert run.gold == 40
    assert run.max_hp == before_max_hp
