"""Tier-2 campaign Task 26 — two §2J mechanisms:

Mechanism A (`creature_card_cmds/step8c` + 5 power sites): the win check's
veto point, `Hook.ShouldStopCombatFromEnding` (Hook.cs:2442-2452,
CombatManager.cs:196). Re-execution found the engine-level hook, its
`combat.py` wiring, and 4 of the 5 ported overrides (Adaptable, Infested,
SteamEruption, Stock) ALREADY landed by earlier campaign rounds
(2026-07-27/28) — only `power/surprise` was still missing its override. This
file pins the general dispatch mechanism (still worth a direct regression
test — nothing else in the suite exercises "a listener vetoes
`_all_enemies_dead` while every enemy is gone" end to end) and the one
power-site fix.

Mechanism B (`power/_after_damage_given_substitution`, 2 entries: imbalanced,
paper_cuts): `Hook.AfterDamageGiven` (Hook.cs:389-396) is the DEALER-side
after-damage event, dispatched to every listener for every hit — blocked or
not, killing or not. `cmds.py`'s `on_damage_dealt` dispatch used to require
`hp_lost > 0`, so a fully-blocked or zero-damage hit was invisible to it;
Imbalanced and PaperCuts had been ported onto `on_damage_received` (the
VICTIM-side, killing-blow-guarded event) instead, filtered on `dealer is
self.owner`, as a workaround. Both are now moved onto the real hook.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd, PowerCmd, ValueProp
from sts2_rl.combat import Phase
from sts2_rl.hooks import _COMBAT_GATED_HOOKS
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.hive.bowlbugs import BowlbugRock
from sts2_rl.monsters.underdocks.gremlin_merc import GremlinMerc, GREMLIN_MERC_NORMAL
from sts2_rl.powers import ImbalancedPower, PaperCutsPower
from sts2_rl.valueprops import DamageProps


def fresh_with(monster_cls, seed: int = 0) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc)


# ═════════════════════════════════════════════════════════════════════════
# Mechanism A — ShouldStopCombatFromEnding
# ═════════════════════════════════════════════════════════════════════════

class TestShouldStopCombatFromEndingVeto:
    def test_is_not_combat_gated(self):
        """The C# dispatcher (Hook.cs:2436-2441) is explicit that gating this
        predicate behind IsOverOrEnding would drop the votes it exists to
        collect -- it must stay one of Hook.cs's ten deliberate bypasses, not
        one of the 73 `_COMBAT_GATED_HOOKS` entries."""
        assert "should_stop_combat_from_ending" not in _COMBAT_GATED_HOOKS

    def test_a_true_listener_vetoes_all_enemies_dead(self):
        """CombatManager.cs:196 — the win check's own last gate. A synthetic
        listener stands in for the five real powers, isolating the dispatch
        mechanism from any one power's spawn/prevention machinery."""
        cs = CombatState(rng=random.Random(0))  # default Fuzzy Wurm encounter
        DamageCmd.deal(cs.hooks, cs.enemies[0], 9999,
                        props=DamageProps.NON_CARD_UNPOWERED)
        assert cs.enemies[0].is_gone
        assert cs._all_enemies_dead()  # baseline: nothing vetoes

        class _Vetoer:
            hook_category = 0

            def should_stop_combat_from_ending(self) -> bool:
                return True

        vetoer = _Vetoer()
        cs.hooks.register(vetoer)
        assert not cs._all_enemies_dead()
        assert cs.is_ending is False  # CombatManager.IsEnding reads the same gate

        cs.hooks.unregister(vetoer)
        assert cs._all_enemies_dead()

    def test_the_veto_still_dispatches_once_the_combat_is_over(self):
        """One of Hook.cs's ten deliberate combat-over bypasses
        (Hook.cs:62-65 lists it by name) -- unlike the 73 `_COMBAT_GATED_HOOKS`
        entries, flipping `Phase.COMBAT_OVER` must not silence it."""
        cs = CombatState(rng=random.Random(0))
        seen = []

        class _Vetoer:
            hook_category = 0

            def should_stop_combat_from_ending(self) -> bool:
                seen.append(1)
                return True

        cs.hooks.register(_Vetoer())
        cs.phase = Phase.COMBAT_OVER
        assert cs.hooks.should_stop_combat_from_ending() is True
        assert seen == [1]

    def test_surprise_power_implements_the_override(self):
        """SurprisePower.cs:40-43 -- an unconditional `return true`, the one
        of the five ported powers that had not been moved onto the hook yet
        (power/surprise/ShouldStopCombatFromEnding, narrowed 2026-07-27)."""
        cs = fresh_with(GremlinMerc)
        merc = cs.enemy
        assert "surprise" in merc.powers
        assert merc.powers["surprise"].should_stop_combat_from_ending() is True

    def test_gremlin_merc_encounter_still_ends_normally(self):
        """Regression: adding the override must not strand the real
        encounter open. Surprise's own spawn already keeps
        `_all_enemies_dead()` false structurally (both gremlins join
        `combat.enemies` before either creature's own construction or the
        Heist application could read `is_ending`, and neither is a minion),
        so the veto never actually fires here -- the encounter must still
        resolve exactly as before."""
        cs = CombatState(rng=random.Random(0), encounter=GREMLIN_MERC_NORMAL)
        merc = cs.enemy
        DamageCmd.deal(cs.hooks, merc, 99, dealer=cs.player)
        assert merc.is_dead
        assert not cs._all_enemies_dead()
        sneaky = cs.enemies[1]
        DamageCmd.deal(cs.hooks, sneaky, 99, dealer=cs.player)
        # Fat Gremlin flees; Sneaky is now dead too, so the fight is over even
        # though Surprise's own veto returns True -- because the merc's copy
        # of the power was already stripped after its own AfterDeath ran
        # (Creature.RemoveAllPowersAfterDeath, cmds.py
        # `_strip_powers_after_death`), and neither gremlin itself carries
        # the power.
        from sts2_rl.cmds import CreatureCmd
        CreatureCmd.escape(cs.hooks, cs.enemies[2])
        assert cs._all_enemies_dead()


# ═════════════════════════════════════════════════════════════════════════
# Mechanism B — on_damage_dealt / AfterDamageGiven
# ═════════════════════════════════════════════════════════════════════════

class _DealtSpy:
    hook_category = 99

    def __init__(self) -> None:
        self.seen: list[tuple] = []

    def on_damage_dealt(self, dealer, target, amount, card=None,
                        props=ValueProp.NONE, was_fully_blocked=False) -> None:
        self.seen.append((dealer, target, amount, was_fully_blocked))


class TestOnDamageDealtSeesEveryHit:
    def test_fires_on_a_fully_blocked_hit(self):
        """The core divergence: C#'s AfterDamageGiven sees a fully-blocked
        hit (`result.WasFullyBlocked` is a field listeners read,
        ImbalancedPower.cs:19); the sim's old `hp_lost > 0` gate made it
        invisible."""
        cs = CombatState(rng=random.Random(0))
        cs.player.block = 999
        spy = _DealtSpy()
        cs.hooks.register(spy)
        dealer = cs.enemies[0]
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=dealer)
        assert spy.seen == [(dealer, cs.player, 0, True)]

    def test_a_zero_damage_unblocked_hit_is_not_was_fully_blocked(self):
        """`WasFullyBlocked` (CreatureCmd.cs:268) requires block to have
        actually been in play (`blockedDamage > 0 || originalTarget.Block >
        0`); a hit that was already 0 before block is a DIFFERENT case the
        old `amount == 0` substitution conflated with this one (recurring gap
        shape 8, per the imbalanced.json record)."""
        cs = CombatState(rng=random.Random(0))
        assert cs.player.block == 0
        spy = _DealtSpy()
        cs.hooks.register(spy)
        dealer = cs.enemies[0]
        DamageCmd.deal(cs.hooks, cs.player, 0, dealer=dealer)
        assert spy.seen == [(dealer, cs.player, 0, False)]

    def test_fires_on_the_killing_blow(self):
        """AfterDamageGiven is NOT killing-blow guarded (CreatureCmd.cs:390
        runs unconditionally on `combatState != null`, unlike
        AfterDamageReceived at :392-395). `on_damage_received` skips a
        killing blow; `on_damage_dealt` must not."""
        cs = CombatState(rng=random.Random(0))
        target = cs.enemies[0]
        spy = _DealtSpy()
        cs.hooks.register(spy)
        DamageCmd.deal(cs.hooks, target, 99999, dealer=cs.player)
        assert target.is_dead
        assert spy.seen == [(cs.player, target, 99999, False)]

    def test_dealer_none_still_fires_nothing(self):
        """No dealer, nothing to attribute the event to -- kept, matching
        the brief's fix sketch (only the `hp_lost > 0` half is dropped)."""
        cs = CombatState(rng=random.Random(0))
        spy = _DealtSpy()
        cs.hooks.register(spy)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=None)
        assert spy.seen == []


class TestImbalancedPowerOnRealHook:
    def test_stuns_owner_on_a_fully_blocked_move(self):
        """ImbalancedPower.cs:17-30: `dealer == base.Owner &&
        result.WasFullyBlocked`, no target check, no MOVE-only gate. Real
        content (BowlbugRock) rather than a synthetic dealer, so the fix is
        checked against an actual applier of the power."""
        cs = fresh_with(BowlbugRock)
        rock = cs.enemy
        assert "imbalanced" in rock.powers
        cs.player.block = 20
        cs.end_turn()  # HEADBUTT (15) fully blocked -> off balance
        assert cs.player.hp == 80
        assert rock.is_off_balance

    def test_does_not_fire_on_a_merely_reduced_hit(self):
        cs = fresh_with(BowlbugRock)
        rock = cs.enemy
        cs.player.block = 10
        cs.end_turn()  # 15 - 10 block = 5 through, NOT fully blocked
        assert cs.player.hp == 75
        assert not rock.is_off_balance

    def test_no_longer_requires_a_move_prop(self):
        """The substitution's `ValueProp.MOVE in props` clause has no C#
        counterpart -- `WasFullyBlocked` does not gate on it. A fully
        blocked NON-card, non-move hit from the owner must still trigger."""
        cs = fresh_with(BowlbugRock)
        rock = cs.enemy
        cs.player.block = 999
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=rock,
                        props=DamageProps.NON_CARD_UNPOWERED)
        assert rock.is_off_balance


class TestPaperCutsPowerOnRealHook:
    def test_costs_max_hp_on_a_killing_blow(self):
        """The record's named divergence: PaperCutsPower.AfterDamageGiven
        fires on a lethal Scroll of Biting hit in the game; the
        `on_damage_received` substitution's killing-blow guard
        (cmds.py step 9, `if not was_lethal`) silently ate it in the sim."""
        cs = CombatState(rng=random.Random(0))
        scroll = cs.enemies[0]
        PowerCmd.apply(cs.hooks, scroll, PaperCutsPower, 2)
        cs.player.hp = 5
        mhp = cs.player.max_hp
        DamageCmd.deal(cs.hooks, cs.player, 999, dealer=scroll)
        assert cs.player.is_dead
        assert cs.player.max_hp == mhp - 2

    def test_still_costs_max_hp_on_a_non_lethal_hit(self):
        """Regression: the non-lethal path (already faithful pre-fix) must
        keep working."""
        cs = CombatState(rng=random.Random(0))
        scroll = cs.enemies[0]
        PowerCmd.apply(cs.hooks, scroll, PaperCutsPower, 2)
        mhp = cs.player.max_hp
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=scroll)
        assert not cs.player.is_dead
        assert cs.player.max_hp == mhp - 2

    def test_does_not_fire_on_a_fully_blocked_hit(self):
        """PaperCuts keys on `result.UnblockedDamage > 0`
        (PaperCutsPower.cs:18) -- a fully blocked hit must not cost max HP,
        unlike Imbalanced which keys on the opposite."""
        cs = CombatState(rng=random.Random(0))
        scroll = cs.enemies[0]
        PowerCmd.apply(cs.hooks, scroll, PaperCutsPower, 2)
        cs.player.block = 999
        mhp = cs.player.max_hp
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=scroll)
        assert cs.player.max_hp == mhp
