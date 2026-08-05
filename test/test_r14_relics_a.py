"""Round 14 (R4) -- settling the `relic-tier-batch-A` unlabelled hook batch:
archaic_tooth, booming_conch, charons_ashes, festive_popper, gambling_chip,
gremlin_horn, philosophers_stone, silver_crucible, spiked_gauntlets,
stone_calendar, stone_cracker, sword_of_jade.

Every one of these twelve records was already carried through several rounds
of guard-level analysis (2026-07-26 initial audit, narrowed 2026-07-27/28/29,
and -- for three of them -- a round-13 R8 fix pass on 2026-08-01). This file
does NOT re-derive that analysis from scratch; it RE-EXECUTES each guard's
own reachability/mechanism claim against the CURRENT tree, and several times
finds the claim has gone stale in one direction or the other.
"""
from __future__ import annotations

import inspect
import random

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardCmd, CreatureCmd, DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState
from sts2_rl.valueprops import DamageProps


def _combat(relic_ids=(), hand=(), seed: int = 0, enemy_count: int = 1,
            room_type=None) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(10)],
                     encounter=Encounter("test", [LeafSlimeS] * enemy_count),
                     relics=[make_relic(r) for r in relic_ids],
                     room_type=room_type)
    cs.player.hand.clear()
    for cid in hand:
        card = make_card(cid)
        card.combat = cs
        cs.hooks.register(card)
        cs.player.hand.append(card)
    return cs


# ══════════════════════════════════════════════════════════════════════════
# relic/archaic_tooth/AfterObtained
#
# Guards G1 (upgrade-carry) and G2 (enchant-carry) were both audited DORMANT
# 2026-07-26 and never revisited. Both re-executed here against the CURRENT
# code, which has grown from 2 to 21 registered enchantment classes since the
# audit -- so G2's census needed re-running, not just re-reading.
# ══════════════════════════════════════════════════════════════════════════

def test_archaic_tooth_g1_bash_max_upgrade_level_is_still_one():
    """G1's whole dormancy argument is that the sim's upgrade-carry LOOP
    (`for _ in range(original.upgrade_level): transformed.upgrade()`) can
    only ever run 0 or 1 times, matching C#'s single `if (IsUpgraded)
    CardCmd.Upgrade(cardModel)` (ArchaicTooth.cs:154-157) exactly -- because
    Bash's max_upgrade_level is 1. Re-confirmed directly against the card
    class, not assumed."""
    from sts2_rl.cards.bash import BashCard
    assert BashCard.max_upgrade_level == 1


def test_archaic_tooth_after_obtained_carries_the_upgrade():
    """Fresh execution: an upgraded Bash transcends into an upgraded Break,
    matching both C#'s single-call Upgrade and the sim's bounded loop."""
    run = RunState(rng=random.Random(0))
    bash = next(c for c in run.deck if c.id == "bash")
    bash.upgrade()
    assert bash.upgrade_level == 1

    relic = make_relic("archaic_tooth")
    relic.after_obtained(run)

    assert not any(c.id == "bash" for c in run.deck)
    brk = next(c for c in run.deck if c.id == "break")
    assert brk.upgrade_level == 1


def test_archaic_tooth_g2_no_currently_ported_enchantment_distinguishes_bash_from_break():
    """G2's dormancy argument, RE-DERIVED rather than inherited: the record's
    2026-07-26 citation named Swift as the one narrow-enough eligibility
    predicate ('BASIC rarity and a strike/defend tag') and said Bash could
    never carry it because Bash is neither BASIC-tagged nor tag-marked. That
    citation is now WRONG -- current SwiftEnchantment.can_enchant has no
    override at all (enchantments.py); the BASIC+tag restriction the record
    described belongs to SpiralEnchantment instead. The CONCLUSION still
    holds by a wider census: of the 21 enchantment classes registered today
    (up from the audit's 2), NONE returns a different answer for Bash than
    for Break -- Bash carries no tags (cards/bash.py never sets `tags`) and
    is not Skill/Exhaust/GainsBlock, so every tag-or-type-gated can_enchant
    (Spiral, Souls, Imbued, Goopy, Nimble, Instinct, Sharp, Vigorous,
    Corrupted, RoyallyApproved) that could possibly separate the two either
    accepts both (both are Attack) or rejects both (neither has the tag)."""
    from sts2_rl.enchantments import ALL_ENCHANTMENTS

    bash = make_card("bash")
    brk = make_card("break")
    assert bash.tags == frozenset()
    assert brk.rarity != bash.rarity  # ANCIENT vs BASIC -- the one axis that
                                       # could matter if either card had tags

    diverging = []
    for eid, cls in ALL_ENCHANTMENTS.items():
        if cls.can_enchant(bash) != cls.can_enchant(brk):
            diverging.append(eid)
    assert diverging == []
    # Not vacuous: at least one class actually restricts by card_type/tag,
    # so the loop is exercising real predicates and not just the base check.
    assert any(cls.can_enchant(bash) is False
               for cls in ALL_ENCHANTMENTS.values())


def test_archaic_tooth_after_obtained_carries_an_eligible_enchantment():
    """Executed transform with an eligible enchantment (Adroit, the least
    restrictive real one -- base CanEnchant only) attached to Bash: the
    replacement Break ends up carrying it, matching
    ArchaicTooth.cs:158-162's clone-and-enchant."""
    from sts2_rl.enchantments import make_enchantment

    run = RunState(rng=random.Random(1))
    bash = next(c for c in run.deck if c.id == "bash")
    ench = make_enchantment("adroit")
    ench.card = bash
    bash.enchantment = ench

    relic = make_relic("archaic_tooth")
    relic.after_obtained(run)

    brk = next(c for c in run.deck if c.id == "break")
    assert brk.enchantment is not None
    assert brk.enchantment.id == "adroit"
    assert brk.enchantment.card is brk


# ══════════════════════════════════════════════════════════════════════════
# relic/booming_conch/AfterSideTurnStart
#
# G1 (hook slot) is already closed (round 11). G2 (the energy-gain modifier
# chain bypass) is re-confirmed DORMANT below: the bypass is real, but the
# one power that could expose it (NoEnergyGainPower) can only be armed by a
# played card, and no card can be played before this relic's own dispatch.
# ══════════════════════════════════════════════════════════════════════════

def test_booming_conch_after_side_turn_start_bypasses_the_energy_gain_chain():
    """G2's MECHANISM, direct demonstration: the grant does not go through
    hooks.modify_energy_gain at all (booming_conch.py:34 assigns
    `player.energy +=` directly), where PlayerCmd.GainEnergy always routes
    through Hook.ModifyEnergyGain. Spy on the hook to prove it is never
    consulted."""
    cs = _combat(["booming_conch"], seed=200, room_type=RoomType.ELITE)
    relic = cs.relics[0]
    calls = []
    original = cs.hooks.modify_energy_gain

    def spy(player, amount):
        calls.append(amount)
        return original(player, amount)

    cs.hooks.modify_energy_gain = spy
    try:
        before = cs.player.energy
        relic.after_side_turn_start(cs.player)
    finally:
        cs.hooks.modify_energy_gain = original
    assert cs.player.energy == before + relic.ENERGY
    assert calls == []          # the chain was never consulted


def test_booming_conch_g2_no_energy_gain_power_cannot_predate_the_grant():
    """G2's REACHABILITY leg, re-executed rather than assumed: the only
    ported source of NoEnergyGainPower is the `expect_a_fight` card's own
    on_play, and this relic's dispatch (after_side_turn_start, turn <= 1)
    fires from PlayerCombatState.start_turn -- strictly before the game
    reaches a state where any card CAN be played (no decision loop has
    opened yet). Demonstrated directly: a freshly-built combat has no
    no_energy_gain power on the player before start_turn runs, and
    after_side_turn_start is what start_turn calls after energy/draw."""
    from sts2_rl.cards.expect_a_fight import ExpectAFightCard

    # The only ported granter of NoEnergyGainPower is this card's on_play --
    # a played-card action, gated behind a decision the driver has not yet
    # offered when after_side_turn_start fires.
    granter_src = inspect.getsource(ExpectAFightCard.on_play)
    assert "NoEnergyGainPower" in granter_src

    cs = _combat(["booming_conch"], seed=201, room_type=RoomType.ELITE)
    # Before start_turn has run at all, the player cannot have no_energy_gain:
    # nothing has played expect_a_fight (no decision loop has opened).
    assert "no_energy_gain" not in cs.player.powers
    cs.player.start_turn()
    # Even after the real turn-1 setup (which is what actually dispatches
    # after_side_turn_start), the power still cannot be present -- no card
    # was played to grant it.
    assert "no_energy_gain" not in cs.player.powers
    assert cs.player.energy >= cs.relics[0].ENERGY  # the grant landed


# ══════════════════════════════════════════════════════════════════════════
# relic/charons_ashes/AfterCardExhausted
#
# Fully settled in round 13 (R8 fix pass); re-run here as-is to confirm the
# witness the round-13 lane wrote still passes against today's tree, per
# protocol's "start by re-executing the entry's own witness."
# ══════════════════════════════════════════════════════════════════════════

def test_charons_ashes_still_deals_zero_to_a_corpse_via_the_is_dead_guard():
    """Re-execution of the round-13 R8 witness
    (test_r13_relic2.py::test_damage_cmd_deal_refuses_the_damage_relics_at_the_is_dead_guard),
    narrowed to charons_ashes' own call shape: DamageCmd.deal's is_dead guard
    -- not living_enemies() vs hittable_enemies() -- is what actually refuses
    a dead-but-still-listed target, so the G1 predicate gap stays dormant."""
    cs = _combat(["charons_ashes"], seed=202, enemy_count=2)
    corpse = cs.enemies[0]
    DamageCmd.deal(cs.hooks, corpse, 9999, dealer=cs.player)
    assert corpse.is_dead is True
    dealt = DamageCmd.deal(cs.hooks, corpse, 3, dealer=cs.player,
                           props=DamageProps.NON_CARD_UNPOWERED)
    assert dealt == 0


def test_charons_ashes_hits_every_living_enemy_with_no_should_allow_hitting_backstop():
    """N-side sanity check pinning the ACTUAL relic call shape end to end: a
    normal exhaust deals the full 3 to every living enemy, matching
    CharonsAshes.cs:17-25."""
    cs = _combat(["charons_ashes"], hand=["strike"], seed=203, enemy_count=2)
    before_hp = [e.hp for e in cs.enemies]
    relic = cs.relics[0]
    card = cs.player.hand[0]
    from sts2_rl.hooks import HookSystem
    cs.hooks.on_card_exhausted(card)
    for e, hp in zip(cs.enemies, before_hp):
        assert e.hp == hp - 3


# ══════════════════════════════════════════════════════════════════════════
# relic/festive_popper/AfterPlayerTurnStart
#
# G1 (slot) closed round 13 R8. G2 (enemy-set predicate) and G3 (hand-rolled
# win check) both re-confirmed DORMANT in round 13 R8 with a pinning test in
# test_r13_relic2.py; re-executed narrowly here for the G2 leg that file
# did not carry a dedicated test for.
# ══════════════════════════════════════════════════════════════════════════

def test_festive_popper_g2_damage_cmd_backstops_an_unhittable_enemy():
    """G2 re-confirmed: living_enemies() would include a mid-revival enemy
    that HittableEnemies excludes, but DamageCmd.deal's own is_dead guard
    (the same dead-code-dominated guard charons_ashes leans on) means an
    unhittable-but-not-dead target still can't exist among living_enemies()
    for a reachable creature -- so no ported should_allow_hitting-false
    creature is EVER alive-and-in-living_enemies at the same time. Direct
    demonstration with the one live should_allow_hitting=False case the sim
    has (a reviving IllusionPower target, which is also is_dead=True)."""
    from sts2_rl.powers import IllusionPower

    cs = _combat(["festive_popper"], seed=204, enemy_count=2)
    enemy = cs.enemies[1]
    PowerCmd.apply(cs.hooks, enemy, IllusionPower, 1)
    DamageCmd.deal(cs.hooks, enemy, 9999, dealer=cs.player)
    assert enemy.is_dead is True
    assert cs.hooks.should_allow_hitting(enemy) is False
    relic = cs.relics[0]
    assert enemy not in relic.living_enemies()   # already excluded via is_gone


def test_festive_popper_g3_early_check_win_is_still_the_current_code():
    """Confirms the mechanism test_r13_relic2.py pins is still literally true
    of today's festive_popper.py -- `_check_win()` still runs inside
    on_player_turn_started's own body, not from a post-dispatch
    CheckWinCondition recomputation."""
    src = inspect.getsource(make_relic("festive_popper").__class__.on_player_turn_started)
    assert "_check_win" in src


# ══════════════════════════════════════════════════════════════════════════
# relic/gambling_chip/AfterPlayerTurnStart
#
# FINDING: G1 has FLIPPED since the audit. gambling_chip.py no longer
# open-codes the discard loop -- it calls the shared CardCmd.discard_and_draw
# (cmds.py), which now implements the Sly-collect-and-auto-play tail
# (CardCmd.cs:186-204) in full. The record's own hooks-level rollup text
# ("CardCmd.DiscardAndDraw does two things the sim's inline loop does not")
# describes CODE THAT NO LONGER EXISTS -- there is no inline loop left to
# compare. G2's pile-mutation half also moved onto the shared helper's
# `remove_from_current_pile` + append, in the C# order (append before the
# on_card_discarded hook). G3 was already closed 2026-07-27 (SKIPPABLE_
# PURPOSES) -- the hooks-level rollup text still listing G3 as "also a gap"
# is a SEPARATE staleness the guards array itself already contradicts.
# ══════════════════════════════════════════════════════════════════════════

def test_gambling_chip_calls_the_shared_discard_and_draw_not_an_inline_loop():
    """Direct proof the record's premise (an inline discard loop) is gone:
    gambling_chip.py's body now names CardCmd.discard_and_draw and contains
    no direct discard_pile mutation of its own."""
    import sts2_rl.relics.gambling_chip as mod
    src = inspect.getsource(mod.GamblingChip.on_player_turn_started)
    assert "discard_and_draw" in src
    assert "discard_pile.append" not in src


def test_gambling_chip_g1_sly_card_is_auto_played_after_the_mulligan():
    """G1's MECHANISM re-tested end to end: with a hand-fed Sly card among
    the chosen discards, CardCmd.discard_and_draw's Sly tail (cmds.py's
    `combat.auto_play_card(card, auto_play_type='sly_discard')`) fires
    through Gambling Chip's own call site -- something the OLD inline loop
    could never do regardless of whether any card had `sly=True`. G1's
    remaining residue is a pure content gap (no registered card sets
    sly=True today), re-confirmed in the second half; it is no longer a
    mechanism gap at gambling_chip's own site."""
    from sts2_rl.cards.base import _CARD_CLASSES

    cs = _combat(["gambling_chip"], seed=205)
    sly_card = make_card("strike")
    sly_card.sly = True
    cs.player.hand[:] = [sly_card, make_card("defend")]
    for c in cs.player.hand:
        c.combat = cs
        cs.hooks.register(c)
    relic = cs.relics[0]

    played = []
    original_auto_play = cs.auto_play_card

    def spy_auto_play(card, target_idx=None, auto_play_type="default"):
        played.append((card, auto_play_type))
        return original_auto_play(card, target_idx, auto_play_type)

    cs.auto_play_card = spy_auto_play
    try:
        relic.on_player_turn_started(cs.player)
    finally:
        cs.auto_play_card = original_auto_play

    assert any(c is sly_card and t == "sly_discard" for c, t in played)

    # Residual content census: still zero registered cards default to Sly.
    assert not any(getattr(cls, "sly", False) for cls in _CARD_CLASSES.values())


def test_gambling_chip_g3_is_still_closed_contradicting_the_stale_hooks_rollup():
    """The record's hooks-level `issue` text says G3 ('the min=0 decline') is
    'also a gap', but the record's OWN guards array marks G3 verdict
    'faithful', 'Closed 2026-07-27'. Re-confirmed against the current
    driver: gambling_chip is still in SKIPPABLE_PURPOSES, so an empty
    selection is expressible and the relic returns early without
    mulliganing the whole hand."""
    from sts2_rl.driver import SKIPPABLE_PURPOSES
    assert "gambling_chip" in SKIPPABLE_PURPOSES

    cs = _combat(["gambling_chip"], seed=206)
    cs.player.hand[:] = [make_card("strike") for _ in range(3)]
    for c in cs.player.hand:
        c.combat = cs
        cs.hooks.register(c)
    relic = cs.relics[0]
    before = list(cs.player.hand)
    cs.select_cards = lambda *a, **k: []   # selector declines everything
    relic.on_player_turn_started(cs.player)
    assert cs.player.hand == before        # nothing discarded, nothing drawn


# ══════════════════════════════════════════════════════════════════════════
# relic/gremlin_horn/AfterDeath
#
# FINDING: the hooks-level rollup ("Rollup of guards G1 and G2... WHICH
# deaths reach the hook (G1)... and WHEN (G2)") is STALE. G1 was closed
# 2026-07-29 (round 7) -- the guards array already says so -- and its own
# `what` field's "(LIVE)" tag is a historical label, not the current
# verdict. Only G2 remains open. G2's own census claim ("no sim power
# implements on_damage_dealt at all") has ALSO gone stale -- two now do
# (ImbalancedPower, PaperCutsPower) -- but neither reads player energy or
# hand, so the verdict itself (dormant) is unchanged; the reachability
# argument just needs the wider census recorded below.
# ══════════════════════════════════════════════════════════════════════════

def test_gremlin_horn_g1_neither_revive_power_overrides_should_die():
    """Re-confirms round 7's closure still holds: IllusionPower and
    AdaptablePower take the REAL death arm (should_die is not overridden by
    either), matching C#'s ShouldDie override census (only FairyInABottle
    and LizardTail under src/Core/Models)."""
    from sts2_rl.powers import IllusionPower, AdaptablePower

    assert "should_die" not in IllusionPower.__dict__
    assert "should_die" not in AdaptablePower.__dict__
    assert "should_remove_from_combat_after_death" in IllusionPower.__dict__
    assert "should_remove_from_combat_after_death" in AdaptablePower.__dict__


def test_gremlin_horn_pays_out_on_a_real_illusion_death():
    """Executed end to end: a killed Illusion enemy still dies for real
    (was_removal_prevented False) and Gremlin Horn pays its energy+draw,
    matching C#'s AfterDeath(..., wasRemovalPrevented: false)."""
    from sts2_rl.powers import IllusionPower

    # TWO enemies on purpose (same reason test_r13_relic2.py's
    # _make_reviving_enemy helper insists on it): with only one enemy,
    # killing it to arm the revive makes the combat register as ending
    # before Gremlin Horn's own commands run, which would make this pass
    # for the wrong reason (an early bail, not a real payout).
    cs = _combat(["gremlin_horn"], seed=207, enemy_count=2)
    enemy = cs.enemies[1]
    PowerCmd.apply(cs.hooks, enemy, IllusionPower, 1)
    energy_before, hand_before = cs.player.energy, len(cs.player.hand)
    DamageCmd.deal(cs.hooks, enemy, 9999, dealer=cs.player)
    assert enemy.is_dead is True
    assert cs.player.energy == energy_before + 1
    assert len(cs.player.hand) == hand_before + 1


def test_gremlin_horn_g2_census_is_now_two_on_damage_dealt_implementers_neither_reading_energy_or_hand():
    """G2's WIDENED census: `def on_damage_dealt` now has two implementers
    (ImbalancedPower, PaperCutsPower), not zero as the audit recorded, so the
    old 'nothing runs in the window whose order changed' claim is false as
    stated. Re-derived rather than just re-read: neither implementer's body
    reads the DEALER's energy or hand (Gremlin Horn's own outputs), and
    Gremlin Horn only pays out on an ENEMY death, so the ordering-sensitive
    window G2 names (on_death firing before vs after on_damage_dealt/
    on_damage_received in the same batch) still has nothing that would
    observe it. Verdict unchanged; reasoning replaced."""
    import inspect as _inspect
    from sts2_rl.powers import ImbalancedPower, PaperCutsPower

    impls = [ImbalancedPower, PaperCutsPower]
    for cls in impls:
        src = _inspect.getsource(cls.on_damage_dealt)
        assert ".energy" not in src
        assert ".hand" not in src


# ══════════════════════════════════════════════════════════════════════════
# relic/philosophers_stone/AfterCreatureAddedToCombat
#
# G1 re-confirmed dormant (round 13 R8 already carries a pinning test,
# test_on_creature_added_only_ever_reaches_combat_enemies); re-executed here
# narrowly for this round's own file.
# ══════════════════════════════════════════════════════════════════════════

def test_philosophers_stone_g1_the_sim_models_no_player_side_creature_to_confuse():
    """G1's reachability leg: the sim's CombatState constructor takes no
    player-side creature parameter at all, and CreatureCmd.add's only
    destination is combat.enemies -- so the side-vs-identity substitution in
    philosophers_stone.py:39 (`creature is self.combat.player` instead of a
    side comparison) cannot currently misfire, because there is no
    player-side creature other than the player to misclassify."""
    cs = _combat(["philosophers_stone"], seed=208)
    joiner = LeafSlimeS(cs.hooks, random.Random(9))
    CreatureCmd.add(cs.hooks, joiner)
    assert joiner in cs.enemies
    assert joiner.powers["strength"].amount == 1
    assert cs.player.powers.get("strength") is None


# ══════════════════════════════════════════════════════════════════════════
# relic/silver_crucible/ShouldGenerateTreasure
#
# G3 re-confirmed dormant: the gate (`should_generate_treasure`) and the
# Spoils Map quest payout (`_complete_map_point_quests`) are two genuinely
# independent code paths in RunState.enter_point, and Silver Crucible can
# only ever suppress the FIRST treasure room of the run, which Spoils Map
# (Act 2, SPOILS_ACT_INDEX=1) can never be first to reach.
# ══════════════════════════════════════════════════════════════════════════

def test_silver_crucible_g3_quest_payout_call_site_sits_outside_the_gate():
    """Structural re-check against TODAY's RunState.enter_point (line numbers
    have moved since the 2026-07-26 audit -- it is no longer even named
    enter_room): `_complete_map_point_quests(point)` is called at the SAME
    indentation as the `if all(r.should_generate_treasure(...))` block, i.e.
    unconditionally, not nested inside it."""
    src = inspect.getsource(RunState.enter_point)
    lines = src.splitlines()
    gate_idx = next(i for i, l in enumerate(lines)
                    if "should_generate_treasure(self)" in l)
    quest_idx = next(i for i, l in enumerate(lines)
                     if "_complete_map_point_quests(point)" in l)
    gate_indent = len(lines[gate_idx]) - len(lines[gate_idx].lstrip())
    quest_indent = len(lines[quest_idx]) - len(lines[quest_idx].lstrip())
    assert quest_indent <= gate_indent
    assert quest_idx > gate_idx


def test_silver_crucible_g3_quest_pays_out_even_while_the_gate_is_closed():
    """Direct behavioural proof, bypassing full map machinery: with Silver
    Crucible fresh (treasure_rooms_entered == 0, so should_generate_treasure
    is False -- the suppressed-chest state), `_complete_map_point_quests`
    still pays a stub quest's gold in full. This is the actual bug: the two
    calls are independent, so a Spoils-Map-shaped quest attached to a
    suppressed treasure node would still pay out in the sim."""
    run = RunState(rng=random.Random(2))
    relic = make_relic("silver_crucible")
    run.relics.append(relic)
    assert relic.should_generate_treasure(run) is False   # the suppressed case

    calls = []

    class _StubQuest:
        def on_quest_complete(self, run_state) -> int:
            calls.append(run_state)
            run_state.gain_gold(600)
            return 600

    class _StubPoint:
        quests = [_StubQuest()]

    gold_before = run.gold
    gained = run._complete_map_point_quests(_StubPoint())
    assert gained == 600
    assert run.gold == gold_before + 600
    assert calls == [run]


def test_silver_crucible_spoils_map_act_index_cannot_be_the_first_treasure_room():
    """The reachability leg re-confirmed at the constant that matters: Spoils
    Map only ever retargets Act 2 (index 1), which the run always reaches
    strictly after Act 1 (index 0) -- and Act 1 has its own unavoidable
    treasure room, which is what spends Silver Crucible's one-time
    suppression before Act 2 is ever entered."""
    from sts2_rl.cards.spoils_map import SpoilsMapCard
    assert SpoilsMapCard.SPOILS_ACT_INDEX == 1
    assert SpoilsMapCard.SPOILS_ACT_INDEX > 0


# ══════════════════════════════════════════════════════════════════════════
# relic/spiked_gauntlets/TryModifyEnergyCostInCombat
#
# FINDING: G2 has FLIPPED since the audit (matches test_r13_relic2.py's
# already-landed test_spiked_gauntlets_g2_phase_machinery_now_generic_via_each,
# from round 13's R8 lane). hooks.py's `_each`/`_PHASES` generalization now
# gives modify_card_energy_cost a real plain-then-Late two-pass structure for
# free. Re-confirmed narrowly here: the phase machinery exists and dispatches
# this exact hook.
# ══════════════════════════════════════════════════════════════════════════

def test_spiked_gauntlets_g2_modify_card_energy_cost_now_dispatches_through_each():
    """Direct source check: HookSystem.modify_card_energy_cost calls
    `self._each('modify_card_energy_cost')`, the same phase-aware dispatcher
    every multi-pass hook uses -- not a flat single-pass walk as the audit
    (and the record's still-unrefreshed G2 guard text) describe."""
    from sts2_rl.hooks import HookSystem
    src = inspect.getsource(HookSystem.modify_card_energy_cost)
    assert '_each("modify_card_energy_cost")' in src


def test_spiked_gauntlets_g3_still_no_x_cost_power_cards_exist():
    """G3 re-confirmed dormant: still zero X-cost Power cards in the pool, so
    the sim's missing `originalCost < 0` bail and its extra terminal
    max(0, cost) clamp remain unreachable together."""
    from sts2_rl.cards import CardType
    from sts2_rl.cards.base import _CARD_CLASSES

    x_cost_powers = [
        cid for cid, cls in _CARD_CLASSES.items()
        if getattr(make_card(cid), "energy_cost_x", False)
        and cls.card_type == CardType.POWER
    ]
    assert x_cost_powers == []


# ══════════════════════════════════════════════════════════════════════════
# relic/stone_calendar/BeforeSideTurnEnd
#
# FINDING: same shape as gremlin_horn's -- the hooks-level rollup ("the
# divergences are the flattened sub-phase ordering (G1) and the
# living_enemies-vs-HittableEnemies set (G2)") is STALE. The guards array
# already shows G1 'Closed 2026-07-27' (the `_each` VeryEarly/Early/plain
# phase walk). Only G2 remains, and it is dormant for the identical
# DamageCmd.deal is_dead-guard reason as charons_ashes/festive_popper.
# ══════════════════════════════════════════════════════════════════════════

def test_stone_calendar_g1_on_player_turn_end_now_phases_through_each():
    """G1 re-confirmed closed: on_player_turn_end dispatches through the
    same phase-aware `_each`, so a VeryEarly/Early listener (Orichalcum's
    snapshot, Pael's Eye's exhaust) is guaranteed to run before Stone
    Calendar's plain-pass damage."""
    from sts2_rl.hooks import HookSystem
    src = inspect.getsource(HookSystem.on_player_turn_end)
    assert '_each("on_player_turn_end")' in src


def test_stone_calendar_g2_deals_full_damage_and_backstops_at_is_dead():
    """G2 re-confirmed dormant via the same mechanism as charons_ashes: a
    turn-7 Stone Calendar hits every living enemy for 52, and a corpse in
    living_enemies() (impossible for a reachable creature, per the
    set-coincidence argument) would take 0 from DamageCmd.deal's own
    is_dead guard regardless."""
    cs = _combat(["stone_calendar"], seed=209, enemy_count=2)
    cs.enemies[0].hp = 9999
    cs.enemies[1].hp = 9999
    relic = cs.relics[0]
    cs.turn = relic.DAMAGE_TURN
    relic.on_player_turn_end(cs.player)
    assert cs.enemies[0].hp == 9999 - 52
    assert cs.enemies[1].hp == 9999 - 52


# ══════════════════════════════════════════════════════════════════════════
# relic/stone_cracker/AfterRoomEntered and relic/sword_of_jade/AfterRoomEntered
#
# Both G2/G1 (AfterRoomEntered-vs-on_combat_start dispatch slot) already
# carry round-13 R8 pinning tests in test_r13_relic2.py. Re-executed here
# narrowly, with the census re-run rather than re-read.
# ══════════════════════════════════════════════════════════════════════════

def test_stone_cracker_g2_only_two_on_combat_start_listeners_touch_the_draw_pile():
    """Re-run of the pool-wide census this round, not inherited: of the
    sim's on_combat_start implementers (relics + the two powers.py ones),
    only stone_cracker (AfterRoomEntered side) and tea_of_discourtesy
    (BeforeCombatStart side) touch the draw pile, and they draw from
    different RNG streams (CombatCardSelection vs Shuffle) and neither
    changes the pile's SIZE in a way the other reads -- so their relative
    order inside the sim's single on_combat_start walk cannot matter."""
    from sts2_rl.relics import ALL_RELICS

    patterns = ("draw_pile", "add_to_draw")
    touches_draw_pile = []
    for rid, cls in ALL_RELICS.items():
        fn = cls.__dict__.get("on_combat_start")
        if fn is None:
            continue
        src = inspect.getsource(fn)
        if any(p in src for p in patterns):
            touches_draw_pile.append(rid)
    assert sorted(touches_draw_pile) == ["stone_cracker", "tea_of_discourtesy"]


def test_sword_of_jade_g1_pool_wide_after_room_entered_relics_still_the_same_twelve():
    """G1's census re-run: the twelve relics whose C# combat effect hangs off
    AfterRoomEntered and is mapped onto the sim's on_combat_start are
    unchanged from the audit's list, so the same reachability argument
    (nothing on the BeforeCombatStart side reads or contests Strength)
    still applies to today's tree."""
    from sts2_rl.relics import ALL_RELICS

    after_room_entered_side = {
        "bronze_scales", "ember_tea", "ghost_seed", "girya", "gorget",
        "oddly_smooth_stone", "philosophers_stone", "red_skull",
        "stone_cracker", "sword_of_jade", "throwing_axe", "vajra",
    }
    assert after_room_entered_side <= set(ALL_RELICS)
    cs = _combat(["sword_of_jade"], seed=210)
    assert cs.player.powers["strength"].amount == 3
