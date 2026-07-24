"""SP2 Task 6: RunState carries the game's parity RNG streams.

When constructed with a string seed, RunState seats a RunRngSet (12 map/economy
streams) and a PlayerRngSet (3 per-player streams), both seeded from the seed's
deterministic hash (single-player slot 0 => player seed == run seed). Without a
string seed the streams are absent and the legacy random.Random path is
unchanged, so every pre-SP2 test keeps its exact draw sequence."""
from __future__ import annotations

import random

from sts2_rl.rng import PlayerRngSet, RunRngSet, deterministic_hash_code
from sts2_rl.run import RunState

SEED = "89U21BV1TZ"
SEED_HASH = 2221240958  # deterministic_hash_code("89U21BV1TZ") & 0xFFFFFFFF


def test_string_seed_seats_parity_streams():
    run = RunState(string_seed=SEED)
    assert isinstance(run.rng_set, RunRngSet)
    assert isinstance(run.player_rng, PlayerRngSet)
    # Single-player slot 0: both sets share the run seed.
    assert run.rng_set.seed == SEED_HASH
    assert run.player_rng.seed == SEED_HASH
    assert run.string_seed == SEED
    assert deterministic_hash_code(SEED) & 0xFFFFFFFF == SEED_HASH


def test_no_string_seed_leaves_streams_absent():
    # Legacy construction path (the whole existing suite) gets no parity
    # streams and keeps its random.Random exactly as before.
    run = RunState(rng=random.Random(0))
    assert run.rng_set is None
    assert run.player_rng is None
    assert run.string_seed is None


def test_string_seed_does_not_disturb_legacy_rng():
    # Seating the parity streams must consume none of the legacy rng's draws,
    # so two runs built from equal random.Random states — one with a string
    # seed, one without — leave those RNGs at the same position.
    #
    # The merged relic grab bag is no longer the probe for this: a parity run
    # re-seats it from the UpFront-shuffled per-rarity deques (so pulls are a
    # deterministic function of the seed instead of an unseeded shuffle), while
    # the legacy run keeps its own random.Random order. The legacy shuffle
    # still runs in both, which is what this asserts.
    a, b = random.Random(1234), random.Random(1234)
    RunState(rng=a, string_seed=SEED)
    RunState(rng=b)
    assert a.random() == b.random()
    assert a.getstate() == b.getstate()


def test_string_seed_seats_the_grab_bag_from_the_parity_deques():
    # With parity streams the pull bag is the concatenation of the player
    # grab bag's per-rarity deques, so `pull_relic_from_front` scanning it for
    # the rolled rarity IS RelicGrabBag.PullFromFront — and the same seed always
    # yields the same relics (an unseeded shuffle made every replay differ).
    first = RunState(string_seed=SEED)
    second = RunState(string_seed=SEED)
    assert first.relic_grab_bag == second.relic_grab_bag
    assert first.relic_grab_bag
    expected = [
        rid.split(".", 1)[-1].lower()
        for deque in first.player_relic_bag.values()
        for rid in deque
    ]
    # Every bag entry is a ported relic, in deque order (unported ids dropped).
    assert first.relic_grab_bag == [r for r in expected
                                    if r in set(first.relic_grab_bag)]
