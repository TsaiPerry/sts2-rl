"""Task 8, Mechanisms A + B: `AfterCardChangedPiles` residue + the
transform's missing `AfterCardGeneratedForCombat` companion event.

Mechanism A (seam/creature_card_cmds guard G8, steps 81/89/96): the
`after_card_changed_piles` hook already existed (wired at the transform site
only, step59). This wires it at the three remaining sim entry points reachable
from this footprint -- `CardPileCmd.add_to_hand`/`add_to_draw`/`add_to_discard`
(the sim's `AddGeneratedCardToCombat`, step81/step70), the player's per-card
Draw (`PlayerCombatState._draw`, step89), and the two mid-combat reshuffle
helpers (`reshuffle_discard_into_draw`/`shuffle_draw_and_discard`, step96).
RemoveFromCombat (CardPileCmd.cs:188) and the manual play (CardPileCmd.cs:683)
are NOT wired here -- their sim analogues, `monsters/hive/thieving_hopper.py`
and `combat.py`, sit outside this task's footprint.

Mechanism B (step61/step70): `on_card_generated_for_combat`
(Hook.AfterCardGeneratedForCombat) is wired at its two C# sites -- inside the
Add pipeline (`CardPileCmd._generated_for_combat`, called from
`add_to_hand`/`add_to_draw`/`add_to_discard`) and after a combat-pile
transform's `AfterTransformedTo` (`CardCmd.transform_to_random`).
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardCmd, CardPileCmd
from sts2_rl.relics.bing_bong import BingBong


def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


class PileSpy:
    """Records every `after_card_changed_piles` / `on_card_generated_for_combat`
    call it is handed, tagged by hook name so one spy can watch both."""

    def __init__(self):
        self.changed_piles: list[tuple[str, object, object]] = []
        self.generated: list[tuple[str, object]] = []
        self.order: list[str] = []

    def after_card_changed_piles(self, card, pile, cloned_by):
        self.changed_piles.append((card.id, pile, cloned_by))
        self.order.append("changed_piles")

    def on_card_generated_for_combat(self, card, creator=None):
        self.generated.append((card.id, creator))
        self.order.append("generated")


# ══════════════════════════════════════════════════════════════════════════
# Mechanism A -- the Add site (add_to_hand / add_to_draw / add_to_discard)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("verb, pile_attr", [
    ("add_to_hand", "hand"),
    ("add_to_draw", "draw_pile"),
    ("add_to_discard", "discard_pile"),
])
def test_add_site_fires_changed_piles_with_pile_none_and_creator_none(verb, pile_attr):
    """CardPileCmd.cs:635 (inside Add, reached via AddGeneratedCardsToCombat)
    and :246 (right after). `oldPile?.Type ?? PileType.None` is `None` for a
    freshly generated card, and `creator` is `None` at both reachable
    callers (Aeonglass.cs:145, WitheringPresencePower.cs:55)."""
    cs = fresh()
    spy = PileSpy()
    cs.hooks.register(spy)
    card = make_card("bash")
    getattr(CardPileCmd, verb)(cs.hooks, cs.player, card)
    assert spy.changed_piles == [(card.id, None, None)]
    assert spy.generated == [(card.id, None)]
    assert card in getattr(cs.player, pile_attr)


def test_add_site_fires_changed_piles_before_generated_for_combat():
    """CardPileCmd.cs:246 dispatches AfterCardGeneratedForCombat AFTER the
    Add call (which fires AfterCardChangedPiles internally) returns."""
    cs = fresh()
    spy = PileSpy()
    cs.hooks.register(spy)
    CardPileCmd.add_to_hand(cs.hooks, cs.player, make_card("bash"))
    assert spy.order == ["changed_piles", "generated"]


def test_full_hand_overflow_still_dispatches_both_hooks():
    """`isFullHandAdd` redirects the target pile to Discard
    (CardPileCmd.cs:419-423) but the dispatch loop at the end of Add() does
    not distinguish -- `item3.oldPile` is still None either way."""
    cs = fresh()
    cs.player.hand[:] = [make_card("strike") for _ in range(cs.player.MAX_HAND_SIZE)]
    spy = PileSpy()
    cs.hooks.register(spy)
    card = make_card("bash")
    CardPileCmd.add_to_hand(cs.hooks, cs.player, card)
    assert card in cs.player.discard_pile
    assert spy.changed_piles == [(card.id, None, None)]
    assert spy.generated == [(card.id, None)]


def test_refused_add_dispatches_neither_hook():
    """`_refuses_combat_add` (the sim's CardPileCmd.cs:312-319/329-340/398-401
    trio) short-circuits before the card ever moves -- neither hook should
    fire for a card that never entered a pile."""
    cs = fresh()
    cs.player.hp = 0  # creature.IsDead -> success=false
    spy = PileSpy()
    cs.hooks.register(spy)
    CardPileCmd.add_to_hand(cs.hooks, cs.player, make_card("bash"))
    assert spy.changed_piles == []
    assert spy.generated == []


def test_add_site_does_not_touch_the_deck_shim():
    """BingBong (registered on the combat HookSystem too, mirroring
    `Relic.attach`) only implements `after_card_added_to_deck` -- a different
    method with a different signature (`run, card` vs `card, pile,
    cloned_by`). The new dispatch must not crash it or invoke it."""
    cs = fresh()
    bb = BingBong()
    cs.hooks.register(bb)
    CardPileCmd.add_to_hand(cs.hooks, cs.player, make_card("bash"))
    assert bb._cards_to_skip == set()  # untouched


# ══════════════════════════════════════════════════════════════════════════
# Mechanism A -- Draw (player.py `_draw`)
# ══════════════════════════════════════════════════════════════════════════

def test_draw_fires_changed_piles_with_old_pile_draw():
    """`await Add(card, hand)` (CardPileCmd.cs:849) is the full Add
    pipeline; its own dispatch names the OLD pile, Draw."""
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile[:] = [make_card("strike")]
    spy = PileSpy()
    cs.hooks.register(spy)
    cs.player._draw(1)
    assert spy.changed_piles == [(spy.changed_piles[0][0], "draw", None)]
    assert spy.changed_piles[0][0] == "strike"


def test_draw_does_not_fire_generated_for_combat():
    """Draw routes through the general `Add`, not `AddGeneratedCardsToCombat`
    -- AfterCardGeneratedForCombat has exactly two C# sites and neither is
    Draw."""
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile[:] = [make_card("strike")]
    spy = PileSpy()
    cs.hooks.register(spy)
    cs.player._draw(1)
    assert spy.generated == []


def test_draw_dispatches_changed_piles_before_on_card_drawn():
    """CardPileCmd.cs:849-851: `await Add(card, hand)` (whose own dispatch
    fires internally) precedes `Hook.AfterCardDrawn`."""
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile[:] = [make_card("strike")]
    log: list[str] = []

    class Spy:
        def after_card_changed_piles(self, card, pile, cloned_by):
            log.append("changed_piles")

        def on_card_drawn(self, card, from_hand_draw=False):
            log.append("drawn")

    cs.hooks.register(Spy())
    cs.player._draw(1)
    assert log == ["changed_piles", "drawn"]


def test_multi_card_draw_fires_once_per_card():
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile[:] = [make_card("strike") for _ in range(3)]
    spy = PileSpy()
    cs.hooks.register(spy)
    cs.player._draw(3)
    assert len(spy.changed_piles) == 3
    assert all(pile == "draw" for _, pile, _ in spy.changed_piles)


# ══════════════════════════════════════════════════════════════════════════
# Mechanism A -- the two mid-combat reshuffle helpers
# ══════════════════════════════════════════════════════════════════════════

def test_reshuffle_discard_into_draw_dispatches_for_every_card():
    """This helper only ever runs with an EMPTY draw pile (every one of its
    five callers gates on `not draw_pile` first), so every card in the
    shuffled result originated in the discard -- CardPileCmd.cs:892-912's
    silent branch never applies here."""
    cs = fresh()
    cs.player.draw_pile.clear()
    cards = [make_card("strike"), make_card("defend"), make_card("bash")]
    cs.player.discard_pile[:] = cards
    spy = PileSpy()
    cs.hooks.register(spy)
    cs.player.reshuffle_discard_into_draw()
    assert len(spy.changed_piles) == 3
    assert all(pile == "discard" and cloned_by is None
              for _, pile, cloned_by in spy.changed_piles)
    assert {c for c, _, _ in spy.changed_piles} == {c.id for c in cards}
    assert spy.generated == []  # not a generated-card site


def test_reshuffle_discard_into_draw_excludes_the_held_card():
    """A card mid-OnPlay sits in limbo (`_playing_card`), not the discard --
    it must not fire the hook either."""
    cs = fresh()
    cs.player.draw_pile.clear()
    held = make_card("pommel_strike")
    other = make_card("strike")
    cs.player.discard_pile[:] = [held, other]
    cs.player._playing_card = held
    spy = PileSpy()
    cs.hooks.register(spy)
    cs.player.reshuffle_discard_into_draw()
    assert [c for c, _, _ in spy.changed_piles] == [other.id]


def test_shuffle_draw_and_discard_only_fires_for_discard_sourced_cards():
    """CardPileCmd.cs:874 `drawPileCards = drawPile.Cards.ToHashSet()` is
    captured BEFORE the shuffle; only non-origin (discard-sourced) cards get
    the full Add() -> AfterCardChangedPiles dispatch, cards already in the
    draw pile are re-seated silently (CardPileCmd.cs:911). Bottled
    Potential/Reboot are the callers where the draw pile can be non-empty, so
    this is the one call site where the asymmetry has a real surface."""
    cs = fresh()
    from_draw = [make_card("strike"), make_card("defend")]
    from_discard = [make_card("bash"), make_card("anger")]
    cs.player.draw_pile[:] = from_draw
    cs.player.discard_pile[:] = from_discard
    spy = PileSpy()
    cs.hooks.register(spy)
    cs.player.shuffle_draw_and_discard()
    fired_ids = {c for c, _, _ in spy.changed_piles}
    assert fired_ids == {c.id for c in from_discard}
    assert fired_ids.isdisjoint({c.id for c in from_draw})
    assert all(pile == "discard" for _, pile, _ in spy.changed_piles)
    # Every card, from both origins, still ends up in the new draw pile --
    # the asymmetry is in the HOOK, not in where the cards land.
    assert set(cs.player.draw_pile) == set(from_draw) | set(from_discard)


def test_shuffle_draw_and_discard_with_empty_draw_pile_fires_for_all():
    """The degenerate case (draw pile empty) collapses to the same shape as
    `reshuffle_discard_into_draw` -- every card is discard-sourced."""
    cs = fresh()
    cs.player.draw_pile.clear()
    cards = [make_card("strike"), make_card("defend")]
    cs.player.discard_pile[:] = cards
    spy = PileSpy()
    cs.hooks.register(spy)
    cs.player.shuffle_draw_and_discard()
    assert len(spy.changed_piles) == 2


# ══════════════════════════════════════════════════════════════════════════
# Mechanism B -- the transform site's second event
# ══════════════════════════════════════════════════════════════════════════

def _combat_with_one_hand_card(card_id="strike"):
    cs = fresh()
    card = make_card(card_id)
    for pile in (cs.player.hand, cs.player.draw_pile,
                 cs.player.discard_pile, cs.player.exhaust_pile):
        pile.clear()
    cs.player.hand.append(card)
    CardPileCmd._enter_combat(cs.hooks, card)
    return cs, card


def test_transform_fires_generated_for_combat_with_creator_is_the_player():
    """CardCmd.cs:499-506: a THIRD pass, after AfterCardChangedPiles/
    AfterTransformedFrom/AfterTransformedTo, gated on
    `cardAdded.Pile.Type.IsCombatPile()` (always true here) --
    `creator` is `cardAdded.Owner`, unlike the Add site's `null`."""
    cs, original = _combat_with_one_hand_card()
    spy = PileSpy()
    cs.hooks.register(spy)
    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, original)
    assert replacement is not None
    assert spy.generated == [(replacement.id, cs.player)]


def test_transform_fires_generated_for_combat_after_changed_piles():
    cs, original = _combat_with_one_hand_card()
    spy = PileSpy()
    cs.hooks.register(spy)
    CardCmd.transform_to_random(cs.hooks, cs.player, original)
    assert spy.order == ["changed_piles", "generated"]


def test_transform_still_fires_changed_piles_exactly_as_before():
    """Regression: Mechanism B must not touch the already-closed step59
    dispatch (pile = the pile the replacement landed IN, not the old pile)."""
    cs, original = _combat_with_one_hand_card()
    spy = PileSpy()
    cs.hooks.register(spy)
    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, original)
    assert spy.changed_piles == [(replacement.id, "hand", None)]
