"""
Tests for the Ironclad power-backed cards (Aggression, Battle Trance, ...)
and their Power classes, plus the engine additions that support them
(Innate keyword, CardCmd.AutoPlay, current_side).

Run with:  python -m pytest test/test_ironclad_powers.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import (
    AggressionCard,
    AngerCard,
    BashCard,
    BattleTranceCard,
    BludgeonCard,
    ColossusCard,
    CorruptionCard,
    CrimsonMantleCard,
    CrueltyCard,
    DefendCard,
    ExpectAFightCard,
    FlameBarrierCard,
    HellraiserCard,
    InfernoCard,
    JuggernautCard,
    JugglingCard,
    MangleCard,
    OneTwoPunchCard,
    PyreCard,
    RageCard,
    SetupStrikeCard,
    StampedeCard,
    StoneArmorCard,
    StrikeCard,
    UnmovableCard,
    UnrelentingCard,
    ViciousCard,
)
from sts2_rl.cmds import BlockCmd, DrawCmd, EnergyCmd
from sts2_rl.powers import FeelNoPainPower, VulnerablePower
from sts2_rl.valueprops import DamageProps, ValueProp


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    """Fresh combat with a fixed RNG seed (9-card starter deck, enemy HP 55–57)."""
    return CombatState(rng=random.Random(seed))


def combat(deck, seed: int = 0) -> CombatState:
    """Combat whose starting deck is exactly `deck` (≤5 cards ⇒ all in hand)."""
    return CombatState(starting_deck=deck, rng=random.Random(seed))


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    """Give the player `card`, plenty of energy, and play it."""
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


# ══════════════════════════════════════════════════════════════════════════
# Engine additions
# ══════════════════════════════════════════════════════════════════════════

class TestInnateKeyword:
    def test_innate_card_starts_in_opening_hand(self):
        agg = AggressionCard()
        agg.upgrade()  # Aggression+ gains Innate
        assert agg.innate
        deck = [DefendCard() for _ in range(9)] + [agg]
        cs = combat(deck)
        assert agg in cs.player.hand

    def test_unupgraded_card_is_not_innate(self):
        assert not JugglingCard().innate
        jug = JugglingCard()
        jug.upgrade()
        assert jug.innate


class TestAutoPlay:
    def test_auto_play_costs_no_energy(self):
        cs = fresh()
        cs.player.energy = 0
        strike = StrikeCard()
        cs.player.hand.append(strike)
        before = cs.enemy.hp
        cs.auto_play_card(strike)
        assert cs.enemy.hp == before - 6
        assert strike in cs.player.discard_pile
        assert cs.player.energy == 0

    def test_auto_play_unplayable_card_moves_to_discard(self):
        cs = fresh()
        from sts2_rl.cards import WoundCard
        wound = WoundCard()
        cs.player.hand.append(wound)
        cs.auto_play_card(wound)
        assert wound in cs.player.discard_pile
        assert wound not in cs.player.hand


# ══════════════════════════════════════════════════════════════════════════
# Battle Trance / Expect A Fight (No Draw / No Energy Gain)
# ══════════════════════════════════════════════════════════════════════════

class TestBattleTrance:
    def test_draws_then_blocks_further_draws(self):
        cs = fresh()
        play(cs, BattleTranceCard())
        assert len(cs.player.hand) == 8  # 5 + 3 drawn
        DrawCmd.draw(cs.player, 1)
        assert len(cs.player.hand) == 8  # blocked by NoDraw

    def test_no_draw_expires_at_turn_end(self):
        cs = fresh()
        play(cs, BattleTranceCard())
        cs.end_turn()
        assert "no_draw" not in cs.player.powers
        assert len(cs.player.hand) == 5  # start-of-turn draw unaffected

    def test_upgrade_draws_four(self):
        cs = fresh()
        card = BattleTranceCard()
        card.upgrade()
        play(cs, card)
        assert len(cs.player.hand) == 9


class TestExpectAFight:
    def test_gains_energy_per_attack_in_hand(self):
        cs = combat([StrikeCard(), StrikeCard(), DefendCard()])
        play(cs, ExpectAFightCard(), energy=3)
        assert cs.player.energy == 3  # 3 - 2 cost + 2 attacks

    def test_blocks_further_energy_gain_until_turn_end(self):
        cs = combat([StrikeCard(), DefendCard()])
        play(cs, ExpectAFightCard(), energy=2)
        assert cs.player.energy == 1  # 2 - 2 + 1
        EnergyCmd.gain(cs.hooks, cs.player, 5)
        assert cs.player.energy == 1  # blocked
        cs.end_turn()
        assert "no_energy_gain" not in cs.player.powers
        assert cs.player.energy == 3  # turn-start energy unaffected


# ══════════════════════════════════════════════════════════════════════════
# Colossus / Flame Barrier / Rage (defensive skills)
# ══════════════════════════════════════════════════════════════════════════

class TestColossus:
    def test_halves_damage_from_vulnerable_dealers(self):
        cs = fresh()
        play(cs, ColossusCard())
        assert cs.player.block == 5
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        cs.player.block = 0
        hp0 = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=cs.enemy, props=DamageProps.MONSTER_MOVE)
        assert cs.player.hp == hp0 - 5

    def test_full_damage_from_non_vulnerable_dealers(self):
        cs = fresh()
        play(cs, ColossusCard())
        cs.player.block = 0
        hp0 = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=cs.enemy, props=DamageProps.MONSTER_MOVE)
        assert cs.player.hp == hp0 - 10

    def test_ticks_at_enemy_side_end(self):
        cs = fresh()
        play(cs, ColossusCard())
        cs.hooks.on_enemy_side_end()
        assert "colossus" not in cs.player.powers


class TestFlameBarrier:
    def test_reflects_damage_even_when_blocked(self):
        cs = fresh()
        play(cs, FlameBarrierCard())
        assert cs.player.block == 12
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy, props=DamageProps.MONSTER_MOVE)
        assert cs.enemy.hp == before - 4  # blocked hit still reflects

    def test_no_reflect_on_self_damage_or_dealerless_damage(self):
        cs = fresh()
        play(cs, FlameBarrierCard())
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 3, dealer=cs.player, props=DamageProps.NON_CARD_HP_LOSS)
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        assert cs.enemy.hp == before

    def test_no_reflect_on_unpowered_damage_with_dealer(self):
        # e.g. Thorns-style reflection at the player: has a dealer but is not
        # a powered attack, so Flame Barrier must not counter it.
        cs = fresh()
        play(cs, FlameBarrierCard())
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 3, dealer=cs.enemy, props=DamageProps.NON_CARD_UNPOWERED)
        assert cs.enemy.hp == before

    def test_removed_at_enemy_side_end(self):
        cs = fresh()
        play(cs, FlameBarrierCard())
        cs.hooks.on_enemy_side_end()
        assert "flame_barrier" not in cs.player.powers


class TestRage:
    def test_block_per_attack_played(self):
        cs = fresh()
        play(cs, RageCard())
        play(cs, StrikeCard())
        play(cs, StrikeCard())
        assert cs.player.block == 6
        play(cs, DefendCard())  # skill: +5 block only, no Rage trigger
        assert cs.player.block == 11

    def test_removed_at_turn_end(self):
        cs = fresh()
        play(cs, RageCard())
        # These powers are AfterSideTurnEnd in C# (power/_side_turn_slot),
        # so they moved off the sim's BeforeTurnEnd slot onto
        # after_player_turn_end. end_turn fires both in order.
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.after_player_turn_end(cs.player)
        assert "rage" not in cs.player.powers


# ══════════════════════════════════════════════════════════════════════════
# One-Two Punch / Unrelenting (play-count and cost powers)
# ══════════════════════════════════════════════════════════════════════════

class TestOneTwoPunch:
    def test_next_attack_played_twice(self):
        cs = fresh()
        play(cs, OneTwoPunchCard())
        before = cs.enemy.hp
        play(cs, StrikeCard())
        assert cs.enemy.hp == before - 12
        play(cs, StrikeCard())
        assert cs.enemy.hp == before - 18  # power consumed

    def test_upgrade_covers_two_attacks(self):
        cs = fresh()
        card = OneTwoPunchCard()
        card.upgrade()
        play(cs, card)
        before = cs.enemy.hp
        play(cs, StrikeCard())
        play(cs, StrikeCard())
        assert cs.enemy.hp == before - 24

    def test_expires_at_turn_end(self):
        cs = fresh()
        play(cs, OneTwoPunchCard())
        # These powers are AfterSideTurnEnd in C# (power/_side_turn_slot),
        # so they moved off the sim's BeforeTurnEnd slot onto
        # after_player_turn_end. end_turn fires both in order.
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.after_player_turn_end(cs.player)
        assert "one_two_punch" not in cs.player.powers


class TestUnrelenting:
    def test_damage_and_next_attack_free(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, UnrelentingCard())
        assert cs.enemy.hp == before - 14
        # Bludgeon (3E) is free now.
        play(cs, BludgeonCard(), energy=0)
        assert cs.enemy.hp == before - 14 - 32
        assert "free_attack" not in cs.player.powers
        # Next attack is no longer free.
        cs.player.hand.append(StrikeCard())
        cs.player.energy = 0
        assert not cs.play_card(len(cs.player.hand) - 1)

    def test_auto_played_attack_consumes_stack(self):
        cs = fresh()
        play(cs, UnrelentingCard())
        assert "free_attack" in cs.player.powers
        strike = StrikeCard()
        cs.player.hand.append(strike)
        cs.auto_play_card(strike)
        assert "free_attack" not in cs.player.powers


# ══════════════════════════════════════════════════════════════════════════
# Pyre / Corruption / Crimson Mantle / Inferno (persistent powers)
# ══════════════════════════════════════════════════════════════════════════

class TestPyre:
    def test_extra_energy_each_turn(self):
        cs = fresh()
        play(cs, PyreCard())
        cs.end_turn()
        assert cs.player.energy == 4


class TestCorruption:
    def test_skills_cost_zero_and_exhaust(self):
        cs = fresh()
        play(cs, CorruptionCard())
        defend = DefendCard()
        cs.player.hand.append(defend)
        cs.player.energy = 0
        assert cs.play_card(len(cs.player.hand) - 1)
        assert cs.player.block == 5
        assert defend in cs.player.exhaust_pile
        assert defend not in cs.player.discard_pile

    def test_attacks_unaffected(self):
        cs = fresh()
        play(cs, CorruptionCard())
        strike = StrikeCard()
        cs.player.hand.append(strike)
        cs.player.energy = 0
        assert not cs.play_card(len(cs.player.hand) - 1)  # still costs 1

    def test_corruption_exhaust_triggers_feel_no_pain(self):
        cs = fresh()
        play(cs, CorruptionCard())
        PowerCmd.apply(cs.hooks, cs.player, FeelNoPainPower, 3)
        play(cs, DefendCard())
        assert cs.player.block == 5 + 3


class TestCrimsonMantle:
    def test_turn_start_hp_loss_and_block(self):
        cs = fresh()
        play(cs, CrimsonMantleCard())
        hp0 = cs.player.hp
        cs.hooks.on_player_turn_started(cs.player)
        assert cs.player.hp == hp0 - 1  # 1 Crimson Mantle played
        assert cs.player.block == 8

    def test_second_mantle_stacks_block_and_self_damage(self):
        cs = fresh()
        play(cs, CrimsonMantleCard())
        play(cs, CrimsonMantleCard())
        power = cs.player.powers["crimson_mantle"]
        assert power.amount == 16
        assert power.self_damage == 2
        hp0 = cs.player.hp
        cs.hooks.on_player_turn_started(cs.player)
        assert cs.player.hp == hp0 - 2
        assert cs.player.block == 16


class TestInferno:
    def test_hp_loss_on_own_turn_burns_all_enemies(self):
        cs = fresh()
        play(cs, InfernoCard())
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        assert cs.enemy.hp == before - 6

    def test_no_burst_during_enemy_turn(self):
        cs = fresh()
        play(cs, InfernoCard())
        before = cs.enemy.hp
        cs.current_side = "enemy"
        try:
            DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        finally:
            cs.current_side = "player"
        assert cs.enemy.hp == before

    def test_turn_start_self_damage_triggers_burst(self):
        cs = fresh()
        play(cs, InfernoCard())
        hp0 = cs.player.hp
        before = cs.enemy.hp
        cs.hooks.on_player_turn_started(cs.player)
        assert cs.player.hp == hp0 - 1
        assert cs.enemy.hp == before - 6

    def test_a_turn_start_burst_kill_ends_the_combat(self):
        # CombatManager.cs:573 -- the game runs CheckWinCondition() right after
        # the player's turn setup / auto-pre-play phase, so a kill landed by a
        # turn-start effect (Inferno's burst here) ends the fight immediately
        # instead of leaving the player in a turn with no living enemies.
        cs = fresh()
        play(cs, InfernoCard())
        cs.enemy.hp = 4  # burst is 6: the turn-start tick is lethal
        cs.end_turn()
        assert cs.enemy.is_dead
        assert cs.is_over
        assert cs.result is not None and cs.result.player_won


# ══════════════════════════════════════════════════════════════════════════
# Juggernaut / Juggling / Vicious (trigger powers)
# ══════════════════════════════════════════════════════════════════════════

class TestJuggernaut:
    def test_block_gain_hits_random_enemy(self):
        cs = fresh()
        play(cs, JuggernautCard())
        before = cs.enemy.hp
        play(cs, DefendCard())
        assert cs.enemy.hp == before - 6

    def test_unpowered_block_also_triggers(self):
        cs = fresh()
        play(cs, JuggernautCard())
        before = cs.enemy.hp
        BlockCmd.apply(cs.hooks, cs.player, 4, props=ValueProp.UNPOWERED)
        assert cs.enemy.hp == before - 6


class TestJuggling:
    def test_third_attack_is_copied_to_hand(self):
        cs = combat([DefendCard() for _ in range(5)])
        play(cs, JugglingCard())
        play(cs, StrikeCard())
        play(cs, StrikeCard())
        assert not any(isinstance(c, StrikeCard) for c in cs.player.hand)
        play(cs, StrikeCard())
        clones = [c for c in cs.player.hand if isinstance(c, StrikeCard)]
        assert len(clones) == 1
        # A 4th attack does not trigger again.
        play(cs, StrikeCard())
        assert len([c for c in cs.player.hand if isinstance(c, StrikeCard)]) == 1

    def test_clone_keeps_upgrade_level(self):
        cs = combat([DefendCard() for _ in range(5)])
        play(cs, JugglingCard())
        for _ in range(2):
            play(cs, StrikeCard())
        third = StrikeCard()
        third.upgrade()
        play(cs, third)
        clone = [c for c in cs.player.hand if isinstance(c, StrikeCard)][0]
        assert clone.upgrade_level == 1

    def test_attacks_played_before_juggling_count(self):
        # The counter is seeded from the combat's attack-play history, so
        # attacks played earlier in the same turn count toward the 3.
        cs = combat([DefendCard() for _ in range(5)])
        play(cs, StrikeCard())
        play(cs, StrikeCard())
        play(cs, JugglingCard())
        play(cs, StrikeCard())  # 3rd attack this turn
        assert len([c for c in cs.player.hand if isinstance(c, StrikeCard)]) == 1

    def test_seed_resets_next_turn(self):
        # 10 defends: turn 2 draws from the untouched draw pile, so the
        # strikes played on turn 1 stay in the discard pile.
        cs = combat([DefendCard() for _ in range(10)])
        play(cs, StrikeCard())
        play(cs, StrikeCard())
        cs.end_turn()
        play(cs, JugglingCard())
        play(cs, StrikeCard())  # only the 1st attack this turn — no clone
        assert len([c for c in cs.player.hand if isinstance(c, StrikeCard)]) == 0


class TestVicious:
    def test_applying_vulnerable_draws(self):
        cs = fresh()
        play(cs, ViciousCard())
        hand_before = len(cs.player.hand)
        play(cs, BashCard())
        # Bash was appended and played (net 0), Vicious drew 1.
        assert len(cs.player.hand) == hand_before + 1

    def test_stacking_vulnerable_draws_again(self):
        cs = fresh()
        play(cs, ViciousCard())
        play(cs, BashCard())
        hand_before = len(cs.player.hand)
        play(cs, BashCard())  # stacks Vulnerable on the same enemy
        assert len(cs.player.hand) == hand_before + 1

    def test_enemy_applying_vulnerable_to_player_does_not_draw(self):
        cs = fresh()
        play(cs, ViciousCard())
        hand_before = len(cs.player.hand)
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 2, applier=cs.enemy)
        assert len(cs.player.hand) == hand_before

    def test_applierless_vulnerable_does_not_draw(self):
        cs = fresh()
        play(cs, ViciousCard())
        hand_before = len(cs.player.hand)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)  # no applier
        assert len(cs.player.hand) == hand_before


# ══════════════════════════════════════════════════════════════════════════
# Mangle / Setup Strike (temporary Strength)
# ══════════════════════════════════════════════════════════════════════════

class TestMangle:
    def test_damage_and_temporary_strength_loss(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, MangleCard())
        assert cs.enemy.hp == before - 15
        assert cs.enemy.strength == -10
        assert "mangle" in cs.enemy.powers
        cs.hooks.on_enemy_side_end()  # end of the enemy's side turn
        assert cs.enemy.strength == 0
        assert "mangle" not in cs.enemy.powers

    def test_upgrade_values(self):
        cs = fresh()
        card = MangleCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 20
        assert cs.enemy.strength == -15


class TestSetupStrike:
    def test_damage_and_temporary_strength(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, SetupStrikeCard())
        assert cs.enemy.hp == before - 7
        assert cs.player.strength == 2
        play(cs, StrikeCard())
        assert cs.enemy.hp == before - 7 - 8  # 6 + 2 Strength
        # TemporaryStrengthPower.cs:173-181 is AfterSideTurnEnd, so the revert
        # rides Hook.AfterTurnEnd, not BeforeTurnEnd.
        cs.hooks.on_player_turn_end(cs.player)
        assert cs.player.strength == 2
        cs.hooks.after_player_turn_end(cs.player)
        assert cs.player.strength == 0
        assert "setup_strike" not in cs.player.powers

    def test_temporary_strength_survives_the_turn_end_cards_and_the_flush(self):
        """AfterSideTurnEnd for the player side is CombatManager.cs:1307 —
        after DoTurnEnd's card effects AND after FlushPlayerHand — so nothing
        in either step sees the Strength already gone, and the revert cannot
        race a BeforeTurnEnd listener on registration order."""
        cs = fresh()
        play(cs, SetupStrikeCard())
        assert cs.player.strength == 2
        seen = []

        class _Probe:
            def on_player_turn_end(self, player):
                seen.append(("before_turn_end", cs.player.strength))

            def after_player_turn_end(self, player):
                seen.append(("after_turn_end", cs.player.strength))

        # Registered LAST, so under the old single-pass model the revert (which
        # registered first, with the card) had already run by the time the
        # probe's BeforeTurnEnd leg ran. Its AfterTurnEnd leg is genuinely
        # order-dependent in C# too — both are AfterSideTurnEnd — so only the
        # BeforeTurnEnd reading is asserted.
        cs.hooks.register(_Probe())
        cs.end_turn()
        assert seen[0] == ("before_turn_end", 2)
        assert cs.player.strength == 0

    def test_has_strike_tag(self):
        assert "strike" in SetupStrikeCard.tags


# ══════════════════════════════════════════════════════════════════════════
# Stone Armor / Unmovable (block powers)
# ══════════════════════════════════════════════════════════════════════════

class TestStoneArmor:
    def test_block_at_turn_end(self):
        cs = fresh()
        play(cs, StoneArmorCard())
        cs.hooks.on_player_turn_end(cs.player)
        assert cs.player.block == 4

    def test_decays_at_turn_start(self):
        cs = fresh()
        play(cs, StoneArmorCard())
        cs.end_turn()
        assert cs.player.powers["plating"].amount == 3


class TestUnmovable:
    def test_first_block_card_each_turn_doubled(self):
        cs = fresh()
        play(cs, UnmovableCard())
        play(cs, DefendCard())
        assert cs.player.block == 10
        play(cs, DefendCard())
        assert cs.player.block == 15  # second card not doubled

    def test_resets_each_turn(self):
        cs = fresh()
        play(cs, UnmovableCard())
        play(cs, DefendCard())
        assert cs.player.block == 10
        cs.hooks.before_side_turn_start(cs.player)
        play(cs, DefendCard())
        assert cs.player.block == 20


# ══════════════════════════════════════════════════════════════════════════
# Cruelty (Vulnerable multiplier)
# ══════════════════════════════════════════════════════════════════════════

class TestCruelty:
    def test_vulnerable_multiplier_raised_to_1_75(self):
        cs = fresh()
        play(cs, CrueltyCard())
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 3, applier=cs.player)
        before = cs.enemy.hp
        play(cs, StrikeCard())
        assert cs.enemy.hp == before - 10  # int(6 * 1.75)

    def test_upgraded_multiplier_2x(self):
        cs = fresh()
        card = CrueltyCard()
        card.upgrade()
        play(cs, card)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 3, applier=cs.player)
        before = cs.enemy.hp
        play(cs, StrikeCard())
        assert cs.enemy.hp == before - 12  # int(6 * 2.0)

    def test_no_effect_without_vulnerable(self):
        cs = fresh()
        play(cs, CrueltyCard())
        before = cs.enemy.hp
        play(cs, StrikeCard())
        assert cs.enemy.hp == before - 6


# ══════════════════════════════════════════════════════════════════════════
# Hellraiser / Stampede / Aggression (auto-play powers)
# ══════════════════════════════════════════════════════════════════════════

class TestHellraiser:
    def test_drawn_strike_is_auto_played(self):
        cs = fresh()
        play(cs, HellraiserCard())
        strike = StrikeCard()
        cs.player.draw_pile.append(strike)  # top of the draw pile
        before = cs.enemy.hp
        DrawCmd.draw(cs.player, 1)
        assert cs.enemy.hp == before - 6
        assert strike in cs.player.discard_pile
        assert strike not in cs.player.hand

    def test_non_strike_draws_normally(self):
        cs = fresh()
        play(cs, HellraiserCard())
        defend = DefendCard()
        cs.player.draw_pile.append(defend)
        DrawCmd.draw(cs.player, 1)
        assert defend in cs.player.hand


class TestStampede:
    def test_random_attack_auto_played_at_turn_end(self):
        cs = fresh()
        play(cs, StampedeCard())
        strike = StrikeCard()
        cs.player.hand = [strike]
        before = cs.enemy.hp
        cs.end_turn()
        assert cs.enemy.hp == before - 6  # played before the enemy acts

    def test_attack_auto_play_costs_nothing_and_discards(self):
        cs = fresh()
        play(cs, StampedeCard())
        strike = StrikeCard()
        cs.player.hand = [strike]
        cs.player.energy = 0
        before = cs.enemy.hp
        # StampedePower.cs is AfterAutoPostPlayPhaseEntered, not BeforeTurnEnd
        # (turn_structure/G8) -- the auto-plays drain in their own phase.
        cs.hooks.after_auto_post_play_phase_entered(cs.player)
        assert cs.enemy.hp == before - 6
        assert strike in cs.player.discard_pile
        assert cs.player.energy == 0


class TestAggression:
    def test_returns_and_upgrades_attack_from_discard(self):
        cs = combat([DefendCard() for _ in range(5)])
        play(cs, AggressionCard())
        anger = AngerCard()
        cs.player.discard_pile.append(anger)
        cs.end_turn()
        assert anger in cs.player.hand
        assert anger.upgrade_level == 1

    def test_no_attacks_in_discard_is_a_no_op(self):
        cs = combat([DefendCard() for _ in range(5)])
        play(cs, AggressionCard())
        cs.end_turn()
        assert len(cs.player.hand) == 5
