"""
Tests for the 11 overgrowth enemy powers, card afflictions, and status card creation.

Run with:  python -m pytest test/test_overgrowth_powers.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, PowerCmd, DamageCmd, BlockCmd, ALL_POWERS
from sts2_rl.cards import (
    CardType,
    SlimedCard,
    DazedCard,
    InfectionCard,
    WoundCard,
)
from sts2_rl.monsters import Encounter, MoveType
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS, LeafSlimeM, TwigSlimeM
from sts2_rl.monsters.overgrowth.fogmog import EyeWithTeeth
from sts2_rl.monsters.overgrowth.phrog_parasite import PhrogParasite, Wriggler
from sts2_rl.monsters.overgrowth.vantom import Vantom
from sts2_rl.monsters.overgrowth.vine_shambler import VineShambler
from sts2_rl.powers import (
    ArtifactPower,
    PowerType,
    SlowPower,
    TerritorialPower,
    PlowPower,
    RingingPower,
    ShrinkPower,
    InfestedPower,
    ConstrictPower,
    TangledPower,
    SlipperyPower,
    MinionPower,
    IllusionPower,
)


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


def fresh_with(monster_cls, seed: int = 0) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc)


def _status_cards_in_discard(cs: CombatState) -> list:
    return [c for c in cs.player.discard_pile if c.card_type == CardType.STATUS]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Stub power registry and basic properties
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

_STUB_POWERS = [
    SlowPower,
    TerritorialPower,
    PlowPower,
    RingingPower,
    ShrinkPower,
    InfestedPower,
    ConstrictPower,
    TangledPower,
    SlipperyPower,
    MinionPower,
    IllusionPower,
]

_DEBUFF_POWERS = [SlowPower, PlowPower, RingingPower, ShrinkPower, ConstrictPower, TangledPower]
_BUFF_POWERS = [TerritorialPower, InfestedPower, SlipperyPower, MinionPower, IllusionPower]


class TestStubPowerRegistry:
    @pytest.mark.parametrize("cls", _STUB_POWERS)
    def test_in_ALL_POWERS(self, cls):
        assert cls.id in ALL_POWERS
        assert ALL_POWERS[cls.id] is cls

    @pytest.mark.parametrize("cls", _DEBUFF_POWERS)
    def test_debuffs_have_debuff_type(self, cls):
        assert cls.power_type == PowerType.DEBUFF

    @pytest.mark.parametrize("cls", _BUFF_POWERS)
    def test_buffs_have_buff_type(self, cls):
        assert cls.power_type == PowerType.BUFF


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Apply and stacking
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestStubPowerApplyAndStack:
    @pytest.mark.parametrize("cls", _STUB_POWERS)
    def test_apply_registers_on_creature(self, cls):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, cls, 3)
        assert cls.id in cs.enemy.powers
        assert cs.enemy.powers[cls.id].amount == 3

    @pytest.mark.parametrize("cls", _STUB_POWERS)
    def test_stacks_additively(self, cls):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, cls, 2)
        PowerCmd.apply(cs.hooks, cs.enemy, cls, 5)
        assert cs.enemy.powers[cls.id].amount == 7

    @pytest.mark.parametrize("cls", _STUB_POWERS)
    def test_can_be_applied_to_player(self, cls):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, cls, 1)
        assert cls.id in cs.player.powers

    @pytest.mark.parametrize("cls", _STUB_POWERS)
    def test_owner_and_amount_set_correctly(self, cls):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, cls, 4)
        p = cs.enemy.powers[cls.id]
        assert p.owner is cs.enemy
        assert p.amount == 4


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Artifact interaction (debuffs blocked; buffs pass through)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestStubPowerArtifactInteraction:
    @pytest.mark.parametrize("cls", _DEBUFF_POWERS)
    def test_debuff_blocked_by_artifact(self, cls):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, cls, 3)
        assert cls.id not in cs.enemy.powers  # blocked
        assert "artifact" not in cs.enemy.powers  # artifact consumed

    @pytest.mark.parametrize("cls", _BUFF_POWERS)
    def test_buff_not_blocked_by_artifact(self, cls):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, cls, 3)
        assert cls.id in cs.enemy.powers  # buff lands
        assert cs.enemy.powers["artifact"].amount == 1  # artifact intact


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Power behaviors (mirroring the STS2 source implementations)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestConstrictBehavior:
    def test_constrict_damages_player_at_end_of_their_turn(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ConstrictPower, 3)
        before = cs.player.hp
        # These powers are AfterSideTurnEnd in C# (power/_side_turn_slot),
        # so they moved off the sim's BeforeTurnEnd slot onto
        # after_player_turn_end. end_turn fires both in order.
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.after_player_turn_end(cs.player)
        assert cs.player.hp == before - 3

    def test_constrict_does_not_affect_direct_incoming_damage(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ConstrictPower, 3)
        before = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=cs.enemy)
        assert cs.player.hp == before - 10

    def test_constrict_removed_when_applier_dies(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ConstrictPower, 3, applier=cs.enemy)
        DamageCmd.deal(cs.hooks, cs.enemy, 999, dealer=cs.player)
        assert "constrict" not in cs.player.powers


class TestTangledBehavior:
    def test_tangled_raises_attack_card_cost(self):
        from sts2_rl.cards import StrikeCard
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        card = next(c for c in cs.player.all_cards if isinstance(c, StrikeCard))
        assert cs.hooks.modify_card_energy_cost(card, card.energy_cost) == card.energy_cost + 1

    def test_tangled_does_not_affect_skill_cost(self):
        from sts2_rl.cards import DefendCard
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        card = next(c for c in cs.player.all_cards if isinstance(c, DefendCard))
        assert cs.hooks.modify_card_energy_cost(card, card.energy_cost) == card.energy_cost

    def test_tangled_afflicts_only_attack_cards(self):
        from sts2_rl.afflictions import EntangledAffliction
        from sts2_rl.cards import CardType
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        for card in cs.player.all_cards:
            if card.card_type == CardType.ATTACK:
                assert isinstance(card.affliction, EntangledAffliction)
            else:
                assert card.affliction is None

    def test_tangled_removed_at_end_of_player_turn(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        # These powers are AfterSideTurnEnd in C# (power/_side_turn_slot),
        # so they moved off the sim's BeforeTurnEnd slot onto
        # after_player_turn_end. end_turn fires both in order.
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.after_player_turn_end(cs.player)
        assert "tangled" not in cs.player.powers
        assert all(c.affliction is None for c in cs.player.all_cards)


class TestSlowBehavior:
    def test_slow_owner_takes_more_damage_per_card_played(self):
        from sts2_rl.cards import StrikeCard
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SlowPower, 1)
        card = StrikeCard()
        for _ in range(3):
            cs.hooks.on_card_played(card)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player, card=card)
        assert cs.enemy.hp == before - 13  # 10 Ã— 1.3

    def test_slow_counter_resets_at_the_enemy_side_start(self):
        # SlowPower.cs:52 is AfterSideTurnStart (CombatManager.cs:522), one
        # dispatch for the whole side; the sim reset it on a per-enemy slot.
        from sts2_rl.cards import StrikeCard
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SlowPower, 1)
        card = StrikeCard()
        cs.hooks.on_card_played(card)
        cs.hooks.after_enemy_side_start()
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player, card=card)
        assert cs.enemy.hp == before - 10


class TestSlipperyBehavior:
    def test_slippery_caps_hit_to_one_hp_and_consumes_stack(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SlipperyPower, 2)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player)
        assert cs.enemy.hp == before - 1
        assert cs.enemy.powers["slippery"].amount == 1

    def test_slippery_expires_after_all_stacks_consumed(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SlipperyPower, 1)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player)
        assert "slippery" not in cs.enemy.powers
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player)
        assert cs.enemy.hp == before - 11

    def test_fully_blocked_hit_does_not_consume_slippery(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SlipperyPower, 1)
        cs.enemy.block = 20
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player)
        assert cs.enemy.powers["slippery"].amount == 1


class TestPlowBehavior:
    def test_plow_breaks_at_threshold_and_strips_strength(self):
        from sts2_rl.powers import StrengthPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, 5)
        PowerCmd.apply(cs.hooks, cs.enemy, PlowPower, cs.enemy.hp)  # any damage breaks it
        DamageCmd.deal(cs.hooks, cs.enemy, 3, dealer=cs.player)
        assert "plow" not in cs.enemy.powers
        assert "strength" not in cs.enemy.powers

    def test_plow_holds_while_hp_above_threshold(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, PlowPower, 1)
        DamageCmd.deal(cs.hooks, cs.enemy, 3, dealer=cs.player)
        assert "plow" in cs.enemy.powers


class TestRingingBehavior:
    def test_ringing_allows_only_first_card_play(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        playable_card = next(i for i, c in enumerate(cs.player.hand) if c.is_playable)
        assert cs.play_card(playable_card)
        assert all(not cs.play_card(i) for i in range(len(cs.player.hand)))

    def test_ringing_afflicts_every_unafflicted_card(self):
        from sts2_rl.afflictions import RingingAffliction
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        assert all(isinstance(c.affliction, RingingAffliction) for c in cs.player.all_cards)

    def test_ringing_removed_at_end_of_player_turn(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        # These powers are AfterSideTurnEnd in C# (power/_side_turn_slot),
        # so they moved off the sim's BeforeTurnEnd slot onto
        # after_player_turn_end. end_turn fires both in order.
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.after_player_turn_end(cs.player)
        assert "ringing" not in cs.player.powers
        assert all(c.affliction is None for c in cs.player.all_cards)

    def test_card_entering_combat_gets_ringing(self):
        from sts2_rl.afflictions import RingingAffliction
        from sts2_rl.cmds import CardPileCmd
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        card = SlimedCard()
        CardPileCmd.add_to_discard(cs.hooks, cs.player, card)
        assert isinstance(card.affliction, RingingAffliction)


class TestAfflictionExclusivity:
    def test_card_holds_at_most_one_affliction(self):
        from sts2_rl.afflictions import EntangledAffliction, RingingAffliction
        from sts2_rl.cards import CardType
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        # Ringing got there first: Attack cards keep Ringing, never Entangled.
        attacks = [c for c in cs.player.all_cards if c.card_type == CardType.ATTACK]
        assert all(isinstance(c.affliction, RingingAffliction) for c in attacks)
        assert not any(isinstance(c.affliction, EntangledAffliction) for c in cs.player.all_cards)

    def test_ringing_afflicted_attacks_escape_tangled_cost_increase(self):
        from sts2_rl.cards import StrikeCard
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        card = next(c for c in cs.player.all_cards if isinstance(c, StrikeCard))
        assert cs.hooks.modify_card_energy_cost(card, card.energy_cost) == card.energy_cost

    def test_same_stackable_affliction_reapplied_stacks_amount(self):
        """Only an `IsStackable` affliction restacks (AfflictionModel.
        CanAfflict, AfflictionModel.cs:190-205) -- Galvanized.cs:7 overrides
        it true. Was RingingAffliction, which does NOT override IsStackable
        (default False) and so is actually REFUSED on a second application,
        not stacked; fixed alongside creature_card_cmds/N2's CanAfflict
        guard (test_hook_order.py::TestCreatureCardCmdsOrder::
        test_can_afflict_refuses_a_non_stackable_reafflict pins the
        corrected Ringing behavior this test used to assert wrongly)."""
        from sts2_rl.afflictions import GalvanizedAffliction
        from sts2_rl.cmds import CardCmd
        card = SlimedCard()
        CardCmd.afflict(card, GalvanizedAffliction, 1)
        CardCmd.afflict(card, GalvanizedAffliction, 2)
        assert isinstance(card.affliction, GalvanizedAffliction)
        assert card.affliction.amount == 3

    def test_attack_card_entering_combat_while_tangled_gets_entangled(self):
        from sts2_rl.afflictions import EntangledAffliction
        from sts2_rl.cards import StrikeCard
        from sts2_rl.cmds import CardPileCmd
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        card = StrikeCard()
        CardPileCmd.add_to_discard(cs.hooks, cs.player, card)
        assert isinstance(card.affliction, EntangledAffliction)

    def test_status_card_entering_combat_while_tangled_is_untouched(self):
        from sts2_rl.cmds import CardPileCmd
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1)
        card = SlimedCard()
        CardPileCmd.add_to_discard(cs.hooks, cs.player, card)
        assert card.affliction is None


class TestShrinkBehavior:
    def test_shrink_reduces_powered_damage_by_30_percent(self):
        from sts2_rl.cards import StrikeCard
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ShrinkPower, -1)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player, card=StrikeCard())
        assert cs.enemy.hp == before - 7

    def test_negative_shrink_is_permanent_until_applier_dies(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ShrinkPower, -1, applier=cs.enemy)
        cs.hooks.on_player_turn_end(cs.player)
        assert "shrink" in cs.player.powers
        DamageCmd.deal(cs.hooks, cs.enemy, 999, dealer=cs.player)
        assert "shrink" not in cs.player.powers


class TestTerritorialBehavior:
    def test_territorial_grants_strength_at_enemy_side_end(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, TerritorialPower, 1)
        cs.hooks.on_enemy_side_end()
        assert cs.enemy.strength == 1
        cs.hooks.on_enemy_side_end()
        assert cs.enemy.strength == 2


class TestInfestedBehavior:
    def test_phrog_death_spawns_four_stunned_wrigglers(self):
        cs = fresh_with(PhrogParasite)
        DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
        wrigglers = [e for e in cs.enemies if isinstance(e, Wriggler)]
        assert len(wrigglers) == 4
        assert all(w.stunned for w in wrigglers)
        assert not cs.is_over

    def test_wriggler_slots_alternate_starting_moves(self):
        cs = fresh_with(PhrogParasite)
        DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
        wrigglers = [e for e in cs.enemies if isinstance(e, Wriggler)]
        assert [w._move_key for w in wrigglers] == [
            "NASTY_BITE", "WRIGGLE", "NASTY_BITE", "WRIGGLE"
        ]


class TestIllusionBehavior:
    def test_eye_survives_lethal_damage_and_revives(self):
        cs = fresh_with(EyeWithTeeth)
        eye = cs.enemies[0]
        DamageCmd.deal(cs.hooks, eye, 999, dealer=cs.player)
        # CreatureCmd.cs:565 leaves a prevented death AT 0 HP and retained in
        # combat -- it is genuinely dead until its REVIVE move heals it. This
        # asserted `not is_dead` and `hp == 1` while the sim floored a
        # prevented death at 1 HP (power/_death_prevention_branch).
        assert eye.is_dead
        assert eye.hp == 0
        assert eye.retained_after_death
        # Unhittable while reviving.
        DamageCmd.deal(cs.hooks, eye, 999, dealer=cs.player)
        assert eye.hp == 0
        # Its next turn is spent reviving to full instead of Distracting.
        before = len(cs.player.discard_pile)
        eye.take_turn(cs._ctx())
        assert eye.hp == eye.max_hp
        assert len(cs.player.discard_pile) == before

    def test_illusion_auto_applies_minion(self):
        cs = fresh_with(EyeWithTeeth)
        assert "minion" in cs.enemies[0].powers


class TestMinionBehavior:
    def test_combat_won_when_primaries_dead_even_if_minions_alive(self):
        from sts2_rl.monsters.overgrowth.fogmog import Fogmog
        enc = Encounter("test", [Fogmog, EyeWithTeeth])
        cs = CombatState(rng=random.Random(0), encounter=enc)
        DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
        assert cs._all_enemies_dead()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Status card classes
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestStatusCardClasses:
    def test_slimed_is_status_type(self):
        assert SlimedCard.card_type == CardType.STATUS

    def test_slimed_is_playable_for_1_and_exhausts(self):
        # Slimed.cs: Cost 1 | Exhaust keyword (playable, unlike most statuses).
        assert SlimedCard.is_playable
        assert SlimedCard.exhausts
        assert SlimedCard().energy_cost == 1

    def test_slimed_play_draws_one_and_exhausts(self):
        from sts2_rl.cmds import CardPileCmd
        cs = fresh()
        card = SlimedCard()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, card)
        hand_before = len(cs.player.hand)
        energy_before = cs.player.energy
        assert cs.play_card(cs.player.hand.index(card))
        assert card in cs.player.exhaust_pile
        assert cs.player.energy == energy_before - 1
        assert len(cs.player.hand) == hand_before  # played one, drew one

    def test_dazed_is_status_type(self):
        assert DazedCard.card_type == CardType.STATUS

    def test_dazed_is_not_playable(self):
        assert not DazedCard.is_playable

    def test_dazed_is_ethereal(self):
        # Dazed.cs keywords: Ethereal, Unplayable.
        assert DazedCard.is_ethereal

    def test_dazed_exhausts_at_turn_end(self):
        from sts2_rl.cmds import CardPileCmd
        cs = fresh()
        card = DazedCard()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, card)
        cs.end_turn()
        assert card in cs.player.exhaust_pile

    def test_infection_is_status_type(self):
        assert InfectionCard.card_type == CardType.STATUS

    def test_infection_is_not_playable(self):
        assert not InfectionCard.is_playable

    def test_infection_is_unpowered(self):
        assert InfectionCard.is_unpowered

    def test_infection_deals_3_at_turn_end_in_hand(self):
        # Infection.cs: OnTurnEndInHand damages the owner for 3 (Unpowered|Move),
        # then the card is discarded like any other non-ethereal status.
        from sts2_rl.cmds import CardPileCmd
        cs = fresh()
        card = InfectionCard()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, card)
        before = cs.player.hp
        cs._process_turn_end_cards()
        assert cs.player.hp == before - 3
        assert card in cs.player.discard_pile

    def test_infection_damage_is_blockable(self):
        from sts2_rl.cmds import CardPileCmd
        cs = fresh()
        card = InfectionCard()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, card)
        cs.player.block = 3
        before = cs.player.hp
        cs._process_turn_end_cards()
        assert cs.player.hp == before

    def test_all_three_have_distinct_ids(self):
        assert len({SlimedCard.id, DazedCard.id, InfectionCard.id}) == 3

    def test_all_three_registered_in_make_card(self):
        from sts2_rl.cards import make_card
        for card_id in ("slimed", "dazed", "infection"):
            card = make_card(card_id)
            assert card.id == card_id


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Status card creation â€” monsters add cards to player discard
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestLeafSlimeSGoop:
    def test_goop_adds_one_slimed_to_discard(self):
        cs = fresh_with(LeafSlimeS)
        slime = cs.enemies[0]
        slime._move_key = "GOOP"
        ctx = cs._ctx()
        slime.take_turn(ctx)
        assert len(_status_cards_in_discard(cs)) == 1
        assert isinstance(cs.player.discard_pile[0], SlimedCard)

    def test_goop_adds_exactly_one_card(self):
        cs = fresh_with(LeafSlimeS)
        slime = cs.enemies[0]
        slime._move_key = "GOOP"
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        slime.take_turn(ctx)
        assert len(cs.player.discard_pile) == before + 1

    def test_goop_then_advances_to_tackle(self):
        cs = fresh_with(LeafSlimeS)
        slime = cs.enemies[0]
        slime._move_key = "GOOP"
        ctx = cs._ctx()
        slime.take_turn(ctx)
        # The intent roll is NOT part of taking the turn: CombatManager.cs:
        # 478-484 rolls every enemy's next move in one pass at the top of the
        # player's turn (CombatState._roll_enemy_intents), so a test driving
        # the monster by hand makes that pass itself (turn_structure gap G9).
        slime.telegraph_next_move()
        assert slime._move_key == "TACKLE"

    def test_tackle_does_not_add_cards(self):
        cs = fresh_with(LeafSlimeS)
        slime = cs.enemies[0]
        slime._move_key = "TACKLE"
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        slime.take_turn(ctx)
        assert len(cs.player.discard_pile) == before


class TestLeafSlimeMStickyShot:
    def test_sticky_shot_adds_two_slimed_to_discard(self):
        cs = fresh_with(LeafSlimeM)
        slime = cs.enemies[0]
        assert slime._move_key == "STICKY_SHOT"
        ctx = cs._ctx()
        slime.take_turn(ctx)
        slimed = [c for c in cs.player.discard_pile if isinstance(c, SlimedCard)]
        assert len(slimed) == 2

    def test_sticky_shot_advances_to_clump_shot(self):
        cs = fresh_with(LeafSlimeM)
        slime = cs.enemies[0]
        ctx = cs._ctx()
        slime.take_turn(ctx)
        assert slime._move_key == "CLUMP_SHOT"

    def test_clump_shot_does_not_add_cards(self):
        cs = fresh_with(LeafSlimeM)
        slime = cs.enemies[0]
        slime._move_key = "CLUMP_SHOT"
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        slime.take_turn(ctx)
        assert len(cs.player.discard_pile) == before

    def test_two_sticky_shots_add_four_slimed(self):
        cs = fresh_with(LeafSlimeM)
        slime = cs.enemies[0]
        ctx = cs._ctx()
        slime.take_turn(ctx)  # STICKY_SHOT â†’ 2 Slimed
        slime._move_key = "STICKY_SHOT"
        slime.take_turn(ctx)  # STICKY_SHOT again â†’ 2 more
        assert len([c for c in cs.player.discard_pile if isinstance(c, SlimedCard)]) == 4


class TestTwigSlimeMStickyShot:
    def test_sticky_shot_adds_one_slimed_to_discard(self):
        cs = fresh_with(TwigSlimeM)
        slime = cs.enemies[0]
        assert slime._move_key == "STICKY_SHOT"
        ctx = cs._ctx()
        slime.take_turn(ctx)
        slimed = [c for c in cs.player.discard_pile if isinstance(c, SlimedCard)]
        assert len(slimed) == 1

    def test_sticky_shot_advances_to_pokey_pounce(self):
        cs = fresh_with(TwigSlimeM)
        slime = cs.enemies[0]
        ctx = cs._ctx()
        slime.take_turn(ctx)
        # The intent roll happens in the player-turn-start pass, not inside
        # the move (CombatManager.cs:478-484; turn_structure gap G9).
        slime.telegraph_next_move()
        assert slime._move_key == "POKEY_POUNCE"

    def test_pokey_pounce_does_not_add_cards(self):
        cs = fresh_with(TwigSlimeM)
        slime = cs.enemies[0]
        slime._move_key = "POKEY_POUNCE"
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        slime.take_turn(ctx)
        assert len(cs.player.discard_pile) == before


class TestEyeWithTeethDistract:
    def test_distract_adds_three_dazed_to_discard(self):
        cs = fresh_with(EyeWithTeeth)
        eye = cs.enemies[0]
        ctx = cs._ctx()
        eye.take_turn(ctx)
        dazed = [c for c in cs.player.discard_pile if isinstance(c, DazedCard)]
        assert len(dazed) == 3

    def test_distract_fires_every_turn(self):
        cs = fresh_with(EyeWithTeeth)
        eye = cs.enemies[0]
        ctx = cs._ctx()
        eye.take_turn(ctx)
        eye.take_turn(ctx)
        assert len([c for c in cs.player.discard_pile if isinstance(c, DazedCard)]) == 6

    def test_eye_starts_with_illusion_power(self):
        cs = fresh_with(EyeWithTeeth)
        eye = cs.enemies[0]
        assert "illusion" in eye.powers


class TestPhrogParasiteInfect:
    def test_infect_adds_three_infection_to_discard(self):
        cs = fresh_with(PhrogParasite)
        parasite = cs.enemies[0]
        assert parasite._move_key == "INFECT"
        ctx = cs._ctx()
        parasite.take_turn(ctx)
        infected = [c for c in cs.player.discard_pile if isinstance(c, InfectionCard)]
        assert len(infected) == 3

    def test_infect_advances_to_lash(self):
        cs = fresh_with(PhrogParasite)
        parasite = cs.enemies[0]
        ctx = cs._ctx()
        parasite.take_turn(ctx)
        assert parasite._move_key == "LASH"

    def test_lash_does_not_add_cards(self):
        cs = fresh_with(PhrogParasite)
        parasite = cs.enemies[0]
        parasite._move_key = "LASH"
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        parasite.take_turn(ctx)
        assert len(cs.player.discard_pile) == before

    def test_parasite_starts_with_infested_power(self):
        cs = fresh_with(PhrogParasite)
        parasite = cs.enemies[0]
        assert "infested" in parasite.powers
        assert parasite.powers["infested"].amount == 4

    def test_infect_then_lash_then_infect_again(self):
        cs = fresh_with(PhrogParasite)
        parasite = cs.enemies[0]
        ctx = cs._ctx()
        parasite.take_turn(ctx)  # INFECT â†’ 3 cards
        parasite.take_turn(ctx)  # LASH â†’ no cards
        parasite.take_turn(ctx)  # INFECT â†’ 3 more cards
        assert len([c for c in cs.player.discard_pile if isinstance(c, InfectionCard)]) == 6


class TestWrigglerWriggle:
    def test_wriggle_adds_one_infection_to_discard(self):
        cs = fresh_with(Wriggler)
        wriggler = cs.enemies[0]
        wriggler._move_key = "WRIGGLE"
        ctx = cs._ctx()
        wriggler.take_turn(ctx)
        infected = [c for c in cs.player.discard_pile if isinstance(c, InfectionCard)]
        assert len(infected) == 1

    def test_wriggle_also_applies_strength(self):
        cs = fresh_with(Wriggler)
        wriggler = cs.enemies[0]
        wriggler._move_key = "WRIGGLE"
        ctx = cs._ctx()
        wriggler.take_turn(ctx)
        assert wriggler.strength == 2

    def test_nasty_bite_does_not_add_cards(self):
        cs = fresh_with(Wriggler)
        wriggler = cs.enemies[0]
        wriggler._move_key = "NASTY_BITE"
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        wriggler.take_turn(ctx)
        assert len(cs.player.discard_pile) == before

    def test_stunned_wriggler_does_not_add_cards(self):
        cs = fresh_with(Wriggler)
        wriggler = cs.enemies[0]
        wriggler.stunned = True
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        wriggler.take_turn(ctx)
        assert len(cs.player.discard_pile) == before


class TestVantomDismember:
    def test_dismember_adds_three_wound_to_discard(self):
        cs = fresh_with(Vantom)
        vantom = cs.enemies[0]
        vantom._move_key = "DISMEMBER"
        ctx = cs._ctx()
        vantom.take_turn(ctx)
        wounds = [c for c in cs.player.discard_pile if isinstance(c, WoundCard)]
        assert len(wounds) == 3

    def test_dismember_also_deals_damage(self):
        cs = fresh_with(Vantom)
        vantom = cs.enemies[0]
        vantom._move_key = "DISMEMBER"
        ctx = cs._ctx()
        before = cs.player.hp
        vantom.take_turn(ctx)
        assert cs.player.hp < before  # damage was dealt

    def test_ink_blot_does_not_add_cards(self):
        cs = fresh_with(Vantom)
        vantom = cs.enemies[0]
        assert vantom._move_key == "INK_BLOT"
        ctx = cs._ctx()
        before = len(cs.player.discard_pile)
        vantom.take_turn(ctx)
        assert len(cs.player.discard_pile) == before

    def test_vantom_starts_with_slippery(self):
        cs = fresh_with(Vantom)
        vantom = cs.enemies[0]
        assert "slippery" in vantom.powers
        assert vantom.powers["slippery"].amount == 8

    def test_three_wounds_are_distinct_instances(self):
        cs = fresh_with(Vantom)
        vantom = cs.enemies[0]
        vantom._move_key = "DISMEMBER"
        ctx = cs._ctx()
        vantom.take_turn(ctx)
        wounds = [c for c in cs.player.discard_pile if isinstance(c, WoundCard)]
        assert len({id(w) for w in wounds}) == 3  # distinct objects

    def test_dismember_telegraphs_the_status_intent_too(self):
        # Vantom.cs:119 builds DISMEMBER_MOVE with TWO intents:
        # SingleAttackIntent(26) AND StatusIntent(3). Round 13 R11 item 2:
        # the 4th site of monster/_intent_count_lost -- the StatusIntent's
        # CardCount (3) must be carried, not just the STATUS_CARD flag bit.
        cs = fresh_with(Vantom)
        vantom = cs.enemies[0]
        vantom._move_key = "DISMEMBER"
        intent = vantom.current_intent
        assert intent.move_type == MoveType.ATTACK
        assert intent.damage == 26 and intent.hits == 1
        assert intent.has(MoveType.STATUS_CARD)
        assert intent.status_count == 3


class TestVineShamblerGraspingVines:
    def test_grasping_vines_telegraphs_the_card_debuff_too(self):
        # VineShambler.cs:47 builds GRASPING_VINES_MOVE with TWO intents:
        # SingleAttackIntent(8) AND CardDebuffIntent.
        cs = fresh_with(VineShambler)
        shambler = cs.enemies[0]
        shambler._move_key = "GRASPING_VINES"
        intent = shambler.current_intent
        assert intent.move_type == MoveType.ATTACK
        assert intent.damage == 8 and intent.hits == 1
        assert intent.has(MoveType.CARD_DEBUFF)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Status cards accumulate across multiple enemy turns
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestStatusCardAccumulation:
    def test_multiple_slime_goop_turns_stack_in_discard(self):
        cs = fresh_with(LeafSlimeS)
        slime = cs.enemies[0]
        ctx = cs._ctx()
        for _ in range(3):
            slime._move_key = "GOOP"
            slime.take_turn(ctx)
        assert len([c for c in cs.player.discard_pile if isinstance(c, SlimedCard)]) == 3

    def test_status_cards_remain_in_discard_not_hand(self):
        cs = fresh_with(LeafSlimeM)
        slime = cs.enemies[0]
        ctx = cs._ctx()
        slime.take_turn(ctx)  # STICKY_SHOT â†’ 2 Slimed to discard
        hand_slimed = [c for c in cs.player.hand if isinstance(c, SlimedCard)]
        discard_slimed = [c for c in cs.player.discard_pile if isinstance(c, SlimedCard)]
        assert len(hand_slimed) == 0
        assert len(discard_slimed) == 2
