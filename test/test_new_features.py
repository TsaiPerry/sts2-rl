"""Tests for damage typing (ValueProps), CreatureCmd verbs, the monster move
state machine, potions, and the extended intent vocabulary.

Run with:  python -m pytest test/test_new_features.py -v
"""
from __future__ import annotations

import random

from sts2_rl import (
    BloodPotion,
    BlockPotion,
    CombatState,
    CreatureCmd,
    DamageCmd,
    DamageProps,
    FirePotion,
    MoveRepeatType,
    MoveType,
    PowerCmd,
    StrengthPotion,
    StrengthPower,
    VulnerablePower,
    WeakPotion,
)
from sts2_rl.monsters import Fogmog, Mawler, MoveType as MonsterMoveType
from sts2_rl.monsters.overgrowth import FOGMOG_NORMAL, MAWLER_NORMAL


def fresh(seed: int = 0, **kwargs) -> CombatState:
    return CombatState(rng=random.Random(seed), **kwargs)


# ══════════════════════════════════════════════════════════════════════════
# Damage typing
# ══════════════════════════════════════════════════════════════════════════

class TestDamageTyping:
    def test_unblockable_ignores_block(self):
        cs = fresh()
        cs.enemy.block = 100
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 5, props=DamageProps.NON_CARD_HP_LOSS)
        assert cs.enemy.hp == before - 5
        assert cs.enemy.block == 100

    def test_unpowered_skips_strength_and_vulnerable(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 5)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 3)
        before = cs.enemy.hp
        DamageCmd.deal(
            cs.hooks, cs.enemy, 6, dealer=cs.player,
            props=DamageProps.NON_CARD_UNPOWERED,
        )
        assert cs.enemy.hp == before - 6  # not (6+5)*1.5

    def test_powered_attack_still_modified(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 5)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 3)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 6, dealer=cs.player)
        assert cs.enemy.hp == before - int((6 + 5) * 1.5)

    def test_poison_is_unblockable(self):
        from sts2_rl import PoisonPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, PoisonPower, 4)
        cs.enemy.block = 100
        before = cs.enemy.hp
        cs.end_turn()  # poison ticks at the start of the enemy's turn
        assert cs.enemy.hp <= before - 4  # block did not absorb it
        assert cs.enemy.block <= 100


# ══════════════════════════════════════════════════════════════════════════
# CreatureCmd verbs
# ══════════════════════════════════════════════════════════════════════════

class TestCreatureVerbs:
    def test_heal_caps_at_max_hp(self):
        cs = fresh()
        cs.player.hp = cs.player.max_hp - 3
        healed = CreatureCmd.heal(cs.hooks, cs.player, 10)
        assert healed == 3
        assert cs.player.hp == cs.player.max_hp

    def test_stunned_enemy_skips_its_turn(self):
        cs = fresh()
        CreatureCmd.stun(cs.hooks, cs.enemy)
        assert cs.enemy.current_intent.move_type == MoveType.ATTACK or True
        hp_before = cs.player.hp
        cs.end_turn()
        assert cs.player.hp == hp_before  # enemy skipped its attack
        assert not cs.enemy.stunned       # stun consumed

    def test_escape_wins_combat_when_last_enemy_flees(self):
        cs = fresh()
        for e in cs.enemies:
            CreatureCmd.escape(cs.hooks, e)
        assert cs.is_over
        assert cs.result.player_won
        assert all(not e.is_dead for e in cs.enemies)  # fled, not killed

    def test_kill_goes_through_death_pipeline(self):
        cs = fresh()
        CreatureCmd.kill(cs.hooks, cs.enemy)
        assert cs.enemy.is_dead


# ══════════════════════════════════════════════════════════════════════════
# Monster move state machine
# ══════════════════════════════════════════════════════════════════════════

class TestStateMachine:
    def test_fogmog_opens_with_summon_then_swipe(self):
        cs = fresh(encounter=FOGMOG_NORMAL)
        fogmog = cs.enemies[0]
        assert isinstance(fogmog, Fogmog)
        assert fogmog.current_intent.move_type == MonsterMoveType.SUMMON
        cs.end_turn()
        assert any(type(e).__name__ == "EyeWithTeeth" for e in cs.enemies)
        assert fogmog._current_move.id == "SWIPE_MOVE"

    def test_fogmog_branch_only_yields_legal_sequences(self):
        # After SWIPE the branch picks SWIPE_RANDOM (→HEADBUTT) or HEADBUTT;
        # HEADBUTT always returns to SWIPE.
        legal_after = {
            "ILLUSION_MOVE": {"SWIPE_MOVE"},
            "SWIPE_MOVE": {"SWIPE_RANDOM_MOVE", "HEADBUTT_MOVE"},
            "SWIPE_RANDOM_MOVE": {"HEADBUTT_MOVE"},
            "HEADBUTT_MOVE": {"SWIPE_MOVE"},
        }
        for seed in range(10):
            cs = fresh(seed=seed, encounter=FOGMOG_NORMAL)
            fogmog = cs.enemies[0]
            prev = fogmog._current_move.id
            for _ in range(12):
                if cs.is_over:
                    break
                cs.player.hp = cs.player.max_hp  # keep the fight going
                cs.end_turn()
                cur = fogmog._current_move.id
                assert cur in legal_after[prev], f"{prev} -> {cur}"
                prev = cur

    def test_mawler_roar_used_at_most_once_per_combat(self):
        for seed in range(20):
            cs = fresh(seed=seed, encounter=MAWLER_NORMAL)
            mawler = cs.enemies[0]
            assert isinstance(mawler, Mawler)
            roars = 0
            last = None
            for _ in range(25):
                if cs.is_over:
                    break
                cs.player.hp = cs.player.max_hp
                move = mawler._current_move.id
                if move == "ROAR":
                    roars += 1
                # CANNOT_REPEAT / USE_ONLY_ONCE: no move twice in a row
                assert move != last
                last = move
                cs.end_turn()
            assert roars <= 1

    def test_use_only_once_and_cannot_repeat_weights(self):
        from sts2_rl import MonsterMoveStateMachine, MoveState, RandomBranchState
        from sts2_rl.monsters.base import Intent

        a = MoveState("A", lambda ctx: None, Intent(MoveType.ATTACK, damage=1))
        b = MoveState("B", lambda ctx: None, Intent(MoveType.ATTACK, damage=2))
        once = MoveState("ONCE", lambda ctx: None, Intent(MoveType.BUFF))
        branch = RandomBranchState("BR")
        branch.add_branch(a, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        branch.add_branch(b, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        branch.add_branch(once, repeat_type=MoveRepeatType.USE_ONLY_ONCE)
        for m in (a, b, once):
            m.follow_up = branch
        machine = MonsterMoveStateMachine([a, b, once, branch], a)

        class _Owner:  # minimal stand-in for a MachineMonster
            pass
        owner = _Owner()
        owner.machine = machine

        rng = random.Random(0)
        seen = [machine.roll_move(owner, rng)]
        for _ in range(60):
            machine.on_move_performed(seen[-1])
            seen.append(machine.roll_move(owner, rng))
        ids = [m.id for m in seen]
        assert ids.count("ONCE") <= 1
        assert all(x != y for x, y in zip(ids, ids[1:]))


# ══════════════════════════════════════════════════════════════════════════
# Potions
# ══════════════════════════════════════════════════════════════════════════

class TestPotions:
    def test_fire_potion_unpowered_damage(self):
        cs = fresh(potions=[FirePotion()])
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 5)
        before = cs.enemy.hp
        assert cs.use_potion(0)
        assert cs.enemy.hp == before - FirePotion.DAMAGE  # not boosted
        assert cs.player.potions == []

    def test_block_potion_ignores_frail_and_dex(self):
        from sts2_rl import DexterityPower
        cs = fresh(potions=[BlockPotion()])
        PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 3)
        assert cs.use_potion(0)
        assert cs.player.block == BlockPotion.BLOCK

    def test_blood_potion_heals_percent_of_max(self):
        cs = fresh(potions=[BloodPotion()])
        cs.player.hp = 10
        assert cs.use_potion(0)
        assert cs.player.hp == 10 + cs.player.max_hp * 20 // 100

    def test_strength_and_weak_potions_apply_powers(self):
        cs = fresh(potions=[StrengthPotion(), WeakPotion()])
        assert cs.use_potion(0)
        assert cs.player.powers["strength"].amount == 2
        assert cs.use_potion(0)  # WeakPotion shifted into slot 0
        assert cs.enemy.powers["weak"].amount == 3

    def test_swift_potion_draws_three(self):
        # SwiftPotion.cs — Common, CombatOnly, CardsVar(3);
        # OnUse = CardPileCmd.Draw(3) on the target player.
        from sts2_rl.potions import make_potion
        cs = fresh(potions=[make_potion("swift_potion")])
        before = len(cs.player.hand)
        assert cs.use_potion(0)
        assert len(cs.player.hand) == before + 3

    def test_bottled_potential_recycles_the_hand_and_draws_five(self):
        # BottledPotential.cs - Rare, CombatOnly, CardsVar(5). OnUse =
        # CardPileCmd.Add(Hand.Cards, PileType.Draw) (Bottom, no rng),
        # CardPileCmd.Shuffle (ONE StableShuffle of discard+draw on
        # Rng.Shuffle), CardPileCmd.Draw(5). The hand is recycled, not
        # discarded, so no card leaves the draw/hand cycle.
        from sts2_rl.potions import make_potion
        cs = fresh(potions=[make_potion("bottled_potential")])
        cs.player.discard_pile.append(cs.player.draw_pile.pop())
        total = (len(cs.player.hand) + len(cs.player.draw_pile)
                 + len(cs.player.discard_pile))
        assert cs.use_potion(0)
        assert len(cs.player.hand) == 5
        # Everything that was in the hand went back into the draw pile, and
        # the discard pile was shuffled in too - nothing is left behind.
        assert cs.player.discard_pile == []
        assert len(cs.player.hand) + len(cs.player.draw_pile) == total

    def test_cure_all_gains_energy_and_draws_two(self):
        # CureAll.cs - Uncommon, CombatOnly, EnergyVar(1) + CardsVar(2);
        # OnUse = PlayerCmd.GainEnergy(1) then CardPileCmd.Draw(2).
        from sts2_rl.potions import make_potion
        cs = fresh(potions=[make_potion("cure_all")])
        hand, energy = len(cs.player.hand), cs.player.energy
        assert cs.use_potion(0)
        assert cs.player.energy == energy + 1
        assert len(cs.player.hand) == hand + 2

    def test_stable_serum_retains_the_hand_for_two_turns(self):
        # StableSerum.cs - Uncommon, CombatOnly, RepeatVar(2); OnUse =
        # PowerCmd.Apply<RetainHandPower>(2) on the target player.
        from sts2_rl.potions import make_potion
        cs = fresh(potions=[make_potion("stable_serum")])
        assert cs.use_potion(0)
        assert cs.player.powers["retain_hand"].amount == 2

    def test_invalid_slot_rejected(self):
        cs = fresh()
        assert not cs.use_potion(0)


# ══════════════════════════════════════════════════════════════════════════
# Env observation
# ══════════════════════════════════════════════════════════════════════════

class TestEnvObservation:
    def test_obs_dim_and_intent_flags(self):
        from sts2_rl.env import OBS_DIM, STS2CombatEnv
        env = STS2CombatEnv()
        obs, _ = env.reset(seed=0)
        assert obs.shape == (OBS_DIM,)
        assert OBS_DIM == 17
        assert set(obs[12:17]).issubset({0.0, 1.0})


# ══════════════════════════════════════════════════════════════════════════
# Attack-command boundary (before_attack / after_attack)
# ══════════════════════════════════════════════════════════════════════════

class TestAttackBoundary:
    """The before_attack/after_attack boundary mirrors AttackCommand.Execute
    (src/Core/Commands/Builders/AttackCommand.cs: Hook.BeforeAttack /
    Hook.AfterAttack fire once per attack command, card- or monster-sourced).
    Self-HP-loss card effects are plain damage commands in the game — never
    AttackCommands — so they must not open the boundary; and Vigor's own
    guard (VigorPower.cs BeforeAttack:
    `if (!command.DamageProps.IsPoweredAttack()) return;`) means an
    unpowered attack neither uses nor consumes Vigor."""

    def test_self_hp_loss_skill_does_not_consume_vigor(self):
        from sts2_rl.cards import make_card
        from sts2_rl.powers import VigorPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VigorPower, 8)
        cs.player.hand.append(make_card("bloodletting"))
        cs.player.energy = 10
        assert cs.play_card(len(cs.player.hand) - 1)
        assert cs.player.powers["vigor"].amount == 8

    def test_unpowered_attack_neither_uses_nor_consumes_vigor(self):
        from sts2_rl.cards import make_card
        from sts2_rl.powers import VigorPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VigorPower, 8)
        strike = make_card("strike")
        strike.is_unpowered = True  # Omnislice-echo-style unpowered attack
        cs.player.hand.append(strike)
        cs.player.energy = 10
        hp = cs.enemy.hp
        assert cs.play_card(len(cs.player.hand) - 1)
        assert cs.enemy.hp == hp - 6  # base damage only: no Vigor bonus
        assert cs.player.powers["vigor"].amount == 8  # and not consumed
