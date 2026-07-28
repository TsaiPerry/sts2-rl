"""Out-of-combat run-layer fidelity gaps (audit/GAP-QUEUE.md entries 13, 26,
27, 31 — event/EV-1, event/EV-2, event/EV-10, creature_card_cmds/G3).

Run with:  py -m pytest test/test_run_layer_gaps.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.cards import make_card
from sts2_rl.potions import FairyInABottle, Potion, make_potion
from sts2_rl.relics import Relic, make_relic
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ── event/EV-1 — the out-of-combat death / death-prevention pass ───────────


class _SaviorPotion(Potion):
    """A stand-in for Fairy in a Bottle's run-level listener half: C#'s
    RunState.IterateHookListeners (RunState.cs:545-596) yields the potion belt
    when there is no child combat state, so Hook.ShouldDie /
    Hook.AfterPreventingDeath reach the belt during an event."""

    id = "test_savior_potion"
    name = "Test Savior"
    in_reward_pool = False
    HEAL_TO = 7

    def __init__(self) -> None:
        self.prevented = 0

    def should_die(self, creature) -> bool:
        return creature.side != "player"

    def after_preventing_death(self, creature) -> None:
        self.prevented += 1
        creature.discard_potion(self)               # RemoveBeforeUse
        creature.heal(self.HEAL_TO - creature.hp)


def test_run_hp_loss_floors_at_zero():
    # Creature.LoseHpInternal (Creature.cs:450): CurrentHp = Max(CurrentHp - n, 0).
    run = fresh_run()
    run.hp = 5
    run.lose_hp(15)
    assert run.hp == 0
    assert run.is_dead


def test_run_hp_loss_runs_the_death_prevention_pass_over_the_belt():
    run = fresh_run()
    run.hp = 5
    savior = _SaviorPotion()
    assert run.add_potion(savior)
    run.lose_hp(15)
    assert savior.prevented == 1
    assert not run.is_dead
    assert run.hp == _SaviorPotion.HEAL_TO
    assert run.held_potions == []                   # consumed by the save


def test_run_hp_loss_with_an_empty_belt_still_kills():
    run = fresh_run()
    run.hp = 5
    assert run.add_potion(make_potion("fire_potion"))   # no death listener
    run.lose_hp(15)
    assert run.is_dead and run.hp == 0
    assert len(run.held_potions) == 1


@pytest.mark.xfail(
    reason="event/EV-1 (audit/GAP-QUEUE.md entry 13) — HANDOFF to the lead: "
           "FairyInABottle.after_preventing_death (sts2_rl/potions.py:1250-1255) "
           "returns early when `self.combat is None`, so the ported Fairy is "
           "inert during an event even though RunState.lose_hp now runs the "
           "belt death pass. Delete this marker when potions.py grows the "
           "out-of-combat arm.",
    strict=True,
)
def test_fairy_in_a_bottle_saves_a_run_out_of_combat():
    # FairyInABottle.cs:33-45 — ShouldDie is false for its owner and
    # AfterPreventingDeath heals to max(MaxHp * 0.3, 1): 80 * 0.3 = 24.
    run = fresh_run()
    run.hp = 5
    assert run.add_potion(FairyInABottle())
    run.lose_hp(15)
    assert not run.is_dead
    assert run.hp == 24
    assert run.held_potions == []


# ── event/EV-2 — LoseMaxHp's overflow is real damage ───────────────────────


class _BruiseRelic(Relic):
    """A run-level Hook.ModifyHpLost listener that ADDS to the loss — the
    opposite sign from Tungsten Rod, so its effect survives SetMaxHp's
    current-HP clamp and proves the overflow really goes through the HP-loss
    path."""

    id = "test_bruise_relic"
    name = "Test Bruise"
    EXTRA = 5

    def modify_run_hp_loss(self, run, amount: int) -> int:
        return amount + self.EXTRA


def test_lose_max_hp_routes_the_overflow_through_the_hp_loss_path():
    # CreatureCmd.LoseMaxHp (CreatureCmd.cs:815-825): newMax = 80 - 10 = 70,
    # 70 < CurrentHp 80, so Damage(80 - 70 = 10) runs the HP-loss hooks first.
    run = fresh_run()
    run.max_hp, run.hp = 80, 80
    run.relics.append(_BruiseRelic())
    run.lose_max_hp(10)
    assert (run.hp, run.max_hp) == (65, 70)         # 10 + 5 lost, then max 70


def test_lose_max_hp_with_tungsten_rod():
    # The queue's entry 26 predicted 71 here; the C# is 70. The Rod does soften
    # the overflow damage (10 -> 9, HP 71), but LoseMaxHp then calls
    # SetMaxHp(max(1, 70)) -> Creature.SetMaxHpInternal (Creature.cs:493-501),
    # whose `CurrentHp = Min(CurrentHp, MaxHp)` takes the spare point straight
    # back. A reduction is only observable when the loss is not the overflow.
    run = fresh_run()
    run.max_hp, run.hp = 80, 80
    run.add_relic(make_relic("tungsten_rod"))
    run.lose_max_hp(10)
    assert (run.hp, run.max_hp) == (70, 70)


def test_lose_max_hp_can_kill():
    # Leg 2: the damage is computed against the UNFLOORED new max
    # (80 - 100 = -20, so 80 - (-20) = 100 damage) and only then is max HP
    # floored at 1, so the player dies.
    run = fresh_run()
    run.max_hp, run.hp = 80, 80
    run.lose_max_hp(100)
    assert run.is_dead
    assert (run.hp, run.max_hp) == (0, 1)


def test_lose_max_hp_death_can_be_prevented_by_the_belt():
    run = fresh_run()
    run.max_hp, run.hp = 80, 80
    savior = _SaviorPotion()
    assert run.add_potion(savior)
    run.lose_max_hp(100)
    assert savior.prevented == 1
    # The save heals against the OLD max (SetMaxHp has not run yet), then
    # SetMaxHpInternal clamps current HP to the floored max of 1.
    assert (run.hp, run.max_hp) == (1, 1)
    assert not run.is_dead


# ── event/EV-10 — the transform screen is not the removal screen ───────────


def test_transform_screen_excludes_quest_cards():
    # CardSelectCmd.FromDeckForTransformation (CardSelectCmd.cs:487) filters
    # `c.Type != CardType.Quest && c.IsTransformable`.
    run = fresh_run(deck=[make_card("strike"), make_card("spoils_map")])
    assert [c.id for c in run.transformable_cards()] == ["strike"]
    # The REMOVAL predicate (CardModel.IsRemovable, CardModel.cs:737) has no
    # Quest clause and must be left alone.
    assert [c.id for c in run.removable_cards()] == ["strike", "spoils_map"]


# ── creature_card_cmds/G3 — a deck transform is a deck entry ───────────────


def test_deck_transform_runs_the_deck_add_hook():
    # CardCmd.Transform fires Hook.AfterCardChangedPiles for a Deck-pile
    # transform (CardCmd.cs:447) — Bing Bong clones the arrival.
    run = RunState(string_seed="creature-card-cmds-bing-bong")
    run.add_relic(make_relic("bing_bong"))
    before = len(run.deck)
    replacement = run.transform_card(run.deck[0], into=make_card("inflame"))
    # -1 original, +1 replacement, +1 Bing Bong clone.
    assert len(run.deck) == before + 1
    assert [c.id for c in run.deck].count("inflame") == 2
    assert replacement in run.deck


def test_deck_transform_keeps_the_append_at_deck_end_position():
    # CardCmd.cs:437 — a Deck-pile transform AddInternal()s with no index.
    run = RunState(string_seed="creature-card-cmds-position")
    replacement = run.transform_card(run.deck[0], into=make_card("inflame"))
    assert run.deck[-1] is replacement


def test_legacy_deck_transform_also_runs_the_deck_entry_hooks():
    # The legacy (no string_seed) path keeps the in-place replace, but the
    # hooks are not a placement concern.
    run = fresh_run()
    run.add_relic(make_relic("frozen_egg"))
    replacement = run.transform_card(run.deck[3], into=make_card("inflame"))
    assert run.deck[3] is replacement
    assert replacement.upgrade_level == 1
