"""Five live event residues from round 7's tail.

event/brain_leech/g3, event/fake_merchant/g3, event/morphic_grove/EV-10,
event/orobas/g6, event/trial/g8.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.cards import make_card
from sts2_rl.run import RunState


def _run(gold: int = 0, seed: int = 0) -> RunState:
    run = RunState(rng=random.Random(seed))
    run.gold = gold
    return run


# ══════════════════════════════════════════════════════════════════════════
# event/morphic_grove/EV-10 — the GATE has no Quest clause
# ══════════════════════════════════════════════════════════════════════════

def test_morphic_grove_gate_counts_quest_cards():
    """MorphicGrove.cs:26 counts `c.IsTransformable` with NO Quest clause, while
    CardSelectCmd.FromDeckForTransformation (CardSelectCmd.cs:487) adds
    `c.Type != CardType.Quest`. Closing the SELECTION leg with the Quest filter
    made the GATE wrong the other way: a deck of [strike, spoils_map] with 100
    gold is an event the game serves and the sim refused."""
    from sts2_rl.events.morphic_grove import MorphicGrove

    run = _run(gold=100)
    run.deck = [make_card("strike"), make_card("spoils_map")]
    assert MorphicGrove.is_allowed(run) is True


def test_morphic_grove_selection_still_excludes_quest_cards():
    """The other leg stays closed — the two predicates really are different."""
    from sts2_rl.cards import CardType

    run = _run(gold=100)
    run.deck = [make_card("strike"), make_card("spoils_map")]
    assert len(run.removable_cards()) == 2
    assert not any(c.card_type == CardType.QUEST
                   for c in run.transformable_cards())


# ══════════════════════════════════════════════════════════════════════════
# event/orobas/g6 — the LOCKED path still takes its draw
# ══════════════════════════════════════════════════════════════════════════

def test_orobas_locked_pool3_still_takes_the_draw():
    """Orobas.cs:54-56 puts the locked placeholder INTO OptionPool3 and
    Orobas.cs:75 calls `base.Rng.NextItem(OptionPool3)` unconditionally, so the
    game takes a NextItem draw over a one-element list. The sim branched around
    `pick` and took one fewer draw off the event stream."""
    from sts2_rl.events.orobas import OrobasEvent

    run = _run()
    run.deck = [make_card("strike")]
    event = OrobasEvent(run)
    picks: list[int] = []
    real = run.rng.choice

    def counting(seq, *a, **k):
        picks.append(len(seq))
        return real(seq, *a, **k)

    run.rng.choice = counting
    event.rng = run.rng
    options = event.initial_options()
    assert options[-1].key.endswith("LOCKED")
    assert options[-1].on_chosen is None
    # FOUR NextItem draws: the Sea Glass character, pool 1, pool 2 and pool 3 —
    # the locked pool is not exempt, and its list has exactly one element.
    assert len(picks) == 4
    assert picks[-1] == 1


# ══════════════════════════════════════════════════════════════════════════
# event/fake_merchant/g3 — CalcCost, not the dead `relicCost` constant
# ══════════════════════════════════════════════════════════════════════════

def test_fake_merchant_jitters_every_price_on_the_shops_stream():
    """MerchantRelicEntry.CalcCost (MerchantRelicEntry.cs:42-45) is
    `Round(MerchantCost * Shops.NextFloat(0.85f, 1.15f))`, one draw per stocked
    entry. `FakeMerchant.relicCost = 50` is a DEAD constant — grep finds only its
    own declaration."""
    from sts2_rl.events.fake_merchant import FakeMerchant

    run = _run(gold=500)
    event = FakeMerchant(run)
    event.begin()
    prices = [event.price_of(r) for r in event.stock]
    assert len(prices) == 6
    assert all(43 <= p <= 58 for p in prices), prices
    assert len(set(prices)) > 1, "a flat 50 for every entry is the old bug"


def test_fake_merchant_charges_the_jittered_price():
    from sts2_rl.events.fake_merchant import FakeMerchant

    run = _run(gold=500)
    event = FakeMerchant(run)
    event.begin()
    relic = event.stock[0]
    price = event.price_of(relic)
    before = run.gold
    event._buy(relic)
    assert run.gold == before - price


def test_fake_merchant_locks_what_you_cannot_afford():
    """The affordability lock is per-entry and must use that entry's price."""
    from sts2_rl.events.fake_merchant import FakeMerchant

    run = _run(gold=500)
    event = FakeMerchant(run)
    event.begin()
    run.gold = min(event.price_of(r) for r in event.stock) - 1
    keys = [o.key for o in event._page_options()]
    assert all(k.endswith("_LOCKED") for k in keys
               if k not in ("LEAVE", "THROW_POTION"))


# ══════════════════════════════════════════════════════════════════════════
# event/brain_leech/g3 — RIP's card screens are SKIPPABLE
# ══════════════════════════════════════════════════════════════════════════

def test_brain_leech_rip_offers_rather_than_grants():
    """BrainLeech.cs:51-61 hands its `RewardCount` 3-card colourless CardRewards
    (IntVar RewardCount = 1, BrainLeech.cs:32) to
    `RewardsCmd.OfferCustom` — a skippable screen. The SHARE_KNOWLEDGE branch
    sets `Cancelable = false` and this one does not, so the source distinguishes
    them deliberately. The sim added a card through select_cards, which never
    returns empty for a non-empty candidate list."""
    from sts2_rl.events.brain_leech import BrainLeech

    run = _run()
    before = len(run.deck)
    event = BrainLeech(run)
    event.begin()
    rip = next(i for i, o in enumerate(event.options) if o.key == "RIP")
    event.choose(rip)
    assert len(run.deck) == before, "the card must be OFFERED, not added"
    assert event.pending_rewards is not None
    groups = event.pending_rewards.card_rewards
    assert len(groups) == 1
    assert all(len(g.cards) == 3 for g in groups)


def test_brain_leech_share_knowledge_still_grants():
    """The un-cancelable branch is unchanged."""
    from sts2_rl.events.brain_leech import BrainLeech

    run = _run()
    before = len(run.deck)
    event = BrainLeech(run)
    event.begin()
    idx = next(i for i, o in enumerate(event.options)
               if o.key == "SHARE_KNOWLEDGE")
    event.choose(idx)
    assert len(run.deck) == before + 1


# ══════════════════════════════════════════════════════════════════════════
# event/trial/g8 — NondescriptGuilty's two screens
# ══════════════════════════════════════════════════════════════════════════

def test_trial_nondescript_guilty_offers_two_card_screens():
    """Trial.cs:177-187 — Doubt, then TWO `CardReward(ForNonCombatWithDefault
    Odds([Character.CardPool]), 3)` entries through RewardsCmd.OfferCustom. The
    sim added Doubt and stopped."""
    from sts2_rl.events.trial import Trial

    run = _run()
    before = len(run.deck)
    event = Trial(run)
    event.begin()
    # Force the NONDESCRIPT trial, then take GUILTY.
    event._nondescript_guilty()
    assert len(run.deck) == before + 1          # Doubt only
    assert run.deck[-1].id == "doubt"
    assert event.pending_rewards is not None
    groups = event.pending_rewards.card_rewards
    assert len(groups) == 2
    assert all(len(g.cards) == 3 for g in groups)
