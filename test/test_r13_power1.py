"""Round 13, unlabelled batch `power-1` (`.superpowers/sdd/unlabelled-r13/
power-1-brief.md`): pinning tests for the entries settled FIXED in
`.superpowers/sdd/round13/R3-report.md`.

- Dark Embrace: draws `Amount`, not a hard-coded 1 (DarkEmbracePower.cs:47),
  and defers an Ethereal-caused exhaust's draw to `AfterSideTurnEnd` so the
  cards survive the hand flush (DarkEmbracePower.cs:18-23, :37-60).
- Rebound: the destination DECISION moves onto
  `modify_card_play_result_pile` (ReboundPower.cs:19-30), which — as a
  side effect confirmed against CardModel.cs:1890/1931 — also stops Rebound
  redirecting the very card that applied it (a previously-mislabelled
  `faithful` guard; Rebound's own OnPlay runs strictly after the decision).
  The stack tick is folded into that same call, gated on this call being
  the one that performed the redirect, reproducing
  AfterModifyingCardPlayResultPileOrPosition's per-listener "did I change
  it" coupling (Hook.cs:1391-1405) without the notification-list machinery
  the sim does not have (seam/power_cmd G4).
- Retain Hand: the tick moves from `on_enemy_side_end` to
  `after_player_turn_end` (RetainHandPower.cs:28-34's AfterSideTurnEnd is
  the PLAYER side's Hook.AfterTurnEnd, CombatManager.cs:1307) so an extra
  turn — which never reaches `_execute_enemy_turn` — still ticks it.

Run with:  py -m pytest test/test_r13_power1.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, PowerCmd
from sts2_rl.cards import ImperviousCard, StrikeCard, make_card
from sts2_rl.cards.trash_heap_cards import ReboundCard
from sts2_rl.cmds import ExhaustCmd
from sts2_rl.powers import (
    DarkEmbracePower,
    NostalgiaPower,
    ReboundPower,
    RetainHandPower,
)


def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


# ══════════════════════════════════════════════════════════════════════════
# Dark Embrace
# ══════════════════════════════════════════════════════════════════════════

class TestDarkEmbraceAmountAndEtherealDeferral:
    def test_draws_amount_cards_per_exhaust_not_a_hardcoded_one(self):
        """DarkEmbracePower.cs:47 — `CardPileCmd.Draw(base.Amount, ...)`."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DarkEmbracePower, 3)
        draw_before = len(cs.player.draw_pile)
        card = make_card("wound")
        cs.player.hand.append(card)
        ExhaustCmd.exhaust(cs.hooks, cs.player, card)
        assert len(cs.player.draw_pile) == draw_before - 3

    def test_ethereal_exhaust_does_not_draw_immediately(self):
        """DarkEmbracePower.cs:41-44 — a `causedByEthereal` exhaust
        increments `etherealCount` instead of drawing."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DarkEmbracePower, 2)
        draw_before = len(cs.player.draw_pile)
        card = make_card("wound")
        cs.player.hand.append(card)
        cs.hooks.on_card_exhausted(card, caused_by_ethereal=True)
        assert len(cs.player.draw_pile) == draw_before

    def test_ethereal_exhaust_draw_is_deferred_to_after_player_turn_end(self):
        """DarkEmbracePower.cs:52-60 draws `Amount * etherealCount` from
        AfterSideTurnEnd and resets the counter."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DarkEmbracePower, 1)
        draw_before = len(cs.player.draw_pile)  # fresh() starts with 4
        for _ in range(3):
            # Not added to hand: the real caller (`_process_turn_end_cards`)
            # already moved the card to the exhaust pile before firing this
            # hook, so hand size is not affected by the exhausted cards
            # themselves — only isolating the draw-count/deferral logic here.
            card = make_card("wound")
            cs.hooks.on_card_exhausted(card, caused_by_ethereal=True)
        cs.hooks.after_player_turn_end(cs.player)
        assert len(cs.player.draw_pile) == draw_before - 3  # 1 * 3

        # The counter resets: a second turn end with no ethereal exhausts
        # draws nothing further.
        draw_before_2 = len(cs.player.draw_pile)
        cs.hooks.after_player_turn_end(cs.player)
        assert len(cs.player.draw_pile) == draw_before_2

    def test_ethereal_exhaust_draw_survives_the_hand_flush(self):
        """The whole reason DarkEmbracePower.cs defers (source comment
        :18-23): drawing immediately would hand the card to `discard_hand`'s
        flush a moment later. Drives the real turn-end sequence
        (`_process_turn_end_cards` -> flush -> `after_player_turn_end`,
        combat.py's `_end_turn_internal`) rather than calling the power
        directly, so the fix is pinned against the actual ordering."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DarkEmbracePower, 1)
        card = make_card("wound")
        card.is_ethereal = True
        cs.player.hand = [card]
        cs._process_turn_end_cards()
        cs.player.discard_hand(flush=cs.hooks.should_flush_hand())
        cs.hooks.after_player_turn_end(cs.player)
        assert card in cs.player.exhaust_pile
        assert len(cs.player.hand) == 1  # the deferred draw, not flushed away


# ══════════════════════════════════════════════════════════════════════════
# Rebound
# ══════════════════════════════════════════════════════════════════════════

class TestReboundResultPileHook:
    def test_does_not_redirect_the_card_that_applied_it(self):
        """Rebound.cs:31 applies ReboundPower from inside the Rebound card's
        own OnPlay (CardModel.cs:1931), strictly AFTER
        Hook.ModifyCardPlayResultPileTypeAndPosition was already decided for
        THIS card (CardModel.cs:1890). The power cannot see its own
        application in time to redirect the card that created it."""
        cs = fresh()
        rebound = ReboundCard()
        play(cs, rebound, target_idx=0)
        assert rebound in cs.player.discard_pile
        assert rebound not in cs.player.draw_pile
        assert cs.player.powers["rebound"].amount == 1

    def test_redirects_the_next_play_and_consumes_a_stack(self):
        cs = fresh()
        play(cs, ReboundCard(), target_idx=0)
        strike = StrikeCard()
        cs.player.hand.append(strike)
        cs.player.energy = 10
        assert cs.play_card(len(cs.player.hand) - 1, 0)
        assert cs.player.draw_pile[-1] is strike
        assert strike not in cs.player.discard_pile
        assert "rebound" not in cs.player.powers  # 1 -> 0 -> expired

    def test_rebound_registered_first_wins_the_redirect_and_ticks(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 1, applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.player, NostalgiaPower, 1, applier=cs.player)
        strike = StrikeCard()
        cs.player.hand.append(strike)
        cs.player.energy = 10
        assert cs.play_card(len(cs.player.hand) - 1, 0)
        assert strike in cs.player.draw_pile
        assert "rebound" not in cs.player.powers
        assert cs.player.powers["nostalgia"].amount == 1  # never consumes

    def test_nostalgia_registered_first_leaves_rebound_unticked(self):
        """Order-dependent, mirroring C#'s per-listener 'did I change it'
        coupling (Hook.cs:1391-1405): if Nostalgia's own chain call already
        redirected the card, Rebound's guard
        (`pileType != Discard -> unchanged`, ReboundPower.cs:25-28) sees the
        pile already changed and reports no change either, so it is not
        credited with the redirect and does not tick. Not a divergence —
        which power wins is hook_dispatch/G2's listener-order question, out
        of scope here; this pins that the sim now reproduces SOME
        C#-consistent answer instead of Rebound's stack silently surviving
        every contended play."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, NostalgiaPower, 1, applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 1, applier=cs.player)
        strike = StrikeCard()
        cs.player.hand.append(strike)
        cs.player.energy = 10
        assert cs.play_card(len(cs.player.hand) - 1, 0)
        assert strike in cs.player.draw_pile
        assert cs.player.powers["rebound"].amount == 1  # did not tick

    def test_exhausting_card_does_not_spend_a_rebound_stack(self):
        """GetResultPileTypeForCardPlay (CardModel.cs:2070-2083) seeds the
        chain with PileType.Exhaust for an Exhaust-keyword card (or a
        consumed ExhaustOnNextPlay); ReboundPower.cs:25-28 bails on any
        non-Discard incoming pile, so C# Rebound never redirects an
        exhausting card and never spends a stack — it abstains.
        combat.py's `_resolve_card_play` always hands the chain the literal
        "discard" (`exhausts_this_play` is only computed after the hook
        call, and the card is genuinely sitting in `discard_pile` at that
        point — CardModel's PileType.Play limbo is not modelled), so
        ReboundPower has to make the exhaust check itself or it silently
        ticks/redirects an exhausting card while the final pile (moved by
        the separate post-loop exhaust branch) still comes out right."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 1, applier=cs.player)
        card = ImperviousCard()
        play(cs, card)
        assert card in cs.player.exhaust_pile
        assert card not in cs.player.draw_pile
        assert card not in cs.player.discard_pile
        assert cs.player.powers["rebound"].amount == 1  # stack NOT spent

        # The untouched stack still redirects the next ordinary play.
        strike = StrikeCard()
        cs.player.hand.append(strike)
        cs.player.energy = 10
        assert cs.play_card(len(cs.player.hand) - 1, 0)
        assert strike in cs.player.draw_pile
        assert "rebound" not in cs.player.powers


# ══════════════════════════════════════════════════════════════════════════
# Retain Hand
# ══════════════════════════════════════════════════════════════════════════

class _ExtraTurn:
    """A `should_take_extra_turn` listener granting the player one extra
    turn (mirrors Pael's Eye without depending on the relic)."""

    def __init__(self, times: int = 1) -> None:
        self.left = times

    def should_take_extra_turn(self, player) -> bool:
        if self.left:
            self.left -= 1
            return True
        return False


class TestRetainHandTicksOnPlayerSideEnd:
    def test_ticks_on_a_normal_turn_end(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RetainHandPower, 2)
        cs.end_turn()
        assert cs.player.powers["retain_hand"].amount == 1

    def test_ticks_on_an_extra_turn_too(self):
        """RetainHandPower.cs:28-34's AfterSideTurnEnd is the PLAYER side's
        Hook.AfterTurnEnd (CombatManager.cs:1307), which fires on EVERY
        end_turn including one that grants an extra turn — unlike
        `on_enemy_side_end`, which an extra turn never reaches
        (`should_take_extra_turn` short-circuits before
        `_execute_enemy_turn`)."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RetainHandPower, 1)
        cs.hooks.register(_ExtraTurn(times=1))
        cs.end_turn()
        assert "retain_hand" not in cs.player.powers
