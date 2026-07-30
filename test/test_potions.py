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


def _play(cs: CombatState, card) -> None:
    """Give the player `card`, plenty of energy, and play it."""
    cs.player.energy = 10
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1)


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
        # The screen is MinSelect 0 / canSkip, so pin the pick with a selector
        # rather than relying on the selectorless default (which may decline —
        # see test_the_generator_screen_can_be_declined).
        cs = fresh("colorless_potion",
                   card_selector=lambda purpose, cands, count: cands[:1])
        cs.player.hand = []
        assert cs.use_potion(0)
        assert len(cs.player.hand) == 1
        assert cs.player.hand[0].id in COLORLESS_POOL
        assert cs.player.hand[0].energy_cost == 0

    def test_the_generator_screen_can_be_declined(self):
        """`FromChooseACardScreen(..., canSkip: true)` (CardSelectCmd.cs:216-261)
        with `GetSelectedCards(cards, 0, 1)` at :230 — taking nothing is a
        first-class outcome, and the caller's `if (cardModel != null)` is what
        makes it add nothing. Toolbox and Choices Paradox open the same screen
        with canSkip FALSE, hence the separate purpose."""
        from sts2_rl.driver import SKIPPABLE_PURPOSES

        seen = []

        def decline(purpose, candidates, count):
            seen.append(purpose)
            return []

        cs = fresh("colorless_potion", card_selector=decline)
        cs.player.hand = []
        assert cs.use_potion(0)
        assert cs.player.hand == []
        assert seen == ["choose_a_card_optional"]
        assert seen[0] in SKIPPABLE_PURPOSES

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


# ══════════════════════════════════════════════════════════════════════════
# The choose-a-card screen (CardSelectCmd.FromChooseACardScreen, canSkip)
# ══════════════════════════════════════════════════════════════════════════

class TestChooseACardScreen:
    """AttackPotion/ColorlessPotion/PowerPotion/SkillPotion each generate three
    cards and hand them to `CardSelectCmd.FromChooseACardScreen(..., canSkip:
    true)` (CardSelectCmd.cs:216-261), adding the result only `if (cardModel !=
    null)`. The legacy (non-parity) arm used to take `cards[0]`
    unconditionally, so the other two candidates did not exist and the screen
    could never be declined."""

    POTIONS = ("attack_potion", "colorless_potion", "power_potion", "skill_potion")

    def test_the_screen_pick_is_the_card_that_reaches_the_hand(self):
        for pid in self.POTIONS:
            offered: list = []

            def pick_last(purpose, candidates, count, _o=offered):
                _o[:] = candidates
                return candidates[-1:]

            cs = fresh(pid, card_selector=pick_last)
            cs.player.hand = []
            assert cs.use_potion(0)
            assert len(offered) == 3, pid
            assert [c.id for c in cs.player.hand] == [offered[-1].id], pid
            assert cs.player.hand[0].energy_cost == 0, pid   # SetToFreeThisTurn

    def test_the_screen_can_be_declined(self):
        # canSkip: true -> `if (cardModel != null)` adds nothing.
        for pid in self.POTIONS:
            cs = fresh(pid, card_selector=lambda *a: [])
            cs.player.hand = []
            assert cs.use_potion(0)
            assert cs.player.hand == [], pid


# ══════════════════════════════════════════════════════════════════════════
# MinSelect 0 screens (Ashwater, Gambler's Brew)
# ══════════════════════════════════════════════════════════════════════════

class TestMinSelectZero:
    """Both potions build `CardSelectorPrefs(prompt, 0, 999999999)`, and
    `FromHand`'s auto-resolve shortcut is `list.Count <= prefs.MinSelect`
    (CardSelectCmd.cs:708-711) — false for any non-empty hand at MinSelect 0,
    so the screen is always shown and the player may confirm none."""

    def test_ashwater_under_the_scripted_selector_exhausts_only_junk(self):
        from sts2_rl.selectors import scripted_card_selector

        cs = fresh("ashwater", card_selector=scripted_card_selector)
        cs.player.hand = [make_card("strike"), make_card("wound"),
                          make_card("defend")]
        assert cs.use_potion(0)
        assert [c.id for c in cs.player.exhaust_pile] == ["wound"]
        assert [c.id for c in cs.player.hand] == ["strike", "defend"]

    def test_gamblers_brew_under_the_scripted_selector_cycles_only_junk(self):
        from sts2_rl.selectors import scripted_card_selector

        cs = fresh("gamblers_brew", card_selector=scripted_card_selector)
        cs.player.draw_pile = [make_card("bash")]
        cs.player.hand = [make_card("strike"), make_card("wound")]
        assert cs.use_potion(0)
        assert [c.id for c in cs.player.discard_pile] == ["wound"]
        assert sorted(c.id for c in cs.player.hand) == ["bash", "strike"]

    def test_the_zero_reaches_the_selectorless_engine_default(self):
        """The MinSelect is only real if the call site PASSES it: without
        `min_select=0` the engine default clamps to `count` and takes the whole
        hand every time.  Over many seeds a genuine 0..N screen must return
        different sizes, including sometimes none."""
        sizes = set()
        for seed in range(30):
            cs = fresh("ashwater", seed=seed, card_selector=None)
            cs.player.hand = [make_card(cid) for cid in
                              ("strike", "defend", "bash", "wound")]
            assert cs.use_potion(0)
            sizes.add(len(cs.player.exhaust_pile))
        assert sizes <= {0, 1, 2, 3, 4}
        assert len(sizes) > 1, f"still an exactly-N screen: {sizes}"
        assert 0 in sizes, "confirming none was never reachable"

    def test_gambling_chip_is_the_same_screen(self):
        """GamblingChip.cs:20 builds the identical prefs, so its turn-1
        mulligan is 0..hand-size too, not always-all."""
        from sts2_rl.relics import make_relic

        sizes = set()
        for seed in range(30):
            cs = fresh(seed=seed, card_selector=None,
                       relics=[make_relic("gambling_chip")],
                       starting_deck=[make_card("strike") for _ in range(12)])
            sizes.add(len(cs.player.discard_pile))
        assert len(sizes) > 1, f"still an all-or-nothing mulligan: {sizes}"


# ══════════════════════════════════════════════════════════════════════════
# PotionUsage.AnyTime — the out-of-combat use path
# ══════════════════════════════════════════════════════════════════════════

class TestAnyTimeUsage:
    """`PotionUsage.AnyTime` means the Use button is live outside combat, and
    `OnUseWrapper` is written for it (PotionModel.cs:294,298,334,336 all
    null-check the combat state)."""

    def _run(self, *potion_ids: str):
        from sts2_rl.run import RunState
        run = RunState(rng=random.Random(0))
        run.start_run(acts=["overgrowth"])
        for pid in potion_ids:
            run.add_potion(make_potion(pid))
        return run

    def test_the_four_any_time_potions_are_marked(self):
        for pid in ("blood_potion", "entropic_brew", "foul_potion", "fruit_juice"):
            assert make_potion(pid).usage == "any_time", pid
        assert make_potion("fire_potion").usage == "combat_only"
        assert make_potion("fairy_in_a_bottle").usage == "automatic"

    def test_fruit_juice_on_the_map_raises_max_hp(self):
        run = self._run("fruit_juice")
        max_hp = run.max_hp
        assert run.use_potion(0)
        assert run.max_hp == max_hp + 5
        assert run.potions[0] is None

    def test_blood_potion_on_the_map_heals(self):
        run = self._run("blood_potion")
        run.hp = 10
        assert run.use_potion(0)
        assert run.hp == 10 + run.max_hp * 20 // 100

    def test_entropic_brew_on_the_map_refills_the_belt(self):
        run = self._run("entropic_brew")
        assert run.use_potion(0)
        assert len(run.held_potions) == run.max_potions

    def test_a_combat_only_potion_cannot_be_drunk_on_the_map(self):
        run = self._run("fire_potion")
        assert not run.use_potion(0)
        assert len(run.held_potions) == 1

    def test_foul_potion_drives_the_merchant_off_for_a_hundred_gold(self):
        # FoulPotion.cs:79-88 — the MerchantRoom arm.
        run = self._run("foul_potion")
        gold = run.gold
        assert not run.merchant_driven_off
        assert run.use_potion(0)
        assert run.merchant_driven_off
        assert run.gold == gold + 100


# ══════════════════════════════════════════════════════════════════════════
# Procurement (PotionCmd.TryToProcure)
# ══════════════════════════════════════════════════════════════════════════

class TestProcurement:
    def test_combat_side_procurement_runs_the_should_procure_gate(self):
        # Sozu.cs:17-20 is the source's only ShouldProcurePotion implementer,
        # and PotionCmd.TryToProcure (PotionCmd.cs:31-39) is the only procure
        # entry point in the game.
        from sts2_rl.cards import make_card
        from sts2_rl.relics import make_relic

        plain = CombatState(rng=random.Random(0), relics=[])
        _play(plain, make_card("alchemize"))
        assert plain.player.held_potions != []

        sozu = CombatState(rng=random.Random(0), relics=[make_relic("sozu")])
        _play(sozu, make_card("alchemize"))
        assert sozu.player.held_potions == []

    def test_entropic_brew_stops_when_the_gate_refuses(self):
        from sts2_rl.relics import make_relic

        cs = fresh("entropic_brew", relics=[make_relic("sozu")])
        assert cs.use_potion(0)
        assert cs.player.held_potions == []

    def test_belt_buckle_loses_its_dexterity_on_a_procured_potion(self):
        # BeltBuckle.cs:63-70 (AfterPotionProcured) is the half of "while you
        # have no potions" that enforces the *no*.
        from sts2_rl.cards import make_card
        from sts2_rl.relics import make_relic

        cs = CombatState(rng=random.Random(0), relics=[make_relic("belt_buckle")])
        assert cs.player.powers["dexterity"].amount == 2
        _play(cs, make_card("alchemize"))
        assert cs.player.held_potions != []
        assert "dexterity" not in cs.player.powers


# ══════════════════════════════════════════════════════════════════════════
# Single-unit source fixes
# ══════════════════════════════════════════════════════════════════════════

class TestSingleUnitFixes:
    def test_touch_of_insanity_offers_a_globally_costed_card(self):
        # TouchOfInsanity.cs:22 ORs CostsEnergyOrStars(local) with
        # CostsEnergyOrStars(global) — a card free THIS TURN but raised by
        # Spiked Gauntlets still costs energy globally, so it is offered.
        from sts2_rl.relics import make_relic

        cs = CombatState(rng=random.Random(0),
                         potions=[make_potion("touch_of_insanity")],
                         relics=[make_relic("spiked_gauntlets")])
        card = make_card("inflame")          # a Power card
        card.set_free_this_turn()            # local cost 0, global cost 1
        cs.player.hand = [card]
        assert cs.use_potion(0)
        assert card._cost_this_combat == 0

    def test_touch_of_insanity_still_skips_a_globally_free_card(self):
        cs = fresh("touch_of_insanity")
        card = make_card("strike")
        card.set_free_this_turn()
        cs.player.hand = [card]
        assert cs.use_potion(0)
        assert card._cost_this_combat is None

    def test_foul_potion_damages_the_thrower_first(self):
        # CombatState.Creatures is `_allies.Concat(_enemies)`
        # (CombatState.cs:70) — the thrower before the enemies.
        cs = fresh("foul_potion", encounter=TWO_CRAWLERS)
        order: list[str] = []
        orig = cs.hooks.on_hp_changed

        def watch(creature, delta, _orig=orig):
            order.append("player" if creature is cs.player else "enemy")
            return _orig(creature, delta)

        cs.hooks.on_hp_changed = watch
        assert cs.use_potion(0)
        assert order == ["player", "enemy", "enemy"]

    def test_fairy_in_a_bottle_runs_the_whole_use_pipeline(self):
        # FairyInABottle.cs:44 — AfterPreventingDeath awaits OnUseWrapper, so
        # PotionModel.cs:338's Hook.AfterPotionUsed fires when the fairy pops.
        from sts2_rl.relics import make_relic

        cs = CombatState(rng=random.Random(0),
                         potions=[make_potion("fairy_in_a_bottle")],
                         relics=[make_relic("reptile_trinket")])
        cs.player.hp = 5
        DamageCmd.deal(cs.hooks, cs.player, 99, dealer=cs.enemy)
        assert cs.player.hp == max(cs.player.max_hp * 30 // 100, 1)
        assert cs.player.powers["reptile_trinket"].amount == 3

    def test_entropic_brew_can_roll_the_out_of_combat_only_potions(self):
        # EntropicBrew.cs:23 calls CreateRandomPotionOutOfCombat on purpose,
        # so the three CanBeGeneratedInCombat=false potions ARE reachable.
        from sts2_rl.potion_pools import (
            POTION_POOL, legacy_random_potion_out_of_combat,
        )
        rng = random.Random(0)
        ids = {
            legacy_random_potion_out_of_combat(rng, POTION_POOL).id
            for _ in range(400)
        }
        assert ids & {"fruit_juice", "fairy_in_a_bottle", "regen_potion"}

    def test_entropic_brew_rolls_a_rarity_before_it_picks(self):
        # CreateRandomPotion: one NextFloat picks the bucket (Rare <= 0.1,
        # Uncommon <= 0.35, else Common), THEN one pick inside it — not a
        # uniform draw over the whole pool.
        from sts2_rl.potion_pools import POTION_POOL, legacy_random_potion_out_of_combat
        rarity = dict(POTION_POOL)
        rng = random.Random(1)
        rolled = [
            legacy_random_potion_out_of_combat(rng, POTION_POOL).id
            for _ in range(2000)
        ]
        rares = sum(1 for pid in rolled if rarity[pid] == "rare")
        assert 0.05 < rares / len(rolled) < 0.15
        commons = sum(1 for pid in rolled if rarity[pid] == "common")
        assert 0.55 < commons / len(rolled) < 0.75

    def test_shackling_potion_skips_an_unhittable_enemy(self):
        # ShacklingPotion.cs:33 applies over CombatState.HittableEnemies.
        # PowerCmd.apply's should_allow_hitting backstop (cmds.py:381) is what
        # enforces the ShouldAllowHitting half today; `not is_gone` covers the
        # IsDead half.
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.overgrowth.fogmog import EyeWithTeeth

        cs = CombatState(rng=random.Random(0),
                         potions=[make_potion("shackling_potion")],
                         encounter=Encounter("pin_illusion", [EyeWithTeeth]))
        enemy = cs.enemies[0]
        enemy.hp = 1
        enemy.powers["illusion"].is_reviving = True
        assert cs.use_potion(0)
        assert "shackling_potion" not in enemy.powers


class TestOnUseWrapper:
    """PotionModel.OnUseWrapper (PotionModel.cs:291-342) is one pipeline for
    every potion, and it was covered by no seam record until 2026-07-29
    (potion/_use_pipeline).  These pin the three dispatches the sim used to
    skip, in the source's order: :297 BeforePotionUsed, :324-331 the
    Begin/EndCardOrPotionEffect bracket, :340 CheckForEmptyHand."""

    def test_check_for_empty_hand_runs_after_the_use(self):
        # PotionModel.cs:340 -- the hand is tested AFTER the effect, so any
        # potion can trigger it.  Unceasing Top (UnceasingTop.cs:16,
        # AfterHandEmptied) is the sole implementer; the record's own witness
        # is a Block Potion used on an already-empty hand.
        from sts2_rl.relics import UnceasingTop

        cs = CombatState(rng=random.Random(0), relics=[UnceasingTop()],
                         potions=[make_potion("block_potion")])
        cs.player.hand = []
        assert cs.use_potion(0)
        assert len(cs.player.hand) == 1

    def test_before_potion_used_precedes_the_effect(self):
        # Hook.BeforePotionUsed (:297) fires BEFORE OnUse (:327).  Its one C#
        # implementer is SurroundedPower.cs:82, so a targeted potion thrown at
        # the far Kaiser Crab arm turns the player to face it first.
        seen: list[str] = []

        class _Spy:
            id = "spy"

            def before_potion_used(self, potion, target):
                seen.append("before")

            def on_potion_used(self, potion, target):
                seen.append("after")

        cs = CombatState(rng=random.Random(0),
                         potions=[make_potion("block_potion")])
        spy = _Spy()
        cs.hooks.register(spy)
        assert cs.use_potion(0)
        assert seen == ["before", "after"]

    def test_the_effect_bracket_defers_the_empty_hand_check(self):
        # CombatManager.cs:889's `!IsExecutingCardOrPotionEffect(player)`:
        # a potion body that empties the hand must NOT trigger the check
        # until PotionModel.cs:331's `finally` releases the bracket.
        from sts2_rl.relics import UnceasingTop

        cs = CombatState(rng=random.Random(0), relics=[UnceasingTop()],
                         potions=[make_potion("block_potion")])
        cs.player.hand = []
        depth_seen = []
        with cs._card_or_potion_effect():
            cs._check_for_empty_hand()
            depth_seen.append(len(cs.player.hand))
        assert depth_seen == [0]      # suppressed inside the bracket
        cs._check_for_empty_hand()
        assert len(cs.player.hand) == 1
