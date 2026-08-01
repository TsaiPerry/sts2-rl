"""Task 28 — monster-tier dormant families (audit §2K).

Five independent mechanisms:

* ``monster/_no_intent_unrepresentable`` — Battle Friend's NOTHING_MOVE is
  built from C#'s EMPTY ``params AbstractIntent[]`` (no telegraph at all);
  the sim's ``Intent`` dataclass could not express that.
* ``monster/_intent_count_lost`` — C#'s ``StatusIntent(N)`` carries a card
  count the sim's ``Intent`` dropped (Aeonglass/TheInsatiable/TestSubject).
* ``monster/_retained_corpse_in_scan`` — Guardbot's ``GuardMove`` and Queen's
  ``BurnBrightForMe`` scan C#'s teammate/enemy lists on MEMBERSHIP alone; the
  sim's ports also filtered on liveness, so a death-vetoed retained corpse
  fell out of both scans.
* ``monster/knowledge_demon/g1`` — the curse cards apply their own power with
  the PLAYER as applier; the port used the demon.
* ``monster/magi_knight/g1`` — ``DampenPower``'s caster set collapsed to a
  bare re-apply; MagiKnight now fetches-or-creates and ``DampenPower`` tracks
  every caster, expiring only once the last one dies.

Run with:  py -m pytest test/test_monster_tier_families.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import make_card
from sts2_rl.monsters import Encounter, Intent, MoveType
from sts2_rl.monsters.glory import (
    Aeonglass,
    BattleFriendV1,
    BattleFriendV2,
    BattleFriendV3,
    Fabricator,
    Guardbot,
    MagiKnight,
    Noisebot,
    Queen,
    QUEEN_BOSS,
    TestSubject as SubjectMonster,  # alias: pytest collects any Test* binding
)
from sts2_rl.monsters.hive import KnowledgeDemon, TheInsatiable
from sts2_rl.powers import DampenPower, Power, PowerType
from sts2_rl.valueprops import DamageProps


# ── Helpers ──────────────────────────────────────────────────────────────

def fresh_with(monster_cls, seed: int = 0, deck=None) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc, starting_deck=deck)


def fresh_encounter(enc: Encounter, seed: int = 0, deck=None) -> CombatState:
    return CombatState(rng=random.Random(seed), encounter=enc, starting_deck=deck)


def kill(cs: CombatState, creature) -> None:
    DamageCmd.deal(cs.hooks, creature, 99999, props=DamageProps.NON_CARD_UNPOWERED)


class _StaysInCombatPower(Power):
    """Test-only stand-in for a death-prevention power, matching the pattern
    ``test/test_can_receive_powers.py`` already uses for the same purpose
    (its own ``_StaysInCombatPower``). Answering
    ``should_remove_from_combat_after_death`` False for the owner routes a
    kill through the SIM'S REAL ``retained_after_death`` machinery
    (cmds.py's should_die / should_remove_from_combat_after_death hooks) —
    this is not a hand-set attribute, it is C#'s
    ``Hook.ShouldCreatureBeRemovedFromCombatAfterDeath`` answering no, exactly
    like AdaptablePower/IllusionPower/ReattachPower do for real content."""

    id = "_stays_in_combat_t28"
    name = "Stays In Combat (test)"
    power_type = PowerType.BUFF

    def should_remove_from_combat_after_death(self, creature) -> bool:
        return creature is not self.owner


# ══════════════════════════════════════════════════════════════════════════
# A. monster/_no_intent_unrepresentable
# ══════════════════════════════════════════════════════════════════════════

class TestNoIntentUnrepresentable:
    def test_battle_friend_dummies_construct_a_true_no_intent(self):
        """BattleFriendV1/2/3.cs:28's NOTHING_MOVE builds `new MoveState(...)`
        with an EMPTY `params AbstractIntent[]`. Every flag the encoder tests
        (full_env.py:562-580) must read False -- the same "nothing lit up"
        the empty C# array produces."""
        for cls in (BattleFriendV1, BattleFriendV2, BattleFriendV3):
            cs = fresh_with(cls)
            intent = cs.enemy.current_intent
            assert intent.move_type == MoveType.NONE
            assert intent.also == ()
            for mt in (
                MoveType.ATTACK, MoveType.DEFEND, MoveType.BUFF,
                MoveType.DEBUFF, MoveType.DEBUFF_STRONG, MoveType.CARD_DEBUFF,
                MoveType.STATUS_CARD, MoveType.SUMMON, MoveType.ESCAPE,
                MoveType.HEAL, MoveType.STUN, MoveType.SLEEP,
            ):
                assert not intent.has(mt), mt

    def test_no_intent_is_distinct_from_unset_and_hidden(self):
        """MoveType.NONE must not collide with the sim's two OTHER
        placeholder values: UNKNOWN (state_machine.py's transient
        not-yet-rolled UNSET_MOVE sentinel, mirroring C#'s real, DISPLAYED
        UnknownIntent "?" glyph) or HIDDEN (a real, registered intent with no
        sprite/tip -- DecimillipedeSegment's DEAD_MOVE, HiddenIntent)."""
        cs = fresh_with(BattleFriendV1)
        assert cs.enemy.current_intent.move_type is MoveType.NONE
        assert MoveType.NONE is not MoveType.UNKNOWN
        assert MoveType.NONE is not MoveType.HIDDEN

    def test_intent_none_classmethod(self):
        assert Intent.none() == Intent(MoveType.NONE)


# ══════════════════════════════════════════════════════════════════════════
# B. monster/_intent_count_lost
# ══════════════════════════════════════════════════════════════════════════

class TestIntentCountLost:
    def test_aeonglass_increasing_intensity_carries_wither_count(self):
        """Aeonglass.cs:102 `new StatusIntent(WitherAmount)`; non-ascension
        WitherAmount = 1 (Aeonglass.cs:44)."""
        cs = fresh_with(Aeonglass)
        assert cs.enemy._current_move.id == "EBB_MOVE"
        cs.end_turn()  # perform EBB, roll EYE_LASERS
        assert cs.enemy._current_move.id == "EYE_LASERS_MOVE"
        cs.end_turn()  # perform EYE_LASERS, roll INCREASING_INTENSITY
        assert cs.enemy._current_move.id == "INCREASING_INTENSITY_MOVE"
        intent = cs.enemy.current_intent
        assert intent.has(MoveType.STATUS_CARD)
        assert intent.status_count == 1

    def test_the_insatiable_liquify_ground_carries_status_count(self):
        """TheInsatiable.cs:96 `new StatusIntent(6)` -- a bare literal."""
        cs = fresh_with(TheInsatiable)
        assert cs.enemy._current_move.id == "LIQUIFY_GROUND_MOVE"
        intent = cs.enemy.current_intent
        assert intent.has(MoveType.STATUS_CARD)
        assert intent.status_count == 6

    def test_test_subject_burning_growl_carries_burn_count(self):
        """TestSubject.cs:201 `new StatusIntent(BurningGrowlBurnCount)`;
        non-ascension BurningGrowlBurnCount = 3 (TestSubject.cs:101). Reached
        only in phase 3 (LACERATE -> BIG_POUNCE -> BURNING_GROWL loop), so
        this witness also exercises the double-respawn machinery
        test/test_glory.py's TestTestSubject already pins."""
        cs = fresh_with(SubjectMonster)
        ts = cs.enemy
        kill(cs, ts)
        cs.end_turn()  # RESPAWN -> phase 2 (200 HP)
        kill(cs, ts)
        cs.end_turn()  # RESPAWN -> phase 3 (300 HP), routes to LACERATE
        assert ts._current_move.id == "PHASE3_LACERATE_MOVE"
        cs.player.hp = cs.player.max_hp
        cs.end_turn()  # perform LACERATE, roll BIG_POUNCE
        assert ts._current_move.id == "BIG_POUNCE"
        cs.player.hp = cs.player.max_hp
        cs.end_turn()  # perform BIG_POUNCE, roll BURNING_GROWL
        assert ts._current_move.id == "BURNING_GROWL_MOVE"
        intent = ts.current_intent
        assert intent.has(MoveType.STATUS_CARD)
        assert intent.status_count == 3

    def test_other_status_card_intents_are_unaffected(self):
        """Byte-identical guard: a STATUS_CARD intent NOT among this
        mechanism's three sites (Noisebot's NOISE_MOVE) must keep the
        field's default."""
        cs = fresh_with(Noisebot)
        intent = cs.enemy.current_intent
        assert intent.move_type == MoveType.STATUS_CARD
        assert intent.status_count is None


# ══════════════════════════════════════════════════════════════════════════
# C. monster/_retained_corpse_in_scan
# ══════════════════════════════════════════════════════════════════════════

class TestRetainedCorpseInScan:
    def test_guardbot_scan_reaches_a_retained_fabricator_corpse(self):
        """Guardbot.cs:51 `Enemies.Where(c => c.Monster is Fabricator)` --
        membership of Enemies is the only test, and a death-vetoed corpse is
        still a member."""
        cs = CombatState(rng=random.Random(0),
                          encounter=Encounter("test", [Fabricator, Guardbot]))
        fabricator, guardbot = cs.enemies
        PowerCmd.apply(cs.hooks, fabricator, _StaysInCombatPower, 1)
        DamageCmd.deal(cs.hooks, fabricator, 999, dealer=cs.player)
        assert fabricator.is_dead and fabricator.retained_after_death
        assert fabricator.block == 0
        guardbot._guard(cs._ctx())
        assert fabricator.block == 15  # _GUARD_BLOCK -- reached despite death

    def test_guardbot_scan_still_excludes_an_actually_removed_corpse(self):
        """The over-correction guard: an ORDINARY kill really does drop the
        Fabricator from C#'s Enemies, so it must stay excluded -- the fix is
        `is_removed_from_combat`, not "no filter at all"."""
        cs = CombatState(rng=random.Random(0),
                          encounter=Encounter("test", [Fabricator, Guardbot]))
        fabricator, guardbot = cs.enemies
        DamageCmd.deal(cs.hooks, fabricator, 999, dealer=cs.player)
        assert fabricator.is_removed_from_combat
        guardbot._guard(cs._ctx())
        assert fabricator.block == 0

    def test_queen_scan_reaches_a_retained_amalgam_corpse(self):
        """Queen.cs:187-188 `GetTeammatesOf(Creature).Where(t => t !=
        Creature)` -- membership (minus self) is the only test."""
        cs = fresh_encounter(QUEEN_BOSS)
        amalgam, queen = cs.enemies
        PowerCmd.apply(cs.hooks, amalgam, _StaysInCombatPower, 1)
        DamageCmd.deal(cs.hooks, amalgam, 999, dealer=cs.player)
        assert amalgam.is_dead and amalgam.retained_after_death
        assert "strength" not in amalgam.powers
        queen._burn_bright(cs._ctx())
        assert amalgam.powers["strength"].amount == 1  # reached despite death
        assert queen.block == 20  # own block unaffected by the corpse

    def test_queen_scan_still_excludes_an_actually_removed_corpse(self):
        cs = fresh_encounter(QUEEN_BOSS)
        amalgam, queen = cs.enemies
        DamageCmd.deal(cs.hooks, amalgam, 999, dealer=cs.player)
        assert amalgam.is_removed_from_combat
        queen._burn_bright(cs._ctx())
        assert "strength" not in amalgam.powers


# ══════════════════════════════════════════════════════════════════════════
# D. monster/knowledge_demon/g1
# ══════════════════════════════════════════════════════════════════════════

class TestKnowledgeDemonCurseApplier:
    def test_disintegration_applier_is_the_player_not_the_demon(self):
        """Disintegration.cs:27 `PowerCmd.Apply<DisintegrationPower>(...,
        base.Owner.Creature, amount, base.Owner.Creature, this)` -- target
        AND applier are both the player who owns the card."""
        cs = fresh_with(KnowledgeDemon)
        cs.card_selector = lambda purpose, cands, count: [cands[0]]  # Disintegration
        cs.end_turn()  # CURSE_OF_KNOWLEDGE -> Disintegration 6
        power = cs.player.powers["disintegration"]
        assert power.applier is cs.player
        assert power.applier is not cs.enemy

    def test_mind_rot_applier_is_also_the_player(self):
        """MindRot.cs:27 -- same applier=owner shape as Disintegration."""
        cs = fresh_with(KnowledgeDemon)
        cs.card_selector = lambda purpose, cands, count: [cands[1]]  # Mind Rot
        cs.end_turn()
        power = cs.player.powers["mind_rot"]
        assert power.applier is cs.player
        assert power.applier is not cs.enemy


# ══════════════════════════════════════════════════════════════════════════
# E. monster/magi_knight/g1
# ══════════════════════════════════════════════════════════════════════════

class TestDampenCasterSet:
    def test_second_caster_keeps_the_downgrade_until_both_die(self):
        """MagiKnight.cs:78-96 DampenMove + DampenPower.cs:41-56 AfterDeath:
        a second caster joining an existing Dampen does not re-downgrade, and
        the power only expires once EVERY caster has died. Only one Magi
        Knight exists in shipped content (KNIGHTS_ELITE), so this witness
        builds a throwaway two-Magi-Knight encounter to exercise the
        machinery directly."""
        deck = [make_card("strike") for _ in range(2)]
        deck[0].upgrade()
        cs = CombatState(rng=random.Random(0),
                          encounter=Encounter("test", [MagiKnight, MagiKnight]),
                          starting_deck=deck)
        magi_a, magi_b = cs.enemies
        ctx = cs._ctx()

        magi_a._dampen(ctx)  # first caster: creates the power + downgrades
        assert deck[0].upgrade_level == 0
        dampen = cs.player.powers["dampen"]
        assert dampen._casters == {magi_a}

        magi_b._dampen(ctx)  # second caster: adds to the SAME instance
        assert cs.player.powers["dampen"] is dampen         # not re-created
        assert dampen._casters == {magi_a, magi_b}
        assert deck[0].upgrade_level == 0                    # not re-triggered

        DamageCmd.deal(cs.hooks, magi_a, 999, dealer=cs.player)
        assert "dampen" in cs.player.powers                  # magi_b still alive
        assert deck[0].upgrade_level == 0

        DamageCmd.deal(cs.hooks, magi_b, 999, dealer=cs.player)
        assert "dampen" not in cs.player.powers              # last caster died
        assert deck[0].upgrade_level == 1                    # restored only now

    def test_single_caster_still_restores_on_its_own_death(self):
        """The pre-existing single-caster behaviour
        (test/test_glory.py::TestKnights::test_magi_knight_dampen_downgrades_then_restores)
        must still hold -- this is the same scenario, additionally pinning
        the caster-set's contents and that the power is fully removed."""
        deck = [make_card("strike") for _ in range(2)]
        deck[0].upgrade()
        cs = fresh_with(MagiKnight, deck=deck)
        assert deck[0].upgrade_level == 1
        cs.end_turn()  # Power Shield
        cs.end_turn()  # Dampen -> downgrade the +1 card
        assert deck[0].upgrade_level == 0
        assert cs.player.powers["dampen"]._casters == {cs.enemy}
        kill(cs, cs.enemy)
        assert deck[0].upgrade_level == 1
        assert "dampen" not in cs.player.powers
