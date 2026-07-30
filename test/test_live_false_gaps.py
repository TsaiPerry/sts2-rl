"""The three gap entries that sat at `live: false` after round 8.

seam/creature_card_cmds/step59, power/improvement/g1 (+AfterCombatEnd),
relic/fake_strike_dummy/g4.

Each was a real divergence with no *currently reachable* observable, which is
why round 6/7 relabelled them rather than closing them. Round 9 implements the
machinery, so the pins below are the observable: they are written against the
C# contract, not against whichever listener happens to be ported today.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardCmd, PowerCmd
from sts2_rl.powers import ImprovementPower, StrengthPower
from sts2_rl.run import RunState


# ══════════════════════════════════════════════════════════════════════════
# creature_card_cmds/step59 — the transform site's three missing dispatches
#
# CardCmd.cs:447-450, in order:
#     await Hook.AfterCardChangedPiles(runState, combatState, replacement,
#                                      pile.Type, null);
#     pile.InvokeCardAddFinished();
#     original.AfterTransformedFrom();
#     replacement.AfterTransformedTo();
# ══════════════════════════════════════════════════════════════════════════

class PileSpy:
    """A listener that records every AfterCardChangedPiles it is handed."""

    def __init__(self):
        self.seen = []

    def after_card_changed_piles(self, card, pile, cloned_by):
        self.seen.append((card.id, pile, cloned_by))


class LatePileSpy:
    def __init__(self, log):
        self._log = log

    def after_card_changed_piles(self, card, pile, cloned_by):
        self._log.append("plain")

    def after_card_changed_piles_late(self, card, pile, cloned_by):
        self._log.append("late")


def _combat_with_one_hand_card(card_id="strike"):
    cs = CombatState(rng=random.Random(0))
    card = make_card(card_id)
    for pile in (cs.player.hand, cs.player.draw_pile,
                 cs.player.discard_pile, cs.player.exhaust_pile):
        pile.clear()
    cs.player.hand.append(card)
    CardCmd  # keep the import honest
    from sts2_rl.cmds import CardPileCmd
    CardPileCmd._enter_combat(cs.hooks, card)
    return cs, card


def test_combat_pile_transform_fires_after_card_changed_piles():
    """Residue (a) of step59: the COMBAT-pile transform fired nothing of the
    kind. CardCmd.cs:447 dispatches for BOTH branches of the pile-type test —
    the Deck early-branch at :437-440 and the combat branch at :441-446 fall
    through to the same call."""
    cs, original = _combat_with_one_hand_card()
    spy = PileSpy()
    cs.hooks.register(spy)
    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, original)
    assert replacement is not None
    assert spy.seen == [(replacement.id, "hand", None)]


def test_after_card_changed_piles_reports_the_pile_the_card_landed_in():
    """The transform site passes `pile2.Type` — the pile the replacement was
    just placed in — into the parameter C# *names* `oldPileType`
    (CardCmd.cs:447). Not a typo on our side: the four ported listeners all read
    `card.Pile.Type` instead (BingBong.cs:31, DarkstonePeriapt.cs:19), so the
    argument's name is misleading and its value is the new pile."""
    cs, original = _combat_with_one_hand_card()
    cs.player.hand.clear()
    cs.player.draw_pile.append(original)
    spy = PileSpy()
    cs.hooks.register(spy)
    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, original)
    assert spy.seen == [(replacement.id, "draw", None)]


def test_transform_fires_from_on_the_original_and_to_on_the_replacement():
    """Residue (b): `AfterTransformedFrom` goes to the card that LEFT and
    `AfterTransformedTo` to the card that arrived (CardCmd.cs:449-450), and the
    pair runs after the pile hook."""
    cs, original = _combat_with_one_hand_card()
    log = []
    spy = PileSpy()

    def _from():
        log.append("from")

    def _to():
        log.append("to")

    original.after_transformed_from = _from
    cs.hooks.register(spy)
    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, original)
    replacement.after_transformed_to = _to  # too late by design; see below
    assert log == ["from"]
    assert spy.seen and spy.seen[0][0] == replacement.id


def test_transform_calls_after_transformed_to_on_the_replacement():
    """Patched on the CLASS so the call the command makes is observed."""
    cs, original = _combat_with_one_hand_card()
    seen = []
    from sts2_rl.cards.base import Card
    real = Card.after_transformed_to
    try:
        Card.after_transformed_to = lambda self: seen.append(self.id)
        replacement = CardCmd.transform_to_random(cs.hooks, cs.player, original)
    finally:
        Card.after_transformed_to = real
    assert seen == [replacement.id]


def test_after_card_changed_piles_runs_a_late_pass():
    """Hook.cs:167-179 is one of the 24 multi-pass dispatchers: a complete plain
    pass, then a complete Late pass. SoulFysh.cs:91-108 is the game's only
    AfterCardChangedPilesLate implementer."""
    cs, original = _combat_with_one_hand_card()
    log = []
    cs.hooks.register(LatePileSpy(log))
    CardCmd.transform_to_random(cs.hooks, cs.player, original)
    assert log == ["plain", "late"]


def test_deck_transform_still_reaches_the_deck_relics_exactly_once():
    """The DECK leg of CardCmd.cs:447 was closed in round 7 and is NOT re-routed
    through the new dispatcher: `Relic.after_card_added_to_deck` already IS
    `AfterCardChangedPiles` filtered to `card.Pile.Type == PileType.Deck`, which
    is the filter all four ported listeners apply themselves (BingBong.cs:31,
    DarkstonePeriapt.cs:19). This is the regression guard for that leg."""
    run = RunState(rng=random.Random(0))
    run.add_relic("darkstone_periapt")
    curse = make_card("regret")
    run.deck.append(curse)
    before = run.max_hp
    run.transform_card(curse, into=make_card("regret"))
    assert run.max_hp == before + 6


# ══════════════════════════════════════════════════════════════════════════
# power/improvement — AfterCombatEnd upgrades `Amount` distinct deck cards
#
# ImprovementPower.cs:17-31:
#   list = PileType.Deck.GetPile(Owner.Player).Cards.Where(c => c.IsUpgradable)
#   for (num = 0; num < Amount; num++) {
#       if (list.Count == 0) break;
#       card = Owner.Player.RunState.Rng.CombatCardSelection.NextItem(list);
#       list.Remove(card);
#       CardCmd.Upgrade(card);
#   }
# ══════════════════════════════════════════════════════════════════════════

def _run_with_combat(deck_ids, improvement=0):
    """A run whose deck is `deck_ids`, plus a combat carrying Improvement.

    The effect fires from `RunState.finish_combat` (the run-level
    Hook.AfterCombatEnd walk), so the tests below end the combat and then sync
    it, which is the order CombatManager.EndCombatInternal uses.
    """
    run = RunState(rng=random.Random(0))
    run.deck = [make_card(i) for i in deck_ids]
    cs = CombatState(rng=random.Random(0))
    if improvement:
        PowerCmd.apply(cs.hooks, cs.player, ImprovementPower, improvement)
    return run, cs


def _finish(run, cs):
    cs._end_combat(player_won=True)
    run.finish_combat(cs)


def test_improvement_upgrades_amount_deck_cards_after_the_combat():
    run, cs = _run_with_combat(["strike"] * 4, improvement=2)
    _finish(run, cs)
    assert sum(1 for c in run.deck if c.upgrade_level) == 2


def test_improvement_picks_are_distinct():
    """`list.Remove(cardModel)` before the next draw — the same card can never
    be upgraded twice by one Improvement."""
    run, cs = _run_with_combat(["strike"] * 3, improvement=3)
    _finish(run, cs)
    assert all(c.upgrade_level == 1 for c in run.deck)


def test_improvement_stops_when_no_upgradable_card_is_left():
    """`if (list.Count == 0) break;` — Amount larger than the upgradable pool
    is not an error and does not double-upgrade."""
    run, cs = _run_with_combat(["strike", "bash"], improvement=5)
    _finish(run, cs)
    assert sum(1 for c in run.deck if c.upgrade_level) == 2


def test_improvement_only_considers_upgradable_cards():
    """`.Where(c => c.IsUpgradable)` — a Curse is not upgradable, so it is not
    even a candidate and the draw cannot land on it."""
    run, cs = _run_with_combat(["regret", "regret", "strike"], improvement=3)
    _finish(run, cs)
    upgraded = [c.id for c in run.deck if c.upgrade_level]
    assert upgraded == ["strike"]


def test_improvement_draws_on_the_card_selection_stream():
    """power/improvement/g1, the entry these tests exist for: the picks come off
    `RunState.Rng.CombatCardSelection` — the sim's
    `combat.combat_rng.card_selection` — and NOT the shared `combat._rng`. Six
    earlier powers in this seam had exactly this defect, which is why the warning
    was recorded even while the effect was a stub."""
    run, cs = _run_with_combat(["strike"] * 4, improvement=2)
    picked = []

    class Separate:
        """Stands in for the CombatCardSelection stream with an INDEPENDENT
        Random, so a draw taken off `combat._rng` instead cannot be mistaken for
        one taken here — in legacy mode the two accessors are the same object."""

        def __init__(self):
            self._own = random.Random(99)

        def choice(self, seq):
            out = self._own.choice(seq)
            picked.append(out)
            return out

    cs.combat_rng._accessors["card_selection"] = Separate()
    shared_before = cs._rng.getstate()
    _finish(run, cs)
    assert len(picked) == 2, "the picks did not come off card_selection"
    assert cs._rng.getstate() == shared_before, "a draw leaked to the shared rng"


def test_improvement_is_inert_on_a_combat_that_is_never_synced():
    """A bare CombatState (the RL combat-only envs and most unit tests) never
    calls `finish_combat`, so there is no run deck in reach and nothing happens —
    the power must not raise on the combat-level end either."""
    cs = CombatState(rng=random.Random(0))
    PowerCmd.apply(cs.hooks, cs.player, ImprovementPower, 2)
    cs._end_combat(player_won=True)


def test_improvement_fires_on_a_lost_combat_too():
    """Hook.AfterCombatEnd runs from EndCombatInternal on EVERY combat end, win
    or loss, and before Hook.AfterCombatVictory (CombatManager.cs:988)."""
    run, cs = _run_with_combat(["strike"] * 3, improvement=1)
    cs.player.hp = 0
    cs._end_combat(player_won=False)
    run.finish_combat(cs)
    assert sum(1 for c in run.deck if c.upgrade_level) == 1


# ══════════════════════════════════════════════════════════════════════════
# relic/fake_strike_dummy/g4 — the additive chain hands over the RUNNING value
#
# ModifyDamageInternal (Hook.cs:2515-2526):
#     num2 = item.ModifyDamageAdditive(target, num, props, dealer, cardSource);
#     num += num2;
# ══════════════════════════════════════════════════════════════════════════

class RunningValueSpy:
    """An additive listener that RETURNS a function of the amount it is handed,
    which is the only way to tell a chain from a parallel sum."""

    def __init__(self, log):
        self._log = log

    def modify_damage_additive(self, target, amount, dealer, card, props):
        self._log.append(amount)
        return 1


def test_modify_damage_additive_hands_each_listener_the_running_total():
    """Every one of the game's 13 additive implementers ignores the `amount`
    parameter, so no *shipped* listener can tell the shapes apart — which is why
    this entry was dormant. The dispatcher's contract is still a chain, and this
    pins it: three +1 listeners see 10, 11, 12, not 10, 10, 10."""
    cs = CombatState(rng=random.Random(0))
    log = []
    for _ in range(3):
        cs.hooks.register(RunningValueSpy(log))
    out = cs.hooks.modify_damage_additive(cs.player, 10)
    assert log == [10, 11, 12]
    assert out == 13


def test_modify_block_additive_hands_each_listener_the_running_total():
    """The block twin, Hook.ModifyBlock (Hook.cs:1310-1340), folds the same
    way."""
    cs = CombatState(rng=random.Random(0))
    log = []

    class BlockSpy:
        def modify_block_additive(self, target, amount, card, props):
            log.append(amount)
            return 2

    cs.hooks.register(BlockSpy())
    cs.hooks.register(BlockSpy())
    out = cs.hooks.modify_block_additive(cs.player, 5)
    assert log == [5, 7]
    assert out == 9


def test_additive_modifiers_list_still_only_collects_real_modifiers():
    """`if (num2 != 0m) list.Add(item)` — the out-param is unchanged by the
    chain rewrite."""
    cs = CombatState(rng=random.Random(0))

    class Zero:
        def modify_damage_additive(self, target, amount, dealer, card, props):
            return 0

    class One:
        def modify_damage_additive(self, target, amount, dealer, card, props):
            return 1

    zero, one = Zero(), One()
    cs.hooks.register(zero)
    cs.hooks.register(one)
    mods = []
    cs.hooks.modify_damage_additive(cs.player, 10, modifiers=mods)
    assert mods == [one]


def test_strength_still_adds_flat_damage():
    """The regression guard: the 13 shipped additive listeners return a
    constant, so the chain must produce the same number the parallel sum did."""
    cs = CombatState(rng=random.Random(0))
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3)
    enemy = cs.enemies[0]
    before = enemy.hp
    cs.player.hand.clear()
    from sts2_rl.cmds import CardPileCmd
    CardPileCmd.add_to_hand(cs.hooks, cs.player, make_card("strike"))
    cs.play_card(0, 0)
    assert before - enemy.hp == 6 + 3
