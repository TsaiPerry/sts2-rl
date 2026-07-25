"""Tests for the potions ported from src/Core/Models/Potions.

The older potions (Fire/Block/Strength/Blood/Weak/Swift/Bottled Potential/
Cure All/Stable Serum/Flex/Speed/Touch of Insanity/Gambler's Brew/Explosive
Ampoule/Glowwater/Foul/Skill/Attack) are covered by test_new_features.py's
TestPotions and test_shared_events.py; this file covers the rest of the
Ironclad-reachable pool (SharedPotionPool + Ironclad4Epoch).

Run with:  python -m pytest test/test_potions.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cmds import DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter, FuzzyWurmCrawler
from sts2_rl.potions import make_potion

TWO_CRAWLERS = Encounter(
    id="two_crawlers", monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler]
)


def fresh(*potion_ids: str, seed: int = 0, **kwargs) -> CombatState:
    """Combat with a fixed RNG seed, carrying the named potions in belt order."""
    return CombatState(
        rng=random.Random(seed),
        potions=[make_potion(pid) for pid in potion_ids],
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════════
# Stat / power potions
# ══════════════════════════════════════════════════════════════════════════

class TestPowerPotions:
    def test_dexterity_potion_grants_two_dexterity(self):
        # DexterityPotion.cs — Common, AnyPlayer, PowerVar<DexterityPower>(2).
        cs = fresh("dexterity_potion")
        assert cs.use_potion(0)
        assert cs.player.powers["dexterity"].amount == 2

    def test_vulnerable_potion_applies_three_vulnerable_to_the_target(self):
        # VulnerablePotion.cs — Common, AnyEnemy, PowerVar<VulnerablePower>(3).
        cs = fresh("vulnerable_potion", encounter=TWO_CRAWLERS)
        assert make_potion("vulnerable_potion").targeted
        assert cs.use_potion(0, target_idx=1)
        assert "vulnerable" not in cs.enemies[0].powers
        assert cs.enemies[1].powers["vulnerable"].amount == 3

    def test_fysh_oil_grants_one_strength_and_one_dexterity(self):
        # FyshOil.cs — Uncommon, AnyPlayer, StrengthPower(1) + DexterityPower(1).
        cs = fresh("fysh_oil")
        assert cs.use_potion(0)
        assert cs.player.powers["strength"].amount == 1
        assert cs.player.powers["dexterity"].amount == 1

    def test_liquid_bronze_grants_three_thorns(self):
        # LiquidBronze.cs — Uncommon, AnyPlayer, PowerVar<ThornsPower>(3).
        cs = fresh("liquid_bronze")
        assert cs.use_potion(0)
        assert cs.player.powers["thorns"].amount == 3

    def test_heart_of_iron_grants_seven_plating(self):
        # HeartOfIron.cs — Uncommon, AnyPlayer, PowerVar<PlatingPower>(7).
        cs = fresh("heart_of_iron")
        assert cs.use_potion(0)
        assert cs.player.powers["plating"].amount == 7

    def test_regen_potion_grants_five_regen(self):
        # RegenPotion.cs — Uncommon, AnyPlayer, PowerVar<RegenPower>(5),
        # CanBeGeneratedInCombat=false.
        cs = fresh("regen_potion")
        assert cs.use_potion(0)
        assert cs.player.powers["regen"].amount == 5

    def test_mazaleths_gift_grants_one_ritual(self):
        # MazalethsGift.cs — Rare, AnyPlayer, PowerVar<RitualPower>(1).
        cs = fresh("mazaleths_gift")
        assert cs.use_potion(0)
        assert cs.player.powers["ritual"].amount == 1

    def test_energy_potion_grants_two_energy(self):
        # EnergyPotion.cs — Common, AnyPlayer, EnergyVar(2) → PlayerCmd.GainEnergy.
        cs = fresh("energy_potion")
        energy = cs.player.energy
        assert cs.use_potion(0)
        assert cs.player.energy == energy + 2

    def test_fortifier_triples_current_block(self):
        # Fortifier.cs — Uncommon, AnyPlayer, GainBlock(target.Block * 2,
        # Unpowered): "Triple your Block".
        cs = fresh("fortifier")
        cs.player.block = 7
        assert cs.use_potion(0)
        assert cs.player.block == 21

    def test_fortifier_on_no_block_does_nothing(self):
        cs = fresh("fortifier")
        assert cs.use_potion(0)
        assert cs.player.block == 0

    def test_fortifier_block_is_unpowered(self):
        # ValueProp.Unpowered — Dexterity does not raise it.
        from sts2_rl import DexterityPower
        cs = fresh("fortifier")
        PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 5)
        cs.player.block = 4
        assert cs.use_potion(0)
        assert cs.player.block == 12

    def test_ship_in_a_bottle_blocks_ten_now_and_ten_next_turn(self):
        # ShipInABottle.cs — Rare, AnyPlayer, BlockVar(10, Unpowered): block
        # now plus BlockNextTurnPower(10).
        cs = fresh("ship_in_a_bottle")
        assert cs.use_potion(0)
        assert cs.player.block == 10
        assert cs.player.powers["block_next_turn"].amount == 10
        cs.end_turn()
        # The next turn's block clear pays out the stored block.
        assert cs.player.block >= 10
        assert "block_next_turn" not in cs.player.powers

    def test_beetle_juice_shrinks_the_target_for_four_turns(self):
        # BeetleJuice.cs — Rare, AnyEnemy, RepeatVar(4) → ShrinkPower(4):
        # "Enemy's attacks deal 30% less damage for the next 4 turns".
        cs = fresh("beetle_juice", encounter=TWO_CRAWLERS)
        assert cs.use_potion(0, target_idx=0)
        assert cs.enemies[0].powers["shrink"].amount == 4
        assert "shrink" not in cs.enemies[1].powers

    def test_potion_of_binding_weakens_every_enemy(self):
        # PotionOfBinding.cs — Uncommon, AllEnemies, WeakPower(1) +
        # VulnerablePower(1) over CombatState.HittableEnemies.
        cs = fresh("potion_of_binding", encounter=TWO_CRAWLERS)
        assert not make_potion("potion_of_binding").targeted
        assert cs.use_potion(0)
        for enemy in cs.enemies:
            assert enemy.powers["weak"].amount == 1
            assert enemy.powers["vulnerable"].amount == 1

    def test_potion_of_binding_skips_dead_enemies(self):
        cs = fresh("potion_of_binding", encounter=TWO_CRAWLERS)
        cs.enemies[0].hp = 0
        DamageCmd.deal(cs.hooks, cs.enemies[0], 1, dealer=cs.player)
        assert cs.use_potion(0)
        assert "weak" not in cs.enemies[0].powers
        assert cs.enemies[1].powers["weak"].amount == 1


# ══════════════════════════════════════════════════════════════════════════
# Potions granting the new potion-only powers
# ══════════════════════════════════════════════════════════════════════════

class TestNewPowerPotions:
    def test_clarity_draws_one_then_grants_three_clarity(self):
        # Clarity.cs — Uncommon, AnyPlayer, ClarityPower(3) + CardsVar(1):
        # Draw(1) happens BEFORE the power is applied, so the draw itself is
        # not boosted.
        cs = fresh("clarity")
        hand = len(cs.player.hand)
        assert cs.use_potion(0)
        assert len(cs.player.hand) == hand + 1
        assert cs.player.powers["clarity"].amount == 3

    def test_duplicator_grants_one_duplication(self):
        # Duplicator.cs — Uncommon, Self, DuplicationPower(1).
        cs = fresh("duplicator")
        assert cs.use_potion(0)
        assert cs.player.powers["duplication"].amount == 1

    def test_gigantification_potion_grants_one_gigantification(self):
        # GigantificationPotion.cs — Rare, AnyPlayer, GigantificationPower(1).
        cs = fresh("gigantification_potion")
        assert cs.use_potion(0)
        assert cs.player.powers["gigantification"].amount == 1

    def test_lucky_tonic_grants_one_buffer(self):
        # LuckyTonic.cs — Rare, AnyPlayer, BufferPower(1).
        cs = fresh("lucky_tonic")
        assert cs.use_potion(0)
        assert cs.player.powers["buffer"].amount == 1

    def test_radiant_tincture_grants_energy_now_and_radiance(self):
        # RadiantTincture.cs — Uncommon, AnyPlayer, EnergyVar(1) +
        # RadiancePower(3).
        cs = fresh("radiant_tincture")
        energy = cs.player.energy
        assert cs.use_potion(0)
        assert cs.player.energy == energy + 1
        assert cs.player.powers["radiance"].amount == 3

    def test_powdered_demise_applies_nine_demise_to_the_target(self):
        # PowderedDemise.cs — Uncommon, AnyEnemy, DynamicVar("Demise", 9).
        cs = fresh("powdered_demise", encounter=TWO_CRAWLERS)
        assert make_potion("powdered_demise").targeted
        assert cs.use_potion(0, target_idx=1)
        assert cs.enemies[1].powers["demise"].amount == 9
        assert "demise" not in cs.enemies[0].powers

    def test_shackling_potion_lowers_every_enemys_strength(self):
        # ShacklingPotion.cs — Rare, AllEnemies, ShacklingPotionPower(7) over
        # HittableEnemies: "ALL enemies lose 7 Strength this turn".
        cs = fresh("shackling_potion", encounter=TWO_CRAWLERS)
        assert not make_potion("shackling_potion").targeted
        assert cs.use_potion(0)
        for enemy in cs.enemies:
            assert enemy.powers["strength"].amount == -7
        cs.hooks.on_enemy_side_end()
        for enemy in cs.enemies:
            assert "strength" not in enemy.powers


# ══════════════════════════════════════════════════════════════════════════
# Card-manipulation potions
# ══════════════════════════════════════════════════════════════════════════

def picker(*wanted: str):
    """A CombatState.card_selector that picks the named card ids, in order."""
    def select(purpose, candidates, count):
        chosen = []
        for cid in wanted:
            for card in candidates:
                if card.id == cid and card not in chosen:
                    chosen.append(card)
                    break
        return chosen[:count]
    return select


class TestCardPotions:
    def test_ashwater_exhausts_the_chosen_cards(self):
        # Ashwater.cs — Uncommon, Self: CardSelectCmd.FromHand(min 0, max
        # 999999999) then CardCmd.Exhaust on each pick.
        cs = fresh("ashwater", card_selector=picker("strike", "defend"))
        cs.player.hand = [make_card("strike"), make_card("defend"), make_card("strike")]
        assert cs.use_potion(0)
        assert [c.id for c in cs.player.hand] == ["strike"]
        assert sorted(c.id for c in cs.player.exhaust_pile) == ["defend", "strike"]

    def test_ashwater_can_exhaust_nothing(self):
        # MinSelect 0 — declining the screen is legal.
        cs = fresh("ashwater", card_selector=lambda *a: [])
        cs.player.hand = [make_card("strike")]
        assert cs.use_potion(0)
        assert len(cs.player.hand) == 1
        assert cs.player.exhaust_pile == []

    def test_blessing_of_the_forge_upgrades_the_whole_hand(self):
        # BlessingOfTheForge.cs — Uncommon, Self: CardCmd.Upgrade on every
        # IsUpgradable card in the hand.
        cs = fresh("blessing_of_the_forge")
        cs.player.hand = [make_card("strike"), make_card("defend"), make_card("wound")]
        assert cs.use_potion(0)
        assert cs.player.hand[0].upgrade_level == 1
        assert cs.player.hand[1].upgrade_level == 1
        assert cs.player.hand[2].upgrade_level == 0   # Wound is not upgradable

    def test_blessing_of_the_forge_leaves_other_piles_alone(self):
        cs = fresh("blessing_of_the_forge")
        cs.player.hand = []
        assert cs.use_potion(0)
        assert all(c.upgrade_level == 0 for c in cs.player.draw_pile)

    def test_distilled_chaos_plays_the_top_three_draw_pile_cards(self):
        # DistilledChaos.cs — Rare, Self: AutoPlayFromDrawPile(3, Top,
        # forceExhaust: false).
        cs = fresh("distilled_chaos")
        cs.player.hand = []
        cs.player.draw_pile = [make_card("strike") for _ in range(4)]
        before = cs.enemy.hp
        assert cs.use_potion(0)
        assert before - cs.enemy.hp == 18          # three Strikes
        assert len(cs.player.draw_pile) == 1
        assert len(cs.player.discard_pile) == 3
        assert cs.player.hand == []               # auto-plays never enter hand

    def test_droplet_of_precognition_moves_a_draw_pile_card_to_hand(self):
        # DropletOfPrecognition.cs — Rare, Self: FromCombatPile(Draw, 1) then
        # CardPileCmd.Add(card, PileType.Hand). No cost change.
        cs = fresh("droplet_of_precognition", card_selector=picker("bash"))
        cs.player.hand = []
        cs.player.draw_pile = [make_card("strike"), make_card("bash")]
        assert cs.use_potion(0)
        assert [c.id for c in cs.player.hand] == ["bash"]
        assert [c.id for c in cs.player.draw_pile] == ["strike"]
        assert cs.player.hand[0].energy_cost == 2   # still costs its 2

    def test_liquid_memories_returns_a_discarded_card_free_this_turn(self):
        # LiquidMemories.cs — Rare, Self: FromCombatPile(Discard, 1),
        # SetToFreeThisTurn, then add to hand.
        cs = fresh("liquid_memories", card_selector=picker("bash"))
        cs.player.hand = []
        cs.player.discard_pile = [make_card("strike"), make_card("bash")]
        assert cs.use_potion(0)
        assert [c.id for c in cs.player.hand] == ["bash"]
        assert [c.id for c in cs.player.discard_pile] == ["strike"]
        assert cs.player.hand[0].energy_cost == 0

    def test_snecko_oil_draws_seven_and_randomizes_hand_costs(self):
        # SneckoOil.cs — Rare, AnyPlayer, CardsVar(7): Draw(7) then every
        # non-X card in hand gets EnergyCost.SetThisTurnOrUntilPlayed(
        # Rng.CombatEnergyCosts.NextInt(4)).
        cs = fresh("snecko_oil")
        cs.player.hand = [make_card("bash")]
        cs.player.draw_pile = [make_card("strike") for _ in range(8)]
        hand_before = len(cs.player.hand)
        assert cs.use_potion(0)
        assert len(cs.player.hand) == hand_before + 7
        costs = [c.energy_cost for c in cs.player.hand]
        assert all(0 <= cost <= 3 for cost in costs)
        assert costs != [c._energy_cost for c in cs.player.hand]  # something moved

    def test_snecko_oil_costs_reset_next_turn(self):
        cs = fresh("snecko_oil")
        cs.player.hand = [make_card("bash")]
        assert cs.use_potion(0)
        bash = cs.player.hand[0]
        bash.reset_turn_cost_modifiers()
        assert bash.energy_cost == 2

    def test_snecko_oil_skips_x_cost_cards(self):
        # `Where(c => !c.EnergyCost.CostsX)`.
        cs = fresh("snecko_oil")
        cs.player.hand = [make_card("whirlwind")]
        assert cs.use_potion(0)
        assert cs.player.hand[0].energy_cost == 0   # X cards print 0 and stay 0
        assert cs.player.hand[0]._cost_this_turn is None

    def test_soldiers_stew_gives_every_strike_card_one_replay(self):
        # SoldiersStew.cs — Rare (Ironclad), AnyPlayer: every card in
        # PlayerCombatState.AllCards tagged CardTag.Strike gets
        # BaseReplayCount++.
        cs = fresh("soldiers_stew")
        cs.player.hand = [make_card("twin_strike"), make_card("defend")]
        cs.player.discard_pile = [make_card("pommel_strike")]
        assert cs.use_potion(0)
        assert cs.player.hand[0].base_replay_count == 1
        assert cs.player.hand[1].base_replay_count == 0
        assert cs.player.discard_pile[0].base_replay_count == 1
        for card in cs.player.draw_pile:
            expected = 1 if "strike" in card.tags else 0
            assert card.base_replay_count == expected, card.id

    def test_soldiers_stew_strikes_are_played_twice(self):
        cs = fresh("soldiers_stew")
        cs.player.hand = [make_card("strike")]
        cs.player.energy = 3
        assert cs.use_potion(0)
        before = cs.enemy.hp
        assert cs.play_card(0)
        assert before - cs.enemy.hp == 12


# ══════════════════════════════════════════════════════════════════════════
# Card-generation potions
# ══════════════════════════════════════════════════════════════════════════

class TestGeneratedCardPotions:
    def test_colorless_potion_adds_a_free_colorless_card(self):
        # ColorlessPotion.cs — Common, Self: GetDistinctForCombat(
        # ColorlessCardPool.GetUnlockedCards(), 3, CombatCardGeneration), a
        # canSkip choose-a-card screen, then SetToFreeThisTurn + add to hand.
        # Legacy play resolves the pick inline (like Skill/Attack Potion).
        from sts2_rl.cards.pool import COLORLESS_POOL
        cs = fresh("colorless_potion")
        cs.player.hand = []
        assert cs.use_potion(0)
        assert len(cs.player.hand) == 1
        assert cs.player.hand[0].id in COLORLESS_POOL
        assert cs.player.hand[0].energy_cost == 0

    def test_colorless_potion_offers_three_cards_in_a_parity_run(self):
        from sts2_rl.cards.pool import COLORLESS_POOL
        from sts2_rl.combat import CombatState
        from sts2_rl.rng import RunRngSet
        cs = CombatState(
            rng_set=RunRngSet("89U21BV1TZ"), potions=[make_potion("colorless_potion")]
        )
        assert cs.use_potion(0)
        offered = cs._pending_screen_cards
        assert len(offered) == 3
        assert len({c.id for c in offered}) == 3          # distinct
        assert all(c.id in COLORLESS_POOL for c in offered)

    def test_power_potion_adds_a_free_power_card(self):
        # PowerPotion.cs — Common, Self: the character pool filtered to
        # Type == Power, 3 distinct, choose-a-card screen, free this turn.
        from sts2_rl.cards.base import CardType
        cs = fresh("power_potion")
        cs.player.hand = []
        assert cs.use_potion(0)
        assert len(cs.player.hand) == 1
        assert cs.player.hand[0].card_type == CardType.POWER
        assert cs.player.hand[0].energy_cost == 0

    def test_power_potion_offers_three_powers_in_a_parity_run(self):
        from sts2_rl.cards.base import CardType
        from sts2_rl.combat import CombatState
        from sts2_rl.rng import RunRngSet
        cs = CombatState(
            rng_set=RunRngSet("89U21BV1TZ"), potions=[make_potion("power_potion")]
        )
        assert cs.use_potion(0)
        offered = cs._pending_screen_cards
        assert len(offered) == 3
        assert all(c.card_type == CardType.POWER for c in offered)

    def test_orobic_acid_adds_one_free_attack_skill_and_power(self):
        # OrobicAcid.cs — Rare, Self: three GetDistinctForCombat(…, 1) calls
        # (Attack, then Skill, then Power) off the character pool, each
        # SetToFreeThisTurn, all added to hand. No selection screen.
        from sts2_rl.cards.base import CardType
        cs = fresh("orobic_acid")
        cs.player.hand = []
        assert cs.use_potion(0)
        assert [c.card_type for c in cs.player.hand] == [
            CardType.ATTACK, CardType.SKILL, CardType.POWER
        ]
        assert all(c.energy_cost == 0 for c in cs.player.hand)


# ══════════════════════════════════════════════════════════════════════════
# Run-layer potions (max HP, belt refill, automatic death prevention)
# ══════════════════════════════════════════════════════════════════════════

class TestRunLayerPotions:
    def test_fruit_juice_raises_max_hp_and_heals(self):
        # FruitJuice.cs — Rare, AnyTime, MaxHpVar(5) → CreatureCmd.GainMaxHp,
        # which raises Max HP and then heals the same amount.
        cs = fresh("fruit_juice")
        cs.player.hp = 40
        max_hp = cs.player.max_hp
        assert cs.use_potion(0)
        assert cs.player.max_hp == max_hp + 5
        assert cs.player.hp == 45

    def test_fruit_juice_at_full_hp_still_gains_max_hp(self):
        cs = fresh("fruit_juice")
        max_hp = cs.player.max_hp
        assert cs.use_potion(0)
        assert cs.player.max_hp == max_hp + 5
        assert cs.player.hp == max_hp + 5

    def test_healing_potions_are_never_generated_in_combat(self):
        # PotionModel.CanBeGeneratedInCombat=false on the healing-adjacent three.
        from sts2_rl.potion_pools import NOT_GENERATED_IN_COMBAT
        assert {"fruit_juice", "fairy_in_a_bottle", "regen_potion"} == set(
            NOT_GENERATED_IN_COMBAT
        )

    def test_entropic_brew_fills_every_empty_potion_slot(self):
        # EntropicBrew.cs — Rare, AnyTime: `while (Owner.HasOpenPotionSlots)`
        # create a random potion (CombatPotionGeneration) and TryToProcure it.
        # The brew's own slot is freed before OnUse runs (RemoveBeforeUse), so
        # it is refilled too.
        cs = fresh("entropic_brew", "block_potion")
        assert cs.use_potion(0)
        assert len(cs.player.held_potions) == cs.player.max_potions
        assert cs.player.potions[1].id == "block_potion"   # untouched slot

    def test_entropic_brew_only_rolls_reward_pool_potions(self):
        from sts2_rl.potion_pools import POTION_POOL
        pool_ids = {pid for pid, _ in POTION_POOL}
        cs = fresh("entropic_brew")
        assert cs.use_potion(0)
        assert all(p.id in pool_ids for p in cs.player.held_potions)

    def test_fairy_in_a_bottle_prevents_death_and_heals_to_thirty_percent(self):
        # FairyInABottle.cs — Rare, Automatic: ShouldDie is false for its owner,
        # and AfterPreventingDeath heals max(MaxHp * 0.3, 1) from 0 HP — i.e.
        # the player ends the hit at 30% of Max HP, and the potion is discarded.
        cs = fresh("fairy_in_a_bottle")
        cs.player.hp = 10
        DamageCmd.deal(cs.hooks, cs.player, 50, dealer=cs.enemy)
        assert cs.player.hp == cs.player.max_hp * 30 // 100
        assert not cs.player.is_dead
        assert cs.player.held_potions == []

    def test_fairy_in_a_bottle_only_saves_once(self):
        cs = fresh("fairy_in_a_bottle")
        cs.player.hp = 10
        DamageCmd.deal(cs.hooks, cs.player, 50, dealer=cs.enemy)
        DamageCmd.deal(cs.hooks, cs.player, 500, dealer=cs.enemy)
        assert cs.player.is_dead

    def test_fairy_in_a_bottle_ignores_enemy_deaths(self):
        # `ShouldDie(creature) => creature != Owner.Creature`.
        cs = fresh("fairy_in_a_bottle")
        DamageCmd.deal(cs.hooks, cs.enemy, 500, dealer=cs.player)
        assert cs.enemy.is_dead
        assert len(cs.player.held_potions) == 1

    def test_fairy_in_a_bottle_cannot_be_used_manually(self):
        # PotionUsage.Automatic — the game's Use button is disabled
        # (NPotionPopup.cs:131), so the action is invalid.
        cs = fresh("fairy_in_a_bottle")
        assert make_potion("fairy_in_a_bottle").automatic
        assert not cs.use_potion(0)
        assert len(cs.player.held_potions) == 1

    def test_automatic_potions_are_masked_out_of_the_action_space(self):
        from sts2_rl.full_env import COMBAT_POTION_BASE, MAX_ENEMIES, combat_action_masks
        cs = fresh("fairy_in_a_bottle", "block_potion")
        mask = combat_action_masks(cs)
        assert not mask[
            COMBAT_POTION_BASE:COMBAT_POTION_BASE + MAX_ENEMIES
        ].any()                                    # slot 0: the fairy
        assert mask[
            COMBAT_POTION_BASE + MAX_ENEMIES:COMBAT_POTION_BASE + 2 * MAX_ENEMIES
        ].any()                                    # slot 1: the block potion


# ══════════════════════════════════════════════════════════════════════════
# Pool coverage
# ══════════════════════════════════════════════════════════════════════════

class TestPoolCoverage:
    def test_every_pooled_potion_is_implemented(self):
        # potion_pools.POTION_POOL is the Ironclad-reachable roster
        # (IroncladPotionPool + SharedPotionPool). Nothing in it should still
        # resolve to a membership placeholder.
        from sts2_rl.potion_pools import POTION_POOL, _ParityPotion, make_pool_potion
        missing = [
            pid for pid, _ in POTION_POOL
            if isinstance(make_pool_potion(pid), _ParityPotion)
        ]
        assert missing == []

    def test_pool_rarities_match_the_potion_classes(self):
        from sts2_rl.potion_pools import POTION_POOL
        from sts2_rl.potions import ALL_POTIONS
        for pid, rarity in POTION_POOL:
            assert ALL_POTIONS[pid].rarity == rarity, pid

    def test_in_combat_generation_skips_the_healing_potions(self):
        # PotionFactory.CreateRandomPotionInCombat filters
        # CanBeGeneratedInCombat=false.
        from sts2_rl.potions import random_potion
        rng = random.Random(0)
        ids = {random_potion(rng).id for _ in range(400)}
        assert not ids & {"fruit_juice", "fairy_in_a_bottle", "regen_potion"}

    def test_every_potion_id_is_the_snake_case_source_class_name(self):
        from sts2_rl.potion_pools import POTION_POOL, _RAW_POOL
        from sts2_rl.rng import snake_case
        for (name, _), (pid, _) in zip(_RAW_POOL, POTION_POOL):
            assert snake_case(name) == pid
