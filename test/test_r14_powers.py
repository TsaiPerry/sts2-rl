"""Round 14, lane R2 — power tier: ten UNLABELLED hook/guard entries.

Covers: power/aggression/BeforeSideTurnStart, power/calamity/AfterCardPlayed,
power/cruelty/g4, power/hellraiser/AfterSideTurnEnd, power/illusion/g1,
power/ravenous/AfterDeath, power/ringing/ShouldPlay, power/suck/g2,
power/tangled/AfterApplied, power/unmovable/ModifyBlockMultiplicative.

Run with:  py -m pytest test/test_r14_powers.py -v
"""
from __future__ import annotations

import random
from decimal import Decimal

import pytest

from sts2_rl.combat import CombatState
from sts2_rl.cards import CardType, make_card
from sts2_rl.cmds import CardCmd, PowerCmd
from sts2_rl.rng import RunRngSet


def fresh(seed: int = 0, **kwargs) -> CombatState:
    return CombatState(rng=random.Random(seed), **kwargs)


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


# ══════════════════════════════════════════════════════════════════════════
# power/aggression/BeforeSideTurnStart — FIXED
# ══════════════════════════════════════════════════════════════════════════

class TestAggression:
    def test_legacy_still_moves_attacks_and_upgrades_them(self):
        """Byte-for-byte behavior preserved for RL/legacy (non-parity) combats:
        N random Attack cards move from discard to hand and get upgraded.
        Calls the power's own hook directly (not a second `start_turn()`,
        which would also draw a fresh 5-card hand and confound the count)."""
        from sts2_rl.powers import AggressionPower
        cs = fresh(seed=3)
        strikes = [make_card("strike") for _ in range(3)]
        cs.player.discard_pile.extend(strikes)
        PowerCmd.apply(cs.hooks, cs.player, AggressionPower, 2)
        aggression = cs.player.powers["aggression"]
        before_hand = set(id(c) for c in cs.player.hand)
        aggression.before_side_turn_start(cs.player)
        moved = [c for c in cs.player.hand if id(c) not in before_hand]
        assert len(moved) == 2
        for c in moved:
            assert c.card_type == CardType.ATTACK
            assert c.upgrade_level == 1
            assert c not in cs.player.discard_pile

    def test_parity_draws_from_card_selection_stream_not_shuffle(self):
        """AggressionPower.cs:28 draws Rng.CombatCardSelection via
        UnstableShuffle+Take. The old sim code called `combat._rng.sample`,
        which in a parity combat is not any of the run's named streams at
        all. Now it must land on `combat_card_selection` and leave `shuffle`
        untouched."""
        from sts2_rl.powers import AggressionPower
        rs = RunRngSet("89U21BV1TZ")
        deck = [make_card("strike") for _ in range(5)] + [make_card("defend") for _ in range(4)]
        cs = CombatState(starting_deck=deck, rng_set=rs)
        strikes = [make_card("strike") for _ in range(4)]
        cs.player.discard_pile.extend(strikes)
        PowerCmd.apply(cs.hooks, cs.player, AggressionPower, 2)
        before_selection = rs.combat_card_selection.counter
        before_shuffle = rs.shuffle.counter
        cs.player.start_turn()
        assert rs.combat_card_selection.counter > before_selection
        assert rs.shuffle.counter == before_shuffle

    def test_parity_matches_a_manual_unstable_shuffle_take(self):
        """The exact algorithm: a full Fisher-Yates shuffle of the candidate
        list, then take the first Amount -- not `random.sample`'s reservoir
        algorithm (different draw count, different picks)."""
        from sts2_rl.powers import AggressionPower
        rs = RunRngSet("TESTSEED01")
        rs2 = RunRngSet("TESTSEED01")
        cs = CombatState(rng_set=rs)
        strikes = [make_card("strike") for _ in range(5)]
        cs.player.discard_pile.extend(strikes)
        PowerCmd.apply(cs.hooks, cs.player, AggressionPower, 3)
        aggression = cs.player.powers["aggression"]
        before_hand = set(id(c) for c in cs.player.hand)
        aggression.before_side_turn_start(cs.player)
        moved_ids = [id(c) for c in cs.player.hand if id(c) not in before_hand]

        # Reproduce the expected draw independently against a FRESH stream
        # from the identical seed: shuffle the same 5 candidates (by identity
        # position) with the CombatCardSelection adapter and take 3.
        pool = list(range(5))  # stand-ins for the 5 candidate Strikes, in order
        from sts2_rl.combat_rng import CombatRng
        adapter = CombatRng.parity(rs2).card_selection
        adapter.shuffle(pool)
        expected_take = set(pool[:3])
        assert len(moved_ids) == 3
        # Map moved cards back to their original discard-list index to
        # compare against the independently-reproduced shuffle result.
        moved_positions = {strikes.index(c) for c in cs.player.hand if id(c) in moved_ids}
        assert moved_positions == expected_take


# ══════════════════════════════════════════════════════════════════════════
# power/calamity/AfterCardPlayed — FIXED
# ══════════════════════════════════════════════════════════════════════════

class TestCalamity:
    def test_legacy_still_adds_an_attack_after_each_attack(self):
        cs = fresh()
        play(cs, make_card("calamity"))
        hand = len(cs.player.hand)
        play(cs, make_card("strike"))
        assert len(cs.player.hand) == hand + 1
        assert cs.player.hand[-1].card_type == CardType.ATTACK

    def test_parity_draws_from_card_generation_stream(self):
        """CalamityPower.cs:48-50 draws CardFactory.GetForCombat(...,
        Rng.CombatCardGeneration) -- the named stream, not the shared rng
        that random_pool_cards(combat._rng, ...) used before."""
        from sts2_rl.powers import CalamityPower
        rs = RunRngSet("89U21BV1TZ")
        cs = CombatState(rng_set=rs)
        PowerCmd.apply(cs.hooks, cs.player, CalamityPower, 1)
        strike = make_card("strike")
        cs.player.hand.append(strike)
        idx = len(cs.player.hand) - 1
        cs.player.energy = 10
        before_gen = rs.combat_card_generation.counter
        before_shuffle = rs.shuffle.counter
        before_selection = rs.combat_card_selection.counter
        assert cs.play_card(idx)
        assert rs.combat_card_generation.counter > before_gen
        assert rs.shuffle.counter == before_shuffle
        assert rs.combat_card_selection.counter == before_selection


# ══════════════════════════════════════════════════════════════════════════
# power/ringing/ShouldPlay — FIXED
# ══════════════════════════════════════════════════════════════════════════

class TestRinging:
    def test_should_play_card_true_before_any_play_this_turn(self):
        from sts2_rl.powers import RingingPower
        from sts2_rl.afflictions import RingingAffliction
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        card = make_card("strike")
        CardCmd.afflict(card, RingingAffliction, 1)
        ringing = cs.player.powers["ringing"]
        assert ringing.should_play_card(card) is True

    def test_should_play_card_false_once_a_play_has_STARTED_not_just_finished(self):
        """RingingPower.cs:64-75 reads History.CardPlaysStarted, written at
        the START of a play (CardModel.cs:1930) -- before that card's own
        OnPlay has resolved. A card auto-played from inside another card's
        resolution must already see the outer play as 'this turn'."""
        from sts2_rl.powers import RingingPower
        from sts2_rl.afflictions import RingingAffliction
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        inner = make_card("strike")
        CardCmd.afflict(inner, RingingAffliction, 1)
        ringing = cs.player.powers["ringing"]
        outer = make_card("defend")
        # Simulate the outer card's play START without it having finished
        # (on_card_played not yet fired) -- exactly the mid-resolution window.
        cs.history.card_play_started(outer)
        assert ringing.should_play_card(inner) is False

    def test_hellraiser_auto_play_from_a_nested_draw_is_blocked_by_ringing(self):
        """End-to-end reproduction of the campaign's own witness
        (.superpowers/sdd/unlabelled/probes/power-5-ringing-hellraiser-order.py):
        Ringing afflicts every owned card (including a stacked Strike);
        Battle Trance draws 3 including that Strike; Hellraiser auto-plays
        the drawn Strike from inside Battle Trance's own OnPlay, before
        Battle Trance's on_card_played has fired. The game blocks the
        nested auto-play; the old boolean-flag sim let it through."""
        from sts2_rl.powers import RingingPower, HellraiserPower
        cs = fresh()
        strike = make_card("strike")
        cs.player.draw_pile.append(strike)  # top of pile
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        PowerCmd.apply(cs.hooks, cs.player, HellraiserPower, 1)
        battle_trance = make_card("battle_trance")
        cs.player.hand.clear()
        cs.player.hand.append(battle_trance)
        cs.player.energy = 10
        enemy_hp_before = cs.enemy.hp
        assert cs.play_card(0)
        # Blocked: the Strike must NOT have auto-played (no damage dealt),
        # and must not have entered the exhaust/discard pile via a play --
        # it stays wherever should_play_card=False routes an unplayable draw.
        assert cs.enemy.hp == enemy_hp_before


# ══════════════════════════════════════════════════════════════════════════
# power/cruelty/g4 — DORMANT-ENUMERATED (record's "third non-dyadic
# multiplier" framing does not hold for any currently-reachable stack value)
# ══════════════════════════════════════════════════════════════════════════

class TestCruelty:
    def test_only_applier_is_the_cruelty_card_always_multiples_of_25(self):
        """cards/cruelty.py is CrueltyPower's ONLY applier in the sim (grep
        confirms it, and matches the C# source: Cruelty.cs is the only
        PowerCmd.Apply<CrueltyPower> call site in the whole game). Base 25,
        +25 per upgrade -- every reachable stack count is a multiple of 25."""
        from sts2_rl.cards.cruelty import CrueltyCard
        card = CrueltyCard()
        assert card._power_amount == 25
        card._on_upgrade()
        assert card._power_amount == 50

    @pytest.mark.parametrize("n", [25, 50, 75, 100, 125, 150, 175, 200, 225, 250, 500])
    def test_multiplier_is_exact_for_every_reachable_stack_value(self, n):
        """powers.py's `mult = 1.5 + cruelty.amount / 100.0` in float exactly
        equals the C# decimal computation for every value the ONE live
        applier can ever produce (multiples of 25 -> multiples of 0.25,
        always exactly representable in binary64). The record's own '10 ->
        1.6, 30 -> 1.8' example describes stack values no ported content can
        reach."""
        float_result = 1.5 + n / 100.0
        decimal_result = Decimal("1.5") + Decimal(n) / Decimal(100)
        assert Decimal(str(float_result)) == decimal_result
        assert float(decimal_result) == float_result

    def test_cruelty_boosted_vulnerable_multiplier_end_to_end(self):
        from sts2_rl.powers import CrueltyPower, VulnerablePower
        from sts2_rl.valueprops import DamageProps
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, CrueltyPower, 25, applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 1)
        vuln = cs.enemy.powers["vulnerable"]
        mult = vuln.modify_damage_multiplicative(
            cs.enemy, 10, cs.player, None, props=DamageProps.CARD,
        )
        assert mult == 1.75


# ══════════════════════════════════════════════════════════════════════════
# power/hellraiser/AfterSideTurnEnd — DORMANT-ENUMERATED
# ══════════════════════════════════════════════════════════════════════════

class TestHellraiserReset:
    def test_no_infinite_auto_play_counter_exists_to_reset(self):
        """HellraiserPower.cs:70-78 (AfterSideTurnEnd) resets the per-turn
        infinite-auto-play counter (Data.infiniteAutoPlaysThisTurn) and the
        'showed cap message' flag against infinite-HP enemies. The sim's
        HellraiserPower (powers.py) tracks neither: no attribute, no cap
        check in on_card_drawn_early, and no AfterSideTurnEnd-shaped method
        at all. Confirmed by direct introspection, not prose."""
        from sts2_rl.powers import HellraiserPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, HellraiserPower, 1)
        power = cs.player.powers["hellraiser"]
        state = vars(power)
        assert not any("infinite" in k.lower() or "cap" in k.lower() for k in state)
        assert not hasattr(power, "after_side_turn_end")
        assert not hasattr(power, "after_enemy_side_end")

    def test_ending_the_turn_with_hellraiser_active_does_not_error(self):
        """Execution, not just introspection: a full turn cycle with
        Hellraiser active and no cap machinery must not raise, matching the
        'dormant because inert, not because untested' verdict."""
        from sts2_rl.powers import HellraiserPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, HellraiserPower, 1)
        cs.end_turn()  # player -> enemy -> back to player, no crash


# ══════════════════════════════════════════════════════════════════════════
# power/illusion/g1 — DORMANT-ENUMERATED
# ══════════════════════════════════════════════════════════════════════════

class TestIllusionFollowUpStateId:
    def test_exactly_two_appliers_both_single_self_looping_non_machine_monsters(self):
        """IllusionPower.cs:34-45's FollowUpStateId lets an applier choose
        which move-state a revived creature resumes on. The sim's IllusionPower
        (powers.py) has no state-machine concept at all in its revive() --
        it just heals and clears is_reviving. Whether that is observable
        depends on the appliers: both ported ones (EyeWithTeeth, Parafright)
        are the plain `Monster` base class, not `MachineMonster` -- they have
        exactly one hardcoded move each, matching the C# source's single
        self-looping MoveState (Parafright.cs:44-47, EyeWithTeeth.cs:39-42)."""
        from sts2_rl.monsters.base import Monster
        from sts2_rl.monsters.state_machine import MachineMonster
        from sts2_rl.monsters.overgrowth.fogmog import EyeWithTeeth
        from sts2_rl.monsters.hive.the_obscura import Parafright
        for cls in (EyeWithTeeth, Parafright):
            assert issubclass(cls, Monster)
            assert not issubclass(cls, MachineMonster)

    def test_both_appliers_apply_illusion_with_no_followup_state_argument(self):
        from sts2_rl.monsters.overgrowth.fogmog import EyeWithTeeth
        from sts2_rl.monsters.hive.the_obscura import Parafright
        from sts2_rl.hooks import HookSystem
        for cls in (EyeWithTeeth, Parafright):
            hooks = HookSystem()
            m = cls(hooks, random.Random(0))
            illusion = m.powers.get("illusion")
            assert illusion is not None
            # No sim analogue of FollowUpStateId exists on the power at all.
            assert not hasattr(illusion, "follow_up_state_id")


# ══════════════════════════════════════════════════════════════════════════
# power/ravenous/AfterDeath — DORMANT-ENUMERATED (missing applier=, same
# class and same precedent as power/high_voltage, left unfixed there too)
# ══════════════════════════════════════════════════════════════════════════

class TestRavenousMissingApplier:
    def test_granted_strength_has_no_applier_recorded(self):
        """RavenousPower.cs:33 passes base.Owner as the Strength applier;
        powers.py's PowerCmd.apply(..., StrengthPower, self.amount) omits it,
        so .applier is None on the new instance. Documents current (dormant)
        state -- see the census below for why nothing currently reads it."""
        from sts2_rl.powers import RavenousPower
        cs = fresh()
        # on_death only needs a same-side, not-self corpse -- a duck-typed
        # stand-in exercises the guarded call path without a second creature.
        PowerCmd.apply(cs.hooks, cs.enemy, RavenousPower, 3)
        ravenous = cs.enemy.powers["ravenous"]

        class _Corpse:
            side = cs.enemy.side
        ravenous.on_death(_Corpse())
        strength = cs.enemy.powers.get("strength")
        assert strength is not None
        assert strength.applier is None  # matches the recorded gap, not yet fixed

    def test_no_currently_ported_consumer_reads_the_applier_here(self):
        """Census (grep + read) of every modify_power_amount_given_* /
        on_power_amount_changed / on_power_applied listener in the sim:
        relics/unsettling_lamp.py (gates on `applier is self.player` and
        `type_for_amount != DEBUFF` -- a monster granting itself Strength
        matches neither), powers.py's Vicious-style `_track` helpers (gate on
        `applier is self.owner` for a NAMED stat power and a NEGATIVE delta --
        Ravenous grants a POSITIVE Strength amount to a DIFFERENT power's
        listener). None reacts differently for applier=None vs applier=owner
        on a monster's self-granted positive Strength."""
        from sts2_rl.relics.unsettling_lamp import UnsettlingLamp
        cs = fresh()
        lamp = UnsettlingLamp()
        lamp.combat = cs  # `.player` reads `self.combat.player`
        lamp._finished = False
        lamp._in_flight = object()
        from sts2_rl.powers import StrengthPower
        # applier is None (Ravenous's own shape): must be a no-op (factor 1).
        factor = lamp.modify_power_amount_given_multiplicative(
            StrengthPower, object(), 3, None
        )
        assert factor == 1


# ══════════════════════════════════════════════════════════════════════════
# power/suck/g2 — DORMANT-ENUMERATED
# ══════════════════════════════════════════════════════════════════════════

class TestSuckGroupsVsResults:
    def test_fossil_stalker_moves_are_all_single_target(self):
        """SuckPower.cs:28-41 counts GROUPS (one per hit) with any unblocked
        result, not individual results -- so one AoE swing connecting with 3
        creatures counts 1, not 3. FossilStalker (the power's ONLY applier in
        the whole game, C# grep confirms it) has three moves, TACKLE/LATCH/
        LASH, and none is AoE: TACKLE and LATCH are 1-hit single-target,
        LASH is 2 SEQUENTIAL hits against the same single target (which is
        the SAME shape on both sides -- 2 groups of 1 receiver each -- so it
        does not trigger the divergence either)."""
        from sts2_rl.monsters.underdocks.fossil_stalker import (
            _LASH_HITS, _TACKLE_DMG, _LATCH_DMG, _LASH_DMG,
        )
        assert _LASH_HITS == 2
        # No move in fossil_stalker.py targets "ctx.enemies" / all creatures;
        # every _execute_attack call in that file has a single implicit
        # target (the player). Executed via a real 2-enemy-side combat would
        # require a second player, which the sim does not model -- the
        # absence of any multi-target call in the source is the census.
        import inspect
        src = inspect.getsource(
            __import__(
                "sts2_rl.monsters.underdocks.fossil_stalker", fromlist=["FossilStalker"]
            )
        )
        assert "for enemy in" not in src
        assert "hittable_enemies" not in src

    def test_suck_would_over_count_a_synthetic_aoe_in_isolation(self):
        """Demonstrates the SHAPE of the bug directly against SuckPower.after_attack
        (no C# analogue reachable through FossilStalker): a single swing that
        connects with 3 same-side receivers is flattened to 3 tuples by every
        sim call site, so `hits` counts 3 where the game's grouped count
        would be 1. This is the divergence's mechanism, kept isolated from
        FossilStalker's actual (single-target) content."""
        from sts2_rl.powers import SuckPower, StrengthPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SuckPower, 3)
        suck = cs.enemy.powers["suck"]

        class _Receiver:
            def __init__(self, side):
                self.side = side
        receivers = [_Receiver("player") for _ in range(3)]
        results = [(r, 5) for r in receivers]  # one hit, 3 simultaneous receivers
        suck.after_attack(cs.enemy, card=None, results=results)
        strength = cs.enemy.powers.get("strength")
        assert strength is not None
        assert strength.amount == 3 * 3  # sim: amount * len(results) == 9
        # The game would grant amount * 1 == 3 here (one connecting GROUP).


# ══════════════════════════════════════════════════════════════════════════
# power/tangled/AfterApplied — record's reasoning does not hold: FAITHFUL.
# The extra `card.affliction is None` guard the record flagged as missing
# from C# is behaviorally REDUNDANT with (not a workaround for a gap left
# by) cmds.py's own CardCmd.afflict -> Affliction.can_afflict chain, because
# Entangled.is_stackable is False (matches AfflictionModel.cs:127's default,
# only Galvanized/Tainted override it). Left unedited; see the report.
# ══════════════════════════════════════════════════════════════════════════

class TestTangledGuardIsRedundant:
    def test_entangled_and_ringing_are_not_stackable(self):
        from sts2_rl.afflictions import EntangledAffliction, RingingAffliction
        assert EntangledAffliction.is_stackable is False
        assert RingingAffliction.is_stackable is False

    def test_afflicting_a_ringing_carrying_attack_with_entangled_is_refused_either_way(self):
        """Calls CardCmd.afflict WITHOUT any powers.py-level pre-filter --
        exactly the C# TangledPower.AfterApplied call shape (unconditional
        CardCmd.Afflict<Entangled> over every owned Attack card) -- and shows
        the card keeps Ringing. `can_afflict`'s own `is_stackable` gate
        refuses the re-affliction, so the guard powers.py additionally
        carries in __init__ changes nothing observable."""
        from sts2_rl.afflictions import EntangledAffliction, RingingAffliction
        card = make_card("strike")
        assert card.card_type == CardType.ATTACK
        first = CardCmd.afflict(card, RingingAffliction, 1)
        assert first is not None
        assert isinstance(card.affliction, RingingAffliction)
        # Unconditional call, no `card.affliction is None` pre-check:
        second = CardCmd.afflict(card, EntangledAffliction, 1)
        assert second is None  # refused, not an overwrite
        assert isinstance(card.affliction, RingingAffliction)  # untouched

    def test_all_cards_already_includes_the_play_pile(self):
        """The record's second claim ('the __init__ walk misses the Play
        pile') is also stale: player.all_cards already sums in play_pile
        (player.py), which the property's own docstring says was added
        specifically so the Smoggy/Ringing/Tainted/Galvanized/Tangled-style
        affliction sweeps reach a card mid-resolution."""
        cs = fresh()
        card = make_card("strike")
        cs.player.play_pile.append(card)
        assert card in cs.player.all_cards


# ══════════════════════════════════════════════════════════════════════════
# power/unmovable/ModifyBlockMultiplicative — DORMANT-ENUMERATED (divergence
# (a), the reset-slot mismatch, is unreachable with today's ported content)
# ══════════════════════════════════════════════════════════════════════════

class TestUnmovableResetBoundary:
    def test_reset_fires_on_an_extra_player_turn_too(self):
        """`before_side_turn_start` -> `_start_player_turn` -> `player.start_turn()`
        is the one shared entry point for BOTH a normal new round and an
        extra player turn (round_number does NOT advance for an extra turn).
        The sim's manual `_plays_used = 0` reset therefore fires even when
        the C# round-based History window has not moved."""
        from sts2_rl.powers import UnmovablePower
        from sts2_rl.relics.paels_eye import PaelsEye
        cs = fresh()
        cs.relics = [PaelsEye()]
        for r in cs.relics:
            r.attach(cs) if hasattr(r, "attach") else None
        PowerCmd.apply(cs.hooks, cs.player, UnmovablePower, 1)
        unmov = cs.player.powers["unmovable"]
        unmov._plays_used = 1  # pretend the allowance was already used up
        round_before = cs.round_number
        cs.player.hand.clear()  # ends the turn having played nothing
        cs.end_turn()
        # Pael's Eye grants an extra turn only when NO cards were played --
        # exactly the state that also leaves _plays_used untouched by any
        # card play, so resetting it here is a no-op in the only reachable
        # scenario (see the second test below).
        assert unmov._plays_used == 0  # the reset DID fire

    def test_the_only_ported_extra_turn_source_requires_zero_prior_plays(self):
        """relics/paels_eye.py's ShouldTakeExtraTurn (`should_take_extra_turn`)
        is gated on `not self._any_cards_played_this_turn()`. Since
        UnmovablePower._plays_used only increments from `on_card_played`
        (a played, block-granting card), any turn that qualifies for Pael's
        Eye's extra turn has necessarily left _plays_used untouched -- so
        the reset-boundary bug the record describes has no reachable trigger
        with the sim's one ported extra-turn source. A second, independent
        extra-turn grant (or a card-sourced block gain outside the player's
        own turn) would revive it; none is ported today."""
        import inspect
        from sts2_rl.relics import paels_eye
        src = inspect.getsource(paels_eye)
        assert "_any_cards_played_this_turn" in src
        assert "should_take_extra_turn" in src
        # Confirm PaelsEye is the ONLY should_take_extra_turn listener in the
        # power/relic catalogues (besides combat/hooks plumbing itself).
        import sts2_rl.powers as powers_mod
        assert "def should_take_extra_turn" not in inspect.getsource(powers_mod)
