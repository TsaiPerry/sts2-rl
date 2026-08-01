"""
Tests for `power/_stack_type_single` — PowerStackType.Single (and Dampen's
StackType.None) was misread as "does not stack": 15 sim powers overrode
`on_stack` to `pass`, dropping a re-application's offset, even though
`PowerCmd.ModifyAmount` (PowerCmd.cs:236) is `power.Amount + modifiedOffset`
with NO StackType branch at all. StackType only controls whether the UI
hides the Amount display (PowerStackType.cs:6-13); it has no bearing on
whether `ModifyAmount` runs. `PowerCmd.FindExistingInstanceForStacking`
(PowerCmd.cs:165-174) is what actually gates re-application, and it
dispatches on `InstanceType`, not `StackType` -- confirmed here to be
`PowerInstanceType.None` (the default) for every one of the 16 sites, so
none of them need T1's Instanced/InstancedPerApplier machinery.

The one unit in the family that does NOT override `on_stack` -- Illusion --
is tested here too, to confirm its non-override was already correct.

Run with:  py -m pytest test/test_stack_type_single.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, PowerCmd
from sts2_rl.cards import WoundCard, make_card
from sts2_rl.cmds import CardPileCmd
from sts2_rl.powers import (
    AdaptablePower,
    BurrowedPower,
    ConfusedPower,
    CorruptionPower,
    DampenPower,
    HellraiserPower,
    HexPower,
    IllusionPower,
    ImbalancedPower,
    NemesisPower,
    NoDrawPower,
    NoEnergyGainPower,
    PowerInstanceType,
    PowerType,
    SmoggyPower,
    SoarPower,
    SurroundedPower,
    TheGambitPower,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0, deck=None) -> CombatState:
    return CombatState(rng=random.Random(seed), starting_deck=deck)


# The 15 `on_stack` no-op sites (power_census.py stack), each paired with the
# side it is applied to by its only known appliers (see per-site research in
# the task report): player-self-cast cards/relics vs. monster self-buffs.
ALL_SINGLE_STACK_POWERS = [
    ("no_draw", NoDrawPower, "player"),
    ("no_energy_gain", NoEnergyGainPower, "player"),
    ("corruption", CorruptionPower, "player"),
    ("hellraiser", HellraiserPower, "player"),
    ("hex", HexPower, "player"),
    ("the_gambit", TheGambitPower, "player"),
    ("confused", ConfusedPower, "player"),
    ("smoggy", SmoggyPower, "player"),
    ("surrounded", SurroundedPower, "player"),
    ("dampen", DampenPower, "player"),
    ("adaptable", AdaptablePower, "enemy"),
    ("nemesis", NemesisPower, "enemy"),
    ("imbalanced", ImbalancedPower, "enemy"),
    ("burrowed", BurrowedPower, "enemy"),
    ("soar", SoarPower, "enemy"),
]
_IDS = [row[0] for row in ALL_SINGLE_STACK_POWERS]


# ══════════════════════════════════════════════════════════════════════════
# The fix, swept across all 15 sites: two applications -> Amount 2, same
# instance (not replaced).
# ══════════════════════════════════════════════════════════════════════════

class TestAmountAccumulatesAcrossReapplication:
    @pytest.mark.parametrize("power_id, power_cls, side", ALL_SINGLE_STACK_POWERS, ids=_IDS)
    def test_two_applications_reach_amount_2(self, power_id, power_cls, side):
        cs = fresh()
        target = getattr(cs, side)
        PowerCmd.apply(cs.hooks, target, power_cls, 1)
        first = target.powers[power_id]
        assert first.amount == 1

        PowerCmd.apply(cs.hooks, target, power_cls, 1)
        second = target.powers[power_id]
        assert second is first, (
            "InstanceType.None (the default) must re-use the existing "
            "instance, not overwrite target.powers with a new one "
            "(PowerCmd.cs:165-174 FindExistingInstanceForStacking)"
        )
        assert second.amount == 2, (
            "PowerCmd.ModifyAmount (PowerCmd.cs:236) is `power.Amount + "
            "modifiedOffset` with NO StackType branch -- StackType.Single "
            "only hides the Amount display, it does not gate ModifyAmount"
        )

    @pytest.mark.parametrize("power_id, power_cls, side", ALL_SINGLE_STACK_POWERS, ids=_IDS)
    def test_instance_type_is_none_not_instanced(self, power_id, power_cls, side):
        """Adjacent to power_cmd/G5 (T1, PowerInstanceType): a StackType.Single
        power that were ALSO InstanceType.Instanced/InstancedPerApplier would
        need T1's instance-creation dispatch, not naive amount-adding. None of
        the 16 sites override InstanceType in C# (power_census.py instance),
        so this is expected to hold for all of them -- pinned so a future
        change to one of these units' InstanceType is caught here instead of
        silently mis-stacking."""
        assert power_cls.instance_type is PowerInstanceType.NONE

    def test_census_reports_zero_no_op_overrides(self):
        """power_census.py stack's own live count, imported directly rather
        than shelled out to, so this fails loudly if a 16th site regresses."""
        import inspect
        from sts2_rl.powers import ALL_POWERS
        noop_ids = []
        for uid, cls in ALL_POWERS.items():
            if "on_stack" not in vars(cls):
                continue
            body = inspect.getsource(cls.on_stack).strip().splitlines()[-1].strip()
            if body.startswith("pass"):
                noop_ids.append(uid)
        assert noop_ids == []


# ══════════════════════════════════════════════════════════════════════════
# Representative sites, spelled out individually with different power_types
# (brief step 4) -- the parametrized sweep above is the mechanical closure;
# these three are the readable, named TDD evidence.
# ══════════════════════════════════════════════════════════════════════════

class TestRepresentativeSites:
    def test_no_draw_is_a_debuff_and_stacks(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, NoDrawPower, 1)
        PowerCmd.apply(cs.hooks, cs.player, NoDrawPower, 1)
        power = cs.player.powers["no_draw"]
        assert power.power_type is PowerType.DEBUFF
        assert power.amount == 2

    def test_corruption_is_a_buff_and_stacks(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
        PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
        power = cs.player.powers["corruption"]
        assert power.power_type is PowerType.BUFF
        assert power.amount == 2

    def test_soar_is_an_enemy_buff_and_stacks(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SoarPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, SoarPower, 1)
        power = cs.enemy.powers["soar"]
        assert power.power_type is PowerType.BUFF
        assert power.amount == 2


# ══════════════════════════════════════════════════════════════════════════
# Illusion -- the ONE unit that does NOT override on_stack. Confirm its
# non-override is correct as-is: default additive stacking, and __init__'s
# one-time Minion grant must not re-fire on the second application (mirrors
# AfterApplied not being called on the ModifyAmount/re-stack path in C#
# either -- PowerCmd.cs:67-89/101-159 only calls AfterApplied on the
# brand-new-instance branch).
# ══════════════════════════════════════════════════════════════════════════

class TestHexAmountFeedsLaterAfflictions:
    """`audit/records/power/hex.json`'s StackType finding calls out Hex as
    the ONE exception among the 15: unlike the other 14, its Amount IS read
    -- `HexPower.cs:79`'s `CardCmd.Afflict<Hexed>(card, base.Amount)` feeds
    every newly-entering card's Hexed affliction amount. The record notes
    this stayed dormant only because the sole applier (Spectral Knight)
    applies Hex once and KNIGHTS_ELITE fields exactly one Spectral Knight;
    "trigger: a second Spectral Knight or a second Hex application." This
    pins the exact citation: after two Hex applications, a card entering
    combat afterward must be Hexed at amount 2, not 1."""

    def test_second_application_afflicts_a_later_card_at_amount_2(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, HexPower, 1, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.player, HexPower, 1, applier=cs.enemy)
        assert cs.player.powers["hex"].amount == 2

        new_card = WoundCard()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, new_card)
        assert new_card.affliction is not None
        assert new_card.affliction.id == "hexed"
        assert new_card.affliction.amount == 2


class TestIllusionNonOverrideIsCorrect:
    def test_illusion_stacks_by_default(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, IllusionPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, IllusionPower, 1)
        assert cs.enemy.powers["illusion"].amount == 2

    def test_illusion_reapplication_does_not_regrant_minion(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, IllusionPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, IllusionPower, 1)
        # __init__ (mirroring AfterApplied) only runs on the first, brand-new
        # instance; the second application must route through on_stack alone.
        assert cs.enemy.powers["minion"].amount == 1


# ══════════════════════════════════════════════════════════════════════════
# Dampen (StackType.None, not Single -- power_census.py stack cites its
# actual C# StackType per-site). T28 gave it a caster set
# (powers.py DampenPower, ~3710-3793); confirm that machinery is unregressed
# by deleting the on_stack no-op.
# ══════════════════════════════════════════════════════════════════════════

class TestDampenCasterSetUnregressed:
    def test_two_casters_power_persists_until_both_die(self):
        """Mirrors DampenPower.cs:41-56 / MagiKnight.DampenMove -- a second
        live caster keeps the downgrade in place after the first dies; only
        an EMPTY caster set expires the power and restores the upgrades."""
        deck = [make_card("strike") for _ in range(2)]
        deck[0].upgrade()
        cs = fresh(deck=deck)
        assert deck[0].upgrade_level == 1

        caster_a, caster_b = object(), object()
        PowerCmd.apply(cs.hooks, cs.player, DampenPower, 1, applier=caster_a)
        dampen = cs.player.powers["dampen"]
        dampen.add_caster(caster_a)
        assert deck[0].upgrade_level == 0          # AfterApplied's downgrade pass
        dampen.add_caster(caster_b)

        dampen.on_death(caster_a)
        assert "dampen" in cs.player.powers
        assert deck[0].upgrade_level == 0           # caster_b still alive

        dampen.on_death(caster_b)
        assert "dampen" not in cs.player.powers
        assert deck[0].upgrade_level == 1            # restored once both are dead

    def test_direct_reapplication_does_not_redowngrade_or_double_restore(self):
        """A second PowerCmd.apply on an existing instance now routes through
        the default additive on_stack (deleted override), exactly like the
        other 14 sites. That must NOT re-run the __init__-hosted downgrade
        pass (mirrors AfterApplied never firing on C#'s ModifyAmount path),
        and a later expiry must restore the upgrade exactly once."""
        deck = [make_card("strike") for _ in range(2)]
        deck[0].upgrade()
        cs = fresh(deck=deck)
        caster = object()

        PowerCmd.apply(cs.hooks, cs.player, DampenPower, 1, applier=caster)
        dampen = cs.player.powers["dampen"]
        dampen.add_caster(caster)
        assert deck[0].upgrade_level == 0

        PowerCmd.apply(cs.hooks, cs.player, DampenPower, 1, applier=caster)
        assert dampen.amount == 2
        assert deck[0].upgrade_level == 0             # not re-downgraded

        dampen.on_death(caster)
        assert deck[0].upgrade_level == 1              # restored exactly once
