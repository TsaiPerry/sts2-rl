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
        reason="gap G1 (audits/seam/damage_pipeline.json): ThornsPower is "
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
    """power_cmd audit (docs/audit/seams/power_cmd.md): pins the ordering
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
        reason="power_cmd audit gap G1 (audits/seam/power_cmd.json): "
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
        reason="power_cmd audit step 20 (audits/seam/power_cmd.json): "
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
    """creature_card_cmds audit (docs/audit/seams/creature_card_cmds.md):
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
               "(audits/seam/creature_card_cmds.json): BlockCmd.apply "
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
               "(audits/seam/creature_card_cmds.json): the sim has no "
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
               "(audits/seam/creature_card_cmds.json): RunState.transform_card "
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
               "(audits/seam/creature_card_cmds.json): CombatState."
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
               "(audits/seam/creature_card_cmds.json): C#'s "
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
               "(audits/seam/creature_card_cmds.json): "
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
