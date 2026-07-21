from __future__ import annotations
import json
from pathlib import Path
import pytest
from sts2_rl.rng import MegaRandom, Rng

GOLDEN = json.loads((Path(__file__).parent / "data" / "rng_golden.json").read_text())

def test_splitmix64_seed0_state():
    m = MegaRandom(0)
    got = [m._s0, m._s1, m._s2, m._s3]
    assert [str(x) for x in got] == GOLDEN["splitmix64_seed0_state"]

@pytest.mark.parametrize("seed", ["0", "1", "42"])
def test_megarandom_next_ulong(seed):
    m = MegaRandom(int(seed))
    got = [str(m.next_ulong()) for _ in range(8)]
    assert got == GOLDEN["megarandom"][seed]["next_ulong"]

@pytest.mark.parametrize("seed", ["0", "1", "42"])
def test_megarandom_next_double(seed):
    m = MegaRandom(int(seed))
    got = [m.next_double() for _ in range(8)]
    assert got == pytest.approx(GOLDEN["megarandom"][seed]["next_double"], rel=0, abs=0)

@pytest.mark.parametrize("seed", ["0", "1", "42"])
def test_megarandom_next_int_full(seed):
    m = MegaRandom(int(seed))
    assert [m.next_int_full() for _ in range(8)] == GOLDEN["megarandom"][seed]["next_int_full"]

@pytest.mark.parametrize("seed", ["0", "1", "42"])
def test_megarandom_next_100_and_range(seed):
    m = MegaRandom(int(seed))
    assert [m.next(100) for _ in range(8)] == GOLDEN["megarandom"][seed]["next_100"]
    m = MegaRandom(int(seed))
    assert [m.next_range(-5, 5) for _ in range(8)] == GOLDEN["megarandom"][seed]["next_range_neg5_5"]

@pytest.mark.parametrize("seed", ["0", "1", "42"])
def test_megarandom_next_float(seed):
    m = MegaRandom(int(seed))
    got = [m.next_float() for _ in range(8)]
    assert got == pytest.approx(GOLDEN["megarandom"][seed]["next_float"], rel=0, abs=0)

def test_rng_next_int_100():
    r = Rng(12345)
    assert [r.next_int(100) for _ in range(10)] == GOLDEN["rng"]["seed_12345"]["next_int_100"]

def test_rng_next_bool():
    r = Rng(12345)
    assert [r.next_bool() for _ in range(10)] == GOLDEN["rng"]["seed_12345"]["next_bool"]

def test_rng_next_float_double():
    r = Rng(12345)
    assert [r.next_float() for _ in range(5)] == pytest.approx(
        GOLDEN["rng"]["seed_12345"]["next_float"], rel=0, abs=0)
    r = Rng(12345)
    assert [r.next_double() for _ in range(5)] == pytest.approx(
        GOLDEN["rng"]["seed_12345"]["next_double"], rel=0, abs=0)

def test_rng_shuffle_matches_game():
    r = Rng(12345)
    lst = list(range(10))
    r.shuffle(lst)
    assert lst == GOLDEN["rng"]["seed_12345"]["shuffle_0_9"]

def test_rng_next_item():
    r = Rng(12345)
    pool = ["a", "b", "c", "d", "e"]
    assert [r.next_item(pool) for _ in range(10)] == GOLDEN["rng"]["seed_12345"]["next_item_abcde"]

def test_rng_counter_increments():
    r = Rng(0)
    r.next_int(10); r.next_double(); r.next_bool()
    assert r.counter == 3

def test_rng_fast_forward():
    assert Rng(777, 5).next_int(1000) == GOLDEN["fast_forward"]["seed_777_to_5_then_next_int_1000"]

def test_rng_next_gaussian_int():
    g = GOLDEN["gaussian"]["next_gaussian_int_12_1_10_14"]
    r = Rng(12345)
    assert [r.next_gaussian_int(12, 1, 10, 14) for _ in range(8)] == g["values"]
    assert r.counter == g["counter_after"]

def test_rng_next_gaussian_int_rest_counts():
    g = GOLDEN["gaussian"]["next_gaussian_int_7_1_6_7"]
    r = Rng(12345)
    assert [r.next_gaussian_int(7, 1, 6, 7) for _ in range(8)] == g["values"]
    assert r.counter == g["counter_after"]

def test_rng_next_gaussian_double_and_float():
    gd = GOLDEN["gaussian"]["next_gaussian_double"]
    r = Rng(12345)
    assert [r.next_gaussian_double(0.0, 1.0, 0.0, 1.0) for _ in range(8)] == pytest.approx(
        gd["values"], rel=0, abs=0)
    assert r.counter == gd["counter_after"]
    gf = GOLDEN["gaussian"]["next_gaussian_float"]
    r = Rng(12345)
    got = [r.next_gaussian_float(0.0, 1.0, 0.0, 1.0) for _ in range(8)]
    assert got == pytest.approx(gf["values"], rel=0, abs=0)
    assert r.counter == gf["counter_after"]

from sts2_rl.rng import deterministic_hash_code, snake_case, RunRngType

def test_deterministic_hash_code():
    for s, expected in GOLDEN["hash"].items():
        assert deterministic_hash_code(s) == expected, s

def test_snake_case():
    for pascal, expected in GOLDEN["snake_case"].items():
        assert snake_case(pascal) == expected, pascal

def test_runrngtype_snake_names():
    for member in RunRngType:
        assert snake_case(member.value) == GOLDEN["snake_case"][member.value]

def test_rng_named_seed_and_first_draw():
    r = Rng(12345, name="shuffle")
    assert r.seed == GOLDEN["rng"]["named_shuffle"]["seed"]
    assert Rng(12345, name="shuffle").next_int(1000) == \
        GOLDEN["rng"]["named_shuffle"]["first_next_int_1000"]

from sts2_rl.rng import RunRngSet

def test_runrngset_run_seed():
    s = RunRngSet(GOLDEN["runrngset"]["seed_str"])
    assert s.seed == GOLDEN["runrngset"]["run_seed"]

def test_runrngset_stream_seeds_and_first_draw():
    for name, exp in GOLDEN["runrngset"]["streams"].items():
        s = RunRngSet(GOLDEN["runrngset"]["seed_str"])
        rng = s.get(RunRngType(name))
        assert rng.seed == exp["seed"], name
        assert rng.next_int(1000) == exp["first_next_int_1000"], name

def test_runrngset_counter_roundtrip():
    s = RunRngSet("ABCDEFGHIJ")
    s.shuffle.next_int(10); s.shuffle.next_int(10); s.monster_ai.next_bool()
    counters = s.counters()
    assert counters[RunRngType.SHUFFLE] == 2
    assert counters[RunRngType.MONSTER_AI] == 1
    s2 = RunRngSet("ABCDEFGHIJ")
    s2.load_counters(counters)
    assert s2.shuffle.counter == 2
    assert s2.shuffle.next_int(10) == s.shuffle.next_int(10)  # aligned streams

def test_public_exports():
    import sts2_rl
    assert sts2_rl.MegaRandom is MegaRandom
    assert sts2_rl.Rng is Rng
    assert sts2_rl.RunRngSet is RunRngSet
    assert sts2_rl.RunRngType is RunRngType

from sts2_rl.rng import PlayerRngSet, PlayerRngType

def test_player_rngset_seed_and_streams():
    pr = GOLDEN["player_rngset"]
    seed = deterministic_hash_code(pr["seed_str"]) & ((1 << 32) - 1)
    assert seed == pr["player_seed"]
    ps = PlayerRngSet(seed)
    for name, exp in pr["streams"].items():
        stream = ps.get(PlayerRngType(name))
        assert stream.seed == exp["seed"], name
        assert stream.next_int(1000) == exp["first_next_int_1000"], name

def test_player_rngset_snake_names():
    for member in PlayerRngType:
        # names have no consecutive-uppercase runs; snake_case == lowercased
        assert snake_case(member.value) == member.value.lower()

def test_player_rngset_counters_roundtrip():
    ps = PlayerRngSet(2221240958)
    ps.rewards.next_int(10); ps.rewards.next_int(10); ps.shops.next_int(10)
    c = ps.counters()
    assert c[PlayerRngType.REWARDS] == 2 and c[PlayerRngType.SHOPS] == 1
    ps2 = PlayerRngSet(2221240958)
    ps2.load_counters(c)
    assert ps2.counters() == c

def test_rng_next_float_bounded():
    r = Rng(12345)
    got = [r.next_float(0.85, 1.15) for _ in range(5)]
    assert got == pytest.approx(
        GOLDEN["rng"]["seed_12345"]["next_float_bounded_085_115"], rel=0, abs=0)

def test_rng_next_unsigned_int():
    r = Rng(12345)
    got = [r.next_unsigned_int(0, 1000) for _ in range(5)]
    assert got == GOLDEN["rng"]["seed_12345"]["next_unsigned_int_1000"]

def test_rng_float_double_min_gt_max_guard():
    with pytest.raises(ValueError):
        Rng(0).next_float(1.0, 0.0)
    with pytest.raises(ValueError):
        Rng(0).next_double(1.0, 0.0)
    r = Rng(0)               # guard must raise BEFORE incrementing the counter
    with pytest.raises(ValueError):
        r.next_float(1.0, 0.0)
    assert r.counter == 0


# ── Task 8a: grab primitives (GrabBag.cs / Rng.NextItem) ──────────────────

def test_game_random_adapter_choice_matches_next_item():
    from sts2_rl.rng import GameRandomAdapter
    seq = ["x", "y", "z", "w"]
    a = GameRandomAdapter(Rng(99))
    b = Rng(99)
    # .choice == Rng.NextItem (one draw over NextInt(0,len)).
    assert a.choice(seq) == b.next_item(seq)
    assert a.rng.counter == 1 == b.counter

def test_grab_and_remove_no_predicate_one_draw():
    from sts2_rl.rng import grab_and_remove
    bag = ["a", "b", "c", "d"]
    r = Rng(42)
    picked = grab_and_remove(bag, r)
    # One weighted draw over the full bag == NextInt(len); removes the pick.
    assert r.counter == 1
    assert picked not in bag and len(bag) == 3

def test_grab_and_remove_empty_predicate_no_draw():
    from sts2_rl.rng import grab_and_remove
    bag = ["a", "b"]
    r = Rng(42)
    # GrabIndex's `_entries.Any(predicate)` guard: no match => -1, zero draws.
    assert grab_and_remove(bag, r, predicate=lambda x: False) is None
    assert r.counter == 0 and bag == ["a", "b"]

def test_grab_and_remove_rejection_redraws():
    from sts2_rl.rng import grab_and_remove
    bag = ["a", "b", "c", "d", "e"]
    # A fresh Rng(7) draws this index first over the full length-5 bag.
    first_idx = Rng(7).next_int(len(bag))
    first_item = bag[first_idx]
    r = Rng(7)
    # Predicate rejects the first-drawn item: the redraw loop must consume
    # >= 2 draws over the still-full bag (no removal until a pick passes).
    picked = grab_and_remove(bag, r, predicate=lambda x: x != first_item)
    assert picked != first_item
    assert r.counter >= 2
    assert picked not in bag and len(bag) == 4
