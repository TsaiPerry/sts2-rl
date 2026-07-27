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

    @pytest.mark.xfail(
        reason="gap G1 (audit/records/seam/damage_pipeline.json): ThornsPower is "
               "wired to on_damage_received, which cmds.py's killing-blow "
               "guard skips entirely (`if not target.is_dead`). C#'s "
               "ThornsPower overrides BeforeDamageReceived (ThornsPower.cs:"
               "17-24), which CreatureCmd.Damage fires unconditionally "
               "before block/HP/death are even resolved (CreatureCmd.cs:"
               "263) -- so the real game reflects Thorns damage even on the "
               "hit that kills the Thorns-bearer.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="power_cmd audit step 20 (audit/records/seam/power_cmd.json): "
               "cmds.py:331-332 sets power.skip_next_tick = True AFTER the "
               "new-vs-stacking if/else, on the shared `power` variable the "
               "stacking branch rebinds to `existing` -- so re-applying a "
               "debuff to the player re-arms the skip on every re-stack. C# "
               "sets SkipNextDurationTick only in the new-power Apply path "
               "(PowerCmd.cs:112-117 early-returns any existing-instance "
               "application into ModifyAmount before the assignment at "
               "PowerCmd.cs:146 is ever reached); ModifyAmount "
               "(PowerCmd.cs:215-271) never touches the flag -- the only "
               "other references are PowerCmd.cs:192-194, which CONSUME it "
               "in TickDownDuration. This is LIVE and reachable with ported "
               "content: any enemy re-applying Vulnerable/Weak/Frail to the "
               "player after the first application's skip has already been "
               "consumed makes that debuff last one extra turn versus the "
               "real game.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="creature_card_cmds audit gap G1 "
               "(audit/records/seam/creature_card_cmds.json): BlockCmd.apply "
               "(cmds.py:145-147) gates the WHOLE modify_block_additive/"
               "modify_block_multiplicative dispatch on is_powered_attack "
               "(Move && !Unpowered). C#'s Hook.ModifyBlock (Hook.cs:1310-1340) "
               "calls every listener for every block gain and leaves the gate "
               "to each implementation, and Vambrace.cs:59-63 (like "
               "PaelsLegion.cs:132-134) self-gates only on "
               "IsCardOrMonsterMove() -- Move alone, ignoring Unpowered "
               "(ValuePropExtensions.cs:22-25). This is LIVE on ported "
               "content: Entrench gains block with MOVE|UNPOWERED "
               "(cards/trash_heap_cards.py:159-179, mirroring Entrench.cs:23) "
               "and Vambrace is a ported Uncommon relic, so the real game "
               "doubles Entrench's block and the sim does not.",
        strict=True,
    )
    def test_unpowered_card_block_still_runs_block_modifiers(self):
        cs = CombatState(rng=random.Random(0), relics=[make_relic("vambrace")])
        cs.player.block = 10
        gained = BlockCmd.apply(
            cs.hooks, cs.player, cs.player.block, card=make_card("entrench"),
            props=ValueProp.MOVE | ValueProp.UNPOWERED,
        )
        assert gained == 20  # C#: Vambrace doubles unpowered card block too

    @pytest.mark.xfail(
        reason="creature_card_cmds audit gap G2 "
               "(audit/records/seam/creature_card_cmds.json): the sim has no "
               "AfterModifyingBlockAmount event (CreatureCmd.cs:646, "
               "Hook.cs:649-656), so Vambrace's port hand-rolls its "
               "once-per-combat latch onto on_block_gained "
               "(relics/vambrace.py:36-40) and burns it on the FIRST block "
               "gain. C# latches only TriggeringCard = cardSource there "
               "(Vambrace.cs:78-90) and does not set BlockGainedThisCombat "
               "until AfterCardPlayed (Vambrace.cs:92-105), so every block "
               "instance of the same card play is doubled. LIVE with ported "
               "content: Evil Eye (cards/evil_eye.py:37-42) gains block twice "
               "in one play and Second Wind (cards/second_wind.py:34-39) once "
               "per exhausted non-Attack.",
        strict=True,
    )
    def test_vambrace_doubles_every_block_gain_of_one_card_play(self):
        cs = CombatState(rng=random.Random(0), relics=[make_relic("vambrace")])
        card = make_card("evil_eye")
        first = BlockCmd.apply(cs.hooks, cs.player, 5, card=card)
        second = BlockCmd.apply(cs.hooks, cs.player, 5, card=card)
        assert (first, second) == (10, 10)  # C#: same CardPlay, still doubled

    @pytest.mark.xfail(
        reason="creature_card_cmds audit gap G3 "
               "(audit/records/seam/creature_card_cmds.json): RunState.transform_card "
               "(run.py:459-469) deletes the original and appends the "
               "replacement directly instead of routing through add_card "
               "(run.py:341-354), so it skips both deck-entry hooks that C#'s "
               "CardCmd.Transform runs for a Deck pile -- "
               "Hook.ModifyCardBeingAddedToDeck (CardCmd.cs:430, the egg "
               "relics' substitution) and Hook.AfterCardChangedPiles "
               "(CardCmd.cs:447, Bing Bong / Book of Five Rings / Darkstone "
               "Periapt / Lucky Fysh). LIVE: Frozen Egg and every deck-level "
               "transformer (Pandora's Box, Astrolabe, Wood Carvings, Morphic "
               "Grove, Symbiote) are ported, so the real game hands back an "
               "upgraded Power and the sim hands back an un-upgraded one.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="creature_card_cmds audit step 52 "
               "(audit/records/seam/creature_card_cmds.json): C#'s "
               "CardModel.DowngradeInternal (CardModel.cs:2135-2147) re-derives "
               "the card from its canonical ModelDb entry and then RE-APPLIES "
               "its decorations -- `AfterDowngraded(); "
               "Enchantment?.ModifyCard(); Affliction?.AfterApplied();`. The "
               "sim's Card.downgrade (cards/base.py:150-165) rebuilds by "
               "running _init_vars() and re-applying upgrades, and never "
               "re-applies the enchantment. Discovery's _init_vars sets "
               "`self.exhausts = True` (cards/colorless_skills.py:211-213), so "
               "a Souls-enchanted Discovery (enchantments.py:209-212, from the "
               "ported Grave of the Forgotten event) silently regains its "
               "Exhaust keyword when downgraded. LIVE: every piece is ported -- "
               "the downgrade verb has two ported callers, DampenPower "
               "(powers.py:3149-3183, the Magi Knight's DAMPEN_MOVE, "
               "monsters/glory/knights.py:69-72, mirroring DampenPower.cs:35) "
               "and Reflections (events/reflections.py:36-41, mirroring "
               "Reflections.cs:43).",
        strict=True,
    )
    def test_downgrade_reapplies_the_cards_enchantment(self):
        from sts2_rl.enchantments import SoulsEnchantment

        card = make_card("discovery")
        assert card.exhausts
        SoulsEnchantment().attach(card)
        assert not card.exhausts
        card.upgrade()
        card.downgrade()
        assert not card.exhausts  # C#: Souls' ModifyCard runs again

    @pytest.mark.xfail(
        reason="creature_card_cmds audit step 38a "
               "(audit/records/seam/creature_card_cmds.json): "
               "PlayerCmd.MimicRestSiteHeal (PlayerCmd.cs:264-274) delegates to "
               "HealRestSiteOption.ExecuteRestSiteHeal "
               "(HealRestSiteOption.cs:106-113), which heals and THEN fires "
               "Hook.AfterRestSiteHeal(player, isMimicked) and "
               "Hook.ModifyRestSiteHealRewards. Its one gameplay caller, "
               "Events/DenseVegetation.cs:90, is ported -- but the sim's "
               "DenseVegetation._rest (events/dense_vegetation.py:65-68) calls "
               "run.heal(run.rest_site_heal_amount()) directly instead of "
               "RunState.rest_heal (run.py:1089-1095), so neither hook fires. "
               "LIVE: Stone Humidifier (relics/stone_humidifier.py:15-16, +5 "
               "Max HP, mirroring StoneHumidifier.cs:18-25) and Dream Catcher "
               "(relics/dream_catcher.py:22-25, a 3-card reward, mirroring "
               "DreamCatcher.cs:16-25) are both ported listeners, so the real "
               "game grants the Max HP and the reward screen on Dense "
               "Vegetation's Rest and the sim grants neither.",
        strict=True,
    )
    def test_dense_vegetation_rest_fires_the_rest_site_heal_hooks(self):
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

        - the extra-turn predicate is consulted FIRST (spec step 65 puts it
          LAST, in SwitchFromPlayerToEnemySide -- gap G3);
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
            "should_take_extra_turn",     # step 65 (sim runs it first: G3)
            "on_player_turn_end",         # step 48  Hook.BeforeTurnEnd
            "should_ethereal_trigger",    # step 52  hand partition (Dazed)
            "on_card_exhausted",          # step 53  ethereal pass
            "on_card_discarded",          # step 54  Burn -> Discard
            "should_flush_hand",          # step 61  Hook.ShouldFlush
            "on_card_discarded",          # step 62  the flush (Strike)
            "on_hand_emptied",            # (sim-only here -- gap G16)
            "after_player_turn_end",      # step 64  Hook.AfterTurnEnd
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

    @pytest.mark.xfail(
        reason="turn_structure audit gap G1 (audit/records/seam/turn_structure.json, "
               "spec step 14): C# runs the block clear and its event in TWO "
               "separate loops -- `foreach (item3 in creaturesStartingTurn) "
               "await item3.AfterTurnStart(side)` (CombatManager.cs:492-499) "
               "then `foreach (item4 in creaturesStartingTurn) await "
               "Hook.AfterBlockCleared(_state, item4)` (500-507) -- so "
               "AfterBlockCleared fires for EVERY participant, including one "
               "whose clear a ShouldClearBlock listener prevented. The sim "
               "fuses them: player.py:157-159 fires on_block_cleared only "
               "inside the `if should_clear_block(...)` arm (and "
               "combat.py:296-298 additionally gates the enemy arm on "
               "`enemy.block > 0`). LIVE: BarricadePower is a ported Ironclad "
               "Rare Power card (cards/barricade_card.py:33-34, powers.py:140) "
               "returning false from ShouldClearBlock "
               "(BarricadePower.cs), and Horn Cleat is a ported Uncommon relic "
               "listening on AfterBlockCleared (HornCleat.cs:20-27, "
               "relics/horn_cleat.py:19-22) -- so the real game still grants "
               "the turn-2 block behind Barricade and the sim grants nothing. "
               "Sturdy Clamp and Captain's Wheel are the same shape, and "
               "Anchor/Fake Anchor are caught by it because gap G6 forced them "
               "onto this hook.",
        strict=True,
    )
    def test_block_clear_event_fires_even_when_prevented(self):
        from sts2_rl.powers import BarricadePower

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("horn_cleat")])
        PowerCmd.apply(cs.hooks, cs.player, BarricadePower, 1,
                       applier=cs.player)
        cs.end_turn()
        assert cs.turn == 2
        assert cs.player.block == 14  # C#: Horn Cleat fires anyway

    @pytest.mark.xfail(
        reason="turn_structure audit gap G2 (audit/records/seam/turn_structure.json, "
               "spec step 13): Creature.ClearBlock passes the vetoing listener "
               "out of Hook.ShouldClearBlock and fires "
               "Hook.AfterPreventingBlockClear(preventer, creature) on the "
               "else-arm (Creature.cs:718-728); SturdyClamp.cs:31-46 caps the "
               "retained block at 10 there and early-returns unless `this == "
               "preventer`. sts2_rl/hooks.py has no such hook and no preventer "
               "concept, so relics/sturdy_clamp.py:27-30 caps from "
               "on_player_turn_start UNCONDITIONALLY. LIVE and proven: "
               "Hook.ShouldClearBlock returns the FIRST vetoing listener "
               "(Hook.cs:2193-2204) and CombatState.IterateHookListeners walks "
               "each creature's POWERS before that player's RELICS "
               "(CombatState.cs:412-435), so with Barricade (a ported Ironclad "
               "card) and Sturdy Clamp (a ported Rare relic) both held the "
               "preventer is BarricadePower and Sturdy Clamp's cap never runs "
               "-- the real game keeps the whole retained block where the sim "
               "trims it to 10.",
        strict=True,
    )
    def test_sturdy_clamp_does_not_cap_when_it_is_not_the_preventer(self):
        from sts2_rl.powers import BarricadePower

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("sturdy_clamp")])
        PowerCmd.apply(cs.hooks, cs.player, BarricadePower, 1,
                       applier=cs.player)
        cs.player.block = 30
        cs.player.start_turn()
        assert cs.player.block == 30  # C#: Barricade is the preventer

    @pytest.mark.xfail(
        reason="turn_structure audit gap G3 (audit/records/seam/turn_structure.json, "
               "spec step 65): combat.py:648-652 tests should_take_extra_turn "
               "at the TOP of end_turn and, on success, runs only "
               "on_extra_turn, `turn += 1` and start_turn(). C# evaluates "
               "Hook.ShouldTakeExtraTurn in SwitchFromPlayerToEnemySide "
               "(CombatManager.cs:1360-1373), i.e. AFTER "
               "EndPlayerTurnPhaseOneInternal (auto-post-play, BeforeTurnEnd, "
               "DoTurnEnd, BeforeFlush) and AFTER EndPlayerTurnPhaseTwoInternal "
               "(FlushPlayerHand, AfterFlush, EndOfTurnCleanup, AfterTurnEnd); "
               "only the ENEMY SIDE is skipped. LIVE: Pael's Eye is a ported "
               "Ancient relic granted by the Pael shrine (events/pael.py:53, "
               "PaelsEye.cs:108-137, relics/paels_eye.py:36-47), and the sim "
               "has dozens of on_player_turn_end listeners plus Parrying "
               "Shield on after_player_turn_end -- every one of which the "
               "real game still runs on an extra-turn round.",
        strict=True,
    )
    def test_extra_turn_still_runs_the_turn_end_pipeline(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("paels_eye")])
        calls = trace(cs.hooks, ["should_take_extra_turn", "on_extra_turn",
                                 "on_player_turn_end", "should_flush_hand",
                                 "after_player_turn_end"])
        cs.end_turn()
        assert calls == [
            "should_take_extra_turn",
            "on_player_turn_end",     # C#: Hook.BeforeTurnEnd still runs
            "should_flush_hand",      # C#: FlushPlayerHand still runs
            "after_player_turn_end",  # C#: Hook.AfterTurnEnd still runs
            "on_extra_turn",          # C#: AfterTakingExtraTurn, last
        ]

    @pytest.mark.xfail(
        reason="turn_structure audit gap G4 (audit/records/seam/turn_structure.json, "
               "spec steps 61-63): C#'s FlushPlayerHand treats ShouldFlush == "
               "false as 'every card is retained' and STILL runs "
               "Hook.AfterFlush and PlayerCombatState.EndOfTurnCleanup "
               "unconditionally (CombatManager.cs:1327-1346). The sim gates "
               "the whole thing -- `if self.hooks.should_flush_hand(): "
               "self.player.discard_hand()` (combat.py:661-662) -- so a false "
               "result also skips on_hand_emptied, which player.py:197 fires "
               "from inside discard_hand. LIVE through Joss Paper: its port "
               "defers Ethereal-caused exhausts and credits them from "
               "on_hand_emptied (relics/joss_paper.py:41-45), where the real "
               "Joss Paper credits them from AfterSideTurnEnd "
               "(JossPaper.cs:116), which fires whatever ShouldFlush returned. "
               "With Runic Pyramid (ported Ancient relic from the Darv shrine, "
               "events/darv.py:33, relics/runic_pyramid.py:16-17) the sim "
               "strands the credit forever and the Joss Paper draw never "
               "happens. See also gap G16 for the on_hand_emptied site itself.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="turn_structure audit gap G6 (audit/records/seam/turn_structure.json, "
               "spec step 12): Creature.AfterTurnStart returns BEFORE "
               "ClearBlock for a player whose PlayerCombatState.TurnNumber == "
               "1 (Creature.cs:681-692) -- which is what lets "
               "Hook.BeforeCombatStart grant block that survives into the "
               "first enemy turn. player.py:157-159 has no turn-1 arm. LIVE "
               "and already load-bearing: Anchor's real hook is "
               "BeforeCombatStart (Anchor.cs:19-23) and the sim had to re-wire "
               "it onto on_block_cleared to compensate "
               "(relics/anchor.py:21-24, whose docstring says so outright), as "
               "did Fake Anchor (relics/fake_anchor.py:24-29) -- and that "
               "workaround is what makes gap G1 bite both of them.",
        strict=True,
    )
    def test_player_block_is_not_cleared_on_turn_one(self):
        cs = fresh()
        cs.player.block = 10
        # PlayerCombatState._first_turn is the sim's TurnNumber == 1 marker;
        # CombatState.__init__ already consumed it at combat.py:209.
        cs.player._first_turn = True
        cs.player.start_turn()
        assert cs.player.block == 10  # C#: turn 1 never clears

    @pytest.mark.xfail(
        reason="turn_structure audit gap G8 (audit/records/seam/turn_structure.json, "
               "spec step 47): C# gives end-of-turn auto-plays their own "
               "phase -- Phase = AutoPostPlay, "
               "Hook.AfterAutoPostPlayPhaseEntered, Phase = End -- entered "
               "strictly BEFORE Hook.BeforeTurnEnd "
               "(CombatManager.cs:1160-1180). The sim has neither the phase "
               "nor the hook, so StampedePower's port fires from "
               "on_player_turn_end (powers.py:1025), the sim's BeforeTurnEnd "
               "slot, and lands in listener-registration order. LIVE: "
               "StampedePower and Cloak Clasp (a ported Rare relic gaining 1 "
               "Block per card in hand from plain BeforeSideTurnEnd, "
               "CloakClasp.cs:24, relics/cloak_clasp.py:19-24) contend "
               "directly -- the real game ALWAYS auto-plays first and lets "
               "Cloak Clasp count the reduced hand, while the sim registers "
               "relics before powers and counts the full one. The ported Howl "
               "From Beyond card (cards/howl_from_beyond.py:45) is the same "
               "shape.",
        strict=True,
    )
    def test_end_of_turn_auto_plays_run_before_turn_end_hooks(self):
        from sts2_rl.powers import StampedePower

        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("cloak_clasp")])
        PowerCmd.apply(cs.hooks, cs.player, StampedePower, 2,
                       applier=cs.player)
        assert len(cs.player.hand) == 5
        # combat.py:654 -- the sim's Hook.BeforeTurnEnd slot.
        cs.hooks.on_player_turn_end(cs.player)
        # C#: Stampede's 2 auto-plays land in AutoPostPlay first, so Cloak
        # Clasp counts the 3 cards left.
        assert cs.player.block == 3

    @pytest.mark.xfail(
        reason="turn_structure audit gap G12 (audit/records/seam/turn_structure.json, "
               "spec step 48): Hook.BeforeTurnEnd runs THREE complete listener "
               "passes in order -- BeforeSideTurnEndVeryEarly, then "
               "BeforeSideTurnEndEarly, then BeforeSideTurnEnd "
               "(Hook.cs:1238-1261) -- and Orichalcum depends on it: "
               "BeforeSideTurnEndVeryEarly snapshots `Block > 0` into "
               "ShouldTrigger (Orichalcum.cs:44-56) and BeforeSideTurnEnd then "
               "grants the 6 Block. The sim's hooks.on_player_turn_end "
               "(hooks.py:297-301) is a single listener walk, so "
               "relics/orichalcum.py:22-26 reads `player.block == 0` at "
               "whatever point registration order puts it. LIVE: Cloak Clasp "
               "is a ported Rare relic granting 1 Block per card in hand from "
               "plain BeforeSideTurnEnd (CloakClasp.cs:24, "
               "relics/cloak_clasp.py:19-24), so acquiring it before "
               "Orichalcum silently switches Orichalcum off; the real game "
               "always grants both. Fake Orichalcum and Ripple Basin are the "
               "same shape, as are the ported SandpitPower "
               "(AfterSideTurnStartLate) and DisintegrationPower "
               "(AfterSideTurnEndLate).",
        strict=True,
    )
    def test_orichalcum_snapshots_block_before_other_turn_end_listeners(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("cloak_clasp"),
                                 make_relic("orichalcum")])
        hand = len(cs.player.hand)
        assert cs.player.block == 0
        cs.hooks.on_player_turn_end(cs.player)
        # C#: Orichalcum latched "no block" before Cloak Clasp ran.
        assert cs.player.block == hand + 6

    @pytest.mark.xfail(
        reason="turn_structure audit gap G13 (audit/records/seam/turn_structure.json, "
               "spec step 27): CombatManager.cs:573 runs `await "
               "CheckWinCondition()` immediately after SetupPlayerTurn (which "
               "ends with Hook.AfterPlayerTurnStart at 675) and after the "
               "auto-pre-play phase. The sim's turn-1 setup -- "
               "`self.hooks.on_combat_start(); self.player.start_turn()` at "
               "combat.py:208-209 -- is followed by NOTHING; the only "
               "post-setup check is combat.py:681-685, on the end_turn path. "
               "LIVE: Royal Poison is a ported Event relic from the Round Tea "
               "Party event (events/round_tea_party.py:40) that deals 4 "
               "unblockable HP loss on turn 1 (RoyalPoison.cs:18-25 -> "
               "relics/royal_poison.py:25-31), so entering a combat at 4 HP or "
               "less leaves the sim in Phase.PLAYER_TURN with a dead player "
               "and a full hand of legal actions, where the real game "
               "processes the pending loss on the spot. Festive Popper and "
               "Mercury Hourglass already hand-roll a `_check_win()` call for "
               "the all-enemies-dead half of the same missing check; neither "
               "covers player death.",
        strict=True,
    )
    def test_turn_one_setup_death_ends_the_combat(self):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("royal_poison")],
                         current_hp=4, max_hp=80)
        assert cs.player.is_dead      # the 4 HP loss landed
        assert cs.is_over             # C#: CheckWinCondition ends it here

    @pytest.mark.xfail(
        reason="turn_structure audit gap G14 (audit/records/seam/turn_structure.json, "
               "spec step 21): on turn 1 CombatManager.cs:657-672 runs TWO "
               "pile moves before the draw -- every card whose enchantment "
               "sets ShouldStartAtBottomOfDrawPile goes to the BOTTOM, then "
               "every Innate card not already moved goes to the TOP. "
               "player.py:172-182 ports only the Innate half. LIVE: "
               "ShouldStartAtBottomOfDrawPile has exactly one implementer in "
               "the whole decompiled game, Imbued.cs:11, and Imbued is ported "
               "(enchantments.py:243-267) and obtainable -- Electric Shrymp is "
               "a ported relic that enchants a deck Skill with it "
               "(relics/electric_shrymp.py:17-21). The bottom-move exists so "
               "the self-auto-playing Imbued card does not occupy an "
               "opening-hand slot; without it the sim draws it like any other "
               "card and the opening hand is one card short (observed on 17 of "
               "30 seeds with a 9-Strike + 1-Imbued-Defend deck). Knock-on: "
               "the sim's Imbued only fires `if self.card in player.hand` "
               "(enchantments.py:261-266), so on the seeds where it is NOT "
               "drawn the sim never auto-plays it at all.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="turn_structure audit gap G17 (audit/records/seam/turn_structure.json, "
               "spec step 53): C# passes the CAUSE of an exhaust to the hook -- "
               "AfterCardExhausted(ctx, card, bool causedByEthereal) "
               "(JossPaper.cs:102-114, dispatched from CardCmd.cs:237-244) -- "
               "and `causedByEthereal: true` is passed from exactly two "
               "turn-end sites in the whole game (CombatManager.cs:1240 and "
               "CardModel.cs:1692). The play-time exhaust of an Exhaust-keyword "
               "card passes FALSE (CardModel.cs:1985). relics/joss_paper.py:36 "
               "has no cause parameter and branches on `card.is_ethereal`, a "
               "property of the card, so it defers the credit for ANY mid-turn "
               "exhaust of an Ethereal card. LIVE: Apparition is a ported "
               "1-cost Ancient Skill with both Exhaust and Ethereal "
               "(cards/apparition.py:12-38), granted by the ported relic "
               "Distinguished Cape (relics/distinguished_cape.py:25), and Joss "
               "Paper is a ported Uncommon relic -- so the real game draws the "
               "5th-exhaust card immediately, mid-turn and still playable, "
               "where the sim withholds it until on_hand_emptied fires from "
               "the flush (and its card then survives into the next turn, "
               "making the next hand 6 instead of 5). Distinct from G4: there "
               "the credit is stranded, here it is merely late.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="turn_structure audit gap G18 (audit/records/seam/turn_structure.json, "
               "spec step 65): PaelsEye.AnyCardsPlayedThisTurn "
               "(PaelsEye.cs:149-156) has two clauses the sim's "
               "relics/paels_eye.py:27-34 has neither of -- the turn-1 "
               "short-circuit `if (TurnNumber == 1 && Owner.Relics.Any(r => r "
               "is WhisperingEarring)) return true` (PaelsEye.cs:152) and the "
               "auto-play exclusion `&& !e.CardPlay.IsAutoPlay` "
               "(PaelsEye.cs:155). The sim scans history unfiltered, and "
               "history.py:80-81 records a CardPlayedEntry for every play "
               "including auto-plays (relics/whispering_earring.py:36 names "
               "the missing auto flag as a known divergence). The two "
               "omissions cancel whenever Whispering Earring actually plays a "
               "card and diverge otherwise. LIVE on the auto-play leg with two "
               "ported relics: Imbued, granted by Electric Shrymp "
               "(relics/electric_shrymp.py:17-21), auto-plays on turn 1, so a "
               "player holding Pael's Eye who ends turn 1 without playing "
               "anything gets the extra turn in the real game and does NOT get "
               "it in the sim. (The other leg: with [whispering_earring, "
               "paels_eye] and an opening hand where nothing is playable, the "
               "Earring plays nothing and the sim grants an extra turn "
               "PaelsEye.cs:152 withholds.)",
        strict=True,
    )
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

    Every HookSystem dispatcher walks `list(self._listeners)` in order
    (hooks.py:61 and the same line in all 66 of them), so this list IS the
    sim's cross-listener ordering rule made visible. Categories mirror the
    five kinds C#'s CombatState.IterateHookListeners walks, plus the sim-only
    CombatHistory (hook_dispatch note N3).
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
    for listener in hooks._listeners:
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

    def test_dispatch_order_is_registration_order_grouped_by_category(self):
        """Spec steps 41-44 and gap G2. The sim's listener list is built once,
        by appending, in CombatState.__init__ order: the combat history first
        (combat.py:112), then every deck card with its enchantment right after
        it (124-133), then relics (158-159), then belt potions (164-166); a
        power joins only when it is applied (cmds.py:326), so powers are always
        LAST among the listeners that exist at that moment.

        Both halves are asserted: the composition of `_listeners`, and that a
        real dispatch visits exactly that sequence -- the second is what makes
        this a pin on dispatch rather than on a data structure.

        C# builds no such list. `CombatState.IterateHookListeners`
        (CombatState.cs:410-493) re-derives the listeners per dispatch from the
        creatures themselves, allies before enemies, and within a player walks
        Powers (416) -> Relics (428-435) -> PotionSlots (436-443) -> Orbs (448)
        -> the cards of AllPiles (449-467). Powers first, cards last: almost
        the mirror image of the assertion below. If a future change reorders
        registration or replaces `_listeners`, this test is where it surfaces.
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

        expected = (["history"] + ["card"] * 9 + ["relic"] * 2 + ["potion"]
                    + ["power"] * 2)
        assert listener_categories(cs.hooks) == expected

        # ...and a dispatch really does visit them in that order.
        visited = self._probe(cs.hooks, "on_combat_start")
        cs.hooks.on_combat_start()
        assert visited == list(cs.hooks._listeners)

        # The enemy's Vulnerable is the LAST listener even though C# would put
        # every enemy power after the player's block but before nothing at all
        # -- enemies come after allies there, powers first within each.
        from sts2_rl.powers import Power
        assert isinstance(cs.hooks._listeners[-1], Power)
        assert cs.hooks._listeners[-1].owner is cs.enemy

    @pytest.mark.xfail(
        reason="hook_dispatch audit gap G2 (audit/records/seam/hook_dispatch.json, "
               "spec steps 1-6, 41-43): CombatState.IterateHookListeners walks "
               "each creature's POWERS (CombatState.cs:416) before that "
               "player's RELICS (428-435), while the sim appends relics at "
               "combat setup (combat.py:158-159) and powers only when applied "
               "(cmds.py:326), so relics always run first. LIVE on "
               "Hook.ModifyEnergyCostInCombat (Hook.cs:1574-1590), a "
               "dispatcher this record owns: CuriousPower reduces a Power "
               "card's cost with a floor of 0 (CuriousPower.cs:12-32 -> "
               "powers.py:2883-2889, applied by the ported Mad Science card, "
               "cards/mad_science.py:174-177) and Spiked Gauntlets raises a "
               "Power card's cost by 1 (SpikedGauntlets.cs:27-39 -> "
               "relics/spiked_gauntlets.py:26-32, from the ported Tanx shrine, "
               "events/tanx.py:13). Both are early-phase, so listener order is "
               "the only thing that decides the result: on a 1-cost Power card "
               "with 2 Curious stacks the game computes max(0, 1-2) = 0 then "
               "+1 = 1, and the sim computes 1+1 = 2 then max(0, 2-2) = 0 -- "
               "the sim hands the player a free Power card the real game "
               "charges 1 energy for.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="hook_dispatch audit gap G3 (audit/records/seam/hook_dispatch.json, "
               "spec steps 27-30): Hook.ModifyEnergyCostInCombat runs TWO "
               "complete listener passes -- every TryModifyEnergyCostInCombat, "
               "then every TryModifyEnergyCostInCombatLate "
               "(Hook.cs:1574-1590) -- and 24 of Hook.cs's 147 dispatchers are "
               "multi-pass while AbstractModel.cs declares 27 phase-suffixed "
               "hooks. hooks.py:196-201 is a single flat walk with no phase "
               "concept (hooks.py:673-680 says so outright). LIVE with two "
               "ported powers that both target Attacks: TangledPower is EARLY "
               "(TangledPower.cs's TryModifyEnergyCostInCombat -> "
               "powers.py:1486-1502, applied by the ported Act-1 monster Vine "
               "Shambler, monsters/overgrowth/vine_shambler.py:42-43) and adds "
               "1 to an Entangled Attack's cost, while FreeAttackPower is LATE "
               "(FreeAttackPower.cs:14-40 -> powers.py:1133-1155, applied by "
               "the ported Ironclad card Unrelenting, cards/unrelenting.py:40) "
               "and sets an Attack's cost to 0. The game always runs Tangled "
               "first and Free Attack last, so the next Attack is free; the "
               "sim's answer depends on which power landed first -- applying "
               "Free Attack before the Vine Shambler's Tangle leaves the "
               "Strike at 1. BufferPower.cs:17-19 is the source's own "
               "statement that Late is load-bearing.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="hook_dispatch audit gap G4 (audit/records/seam/hook_dispatch.json, "
               "spec seed fact 3): CardModel.cs:1904-1965 loops `for (int i = "
               "0; i < playCount; i++)`, builds a FRESH CardPlay each "
               "iteration (1919-1928, PlayIndex = i) and fires "
               "Hook.BeforeCardPlayed at 1929 and Hook.AfterCardPlayed at 1959 "
               "INSIDE that loop. combat.py:466 fires before_card_played once "
               "BEFORE the `for _ in range(play_count)` loop (477-494) and "
               "combat.py:514 fires on_card_played once AFTER it, so a replayed "
               "card brackets its whole multi-play with one pair of events. "
               "LIVE with two ported relics: Throwing Axe plays the first card "
               "of each combat twice (ThrowingAxe.cs -> "
               "relics/throwing_axe.py:30-36, from the ported Tanx shrine, "
               "events/tanx.py:13) and Pen Nib counts Attack plays in "
               "before_card_played and doubles every 10th (PenNib.cs -> "
               "relics/pen_nib.py:30-35). The real game counts the doubled "
               "Strike as two Attacks and the sim counts one, so from the "
               "first combat onward the sim doubles a different Attack. The "
               "four other ported replay sources (enchantments.py:167, "
               "enchantments.py:232, powers.py:966 One-Two Punch, "
               "powers.py:3919 Duplication) widen it, as does every one of the "
               "sim's 48 on_card_played listeners.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="hook_dispatch audit gap G9 (audit/records/seam/hook_dispatch.json "
               "step 31; the same mechanism as damage_pipeline's guard N3, "
               "raised to gap in the same pass): Hook.ModifyDamageInternal "
               "(Hook.cs:2515-2538) threads a RUNNING decimal through the "
               "listeners -- `num *= item.ModifyDamageMultiplicative(target, "
               "num, ...)` folds each factor in immediately -- while "
               "hooks.py:66-78 multiplies every listener's factor together in "
               "FLOAT and cmds.py:58 applies the product once, "
               "`amount = int(amount * hooks.modify_damage_multiplicative"
               "(...))`. No implementation on either side reads the value it "
               "is handed (0 of 46 C# overrides, 0 of 31 sim ones -- "
               "audit/tools/dormancy_probes.py cs-running-value / "
               "sim-running-value), so the divergence is the aggregation "
               "SHAPE, not the argument: 1.5 * 0.7 is 1.0499999999999998 in "
               "float, so 20 * that truncates to 20, where 20m * 1.5m * 0.7m "
               "is exactly 21m. LIVE: Shrink (x0.7 on the dealer, "
               "powers.py:1366-1387, applied by the ported Act-1 Shrinker "
               "Beetle at monsters/overgrowth/shrinker_beetle.py:39-40 and by "
               "the Shrink Potion at potions.py:718-722) plus Vulnerable "
               "(x1.5 on the target, powers.py:403-417, applied by the ported "
               "Bash) on a 20-damage powered attack: the sim deals 20 where "
               "the game deals 21. A control that keeps float arithmetic but "
               "threads it sequentially returns 21, so this is not "
               "float-vs-decimal representation.",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="monster_state_machine audit gap G1 (audit/records/seam/"
               "monster_state_machine.json step 13), LIVE. C#'s "
               "RandomBranchState.AddBranch puts cooldown-or-maxRepeats in "
               "positional slot 2 and NEVER a weight -- every weight is a "
               "float or Func<float> defaulting to 1f (RandomBranchState.cs:"
               "46-113) -- while the sim's add_branch puts WEIGHT there "
               "(monsters/state_machine.py:160-167), so a positional port "
               "turns a repeat limit into a weight. This is the shipped "
               "TwigSlimeM/Flyconid bug class, still present in FIVE ported "
               "monsters (audit/tools/state_machine_probes.py mismatch): "
               "FlailKnight.cs:50,51 AddBranch(FLAIL, 2) / AddBranch(RAM, 2) "
               "= maxRepeats 2 weight 1, ported at "
               "monsters/hive/flail_knight.py:51-52 as weight=2.0 "
               "CAN_REPEAT_FOREVER; HunterKiller.cs:43 -> "
               "monsters/hive/hunter_killer.py:45; ScrollOfBiting.cs:90 -> "
               "monsters/glory/scroll_of_biting.py:65; SpectralKnight.cs:52 "
               "-> monsters/glory/knights.py:111; and "
               "FakeMerchantMonster.cs:58 AddBranch(ENRAGE, 3, CannotRepeat) "
               "= COOLDOWN 3 -> monsters/fake_merchant.py:72-75 "
               "weight=_ENRAGE_WEIGHT (3.0). Observable, executed over "
               "100000 rolls (probe `distribution`): FlailKnight telegraphs "
               "FLAIL/RAM/WAR_CHANT at 41.6/41.6/16.8% where the game gives "
               "36.2/36.4/27.4%, and the game's CanRepeatXTimes(2) bar on "
               "three FLAILs in a row is gone entirely. All five are in "
               "ported encounter pools (monsters/hive/__init__.py:26,31, "
               "monsters/glory/__init__.py:30,35, "
               "monsters/fake_merchant.py:117-120), so a player sees the "
               "wrong intent and a replay records the wrong MonsterAi draw. "
               "FossilStalker.cs:58-60 and TwoTailedRat.cs:127 read the same "
               "argument shapes CORRECTLY, so this is a port defect, not a "
               "machinery one.",
        strict=True,
    )
    def test_addbranch_int_args_are_repeat_limits_not_weights(self):
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

    @pytest.mark.xfail(
        reason="monster_state_machine audit gap G4 (audit/records/seam/"
               "monster_state_machine.json steps 39, 40, 44), LIVE. "
               "Creature.StunInternal (Creature.cs:524-544) makes the stun a "
               "REAL move: it builds MoveState('STUNNED', stunMove, new "
               "StunIntent()) with FollowUpStateId = StateLog.Last().Id and "
               "MustPerformOnceBeforeTransitioning = true, and force-sets it "
               "(MonsterModel.cs:420-432). The sim's CreatureCmd.stun "
               "(cmds.py:208-218) sets a boolean, combat.py:313-329 skips "
               "the turn, and state_machine.py:315-318 special-cases the "
               "intent -- machine.current, machine.state_log and "
               "_current_move are all untouched (executed: probe "
               "stun-machine). Observable: because the game's post-stun roll "
               "transitions STUNNED -> the deferred move id, it APPENDS that "
               "id to StateLog a second time "
               "(MonsterMoveStateMachine.cs:76-79), which by "
               "RandomBranchState.cs:142-157 blocks that move's "
               "CanRepeatXTimes/CannotRepeat branch on the FOLLOWING roll "
               "while the sim still offers it -- a different enemy intent. "
               "LIVE, on the one route that closes end to end (probes "
               "stun-sites, whistle-route, stun-machine): of the sim's 8 "
               "CreatureCmd.stun call sites exactly one takes an EXTERNAL "
               "target, cards/whistle.py:38 (the ported Tanx Ancient Attack, "
               "CreatureCmd.stun with no next move); Whistle comes only from "
               "Tanx's Whistle (relics/tanxs_whistle.py:17) and `tanx` is in "
               "GLORY's ancient pool and no other act's (rooms.py:206), and "
               "Glory is the LAST act (run._ACTS_BY_INDEX), so the "
               "stun-reachable population is Glory's pools -- in which four "
               "RandomBranchState machines read the state log: ScrollOfBiting "
               "(scrolls_of_biting_*), FlailKnight and SpectralKnight "
               "(glory/knights.py:131) and SoulNexus. THIS TEST USES "
               "ScrollOfBiting, whose C# CHEW branch is CanRepeatXTimes(2) "
               "(ScrollOfBiting.cs:90) -- exactly the rule the duplicate "
               "fills. Executed consequence (probe stun-machine, 100000 "
               "rolls, seed 7): after a Whistle stun on a CHEW telegraph the "
               "game's next-but-one intent is CHOMP 100% of the time and the "
               "sim's is CHEW 66.5% / CHOMP 33.5%. The three monsters an "
               "earlier pass cited here -- SlumberingBeetle, "
               "LagavulinMatriarch, TerrorEel -- CANNOT show this observable: "
               "the first two branch on ConditionalBranchState (reads "
               "self.powers, never state_log) and TerrorEel has no branch "
               "state at all, and all three are in earlier acts than the "
               "Whistle.",
        strict=True,
    )
    def test_stun_makes_the_stun_a_move_and_relogs_the_deferred_one(self):
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

    @pytest.mark.xfail(
        reason="monster_state_machine audit gap G5 (audit/records/seam/"
               "monster_state_machine.json step 36), DORMANT. "
               "CreatureCmd.stun's next_move_key override is gated on "
               "hasattr(target, '_move_key') (cmds.py:216-217) -- _move_key "
               "is the HAND-ROLLED monsters' field -- so for a "
               "MachineMonster the caller's explicit next move evaporates "
               "with no error (executed: probe stun-machine reports "
               "next_move_key='LASH_MOVE' SILENTLY DROPPED). C# threads it "
               "into the synthetic stun state's FollowUpStateId "
               "(Creature.cs:532-541), so the monster resumes on exactly "
               "that move. DORMANT: executed, probe stun-sites enumerates all "
               "8 sim CreatureCmd.stun call sites and reports exactly one "
               "passing next_move_key -- monsters/overgrowth/"
               "ceremonial_beast.py:45 -- and CeremonialBeast is a "
               "hand-rolled Monster (ceremonial_beast.py:32) that does have "
               "_move_key, while the other three monster self-stunners "
               "(SlumberingBeetle, LagavulinMatriarch, TerrorEel) are "
               "MachineMonsters that pass none. Named "
               "trigger: porting CeremonialBeast -- or DecimillipedeSegment "
               "/ TestSubject / WaterfallGiant, the other "
               "MustPerformOnceBeforeTransitioning users "
               "(CeremonialBeast.cs:150, DecimillipedeSegment.cs:155, "
               "TestSubject.cs:194, WaterfallGiant.cs:202) -- onto "
               "MachineMonster, or stunning any existing MachineMonster with "
               "an explicit next move.",
        strict=True,
    )
    def test_stun_next_move_key_reaches_a_machine_monster(self):
        from sts2_rl.cmds import CreatureCmd
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker

        enc = Encounter(id="pin_stun_key", monster_classes=[FossilStalker])
        cs = CombatState(rng=random.Random(3), encounter=enc)
        mon = cs.enemies[0]
        CreatureCmd.stun(cs.hooks, mon, next_move_key="LASH_MOVE")
        # C#: the stun's FollowUpStateId is LASH_MOVE, so that is the move
        # performed on the turn after the stunned one.
        assert mon._current_move.id == "LASH_MOVE"

    @pytest.mark.xfail(
        reason="monster_state_machine audit gap G6 (audit/records/seam/"
               "monster_state_machine.json steps 35, 41), DORMANT -- see the "
               "demotion below. The machine "
               "itself is already on the right stream -- "
               "MachineMonster._move_rng is combat_rng.monster_ai "
               "(monsters/state_machine.py:306-312), matching "
               "MonsterModel.cs:417's RunRng.MonsterAi, so the brief's seed "
               "fact 'the sim uses the shared combat stream' is STALE. One "
               "site is not: FlutterPower's stun splice calls "
               "machine.roll_move(self.owner, self.owner._rng) "
               "(powers.py:2226-2235), the SHARED combat random.Random -- "
               "executed, it is the only one of the sim's three "
               "machine.roll_move call sites that is off-stream (probe "
               "move-rng). Worse, roll_move walks all the way to a MoveState "
               "and so CONSUMES a branch draw, where FlutterPower.cs:47 "
               "calls StateLog.Last().GetNextState(...), which by "
               "MoveState.cs:67-70 is DETERMINISTIC and consumes nothing -- "
               "the game defers the branch to the post-stun roll. DORMANT, "
               "and this label CORRECTS a first-pass LIVE claim that this "
               "very pin refuted by XPASSing: FlutterPower has exactly one "
               "applier on each side, ThievingHopper "
               "(monsters/hive/thieving_hopper.py:113-114; in C# only "
               "ThievingHopper.cs), and its machine is a pure deterministic "
               "CHAIN with no RandomBranchState on either side "
               "(thieving_hopper.py:61-65 THIEVERY->FLUTTER->HAT_TRICK->NAB"
               "->ESCAPE, matching ThievingHopper.cs's FollowUpState "
               "assignments), so a chain roll consumes no draw from any "
               "stream and neither clause is observable today. Named "
               "trigger: a FlutterPower user whose current move's follow-up "
               "is a RandomBranchState -- any of the 12 resolved ported "
               "branch ports would do (probe mismatch). "
               "THIS TEST CONSTRUCTS THAT TRIGGER, "
               "splicing a branch behind FLUTTER_MOVE so the splice must "
               "draw, and then asserts the draw did not come off the shared "
               "stream. Cross-referenced to turn_structure's G9, which owns "
               "WHEN the roll happens and is a different mechanism.",
        strict=True,
    )
    def test_flutter_stun_splice_consumes_no_shared_stream_draw(self):
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

        PowerCmd.apply(cs.hooks, hopper, FlutterPower, 1, applier=cs.player)
        before = rng.floats
        # Flutter halves powered damage, so 10 lands as 5 -- enough for
        # on_damage_received's amount > 0 guard to consume the last stack.
        DamageCmd.deal(cs.hooks, hopper, 10, dealer=cs.player,
                       card=StrikeCard(), props=ValueProp.MOVE)
        assert hopper._current_move.id in ("HAT_TRICK_MOVE", "NAB_MOVE")
        # C#: FlutterPower.cs:47 draws off RunRng.MonsterAi, never the shared
        # combat stream.
        assert rng.floats == before

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
