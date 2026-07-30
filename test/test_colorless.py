"""Tests for the Colorless card pool (sts2_rl/cards/colorless_*.py), its
powers, and the shop's Colorless section.

Run with:  python -m pytest test/test_colorless.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import (
    COLORLESS_POOL,
    CardRarity,
    CardType,
    make_card,
    transform_options_in_combat,
)
from sts2_rl.cards.base import _CARD_CLASSES
from sts2_rl.cards.pool import IRONCLAD_POOL
from sts2_rl.cmds import BlockCmd, DrawCmd
from sts2_rl.powers import VulnerablePower, WeakPower
from sts2_rl.run import RunState
from sts2_rl.shop import MerchantInventory


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0, **kwargs) -> CombatState:
    """Fresh combat with a fixed RNG seed (9-card starter deck, one Fuzzy
    Wurm at 55–57 HP)."""
    return CombatState(rng=random.Random(seed), **kwargs)


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    """Give the player `card`, plenty of energy, and play it."""
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ══════════════════════════════════════════════════════════════════════════
# The pool itself
# ══════════════════════════════════════════════════════════════════════════

class TestColorlessPool:
    def test_pool_is_the_single_player_slice(self):
        # 64 cards in ColorlessCardPool.cs minus the 11 multiplayer-only ones.
        assert len(COLORLESS_POOL) == 53
        assert len(set(COLORLESS_POOL)) == 53

    def test_every_pool_card_is_registered_and_uncommon_or_rare(self):
        for cid in COLORLESS_POOL:
            cls = _CARD_CLASSES[cid]
            assert cls.rarity in (CardRarity.UNCOMMON, CardRarity.RARE), cid

    def test_ultimate_cards_are_in_the_pool(self):
        assert "ultimate_strike" in COLORLESS_POOL
        assert "ultimate_defend" in COLORLESS_POOL

    def test_combat_generation_excludes_flagged_cards(self):
        from sts2_rl.cards import pool_card_ids

        ids = pool_card_ids(pool=COLORLESS_POOL)
        for banned in ("alchemize", "hand_of_greed", "hidden_gem"):
            assert banned not in ids

    def test_quest_cards_transform_into_colorless(self):
        options = transform_options_in_combat(make_card("byrdonis_egg"), IRONCLAD_POOL)
        assert options and all(cid in COLORLESS_POOL for cid in options)

    def test_colorless_cards_transform_within_the_pool(self):
        options = transform_options_in_combat(make_card("finesse"), IRONCLAD_POOL)
        assert "finesse" not in options
        assert options and all(cid in COLORLESS_POOL for cid in options)

    def test_ironclad_cards_transform_within_ironclad(self):
        options = transform_options_in_combat(make_card("bludgeon"), IRONCLAD_POOL)
        assert all(cid not in COLORLESS_POOL for cid in options)


# ══════════════════════════════════════════════════════════════════════════
# Attacks
# ══════════════════════════════════════════════════════════════════════════

class TestColorlessAttacks:
    def test_flash_of_steel_damages_and_draws(self):
        cs = fresh()
        hp = cs.enemy.hp
        hand = len(cs.player.hand)
        play(cs, make_card("flash_of_steel"))
        assert cs.enemy.hp == hp - 5
        assert len(cs.player.hand) == hand + 1

    def test_fisticuffs_blocks_for_unblocked_damage(self):
        cs = fresh()
        play(cs, make_card("fisticuffs"))
        assert cs.player.block == 7

    def test_fisticuffs_blocks_for_fully_blocked_damage_too(self):
        # MOVED 2026-07-29 (round 7, card/fisticuffs/OnPlay). It used to be
        # `test_fisticuffs_gains_no_block_when_fully_blocked` and assert 0,
        # which encoded the sim's old reading of the block amount as the HP
        # actually removed. Fisticuffs.cs:32 sums
        # `r.TotalDamage + r.OverkillDamage`, and `TotalDamage` is
        # `BlockedDamage + UnblockedDamage` (DamageResult.cs:63) -- so an
        # attack the target's block eats entirely still grants its full amount.
        cs = fresh()
        cs.enemy.block = 20
        play(cs, make_card("fisticuffs"))
        assert cs.player.block == 7

    def test_gold_axe_scales_with_cards_played_this_combat(self):
        cs = fresh()
        for _ in range(3):
            play(cs, make_card("flash_of_steel"))
        hp = cs.enemy.hp
        play(cs, make_card("gold_axe"))
        assert cs.enemy.hp == hp - 3

    def test_mind_blast_deals_draw_pile_count(self):
        cs = fresh()
        hp = cs.enemy.hp
        pile = len(cs.player.draw_pile)
        play(cs, make_card("mind_blast"))
        assert cs.enemy.hp == hp - pile

    def test_mind_blast_is_innate(self):
        deck = [make_card("strike") for _ in range(8)] + [make_card("mind_blast")]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        assert any(c.id == "mind_blast" for c in cs.player.hand)

    def test_rend_scales_with_target_debuffs(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, 2, applier=cs.player)
        hp = cs.enemy.hp
        play(cs, make_card("rend"))
        assert cs.enemy.hp == hp - 20  # 15 + 5 × 1 debuff

    def test_salvo_and_equilibrium_retain_the_hand(self):
        cs = fresh()
        play(cs, make_card("salvo"))
        kept = list(cs.player.hand)
        assert kept
        cs.end_turn()
        for card in kept:
            assert card in cs.player.hand

    def test_bolas_returns_to_hand_next_turn(self):
        # In the deck from the start so the card is a registered hook
        # listener (the engine registers all starting-deck cards).
        deck = [make_card("bolas")] + [make_card("defend") for _ in range(4)]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        bolas = next(c for c in cs.player.hand if c.id == "bolas")
        cs.player.energy = 3
        assert cs.play_card(cs.player.hand.index(bolas))
        assert bolas in cs.player.discard_pile
        cs.end_turn()
        assert bolas in cs.player.hand

    def test_thrumming_hatchet_returns_only_if_played(self):
        deck = [make_card("thrumming_hatchet")] + [
            make_card("defend") for _ in range(15)
        ]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        hatchet = next(c for c in cs.player.all_cards if c.id == "thrumming_hatchet")
        if hatchet not in cs.player.hand:      # force it into the turn-1 hand
            cs.player.draw_pile.remove(hatchet)
            cs.player.hand.append(hatchet)
        cs.end_turn()   # discarded without being played
        assert hatchet not in cs.player.hand
        cs.player.energy = 3
        cs.player.hand.append(hatchet)
        cs.player.discard_pile.remove(hatchet)
        assert cs.play_card(cs.player.hand.index(hatchet))
        cs.end_turn()   # played this turn → returns
        assert hatchet in cs.player.hand

    def test_volley_hits_x_times(self):
        cs = fresh()
        hp = cs.enemy.hp
        play(cs, make_card("volley"), energy=2)
        assert cs.enemy.hp == hp - 20  # 2 hits × 10
        assert cs.player.energy == 0

    def test_dramatic_entrance_is_innate_and_exhausts(self):
        deck = [make_card("strike") for _ in range(8)] + [make_card("dramatic_entrance")]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        entrance = next(c for c in cs.player.hand if c.id == "dramatic_entrance")
        hp = cs.enemy.hp
        play(cs, entrance)
        assert cs.enemy.hp == hp - 11
        assert entrance in cs.player.exhaust_pile

    def test_alchemize_procures_on_the_combat_potion_generation_stream(self):
        """Alchemize.cs: `PotionFactory.CreateRandomPotionInCombat(owner,
        RunState.Rng.CombatPotionGeneration)` — two draws (a rarity NextFloat
        then a NextItem) on the serialized stream, over the pool minus the
        potions that cannot be generated in combat. The potion is created even
        when the belt is full (PotionCmd.TryToProcure just drops it), so the
        draws happen either way."""
        from sts2_rl.rng import RunRngSet

        rs = RunRngSet("933T39V18D")
        cs = CombatState(rng_set=rs, max_potions=2)
        before = rs.combat_potion_generation.counter
        play(cs, make_card("alchemize"))
        assert len(cs.player.held_potions) == 1
        assert rs.combat_potion_generation.counter == before + 2
        assert cs.player.potions[0].id not in (
            "fairy_in_a_bottle", "fruit_juice", "regen_potion")

        # A full belt still burns the two draws (Player.cs's belt is a
        # fixed-length list[Potion | None]; fill the remaining null slot
        # rather than appending past its length).
        assert cs.player.add_potion(cs.player.potions[0])
        before = rs.combat_potion_generation.counter
        play(cs, make_card("alchemize"))
        assert len(cs.player.held_potions) == 2
        assert rs.combat_potion_generation.counter == before + 2

    def test_hand_of_greed_banks_gold_on_kill(self):
        cs = fresh()
        cs.enemy.hp = 5
        play(cs, make_card("hand_of_greed"))
        assert cs.enemy.is_dead
        assert cs.gold_gained == 20

    def test_hand_of_greed_no_gold_without_kill(self):
        cs = fresh()
        play(cs, make_card("hand_of_greed"))
        assert cs.gold_gained == 0

    def test_hand_of_greed_gold_credits_the_run(self):
        run = fresh_run()
        run.gold = 50
        combat = run.create_combat(_wurm())
        combat.gold_gained = 20
        run.finish_combat(combat)
        assert run.gold == 70

    def test_omnislice_splashes_other_enemies(self):
        cs = fresh(encounter=_two_wurms())
        first, second = cs.enemies
        hp1, hp2 = first.hp, second.hp
        play(cs, make_card("omnislice"), target_idx=0)
        assert first.hp == hp1 - 8
        assert second.hp == hp2 - 8

    def test_seeker_strike_fetches_from_draw_pile(self):
        cs = fresh()
        hand = len(cs.player.hand)
        pile = len(cs.player.draw_pile)
        play(cs, make_card("seeker_strike"))
        assert len(cs.player.hand) == hand + 1
        assert len(cs.player.draw_pile) == pile - 1

    def test_jackpot_adds_three_zero_cost_cards(self):
        cs = fresh()
        hand = len(cs.player.hand)
        play(cs, make_card("jackpot"))
        added = cs.player.hand[hand:]
        assert len(added) == 3
        for card in added:
            assert card._energy_cost == 0 and not card.energy_cost_x


# ══════════════════════════════════════════════════════════════════════════
# Skills
# ══════════════════════════════════════════════════════════════════════════

class TestColorlessSkills:
    def test_finesse_blocks_and_draws(self):
        cs = fresh()
        hand = len(cs.player.hand)
        play(cs, make_card("finesse"))
        assert cs.player.block == 4
        assert len(cs.player.hand) == hand + 1

    def test_master_of_strategy_draws_three_and_exhausts(self):
        cs = fresh()
        hand = len(cs.player.hand)
        card = make_card("master_of_strategy")
        play(cs, card)
        assert len(cs.player.hand) == hand + 3
        assert card in cs.player.exhaust_pile

    def test_scrawl_fills_the_hand(self):
        deck = [make_card("strike") for _ in range(15)]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        play(cs, make_card("scrawl"))
        assert len(cs.player.hand) == cs.player.MAX_HAND_SIZE

    def test_production_gains_energy(self):
        cs = fresh()
        play(cs, make_card("production"), energy=0)
        assert cs.player.energy == 2

    def test_impatience_draws_only_without_attacks(self):
        cs = fresh()
        cs.player.hand = [make_card("defend")]
        cs.player.energy = 3
        cs.player.hand.append(make_card("impatience"))
        assert cs.play_card(1)
        assert len(cs.player.hand) == 3  # defend + 2 drawn

        cs2 = fresh()
        cs2.player.hand = [make_card("strike")]
        cs2.player.energy = 3
        cs2.player.hand.append(make_card("impatience"))
        assert cs2.play_card(1)
        assert len(cs2.player.hand) == 1  # just the strike

    def test_shockwave_debuffs_all_enemies(self):
        cs = fresh(encounter=_two_wurms())
        card = make_card("shockwave")
        play(cs, card)
        for enemy in cs.enemies:
            assert enemy.powers["weak"].amount == 3
            assert enemy.powers["vulnerable"].amount == 3
        assert card in cs.player.exhaust_pile

    def test_dark_shackles_is_temporary_strength_loss(self):
        cs = fresh()
        play(cs, make_card("dark_shackles"))
        assert cs.enemy.powers["strength"].amount == -9
        cs.end_turn()
        assert "strength" not in cs.enemy.powers
        assert "dark_shackles" not in cs.enemy.powers

    def test_panic_button_blocks_then_locks_card_block(self):
        cs = fresh()
        play(cs, make_card("panic_button"))
        assert cs.player.block == 30
        play(cs, make_card("defend"))
        assert cs.player.block == 30  # card block multiplied to 0

    def test_no_block_expires_after_two_enemy_side_ends(self):
        cs = fresh()
        play(cs, make_card("panic_button"))
        cs.end_turn()
        assert "no_block" in cs.player.powers
        cs.end_turn()
        assert "no_block" not in cs.player.powers

    def test_prolong_regains_block_next_turn(self):
        cs = fresh()
        BlockCmd.apply(cs.hooks, cs.player, 40)
        play(cs, make_card("prolong"))
        cs.end_turn()
        # Whatever survived the enemy turn was cleared, then regained (40).
        assert cs.player.block == 40
        assert "block_next_turn" not in cs.player.powers

    def test_the_bomb_explodes_after_three_turns(self):
        cs = fresh()
        play(cs, make_card("the_bomb"))
        cs.end_turn()
        cs.end_turn()
        hp = cs.enemy.hp
        cs.end_turn()
        assert cs.enemy.hp <= hp - 40 or cs.enemy.is_dead
        assert "the_bomb" not in cs.player.powers

    def test_the_gambit_kills_on_unblocked_hit(self):
        cs = fresh()
        play(cs, make_card("the_gambit"))
        assert cs.player.block == 50
        cs.player.block = 0
        DamageCmd.deal(cs.hooks, cs.player, 1, dealer=cs.enemy)
        assert cs.player.is_dead

    def test_the_gambit_survives_blocked_hits(self):
        cs = fresh()
        play(cs, make_card("the_gambit"))
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=cs.enemy)
        assert not cs.player.is_dead
        assert "the_gambit" in cs.player.powers

    def test_purity_exhausts_up_to_three_hand_cards(self):
        cs = fresh()
        cs.player.hand = [make_card("strike"), make_card("defend")]
        purity = make_card("purity")
        cs.player.energy = 3
        cs.player.hand.append(purity)
        assert cs.play_card(2)
        assert len(cs.player.exhaust_pile) == 3  # 2 chosen + Purity itself
        assert not cs.player.hand

    def test_restlessness_fires_only_as_last_card(self):
        cs = fresh()
        cs.player.hand = [make_card("restlessness")]
        cs.player.energy = 0
        assert cs.play_card(0)
        assert len(cs.player.hand) == 2
        assert cs.player.energy == 2

        cs2 = fresh()
        cs2.player.hand = [make_card("restlessness"), make_card("strike")]
        cs2.player.energy = 0
        assert cs2.play_card(0)
        assert len(cs2.player.hand) == 1  # no draws
        assert cs2.player.energy == 0

    def test_anointed_pulls_rares_from_draw_pile(self):
        deck = [make_card("strike") for _ in range(5)] + [
            make_card("bludgeon"), make_card("impervious")
        ]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        rares_in_draw = [c for c in cs.player.draw_pile if c.rarity == CardRarity.RARE]
        play(cs, make_card("anointed"))
        for card in rares_in_draw:
            assert card in cs.player.hand

    def test_secret_weapon_and_technique_fetch_by_type(self):
        deck = [make_card("defend") for _ in range(8)] + [make_card("bludgeon")]
        cs = CombatState(starting_deck=deck, rng=random.Random(1))
        # Make sure the attack is in the draw pile, not the opening hand.
        bludgeon = next(c for c in cs.player.all_cards if c.id == "bludgeon")
        if bludgeon in cs.player.hand:
            cs.player.hand.remove(bludgeon)
            cs.player.draw_pile.append(bludgeon)
        play(cs, make_card("secret_weapon"))
        assert bludgeon in cs.player.hand

        skill = next(
            c for c in cs.player.draw_pile if c.card_type == CardType.SKILL
        )
        play(cs, make_card("secret_technique"))
        assert skill in cs.player.hand or any(
            c.card_type == CardType.SKILL for c in cs.player.hand
        )

    def test_thinking_ahead_draws_and_tops_the_draw_pile(self):
        cs = fresh()
        hand = len(cs.player.hand)
        play(cs, make_card("thinking_ahead"))
        assert len(cs.player.hand) == hand + 1  # +2 drawn, −1 to draw top
        # The topped card is the next draw.
        top = cs.player.draw_pile[-1]
        DrawCmd.draw(cs.player, 1)
        assert cs.player.hand[-1] is top

    def test_jack_of_all_trades_adds_a_colorless_card(self):
        cs = fresh()
        hand = len(cs.player.hand)
        play(cs, make_card("jack_of_all_trades"))
        added = cs.player.hand[hand:]
        assert len(added) == 1
        assert added[0].id in COLORLESS_POOL
        assert added[0].id != "jack_of_all_trades"

    def test_discovery_adds_a_free_character_card(self):
        cs = fresh()
        hand = len(cs.player.hand)
        card = make_card("discovery")
        play(cs, card)
        added = cs.player.hand[hand:]
        assert len(added) == 1
        assert added[0].energy_cost == 0  # free this turn
        assert card in cs.player.exhaust_pile

    def test_splash_adds_a_free_attack(self):
        cs = fresh()
        hand = len(cs.player.hand)
        play(cs, make_card("splash"))
        added = cs.player.hand[hand:]
        assert len(added) == 1
        assert added[0].card_type == CardType.ATTACK
        assert added[0].energy_cost == 0

    def test_splash_upgraded_upgrades_the_options(self):
        cs = fresh()
        hand = len(cs.player.hand)
        splash = make_card("splash")
        splash.upgrade()
        play(cs, splash)
        assert cs.player.hand[hand].upgrade_level == 1

    def test_alchemize_procures_a_potion(self):
        cs = fresh()
        play(cs, make_card("alchemize"))
        assert len(cs.player.held_potions) == 1

    def test_alchemize_does_nothing_with_a_full_belt(self):
        from sts2_rl.potions import make_potion

        potions = [make_potion("fire_potion") for _ in range(3)]
        cs = fresh(potions=potions)
        play(cs, make_card("alchemize"))
        assert len(cs.player.held_potions) == 3

    def test_hidden_gem_grants_replays(self):
        cs = fresh()
        cs.player.hand = []
        strike = make_card("strike")
        cs.player.draw_pile = [strike]
        play(cs, make_card("hidden_gem"))
        assert strike.base_replay_count == 2
        hp = cs.enemy.hp
        cs.player.draw_pile.remove(strike)
        cs.player.energy = 3
        cs.player.hand.append(strike)
        assert cs.play_card(0)
        assert cs.enemy.hp == hp - 18  # 3 plays × 6

    def test_beat_down_plays_attacks_from_discard(self):
        cs = fresh()
        strikes = [make_card("strike"), make_card("strike")]
        cs.player.discard_pile.extend(strikes)
        hp = cs.enemy.hp
        play(cs, make_card("beat_down"))
        assert cs.enemy.hp == hp - 12

    def test_catastrophe_plays_from_the_draw_pile(self):
        cs = fresh()
        pile = len(cs.player.draw_pile)
        play(cs, make_card("catastrophe"))
        assert len(cs.player.draw_pile) == pile - 2

    def test_catastrophe_breaks_duplicate_ties_by_the_games_pile_order(self):
        """Catastrophe.cs shuffles `PileType.Draw.GetPile(owner).Cards` - the
        game's pile, which is stored TOP FIRST - and takes `First()`. The sim
        stores its draw pile bottom-first (top == end of the list), and
        `StableShuffle`'s stabilizing `List.Sort` leaves cards that compare
        EQUAL (same ModelId + CurrentUpgradeLevel, CardModel.cs:2242) in their
        incoming order. So feeding the sim's orientation flips which of two
        identical copies the pick lands on - and since it is the pick's
        POSITION, not its identity, that decides what is left on top of the
        pile, the very next draw diverges (933T39V18D floor_49 line 531: the
        game's Catastrophe+ took the TOP Maul, leaving Feel No Pain to be drawn
        next; the sim took a deeper Maul and drew a Maul)."""
        from sts2_rl.rng import RunRngSet

        def game_first(sim_pile, shuffle_rng):
            """Catastrophe.cs's pick, straight off the source."""
            pile = list(reversed(sim_pile))            # PileType.Draw: top first
            pile.sort(key=lambda c: (c.id.upper(), c.upgrade_level))
            for i in range(len(pile) - 1, 0, -1):      # UnstableShuffle
                j = shuffle_rng.next_int(i + 1)
                pile[i], pile[j] = pile[j], pile[i]
            return pile[0]

        rs = RunRngSet("tie-b")
        probe = RunRngSet("tie-b")                     # same stream, read ahead
        mauls = [make_card("maul") for _ in range(4)]  # identical: CompareTo ties
        cs = CombatState(starting_deck=[make_card("strike")], rng_set=rs)
        cs.player.hand, cs.player.discard_pile = [], []
        cs.player.draw_pile = list(mauls)

        first = game_first(cs.player.draw_pile, probe.shuffle)
        rest = [c for c in cs.player.draw_pile if c is not first]
        second = game_first(rest, probe.shuffle)

        play(cs, make_card("catastrophe"))
        left = [c for c in mauls if c is not first and c is not second]
        assert [id(c) for c in cs.player.draw_pile] == [id(c) for c in left]

    def test_catastrophe_picks_by_stable_shuffling_the_draw_pile(self):
        """Catastrophe.cs picks each card with
        `drawPile.Where(playable).ToList().StableShuffle(Rng.Shuffle).First()`
        — a FULL shuffle of a COPY on the Shuffle stream per card, not a single
        uniform pick. The draw count is what the conformance run compares, and a
        one-draw `choice` left the Shuffle counter hundreds short."""
        from sts2_rl.rng import RunRngSet

        rs = RunRngSet("933T39V18D")
        deck = [make_card("strike") for _ in range(12)]
        cs = CombatState(starting_deck=deck, rng_set=rs)
        n = len(cs.player.draw_pile)
        before = rs.shuffle.counter
        play(cs, make_card("catastrophe"))
        # Two picks; each shuffles the whole (shrinking) playable pile.
        assert rs.shuffle.counter - before == (n - 1) + (n - 2)
        assert len(cs.player.draw_pile) == n - 2


# ══════════════════════════════════════════════════════════════════════════
# Powers
# ══════════════════════════════════════════════════════════════════════════

class TestColorlessPowers:
    def test_automation_pays_energy_every_ten_draws(self):
        deck = [make_card("strike") for _ in range(20)]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        play(cs, make_card("automation"))
        DrawCmd.draw(cs.player, 5)      # draws 6..10 of the counter? no: 1..5
        assert cs.player.powers["automation"].cards_left == 5
        cs.end_turn()                   # next hand draw completes the 10
        assert cs.player.energy == 4    # 3 + 1

    def test_calamity_adds_an_attack_after_each_attack(self):
        cs = fresh()
        play(cs, make_card("calamity"))
        hand = len(cs.player.hand)
        play(cs, make_card("strike"))
        assert len(cs.player.hand) == hand + 1
        assert cs.player.hand[-1].card_type == CardType.ATTACK

    def test_calamity_ignores_skills(self):
        cs = fresh()
        play(cs, make_card("calamity"))
        hand = len(cs.player.hand)
        play(cs, make_card("defend"))
        assert len(cs.player.hand) == hand

    def test_entropy_transforms_a_hand_card_each_turn(self):
        cs = fresh()
        play(cs, make_card("entropy"))
        cs.end_turn()
        # One of the 5 drawn starter cards became a non-Basic card.
        assert any(c.id not in ("strike", "defend") for c in cs.player.hand)

    def test_fasten_boosts_defend_cards_only(self):
        cs = fresh()
        play(cs, make_card("fasten"))
        play(cs, make_card("defend"))
        assert cs.player.block == 9    # 5 + 4
        cs.player.block = 0
        play(cs, make_card("shrug_it_off"))
        assert cs.player.block == 8    # untagged skill: unmodified

    def test_mayhem_plays_the_top_draw_card_each_turn(self):
        deck = [make_card("strike") for _ in range(20)]
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        play(cs, make_card("mayhem"))
        hp_before = cs.enemy.hp
        cs.end_turn()
        wurm_hit = cs.player  # noqa: F841  (enemy may have attacked; check enemy hp)
        assert cs.enemy.hp <= hp_before - 6  # a strike auto-played at turn start

    def test_nostalgia_tops_the_first_attack_or_skill(self):
        cs = fresh()
        play(cs, make_card("nostalgia"))
        strike = make_card("strike")
        play(cs, strike)
        assert cs.player.draw_pile[-1] is strike
        second = make_card("strike")
        play(cs, second)
        assert second in cs.player.discard_pile

    def test_nostalgia_allowance_resets_each_turn(self):
        cs = fresh()
        play(cs, make_card("nostalgia"))
        play(cs, make_card("strike"))
        cs.end_turn()
        strike = make_card("strike")
        play(cs, strike)
        assert cs.player.draw_pile[-1] is strike

    def test_panache_fires_every_five_plays(self):
        cs = fresh()
        play(cs, make_card("panache"))
        hp = cs.enemy.hp
        for _ in range(5):
            play(cs, make_card("defend"))
        assert cs.enemy.hp == hp - 10

    def test_panache_does_not_count_itself(self):
        cs = fresh()
        play(cs, make_card("panache"))
        hp = cs.enemy.hp
        for _ in range(4):
            play(cs, make_card("defend"))
        assert cs.enemy.hp == hp

    def test_prep_time_grants_vigor_each_turn(self):
        cs = fresh()
        play(cs, make_card("prep_time"))
        cs.end_turn()
        assert cs.player.powers["vigor"].amount == 4
        hp = cs.enemy.hp
        play(cs, make_card("strike"))
        assert cs.enemy.hp == hp - 10  # 6 + 4 Vigor
        assert "vigor" not in cs.player.powers  # consumed by the attack

    def test_rolling_boulder_grows_each_turn(self):
        cs = fresh()
        play(cs, make_card("rolling_boulder"))
        hp = cs.enemy.hp
        cs.end_turn()
        dmg_turn2 = hp - cs.enemy.hp
        assert dmg_turn2 >= 5  # 5 boulder (+ possible thorns-free enemy turn)
        assert cs.player.powers["rolling_boulder"].amount == 10

    def test_stratagem_fetches_on_shuffle(self):
        cs = fresh()
        play(cs, make_card("stratagem"))
        player = cs.player
        player.discard_pile.extend(player.draw_pile)
        player.draw_pile = []
        hand = len(player.hand)
        DrawCmd.draw(player, 1)  # forces the reshuffle
        assert len(player.hand) == hand + 2  # 1 fetched + 1 drawn

    def test_stratagem_draining_the_reshuffled_pile_stops_the_draw(self):
        # If Stratagem's on-shuffle fetch empties the just-reshuffled draw
        # pile, the draw stops instead of popping an empty pile (mirrors
        # CardPileCmd.Draw re-checking after ShuffleIfNecessary).
        cs = fresh()
        play(cs, make_card("stratagem"))
        player = cs.player
        player.discard_pile[:] = [make_card("strike")]
        player.draw_pile = []
        hand = len(player.hand)
        DrawCmd.draw(player, 1)
        assert len(player.hand) == hand + 1  # the fetch; nothing left to draw
        assert not player.draw_pile and not player.discard_pile

    def test_eternal_armor_grants_plating(self):
        cs = fresh()
        play(cs, make_card("eternal_armor"))
        assert cs.player.powers["plating"].amount == 9

    def test_prowess_grants_strength_and_dexterity(self):
        cs = fresh()
        play(cs, make_card("prowess"))
        assert cs.player.powers["strength"].amount == 1
        assert cs.player.powers["dexterity"].amount == 1

    def test_the_bomb_stacks_are_independent_fuses(self):
        cs = fresh()
        play(cs, make_card("the_bomb"))
        cs.end_turn()
        play(cs, make_card("the_bomb"))
        power = cs.player.powers["the_bomb"]
        assert sorted(t for t, _ in power.bombs) == [2, 3]


# ══════════════════════════════════════════════════════════════════════════
# Upgrades (a sampling of upgrade shapes)
# ══════════════════════════════════════════════════════════════════════════

class TestColorlessUpgrades:
    @pytest.mark.parametrize("cid,attr,base,upgraded", [
        ("flash_of_steel", "_damage", 5, 8),
        ("bolas", "_damage", 3, 4),
        ("rend", "_base", 15, 18),
        ("finesse", "_block", 4, 7),
        ("panic_button", "_block", 30, 40),
        ("the_gambit", "_block", 50, 75),
        ("the_bomb", "_damage", 40, 50),
        ("shockwave", "_power_amount", 3, 5),
        ("purity", "_cards", 3, 5),
        ("master_of_strategy", "_cards", 3, 4),
    ])
    def test_numeric_upgrades(self, cid, attr, base, upgraded):
        card = make_card(cid)
        assert getattr(card, attr) == base
        card.upgrade()
        assert getattr(card, attr) == upgraded

    @pytest.mark.parametrize("cid", ["alchemize", "calamity", "mayhem",
                                     "mind_blast", "nostalgia", "automation",
                                     "stratagem"])
    def test_cost_reduction_upgrades(self, cid):
        card = make_card(cid)
        cost = card._energy_cost
        card.upgrade()
        assert card._energy_cost == cost - 1

    @pytest.mark.parametrize("cid", ["discovery", "prolong",
                                     "secret_technique", "secret_weapon",
                                     "thinking_ahead"])
    def test_exhaust_removal_upgrades(self, cid):
        card = make_card(cid)
        assert card.exhausts
        card.upgrade()
        assert not card.exhausts
        card.downgrade()
        assert card.exhausts

    @pytest.mark.parametrize("cid", ["gold_axe", "anointed", "scrawl"])
    def test_retain_gain_upgrades(self, cid):
        card = make_card(cid)
        assert not card.retain
        card.upgrade()
        assert card.retain

    @pytest.mark.parametrize("cid", ["entropy"])
    def test_innate_gain_upgrades(self, cid):
        card = make_card(cid)
        assert not card.innate
        card.upgrade()
        assert card.innate


# ══════════════════════════════════════════════════════════════════════════
# Shop — the Colorless section
# ══════════════════════════════════════════════════════════════════════════

def make_shop(seed: int = 1) -> tuple[RunState, MerchantInventory]:
    run = fresh_run(seed)
    run.start_act("overgrowth")
    run.gold = 10_000
    return run, MerchantInventory.create(run)


class TestShopColorlessSection:
    def test_two_colorless_slots_uncommon_then_rare(self):
        _, inv = make_shop()
        assert len(inv.colorless_card_entries) == 2
        uncommon, rare = inv.colorless_card_entries
        assert uncommon.card.rarity == CardRarity.UNCOMMON
        assert rare.card.rarity == CardRarity.RARE
        for entry in inv.colorless_card_entries:
            assert entry.card.id in COLORLESS_POOL
            assert not entry.on_sale

    def test_colorless_cards_cost_fifteen_percent_more(self):
        for seed in range(10):
            _, inv = make_shop(seed)
            uncommon, rare = inv.colorless_card_entries
            # base 75 × 1.15 → 86, base 150 × 1.15 → 172, then ±5% jitter.
            assert round(86 * 0.95) <= uncommon.cost <= round(86 * 1.05)
            assert round(172 * 0.95) <= rare.cost <= round(172 * 1.05)

    def test_colorless_slots_dedupe_against_each_other(self):
        for seed in range(20):
            _, inv = make_shop(seed)
            ids = [e.card.id for e in inv.card_entries]
            assert len(ids) == len(set(ids))

    def test_buying_a_colorless_card_adds_it_to_the_deck(self):
        run, inv = make_shop()
        entry = inv.colorless_card_entries[0]
        card, cost = entry.card, entry.cost
        gold = run.gold
        assert entry.purchase() is True
        assert card in run.deck
        assert run.gold == gold - cost
        assert not entry.is_stocked

    def test_all_entries_order_and_size(self):
        _, inv = make_shop()
        entries = inv.all_entries
        # 5 character + 2 colorless + 3 relics + 3 potions + removal = 14.
        assert len(entries) == 14
        assert entries[5] is inv.colorless_card_entries[0]
        assert entries[6] is inv.colorless_card_entries[1]


def _wurm():
    from sts2_rl.monsters.overgrowth import FUZZY_WURM_ENCOUNTER
    return FUZZY_WURM_ENCOUNTER


def _two_wurms():
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth import FuzzyWurmCrawler
    return Encounter(id="two_wurms", monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler])
