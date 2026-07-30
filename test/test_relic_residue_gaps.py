"""Six relic-tier residues from round 7.

relic/iron_club/g1, relic/claws/g1, relic/seal_of_gold/g1,
relic/toasty_mittens/g1, relic/fiddle/g1 (+ /ShouldDraw),
relic/kusarigama/AfterSideTurnEnd.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.run import RunState


def _combat(relic_ids, deck=None, seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed), starting_deck=deck,
                       encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]),
                       relics=[make_relic(r) for r in relic_ids])


def test_iron_club_draws_on_the_fourth_card():
    """IronClub.cs:38 — `CardsVar(4)`, read by the `CardsPlayed % intValue`
    condition at :88-89. No AscensionHelper branch anywhere in the file."""
    assert make_relic("iron_club").CARDS == 4


def test_claws_does_not_offer_a_quest_card():
    """CardSelectCmd.cs:487 — `c.Type != CardType.Quest && c.IsTransformable`.
    The three ported Quest cards are removable, so the missing clause offered
    them."""
    from sts2_rl.cards import CardType

    run = RunState(rng=random.Random(0))
    run.add_card(make_card("lantern_key"))
    offered: list = []
    run.card_selector = lambda purpose, candidates, count: (
        offered.extend(candidates) or [])
    run.add_relic("claws")
    assert offered
    assert not any(c.card_type == CardType.QUEST for c in offered)


def test_seal_of_gold_can_spend_gold_won_this_combat():
    """SealOfGold.cs:27 gates on `Owner.Gold`, which PlayerCmd.GainGold updates
    live (PlayerCmd.cs:141-170) — so a Hand of Greed payout is spendable on the
    very next turn."""
    relic = make_relic("seal_of_gold")
    cs = _combat([])
    cs.player_gold = 0
    cs.relics.append(relic)
    relic.attach(cs)
    cs.gold_gained = 20
    before = cs.player.energy
    relic.after_side_turn_start(cs.player)
    assert cs.player.energy == before + 1
    assert cs.gold_spent == 5


def test_toasty_mittens_grants_strength_even_with_nothing_to_exhaust():
    """ToastyMittens.cs:50 sits OUTSIDE the `if (cardModel != null)` branch
    that guards the exhaust (:46-49)."""
    relic = make_relic("toasty_mittens")
    cs = _combat([])
    cs.relics.append(relic)
    relic.attach(cs)
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()
    before = cs.player.strength
    relic.on_player_turn_start(cs.player)
    assert cs.player.strength == before + 1


def test_toasty_mittens_grants_strength_alongside_the_exhaust():
    relic = make_relic("toasty_mittens")
    cs = _combat([])
    cs.relics.append(relic)
    relic.attach(cs)
    cs.player.draw_pile = [make_card("strike")]
    before = cs.player.strength
    relic.on_player_turn_start(cs.player)
    assert cs.player.strength == before + 1
    assert len(cs.player.exhaust_pile) == 1


def test_fiddle_only_forbids_draws_on_its_owners_own_turn():
    """Fiddle.cs:34-37 — `player.Creature.Side != CombatState.CurrentSide ->
    return true`. An OFF-turn draw is untouched."""
    relic = make_relic("fiddle")
    cs = _combat([])
    cs.relics.append(relic)
    relic.attach(cs)
    assert relic.should_draw(cs.player, from_hand_draw=True) is True
    assert relic.should_draw(cs.player, from_hand_draw=False) is False
    cs.current_side = "enemy"
    assert relic.should_draw(cs.player, from_hand_draw=False) is True


def test_kusarigama_resets_after_the_hand_flush():
    """Kusarigama.cs is AfterSideTurnEnd (turn_structure step 64), not
    Hook.BeforeTurnEnd (step 48) — ~16 steps apart, and StampedePower
    auto-plays Attacks in between."""
    relic = make_relic("kusarigama")
    assert not hasattr(type(relic), "on_player_turn_end")
    cs = _combat([])
    cs.relics.append(relic)
    relic.attach(cs)
    relic._attacks_this_turn = 2
    relic.after_player_turn_end(cs.player)    # AfterSideTurnEnd: reset
    assert relic._attacks_this_turn == 0
