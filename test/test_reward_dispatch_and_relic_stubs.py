"""Task 31 — two relic-tier mechanisms audited together:

  A. relic/_reward_late_pass (Driftwood, Glitter, Molten Egg): whether
     `Hook.ModifyRewards` (RewardsSet.cs:136, called from EVERY RewardsSet —
     RewardsCmd.cs's four factory methods and NeowsBones.cs) is dispatched at
     every sim site that builds a rewards set. The combat path
     (`generate_combat_rewards` -> `apply_reward_modifiers`,
     sts2_rl/rewards.py) and the rest-site path (`RunState.rest_heal_rewards`,
     sts2_rl/run.py:1398-1420) both already call `apply_reward_modifiers`
     today — this file's Driftwood test pins that the rest-site path (the gap
     the record named) really does carry the reroll flag now. Glitter's and
     Molten Egg's entries under the same mechanism id are a DIFFERENT guard
     (TryModifyCardRewardOptions/Late — a different hook, dispatched from
     CardFactory.cs:104, not RewardsSet.cs) that was already correctly
     narrowed to DORMANT for its own, unrelated reason; this file re-pins
     both by execution rather than changing anything.

  B. relic/_stub (Bing Bong g1, Massive Scroll g4, Punch Dagger g1, Royal
     Stamp g1) — four different relics sharing nothing but a mechanism label.
     Bing Bong and Massive Scroll are genuinely still DORMANT stubs (pinned
     here); Punch Dagger is still blocked on an unported enchantment (Momentum
     — pinned here, plus a docstring correction: the "17" registered count it
     cited is stale, sts2_rl/enchantments.py now registers 19); Royal Stamp
     is NOT a stub any more — sts2_rl/relics/royal_stamp.py already has a full
     `after_obtained` (Niche shuffle + RoyallyApproved enchant) and is already
     covered by test/test_shared_enchantments.py::
     test_royal_stamp_enchants_a_deck_card_and_burns_the_niche_shuffle, so
     this file does not duplicate it — see the task report for the
     right-reason-RED check run directly against that existing test.
"""
from __future__ import annotations

import random

from sts2_rl.cards import CardType, make_card
from sts2_rl.relics import make_relic
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# A. relic/_reward_late_pass
# ═════════════════════════════════════════════════════════════════════════

def test_driftwood_reroll_reaches_rest_site_card_reward():
    """relic/driftwood/TryModifyRewardsLate guard G1.

    C#: HealRestSiteOption.ExecuteRestSiteHeal (HealRestSiteOption.cs:106-113)
    calls Hook.ModifyRestSiteHealRewards, THEN
    `await RewardsCmd.OfferCustom(player, rewards)` — which is
    `new RewardsSet(player).WithCustomRewards(rewards).Offer()`
    (RewardsCmd.cs:47-50) — whose Offer -> GenerateWithoutOffering runs
    `Hook.ModifyRewards` (RewardsSet.cs:136), the plain-then-Late pass
    Driftwood implements. Driftwood.TryModifyRewardsLate does not check
    `room` (Driftwood.cs:16-25), so it fires on this custom, room-less set
    exactly like it does on a combat screen: EVERY CardReward on the set
    becomes rerollable.

    Sim witness: Dream Catcher is the one ported relic that puts a
    CardRewardGroup on RunState.rest_heal_rewards' screen
    (relics/dream_catcher.py). With Driftwood also held, that group's
    can_reroll must come back True.
    """
    run = fresh_run(11)
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]
    run.add_relic("dream_catcher")
    run.add_relic("driftwood")

    rewards = run.rest_heal_rewards()

    assert len(rewards.card_rewards) == 1
    assert rewards.card_rewards[0].cards          # Dream Catcher populated it
    assert rewards.can_reroll, (
        "Driftwood held + Dream Catcher's rest-site CardReward should be "
        "rerollable (RewardsSet.cs:136 fires Hook.ModifyRewards on every "
        "RewardsSet, including a custom rest-heal one) — came back "
        "can_reroll=False"
    )


def test_no_driftwood_rest_site_card_reward_is_not_rerollable():
    """Control for the test above: without Driftwood, Dream Catcher's rest
    reward is an ordinary, non-rerollable CardReward."""
    run = fresh_run(11)
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]
    run.add_relic("dream_catcher")

    rewards = run.rest_heal_rewards()

    assert rewards.card_rewards[0].cards
    assert not rewards.can_reroll


def test_glitter_g1_still_enchants_the_option_card_in_place():
    """relic/glitter/TryModifyCardRewardOptionsLate guard G1 — re-verified,
    unchanged. C#: Glitter.cs:26-32 clones the option
    (`RunState.CloneCard(card)`), enchants the CLONE, then
    `cardReward.ModifyCard(card2, this)` swaps it into the offer. The sim
    (relics/glitter.py:16-21) enchants the SAME object in place instead of
    substituting a clone. DORMANT for the reason the record gives: a reward
    option is a freshly created card with no pre-existing per-instance state
    (no enchantment, no upgrade) to lose by being mutated in place instead of
    replaced — so the two are observably identical. Pinned here as an
    object-identity fact rather than asserted from reading the source.
    """
    run = fresh_run(12)
    run.add_relic("glitter")
    card = make_card("strike")
    cards = [card]
    run.relics[-1].modify_card_reward_options_late(run, cards)
    # The port mutates card in place: the list still holds the SAME object.
    assert cards[0] is card
    assert card.enchantment is not None and card.enchantment.id == "glam"


def test_molten_egg_g4_no_ported_card_is_both_upgraded_and_upgradable():
    """relic/molten_egg/TryModifyCardRewardOptionsLate guard G4 — re-verified,
    unchanged. C#'s reward/merchant hooks (MoltenEgg.cs:21-41) delegate to
    EggRelicHelper.UpgradeValidCards, whose only test is `Type == cardType &&
    IsUpgradable` (EggRelicHelper.cs:15) — no upgrade-level check; only the
    deck-add hook (MoltenEgg.cs:56-61) checks `CurrentUpgradeLevel >= 1`. The
    sim's `_eggs.py:_applies` applies the level filter (ONLY_UNUPGRADED) on
    all three paths alike, so it would wrongly skip an already-upgraded
    Attack on a reward/merchant screen. DORMANT while `is_upgradable` is
    `upgrade_level < max_upgrade_level` (cards/base.py:209-211) and no ported
    card raises `max_upgrade_level` above the default of 1 — so a card that
    IS already upgraded is never `is_upgradable` either, and `_applies`'s
    `card_type`/`is_upgradable` test alone (with or without the extra
    ONLY_UNUPGRADED clause) already filters it out. Pinned by executing the
    reward-options hook on a pre-upgraded Strike.
    """
    run = fresh_run(13)
    run.add_relic("molten_egg")
    strike = make_card("strike")
    strike.upgrade()
    assert not strike.is_upgradable, (
        "premise of the DORMANT verdict: an already-upgraded ported card "
        "must not be upgradable, or G4 would be observable today"
    )
    cards = [strike]
    run.relics[-1].modify_card_reward_options_late(run, cards)
    assert strike.upgrade_level == 1          # left alone either way


# ═════════════════════════════════════════════════════════════════════════
# B. relic/_stub
# ═════════════════════════════════════════════════════════════════════════

def test_bing_bong_g1_clones_indiscriminately_no_adder_tracked():
    """relic/bing_bong/g1 (DORMANT) — re-verified.

    C#: BingBong.AfterCardChangedPiles(card, oldPileType, clonedBy) skips
    cloning when `clonedBy != null` (BingBong.cs:25) — the source's ONLY
    other non-null `clonedBy` setter anywhere in the codebase is Hoarder
    (src/Core/Models/Modifiers/Hoarder.cs:26), a custom-run `ModifierModel`;
    the sim has no Modifier system at all (out of scope). Every other
    `CardPileCmd.Add(..., PileType.Deck, ...)` call site in the decompiled
    source — including the one other ported deck-cloner, Dolly's Mirror
    (DollysMirror.cs:22, `CardPileCmd.Add(card, PileType.Deck)` with no 4th
    argument) — passes clonedBy=null (the parameter default,
    CardPileCmd.cs:259). So today, in the ported scope, there is no C# model
    whose clonedBy the sim's missing adder argument would need to see:
    BingBong's own recursion guard (its CardsToSkip half) is airtight for
    BingBong's own chain, and no other relic would ever ask C#'s BingBong to
    skip a clone. The sim's `after_card_added_to_deck(self, run, card)`
    signature stays as-is; threading an adder through it is deferred as an
    honest documented dormant gap, not fixed here (see task report).

    NOTE this corrects the record's own reachability suggestion — "porting
    Dolly's Mirror... makes it live" — which is now stale: Dolly's Mirror IS
    ported (relics/dollys_mirror.py) and it still does not move the verdict,
    because DollysMirror.cs never sets clonedBy either.
    """
    run = fresh_run(14)
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]
    run.add_relic("bing_bong")
    run.add_relic("dollys_mirror")            # the only other ported cloner
    deck_before = len(run.deck)

    run.add_card(make_card("strike"))
    # BingBong clones the plain add: +1 original, +1 BingBong clone.
    assert len(run.deck) - deck_before == 2

    deck_before = len(run.deck)
    dolly = next(r for r in run.relics if r.id == "dollys_mirror")
    dolly.after_obtained(run)
    # Dolly's Mirror adds one clone of an existing deck card, and BingBong
    # (seeing an ordinary, non-BingBong-tagged deck-add, exactly as C# would
    # since DollysMirror.cs never sets clonedBy) clones THAT too: +2, matching
    # what C# would also do here — this is not a divergence, just the
    # observable shape of today's DORMANT verdict.
    assert len(run.deck) - deck_before == 2


def test_massive_scroll_is_never_offerable_and_after_obtained_is_absent():
    """relic/massive_scroll/g4 (DORMANT) — re-verified.

    MassiveScroll.cs:19-22's `IsAllowed` is `runState.Players.Count > 1`
    (multiplayer only); the port's `is_allowed` mirrors it exactly and always
    returns False in the sim's single-player-only model
    (relics/massive_scroll.py). `AfterObtained` (MassiveScroll.cs:24-42) pulls
    from `CardMultiplayerConstraint.MultiplayerOnly`-tagged cards — a card
    subset the sim has never ported (`grep -rn MultiplayerOnly sts2_rl/`
    matches nothing) — so implementing `after_obtained` today would still
    have no real candidate pool to draw from. The port declares no
    `after_obtained` at all, so a caller that bypasses `is_allowed` (a test
    fixture, a resync granting it by id) would silently do nothing instead of
    offering the 3-card choice — pinned here as today's actual behavior,
    not fixed: the gap is real but permanently unreachable through the
    sim's own single-player pool gate, same verdict as the parent record.
    """
    run = fresh_run(15)
    from sts2_rl.relics import ALL_RELICS

    assert ALL_RELICS["massive_scroll"].is_allowed(run) is False

    relic = make_relic("massive_scroll")
    deck_before = len(run.deck)
    relic.after_obtained(run)                 # base Relic.after_obtained: no-op
    assert len(run.deck) == deck_before, (
        "documented stub: granting Massive Scroll outside the pool gate is "
        "silent, not an error and not the 3-card choice C# offers"
    )


def test_punch_dagger_g1_still_blocked_on_unported_momentum():
    """relic/punch_dagger/g1 (DORMANT) — re-verified.

    PunchDagger.cs:24-33 enchants a chosen deck card with Momentum (amount 5,
    `DynamicVar("Momentum", 5m)`, PunchDagger.cs:15-19). Momentum is still not
    among sts2_rl/enchantments.py's registered enchantments (now 19, not the
    17 the port's old docstring cited — corrected there this task), so
    PunchDagger still declares no `after_obtained` and is a genuine no-op.
    """
    from sts2_rl.enchantments import ALL_ENCHANTMENTS

    assert "momentum" not in ALL_ENCHANTMENTS
    assert len(ALL_ENCHANTMENTS) == 19

    run = fresh_run(16)
    from sts2_rl.relics.base import Relic
    from sts2_rl.relics.punch_dagger import PunchDagger

    # PunchDagger declares no `after_obtained` override at all — confirms the
    # docstring's "STILL A NO-OP" claim structurally, not just behaviorally.
    assert "after_obtained" not in PunchDagger.__dict__

    deck_before = [c.enchantment for c in run.deck]
    relic = make_relic("punch_dagger")
    Relic.after_obtained(relic, run)           # the inherited no-op
    assert [c.enchantment for c in run.deck] == deck_before
