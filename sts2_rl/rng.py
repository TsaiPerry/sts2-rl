"""Bit-exact port of the game's RNG stack (see docs/superpowers/specs/
2026-07-20-sim-to-replay-design.md). Ground truth: Slay the Spire 2/src/Core/
Random/*.cs and src/Core/Helpers/StringHelper.cs. Validated against
test/data/rng_golden.json (dumped from sts2.dll)."""
from __future__ import annotations

import math
from enum import Enum
import numpy as np

_UMASK64 = (1 << 64) - 1
_UMASK32 = (1 << 32) - 1
_2POW53 = 1.0 / (1 << 53)   # MegaRandom._incrDouble = 1.1102230246251565e-16
_2POW24 = np.float32(1.0) / np.float32(1 << 24)  # _incrFloat = 5.9604645e-08f


def _rotl(x: int, k: int) -> int:
    x &= _UMASK64
    return ((x << k) | (x >> (64 - k))) & _UMASK64


def snake_case(s: str) -> str:
    """StringHelper.SnakeCase — insert '_' before each interior uppercase, lowercase.
    (The game's regex also splits consecutive-uppercase runs; the RunRngType names
    have none, and this matches SnakeCase for every stream name — asserted in tests.)"""
    s = s.strip()
    out = []
    for i, ch in enumerate(s):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch)
    return "".join(out).lower()


def deterministic_hash_code(s: str) -> int:
    """StringHelper.GetDeterministicHashCode — two-accumulator int32 hash."""
    def i32(x: int) -> int:                      # wrap to signed 32-bit
        x &= _UMASK32
        return x - (1 << 32) if x & (1 << 31) else x
    num = 352654597
    num2 = num
    i, n = 0, len(s)
    while i < n:
        num = i32(((num << 5) + num) ^ ord(s[i]))
        if i == n - 1:
            break
        num2 = i32(((num2 << 5) + num2) ^ ord(s[i + 1]))
        i += 2
    return i32(num + i32(num2 * 1566083941))


def make_encounter_rng(run_seed: int, total_floor: int, entry: str) -> "Rng":
    """The per-encounter deterministic Rng the game builds to pick an
    encounter's monster composition (EncounterModel.GenerateMonstersWithSlots):

        uint seed = (uint)((int)runState.Rng.Seed + runState.TotalFloor
                           + GetDeterministicHashCode(Id.Entry));
        _rng = new Rng(seed);

    `run_seed` is the base run seed (RunRngSet.Seed == deterministic_hash_code
    of the string seed); `total_floor` is IRunState.TotalFloor at generation
    time; `entry` is the encounter's slugified class name (Id.Entry, e.g.
    "SLIMES_WEAK"). C# does the arithmetic in int32 and reinterprets as uint —
    addition mod 2**32 is sign-agnostic, so a plain sum masked to 32 bits
    reproduces it exactly."""
    seed = (run_seed + total_floor + deterministic_hash_code(entry)) & _UMASK32
    return Rng(seed=seed)


def make_event_rng(run_seed: int, entry: str) -> "Rng":
    """The per-event deterministic Rng the game builds for an event's random
    draws (EventModel ctor):

        Rng = new Rng((uint)((uint)((int)Owner.RunState.Rng.Seed
              + (IsShared ? 0 : GetPlayerSlotIndex(Owner)))
              + GetDeterministicHashCode(Id.Entry)));

    In single player GetPlayerSlotIndex is 0, so the seed reduces to the base
    run seed + the event's slug hash (NO TotalFloor, unlike the encounter Rng).
    `entry` is the event's slugified class name (e.g. "TABLET_OF_TRUTH")."""
    seed = (run_seed + deterministic_hash_code(entry)) & _UMASK32
    return Rng(seed=seed)


class RunRngType(str, Enum):
    UP_FRONT = "UpFront"
    SHUFFLE = "Shuffle"
    UNKNOWN_MAP_POINT = "UnknownMapPoint"
    COMBAT_CARD_GENERATION = "CombatCardGeneration"
    COMBAT_POTION_GENERATION = "CombatPotionGeneration"
    COMBAT_CARD_SELECTION = "CombatCardSelection"
    COMBAT_ENERGY_COSTS = "CombatEnergyCosts"
    COMBAT_TARGETS = "CombatTargets"
    MONSTER_AI = "MonsterAi"
    NICHE = "Niche"
    COMBAT_ORBS = "CombatOrbs"
    TREASURE_ROOM_RELICS = "TreasureRoomRelics"


class MegaRandom:
    """Xoshiro256** with splitmix64 seeding (MegaRandom.cs)."""

    def __init__(self, seed: int = 0) -> None:
        self.reinitialise(seed)

    @staticmethod
    def splitmix64(x: int) -> tuple[int, int]:
        x = (x + 0x9E3779B97F4A7C15) & _UMASK64
        z = x
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _UMASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _UMASK64
        z = z ^ (z >> 31)
        return x, z

    def reinitialise(self, seed: int) -> None:
        seed &= _UMASK64
        seed, self._s0 = self.splitmix64(seed)
        seed, self._s1 = self.splitmix64(seed)
        seed, self._s2 = self.splitmix64(seed)
        seed, self._s3 = self.splitmix64(seed)

    def next_ulong(self) -> int:
        s0, s1, s2, s3 = self._s0, self._s1, self._s2, self._s3
        result = (_rotl((s1 * 5) & _UMASK64, 7) * 9) & _UMASK64
        t = (s1 << 17) & _UMASK64
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl(s3, 45)
        self._s0, self._s1, self._s2, self._s3 = s0, s1, s2, s3
        return result

    def next_double(self) -> float:
        return (self.next_ulong() >> 11) * _2POW53

    def next_int_full(self) -> int:            # NextInt() — inclusive of int.MaxValue
        return self.next_ulong() >> 33

    def next_float(self) -> float:             # 32-bit float math, matching C#
        return float((np.float32(self.next_ulong() >> 40) * _2POW24))

    def next(self, max_value: int) -> int:     # Next(maxValue) — NextInner
        if max_value < 1:
            raise ValueError("maxValue must be > 0")
        return int(self.next_double() * max_value)

    def next_range(self, min_value: int, max_value: int) -> int:  # Next(min,max)
        if min_value >= max_value:
            raise ValueError("maxValue must be > minValue")
        return int(self.next_double() * (max_value - min_value)) + min_value


class Rng:
    """Counter-wrapping RNG (Rng.cs). One `MegaRandom` per stream."""

    def __init__(self, seed: int = 0, counter: int = 0, name: str | None = None) -> None:
        if name is not None:
            seed = (seed + (deterministic_hash_code(name) & _UMASK32)) & _UMASK32
        self.seed = seed & _UMASK32
        self.counter = 0
        self._random = MegaRandom(self.seed)
        self.fast_forward_counter(counter)

    def fast_forward_counter(self, target: int) -> None:
        if self.counter > target:
            raise ValueError(
                f"Cannot fast-forward counter down (current={self.counter}, target={target})")
        while self.counter < target:
            self.counter += 1
            self._random.next_int_full()

    def next_bool(self) -> bool:
        self.counter += 1
        return self._random.next(2) == 0

    def next_int(self, max_exclusive: int = 0x7FFFFFFF) -> int:
        self.counter += 1
        return self._random.next(max_exclusive)

    def next_int_range(self, min_inclusive: int, max_exclusive: int) -> int:
        if min_inclusive >= max_exclusive:
            raise ValueError("Minimum must be lower than maximum.")
        self.counter += 1
        return self._random.next_range(min_inclusive, max_exclusive)

    def next_unsigned_int(self, min_inclusive: int = 0, max_exclusive: int = _UMASK32) -> int:
        if min_inclusive >= max_exclusive:
            raise ValueError("Minimum must be lower than maximum.")
        self.counter += 1
        num = self._random.next_double()
        return (min_inclusive + int(num * (max_exclusive - min_inclusive))) & _UMASK32

    def next_float(self, mn: float = 0.0, mx: float = 1.0) -> float:
        # Rng.NextFloat(float min, float max): the params are 32-bit floats, so
        # (max - min) is evaluated in float32 before widening to double, and the
        # whole expression is cast back to float32 — matching
        #   (float)(_random.NextDouble() * (double)(max - min) + (double)min)
        mn32 = np.float32(mn)
        mx32 = np.float32(mx)
        if mn32 > mx32:
            raise ValueError("Minimum must not be higher than maximum.")
        self.counter += 1
        return float(np.float32(
            self._random.next_double() * float(np.float32(mx32 - mn32)) + float(mn32)))

    def next_double(self, mn: float | None = None, mx: float | None = None) -> float:
        if mn is None:
            self.counter += 1
            return self._random.next_double()
        if mn > mx:
            raise ValueError("Minimum must not be higher than maximum.")
        self.counter += 1
        return self._random.next_double() * (mx - mn) + mn

    def next_gaussian_double(self, mean=0.0, std_dev=1.0, mn=0.0, mx=1.0) -> float:
        # Rng.NextGaussianDouble: Box-Muller with COS, reject until the
        # standard-normal draw lands in [0,1], then scale to [mn,mx]. Two
        # next_double() per rejection-loop iteration (counter parity).
        if mn > mx:
            raise ValueError("Minimum must not be higher than maximum.")
        while True:
            d = 1.0 - self.next_double()
            num = 1.0 - self.next_double()
            z = math.sqrt(-2.0 * math.log(d)) * math.cos(2.0 * math.pi * num)
            v = mean + z * std_dev
            if 0.0 <= v <= 1.0:
                break
        return v * (mx - mn) + mn

    def next_gaussian_float(self, mean=0.0, std_dev=1.0, mn=0.0, mx=1.0) -> float:
        return float(np.float32(self.next_gaussian_double(mean, std_dev, mn, mx)))

    def next_gaussian_int(self, mean: int, std_dev: int, mn: int, mx: int) -> int:
        # Rng.NextGaussianInt: Box-Muller with SIN (note: not Cos, unlike
        # NextGaussianDouble), round (C# Math.Round = banker's rounding, which
        # Python round() matches), reject until the rounded int is in [mn,mx].
        # No (mx-mn) scaling. Two next_double() per iteration.
        while True:
            d = 1.0 - self.next_double()
            num = 1.0 - self.next_double()
            z = math.sqrt(-2.0 * math.log(d)) * math.sin(2.0 * math.pi * num)
            n = round(mean + std_dev * z)
            if mn <= n <= mx:
                return n

    def next_item(self, items):
        seq = list(items)
        if not seq:
            return None
        return seq[self.next_int_range(0, len(seq))]

    def weighted_next_item(self, items, weight_fetcher):
        # TODO(later SP): C# WeightedNextItem uses float32 for the weight sum and
        # per-item accumulation (Enumerable.Sum(Func<T,float>) -> double -> (float),
        # then float subtraction). This does it in double, which can pick a different
        # item on a boundary-straddling weight set. No consumer exists in the decompiled
        # source yet; fix to float32 + add a golden vector when the first caller is ported.
        seq = list(items)
        rand_input = self.next_float()
        total = sum(weight_fetcher(x) for x in seq)
        acc = rand_input * total
        for item in seq:
            acc -= weight_fetcher(item)
            if acc <= 0.0:
                return item
        return None

    def shuffle(self, lst: list) -> None:
        for i in range(len(lst) - 1, 0, -1):
            j = self.next_int(i + 1)
            lst[i], lst[j] = lst[j], lst[i]


class GameRandomAdapter:
    """A `random.Random`-shaped facade over a single game `Rng` stream.

    The map generator (actmap.py) is already a draw-order-faithful port of
    StandardActMap.cs — it just calls the `random.Random` methods instead of
    the game's `Rng`. This adapter lets that exact code draw game-correct
    values by routing each `random.Random` call to the game primitive it
    mirrors (verified 1:1 against the C# source):

      - ``random()``        -> ``Rng.next_double()``   (one draw; feeds the
                               Box-Muller in actmap.gaussian_int, matching
                               Rng.NextGaussianInt draw-for-draw)
      - ``randrange(n)``    -> ``Rng.next_int_range(0, n)``  (== NextInt(0, n))
      - ``randrange(a, b)`` -> ``Rng.next_int_range(a, b)``  (== NextInt(a, b))
      - ``shuffle(list)``   -> ``Rng.shuffle(list)``   (top-down Fisher-Yates,
                               NextInt(i+1); == ListExtensions.UnstableShuffle)

    Only the methods actmap.py exercises are provided; anything else the map
    pipeline never calls is intentionally absent so an accidental new draw
    site surfaces loudly rather than silently diverging.
    """

    def __init__(self, rng: "Rng") -> None:
        self.rng = rng

    def random(self) -> float:
        return self.rng.next_double()

    def randrange(self, start: int, stop: int | None = None) -> int:
        if stop is None:
            start, stop = 0, start
        return self.rng.next_int_range(start, stop)

    def shuffle(self, seq: list) -> None:
        self.rng.shuffle(seq)

    def choice(self, seq):
        # Rng.NextItem: one NextInt(0, len) draw. (== seq[rng.next_int(len)];
        # NextItem uses NextInt(0,len) which is the same value + one counter.)
        return self.rng.next_item(seq)

    def randint(self, a: int, b: int) -> int:
        # random.randint is inclusive; game NextInt(a, b) is exclusive-max.
        return self.rng.next_int_range(a, b + 1)

    def choices(self, population, weights=None, k: int = 1):
        # One weighted pick == Rng.WeightedNextItem (one NextFloat()). Combat
        # sites use .choices(...)[0]; k>1 would be k independent draws, which no
        # ported site needs — assert to surface a new pattern loudly.
        if weights is None:
            return [self.choice(population) for _ in range(k)]
        assert k == 1, "weighted choices with k>1 has no ported game analogue"
        weight_by_id = {id(item): w for item, w in zip(population, weights)}
        return [self.rng.weighted_next_item(
            population, lambda x: weight_by_id[id(x)])]


def grab_and_remove(bag: list, rng: "Rng", predicate=None):
    """GrabBag.GrabAndRemove for a uniform (weight-1.0) bag (GrabBag.cs).

    Every encounter enters the game's GrabBag with weight 1.0, so
    ``GrabIndex(rng) == int(NextDouble()*count) == rng.next_int(count)`` — one
    draw over the FULL current bag. With a predicate the game first checks
    ``_entries.Any(predicate)``: if nothing matches it returns -1 consuming
    **zero** draws (this is how ActModel.AddWithoutRepeatingTags detects the
    "no tag-safe pick" case and falls back to a no-predicate grab). Otherwise
    it redraws over the full bag until the predicate passes, then removes the
    pick.  ``rng`` is a game ``Rng`` (uses ``.next_int``)."""
    if predicate is not None and not any(predicate(x) for x in bag):
        return None
    while True:
        i = rng.next_int(len(bag))
        if predicate is None or predicate(bag[i]):
            return bag.pop(i)


class RunRngSet:
    """The 12 named per-run RNG streams (RunRngSet.cs)."""

    def __init__(self, string_seed: str) -> None:
        self.string_seed = string_seed
        self.seed = deterministic_hash_code(string_seed) & _UMASK32
        self._rngs: dict[RunRngType, Rng] = {
            t: Rng(self.seed, name=snake_case(t.value)) for t in RunRngType
        }

    def get(self, t: RunRngType) -> Rng:
        return self._rngs[t]

    def counters(self) -> dict[RunRngType, int]:
        return {t: r.counter for t, r in self._rngs.items()}

    def load_counters(self, counters: dict[RunRngType, int]) -> None:
        for t, target in counters.items():
            r = self._rngs[t]
            if target < r.counter:
                r = Rng(self.seed, name=snake_case(t.value))
                r.fast_forward_counter(target)
                self._rngs[t] = r
            else:
                r.fast_forward_counter(target)

    up_front = property(lambda self: self._rngs[RunRngType.UP_FRONT])
    shuffle = property(lambda self: self._rngs[RunRngType.SHUFFLE])
    unknown_map_point = property(lambda self: self._rngs[RunRngType.UNKNOWN_MAP_POINT])
    combat_card_generation = property(lambda self: self._rngs[RunRngType.COMBAT_CARD_GENERATION])
    combat_potion_generation = property(lambda self: self._rngs[RunRngType.COMBAT_POTION_GENERATION])
    combat_card_selection = property(lambda self: self._rngs[RunRngType.COMBAT_CARD_SELECTION])
    combat_energy_costs = property(lambda self: self._rngs[RunRngType.COMBAT_ENERGY_COSTS])
    combat_targets = property(lambda self: self._rngs[RunRngType.COMBAT_TARGETS])
    monster_ai = property(lambda self: self._rngs[RunRngType.MONSTER_AI])
    niche = property(lambda self: self._rngs[RunRngType.NICHE])
    combat_orbs = property(lambda self: self._rngs[RunRngType.COMBAT_ORBS])
    treasure_room_relics = property(lambda self: self._rngs[RunRngType.TREASURE_ROOM_RELICS])


class PlayerRngType(str, Enum):
    REWARDS = "Rewards"
    SHOPS = "Shops"
    TRANSFORMATIONS = "Transformations"


class PlayerRngSet:
    """The 3 per-player RNG streams (PlayerRngSet.cs). Single-player seed ==
    run seed: (uint)(GetDeterministicHashCode(string_seed) + slot 0)."""

    def __init__(self, seed: int) -> None:
        self.seed = seed & _UMASK32
        self._rngs: dict[PlayerRngType, Rng] = {
            t: Rng(self.seed, name=snake_case(t.value)) for t in PlayerRngType
        }

    def get(self, t: PlayerRngType) -> Rng:
        return self._rngs[t]

    def counters(self) -> dict[PlayerRngType, int]:
        return {t: r.counter for t, r in self._rngs.items()}

    def load_counters(self, counters: dict[PlayerRngType, int]) -> None:
        for t, target in counters.items():
            r = self._rngs[t]
            if target < r.counter:
                r = Rng(self.seed, name=snake_case(t.value))
                r.fast_forward_counter(target)
                self._rngs[t] = r
            else:
                r.fast_forward_counter(target)

    rewards = property(lambda self: self._rngs[PlayerRngType.REWARDS])
    shops = property(lambda self: self._rngs[PlayerRngType.SHOPS])
    transformations = property(lambda self: self._rngs[PlayerRngType.TRANSFORMATIONS])
