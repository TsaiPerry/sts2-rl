"""R14 R12 — event/war_historian_repy/g2: the whole body ported.

Source: WarHistorianRepy.cs (event) + HistoryCourse.cs (relic, event pool).
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.events import ALL_EVENTS, make_event
from sts2_rl.relics import ALL_RELICS
from sts2_rl.run import RunState


def _run_with_key() -> RunState:
    run = RunState(rng=random.Random(0))
    run.add_card(make_card("lantern_key"))
    return run


# ══════════════════════════════════════════════════════════════════════════
# HistoryCourse relic (WarHistorianRepy.cs:96-100 grants it)
# ══════════════════════════════════════════════════════════════════════════

def test_history_course_is_registered():
    assert "history_course" in ALL_RELICS
    from sts2_rl.relics.base import RelicRarity
    assert ALL_RELICS["history_course"].rarity == RelicRarity.EVENT


def _combat_with_history_course(deck):
    from sts2_rl.cards import make_card
    return CombatState(
        starting_deck=[make_card(c) for c in deck],
        rng=random.Random(0),
        relics=[make_relic("history_course")],
    )


def _dupes_in_history(combat):
    from sts2_rl.history import CardPlayedEntry
    return [e for e in combat.history.of_type(CardPlayedEntry)
            if getattr(e.card, "is_dupe", False)]


def test_history_course_skips_turn_one():
    """HistoryCourse.cs:19 — `TurnNumber == 1` is a hard skip; there is no
    previous player turn yet. CombatState's construction already runs the
    turn-1 AutoPrePlay phase, so this pins that nothing was queued by it."""
    combat = _combat_with_history_course(
        ["strike"] + ["defend"] * 9)
    assert _dupes_in_history(combat) == []


def test_history_course_autoplays_a_dupe_of_last_turns_attack_or_skill():
    """The core case: play a Strike on turn 1, end the turn (through both
    sides, back to a fresh player turn 2), and confirm the new turn's
    AfterAutoPrePlayPhaseEntered auto-played a dupe of it for free."""
    combat = _combat_with_history_course(
        ["strike"] + ["defend"] * 9)
    hand_ids = [c.id for c in combat.player.hand]
    strike_idx = hand_ids.index("strike")
    hp_before_dupe = combat.enemies[0].hp
    combat.play_card(strike_idx, target_idx=0)
    hp_after_manual_play = combat.enemies[0].hp
    assert hp_after_manual_play < hp_before_dupe
    combat.end_turn()  # -> enemy turn -> fresh player turn 2, AutoPrePlay runs
    assert combat.turn == 2
    dupes = _dupes_in_history(combat)
    assert len(dupes) == 1
    assert dupes[0].card.id == "strike"


def test_history_course_ignores_powers():
    """`(uint)(type - 1) <= 1u` selects exactly Attack (1) and Skill (2), not
    Power (3): a Power played last turn must not be duped."""
    combat = _combat_with_history_course(
        ["inflame"] + ["defend"] * 9)
    hand_ids = [c.id for c in combat.player.hand]
    power_idx = hand_ids.index("inflame")
    combat.play_card(power_idx)
    combat.end_turn()
    assert combat.turn == 2
    assert _dupes_in_history(combat) == []


def test_history_course_ignores_a_dupe_itself():
    """`!e.CardPlay.Card.IsDupe` — a card that was itself a dupe (e.g. from
    an earlier trigger) is not itself re-duped; the search keeps looking
    further back for the last NON-dupe Attack/Skill."""
    combat = _combat_with_history_course(
        ["strike"] + ["defend"] * 9)
    hand_ids = [c.id for c in combat.player.hand]
    strike_idx = hand_ids.index("strike")
    combat.play_card(strike_idx, target_idx=0)
    # Fabricate a dupe entry played (as the auto-play machinery would) right
    # after the real Strike, still within turn 1.
    from sts2_rl.cards.base import create_clone
    from sts2_rl.history import CardPlayedEntry
    real_strike = [e.card for e in _iter_played(combat) if e.card.id == "strike"][0]
    fabricated_dupe = create_clone(real_strike)
    fabricated_dupe.is_dupe = True
    combat.history.entries.append(
        CardPlayedEntry(combat.round_number, fabricated_dupe, is_auto_play=True))
    combat.end_turn()
    assert combat.turn == 2
    new_dupes = [e for e in _dupes_in_history(combat) if e.card is not fabricated_dupe]
    assert len(new_dupes) == 1, "a dupe-of-a-dupe should not happen"


def _iter_played(combat):
    from sts2_rl.history import CardPlayedEntry
    return list(combat.history.of_type(CardPlayedEntry))


# ══════════════════════════════════════════════════════════════════════════
# war_historian_repy event body
# ══════════════════════════════════════════════════════════════════════════

def test_war_historian_repy_still_unreachable_by_is_allowed():
    assert ALL_EVENTS["war_historian_repy"].is_allowed(_run_with_key()) is False


def test_lantern_key_still_routes_here_bypassing_is_allowed():
    """Leg 1 (round 8) stays intact: the routing hook redirects here
    regardless of this event's own IsAllowed."""
    card = make_card("lantern_key")
    run = RunState(rng=random.Random(0))
    run.act_index = 2
    assert card.modify_next_event(run, "brain_leech") == "war_historian_repy"


def test_initial_options_are_unlock_cage_and_unlock_chest():
    run = _run_with_key()
    event = make_event("war_historian_repy", run).begin()
    assert not event.finished
    assert event.option_keys() == ["UNLOCK_CAGE", "UNLOCK_CHEST"]


def test_unlock_cage_grants_history_course_and_consumes_one_key():
    run = _run_with_key()
    event = make_event("war_historian_repy", run).begin()
    event.choose("UNLOCK_CAGE")
    assert any(r.id == "history_course" for r in run.relics)
    assert not any(c.id == "lantern_key" for c in run.deck)
    assert event.finished


def _filled_potion_slots(run) -> int:
    return sum(1 for p in run.potions if p is not None)


def test_unlock_chest_offers_two_potions_and_two_relics():
    run = _run_with_key()
    run.reward_selector = lambda kind, item: True  # take everything offered
    relics_before = len(run.relics)
    potions_before = _filled_potion_slots(run)
    event = make_event("war_historian_repy", run).begin()
    event.choose("UNLOCK_CHEST")
    assert not any(c.id == "lantern_key" for c in run.deck)
    assert len(run.relics) == relics_before + 2
    assert _filled_potion_slots(run) == potions_before + 2
    assert event.finished


def test_unlock_chest_rewards_are_declinable():
    """RewardsCmd.OfferCustom is cancelable (RewardsSet.cs:47-50): a decline
    on every offer leaves the run exactly as it started, minus the key."""
    run = _run_with_key()
    run.reward_selector = lambda kind, item: False
    relics_before = len(run.relics)
    potions_before = _filled_potion_slots(run)
    event = make_event("war_historian_repy", run).begin()
    event.choose("UNLOCK_CHEST")
    assert len(run.relics) == relics_before
    assert _filled_potion_slots(run) == potions_before


def test_second_reward_page_appears_with_a_second_lantern_key():
    """ShouldGetSecondReward (:18-28): true when the deck STILL holds a
    Lantern Key after the initial choice consumed one -- i.e. the player
    carried more than one across separate visits to The Lantern Key event."""
    run = RunState(rng=random.Random(0))
    run.add_card(make_card("lantern_key"))
    run.add_card(make_card("lantern_key"))
    event = make_event("war_historian_repy", run).begin()
    event.choose("UNLOCK_CAGE")
    assert not event.finished
    assert event.option_keys() == ["UNLOCK_CHEST"]
    run.reward_selector = lambda kind, item: True
    event.choose("UNLOCK_CHEST")
    assert event.finished
    assert not any(c.id == "lantern_key" for c in run.deck)
    assert any(r.id == "history_course" for r in run.relics)


def test_no_second_reward_page_with_only_one_key():
    run = _run_with_key()
    event = make_event("war_historian_repy", run).begin()
    event.choose("UNLOCK_CAGE")
    assert event.finished
    assert event.options == []


def test_war_historian_repy_is_still_registered_for_the_shared_shuffle():
    from sts2_rl.events import SHARED_EVENTS
    assert "war_historian_repy" in SHARED_EVENTS
