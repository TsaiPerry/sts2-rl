"""Order-tracing tests pinning engine-seam hook sequences (Tier 2 of
docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md).

`trace` wraps HookSystem instance methods to record invocation order. These
tests are the durable form of the seam audits: a future edit cannot
silently reorder a pipeline without a failure here.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import (
    ArtifactPower,
    CombatState,
    DamageCmd,
    DexterityPower,
    PowerCmd,
    ThornsPower,
    ValueProp,
    VulnerablePower,
    DamageProps,
)
from sts2_rl.cards import StrikeCard


def trace(hooks, names):
    """Record invocation order of the named hooks on this HookSystem.

    Wraps each named hook on the *instance* in place and never unwraps, so
    pass a throwaway combat's `cs.hooks` (see `fresh`). Raises AttributeError
    on a name HookSystem doesn't define, so a typo'd hook can't produce a
    vacuously passing test, and ValueError if a name is already traced —
    re-wrapping would capture the previous wrapper and append into both
    lists. To watch more hooks, pass them all in one call.
    """
    calls: list[str] = []
    for name in names:
        if name in vars(hooks):
            raise ValueError(f"{name} is already traced on this HookSystem")
        orig = getattr(hooks, name)

        def make(name=name, orig=orig):
            def wrapper(*args, **kwargs):
                calls.append(name)
                return orig(*args, **kwargs)
            return wrapper

        setattr(hooks, name, make())
    return calls


PIPELINE = [
    "modify_damage_additive",
    "modify_damage_multiplicative",
    "modify_damage_cap",
    "on_attacked",
    "modify_hp_lost",
    "should_die",
    "on_damage_received",
]


def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


class TestTraceHelper:
    """The seam audits (Tasks 5-10) all pin their findings through `trace`,
    so its two loud-failure guarantees are themselves pinned here."""

    def test_unknown_hook_name_raises(self):
        with pytest.raises(AttributeError):
            trace(fresh().hooks, ["modify_damage_addative"])

    def test_double_tracing_a_hook_raises(self):
        hooks = fresh().hooks
        trace(hooks, ["on_attacked"])
        with pytest.raises(ValueError):
            trace(hooks, ["on_attacked"])


class TestDamagePipelineOrder:
    def test_non_lethal_hit_order(self):
        """DamageCmd.deal source order: additive -> multiplicative -> cap ->
        on_attacked -> block -> modify_hp_lost -> apply -> (death check) ->
        on_damage_received. should_die must NOT fire on a non-lethal hit."""
        cs = fresh()
        calls = trace(cs.hooks, PIPELINE)
        DamageCmd.deal(cs.hooks, cs.enemy, 6, dealer=cs.player, card=StrikeCard())
        assert [c for c in calls if c in PIPELINE] == [
            "modify_damage_additive",
            "modify_damage_multiplicative",
            "modify_damage_cap",
            "on_attacked",
            "modify_hp_lost",
            "on_damage_received",
        ]

    def test_killing_blow_skips_on_damage_received(self):
        """The game skips the victim's AfterDamageReceived on a kill
        (CreatureCmd.cs:392 `!WasTargetKilled || !IsDead`); the sim guards
        with `if not target.is_dead` in DamageCmd.deal."""
        cs = fresh()
        cs.enemy.hp = 1
        calls = trace(cs.hooks, PIPELINE)
        DamageCmd.deal(cs.hooks, cs.enemy, 6, dealer=cs.player, card=StrikeCard())
        assert "should_die" in calls
        assert "on_damage_received" not in calls

    def test_unblockable_skips_block_absorption(self):
        """damage_pipeline audit, spec step 7 (CreatureCmd.cs:264-265,
        Creature.cs:430-435): ValueProp.Unblockable damage bypasses
        DamageBlockInternal entirely (blocked = 0 regardless of Block), so a
        creature holding block still takes the full HP loss. Unlike
        TestPoison.test_deals_unblockable_damage_on_enemy_turn_start (whose
        block is confounded by the normal turn-start block-clear), this
        calls DamageCmd.deal directly against a creature that still holds
        block at call time."""
        cs = fresh()
        cs.enemy.block = 10
        hp_before = cs.enemy.hp
        DamageCmd.deal(
            cs.hooks, cs.enemy, 5, dealer=cs.player,
            props=DamageProps.NON_CARD_HP_LOSS,  # Unblockable | Unpowered
        )
        assert cs.enemy.hp == hp_before - 5  # block untouched, full HP loss
        assert cs.enemy.block == 10

    @pytest.mark.xfail(
        reason="gap G1 (audits/seam/damage_pipeline.json): ThornsPower is "
               "wired to on_damage_received, which cmds.py's killing-blow "
               "guard skips entirely (`if not target.is_dead`). C#'s "
               "ThornsPower overrides BeforeDamageReceived (ThornsPower.cs:"
               "17-24), which CreatureCmd.Damage fires unconditionally "
               "before block/HP/death are even resolved (CreatureCmd.cs:"
               "263) -- so the real game reflects Thorns damage even on the "
               "hit that kills the Thorns-bearer.",
        strict=True,
    )
    def test_thorns_reflects_even_on_killing_blow(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        cs.player.hp = 1
        enemy_hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.player.is_dead
        assert cs.enemy.hp == enemy_hp_before - 3  # C# still reflects


class TestPowerCmdOrder:
    """power_cmd audit (docs/audit/seams/power_cmd.md): pins the ordering
    the Unsettling Lamp fix depends on, plus the sign-aware-typing gap (G1)
    found auditing the rest of the seam."""

    def test_modify_power_amount_runs_before_artifact_block(self):
        """PowerCmd.cs:122-127: Hook.ModifyPowerAmountGiven (the sim's
        modify_power_amount, which Unsettling Lamp's doubling hooks into)
        runs BEFORE Hook.ModifyPowerAmountReceived (Artifact's veto) --
        cmds.py:297-306 mirrors this ordering (`amount =
        hooks.modify_power_amount(...)` precedes the Artifact block). A
        debuff Artifact fully blocks still goes through modify_power_amount
        first, and Artifact consumes exactly its one stack."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        calls = trace(cs.hooks, ["modify_power_amount"])
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        assert "modify_power_amount" in calls
        assert "vulnerable" not in cs.enemy.powers   # debuff blocked
        assert "artifact" not in cs.enemy.powers     # its one stack consumed

    @pytest.mark.xfail(
        reason="power_cmd audit gap G1 (audits/seam/power_cmd.json): "
               "PowerCmd.apply's Artifact check (cmds.py:299) tests the "
               "static power_cls.power_type class attribute instead of C#'s "
               "sign-aware GetTypeForAmount(amount) (PowerModel.cs:460-471, "
               "consumed by ArtifactPower.cs:24). A negative-amount "
               "application of a Buff-typed, allow_negative power (Strength/"
               "Dexterity) is a Debuff by C#'s rule but never even reaches "
               "the sim's Artifact branch, since power_cls.power_type stays "
               "BUFF regardless of sign. Live via "
               "monsters/glory/the_lost_and_forgotten.py:54,99 and "
               "monsters/underdocks/lagavulin_matriarch.py:106-107, both of "
               "which steal Strength/Dexterity from the player via a "
               "negative-amount PowerCmd.apply call.",
        strict=True,
    )
    def test_artifact_blocks_negative_signed_debuff(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        # Mirrors the Lost and Forgotten / Lagavulin Matriarch steal shape:
        # a negative amount applied to a Buff-typed, allow_negative power.
        PowerCmd.apply(cs.hooks, cs.enemy, DexterityPower, -3, applier=cs.player)
        assert "dexterity" not in cs.enemy.powers  # C#: Artifact blocks the steal
        assert "artifact" not in cs.enemy.powers   # and consumes its stack
