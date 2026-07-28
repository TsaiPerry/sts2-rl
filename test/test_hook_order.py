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
from sts2_rl.cards import StrikeCard, make_card
from sts2_rl.cmds import BlockCmd
from sts2_rl.relics import make_relic
from sts2_rl.rng import RunRngSet
from sts2_rl.run import RunState


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

    def test_thorns_reflects_even_on_killing_blow(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        cs.player.hp = 1
        enemy_hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.player.is_dead
        assert cs.enemy.hp == enemy_hp_before - 3  # C# still reflects


class TestPowerCmdOrder:
    """power_cmd audit (audit/seams/power_cmd.md): pins the ordering
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
        reason="power_cmd audit gap G1 (audit/records/seam/power_cmd.json): "
               "PowerCmd.apply's Artifact check (cmds.py:299) tests the "
               "static power_cls.power_type class attribute instead of C#'s "
               "sign-aware GetTypeForAmount(amount) (PowerModel.cs:460-471, "
               "consumed by ArtifactPower.cs:24). A negative-amount "
               "application of a Buff-typed, allow_negative power (Strength/"
               "Dexterity) is a Debuff by C#'s rule but never even reaches "
               "the sim's Artifact branch, since power_cls.power_type stays "
               "BUFF regardless of sign. This test exercises the ENEMY-side "
               "direction -- the player applying a negative-amount buff to "
               "an Artifact-holding enemy -- whose only C# sources are "
               "Malaise.cs:39 and Resonance.cs:33, neither of which is "
               "ported; porting either makes this live. The mirror-image "
               "player-side direction (a monster stealing Strength/Dexterity "
               "off an Artifact-holding player) is unreachable in principle: "
               "no relic, potion, event, or card anywhere in the game grants "
               "ArtifactPower to a player -- every ArtifactPower application "
               "site is a monster self-applying, and the one card that "
               "mentions it (Expose.cs:40-43) only removes it.",
        strict=True,
    )
    def test_artifact_blocks_negative_signed_debuff(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        # Mirrors the Malaise / Resonance shape: the player applying a
        # negative amount of a Buff-typed, allow_negative power to an enemy
        # that holds Artifact.
        PowerCmd.apply(cs.hooks, cs.enemy, DexterityPower, -3, applier=cs.player)
        assert "dexterity" not in cs.enemy.powers  # C#: Artifact blocks the steal
        assert "artifact" not in cs.enemy.powers   # and consumes its stack

    def test_restacking_a_player_debuff_does_not_rearm_skip_next_tick(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 2, applier=cs.enemy)
        vuln = cs.player.powers["vulnerable"]
        assert vuln.skip_next_tick  # first application skips its first tick
        vuln.skip_next_tick = False  # that first tick has now been consumed
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 2, applier=cs.enemy)
        assert not cs.player.powers["vulnerable"].skip_next_tick


class TestCreatureCardCmdsOrder:
    """creature_card_cmds audit (audit/seams/creature_card_cmds.md):
    pins the two seed-fact behaviours from the brief's pin table plus the
    three live gaps the seam audit found."""

    BLOCK_PIPELINE = [
        "modify_block_additive",
        "modify_block_multiplicative",
        "on_block_gained",
    ]

    def test_gain_block_hook_order(self):
        """Spec steps 12-17 (CreatureCmd.cs:642-662): the block modifiers run
        additive-then-multiplicative, and the post-gain event fires last,
        after the block has actually landed."""
        cs = fresh()
        calls = trace(cs.hooks, self.BLOCK_PIPELINE)
        gained = BlockCmd.apply(cs.hooks, cs.player, 5, card=make_card("defend"))
        assert calls == self.BLOCK_PIPELINE
        assert gained == 5 and cs.player.block == 5

    def test_card_mid_play_is_excluded_from_a_reshuffle_it_triggers(self):
        """Seed fact 1 / spec step 82 (CardPileCmd.cs:669-670): a card being
        played sits in PileType.Play, and CardPileCmd.Shuffle only ever reads
        the Draw and Discard piles (CardPileCmd.cs:870-871) -- so a reshuffle
        the card's own effect triggers must not shuffle it back into the draw
        pile. The sim models the limbo with PlayerCombatState._playing_card
        (combat.py:452-454, player.py:202-215)."""
        cs = CombatState(
            starting_deck=[make_card("strike") for _ in range(3)],
            rng_set=RunRngSet("creature-card-cmds-limbo"),
        )
        p = cs.player
        p.hand.clear()
        p.draw_pile.clear()
        p.discard_pile.clear()
        held = make_card("pommel_strike")
        p.discard_pile.extend([held, make_card("strike")])
        p._playing_card = held           # mid-OnPlay: the card is in Play limbo
        p.reshuffle_discard_into_draw()
        assert held not in p.draw_pile
        assert p.discard_pile == [held]  # it lands in its result pile after OnPlay

    def test_deck_transform_appends_at_the_end_under_parity(self):
        """Seed fact 2 / spec step 58 (CardCmd.cs:436-439): a Deck-pile
        transform calls AddInternal(replacement) with no index, and
        CardPile.AddInternal's index = -1 default appends (CardPile.cs:83-97);
        only combat-pile transforms re-insert at the original's index. Pins
        the parity path -- test_events.py::
        test_transform_replaces_in_place_with_pool_card pins the legacy
        in-place behaviour on an unseeded run."""
        run = RunState(string_seed="creature-card-cmds-transform")
        original = run.deck[0]
        replacement = run.transform_card(original)
        assert original not in run.deck
        assert run.deck[-1] is replacement
        assert run.deck.index(replacement) == len(run.deck) - 1

    def test_unpowered_card_block_still_runs_block_modifiers(self):
        cs = CombatState(rng=random.Random(0), relics=[make_relic("vambrace")])
        cs.player.block = 10
        gained = BlockCmd.apply(
            cs.hooks, cs.player, cs.player.block, card=make_card("entrench"),
            props=ValueProp.MOVE | ValueProp.UNPOWERED,
        )
        assert gained == 20  # C#: Vambrace doubles unpowered card block too

    def test_vambrace_doubles_every_block_gain_of_one_card_play(self):
        cs = CombatState(rng=random.Random(0), relics=[make_relic("vambrace")])
        card = make_card("evil_eye")
        first = BlockCmd.apply(cs.hooks, cs.player, 5, card=card)
        second = BlockCmd.apply(cs.hooks, cs.player, 5, card=card)
        assert (first, second) == (10, 10)  # C#: same CardPlay, still doubled

    # creature_card_cmds gap G3 FIXED (GAP-QUEUE.md entry 31):
    # RunState.transform_card now runs the same two deck-entry hooks
    # CardCmd.Transform runs for a Deck pile — Hook.ModifyCardBeingAddedToDeck
    # before the insert (CardCmd.cs:430) and Hook.AfterCardChangedPiles after it
    # (CardCmd.cs:447) — while keeping the append-at-deck-end position
    # (CardCmd.cs:437).
    def test_deck_transform_runs_modify_card_being_added_to_deck(self):
        run = RunState(string_seed="creature-card-cmds-egg")
        run.add_relic(make_relic("frozen_egg"))
        replacement = run.transform_card(run.deck[0], into=make_card("inflame"))
        assert replacement.upgrade_level == 1  # C#: Frozen Egg upgrades it

    @pytest.mark.xfail(
        reason="creature_card_cmds audit step 103b / guard G14 "
               "(audit/records/seam/creature_card_cmds.json): CombatState."
               "select_cards (combat.py:560-581) implements only the "
               "0-candidate arm of CardSelectCmd's guards; it has no "
               "CombatManager.IsEnding / IsOverOrEnding check, where every C# "
               "selection screen returns an empty list once the combat is over "
               "(CardSelectCmd.cs:194-199, 277-285, 382-394, 694-707). The sim "
               "guards exactly one site in this whole family -- "
               "CombatState.auto_play_card (combat.py:525). DORMANT: the sim "
               "sets Phase.COMBAT_OVER only inside _end_combat, which the "
               "card-play paths reach strictly after _resolve_card_play returns "
               "(combat.py:417-420, 554-557), so no ported select_cards caller "
               "can run with the phase already flipped; the observable effect "
               "is that an out-of-band or future combat-ending effect would "
               "still get a card handed to it.",
        strict=True,
    )
    def test_select_cards_refuses_once_the_combat_is_over(self):
        from sts2_rl.combat import Phase

        cs = fresh()
        cs.phase = Phase.COMBAT_OVER
        candidates = [make_card("strike"), make_card("defend")]
        assert cs.select_cards("exhaust", candidates, 1) == []  # C#: empty

    def test_downgrade_reapplies_the_cards_enchantment(self):
        # creature_card_cmds audit step 52: CardModel.DowngradeInternal
        # (CardModel.cs:2135-2147) re-derives the card from its canonical
        # ModelDb entry and then RE-APPLIES its decorations --
        # `AfterDowngraded(); Enchantment?.ModifyCard();
        # Affliction?.AfterApplied();`. Card.downgrade now re-runs the
        # enchantment's modify_card after the rebuild (gap queue entry 28).
        from sts2_rl.enchantments import SoulsEnchantment

        card = make_card("discovery")
        assert card.exhausts
        SoulsEnchantment().attach(card)
        assert not card.exhausts
        card.upgrade()
        card.downgrade()
        assert not card.exhausts  # C#: Souls' ModifyCard runs again

    def test_dense_vegetation_rest_fires_the_rest_site_heal_hooks(self):
        # creature_card_cmds audit step 38a: PlayerCmd.MimicRestSiteHeal
        # (PlayerCmd.cs:264-274) delegates to HealRestSiteOption.
        # ExecuteRestSiteHeal (HealRestSiteOption.cs:106-113), which heals and
        # THEN fires Hook.AfterRestSiteHeal(player, isMimicked) and
        # Hook.ModifyRestSiteHealRewards. Its one gameplay caller,
        # Events/DenseVegetation.cs:90, is ported, so Dense Vegetation's Rest
        # takes RunState.rest_heal + rest_heal_rewards like a real rest.
        from sts2_rl.events.dense_vegetation import DenseVegetation

        run = RunState(string_seed="creature-card-cmds-rest")
        run.add_relic(make_relic("stone_humidifier"))
        run.hp = max(1, run.max_hp - 40)
        before_max = run.max_hp
        rest = next(o for o in DenseVegetation(run).initial_options()
                    if o.key == "REST")
        rest.on_chosen()
        assert run.max_hp == before_max + 5  # C#: Stone Humidifier fires


class TestTurnStructureOrder:
    """turn_structure audit (audit/seams/turn_structure.md,
    audit/records/seam/turn_structure.json): pins the whole end_turn hook pipeline
    plus the seam's eleven pinnable live gaps."""

    # Every turn-lifecycle hook one CombatState.end_turn touches, in the
    # order the sim fires them. Deliberately excludes the damage-pipeline
    # hooks the enemy's attack runs through (damage_pipeline's seam) and
    # on_shuffle (creature_card_cmds').
    TURN_HOOKS = [
        "should_take_extra_turn", "on_player_turn_end",
        "should_ethereal_trigger", "on_card_exhausted", "should_flush_hand",
        "on_card_discarded", "on_hand_emptied", "after_player_turn_end",
        "should_clear_block", "on_block_cleared", "on_enemy_turn_start",
        "on_enemy_turn_end", "on_enemy_side_end", "modify_max_energy",
        "should_reset_energy", "on_energy_reset", "on_player_turn_start",
        "modify_hand_draw", "should_draw", "on_card_drawn",
        "on_player_turn_started",
    ]

    def test_end_turn_hook_sequence(self):
        """The complete ordered turn pipeline, spec steps 42-74 then 5-29
        (CombatManager.cs). Reading the assertion top to bottom:

        - the extra-turn predicate is consulted LAST, in
          SwitchFromPlayerToEnemySide (spec step 65) -- it used to be tested
          first, which short-circuited this whole pipeline (gap G3, fixed);
        - Hook.BeforeTurnEnd (step 48) -> DoTurnEnd's ethereal pass (step 53,
          Dazed) -> the turn-end-in-hand effect and its discard (step 54,
          Burn) -> ShouldFlush (step 61) -> the flush (step 62) -> the
          player-side Hook.AfterTurnEnd (step 64, the Parrying Shield slot,
          AFTER the flush);
        - the enemy side (steps 30-39): block clear, per-enemy turn start,
          per-enemy turn end, then ONE side-end (where Vulnerable/Weak/Frail
          tick, step 39);
        - the next player turn's setup (steps 12-23): block clear -> energy
          (modify_max_energy, ShouldPlayerResetEnergy, AfterEnergyReset) ->
          BeforeHandDraw -> ModifyHandDraw -> the 5-card draw ->
          AfterPlayerTurnStart.

        The hand is seeded so the ethereal pass and the turn-end-in-hand pass
        are both exercised: Dazed is Ethereal with no turn-end effect, Burn
        has a turn-end effect, Strike is an ordinary card that flushes."""
        cs = fresh()
        p = cs.player
        p.hand.clear()
        p.hand.extend([make_card("dazed"), make_card("burn"),
                       make_card("strike")])
        p.block = 7                      # absorbs Burn, so nobody dies
        cs.enemies[0].block = 5          # so the enemy's clear is visible
        p.draw_pile.clear()
        p.discard_pile.clear()
        p.draw_pile.extend([make_card("strike") for _ in range(8)])
        calls = trace(cs.hooks, self.TURN_HOOKS)
        cs.end_turn()
        assert calls == [
            # --- the player's end of turn -------------------------------
            "on_player_turn_end",         # step 48  Hook.BeforeTurnEnd
            "should_ethereal_trigger",    # step 52  hand partition (Dazed)
            "on_card_exhausted",          # step 53  ethereal pass
            "on_card_discarded",          # step 54  Burn -> Discard
            "should_flush_hand",          # step 61  Hook.ShouldFlush
            "on_card_discarded",          # step 62  the flush (Strike)
            "on_hand_emptied",            # (sim-only here -- gap G16)
            "after_player_turn_end",      # step 64  Hook.AfterTurnEnd
            "should_take_extra_turn",     # step 65  SwitchFromPlayerToEnemySide
            # --- the enemy side -----------------------------------------
            "should_clear_block",         # step 13  the enemy's clear
            "on_block_cleared",           # step 14
            "on_enemy_turn_start",        # (sim-only per-enemy -- gap G5)
            "on_enemy_turn_end",          # (sim-only per-enemy -- gap G5)
            "on_enemy_side_end",          # step 39  V/W/F tick down here
            # --- the next player turn's setup ---------------------------
            "should_clear_block",         # step 13  the player's clear
            "on_block_cleared",           # step 14
            "modify_max_energy",          # step 17  Hook.ModifyMaxEnergy
            "should_reset_energy",        # step 17  ShouldPlayerResetEnergy
            "on_energy_reset",            # step 18  Hook.AfterEnergyReset
            "on_player_turn_start",       # step 19  Hook.BeforeHandDraw
            "modify_hand_draw",           # step 20  Hook.ModifyHandDraw
            "should_draw", "on_card_drawn",
            "should_draw", "on_card_drawn",
            "should_draw", "on_card_drawn",
            "should_draw", "on_card_drawn",
            "should_draw", "on_card_drawn",   # step 22  the 5-card draw
            "on_player_turn_started",     # steps 22/23 AfterPlayerTurnStart
        ]

    def test_enemy_side_is_interleaved_per_enemy(self):
        """Gap G5, pinned as a PASSING trace of the sim's current (divergent)
        order so that fixing it has to come here and change this deliberately.
        C# runs three complete passes over every participant before any enemy
        acts (BeforeTurnStart 449-455, AfterTurnStart/ClearBlock 492-499,
        AfterBlockCleared 500-507), then ONE Hook.AfterSideTurnStart (522),
        then the moves (1072-1090), then ONE Hook.BeforeTurnEnd (1251) and ONE
        Hook.AfterTurnEnd (1256) -- i.e. [clear1, clear2, cleared1, cleared2,
        SideTurnStart, move1, move2, BeforeTurnEnd, AfterTurnEnd]. The sim
        brackets each enemy individually and has no side-start slot at all."""
        from sts2_rl.monsters import Encounter, FuzzyWurmCrawler

        cs = CombatState(
            rng=random.Random(0),
            encounter=Encounter(id="two_crawlers",
                                monster_classes=[FuzzyWurmCrawler,
                                                 FuzzyWurmCrawler]),
        )
        for e in cs.enemies:
            e.block = 5
        calls = trace(cs.hooks, ["should_clear_block", "on_block_cleared",
                                 "on_enemy_turn_start", "on_enemy_turn_end",
                                 "on_enemy_side_end"])
        cs._run_enemy_turns()
        assert calls == [
            "should_clear_block", "on_block_cleared",
            "on_enemy_turn_start", "on_enemy_turn_end",
            "should_clear_block", "on_block_cleared",
            "on_enemy_turn_start", "on_enemy_turn_end",
            "on_enemy_side_end",
        ]

    def test_block_clear_event_fires_even_when_prevented(self):
        from sts2_rl.powers import BarricadePower

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("horn_cleat")])
        PowerCmd.apply(cs.hooks, cs.player, BarricadePower, 1,
                       applier=cs.player)
        cs.end_turn()
        assert cs.turn == 2
        assert cs.player.block == 14  # C#: Horn Cleat fires anyway

    def test_sturdy_clamp_does_not_cap_when_it_is_not_the_preventer(self):
        from sts2_rl.powers import BarricadePower

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("sturdy_clamp")])
        PowerCmd.apply(cs.hooks, cs.player, BarricadePower, 1,
                       applier=cs.player)
        cs.player.block = 30
        cs.player.start_turn()
        assert cs.player.block == 30  # C#: Barricade is the preventer

    def test_extra_turn_still_runs_the_turn_end_pipeline(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("paels_eye")])
        calls = trace(cs.hooks, ["should_take_extra_turn", "on_extra_turn",
                                 "on_player_turn_end", "should_flush_hand",
                                 "after_player_turn_end"])
        cs.end_turn()
        assert calls == [
            "on_player_turn_end",     # C#: Hook.BeforeTurnEnd still runs
            "should_flush_hand",      # C#: FlushPlayerHand still runs
            "after_player_turn_end",  # C#: Hook.AfterTurnEnd still runs
            # The predicate is evaluated inside SwitchFromPlayerToEnemySide
            # (CombatManager.cs:1364-1368), i.e. AFTER both end-turn phases --
            # not before them. This pin originally listed it first, which was
            # the sim's old position rather than the game's; the gap entry's own
            # text ("after both end-turn phases have run") is the authority and
            # the source agrees.
            "should_take_extra_turn",
            "on_extra_turn",          # C#: AfterTakingExtraTurn, last
        ]

    def test_no_flush_still_credits_the_end_of_turn_hand_events(self):
        cs = CombatState(rng=random.Random(1),
                         relics=[make_relic("joss_paper"),
                                 make_relic("runic_pyramid")])
        p = cs.player
        p.hand.clear()
        p.hand.extend([make_card("dazed") for _ in range(5)])  # 5 Ethereal
        p.draw_pile.clear()
        p.discard_pile.clear()
        p.draw_pile.extend([make_card("strike") for _ in range(20)])
        cs.end_turn()
        # C#: the 5 ethereal exhausts are credited at the player's turn end,
        # Joss Paper draws its 1 card, and the next hand is 5 + 1.
        assert len(p.hand) == 6

    def test_player_block_is_not_cleared_on_turn_one(self):
        cs = fresh()
        cs.player.block = 10
        # PlayerCombatState._first_turn is the sim's TurnNumber == 1 marker;
        # CombatState.__init__ already consumed it at combat.py:209.
        cs.player._first_turn = True
        cs.player.start_turn()
        assert cs.player.block == 10  # C#: turn 1 never clears

    def test_end_of_turn_auto_plays_run_before_turn_end_hooks(self):
        """turn_structure gap G8's observable, which now holds -- but only
        because gap G2 was closed and powers dispatch before relics, so
        Stampede's auto-plays land before Cloak Clasp counts the hand.

        C#'s guarantee is stronger and does not depend on listener order:
        end-of-turn auto-plays get their own phase (Phase = AutoPostPlay,
        Hook.AfterAutoPostPlayPhaseEntered, Phase = End) entered strictly
        before Hook.BeforeTurnEnd (CombatManager.cs:1160-1180). The sim still
        has neither phase, so a *relic* that auto-played and a *power* that
        counted the hand would still come out wrong. G8's mechanism is open;
        this assertion is its observable, not its proof.
        """
        from sts2_rl.powers import StampedePower

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("cloak_clasp")])
        PowerCmd.apply(cs.hooks, cs.player, StampedePower, 2,
                       applier=cs.player)
        assert len(cs.player.hand) == 5
        # AutoPostPlay is a real STEP now, entered strictly before BeforeTurnEnd
        # (CombatManager.cs:1160-1176), so the guarantee no longer depends on
        # which listener category each of the two happens to be.
        cs.hooks.after_auto_post_play_phase_entered(cs.player)
        assert len(cs.player.hand) == 3     # the phase drained the auto-plays
        cs.hooks.on_player_turn_end(cs.player)
        # Cloak Clasp counts the 3 cards left.
        assert cs.player.block == 3

    def test_orichalcum_snapshots_block_before_other_turn_end_listeners(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("cloak_clasp"),
                                 make_relic("orichalcum")])
        hand = len(cs.player.hand)
        assert cs.player.block == 0
        cs.hooks.on_player_turn_end(cs.player)
        # C#: Orichalcum latched "no block" before Cloak Clasp ran.
        assert cs.player.block == hand + 6

    def test_turn_one_setup_death_ends_the_combat(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("royal_poison")],
                         current_hp=4, max_hp=80)
        assert cs.player.is_dead      # the 4 HP loss landed
        assert cs.is_over             # C#: CheckWinCondition ends it here

    def test_imbued_card_starts_at_the_bottom_of_the_draw_pile(self):
        from sts2_rl.enchantments import make_enchantment

        deck = [make_card("strike") for _ in range(9)]
        imbued = make_card("defend")
        make_enchantment("imbued").attach(imbued)
        deck.append(imbued)
        cs = CombatState(starting_deck=deck, rng=random.Random(0))
        # C#: Imbued sat at the bottom, so all 5 drawn cards are Strikes and
        # the auto-play comes out of the draw pile.
        assert len(cs.player.hand) == 5

    def test_joss_paper_credits_a_mid_turn_ethereal_exhaust_at_once(self):
        from sts2_rl.cmds import ExhaustCmd

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("joss_paper")])
        p = cs.player
        p.hand.clear()
        p.draw_pile.clear()
        p.discard_pile.clear()
        p.draw_pile.extend([make_card("strike") for _ in range(20)])
        # Four ordinary (non-Ethereal) exhausts: Joss Paper is now at 4.
        for _ in range(4):
            c = make_card("strike")
            p.hand.append(c)
            ExhaustCmd.exhaust(cs.hooks, p, c)
        assert not p.hand
        # Apparition exhausts itself on play. C#: causedByEthereal is FALSE
        # here, so this is the 5th exhaust and Joss Paper draws right now.
        app = make_card("apparition")
        p.hand.append(app)
        cs.play_card(p.hand.index(app))
        assert len(p.hand) == 1  # C#: the Joss Paper draw landed this turn

    def test_paels_eye_ignores_auto_plays(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("paels_eye")])
        card = make_card("defend")
        cs.player.hand.append(card)
        cs.auto_play(card)            # what Imbued does on turn 1
        # C#: IsAutoPlay plays are excluded, so Pael's Eye still fires.
        assert cs.hooks.should_take_extra_turn(cs.player)


def listener_categories(hooks):
    """The category of every listener on `hooks`, in dispatch order.

    Every HookSystem dispatcher walks `self._each(...)`, which walks
    `_ordered()` (hooks.py), so that list IS the sim's cross-listener ordering
    rule made visible. Categories mirror the five kinds C#'s
    CombatState.IterateHookListeners walks, plus the sim-only CombatHistory
    (hook_dispatch note N3).
    """
    from sts2_rl.cards.base import Card
    from sts2_rl.enchantments import Enchantment
    from sts2_rl.history import CombatHistory
    from sts2_rl.potions import Potion
    from sts2_rl.powers import Power
    from sts2_rl.relics.base import Relic

    kinds = [(CombatHistory, "history"), (Enchantment, "enchantment"),
             (Card, "card"), (Relic, "relic"), (Potion, "potion"),
             (Power, "power")]
    out = []
    for listener in hooks._ordered():
        out.append(next((name for cls, name in kinds
                         if isinstance(listener, cls)),
                        type(listener).__name__))
    return out


class TestHookDispatchOrder:
    """hook_dispatch audit (audit/seams/hook_dispatch.md,
    audit/records/seam/hook_dispatch.json): pins the cross-listener ordering rule the
    sim actually implements plus the seam's four pinnable gaps.

    The sim's rule is "registration order over one flat list"; the game's is a
    structural per-creature walk (CombatState.cs:413-467). The two are close to
    reversed, which is what gap G2 records.
    """

    @staticmethod
    def _probe(hooks, hook_name):
        """Replace `hook_name` on every current listener with a recorder.

        `trace` (above) wraps the HookSystem's own methods, which shows WHICH
        hooks fired and in what order; this shows WHICH LISTENERS a single
        dispatch visits and in what order, which is the thing this seam is
        about. The recorder replaces rather than wraps, so no real listener
        effect runs -- the combat is a throwaway either way.
        """
        seen = []

        for listener in hooks._listeners:
            def rec(*a, _l=listener, **k):
                seen.append(_l)
            setattr(listener, hook_name, rec)
        return seen

    def test_dispatch_order_is_the_games_derived_per_creature_walk(self):
        """Spec steps 41-44 and gap G2, now closed.

        `CombatState.IterateHookListeners` (CombatState.cs:410-493) builds no
        list: it re-derives the listeners per dispatch from the creatures
        themselves, allies before enemies, and within a player walks Powers
        (416) -> Relics (428-435) -> PotionSlots (436-443) -> Orbs (448) ->
        the cards of AllPiles (449-467). `HookSystem._ordered` sorts the
        registration-order `_listeners` into exactly that, with registration
        order as the tie-break inside one (creature, category) pair -- which is
        what keeps an enchantment immediately after its own card. The sim-only
        CombatHistory (note N3) has no C# counterpart and stays ahead of the
        walk, so an entry exists when anything reacts to it.

        Both halves are asserted: the derived composition, and that a real
        dispatch visits exactly that sequence -- the second is what makes this
        a pin on dispatch rather than on a data structure.
        """
        from sts2_rl.potions import make_potion

        cs = CombatState(
            rng=random.Random(0),
            relics=[make_relic("pen_nib"), make_relic("orichalcum")],
            potions=[make_potion("block_potion")],
        )
        # 9 starting cards (5 Strike + 4 Defend), none enchanted.
        assert len(cs.player.all_cards) == 9
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3, applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2,
                       applier=cs.player)

        # Registration order is unchanged -- it is the tie-break input, not the
        # dispatch rule.
        assert [type(l).__name__ for l in cs.hooks._listeners][:1] == \
            ["CombatHistory"]

        # The player's whole walk (powers, relics, potions, cards), then the
        # enemy's.
        expected = (["history", "power", "relic", "relic", "potion"]
                    + ["card"] * 9 + ["power"])
        assert listener_categories(cs.hooks) == expected

        # ...and a dispatch really does visit them in that order.
        visited = self._probe(cs.hooks, "on_combat_start")
        cs.hooks.on_combat_start()
        assert visited == cs.hooks._ordered()

        # The enemy's Vulnerable is last: enemies come after allies, and it is
        # the only listener that enemy owns.
        from sts2_rl.powers import Power
        last = cs.hooks._ordered()[-1]
        assert isinstance(last, Power)
        assert last.owner is cs.enemy

    def test_powers_modify_energy_cost_before_relics_do(self):
        from sts2_rl.powers import CuriousPower

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("spiked_gauntlets")])
        PowerCmd.apply(cs.hooks, cs.player, CuriousPower, 2, applier=cs.player)
        power_card = make_card("inflame")
        assert power_card.energy_cost == 1
        cost = cs.hooks.modify_card_energy_cost(power_card,
                                                power_card.energy_cost)
        assert cost == 1  # C#: Curious floors at 0 first, then Gauntlets +1

    def test_late_energy_cost_modifiers_run_after_early_ones(self):
        from sts2_rl.powers import FreeAttackPower, TangledPower

        cs = CombatState(rng=random.Random(0))
        strike = make_card("strike")
        cs.player.hand.clear()
        cs.player.hand.append(strike)
        # Unrelenting resolves first, then the Vine Shambler tangles the hand.
        PowerCmd.apply(cs.hooks, cs.player, FreeAttackPower, 1,
                       applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.player, TangledPower, 1, applier=cs.enemy)
        assert strike.affliction is not None      # Entangled landed
        cost = cs.hooks.modify_card_energy_cost(strike, strike.energy_cost)
        assert cost == 0  # C#: the Late pass zeroes it whatever Tangled did

    def test_free_attack_makes_a_three_cost_attack_playable(self):
        """The Late pass's observable in a real recorded run, not a synthetic
        pair.

        In 89U21BV1TZ/floor_18 the game plays UNRELENTING (command 200) and
        then BLUDGEON on the very next command (201, Vantom 101 -> 80).
        Bludgeon costs 3 and the player does not have 3 energy left: the play
        is only legal because FreeAttackPower is
        TryModifyEnergyCostInCombatLate (FreeAttackPower.cs:14) and zeroes the
        Attack's cost after every plain modifier has run. Without the Late pass
        the sim could not afford it and played a Strike instead, which is what
        made a whole conformance replay take a different trajectory.
        """
        from sts2_rl.powers import FreeAttackPower

        cs = CombatState(rng=random.Random(0))
        bludgeon = make_card("bludgeon")
        assert bludgeon.energy_cost == 3
        cs.player.hand.clear()
        cs.player.hand.append(bludgeon)
        cs.player.energy = 1                      # cannot pay the printed cost
        PowerCmd.apply(cs.hooks, cs.player, FreeAttackPower, 1,
                       applier=cs.player)
        assert cs.hooks.modify_card_energy_cost(bludgeon, bludgeon.energy_cost) == 0
        assert cs.play_card(0, target_idx=0)      # and so it is playable

    def test_before_card_played_fires_once_per_replay_iteration(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("pen_nib"),
                                 make_relic("throwing_axe")])
        nib = next(r for r in cs.relics if r.id == "pen_nib")
        cs.enemies[0].hp = 200          # survive both hits
        cs.player.hand.clear()
        cs.player.hand.append(make_card("strike"))
        cs.play_card(0)                 # Throwing Axe plays it twice
        assert nib._attacks_played == 2  # C#: one CardPlay per iteration

    @pytest.mark.xfail(
        reason="hook_dispatch audit gap G8 (audit/records/seam/hook_dispatch.json, "
               "spec steps 19-21): Hook.IterateCombatHookListeners "
               "(Hook.cs:53-63) yields NOTHING to a dispatch that begins once "
               "CombatManager.IsOverOrEnding is true, and 73 of the 147 "
               "dispatchers go through it -- the summary comment at "
               "Hook.cs:31-51 spells out that the check is made once, at "
               "enumeration start. The sim has no gate at all: combat.py flips "
               "Phase.COMBAT_OVER only inside _end_combat and no dispatcher "
               "consults the phase, so every listener still runs on the "
               "dispatch that follows the killing blow (C# additionally guards "
               "this particular call site at CardModel.cs:1957). DORMANT: "
               "every effect currently reachable on that path is combat-scoped "
               "state the combat then discards -- here Daughter of the Wind's "
               "1 Block (relics/daughter_of_the_wind.py:23-33) lands on a "
               "player whose fight is already won. The concrete trigger that "
               "would make it live is a ported listener on a guarded "
               "dispatcher that mutates RUN-level state (HP, gold, deck) from "
               "AfterCardPlayed / AfterCardDrawn / AfterCardExhausted / "
               "AfterShuffle / AfterEnergySpent; the conformance exporter is "
               "the nearer-term risk, since extra listener side effects after "
               "the deciding blow perturb the recorded combat state.",
        strict=True,
    )
    def test_no_listener_runs_after_the_combat_starts_ending(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("daughter_of_the_wind")])
        cs.enemy.hp = 1
        cs.player.hand.clear()
        cs.player.hand.append(make_card("strike"))
        block_before = cs.player.block
        cs.play_card(0)                       # the killing blow
        assert cs._all_enemies_dead()
        assert cs.player.block == block_before  # C#: nobody was dispatched to

    def test_multiplicative_damage_modifiers_chain_sequentially(self):
        from sts2_rl.powers import ShrinkPower

        cs = fresh()
        cs.enemy.hp = cs.enemy.max_hp = 9999
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2,
                       applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.player, ShrinkPower, -1, applier=cs.enemy)
        hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 20, dealer=cs.player,
                       card=StrikeCard())
        # C#: 20m * 1.5m = 30m, 30m * 0.7m = 21m.
        assert hp_before - cs.enemy.hp == 21


class TestMonsterStateMachineOrder:
    """Task 10 (`monster_state_machine`) pins.

    The spec is `audit/seams/monster_state_machine.md`; verdicts are in
    `audit/records/seam/monster_state_machine.json`. Every number a reason cites is
    reproducible from `audit/tools/state_machine_probes.py`.

    Pin-table note: the "repeat-rule enforcement" pin is already carried by
    `test/test_new_features.py::TestStateMachine` --
    `test_mawler_roar_used_at_most_once_per_combat` (USE_ONLY_ONCE +
    CANNOT_REPEAT on Mawler), `test_fogmog_branch_only_yields_legal_sequences`
    (Fogmog) and `test_use_only_once_and_cannot_repeat_weights` (both rules,
    60 transitions) -- and the "weight-vs-cooldown" pin by
    `test/test_monster_branch_audit.py` for the hand-rolled overgrowth ports.
    The two holes those leave, CAN_REPEAT_X_TIMES and the five MachineMonster
    ports, are closed here.
    """

    @staticmethod
    def _machine(cls, **fields):
        """Build a monster's machine without a combat (build_machine only
        reads ctor-set fields, which the caller supplies)."""
        obj = cls.__new__(cls)
        for k, v in fields.items():
            setattr(obj, k, v)
        return obj.build_machine()

    def test_can_repeat_x_times_blocks_the_n_plus_first_repeat(self):
        """RandomBranchState.GetStateWeight's CanRepeatXTimes arm
        (RandomBranchState.cs:142-157): a branch is blocked iff the last
        `maxTimes` logged moves are ALL that move. Covered by no existing
        test -- test_new_features.py exercises CANNOT_REPEAT and
        USE_ONLY_ONCE only -- and it is the rule the five ports in the xfail
        below drop, so the sim's correct implementation of it is pinned here.
        FossilStalker is the ported monster whose whole branch is
        CanRepeatXTimes(2) (FossilStalker.cs:58-60,
        monsters/underdocks/fossil_stalker.py:54-60)."""
        from sts2_rl.monsters.state_machine import MoveRepeatType
        from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker

        machine = self._machine(FossilStalker)
        branch = machine.states["RAND"]
        assert len(branch._branches) == 3
        for b in branch._branches:
            assert b["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES
            assert b["max_times"] == 2

        class _Owner:
            pass

        owner = _Owner()
        owner.machine = machine
        machine._performed_first_move = True
        rng = random.Random(11)
        ids = []
        for _ in range(300):
            move = machine.roll_move(owner, rng)
            machine.on_move_performed(move)
            ids.append(move.id)
        assert len(set(ids)) == 3                    # all three stay reachable
        for a, b, c in zip(ids, ids[1:], ids[2:]):   # never three in a row
            assert not (a == b == c)

    def test_a_mid_combat_spawn_rolls_its_move_exactly_once(self):
        """`creature_card_cmds` step 3 handed this record
        `PrepareForNextTurn(rollNewMove: false)` for a monster added while
        `CurrentSide != Enemy` (`CreatureCmd.cs:72-75`). Audited as step 47:
        with the flag false, `PrepareForNextTurn` (`Creature.cs:546-554`)
        reduces to `RefreshIntents()`, so the flag exists to stop that call
        re-rolling what `CombatManager.AfterCreatureAdded`
        (`CombatManager.cs:860-867`) already rolled -- C# rolls a spawn's move
        EXACTLY ONCE, never twice. The sim reaches the same property by a
        different split: `CreatureCmd.add` (`cmds.py:237-266`) never rolls and
        `MachineMonster.__init__` rolls once (`state_machine.py:300-301`).
        Pinned because nothing else asserts it and a future
        `telegraph_next_move` call inside `CreatureCmd.add` would silently
        double-roll (one extra MonsterAi draw plus a second log entry).
        Executed equivalently by `audit/tools/state_machine_probes.py
        spawn-roll`."""
        from sts2_rl.cmds import CreatureCmd
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.state_machine import MonsterMoveStateMachine
        from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker

        enc = Encounter(id="pin_spawn", monster_classes=[FossilStalker])
        cs = CombatState(rng=random.Random(5), encounter=enc)

        real = MonsterMoveStateMachine.roll_move
        calls = []

        def counting(self, owner, rng):
            calls.append(1)
            return real(self, owner, rng)

        MonsterMoveStateMachine.roll_move = counting
        try:
            spawn = FossilStalker(cs.hooks, random.Random(6))
            during_ctor = len(calls)
            CreatureCmd.add(cs.hooks, spawn)
            during_add = len(calls) - during_ctor
        finally:
            MonsterMoveStateMachine.roll_move = real

        assert during_ctor == 1                 # C#: AfterCreatureAdded's roll
        assert during_add == 0                  # C#: rollNewMove: false
        assert len(spawn.machine.state_log) == 1
        assert spawn._current_move.id == spawn.machine.current.id

    def test_addbranch_int_args_are_repeat_limits_not_weights(self):
        """monster_state_machine audit gap G1, FIXED. C#'s
        RandomBranchState.AddBranch puts cooldown-or-maxRepeats in positional
        slot 2 and NEVER a weight -- every weight is a float or Func<float>
        defaulting to 1f (RandomBranchState.cs:46-113) -- while the sim's
        add_branch puts WEIGHT there (monsters/state_machine.py:160-167), so a
        positional port turned a repeat limit into a weight in five monsters
        (FlailKnight, HunterKiller, ScrollOfBiting, SpectralKnight,
        FakeMerchantMonster). All five are re-expressed against the C# overload
        table; the per-monster pins live in
        test/test_monster_branch_audit.py::TestAddBranchIntArgsAreRepeatLimits
        and audit/tools/state_machine_probes.py mismatch now reports 0."""
        from sts2_rl.monsters.hive.flail_knight import FlailKnight
        from sts2_rl.monsters.state_machine import MoveRepeatType

        branch = self._machine(FlailKnight).states["RAND"]
        by_id = {b["state_id"]: b for b in branch._branches}
        for move_id in ("FLAIL_MOVE", "RAM_MOVE"):
            b = by_id[move_id]
            # FlailKnight.cs:50-51 -> overload #9 (:105) -> #7 (:95) -> #3
            # (:75) -> #2 (:62): maxTimes 2, CanRepeatXTimes, weight 1f.
            assert b["weight"] == 1.0, move_id
            assert b["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES
            assert b["max_times"] == 2

    def test_stun_makes_the_stun_a_move_and_relogs_the_deferred_one(self):
        """monster_state_machine audit gap G4 (audit/records/seam/
        monster_state_machine.json steps 39, 40, 44), FIXED.

        Creature.StunInternal (Creature.cs:524-544) makes the stun a REAL
        move: it builds MoveState('STUNNED', stunMove, new StunIntent()) with
        FollowUpStateId = StateLog.Last().Id and
        MustPerformOnceBeforeTransitioning = true, and force-sets it
        (MonsterModel.cs:420-432). The sim's CreatureCmd.stun set a boolean,
        combat.py skipped the turn, and MachineMonster.current_intent
        special-cased it -- machine.current, machine.state_log and
        _current_move were all untouched (executed: probe stun-machine).
        Observable: because the game's post-stun roll transitions STUNNED ->
        the deferred move id, it APPENDS that id to StateLog a second time
        (MonsterMoveStateMachine.cs:76-79), which by
        RandomBranchState.cs:142-157 blocks that move's
        CanRepeatXTimes/CannotRepeat branch on the FOLLOWING roll while the
        sim still offered it -- a different enemy intent. LIVE, on the one
        route that closes end to end (probes stun-sites, whistle-route,
        stun-machine): of the sim's 8 CreatureCmd.stun call sites exactly one
        takes an EXTERNAL target, cards/whistle.py:38 (the ported Tanx Ancient
        Attack, CreatureCmd.stun with no next move); Whistle comes only from
        Tanx's Whistle (relics/tanxs_whistle.py:17) and `tanx` is in GLORY's
        ancient pool and no other act's (rooms.py:206), and Glory is the LAST
        act (run._ACTS_BY_INDEX), so the stun-reachable population is Glory's
        pools -- in which four RandomBranchState machines read the state log:
        ScrollOfBiting (scrolls_of_biting_*), FlailKnight and SpectralKnight
        (glory/knights.py:131) and SoulNexus. THIS TEST USES ScrollOfBiting,
        whose C# CHEW branch is CanRepeatXTimes(2) (ScrollOfBiting.cs:90) --
        exactly the rule the duplicate fills. Executed consequence (probe
        stun-machine, 100000 rolls, seed 7): after a Whistle stun on a CHEW
        telegraph the game's next-but-one intent is CHOMP 100% of the time and
        the sim's was CHEW 66.5% / CHOMP 33.5%. The three monsters an earlier
        pass cited here -- SlumberingBeetle, LagavulinMatriarch, TerrorEel --
        CANNOT show this observable: the first two branch on
        ConditionalBranchState (reads self.powers, never state_log) and
        TerrorEel has no branch state at all, and all three are in earlier acts
        than the Whistle.

        Fixed by MonsterMoveStateMachine.stun (state_machine.py), which
        CreatureCmd.stun now calls for a MachineMonster.
        """
        from sts2_rl.cmds import CreatureCmd
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.glory.scroll_of_biting import ScrollOfBiting

        enc = Encounter(id="pin_stun", monster_classes=[ScrollOfBiting])
        cs = CombatState(rng=random.Random(3), encounter=enc)
        mon = cs.enemies[0]
        deferred = mon._current_move.id
        log_before = [s.id for s in mon.machine.state_log]

        CreatureCmd.stun(cs.hooks, mon)
        # C#: SetMoveImmediate force-sets the synthetic STUNNED MoveState.
        assert mon.machine.current.id == "STUNNED"
        # C#: performing it, then rolling, re-logs the deferred move.
        mon.machine.on_move_performed(mon.machine.current)
        mon.machine.roll_move(mon, mon._move_rng)
        assert [s.id for s in mon.machine.state_log] == log_before + [deferred]

    def test_stun_next_move_key_reaches_a_machine_monster(self):
        """monster_state_machine audit gap G5 (audit/records/seam/
        monster_state_machine.json step 36), FIXED.

        CreatureCmd.stun's next_move_key override was gated on
        hasattr(target, '_move_key') -- _move_key is the HAND-ROLLED monsters'
        field -- so for a MachineMonster the caller's explicit next move
        evaporated with no error (executed: probe stun-machine reported
        next_move_key='LASH_MOVE' SILENTLY DROPPED). C# threads it into the
        synthetic stun state's FollowUpStateId (Creature.cs:532-541), so the
        monster resumes on exactly that move. DORMANT when audited: probe
        stun-sites enumerates all 8 sim CreatureCmd.stun call sites and
        reports exactly one passing next_move_key --
        monsters/overgrowth/ceremonial_beast.py:45 -- and CeremonialBeast is a
        hand-rolled Monster (ceremonial_beast.py:32) that does have _move_key,
        while the other three monster self-stunners (SlumberingBeetle,
        LagavulinMatriarch, TerrorEel) are MachineMonsters that passed none --
        they hand-forced the machine instead. Fixing G4 made those three pass
        the key their C# sources pass (SlumberPower.cs:29 "ROLL_OUT_MOVE",
        AsleepPower.cs:33 "SLASH_MOVE", ShriekPower.cs:30 TerrorState.StateId),
        so this is now live, ported code. Named trigger for the rest: porting
        CeremonialBeast -- or DecimillipedeSegment / TestSubject /
        WaterfallGiant, the other MustPerformOnceBeforeTransitioning users
        (CeremonialBeast.cs:150, DecimillipedeSegment.cs:155,
        TestSubject.cs:194, WaterfallGiant.cs:202) -- onto MachineMonster.

        ASSERTION UPDATED with the fix. The pin originally read
        `mon._current_move.id == "LASH_MOVE"` straight after the stun, which
        is the eager splice the sim used to do and NOT what C# does: the key
        is the SYNTHETIC state's FollowUpStateId, and SetMoveImmediate makes
        NextMove the STUNNED move itself (MonsterModel.cs:420-432). LASH_MOVE
        is "the move performed on the turn after the stunned one", exactly as
        the pin's own comment said -- which is what is asserted below.
        """
        from sts2_rl.cmds import CreatureCmd
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker

        enc = Encounter(id="pin_stun_key", monster_classes=[FossilStalker])
        cs = CombatState(rng=random.Random(3), encounter=enc)
        mon = cs.enemies[0]
        assert mon._current_move.id == "LATCH_MOVE"     # the machine's opener
        CreatureCmd.stun(cs.hooks, mon, next_move_key="LASH_MOVE")
        # C#: NextMove and the machine's current state are both the synthetic
        # stun move; the key is its FollowUpStateId.
        assert mon._current_move.id == "STUNNED"
        assert mon.machine.current.id == "STUNNED"
        # The stunned turn performs it (MonsterModel.PerformMove), and the next
        # player-turn-start roll resumes on exactly the key that was passed --
        # a branch draw would have picked among TACKLE/LATCH/LASH instead.
        mon.machine.on_move_performed(mon.machine.current)
        assert mon.machine.roll_move(mon, mon._move_rng).id == "LASH_MOVE"

    def test_flutter_stun_splice_consumes_no_shared_stream_draw(self):
        """monster_state_machine audit gap G6 (audit/records/seam/
        monster_state_machine.json steps 35, 41), FIXED.

        The machine itself was already on the right stream --
        MachineMonster._move_rng is combat_rng.monster_ai, matching
        MonsterModel.cs:417's RunRng.MonsterAi, so the brief's seed fact 'the
        sim uses the shared combat stream' is STALE. One site was not:
        FlutterPower's stun splice called machine.roll_move(self.owner,
        self.owner._rng), the SHARED combat random.Random -- executed, it was
        the only one of the sim's three machine.roll_move call sites that was
        off-stream (probe move-rng). Worse, roll_move walks all the way to a
        MoveState and so CONSUMED a branch draw, where FlutterPower.cs:47
        calls StateLog.Last().GetNextState(...), which by MoveState.cs:67-70
        is DETERMINISTIC and consumes nothing -- the game defers the branch to
        the post-stun roll. DORMANT when audited, a label that CORRECTS a
        first-pass LIVE claim that this very pin refuted by XPASSing:
        FlutterPower has exactly one applier on each side, ThievingHopper
        (monsters/hive/thieving_hopper.py:113-114; in C# only
        ThievingHopper.cs), and its machine is a pure deterministic CHAIN with
        no RandomBranchState on either side (thieving_hopper.py:61-65
        THIEVERY->FLUTTER->HAT_TRICK->NAB->ESCAPE, matching ThievingHopper.cs's
        FollowUpState assignments), so a chain roll consumes no draw from any
        stream and neither clause was observable today. Named trigger: a
        FlutterPower user whose current move's follow-up is a
        RandomBranchState -- any of the 12 resolved ported branch ports would
        do (probe mismatch). THIS TEST CONSTRUCTS THAT TRIGGER, splicing a
        branch behind FLUTTER_MOVE so the splice would have to draw, and then
        asserts it draws nothing. Cross-referenced to turn_structure's G9,
        which owns WHEN the roll happens and is a different mechanism.

        SETUP AND ASSERTIONS UPDATED with the fix, for two reasons the pin's
        own reason text names:
          - ForceCurrentState does not touch StateLog (a move is logged when a
            roll lands on it, MonsterMoveStateMachine.cs:76-79), so a bare
            force left StateLog.Last() == THIEVERY_MOVE and FlutterPower.cs:47
            would never have reached the spliced branch at all. The log entry
            below is what actually constructs the named trigger.
          - `_current_move.id in (HAT_TRICK, NAB)` immediately after the
            splice IS the eager walk this gap is about; in legacy mode
            CombatRng maps every accessor to the ONE shared random.Random
            (combat_rng.py:38-40), so no walk here can avoid the counted draw.
            The branch is asserted where C# resolves it: the post-stun roll.
        """
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.hive.thieving_hopper import ThievingHopper
        from sts2_rl.monsters.state_machine import RandomBranchState
        from sts2_rl.powers import FlutterPower

        class _Counting(random.Random):
            """Counts random() calls -- the primitive every move roll uses
            (state_machine.py:44) and that randint() does not."""

            def __init__(self, seed):
                super().__init__(seed)
                self.floats = 0

            def random(self):
                self.floats += 1
                return super().random()

        rng = _Counting(5)
        enc = Encounter(id="pin_flutter", monster_classes=[ThievingHopper])
        cs = CombatState(rng=rng, encounter=enc)
        hopper = cs.enemies[0]

        # Construct the named trigger: give FLUTTER_MOVE a RandomBranchState
        # follow-up so the splice roll MUST draw, and park the machine on it.
        machine = hopper.machine
        branch = RandomBranchState("PIN_RAND")
        branch.add_branch(machine.states["HAT_TRICK_MOVE"])
        branch.add_branch(machine.states["NAB_MOVE"])
        machine.states["PIN_RAND"] = branch
        machine.states["FLUTTER_MOVE"].follow_up = branch
        machine._performed_first_move = True
        machine.force_current_state(machine.states["FLUTTER_MOVE"])
        # ...and log it, as a roll onto FLUTTER_MOVE would have: FlutterPower
        # .cs:47 reads StateLog.Last(), not the current state.
        machine.state_log.append(machine.states["FLUTTER_MOVE"])
        hopper._current_move = machine.states["FLUTTER_MOVE"]

        PowerCmd.apply(cs.hooks, hopper, FlutterPower, 1, applier=cs.player)
        before = rng.floats
        # Flutter halves powered damage, so 10 lands as 5 -- enough for
        # on_damage_received's amount > 0 guard to consume the last stack.
        DamageCmd.deal(cs.hooks, hopper, 10, dealer=cs.player,
                       card=StrikeCard(), props=ValueProp.MOVE)
        # C#: FlutterPower.cs:47's StateLog.Last().GetNextState(...) resolves
        # through MoveState.GetNextState, which is deterministic -- the splice
        # draws nothing, off the shared stream or any other, and NextMove
        # becomes the synthetic stun move.
        assert rng.floats == before
        assert hopper._current_move.id == "STUNNED"
        # The spliced branch is resolved by the POST-STUN roll, on MonsterAi.
        hopper.machine.on_move_performed(hopper.machine.current)
        assert hopper.machine.roll_move(
            hopper, hopper._move_rng).id in ("HAT_TRICK_MOVE", "NAB_MOVE")

    @pytest.mark.xfail(
        reason="monster_state_machine audit gap G7 clause (a) (audit/records/seam/"
               "monster_state_machine.json step 21), DORMANT. C# treats "
               "CanRepeatXTimes with maxTimes == 0 as a PERMANENTLY DISABLED "
               "branch -- RandomBranchState.cs:144-147 computes n = 0, "
               "allowed = (Count < 0) ? 1 : 0 = 0, and the while-loop's "
               "num3 < num2 guard is false so nothing can revive it -- and "
               "the machine is built and played with one fewer option. The "
               "sim raises ValueError at construction instead "
               "(monsters/state_machine.py:168-169), so a faithful "
               "transliteration of such a branch would crash at combat "
               "start. DORMANT: probe cs-addbranch enumerates all 15 "
               "non-default integer arguments across the 61 monster "
               "AddBranch call sites and every one is 2 or 3 -- no shipped "
               "monster passes 0 as maxRepeats -- and probe zero-weight now "
               "builds 82 of the 83 ported machines (only _Cultist, which "
               "needs a constructor argument, is unbuilt) without tripping "
               "this ValueError, so no ported PORT passes 0 either. Named "
               "trigger: a C# monster model added with AddBranch(state, 0) "
               "or AddBranch(state, 0, weight). This same guard is why step "
               "22's apparent coverage of C#'s overload-#1 check is "
               "incidental (G8 clause c).",
        strict=True,
    )
    def test_max_times_zero_disables_the_branch_instead_of_raising(self):
        from sts2_rl.monsters.base import Intent, MoveType
        from sts2_rl.monsters.state_machine import (
            MonsterMoveStateMachine, MoveRepeatType, MoveState,
            RandomBranchState,
        )

        a = MoveState("A", lambda ctx: None, Intent(MoveType.ATTACK, damage=1))
        b = MoveState("B", lambda ctx: None, Intent(MoveType.ATTACK, damage=2))
        branch = RandomBranchState("BR")
        branch.add_branch(b)
        # C#: AddBranch(a, 0) builds a branch that simply never wins.
        branch.add_branch(a, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES,
                          max_times=0)
        for m in (a, b):
            m.follow_up = branch
        machine = MonsterMoveStateMachine([a, b, branch], b)

        class _Owner:
            pass

        owner = _Owner()
        owner.machine = machine
        machine._performed_first_move = True
        rng = random.Random(0)
        ids = {machine.roll_move(owner, rng).id for _ in range(200)}
        assert ids == {"B"}

    @pytest.mark.xfail(
        reason="monster_state_machine audit gap G8 clause (a) (audit/records/seam/"
               "monster_state_machine.json step 3; clauses (b) and (c) are "
               "steps 37 and 22, the same mechanism at two more sites and so "
               "the same verdict by rule 3), DORMANT. Every C# "
               "RegisterStates implementation is monsterStates.Add(Id, this) "
               "(RandomBranchState.cs:171, MoveState.cs:74, "
               "ConditionalBranchState.cs:58) and Dictionary.Add THROWS "
               "ArgumentException on a duplicate key, so a monster with two "
               "states sharing an id fails loudly at machine construction. "
               "The sim's states[self.id] = self "
               "(monsters/state_machine.py:86-87) silently OVERWRITES, so "
               "the second definition wins and every follow_up aimed at the "
               "first resolves to the second -- a mis-ported monster gets a "
               "quietly wrong move graph instead of a crash. DORMANT: probe "
               "zero-weight builds and fuzzes 82 ported machines over "
               "6,560,008 transitions (59 via a detached build, the other 23 "
               "via a live instance) and none collides; ONE machine, "
               "_Cultist, is still unbuildable, so dormancy is unproven for "
               "that one. Named trigger: porting a "
               "monster with a repeated state id -- Fogmog.cs:44-45 is the "
               "shipped near-miss, two distinct MoveStates (SWIPE_MOVE and "
               "SWIPE_RANDOM_MOVE) sharing one SwipeMove delegate and "
               "differing only in id.",
        strict=True,
    )
    def test_duplicate_state_id_is_rejected_at_machine_construction(self):
        from sts2_rl.monsters.base import Intent, MoveType
        from sts2_rl.monsters.state_machine import (
            MonsterMoveStateMachine, MoveState,
        )

        first = MoveState("DUP", lambda ctx: None,
                          Intent(MoveType.ATTACK, damage=1))
        second = MoveState("DUP", lambda ctx: None,
                           Intent(MoveType.ATTACK, damage=99))
        first.follow_up = first
        second.follow_up = second
        with pytest.raises((ValueError, KeyError, RuntimeError)):
            MonsterMoveStateMachine([first, second], first)

    @pytest.mark.xfail(
        reason="monster_state_machine audit gap G3 (audit/records/seam/"
               "monster_state_machine.json step 10), DORMANT. "
               "MoveState.GetNextState is (FollowUpState?.Id ?? "
               "FollowUpStateId) ?? throw (MoveState.cs:23-25, 67-70) -- the "
               "game accepts EITHER an object follow-up or a bare state id "
               "string, resolving the object first. The sim's MoveState has "
               "only follow_up: MonsterState | None "
               "(monsters/state_machine.py:116, 136-139), so a monster "
               "needing a forward reference to a state constructed later in "
               "GenerateMoveStateMachine cannot be transliterated without "
               "restructuring build_machine into two passes. DORMANT: "
               "executed, grep -rn FollowUpStateId over the game tree "
               "returns exactly two sites -- the declaration itself "
               "(MoveState.cs:23) and Creature.cs:539, the Stun path, which "
               "the sim does not model at all (gap G4) -- so no monster "
               "model uses the string form today. Named trigger: any monster "
               "model that sets FollowUpStateId on a MoveState.",
        strict=True,
    )
    def test_move_state_accepts_a_string_follow_up_id(self):
        from sts2_rl.monsters.base import Intent, MoveType
        from sts2_rl.monsters.state_machine import (
            MonsterMoveStateMachine, MoveState,
        )

        target = MoveState("TARGET", lambda ctx: None,
                           Intent(MoveType.ATTACK, damage=1))
        target.follow_up = target
        # C#: `new MoveState(...) { FollowUpStateId = "TARGET" }`.
        source = MoveState("SOURCE", lambda ctx: None, Intent(MoveType.BUFF))
        source.follow_up_id = "TARGET"
        machine = MonsterMoveStateMachine([source, target], source)

        class _Owner:
            pass

        owner = _Owner()
        owner.machine = machine
        machine._performed_first_move = True
        assert machine.roll_move(owner, random.Random(0)).id == "TARGET"


class TestPotionContentPins:
    """Content-anchored pins from the `potion` tier (audit/records/potion/**).

    Until this class landed every strict-xfail pin in this file was
    seam-anchored, so a content fix had no acceptance test of its own
    (audit/README.md's standing caveat). Each pin below names its record, the
    sim and C# sites, live-or-dormant, and the observable -- and each one
    FAILS at the assertion its reason describes rather than erroring, which is
    what stops an xfail from reading as coverage it does not provide.

    OWNERSHIP NOTE: audit/prompts/_shared-audit-contract.md reserves this file
    for the seam session. audit/prompts/2026-07-26-content-potion.md overrides
    that for this stream ("add a strict=True xfail to test/test_hook_order.py"),
    and audit/README.md already flags the snag. The pins are confined to this
    one class so the widening is easy to see and easy to move.
    """

    @staticmethod
    def _reviving_illusion_combat():
        """A combat whose only enemy is mid-Illusion-revival: alive at 1 HP,
        so `not is_gone`, but refused by should_allow_hitting."""
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.overgrowth.fogmog import EyeWithTeeth

        cs = CombatState(
            starting_deck=[make_card("strike") for _ in range(5)],
            rng=random.Random(0),
            encounter=Encounter("pin_illusion", [EyeWithTeeth]),
        )
        enemy = cs.enemies[0]
        enemy.hp = 1
        enemy.powers["illusion"].is_reviving = True
        return cs, enemy

    def test_aoe_power_potion_skips_an_unhittable_enemy(self):
        from sts2_rl.potions import PotionOfBinding

        cs, enemy = self._reviving_illusion_combat()
        PotionOfBinding().use(cs._ctx())
        assert "weak" not in enemy.powers
        assert "vulnerable" not in enemy.powers

    def test_touch_of_insanity_offers_a_globally_costed_card(self):
        from sts2_rl.potions import TouchOfInsanity

        cs = CombatState(
            starting_deck=[make_card("strike") for _ in range(5)],
            rng=random.Random(0),
            relics=[make_relic("spiked_gauntlets")],
        )
        card = make_card("inflame")          # a Power card
        card.set_free_this_turn()            # local cost 0, global cost 1
        cs.player.hand = [card]
        TouchOfInsanity().use(cs._ctx())
        # SetToFreeThisCombat == EnergyCost.SetThisCombat(0).
        assert card._cost_this_combat == 0

    def test_fairy_in_a_bottle_fires_after_potion_used(self):
        from sts2_rl.potions import FairyInABottle

        cs = CombatState(
            starting_deck=[make_card("strike") for _ in range(5)],
            rng=random.Random(0),
            potions=[FairyInABottle()],
            relics=[make_relic("reptile_trinket")],
        )
        cs.player.hp = 5
        DamageCmd.deal(cs.hooks, cs.player, 99, dealer=cs.enemy,
                       props=DamageProps.CARD)
        # The fairy prevented the death and healed to 30% of max HP...
        assert cs.player.hp == max(cs.player.max_hp * 30 // 100, 1)
        # ...and the use should have been an AfterPotionUsed for the trinket.
        assert "reptile_trinket" in cs.player.powers

    def test_foul_potion_damages_the_thrower_first(self):
        from sts2_rl.potions import FoulPotion

        cs = fresh()
        order: list[str] = []
        orig = cs.hooks.on_hp_changed

        def watch(creature, delta, _orig=orig):
            order.append("player" if creature is cs.player else "enemy")
            return _orig(creature, delta)

        cs.hooks.on_hp_changed = watch
        FoulPotion().use(cs._ctx())
        assert order, "the potion damaged nobody"
        assert order[0] == "player"
