"""`ActModel.ApplyDiscoveryOrderModifications` and the profile it reads.

`RunManager.GenerateRooms` (RunManager.cs:678-684) calls it for EVERY act,
gated on `ShouldApplyTutorialModifications()` — which, read against its body
rather than its name, has no player-count and no first-run check: it returns
true for any non-test, Standard-mode run (:698-717). So this is the default
boss-selection path, not a tutorial exception.

What makes it a no-op for most runs is the PROFILE, not the gate: an act whose
bosses the profile has all seen keeps its rolled boss. The sim has no profile,
so `RunState` defaults to `UnlockState.VETERAN` (seen everything, has played
before) and the pass changes nothing — a deliberate default, documented in
`rooms.py`, that a fixture can override.

Queue entry: run_layer/G6.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.rooms import RoomSet, UnlockState, act_rooms

ACTS = ("overgrowth", "underdocks", "hive", "glory")


def _room_set(act: str, unlock=None, seed: int = 3) -> RoomSet:
    return RoomSet.generate(
        act_rooms(act), random.Random(seed), 12, 3, unlock_state=unlock)


@pytest.mark.parametrize("act", ACTS)
def test_every_act_declares_its_boss_discovery_order(act):
    """ActModel.BossDiscoveryOrder is abstract — all four acts override it,
    and each lists exactly its three bosses."""
    rooms = act_rooms(act)
    assert len(rooms.boss_discovery_order) == 3
    assert set(rooms.boss_discovery_order) == set(rooms.boss_keys)


@pytest.mark.parametrize("act", ACTS)
def test_a_fresh_profile_is_pinned_to_the_first_unseen_boss(act):
    rooms = act_rooms(act)
    fresh = _room_set(act, UnlockState.FRESH)
    assert fresh.boss_key == rooms.boss_discovery_order[0]


@pytest.mark.parametrize("act", ACTS)
def test_the_override_walks_the_order_as_bosses_are_seen(act):
    rooms = act_rooms(act)
    order = rooms.boss_discovery_order
    seen = UnlockState(encounters_seen=frozenset(order[:2]), number_of_runs=4)
    assert _room_set(act, seen).boss_key == order[2]


@pytest.mark.parametrize("act", ACTS)
def test_a_profile_that_has_seen_them_all_keeps_the_rolled_boss(act):
    """The default. `VETERAN` has seen everything, so the UpFront roll stands
    — which is what the sim did before the mechanism was ported."""
    rolled = _room_set(act).boss_key
    assert rolled in act_rooms(act).boss_keys
    assert _room_set(act, UnlockState.VETERAN).boss_key == rolled


def test_the_pass_draws_no_rng():
    """It runs after GenerateRooms and only rewrites the result, so two runs
    on the same seed differ ONLY in the overridden entries."""
    rooms = act_rooms("underdocks")
    a = RoomSet.generate(rooms, random.Random(11), 12, 3)
    b = RoomSet.generate(rooms, random.Random(11), 12, 3,
                         unlock_state=UnlockState.FRESH)
    assert a.normal_keys == b.normal_keys      # underdocks has no first-run swaps
    assert a.elite_keys == b.elite_keys
    assert a.event_ids == b.event_ids


class TestOvergrowthFirstRunLineup:
    """`Overgrowth.ApplyActDiscoveryOrderModifications` (Overgrowth.cs:110-127)
    — the only non-empty implementation, and it fires on `NumberOfRuns == 0`
    alone."""

    def test_the_opening_seven_are_the_fixed_lineup(self):
        fresh = _room_set("overgrowth", UnlockState.FRESH)
        assert fresh.normal_keys[:7] == [
            "nibbits_weak", "slimes_weak", "shrinker_beetle_weak",
            "inklets_normal", "mawler_normal", "ruby_raiders",
            "nibbits_normal",
        ]

    def test_the_first_two_events_and_elites_are_pinned(self):
        fresh = _room_set("overgrowth", UnlockState.FRESH)
        assert fresh.event_ids[:2] == ["byrdonis_nest", "sapphire_seed"]
        assert fresh.elite_keys[:2] == ["byrdonis", "phrog_parasite"]

    def test_a_profile_with_one_run_gets_none_of_it(self):
        """`NumberOfRuns == 0` is the whole gate — a profile that has never
        SEEN a boss but HAS finished a run still gets the boss override and
        not the lineup."""
        one_run = UnlockState(encounters_seen=frozenset(), number_of_runs=1)
        rs = _room_set("overgrowth", one_run)
        assert rs.boss_key == "vantom"
        assert rs.normal_keys != _room_set(
            "overgrowth", UnlockState.FRESH).normal_keys

    def test_the_queue_keeps_its_length_and_gains_no_duplicates(self):
        rolled = _room_set("overgrowth")
        fresh = _room_set("overgrowth", UnlockState.FRESH)
        assert len(fresh.normal_keys) == len(rolled.normal_keys)
        assert len(fresh.elite_keys) == len(rolled.elite_keys)
        assert len(fresh.event_ids) == len(set(fresh.event_ids))

    def test_the_two_arms_of_swap_to_or_create_at_index(self):
        """RoomSet.cs:177-192: if the queue already holds the wanted entry the
        two positions SWAP (nothing is lost); if it does not, the entry at the
        index is OVERWRITTEN (that one is lost). Both arms are reachable here —
        which is why an encounter the roll produced can vanish from a
        first-run queue."""
        from sts2_rl.rooms import _swap_to_or_create_at_index

        present = ["a", "b", "c", "d"]
        _swap_to_or_create_at_index(present, 0, "c")
        assert present == ["c", "b", "a", "d"]

        absent = ["a", "b", "c", "d"]
        _swap_to_or_create_at_index(absent, 1, "z")
        assert absent == ["a", "z", "c", "d"]


def test_the_run_default_is_the_veteran_profile():
    from sts2_rl.run import RunState

    assert RunState(rng=random.Random(0)).unlock_state is UnlockState.VETERAN
    assert UnlockState.VETERAN.has_seen_encounter("anything_at_all")
    assert not UnlockState.FRESH.has_seen_encounter("anything_at_all")


class TestTheRecordedProfileDrivesTheReplay:
    """The conformance fixtures DO carry the profile the run was recorded on —
    `players[0].unlock_state` — so the replay does not have to assume one."""

    def _oracle(self, seed: str):
        from pathlib import Path

        from sts2_rl.conformance.save import parse_save

        return parse_save(Path.home() / "Desktop" / "RunReplays" / "RunReplays"
                          / "Resources" / seed / "floor_18" / "run.save")

    @pytest.mark.parametrize("seed", ["89U21BV1TZ", "933T39V18D"])
    def test_both_ironclad_captures_are_fully_unlocked_profiles(self, seed):
        """Which is why `UnlockState.VETERAN` is the right default here: every
        boss is seen and the run counter is astronomically past zero, so the
        discovery-order pass cannot fire for either recording."""
        o = self._oracle(seed)
        assert o.number_of_runs > 0
        bosses = {e for e in o.encounters_seen if e.endswith("_BOSS")}
        assert len(bosses) == 12

    @pytest.mark.parametrize("seed", ["89U21BV1TZ", "933T39V18D"])
    def test_the_runner_builds_that_profile(self, seed):
        from pathlib import Path

        from sts2_rl.conformance.recording import parse_recording
        from sts2_rl.conformance.runner import ReplayRunner

        base = (Path.home() / "Desktop" / "RunReplays" / "RunReplays"
                / "Resources" / seed / "floor_18")
        runner = ReplayRunner(parse_recording(base / "actions.sts2replay"),
                              self._oracle(seed))
        unlock = runner._recorded_unlock_state()
        for act in ACTS:
            for key in act_rooms(act).boss_discovery_order:
                assert unlock.has_seen_encounter(key), (act, key)
