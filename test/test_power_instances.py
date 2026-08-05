"""`Creature.powers` as C#'s ordered `List<PowerModel>` (phase 0 of
OBS_SCHEMA.md; closes `power_cmd/G5`).

`Creature.powers` used to be a `dict[str, Power]`, one slot per power id. A
`PowerInstanceType.Instanced` application would overwrite that slot: the
displaced instance stayed hook-registered and kept ticking, but nothing could
read it, so a creature could never be observed holding two of a power. It is
`creatures.PowerList` now — C#'s `_powers` list (Creature.cs:34) with C#'s own
accessors (`GetPower` = FirstOrDefault, `GetPowerInstances` = Where,
`Powers` = all).

Run with:  py -m pytest test/test_power_instances.py -q
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import Creature
from sts2_rl.cards import make_card
from sts2_rl.cmds import CreatureCmd, PowerCmd
from sts2_rl.combat import CombatState
from sts2_rl.full_env import POWER_INDEX, _clip01, _signed, build_combat_obs, combat_obs_layout
from sts2_rl.powers import (
    PowerInstanceType,
    SandpitPower,
    StranglePower,
    StrengthPower,
    TheBombPower,
    VulnerablePower,
)


def fresh(seed: int = 0, **kwargs) -> CombatState:
    return CombatState(rng=random.Random(seed), **kwargs)


# ══════════════════════════════════════════════════════════════════════════
# The container itself
# ══════════════════════════════════════════════════════════════════════════

class TestPowerListAccessors:
    def test_get_is_first_or_default_not_newest(self):
        """`Creature.GetPower(id)` (Creature.cs:571) is a `FirstOrDefault`, so
        it answers with the OLDEST instance. The dict it replaced answered
        with the newest, which is the trap every "configure what I just
        applied" call site fell into."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        first, second = cs.enemy.powers.instances("sandpit")
        assert cs.enemy.powers.get("sandpit") is first
        assert cs.enemy.powers["sandpit"] is first
        assert second.amount == 2

    def test_values_walks_every_instance_in_application_order(self):
        """`Creature.Powers` (Creature.cs:326) is the raw list — the hook
        walk, the death strip and the turn-start snapshot all iterate it, and
        all three must see both instances."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, 2)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        assert [p.id for p in cs.enemy.powers.values()] == [
            "strength", "sandpit", "sandpit"]
        assert len(cs.enemy.powers) == 3

    def test_iteration_and_membership_stay_id_shaped(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        assert "sandpit" in cs.enemy.powers
        assert "strength" not in cs.enemy.powers
        assert list(cs.enemy.powers) == ["sandpit"]     # each id once
        assert set(cs.enemy.powers) == {"sandpit"}

    def test_missing_id_raises_keyerror_and_get_defaults(self):
        cs = fresh()
        with pytest.raises(KeyError):
            cs.enemy.powers["nope"]
        assert cs.enemy.powers.get("nope") is None
        assert cs.enemy.powers.get("nope", "x") == "x"

    def test_expire_removes_by_identity_not_by_id(self):
        """`Creature.RemovePowerInternal` (Creature.cs:641-650) removes THAT
        object. A pop-by-id would take the wrong sandpit off the list."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        first, second = cs.enemy.powers.instances("sandpit")
        second._expire()
        assert cs.enemy.powers.instances("sandpit") == (first,)
        assert second not in cs.hooks._listeners
        assert first in cs.hooks._listeners

    def test_a_non_instanced_power_can_never_be_added_twice(self):
        """C#'s own guard in ApplyPowerInternal (Creature.cs:607-610). Reaching
        it means the command layer skipped the stacking branch."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        clone = VulnerablePower(owner=cs.enemy, amount=2, hooks=cs.hooks)
        with pytest.raises(RuntimeError):
            cs.enemy.powers.add(clone)


# ══════════════════════════════════════════════════════════════════════════
# Dispatch: every instance is a listener, in application order
# ══════════════════════════════════════════════════════════════════════════

class TestEveryInstanceParticipates:
    def test_hook_walk_lists_both_instances_in_application_order(self):
        """`CombatState.IterateHookListeners` does `AddRange(creature.Powers)`
        (CombatState.cs:416) — the whole list, not one per id."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        first, second = cs.enemy.powers.instances("sandpit")
        listeners = cs.hooks._ordered()
        assert listeners.index(first) < listeners.index(second)

    def test_turn_start_snapshot_covers_every_instance(self):
        """`Creature.BeforeTurnStart` (Creature.cs:673-679) walks `_powers`."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        cs.enemy.snapshot_powers_on_turn_start()
        assert [p.amount_on_turn_start
                for p in cs.enemy.powers.instances("sandpit")] == [4, 2]

    def test_death_strips_every_instance(self):
        """`RemoveAllPowersAfterDeath` (Creature.cs:667-671) walks `_powers`,
        so a second instance cannot survive its owner."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        CreatureCmd.kill(cs.hooks, cs.enemy)
        assert cs.enemy.powers.instances("sandpit") == ()


# ══════════════════════════════════════════════════════════════════════════
# FindExistingInstanceForStacking over a real instance list
# ══════════════════════════════════════════════════════════════════════════

class TestFindExistingInstanceForStacking:
    def test_per_applier_searches_every_instance_not_just_the_newest(self):
        """`InstancedPerApplier` is
        `GetPowerInstances(id).FirstOrDefault(p => p.Applier == applier)`
        (PowerCmd.cs:168) — a search over ALL instances. The dict could only
        offer its single slot, so a third application by an applier who
        already had one, made after a SECOND applier displaced that slot,
        wrongly started a third instance."""
        cs = fresh()
        other = Creature(max_hp=40)
        PowerCmd.apply(cs.hooks, cs.enemy, StranglePower, 3, applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.enemy, StranglePower, 4, applier=other)
        PowerCmd.apply(cs.hooks, cs.enemy, StranglePower, 2, applier=cs.player)

        held = cs.enemy.powers.instances("strangle")
        assert len(held) == 2                       # not three
        assert [p.applier for p in held] == [cs.player, other]
        assert held[0].amount == 5                  # 3 + 2, back onto its own
        assert held[1].amount == 4

    def test_apply_returns_the_instance_it_produced(self):
        """`Apply<T>` returns the power it created or stacked
        (PowerCmd.cs:66-87) — the only correct handle for a caller that
        configures what it just applied."""
        cs = fresh()
        created = PowerCmd.apply(cs.hooks, cs.player, TheBombPower, 3,
                                 applier=cs.player)
        second = PowerCmd.apply(cs.hooks, cs.player, TheBombPower, 3,
                                applier=cs.player)
        assert created is not second
        assert cs.player.powers.instances("the_bomb") == (created, second)

        stacked = PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2)
        assert PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 1) is stacked

    def test_apply_returns_none_when_nothing_was_applied(self):
        cs = fresh()
        assert PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 0) is None
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3)
        # Stacking to exactly 0 removes the power; `Apply<T>` nulls its result
        # when ModifyAmount lands on 0 (PowerCmd.cs:84-86).
        assert PowerCmd.apply(cs.hooks, cs.player, StrengthPower, -3) is None
        assert "strength" not in cs.player.powers


# ══════════════════════════════════════════════════════════════════════════
# What the observation can now say (the phase-2 residue, CLOSED by phase 1)
# ══════════════════════════════════════════════════════════════════════════

class TestObservationResidue:
    def test_two_instances_are_two_distinct_observation_rows_with_their_own_aux(self):
        """This test used to be a deliberate tripwire, not a passing test —
        `test_power_triples_still_collapse_instances_to_one_slot` (see git
        history), whose own docstring said "closing that is phase 1's
        integer schema" so the gap phase 0 explicitly declined to claim could
        not quietly be forgotten. `power_cmd/G5` was closed CONSERVATIVELY
        at phase 0: `Creature.powers` became the ordered instance list this
        whole file tests, but `full_env.power_triples` still wrote one
        `(presence, fine, coarse)` triple per power id — with two `the_bomb`
        fuses, the newest instance's amount overwrote the older one's slot,
        so the observation could not distinguish "one fuse at 7" from "two
        fuses, 5 and 2" even though the engine-side state (this file's own
        `TestFindExistingInstanceForStacking.test_apply_returns_the_instance_
        it_produced`, right above) already tracked them as two independently-
        ticking instances.

        Phase 1 (OBS_SCHEMA.md; T4, `sts2_rl/full_env.py`) closed it for
        real: `player.powers` is now a padded ROW block (`.ids` / `.f`, 32
        rows × 1 int / 3 floats — OBS_SCHEMA.md Sec.5.1/5.2), one row per
        POWER INSTANCE in `creature.powers.values()`'s own application
        order, not one slot per id. Two `the_bomb` fuses now occupy two
        separate rows, each with its own `aux` (OBS_SCHEMA.md Sec.5.2's
        `_power_aux` table: the fuse's own `damage`) — the exact property
        `creature.powers` being an ordered *list* rather than a `dict` was
        FOR, all the way back at phase 0.

        Inverting a closed tripwire into its own closure test, rather than
        deleting it once the gap it guarded closes, is the same move phase 0
        itself made with round 14's witness test (see MEMORY.md) — the
        record that the gap ever existed is worth more than a clean diff.
        (`test_combat_obs_v4.py`'s own
        `test_the_bomb_two_instances_are_two_rows_with_distinct_aux` pins
        this identical property from `full_env.py`'s side of the seam; this
        is that property witnessed from `Creature.powers`' side, in the file
        that owns the state the observation now faithfully encodes.)
        """
        cs = fresh()
        pw1 = PowerCmd.apply(cs.hooks, cs.player, TheBombPower, 5, applier=cs.player)
        pw1.set_damage(40)
        pw2 = PowerCmd.apply(cs.hooks, cs.player, TheBombPower, 2, applier=cs.player)
        pw2.set_damage(70)
        # Engine-side sanity: still two real, independently-ticking
        # instances (phase 0's whole point), not one dict slot.
        assert [p.amount for p in cs.player.powers.instances("the_bomb")] == [5, 2]

        obs = build_combat_obs(cs)
        layout = combat_obs_layout()
        bomb_id = POWER_INDEX["the_bomb"] + 1
        ids = obs["i"][layout.i_slices["player.powers.ids"]]
        fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)

        rows = [i for i, v in enumerate(ids) if v == bomb_id]
        assert len(rows) == 2, "both instances must appear as separate rows, not one collapsed slot"
        r_old, r_new = rows
        assert r_old < r_new, "oldest instance (pw1) must sit at the lower row index"
        assert fs[r_old][0] == pytest.approx(_signed(5, 10)), "pw1's own amount, not pw2's"
        assert fs[r_new][0] == pytest.approx(_signed(2, 10)), "pw2's own amount, not pw1's"
        assert fs[r_old][2] == pytest.approx(_clip01(40 / 100.0)), "aux must be pw1's own damage"
        assert fs[r_new][2] == pytest.approx(_clip01(70 / 100.0)), "aux must be pw2's own damage, not pw1's"
