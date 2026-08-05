"""Round 13 (R4) — settling the `relic-1` unlabelled batch.

Each test below pins one of the report's executed claims: a re-confirmed
DORMANT reachability census, a STALE-ALREADY-FIXED behavioural check (the
mechanism the record's `issue` text still described has since been fixed by
other lanes in this round), or a fresh-execution demonstration of a guard's
mechanism.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cards.base import _CARD_CLASSES
from sts2_rl.cmds import CreatureCmd, DamageCmd, EnergyCmd, PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.run import RunState
from sts2_rl.valueprops import DamageProps


def _combat(relic_ids=(), hand=(), seed: int = 0) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test", [LeafSlimeS]),
                     relics=[make_relic(r) for r in relic_ids])
    cs.player.hand.clear()
    for cid in hand:
        card = make_card(cid)
        card.combat = cs
        cs.hooks.register(card)
        cs.player.hand.append(card)
    return cs


# ══════════════════════════════════════════════════════════════════════════
# relic/pen_nib/AfterCardPlayed — G3 flips DORMANT -> STALE-ALREADY-FIXED.
#
# combat.py's `_resolve_card_play` now gates `hooks.on_card_played` on
# `not self.is_over` (combat.py:986-987), and `_check_win_condition` (which
# sets Phase.COMBAT_OVER) is only called by the OUTER `play_card`/`auto_play`
# AFTER `_resolve_card_play` returns (combat.py:863, 880) — never from inside
# DamageCmd.deal itself. So on the very iteration whose Attack lands the
# killing blow, `self.is_over` is still False when `on_card_played` fires,
# exactly mirroring C#'s CardModel.cs:1957 `IsInProgress` gate (which stays
# true until `CheckWinCondition` runs after the whole play action —
# Hook.cs:275-276's own comment: "it completes resolution of the card that
# caused the kill"). Pen Nib's own on_card_played therefore DOES clear the
# mark on the combat-ending 10th Attack, matching the game.
# ══════════════════════════════════════════════════════════════════════════

def test_pen_nib_tenth_attack_that_ends_combat_still_unmarks():
    cs = _combat(["pen_nib"], hand=["strike"], seed=1)
    relic = cs.relics[0]
    relic._attacks_played = 9  # priming: next Attack played is the 10th
    cs.enemies[0].hp = 1       # any powered hit kills it
    cs.play_card(0)
    assert cs.is_over is True
    # The mark must be cleared, not left stuck for the NEXT combat's first
    # Attack (which would double it for free — the exact bug G3 predicted
    # under the record's now-superseded reading of the C# gate).
    assert relic._card_to_double is None


# ══════════════════════════════════════════════════════════════════════════
# relic/unsettling_lamp/BeforePowerAmountChanged
#
# G2 (sign-aware GetTypeForAmount) is now CLOSED: seam/power_cmd.json's own
# G2 guard shows "Closed 2026-07-31" and unsettling_lamp.py's current
# modify_power_amount_given_multiplicative uses `power_cls.type_for_amount
# (amount) != PowerType.DEBUFF` with NO `amount <= 0` bail. Demonstrated here
# with a synthetic negative-amount AllowNegative-buff application (the
# Malaise/Resonance shape), since neither card is ported.
#
# G3 (no target-side/applier check on the C# multiplicative pass) is STILL A
# REAL, UNREACHABLE divergence: UnsettlingLamp.cs's
# ModifyPowerAmountGivenMultiplicative (lines 106-129) has NO target/applier
# guard at all — only the LATCH (BeforePowerAmountChanged, lines 85, 89)
# does. The sim's modify_power_amount_given_multiplicative re-applies
# `applier is not self.player or target is self.player` on every call
# (unsettling_lamp.py), so a SECOND application from the SAME triggering
# card that targets the player (or has a non-player applier) is NOT doubled
# in the sim where C# would double it. No ported card debuffs both an enemy
# and the player in one play (battle_trance/doubt/expect_a_fight/
# panic_button/shame/the_gambit all debuff ONLY the player and never an
# enemy), so this stays dormant.
# ══════════════════════════════════════════════════════════════════════════

def test_unsettling_lamp_doubles_a_negative_amount_buff_sign_aware():
    """G2 closed: a negative-amount, AllowNegative Buff (Strength) applied
    to an enemy is a Debuff by GetTypeForAmount's rule and gets doubled."""
    from sts2_rl.powers import StrengthPower

    cs = _combat(["unsettling_lamp"], hand=["strike"], seed=2)
    relic = cs.relics[0]
    card = cs.player.hand[0]
    relic.before_card_played(card)
    PowerCmd.apply(cs.hooks, cs.enemies[0], StrengthPower, -3, applier=cs.player)
    # -3 Strength (AllowNegative, sign-flips to Debuff) doubles to -6.
    assert cs.enemies[0].powers["strength"].amount == -6


def test_unsettling_lamp_g3_same_card_self_debuff_not_doubled_dormant():
    """G3 still open: after the SAME triggering card also debuffs the
    player, C# would double it too (no target check on the multiplicative
    pass) but the sim's own applier/target re-check refuses it. Executed to
    pin the divergence's existence, not because any ported card reaches it."""
    from sts2_rl.powers import WeakPower

    cs = _combat(["unsettling_lamp"], hand=["strike"], seed=3)
    relic = cs.relics[0]
    card = cs.player.hand[0]
    relic.before_card_played(card)
    # First: an owner-applied enemy debuff latches TriggeringCard (=card).
    PowerCmd.apply(cs.hooks, cs.enemies[0], WeakPower, 1, applier=cs.player)
    assert cs.enemies[0].powers["weak"].amount == 2  # confirms the latch fired
    # Second, same card still resolving: a debuff aimed at the PLAYER.
    # UnsettlingLamp.cs's multiplicative has no target check, so C# would
    # double this too; the sim's applier/target re-check declines it.
    factor = relic.modify_power_amount_given_multiplicative(
        WeakPower, cs.player, 1, cs.player,
    )
    assert factor == 1  # sim declines — the still-open, unreachable half of G3


# ══════════════════════════════════════════════════════════════════════════
# relic/fur_coat/AfterCreatureAddedToCombat
#
# CITATION CORRECTION (not in the brief): the record's divergence (a) reads
# `CombatManager.StartCombatInternal`'s `foreach (...) await
# AfterCreatureAdded(creature)` loop (CombatManager.cs:394-398) as dispatching
# `Hook.AfterCreatureAddedToCombat`. It does not: `CombatManager.
# AfterCreatureAdded` (CombatManager.cs:860-867) only calls
# `creature.AfterAddedToRoom()` and rolls the opening move — it never calls
# `Hook.AfterCreatureAddedToCombat`. The ONLY C# dispatch of that hook is
# `CreatureCmd.cs:81`, inside `CreatureCmd.Add` — the mid-combat path, exactly
# where the sim's `hooks.on_creature_added` already lives (cmds.py's
# `CreatureCmd.add`). There is no starting-creature dispatch to be "shadowed"
# on either side; both codebases agree structurally, not by coincidence.
#
# R4-review.md defect D1: the original version of this test registered its
# spy AFTER `_combat(...)` had already built the CombatState, so the
# "zero calls during construction" half could never fail — the spy did not
# exist yet to observe anything. Fixed by wrapping `HookSystem.
# on_creature_added` itself (a class-level monkeypatch) BEFORE construction,
# so the counter is live for the whole starting-roster build.
# ══════════════════════════════════════════════════════════════════════════

def test_on_creature_added_hook_never_fires_for_starting_enemies():
    import sts2_rl.hooks as hooks_mod

    calls = []
    original = hooks_mod.HookSystem.on_creature_added

    def _spy(self, creature):
        calls.append(creature)
        return original(self, creature)

    hooks_mod.HookSystem.on_creature_added = _spy
    try:
        # The spy is live for the ENTIRE construction, including the
        # StartCombatInternal-equivalent starting-roster build — so this can
        # actually observe a call, unlike the defective version.
        cs = _combat(["fur_coat"], seed=4)
        assert calls == []  # starting enemy never reached on_creature_added

        joiner = LeafSlimeS(cs.hooks, random.Random(5))
        CreatureCmd.add(cs.hooks, joiner)
        assert calls == [joiner]  # mid-combat CreatureCmd.add is the only path
    finally:
        hooks_mod.HookSystem.on_creature_added = original


# ══════════════════════════════════════════════════════════════════════════
# relic/lizard_tail/ShouldDieLate + AfterPreventingDeath
#
# STALE-ALREADY-FIXED: both hook-level rollups' `issue` text still says
# "WHAT REMAINS is guard G3", but G3's own guard entry in the same JSON file
# already reads "Closed 2026-07-29 (round 8)" — the hook-level summary was
# simply never updated after the guard closed. Re-verified against TODAY's
# cmds.py._resolve_death (which round 12 and later tier-2 Task 19 both
# touched): should_die_late is a pure predicate, and the charge/heal are set
# only in after_preventing_death, dispatched from the prevented-death arm.
# ══════════════════════════════════════════════════════════════════════════

def test_lizard_tail_should_die_late_is_a_pure_predicate():
    cs = _combat(["lizard_tail"], seed=6)
    relic = cs.relics[0]
    for _ in range(3):
        assert relic.should_die_late(cs.player) is False
    assert relic.is_used_up is False  # querying alone never spends the charge


def test_lizard_tail_charge_spent_and_healed_only_in_after_preventing_death():
    cs = _combat(["lizard_tail"], seed=7)
    relic = cs.relics[0]
    cs.player.hp = 1
    DamageCmd.deal(cs.hooks, cs.player, 999, dealer=cs.enemies[0],
                    props=DamageProps.NON_CARD_UNPOWERED)
    assert relic.is_used_up is True
    assert cs.player.hp == cs.player.max_hp * 50 // 100
    assert not cs.player.is_dead


# ══════════════════════════════════════════════════════════════════════════
# relic/archaic_tooth/AfterObtained — G1/G2 dormancy re-confirmed against
# TODAY's ported content.
# ══════════════════════════════════════════════════════════════════════════

def test_no_ported_card_has_an_upgrade_level_above_one():
    """G1's dormancy premise: C# grants exactly one upgrade level regardless
    of how many the original had, so a card with max_upgrade_level > 1 is
    needed to observe the sim's `for _ in range(original.upgrade_level)`
    loop over-granting. None exists."""
    above_one = [cid for cid, cls in _CARD_CLASSES.items()
                 if getattr(cls, "max_upgrade_level", 1) > 1]
    assert above_one == []


def test_no_enchantment_discriminates_bash_from_break():
    """G2's dormancy premise: every ported enchantment's can_enchant either
    agrees on Bash and Break (both CardType.ATTACK) or excludes both (Bash
    carries no tags and is not X-cost/exhausting/gains_block/Skill), so no
    enchantment can attach to one but not the other."""
    from sts2_rl.enchantments import _ENCHANTMENT_CLASSES

    bash = make_card("bash")
    break_card = make_card("break")
    for cls in _ENCHANTMENT_CLASSES.values():
        assert cls.can_enchant(bash) == cls.can_enchant(break_card), cls


# ══════════════════════════════════════════════════════════════════════════
# relic/booming_conch/AfterSideTurnStart — G2 dormancy re-confirmed: the
# grant still bypasses hooks.modify_energy_gain, and NoEnergyGainPower still
# expires at the OWNER's turn end, before Booming Conch (turn<=1) could ever
# see it applied by a played card.
# ══════════════════════════════════════════════════════════════════════════

def test_booming_conch_energy_grant_bypasses_modify_energy_gain_chain():
    from sts2_rl.powers import NoEnergyGainPower

    cs = _combat(["booming_conch"], seed=8)
    from sts2_rl.rooms import RoomType
    cs.room_type = RoomType.ELITE
    PowerCmd.apply(cs.hooks, cs.player, NoEnergyGainPower, 1, applier=cs.player)
    before = cs.player.energy
    cs.relics[0].after_side_turn_start(cs.player)
    # A real EnergyCmd.gain would have been reduced to 0 by NoEnergyGainPower.
    assert cs.player.energy == before + 1


# ══════════════════════════════════════════════════════════════════════════
# relic/{fake_strike_dummy,strike_dummy,miniature_cannon} — the dealer==None
# guard's *reachability* is still dormant/unobservable (every ported
# Strike-tagged card, and every ported Upgraded-Attack-dealing path, passes
# dealer=player), but R8 fixed the guard's *output* under a null dealer: the
# sim's `Card` has no `owner` field, so `cardSource.Owner == Owner`
# (StrikeDummy.cs:33-36 / FakeStrikeDummy.cs:35-38) is unconditionally true
# and the AND-of-negatives guard can never both hold -- C# would never
# decline on dealer grounds alone, so `with_none` now equals `with_player`.
# ══════════════════════════════════════════════════════════════════════════

def test_strike_tagged_cards_all_deal_damage_with_the_player_as_dealer():
    """R4-review.md defect D3: the original version of this test asserted
    only `len(strike_tagged) == 8` -- a content count, not the dealer claim
    its name and docstring promise. Fixed to actually PLAY each of the 8
    Strike-tagged cards (through `cs.play_card`, the public API) with
    `DamageCmd.deal` wrapped to record every `dealer=` argument it is
    called with, and assert every recorded dealer, for every card, is the
    acting player."""
    import sts2_rl.cmds as cmds_mod

    strike_tagged = [cid for cid, cls in _CARD_CLASSES.items()
                      if "strike" in getattr(cls, "tags", frozenset())]
    assert len(strike_tagged) == 8

    # `DamageCmd.deal` is a @staticmethod; attribute access on the class
    # already unwraps it to the plain function, so keep the RAW class-dict
    # entry for the restore. Restoring the unwrapped function instead would
    # replace the descriptor permanently, for every test that runs after this
    # one -- which is exactly what broke a sibling lane's suite run (an
    # `AttributeError` from `DamageCmd.__dict__["deal"].__func__`).
    original_deal = cmds_mod.DamageCmd.deal
    original_deal_entry = cmds_mod.DamageCmd.__dict__["deal"]

    for card_id in strike_tagged:
        recorded_dealers = []

        def _spy_deal(hooks, target, amount, dealer=None, card=None,
                      props=None, result=None, _orig=original_deal):
            recorded_dealers.append(dealer)
            return _orig(hooks, target, amount, dealer=dealer, card=card,
                         props=props, result=result)

        cmds_mod.DamageCmd.deal = staticmethod(_spy_deal)
        try:
            cs = _combat(hand=[card_id], seed=20)
            # Extra draw-pile padding: `_combat` clears the initial hand
            # without returning it to the draw pile, and pommel_strike /
            # seeker_strike each draw or offer cards mid-resolution.
            cs.player.draw_pile.extend(make_card("strike") for _ in range(10))
            assert cs.play_card(0) is True, card_id
        finally:
            cmds_mod.DamageCmd.deal = original_deal_entry

        assert recorded_dealers, card_id  # the card really dealt damage
        assert all(d is cs.player for d in recorded_dealers), (card_id, recorded_dealers)


def test_fake_strike_dummy_and_strike_dummy_miss_a_null_dealer_strike():
    cs = _combat(["fake_strike_dummy"], seed=9)
    strike = make_card("strike")
    strike.combat = cs
    base = 6
    with_player = cs.hooks.modify_damage_additive(
        cs.enemies[0], base, cs.player, strike, props=DamageProps.CARD)
    with_none = cs.hooks.modify_damage_additive(
        cs.enemies[0], base, None, strike, props=DamageProps.CARD)
    assert with_player == base + 1   # FakeStrikeDummy.EXTRA_DAMAGE
    assert with_none == base + 1   # FakeStrikeDummy.EXTRA_DAMAGE


def test_strike_dummy_misses_a_null_dealer_strike():
    cs = _combat(["strike_dummy"], seed=12)
    strike = make_card("strike")
    strike.combat = cs
    base = 6
    with_player = cs.hooks.modify_damage_additive(
        cs.enemies[0], base, cs.player, strike, props=DamageProps.CARD)
    with_none = cs.hooks.modify_damage_additive(
        cs.enemies[0], base, None, strike, props=DamageProps.CARD)
    assert with_player == base + 3   # StrikeDummy.EXTRA_DAMAGE
    assert with_none == base + 3   # StrikeDummy.EXTRA_DAMAGE -- card ownership always == player in this sim, so dealer no longer gates it
    # G2's other disjunct: C# also fires when `cardSource.Owner == Owner`,
    # which the sim's Card has no owner concept to consult at all — the same
    # missing alternative, from the other side.


def test_miniature_cannon_misses_a_null_dealer_upgraded_attack():
    cs = _combat(["miniature_cannon"], seed=10)
    strike = make_card("strike")
    strike.combat = cs
    strike.upgrade()
    base = 6
    with_player = cs.hooks.modify_damage_additive(
        cs.enemies[0], base, cs.player, strike, props=DamageProps.CARD)
    with_none = cs.hooks.modify_damage_additive(
        cs.enemies[0], base, None, strike, props=DamageProps.CARD)
    assert with_player == base + 3   # MiniatureCannon.EXTRA_DAMAGE
    assert with_none == base         # dormant divergence: C# would still add 3


# ══════════════════════════════════════════════════════════════════════════
# relic/{kusarigama,stone_calendar} — G2 dormancy re-confirmed: living_enemies
# includes an is_reviving (mid-revival) creature's exclusion only via is_dead,
# and every ported should_allow_hitting implementer's False case coincides
# with is_dead=True, so living_enemies() and hittable_enemies() never
# disagree on any creature currently reachable in ported content.
#
# R4-review.md defect D2: the original version of this test never called
# `should_allow_hitting`, `hittable_enemies`, or `living_enemies`-equivalent
# at all, exercised only 1 of the 3 implementers (AdaptablePower was
# imported and unused), and its two assertions restated a value the test
# itself had just assigned (`enemy.hp = 0` then `assert enemy.is_dead`).
# Fixed to actually drive each of the 3 implementers to `is_reviving` through
# a REAL lethal `DamageCmd.deal` (not a hand-set hp + direct `on_death`
# call), then call `cs.hooks.should_allow_hitting` directly and compare the
# `living_enemies()`-equivalent set against `cs.hittable_enemies` for real.
# ══════════════════════════════════════════════════════════════════════════

def test_should_allow_hitting_false_always_coincides_with_is_dead():
    """The should_allow_hitting implementers census: IllusionPower,
    AdaptablePower and ReattachPower (the Decimillipede-segment power) all
    gate their False case on `is_reviving`, which is only ever armed by
    `on_death` -- reached here through a REAL, lethal `DamageCmd.deal`, the
    same pipeline kusarigama/stone_calendar's own damage goes through, not a
    hand-set hp + direct `on_death` shortcut -- alongside hp<=0 (is_dead).
    So `living_enemies()`'s `is_gone` filter (is_dead or escaped) already
    excludes anything `hittable_enemies()` (which additionally consults
    `should_allow_hitting`) would exclude through any of the three, and
    kusarigama/stone_calendar's `living_enemies()` draw cannot diverge from
    `hittable_enemies()` through them. Exercises `should_allow_hitting` AND
    both enemy-list builders directly, for all three implementers."""
    from sts2_rl.monsters import TEST_SUBJECT_BOSS, DECIMILLIPEDE_ELITE
    from sts2_rl.powers import IllusionPower

    def _living(combat):
        return {e for e in combat.enemies if not e.is_gone}

    # IllusionPower -- applied directly to a plain monster; a second,
    # untouched enemy proves the two lists agree on WHO stays hittable too,
    # not only on the reviving creature.
    cs = CombatState(rng=random.Random(11),
                      encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]))
    reviver, spectator = cs.enemies
    PowerCmd.apply(cs.hooks, reviver, IllusionPower, 1, applier=reviver)
    DamageCmd.deal(cs.hooks, reviver, 99999, dealer=cs.player)
    illusion = reviver.powers.get("illusion")
    assert illusion is not None and illusion.is_reviving is True
    assert cs.hooks.should_allow_hitting(reviver) is False
    assert cs.hooks.should_allow_hitting(spectator) is True
    assert _living(cs) == set(cs.hittable_enemies) == {spectator}

    # AdaptablePower -- Test Subject applies it to itself on construction
    # (test_subject.py:61, TestSubject.__init__).
    cs2 = CombatState(rng=random.Random(14), encounter=TEST_SUBJECT_BOSS)
    boss = cs2.enemies[0]
    spectator2 = LeafSlimeS(cs2.hooks, random.Random(24))
    CreatureCmd.add(cs2.hooks, spectator2)
    DamageCmd.deal(cs2.hooks, boss, 99999, dealer=cs2.player)
    adaptable = boss.powers.get("adaptable")
    assert adaptable is not None and adaptable.is_reviving is True
    assert cs2.hooks.should_allow_hitting(boss) is False
    assert cs2.hooks.should_allow_hitting(spectator2) is True
    assert _living(cs2) == set(cs2.hittable_enemies) == {spectator2}

    # ReattachPower -- Decimillipede's 3 segments all carry it from
    # construction; killing one while its siblings live arms is_reviving (a
    # SOLO segment would short-circuit `_all_others_down()` and never revive
    # at all -- see decimillipede.py's `ReattachPower.on_death`).
    cs3 = CombatState(rng=random.Random(15), encounter=DECIMILLIPEDE_ELITE)
    victim, sibling_a, sibling_b = cs3.enemies
    DamageCmd.deal(cs3.hooks, victim, 99999, dealer=cs3.player)
    reattach = victim.powers.get("reattach")
    assert reattach is not None and reattach.is_reviving is True
    assert cs3.hooks.should_allow_hitting(victim) is False
    assert cs3.hooks.should_allow_hitting(sibling_a) is True
    assert _living(cs3) == set(cs3.hittable_enemies) == {sibling_a, sibling_b}


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
