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
from sts2_rl.relics import ALL_RELICS, RelicRarity
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


def test_treasure_chest_relic_rolls_on_the_treasure_room_relics_stream():
    """The chest's rarity roll is `RelicFactory.RollRarity(_rng)` where `_rng`
    is `State.Rng.TreasureRoomRelics` (RunManager.cs:413 builds the
    TreasureRoomRelicSynchronizer with it; the synchronizer rolls one rarity
    per player, then pulls from the front of the shared grab bag).

    On the shared run RNG — unseeded in the conformance harness — the chest
    hands out a different relic every replay, and a max-HP one (Mango, Pear, …)
    silently moves the player's max HP even after the runner reconciles the
    relic list against the save. Same seed must mean same chest."""
    from sts2_rl.rng import RunRngSet
    from sts2_rl.run import RunState

    def chest():
        run = RunState(string_seed="933T39V18D")
        run.start_run(acts=["overgrowth", "hive", "glory"], ascension=0)
        before = run.rng_set.treasure_room_relics.counter
        relic = run.obtain_relic_from_grab_bag(
            rarity_rng=run.rng_set.treasure_room_relics)
        after = run.rng_set.treasure_room_relics.counter
        return relic.id, after - before

    first = chest()
    assert first == chest()          # deterministic from the seed alone
    assert first[1] == 1             # exactly the one rarity NextFloat
    assert isinstance(RunRngSet("x").treasure_room_relics.counter, int)


def test_pull_relic_from_back_shop_rarity_uses_the_parity_bag():
    """relic_pools/step7 (audit/records/seam/relic_pools.json): a shop's
    dedicated Shop-rarity relic slot must draw from the SAME per-player bag
    reward/chest pulls use. `RelicFactory.PullNextRelicFromBack(player,
    rarity, filter)` always calls `player.RelicGrabBag.PullFromBack(rarity,
    ...)` -- the identical `GetAvailableDeque` used by `PullFromFront` --
    regardless of `rarity` (RelicFactory.cs:73-78; RelicGrabBag.cs:156-173).
    `MerchantRelicEntry.FillSlot` passes `RelicRarity.Shop` through that same
    call with no special-casing (MerchantRelicEntry.cs:39). There is no
    separate per-shop `RelicGrabBag` anywhere in the decompiled game.

    Before the fix, `run.pull_relic_from_back(SHOP, ...)` routed instead to
    `RunState._get_shop_relic_bag()` -- a bag built by independently
    rescanning ALL_RELICS and reshuffling on the legacy shared `run.rng`,
    never touching the UpFront-seeded, game-faithful `Shop` deque already
    sitting in `run.player_relic_bag['Shop']` / `run.relic_grab_bag`. That
    left the real deque un-consumed and handed out a relic the game's RNG
    stream never actually produced at that position -- the root cause of the
    `933T39V18D` conformance seed's floor-24 shop divergence (gold 146 vs
    365: the recorded `BuyRelic Miniature Tent` purchase is silently skipped
    because the sim's shop stock doesn't contain it)."""
    run = RunState(string_seed="933T39V18D")
    shop_deque = run.player_relic_bag["Shop"]
    expected_id = shop_deque[-1].split(".", 1)[-1].lower()  # PullFromBack: the deque's back
    before = len(run.relic_grab_bag)

    pulled = run.pull_relic_from_back(RelicRarity.SHOP, set())

    assert pulled is not None
    assert pulled.id == expected_id, (
        "expected the back-pull to take the actual back of the UpFront-"
        "populated Shop deque, not a relic from a disconnected bag "
        f"(got {pulled.id!r}, expected {expected_id!r})")
    assert len(run.relic_grab_bag) == before - 1, (
        "the parity-populated relic_grab_bag must shrink by one on a Shop "
        "pull -- it must be the bag actually consumed")
    assert run._shop_relic_bag is None, (
        "the disconnected legacy _get_shop_relic_bag() must never be built "
        "on the SP2 parity path")


def test_pull_relic_from_back_escalates_and_falls_back_to_circlet():
    """relic_pools/step6: `RelicFactory.PullNextRelicFromBack` shares
    `GetAvailableDeque`'s escalation ladder (Shop -> Common -> Uncommon ->
    Rare) with `PullNextRelicFromFront`, and the same `?? FallbackRelic`
    (Circlet) guard when the ladder runs out (RelicFactory.cs:47,75). An
    exhausted rarity must climb to the next one and ultimately fall back to
    Circlet, never return bare `None` (which left a shop slot visibly empty
    where the game always shows a purchasable relic)."""
    run = RunState(string_seed="933T_BACKPULL_LADDER_PROBE")
    for rid in [r for r in list(run.relic_grab_bag)
                if ALL_RELICS[r].rarity == RelicRarity.RARE]:
        run.relic_grab_bag.remove(rid)
    assert not any(ALL_RELICS[r].rarity == RelicRarity.RARE
                   for r in run.relic_grab_bag), "Rare deque not actually drained"

    pulled = run.pull_relic_from_back(RelicRarity.RARE, set())

    assert pulled is not None and pulled.id == "circlet", (
        "an exhausted Rare deque must climb the (empty, ladder-ending) rest "
        "and fall back to a Circlet, not return None")
