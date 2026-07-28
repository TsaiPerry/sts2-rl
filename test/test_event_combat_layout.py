"""
A Combat-layout event builds its encounter when the ROOM IS ENTERED, not when
the player picks the fight (audit gap `event/EV-12`).

`EventRoom.EnterInternal` (EventRoom.cs:69-72) calls
`EventModel.GenerateInternalCombatState` for every `EventLayoutType.Combat`
event — the monsters stand behind the event text, so the encounter's
`GenerateMonstersWithSlots` and each creature's `SetUniqueMonsterHpValue`
(the run's Niche stream, CombatState.cs:240) run BEFORE any option is chosen.
`EnterCombatWithoutExitingEvent` then REUSES that state rather than generating
a second one (`ShouldCreateCombat = LayoutType != Combat`,
EventModel.cs:624-628).

So the draws are unconditional: a player who takes Punch-Off's NAB branch and
never fights burns exactly the same monster HP rolls as one who does. The sim
took them only on the fight path, and only once the driver built the combat.

The source's three Combat-layout events are PunchOff.cs:33, TheLanternKey.cs:15
and TheArchitect.cs:52; The Architect is not ported, so it has no sim unit here.

Run with:  py -m pytest test/test_event_combat_layout.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import RunState, make_event
from sts2_rl.combat_rng import CombatRng
from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
from sts2_rl.events.the_lantern_key import MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER
from sts2_rl.hooks import HookSystem


def parity_run(seed: str = "AUDITSLICEA", **kwargs) -> RunState:
    kwargs.setdefault("total_floor", 6)
    return RunState(rng=random.Random(0), string_seed=seed, **kwargs)


def combat_hooks(run: RunState) -> HookSystem:
    """A HookSystem carrying the stream bundle a creature reads while it is
    built, the way CombatState.__init__ sets hooks.combat before it creates the
    enemies."""
    hooks = HookSystem()
    hooks.combat = type("_C", (), {"combat_rng": CombatRng.parity(run.rng_set)})()
    return hooks


def niche_cost(event_id: str, path: list[str]) -> int:
    """Niche-stream draws consumed by entering `event_id` and walking `path`."""
    run = parity_run()
    before = run.rng_set.niche.counter
    ev = make_event(event_id, run).begin()
    for step in path:
        assert ev.choose(step), step
    return run.rng_set.niche.counter - before


# ── the draws are unconditional (the point of the gap) ──────────────────────


@pytest.mark.parametrize("event_id,decline,fight,monsters", [
    ("punch_off", ["NAB"], ["I_CAN_TAKE_THEM", "FIGHT"], 2),
    ("the_lantern_key", ["RETURN_THE_KEY"], ["KEEP_THE_KEY", "FIGHT"], 1),
])
def test_combat_layout_event_costs_the_same_draws_on_both_branches(
        event_id, decline, fight, monsters):
    declined = niche_cost(event_id, decline)
    fought = niche_cost(event_id, fight)
    assert declined == fought == monsters


def test_punch_off_rolls_both_constructs_hp_at_room_entry():
    """Two Punch Constructs => two SetUniqueMonsterHpValue draws, before the
    player has chosen anything."""
    run = parity_run()
    before = run.rng_set.niche.counter
    ev = make_event("punch_off", run).begin()
    assert run.rng_set.niche.counter - before == 2
    assert len(ev.pregenerated_hp) == 2


def test_lantern_key_rolls_the_knight_hp_at_room_entry():
    run = parity_run()
    before = run.rng_set.niche.counter
    ev = make_event("the_lantern_key", run).begin()
    assert run.rng_set.niche.counter - before == 1
    assert len(ev.pregenerated_hp) == 1


# ── the fight REUSES the generated state ────────────────────────────────────


def test_the_fight_reuses_the_room_entry_monsters():
    run = parity_run()
    ev = make_event("punch_off", run).begin()
    rolled = list(ev.pregenerated_hp)
    ev.choose("I_CAN_TAKE_THEM")
    ev.choose("FIGHT")
    after_choice = run.rng_set.niche.counter
    monsters = ev.pending_encounter.create_monsters(
        combat_hooks(run), run.rng, None)
    # No second GenerateMonstersWithSlots / SetUniqueMonsterHpValue pass.
    assert run.rng_set.niche.counter == after_choice
    assert [m.max_hp for m in monsters] == rolled


def test_pending_encounter_still_carries_the_source_encounter_identity():
    run = parity_run()
    ev = make_event("punch_off", run).begin()
    ev.choose("I_CAN_TAKE_THEM")
    ev.choose("FIGHT")
    assert ev.pending_encounter.entry == PUNCH_OFF_EVENT_ENCOUNTER.entry
    assert ev.pending_encounter.should_give_rewards
    key = parity_run()
    kev = make_event("the_lantern_key", key).begin()
    kev.choose("KEEP_THE_KEY")
    kev.choose("FIGHT")
    assert kev.pending_encounter.entry == MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER.entry


# ── legacy (no parity streams) keeps the plain encounter ────────────────────


def test_legacy_runs_are_untouched():
    """Legacy runs have no Niche stream to pre-roll, so the encounter stays the
    canonical singleton the pre-parity tests assert on."""
    run = RunState(rng=random.Random(0), total_floor=6)
    ev = make_event("punch_off", run).begin()
    assert ev.pregenerated_hp == []
    ev.choose("I_CAN_TAKE_THEM")
    ev.choose("FIGHT")
    assert ev.pending_encounter is PUNCH_OFF_EVENT_ENCOUNTER
