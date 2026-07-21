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
    # Seating the parity streams must consume none of the legacy rng's draws:
    # a run built with a string seed and one built from an equivalent
    # random.Random shuffle the grab bag identically.
    shared = random.Random(1234)
    run = RunState(rng=random.Random(1234), string_seed=SEED)
    reference_bag = list(run.relic_grab_bag)
    plain = RunState(rng=shared)
    assert plain.relic_grab_bag == reference_bag
