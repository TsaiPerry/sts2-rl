"""Round 13, R5: the physical `PileType.Play` pile.

`seam/creature_card_cmds` N9 + step82 + G8's last site, plus step51 (Sly's
`CardCmd.DiscardAndDraw`), step56 (`PileIndexSort`) and step99's one residue.

The spec is `CardModel.OnPlayWrapper` (CardModel.cs:1867-2005): the card is
moved INTO `PileType.Play` before anything else happens (:1875 manual,
:1879 auto), stays there for the whole of `OnPlay`, and leaves through a
switch that is GATED on it still being in Play (:1976-1991). `AllPiles` is
`Hand, DrawPile, DiscardPile, ExhaustPile, PlayPile`
(PlayerCombatState.cs:70-80) and `CardPileCmd.Shuffle` reads only Draw and
Discard (CardPileCmd.cs:870-871) — which is the entire mechanism behind the
"a card mid-play is not reshuffled" seed fact the sim used to model with a
`_playing_card` marker on a card that was physically in the discard.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cards.base import Card, CardRarity, CardType, TargetType
from sts2_rl.cmds import CardCmd, CardPileCmd, ExhaustCmd, PowerCmd


def fresh(seed: int = 0, **kw) -> CombatState:
    return CombatState(rng=random.Random(seed), **kw)


def bare(seed: int = 0, **kw) -> CombatState:
    """A combat with all four ordinary piles emptied."""
    cs = fresh(seed, **kw)
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()
    cs.player.exhaust_pile.clear()
    return cs


def enter(cs, card):
    """Put a freshly made card into the combat as a listener (what
    `CombatState.__init__` does for every deck card)."""
    card.reset_combat_state()
    card.combat = cs
    cs.hooks.register(card)
    return card


class _Probe(Card):
    """A 0-cost Skill whose OnPlay runs whatever `hook` is set to."""

    id = "round13_probe"
    name = "Round 13 Probe"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self.hook = None

    def on_play(self, ctx, target_idx=None):
        if self.hook is not None:
            self.hook(ctx, self)


def probe_card(cs, hook=None, **attrs):
    card = _Probe()
    card.hook = hook
    for k, v in attrs.items():
        setattr(card, k, v)
    return enter(cs, card)


class PileSpy:
    def __init__(self):
        self.changed: list[tuple[str, object, object]] = []

    def after_card_changed_piles(self, card, pile, cloned_by):
        self.changed.append((card.id, pile, cloned_by))


# ══════════════════════════════════════════════════════════════════════════
# N9 / step82 — the pile exists and holds the card for the whole of OnPlay
# ══════════════════════════════════════════════════════════════════════════

def test_a_card_being_played_sits_in_the_play_pile():
    """CardPileCmd.AddDuringManualCardPlay (CardPileCmd.cs:669-670):
    `RemoveFromCurrentPile()` then `PileType.Play.GetPile(...).AddInternal()`.
    It is in NO other pile while it resolves."""
    cs = bare()
    seen = {}

    def look(ctx, self):
        p = ctx.player
        seen["play"] = list(p.play_pile)
        seen["discard"] = list(p.discard_pile)
        seen["hand"] = list(p.hand)
        seen["pile_type"] = p.pile_type_of(self)

    card = probe_card(cs, look)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert seen["play"] == [card]
    assert seen["discard"] == []
    assert seen["hand"] == []
    assert seen["pile_type"] == "play"
    # ...and it has left Play by the time the play is over.
    assert cs.player.play_pile == []
    assert cs.player.discard_pile == [card]


def test_all_cards_puts_the_play_pile_last():
    """`AllCards` flattens `AllPiles` (PlayerCombatState.cs:82), and Play is
    the FIFTH entry (:76)."""
    cs = bare()
    order = []

    def look(ctx, self):
        order.extend(ctx.player.all_cards)

    card = probe_card(cs, look)
    other = enter(cs, make_card("strike"))
    cs.player.hand.append(card)
    cs.player.discard_pile.append(other)
    assert cs.play_card(0)
    assert order == [other, card]        # discard leg, then Play last


def test_pile_type_of_is_a_real_membership_test():
    """`CardModel.Pile?.Type` — with a physical Play pile there is no marker
    to consult and no card in two piles at once."""
    cs = bare()
    card = enter(cs, make_card("strike"))
    cs.player.play_pile.append(card)
    assert cs.player.pile_type_of(card) == "play"
    cs.player.play_pile.remove(card)
    cs.player.discard_pile.append(card)
    assert cs.player.pile_type_of(card) == "discard"


def test_a_mid_play_card_is_excluded_from_its_own_reshuffle_by_construction():
    """Seed fact 1: `CardPileCmd.Shuffle` reads `PileType.Draw` and
    `PileType.Discard` only (CardPileCmd.cs:870-871). A card in Play is in
    neither, so the exclusion needs no hold-back code at all."""
    cs = bare()
    out = {}

    def reshuffle(ctx, self):
        ctx.player.reshuffle_discard_into_draw()
        out["draw"] = list(ctx.player.draw_pile)
        out["discard"] = list(ctx.player.discard_pile)

    card = probe_card(cs, reshuffle)
    other = enter(cs, make_card("strike"))
    cs.player.hand.append(card)
    cs.player.discard_pile.append(other)
    assert cs.play_card(0)
    assert out["draw"] == [other]
    assert out["discard"] == []
    assert cs.player.discard_pile == [card]     # its result pile, afterwards


def test_shuffle_draw_and_discard_also_leaves_a_mid_play_card_alone():
    """The explicit `CardPileCmd.Shuffle` (Bottled Potential) reads the same
    two piles."""
    cs = bare()
    out = {}

    def reshuffle(ctx, self):
        ctx.player.shuffle_draw_and_discard()
        out["draw"] = list(ctx.player.draw_pile)
        out["discard"] = list(ctx.player.discard_pile)

    card = probe_card(cs, reshuffle)
    other = enter(cs, make_card("strike"))
    cs.player.hand.append(card)
    cs.player.discard_pile.append(other)
    assert cs.play_card(0)
    assert out["draw"] == [other]
    assert out["discard"] == []


# ══════════════════════════════════════════════════════════════════════════
# G8's last site — the manual-play entry dispatch
# ══════════════════════════════════════════════════════════════════════════

def test_the_manual_play_entry_fires_after_card_changed_piles():
    """CardPileCmd.cs:683 — `Hook.AfterCardChangedPiles(runState,
    combatState, card, oldPile?.Type ?? None, clonedBy: null)`, dispatched
    AFTER the move (`:669-670`), with the OLD pile (Hand for a manual play)
    and a literal null `clonedBy`."""
    cs = bare()
    spy = PileSpy()
    where = []

    def _hook(card, pile, cloned_by):
        where.append(cs.player.pile_type_of(card))
        spy.after_card_changed_piles(card, pile, cloned_by)

    spy_obj = type("S", (), {"after_card_changed_piles": staticmethod(_hook)})()
    cs.hooks.register(spy_obj)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert spy.changed[0] == ("round13_probe", "hand", None)
    assert where[0] == "play"          # fires AFTER the move


def test_the_exit_add_fires_after_card_changed_piles_from_play():
    """The default arm of the exit switch is a full `CardPileCmd.Add`
    (CardModel.cs:1988), which dispatches at CardPileCmd.cs:635 with
    `oldPileType = Play`."""
    cs = bare()
    spy = PileSpy()
    cs.hooks.register(spy)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert spy.changed == [("round13_probe", "hand", None),
                           ("round13_probe", "play", None)]


def test_an_auto_played_card_enters_play_from_none_when_it_had_no_pile():
    """`CardCmd.AutoPlay` pre-adds only `if (card.Pile == null)`
    (CardCmd.cs:114-116); the sim's `auto_play_card` pulls the card out of
    whatever pile holds it first, so the old pile is reported."""
    cs = bare()
    spy = PileSpy()
    cs.hooks.register(spy)
    card = probe_card(cs)
    cs.player.draw_pile.append(card)
    cs.auto_play_card(card)
    assert spy.changed[0] == ("round13_probe", "draw", None)


# ══════════════════════════════════════════════════════════════════════════
# The exit switch (CardModel.cs:1976-1991)
# ══════════════════════════════════════════════════════════════════════════

def test_the_exit_is_a_no_op_when_an_effect_already_moved_the_card():
    """`if (pile != null && pile.Type == PileType.Play)` — an effect that
    moved the card out of Play mid-play owns it; the switch does not run."""
    cs = bare()

    def steal(ctx, self):
        ctx.player.play_pile.remove(self)
        ctx.player.hand.append(self)

    card = probe_card(cs, steal)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.hand == [card]
    assert cs.player.discard_pile == []
    assert cs.player.play_pile == []


def test_a_power_card_is_removed_from_combat():
    """`GetResultPileTypeForCardPlay` (CardModel.cs:2072-2074) returns
    `PileType.None` for a Power, which the switch resolves to
    `CardPileCmd.RemoveFromCombat` (:1981-1983)."""
    cs = bare()
    card = enter(cs, make_card("inflame"))
    cs.player.hand.append(card)
    cs.player.energy = 9
    assert cs.play_card(0)
    for pile in (cs.player.hand, cs.player.draw_pile, cs.player.discard_pile,
                 cs.player.exhaust_pile, cs.player.play_pile):
        assert card not in pile
    assert card.has_been_removed_from_state is True


def test_the_remove_from_combat_exit_fires_after_card_changed_piles():
    """`RemoveFromCombat`'s own tail (CardPileCmd.cs:188-189) dispatches with
    the pile the card just left — Play — then `RemoveFromState()`."""
    cs = bare()
    spy = PileSpy()
    cs.hooks.register(spy)
    card = enter(cs, make_card("inflame"))
    cs.player.hand.append(card)
    cs.player.energy = 9
    assert cs.play_card(0)
    assert spy.changed[-1] == ("inflame", "play", None)


def test_an_exhaust_keyword_card_exits_through_cardcmd_exhaust():
    """`GetResultPileTypeForCardPlay` (:2076-2080) returns Exhaust for the
    keyword, and the switch calls `CardCmd.Exhaust` (:1985)."""
    cs = bare()
    exhausted = []
    card = probe_card(cs, exhausts=True)
    cs.hooks.register(type("S", (), {
        "on_card_exhausted": staticmethod(
            lambda c, caused_by_ethereal=False: exhausted.append(c.id))})())
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.exhaust_pile == [card]
    assert cs.player.discard_pile == []
    assert exhausted == ["round13_probe"]


def test_exhaust_on_next_play_is_consumed_before_the_hook_chain():
    """`GetResultPileTypeForCardPlay` is evaluated as the `defaultPileType`
    ARGUMENT of `Hook.ModifyCardPlayResultPileTypeAndPosition`
    (CardModel.cs:1890), and it clears `ExhaustOnNextPlay` on the spot
    (:2078) — so a listener sees `Exhaust`, never `Discard`."""
    cs = bare()
    seen = []
    cs.hooks.register(type("S", (), {
        "modify_card_play_result_pile": staticmethod(
            lambda card, pile: (seen.append(pile), pile)[1])})())
    card = probe_card(cs)
    card.exhaust_on_next_play = True
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert seen == ["exhaust"]
    assert card.exhaust_on_next_play is False
    assert cs.player.exhaust_pile == [card]


def test_the_result_pile_hook_runs_before_the_play_count_hook():
    """CardModel.cs:1890 (`ModifyCardPlayResultPileTypeAndPosition`) is
    strictly before :1895 (`GeneratePlayCount`). The sim asked for the play
    count first."""
    cs = bare()
    order = []
    cs.hooks.register(type("S", (), {
        "modify_card_play_result_pile": staticmethod(
            lambda card, pile: (order.append("pile"), pile)[1]),
        "modify_card_play_count": staticmethod(
            lambda card, target, count: (order.append("count"), count)[1]),
    })())
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert order == ["pile", "count"]


# ══════════════════════════════════════════════════════════════════════════
# ADDENDUM — the `Owner.Creature.IsDead` early returns
# ══════════════════════════════════════════════════════════════════════════

def test_a_lethal_self_damaging_play_stops_before_after_card_played():
    """CardModel.cs:1932-1935 returns straight out of OnPlayWrapper when the
    player died during `OnPlay`, so neither the enchantment leg (:1937), nor
    `Hook.AfterCardPlayed` (:1959), nor the exit switch (:1976) runs."""
    cs = bare()
    played = []
    cs.hooks.register(type("S", (), {
        "on_card_played": staticmethod(
            lambda card, is_auto_play=False: played.append(card.id))})())

    def suicide(ctx, self):
        ctx.player.hp = 0

    card = probe_card(cs, suicide)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert played == []
    # The exit switch never ran, so the card is still in Play — C# strands it
    # there too (the `return` at :1934 skips :1976-1991 entirely).
    assert cs.player.play_pile == [card]


def test_a_play_that_only_hurts_the_player_still_dispatches():
    """The gate is `IsDead`, not "took damage": a survivable self-damaging
    play runs the whole wrapper."""
    cs = bare()
    played = []
    cs.hooks.register(type("S", (), {
        "on_card_played": staticmethod(
            lambda card, is_auto_play=False: played.append(card.id))})())

    def scratch(ctx, self):
        ctx.player.hp -= 1

    card = probe_card(cs, scratch)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert played == ["round13_probe"]
    assert cs.player.discard_pile == [card]


def test_the_play_count_gate_runs_before_the_loop():
    """CardModel.cs:1896-1899: `if (Owner.Creature.IsDead) return;` sits
    between `GeneratePlayCount` and the loop, so a player already dead when
    the play begins never reaches `BeforeCardPlayed`."""
    cs = bare()
    before = []
    cs.hooks.register(type("S", (), {
        "before_card_played": staticmethod(
            lambda card, target=None: before.append(card.id))})())
    card = probe_card(cs)
    cs.player.hand.append(card)
    cs.player.hp = 0
    cs._resolve_card_play(card, None)
    assert before == []


# ══════════════════════════════════════════════════════════════════════════
# MoveToResultPileWithoutPlaying (CardModel.cs:2089-2107)
# ══════════════════════════════════════════════════════════════════════════

def test_a_refused_play_goes_through_the_play_pile():
    """`CardCmd.MoveToResultPileWithoutPlaying` (CardCmd.cs:133-137) adds the
    card to Play FIRST, then runs the model method, which is itself gated on
    Play membership (:2092)."""
    cs = bare()
    spy = PileSpy()
    cs.hooks.register(spy)
    card = probe_card(cs)
    card.is_playable = False
    cs.player.draw_pile.append(card)
    cs.auto_play_card(card)
    assert cs.player.discard_pile == [card]
    assert [c[1] for c in spy.changed] == ["draw", "play"]


def test_a_refused_power_card_goes_to_the_discard_not_limbo():
    """MoveToResultPileWithoutPlaying's doc comment (CardModel.cs:2086-2087):
    "Power cards do not get sent to Limbo, and instead get sent to the
    discard" — its None arm is `IsDupe`, not `Type == Power`."""
    cs = bare()
    card = enter(cs, make_card("inflame"))
    card.is_playable = False
    cs.player.draw_pile.append(card)
    cs.auto_play_card(card)
    assert cs.player.discard_pile == [card]


# ══════════════════════════════════════════════════════════════════════════
# The four-pile scans that become five
# ══════════════════════════════════════════════════════════════════════════

def test_exhausting_a_card_mid_play_takes_it_out_of_the_play_pile():
    """`CardModel.RemoveFromCurrentPile` is pile-agnostic; with a real Play
    pile the scan in `ExhaustCmd.exhaust` needs its fifth case or the same
    instance ends up in two piles."""
    cs = bare()
    card = enter(cs, make_card("strike"))
    cs.player.play_pile.append(card)
    ExhaustCmd.exhaust(cs.hooks, cs.player, card)
    assert cs.player.play_pile == []
    assert cs.player.exhaust_pile == [card]


def test_a_mid_play_card_can_be_transformed():
    """`CardCmd.Transform` reads `item.Original.Pile` (CardCmd.cs:391) —
    whatever pile holds the card, Play included."""
    cs = bare()
    card = enter(cs, make_card("strike"))
    cs.player.play_pile.append(card)
    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, card)
    assert replacement is not None
    assert cs.player.play_pile == [replacement]
    assert card not in cs.player.play_pile


def test_afflicting_a_mid_play_card_is_refused_once_the_combat_is_ending():
    """CardCmd.cs:627-634's asymmetric guard tests "is this card in a combat
    pile", and Play is a combat pile (PileTypeExtensions.cs:35-42)."""
    from sts2_rl.afflictions import SmogAffliction
    cs = bare()
    card = enter(cs, make_card("strike"))
    cs.player.play_pile.append(card)
    cs._pending_loss = object()
    assert CardCmd.afflict(card, SmogAffliction, 1) is None


def test_a_return_to_hand_effect_can_reach_the_play_pile():
    """Bolas.cs:43-47 / ThrummingHatchet.cs:37-41 move the card from WHEREVER
    it is; the sim's scan listed four piles."""
    from sts2_rl.cards.colorless_attacks import _return_to_hand_if_played_last_turn
    from sts2_rl.history import CardPlayedEntry
    cs = bare()
    card = enter(cs, make_card("strike"))
    cs.player.play_pile.append(card)
    cs.history.entries.append(
        CardPlayedEntry(turn=cs.turn - 1, card=card, is_auto_play=False))
    _return_to_hand_if_played_last_turn(card)
    assert cs.player.hand == [card]
    assert cs.player.play_pile == []


def test_the_combat_card_db_can_resolve_a_mid_play_card():
    """`ordered_piles` is the conformance card-id walk; a card mid-play must
    stay resolvable (test_conformance_combat.py's db round-trip)."""
    from sts2_rl.combat_card_db import CombatCardDb
    cs = bare()
    card = enter(cs, make_card("strike"))
    cs.player.play_pile.append(card)
    piles = CombatCardDb().ordered_piles(cs)
    assert cs.player.play_pile in piles
    assert piles[-1] is cs.player.play_pile      # AllPiles order, Play last


# ══════════════════════════════════════════════════════════════════════════
# The listener derivation's fifth leg (hook_dispatch/G1's Play seam)
# ══════════════════════════════════════════════════════════════════════════

def test_the_listener_walk_reads_the_real_play_pile():
    """`HookSystem._derive`'s Play leg is `PlayerCombatState.AllPiles`' fifth
    entry, not a marker."""
    cs = bare()
    playing, other = enter(cs, make_card("strike")), enter(cs, make_card("defend"))
    log = []
    for card in (playing, other):
        setattr(card, "on_combat_start",
                lambda _c=card: log.append(_c))
    cs.hooks._presence_cache.pop("on_combat_start", None)
    cs.player.discard_pile[:] = [playing, other]
    assert [l for l, _ in cs.hooks._each("on_combat_start")] == [playing, other]
    cs.player.discard_pile.remove(playing)
    cs.player.play_pile.append(playing)
    assert [l for l, _ in cs.hooks._each("on_combat_start")] == [other, playing]


# ══════════════════════════════════════════════════════════════════════════
# OnTurnEndInHandWrapper (CardModel.cs:1682-1698)
# ══════════════════════════════════════════════════════════════════════════

def test_a_turn_end_in_hand_effect_runs_with_the_card_in_play():
    """CardModel.cs:1684 `await CardPileCmd.Add(this, PileType.Play)` before
    `OnTurnEndInHand` (:1689), then Ethereal -> Exhaust else Add(Discard).
    The doc comment at :1673 says it in as many words."""
    cs = bare()
    seen = {}

    class _TurnEnd(_Probe):
        id = "round13_turn_end"
        has_turn_end_in_hand_effect = True

        def on_turn_end_in_hand(self, ctx):
            seen["pile"] = ctx.player.pile_type_of(self)

    card = enter(cs, _TurnEnd())
    cs.player.hand.append(card)
    cs._process_turn_end_cards()
    assert seen["pile"] == "play"
    assert cs.player.discard_pile == [card]
    assert cs.player.play_pile == []


# ══════════════════════════════════════════════════════════════════════════
# The two hard blockers — Corruption and Rebound
# ══════════════════════════════════════════════════════════════════════════

def test_corruption_sends_the_played_skill_to_the_exhaust_pile():
    """CorruptionPower.cs:27-38 is a `ModifyCardPlayResultPileTypeAndPosition`
    implementer that returns `PileType.Exhaust` for the owner's Skills —
    NOT an AfterCardPlayed hand-move, and with no pile-membership test of any
    kind."""
    from sts2_rl.powers import CorruptionPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.exhaust_pile == [card]
    assert cs.player.discard_pile == []


def test_corruption_beats_a_draw_top_redirect():
    """It overrides the incoming pileType unconditionally (there is no
    `pileType != Discard` guard in CorruptionPower.cs), so whichever of the
    chain runs later wins and Corruption never abstains."""
    from sts2_rl.powers import CorruptionPower, ReboundPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 1)
    PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.exhaust_pile == [card]


def test_rebound_still_redirects_a_played_card_to_the_draw_top():
    """ReboundPower.cs:19-29: the only tests are the owner and
    `pileType != PileType.Discard`. The sim's extra
    `card in player.discard_pile` guard was a Play-limbo workaround and is
    false for every card once the pile exists."""
    from sts2_rl.powers import ReboundPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 1)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.draw_pile == [card]
    assert cs.player.discard_pile == []


def test_rebound_abstains_on_an_exhausting_play():
    """`GetResultPileTypeForCardPlay` seeds the chain with Exhaust, and
    ReboundPower.cs:25-28 bails on any non-Discard pileType — so no redirect
    and no stack spent."""
    from sts2_rl.powers import ReboundPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 2)
    card = probe_card(cs, exhausts=True)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.exhaust_pile == [card]
    assert cs.player.powers["rebound"].amount == 2


# ══════════════════════════════════════════════════════════════════════════
# De-hacks — the self-exclusion workarounds
# ══════════════════════════════════════════════════════════════════════════

def test_headbutt_cannot_pick_itself_by_construction():
    """Headbutt.cs picks from the discard pile while it is in Play, so it can
    never be a candidate; the sim filtered `c is not self` by hand."""
    cs = bare()
    card = enter(cs, make_card("headbutt"))
    other = enter(cs, make_card("strike"))
    cs.player.hand.append(card)
    cs.player.discard_pile.append(other)
    cs.player.energy = 9
    assert cs.play_card(0, 0)
    assert cs.player.draw_pile == [other]


def test_neows_fury_cannot_pick_itself_by_construction():
    """The ninth de-hack (R5-review RV-4). `NeowsFury.cs:39` is
    `CardSelectCmd.FromCombatPile(..., PileType.Discard.GetPile(Owner), ...,
    new CardSelectorPrefs(prompt, 0, num))` — no filter of any kind; the
    exclusion is `PileType.Play`. The candidate list the selector is shown
    must never contain the resolving card."""
    cs = bare()
    shown = []
    cs.card_selector = (
        lambda purpose, candidates, count: (shown.append(list(candidates)),
                                            list(candidates)[:count])[1])
    card = enter(cs, make_card("neows_fury"))
    others = [enter(cs, make_card("strike")), enter(cs, make_card("defend"))]
    cs.player.hand.append(card)
    cs.player.discard_pile.extend(others)
    cs.player.energy = 9
    assert cs.play_card(0, 0)
    assert shown == [others]                 # not `others + [card]`
    assert sorted(c.id for c in cs.player.hand) == ["defend", "strike"]


def test_stack_counts_the_discard_pile_without_itself():
    """`Stack` reads the discard pile during its own OnPlay; in the game it
    is in Play and so is never counted — the sim needed an `is not self`
    filter to compensate."""
    cs = bare()
    card = enter(cs, make_card("stack"))
    for _ in range(3):
        cs.player.discard_pile.append(enter(cs, make_card("strike")))
    cs.player.hand.append(card)
    cs.player.energy = 9
    assert cs.play_card(0)
    assert cs.player.block == 3


def test_cascade_does_not_replay_itself():
    """Cascade auto-plays off the draw pile and can trigger a reshuffle; in
    the game it is in Play, so the reshuffle cannot pick it up. The sim
    removed itself from the discard for the duration instead."""
    cs = bare()
    card = enter(cs, make_card("cascade"))
    cs.player.hand.append(card)
    cs.player.discard_pile.append(enter(cs, make_card("defend")))
    cs.player.energy = 2
    assert cs.play_card(0)
    from sts2_rl.history import CardPlayStartedEntry
    plays = [e for e in cs.history.of_type(CardPlayStartedEntry)
             if e.card is card]
    assert len(plays) == 1


# ══════════════════════════════════════════════════════════════════════════
# power/smoggy — the AfterCardEnteredCombat / AfterCardPlayed sweep
# ══════════════════════════════════════════════════════════════════════════

def test_smoggy_afflicts_the_skill_that_is_mid_play():
    """SmoggyPower.cs:24-34 sweeps `AllCards`, which includes the Play pile,
    so the Skill that triggered it is afflicted too. The sim's `all_cards`
    had four piles and skipped it."""
    from sts2_rl.powers import SmoggyPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, SmoggyPower, 1)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert card.affliction is not None


def test_ringing_afflicts_the_power_card_that_is_mid_play():
    """`power/ringing`'s entry, re-derived rather than closed by analogy with
    smoggy. `RingingPower.AfterApplied` (RingingPower.cs:23-31) sweeps
    `AllCards` and afflicts EVERY unafflicted card, of any type — unlike
    Smoggy, which filters to Skills. On the pre-round-13 tree the entry's
    exposure was FALSE for ordinary cards (they were parked in the discard,
    i.e. inside `all_cards`) and TRUE for a POWER card mid-play, which HEAD's
    `_resolve_card_play` put in NO pile at all (`if card.card_type !=
    CardType.POWER: discard_pile.append(card)`). The Play pile closes both."""
    from sts2_rl.powers import RingingPower
    cs = bare()
    inflame = enter(cs, make_card("inflame"))
    seen = {}

    class Applier:
        def on_card_played(self, card, is_auto_play=False):
            if "ringing" not in cs.player.powers:
                PowerCmd.apply(cs.hooks, cs.player, RingingPower, 1)
                seen["affliction"] = card.affliction

    cs.hooks.register(Applier())
    cs.player.hand.append(inflame)
    cs.player.energy = 9
    assert cs.play_card(0)
    assert cs.player.play_pile == []          # the Power left through `None`
    assert seen["affliction"] is not None     # ...but it was swept mid-play


# ══════════════════════════════════════════════════════════════════════════
# step99's residue — AutoPlayFromDrawPile parks its picks in Play
# ══════════════════════════════════════════════════════════════════════════

def test_auto_play_from_draw_pile_parks_every_pick_in_the_play_pile():
    """CardPileCmd.cs:954 `await Add(cardModel, PileType.Play)` in phase 1,
    for every pick, before any of them resolves (:956-965)."""
    cs = bare()
    seen = {}

    def look(ctx, self):
        seen.setdefault("play", list(ctx.player.play_pile))

    picks = [probe_card(cs, look) for _ in range(3)]
    cs.player.draw_pile[:] = list(picks)
    CardPileCmd.auto_play_from_draw_pile(cs.hooks, cs.player, 3, position="top")
    # The FIRST pick to resolve sees all three parked.
    assert len(seen["play"]) == 3
    assert cs.player.play_pile == []


# ══════════════════════════════════════════════════════════════════════════
# step51 — CardCmd.DiscardAndDraw and the Sly tail
# ══════════════════════════════════════════════════════════════════════════

def test_discard_and_draw_appends_before_it_fires_the_hook():
    """CardCmd.cs:192-194 — `await CardPileCmd.Add(card, discardPile)` THEN
    `Hook.AfterCardDiscarded`. `potions.py` fired the hook first."""
    cs = bare()
    where = []
    cs.hooks.register(type("S", (), {
        "on_card_discarded": staticmethod(
            lambda card: where.append(card in cs.player.discard_pile))})())
    card = enter(cs, make_card("strike"))
    cs.player.hand.append(card)
    CardCmd.discard_and_draw(cs.hooks, cs.player, [card], 0)
    assert where == [True]


def test_discard_and_draw_draws_before_it_auto_plays_the_sly_cards():
    """CardCmd.cs:197-204 — the draw happens first, then every collected
    `IsSlyThisTurn` card is auto-played with `AutoPlayType.SlyDiscard`."""
    cs = bare()
    order = []
    sly = probe_card(cs, lambda ctx, self: order.append("play"))
    sly.sly = True
    plain = enter(cs, make_card("strike"))
    cs.player.hand[:] = [sly, plain]
    cs.player.draw_pile[:] = [enter(cs, make_card("defend"))]
    cs.hooks.register(type("S", (), {
        "on_card_drawn": staticmethod(
            lambda card, from_hand_draw=False: order.append("draw"))})())
    CardCmd.discard_and_draw(cs.hooks, cs.player, [sly, plain], 1)
    assert order == ["draw", "play"]


def test_discard_and_draw_passes_the_auto_play_type():
    """`Hook.BeforeCardAutoPlayed`'s fourth argument (CardCmd.cs:122) is the
    `AutoPlayType`; the Sly tail passes `SlyDiscard` (:203)."""
    cs = bare()
    seen = []
    cs.hooks.register(type("S", (), {
        "before_card_auto_played": staticmethod(
            lambda card, target=None, auto_play_type="default":
                seen.append(auto_play_type))})())
    sly = probe_card(cs)
    sly.sly = True
    cs.player.hand[:] = [sly]
    CardCmd.discard_and_draw(cs.hooks, cs.player, [sly], 0)
    assert seen == ["sly_discard"]


def test_discard_and_draw_is_refused_once_the_combat_is_over_or_ending():
    """CardCmd.cs:174-177."""
    cs = bare()
    card = enter(cs, make_card("strike"))
    cs.player.hand.append(card)
    cs._pending_loss = object()
    CardCmd.discard_and_draw(cs.hooks, cs.player, [card], 0)
    assert cs.player.hand == [card]


def test_gamblers_brew_routes_through_discard_and_draw():
    """GamblersBrew.cs:27 is literally `CardCmd.DiscardAndDraw(picked,
    picked.Count)` — including the deferred draw and the Sly tail."""
    from sts2_rl.potions import make_potion
    cs = bare()
    where = []
    cs.hooks.register(type("S", (), {
        "on_card_discarded": staticmethod(
            lambda card: where.append(card in cs.player.discard_pile))})())
    cs.player.hand[:] = [enter(cs, make_card("strike"))]
    cs.player.draw_pile[:] = [enter(cs, make_card("defend"))]
    cs.card_selector = lambda purpose, candidates, count: list(candidates)
    potion = make_potion("gamblers_brew")
    potion.use(cs._ctx())
    assert where == [True]
    assert len(cs.player.hand) == 1


def test_gambling_chip_routes_through_discard_and_draw():
    """GamblingChip.cs:21 is the same command."""
    from sts2_rl.relics.gambling_chip import GamblingChip
    from sts2_rl.relics import make_relic
    cs = bare(relics=[make_relic("gambling_chip")])
    order = []
    cs.hooks.register(type("S", (), {
        "on_card_discarded": staticmethod(lambda card: order.append("discard")),
        "on_card_drawn": staticmethod(
            lambda card, from_hand_draw=False: order.append("draw")),
    })())
    cs.player.hand[:] = [enter(cs, make_card("strike"))]
    cs.player.draw_pile[:] = [enter(cs, make_card("defend"))]
    cs.card_selector = lambda purpose, candidates, count: list(candidates)
    relic = next(r for r in cs.relics if isinstance(r, GamblingChip))
    relic.on_player_turn_started(cs.player)
    assert order == ["discard", "draw"]


# ══════════════════════════════════════════════════════════════════════════
# step56 — PileIndexSort
# ══════════════════════════════════════════════════════════════════════════

def test_pile_index_sort_orders_by_raw_pile_enum_then_index():
    """CardCmd.cs:353-360 sorts on `CardPile.Type.CompareTo` — the RAW
    `PileType` enum value (PileType.cs: None=0, Draw=1, Hand=2, Discard=3,
    Exhaust=4, Play=5, Deck=6) — and then the pre-removal index. That is NOT
    `AllPiles` order: Draw comes before Hand."""
    from sts2_rl.cmds import CardCmd as _CardCmd
    rows = [("hand", 0, "h0"), ("draw", 1, "d1"), ("discard", 0, "x0"),
            ("draw", 0, "d0"), ("play", 0, "p0"), ("exhaust", 2, "e2"),
            ("deck", 0, "k0")]
    out = sorted(rows, key=lambda r: _CardCmd.pile_index_sort_key(r[0], r[1]))
    assert [r[2] for r in out] == ["d0", "d1", "h0", "x0", "e2", "p0", "k0"]


def test_pile_index_sort_refuses_a_pile_it_does_not_know():
    """CardCmd.cs:392-394 THROWS on a null pile ("Can't transform ... because
    it has no pile") before the index is captured at :396, so `PileIndexSort`
    can never see one. A silent `PileType.None` default would be the wrong
    thing to hand a future batch transform (R5-review RV-8)."""
    from sts2_rl.cmds import CardCmd as _CardCmd
    with pytest.raises(KeyError):
        _CardCmd.pile_index_sort_key(None, 0)
    with pytest.raises(KeyError):
        _CardCmd.pile_index_sort_key("limbo", 0)


# ══════════════════════════════════════════════════════════════════════════
# The exit switch's combat-ending refusals (R5-review RV-2)
#
# `CardModel.cs:1979-1989`'s three arms are not unconditional moves:
#   * `default:` is `CardPileCmd.Add`, which refuses a COMBAT pile while
#     `IsEnding` (CardPileCmd.cs:312-319, `success:false` for every card) and
#     while `!IsInProgress` (:398-401, an early `return results`) — both
#     strictly BEFORE `RemoveFromCurrentPile` (:496) and `AddInternal` (:510),
#     so a refused add leaves the card exactly where it was: in Play.
#   * `case Exhaust:` is `CardCmd.Exhaust`, whose ENTIRE body is inside
#     `if (!CombatManager.Instance.IsOverOrEnding)` (CardCmd.cs:239-245), so
#     the Add, `History.CardExhausted` and `Hook.AfterCardExhausted` are all
#     skipped together.
#   * `case None:` is `CardPileCmd.RemoveFromCombat` (:102-191), which has NO
#     liveness gate at all — the negative control below.
# `IsOverOrEnding` is `IsEnding || !IsInProgress` (CombatManager.cs:210-219)
# and `IsEnding` (:180-201) is true the instant the last primary enemy dies,
# i.e. from inside the killing blow's own OnPlayWrapper.
# ══════════════════════════════════════════════════════════════════════════

def test_the_killing_blow_stays_in_the_play_pile():
    """`default:` -> `CardPileCmd.Add(this, Discard)`, refused by :312-319
    once `IsEnding`. C# leaves the card in Play; so does the sim."""
    cs = bare()
    seen = {}

    def kill(ctx, self):
        ctx.enemies[0].hp = 0
        seen["ending"] = ctx.combat.is_ending

    card = probe_card(cs, kill)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert seen["ending"] is True          # the window is real, mid-play
    assert cs.player.play_pile == [card]
    assert cs.player.discard_pile == []
    assert cs.player.pile_type_of(card) == "play"


def test_a_pending_loss_leaves_the_played_card_in_play():
    """The other half of `IsEnding` (CombatManager.cs:188-191): a pending loss.
    The player is NOT dead here, so none of OnPlayWrapper's five
    `if (Owner.Creature.IsDead) return;` gates fires and the exit switch is
    genuinely reached — and refused."""
    cs = bare()

    def pending(ctx, self):
        ctx.combat.lose_combat()

    card = probe_card(cs, pending)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.is_dead is False
    assert cs.player.play_pile == [card]
    assert cs.player.discard_pile == []


def test_an_exhausting_killing_blow_stays_in_play_and_fires_no_exhaust_hook():
    """`case Exhaust:` is a `CardCmd.Exhaust` call and CardCmd.cs:239 wraps
    the WHOLE body, so neither the move nor `Hook.AfterCardExhausted`
    (:244) happens."""
    cs = bare()
    exhausted = []
    cs.hooks.register(type("S", (), {
        "on_card_exhausted": staticmethod(
            lambda c, caused_by_ethereal=False: exhausted.append(c.id))})())

    def kill(ctx, self):
        ctx.enemies[0].hp = 0

    card = probe_card(cs, kill, exhausts=True)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.play_pile == [card]
    assert cs.player.exhaust_pile == []
    assert exhausted == []


def test_the_refused_exhaust_does_not_credit_joss_paper():
    """The exit switch's exhaust refusal is NOT dormant, contrary to the
    review's rating. `JossPaper.CardsExhausted` is a `[SavedProperty]`
    (JossPaper.cs:60-76) incremented from `AfterCardExhausted` (:102-114) and
    cleared by NOTHING at combat end (`AfterCombatEnd` :144-148 clears
    `EtherealCount` only), so it is a RUN-scoped counter. Every combat that
    ended on an exhausting card used to over-credit it by one — an off-by-one
    that persists into the next combat and shifts when the relic draws."""
    from sts2_rl.relics import make_relic
    jp = make_relic("joss_paper")
    cs = bare(relics=[jp])

    def kill(ctx, self):
        ctx.enemies[0].hp = 0

    card = probe_card(cs, kill, exhausts=True)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.is_over_or_ending
    assert jp.cards_exhausted == 0
    assert cs.player.play_pile == [card]


def test_a_direct_exhaust_is_refused_once_the_combat_is_ending():
    """The refusal belongs to the COMMAND, not to the exit switch.
    `CardCmd.cs:242` is the ONLY `CardPileCmd.Add(..., PileType.Exhaust, ...)`
    in the whole source, so every exhaust in the game runs inside
    `CardCmd.Exhaust`'s `if (!CombatManager.Instance.IsOverOrEnding)` wrapper
    (:239) — including the ones a card fires from its own OnPlay after it has
    already killed the last enemy (Fiend Fire, Second Wind, Brand, Thrash,
    Burning Pact, ...). `ExhaustCmd.exhaust` is that method's port and carries
    the gate for all of its call sites."""
    from sts2_rl.relics import make_relic
    jp = make_relic("joss_paper")
    cs = bare(relics=[jp])
    exhausted = []
    cs.hooks.register(type("S", (), {
        "on_card_exhausted": staticmethod(
            lambda c, caused_by_ethereal=False: exhausted.append(c.id))})())
    victim = enter(cs, make_card("strike"))
    cs.player.hand.append(victim)
    cs.enemies[0].hp = 0                      # the IsEnding window
    assert cs.is_over_or_ending and not cs.is_over
    ExhaustCmd.exhaust(cs.hooks, cs.player, victim)
    assert cs.player.hand == [victim]          # never moved
    assert cs.player.exhaust_pile == []
    assert exhausted == []
    assert jp.cards_exhausted == 0
    # ...and it still works while the fight is live.
    alive = bare()
    live_card = enter(alive, make_card("strike"))
    alive.player.hand.append(live_card)
    ExhaustCmd.exhaust(alive.hooks, alive.player, live_card)
    assert alive.player.exhaust_pile == [live_card]


def test_a_power_card_is_still_removed_from_combat_on_the_killing_blow():
    """Negative control. `case None:` -> `CardPileCmd.RemoveFromCombat`
    (CardPileCmd.cs:102-191) has no `IsOverOrEnding` test anywhere, so the
    ending combat does NOT save a played Power from leaving the state — the
    refusal is arm-specific, not a blanket "stop moving cards"."""
    cs = bare()
    inflame = enter(cs, make_card("inflame"))

    class Killer:
        def on_card_played(self, card, is_auto_play=False):
            cs.enemies[0].hp = 0

    cs.hooks.register(Killer())
    cs.player.hand.append(inflame)
    cs.player.energy = 9
    assert cs.play_card(0)
    assert cs.is_over_or_ending
    for pile in (cs.player.hand, cs.player.draw_pile, cs.player.discard_pile,
                 cs.player.exhaust_pile, cs.player.play_pile):
        assert inflame not in pile
    assert inflame.has_been_removed_from_state is True


# ══════════════════════════════════════════════════════════════════════════
# Corruption/Rebound — the ORDER-DEPENDENT half (R5-review RV-10)
# ══════════════════════════════════════════════════════════════════════════

def test_corruption_first_makes_rebound_abstain_and_keep_its_stack():
    """`Hook.cs:1391-1406` adds a listener to `modifiers` only
    `if (pileType3 != pileType2 || cardPilePosition2 != cardPilePosition)` —
    i.e. only if ITS OWN call changed the value — and
    `ReboundPower.AfterModifyingCardPlayResultPileOrPosition`
    (ReboundPower.cs:32-39) decrements unconditionally once it is in that
    list. So the PILE is order-independent (Corruption always wins:
    CorruptionPower.cs:27-38 has no abstention) while the STACK is
    order-dependent. Applied Corruption first, Rebound sees "exhaust", bails
    at ReboundPower.cs:25-28 and is never credited."""
    from sts2_rl.powers import CorruptionPower, ReboundPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
    PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 2)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.exhaust_pile == [card]
    assert cs.player.draw_pile == []
    assert cs.player.powers["rebound"].amount == 2     # abstained, not ticked


def test_corruption_exhausts_once_after_the_whole_play_count_loop():
    """R3's residue 2, closed. Corruption used to be an `on_card_played`
    handler and so exhausted the card INSIDE the play-count loop, once per
    iteration; C# decides the pile at CardModel.cs:1890 and performs the
    exhaust ONCE at the exit switch (:1985). A replayed Skill therefore stays
    in `PileType.Play` for every iteration and fires exactly one
    `Hook.AfterCardExhausted`."""
    from sts2_rl.powers import CorruptionPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
    exhausted, piles = [], []
    cs.hooks.register(type("S", (), {
        "modify_card_play_count": staticmethod(lambda card, target, count: 2),
        "on_card_exhausted": staticmethod(
            lambda c, caused_by_ethereal=False: exhausted.append(c.id)),
    })())
    # PHYSICAL membership, not `pile_type_of`: HEAD's `pile_type_of` tested
    # `_playing_card` FIRST and answered "play" for a card that was sitting in
    # the exhaust pile, so only the pile lists can tell the two trees apart.
    card = probe_card(cs, lambda ctx, self: piles.append(
        (list(ctx.player.play_pile), list(ctx.player.exhaust_pile))))
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert piles == [([card], []), ([card], [])]   # in Play for BOTH passes
    assert exhausted == ["round13_probe"]          # exactly one exhaust, after
    assert cs.player.exhaust_pile == [card]


def test_rebound_first_is_credited_and_ticks_even_though_corruption_wins():
    """The mirror image: Rebound registered first changes "discard" ->
    "draw_top", so it IS in Hook.cs:1401-1404's `modifiers` list and its
    Decrement runs — even though Corruption then overrides the pile to
    Exhaust. Same final pile, different stack."""
    from sts2_rl.powers import CorruptionPower, ReboundPower
    cs = bare()
    PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 2)
    PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
    card = probe_card(cs)
    cs.player.hand.append(card)
    assert cs.play_card(0)
    assert cs.player.exhaust_pile == [card]
    assert cs.player.powers["rebound"].amount == 1     # credited, ticked
