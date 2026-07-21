"""SP2 Task 8d — relic grab-bag UpFront draw-count parity.

At run init the game shuffles the shared + player relic grab bags on the
UpFront stream (RunManager.InitializeNewRun -> RelicGrabBag.Populate). For a
fully-unlocked run this consumes a constant **230** draws: the shared bag (all
6 rarities, 112 draws) is character-independent and every one of the five
recorded character pools contributes exactly 7 bag-eligible relics (118 player
draws). RunState builds these bags at construction when a string seed seats the
parity streams.

The decisive oracle: after the 230 relic-bag draws + 2 shared-ancient subset
draws, act-0's whole-event-pool shuffle reproduces the save's ``event_ids``
exactly (offset 232). This pins the relic-bag draw COUNT end-to-end for all
five recordings without needing the shuffled relic identities (deferred to the
reward-pull parity in Task 9). The count is character-independent, so it holds
for every seed even though the sim builds only the Ironclad bags today.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.ids import ACT_SIM_NAME, event_game_id
from sts2_rl.conformance.save import parse_save
from sts2_rl.events import (
    GLORY_EVENTS,
    HIVE_EVENTS,
    OVERGROWTH_EVENTS,
    SHARED_EVENTS,
    UNDERDOCKS_EVENTS,
)
from sts2_rl.relic_pools import (
    BAG_RARITIES,
    IRONCLAD_RELIC_POOL,
    SHARED_RELIC_POOL,
    populate_relic_grab_bags,
)
from sts2_rl.rng import RunRngSet
from sts2_rl.run import RunState

REC = Path(__file__).resolve().parents[1].parent / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(
    not REC.exists(), reason="RunReplays saves not present"
)

SEEDS = sorted(p.name for p in REC.iterdir()) if REC.exists() else []

RELIC_BAG_DRAWS = 230
SUBSET_DRAWS = 2  # shared-ancient subset rolls for acts 2 & 3 (a 3-act run)

ACT_EVENT_POOL = {
    "overgrowth": OVERGROWTH_EVENTS,
    "underdocks": UNDERDOCKS_EVENTS,
    "hive": HIVE_EVENTS,
    "glory": GLORY_EVENTS,
}


def test_populate_draw_count_is_230():
    """The shared + player bags together consume exactly 230 UpFront draws."""
    up = RunRngSet("89U21BV1TZ").up_front
    populate_relic_grab_bags(up)
    assert up.counter == RELIC_BAG_DRAWS


def test_bucket_sizes_match_game_source():
    """Per-rarity deque sizes match SharedRelicPool + IroncladRelicPool."""
    up = RunRngSet("89U21BV1TZ").up_front
    shared, player = populate_relic_grab_bags(up)
    assert {r: len(v) for r, v in shared.items()} == {
        "Uncommon": 30, "Common": 25, "Rare": 35, "Shop": 25, "Event": 1, "Ancient": 2,
    }
    assert {r: len(v) for r, v in player.items()} == {
        "Uncommon": 32, "Common": 26, "Rare": 38, "Shop": 26,
    }
    # The player bag is exactly the bag-rarity relics of shared ∪ ironclad,
    # with nothing leaked in or out (Burning Blood — Starter — is excluded).
    allowed = {
        i for i, rar in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL if rar in BAG_RARITIES
    }
    assert {i for deque in player.values() for i in deque} == allowed


def test_runstate_seats_relic_bags_and_lands_upfront_at_230():
    """Constructing a parity RunState builds both bags and leaves UpFront at
    230 — its first consumer, before any act generation."""
    run = RunState(string_seed="89U21BV1TZ")
    assert run.shared_relic_bag is not None and run.player_relic_bag is not None
    assert run.rng_set.up_front.counter == RELIC_BAG_DRAWS


def test_no_string_seed_leaves_relic_bags_absent():
    """The legacy (non-parity) path builds no per-rarity parity bags."""
    run = RunState()
    assert run.shared_relic_bag is None
    assert run.player_relic_bag is None


@pytest.mark.parametrize("seed", SEEDS)
def test_act0_event_shuffle_lands_after_relic_bag(seed):
    """End-to-end: a RunState's 230 relic-bag draws + 2 shared-ancient subset
    draws put UpFront exactly where act-0's event shuffle reproduces the save
    (offset 232) — for every recorded character."""
    o = parse_save(REC / seed / "floor_18" / "run.save")
    act0_id = o.acts[0]
    oracle = o.encounter_ids_by_act[0]["event"]
    pool = [event_game_id(k) for k in ACT_EVENT_POOL[ACT_SIM_NAME[act0_id]]]
    pool += [event_game_id(k) for k in SHARED_EVENTS]
    run = RunState(string_seed=seed)
    up = run.rng_set.up_front  # already at 230 from run init
    assert up.counter == RELIC_BAG_DRAWS
    up.fast_forward_counter(RELIC_BAG_DRAWS + SUBSET_DRAWS)  # shared-ancient subset
    up.shuffle(pool)
    assert pool == oracle
