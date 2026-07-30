"""`Creature.CanReceivePowers` and `CombatState.HittableEnemies` (round 7).

Pins the two source predicates the sim had approximated with `is_gone`:

* `Creature.CanReceivePowers` (Creature.cs:308-322) — "in combat AND
  `Hook.ShouldAllowHitting`". It deliberately does NOT test `IsDead`; its own
  doc comment says "dead creatures can still have powers applied to them".
  The refusal is `CombatState == null`, i.e. the corpse was REMOVED, which
  `CreatureCmd.KillWithoutCheckingWinCondition` only does when
  `Hook.ShouldCreatureBeRemovedFromCombatAfterDeath` agrees
  (CreatureCmd.cs:508, :523-531 -> CombatState.cs:277-304).
* `CombatState.HittableEnemies` (CombatState.cs:142) —
  `Enemies.Where(e => e.IsHittable)` with `IsHittable = !IsDead &&
  Hook.ShouldAllowHitting` (Creature.cs:285-299). NOT "enemies that are not
  gone".

Queue entries: card/bash, card/break, card/fight_me, card/mad_science,
card/mangle, card/squash, card/taunt, card/tremble, card/uppercut,
card/whistle (all /OnPlay) and relic/parrying_shield/g1.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, DamageCmd, PowerCmd, make_relic
from sts2_rl.cards import make_card
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.monsters.overgrowth.fogmog import EyeWithTeeth
from sts2_rl.powers import Power, PowerType, VulnerablePower


class _StaysInCombatPower(Power):
    """`SteamEruptionPower.cs:23-35`'s exact pair of overrides —
    `ShouldCreatureBeRemovedFromCombatAfterDeath` and
    `ShouldStopCombatFromEnding`, with NO `ShouldAllowHitting`.
    `PainfulStabsPower.cs:29-32` is the same removal override on its own.

    That is the state C# calls "dead, still in `Enemies`, still
    `CanReceivePowers`" — the row every card in this batch disagreed with the
    game on, and the one row `is_gone` cannot express."""

    id = "_stays_in_combat"
    name = "Stays In Combat"
    power_type = PowerType.BUFF

    def should_power_be_removed_after_owner_death(self) -> bool:
        return False

    def should_stop_combat_from_ending(self) -> bool:
        return True

    def should_remove_from_combat_after_death(self, creature) -> bool:
        return creature is not self.owner


def _two_slimes(seed: int = 0) -> CombatState:
    """Two enemies so a single death never puts the combat in the `IsEnding`
    window that `PowerCmd.Apply`'s own first guard would swallow."""
    return CombatState(rng=random.Random(seed),
                       encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]))


def _retained_corpse(cs: CombatState):
    victim = cs.enemies[0]
    PowerCmd.apply(cs.hooks, victim, _StaysInCombatPower, 1)
    DamageCmd.deal(cs.hooks, victim, 999, dealer=cs.player)
    assert victim.is_dead and victim.retained_after_death
    return victim


# ══════════════════════════════════════════════════════════════════════════
# CanReceivePowers itself
# ══════════════════════════════════════════════════════════════════════════

class TestCanReceivePowers:
    def test_ordinary_corpse_is_removed_and_refuses_powers(self):
        """The `CombatState == null` half. An ordinary kill removes the
        creature (CreatureCmd.cs:523-531), so `CanReceivePowers` is false."""
        cs = _two_slimes()
        victim = cs.enemies[0]
        DamageCmd.deal(cs.hooks, victim, 999, dealer=cs.player)
        assert victim.is_removed_from_combat
        PowerCmd.apply(cs.hooks, victim, VulnerablePower, 2, applier=cs.player)
        assert "vulnerable" not in victim.powers

    def test_retained_corpse_still_receives_powers(self):
        """The half the sim was missing: dead but NOT removed, and nothing
        vetoing the hit, so C# applies (Creature.cs:301-322)."""
        cs = _two_slimes()
        victim = _retained_corpse(cs)
        assert not victim.is_removed_from_combat
        PowerCmd.apply(cs.hooks, victim, VulnerablePower, 2, applier=cs.player)
        assert victim.powers["vulnerable"].amount == 2

    def test_reviving_corpse_still_refuses(self):
        """`ShouldAllowHitting` is the other half and round 6 already wired it;
        an Illusion mid-revive stays refused (IllusionPower.cs:95-105)."""
        cs = CombatState(rng=random.Random(0),
                         encounter=Encounter("test", [EyeWithTeeth, LeafSlimeS]))
        eye = cs.enemies[0]
        DamageCmd.deal(cs.hooks, eye, 999, dealer=cs.player)
        assert eye.retained_after_death
        PowerCmd.apply(cs.hooks, eye, VulnerablePower, 2, applier=cs.player)
        assert "vulnerable" not in eye.powers


# ══════════════════════════════════════════════════════════════════════════
# HittableEnemies
# ══════════════════════════════════════════════════════════════════════════

class TestHittableEnemies:
    def test_excludes_an_alive_but_unhittable_enemy(self):
        cs = CombatState(rng=random.Random(0),
                         encounter=Encounter("test", [EyeWithTeeth, LeafSlimeS]))
        eye = cs.enemies[0]
        DamageCmd.deal(cs.hooks, eye, 999, dealer=cs.player)
        # `living_enemies()` is `not is_gone`; HittableEnemies is
        # `!IsDead && ShouldAllowHitting`.
        assert eye not in cs.hittable_enemies

    def test_excludes_a_retained_corpse(self):
        cs = _two_slimes()
        victim = _retained_corpse(cs)
        assert victim in cs.enemies
        assert victim not in cs.hittable_enemies


class TestParryingShield:
    def test_shield_never_aims_at_an_unhittable_enemy(self):
        """relic/parrying_shield/g1 — ParryingShield.cs:28 draws over
        `CombatState.HittableEnemies`, so a reviving Illusion is not a
        candidate and the CombatTargets draw sees a shorter list."""
        cs = CombatState(rng=random.Random(0),
                         encounter=Encounter("test", [EyeWithTeeth, LeafSlimeS]),
                         relics=[make_relic("parrying_shield")])
        eye = cs.enemies[0]
        DamageCmd.deal(cs.hooks, eye, 999, dealer=cs.player)
        relic = cs.relics[0]
        assert eye not in relic.hittable_enemies()
        assert relic.hittable_enemies() == [cs.enemies[1]]


# ══════════════════════════════════════════════════════════════════════════
# The card sites — the guard C# does not have
# ══════════════════════════════════════════════════════════════════════════

def _corpse_combat(seed: int = 0):
    """One enemy, already a retained corpse and still hittable. `ShouldStop-
    CombatFromEnding` keeps `IsEnding` false, so `PowerCmd.Apply`'s own first
    guard is not what is under test, and with every enemy gone
    `CombatCtx.resolve_target` hands the card the corpse."""
    cs = CombatState(rng=random.Random(seed),
                     encounter=Encounter("test", [LeafSlimeS]))
    victim = cs.enemies[0]
    PowerCmd.apply(cs.hooks, victim, _StaysInCombatPower, 1)
    DamageCmd.deal(cs.hooks, victim, 999, dealer=cs.player)
    assert victim.is_dead and victim.retained_after_death
    assert not cs.is_ending
    return cs, victim


@pytest.mark.parametrize("card_id,power_id", [
    ("bash", "vulnerable"),
    ("break", "vulnerable"),
    ("squash", "vulnerable"),
    ("uppercut", "vulnerable"),
    ("tremble", "vulnerable"),
    ("taunt", "vulnerable"),
    ("mangle", "mangle"),
])
def test_card_applies_its_power_to_a_retained_corpse(card_id, power_id):
    """None of these cards has a liveness guard in C# — the only gate is
    `CanReceivePowers`, which a retained corpse passes."""
    cs, victim = _corpse_combat()
    make_card(card_id).on_play(cs._ctx(), target_idx=0)
    assert power_id in victim.powers


def test_fight_me_gives_the_corpse_its_strength():
    """FightMe.cs:41 — the ENEMY Strength is unguarded, exactly like the SELF
    one on the line above it."""
    cs, victim = _corpse_combat()
    make_card("fight_me").on_play(cs._ctx(), target_idx=0)
    assert victim.powers["strength"].amount == 1


def test_whistle_stuns_a_retained_corpse():
    """`CreatureCmd.Stun` has no liveness guard in either overload
    (CreatureCmd.cs:870-903), and a retained corpse still takes turns."""
    cs, victim = _corpse_combat()
    make_card("whistle").on_play(cs._ctx(), target_idx=0)
    assert victim.stunned


def test_mad_science_rider_lands_on_a_retained_corpse():
    from sts2_rl.cards import CardType
    cs, victim = _corpse_combat()
    card = make_card("mad_science").configure(CardType.ATTACK, "sapping")
    card.on_play(cs._ctx(), target_idx=0)
    assert "weak" in victim.powers and "vulnerable" in victim.powers


def test_cards_still_skip_a_removed_corpse():
    """The other side of the same coin: an ORDINARY kill removes the creature,
    so the power must not land. Before round 7 the card's own `is_gone` guard
    did this; now `PowerCmd.apply`'s CanReceivePowers gate does."""
    cs = _two_slimes()
    victim = cs.enemies[0]
    victim.hp = 1
    make_card("bash").on_play(cs._ctx(), target_idx=0)
    assert victim.is_dead and victim.is_removed_from_combat
    assert "vulnerable" not in victim.powers
