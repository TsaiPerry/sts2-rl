# SP2 — Map/Economy Parity + Conformance Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the sim reproduce the game's map + economy for a given string seed, proven by a conformance harness that replays the `RunReplays` recordings against the parity-sim.

**Architecture:** `RunState` gains `rng_set: RunRngSet` + `player_rng: PlayerRngSet`; map/economy call sites move to the correct streams with game-exact primitives while combat stays on the legacy `random.Random` (disjoint streams make this safe). A harness parses recordings + `run.save`, drives `RunDriver` with a force-win combat stub, and diffs stream counters + structural map/room-type/economy annotations.

**Tech Stack:** Python 3.12 (`venv/Scripts/python.exe`), pytest, numpy; C# .NET 9 for the golden dumper (`tools/rng_dump`). Ground truth: `Slay the Spire 2/src/Core/*`. Oracles: `RunReplays/RunReplays/Resources/*/{actions.sts2replay,run.save}`.

## Global Constraints

- All RNG ports must be **bit-exact** against goldens dumped from `sts2.dll` (`tools/rng_dump`). No approximations except IEEE-exact float compares (`pytest.approx(rel=0, abs=0)`).
- Run tests with `venv/Scripts/python.exe -m pytest` (bare `python` is not on PATH).
- Full suite is green today (2162 tests). Every task ends green; never leave the suite red across a commit.
- Draw **order and count** must match the game exactly — the failure mode is silent. Prefer porting the cited C# method's draw sequence verbatim over "logically equivalent" rewrites.
- Single-player only: player slot index 0, so `PlayerRngSet` seed `== RunRngSet` seed `== deterministic_hash_code(string_seed) & 0xFFFFFFFF`.
- Combat is out of scope; it keeps `random.Random`. Only map/economy streams (`UpFront`, `UnknownMapPoint`, `Rewards`, `Shops`) + the transient `act_N_map` Rng are made parity-correct.
- Line-ending: repo files are LF in git; ignore the CRLF warning on commit.

---

## Phase 1 — Foundation (fully specifiable; the oracle + prerequisites)

### Task 1: Extend the golden dumper for Gaussians + PlayerRngSet

**Files:**
- Modify: `tools/rng_dump/Program.cs`
- Regenerate: `test/data/rng_golden.json`

**Interfaces:**
- Produces golden keys consumed by Tasks 2–3: `gaussian` (int/double/float vectors + resulting counters) and `player_rngset` (seed + per-stream first draw).

- [ ] **Step 1: Add Gaussian + PlayerRngSet dump blocks to `Main()`** (insert before the `root` dictionary is built)

```csharp
        // --- Gaussians (Rng.NextGaussianInt/Double/Float). Data-dependent
        // counter: dump the resulting Counter alongside the values so the
        // Python port's counter accounting can be asserted. ---
        var gi = new Rng(12345); var giVals = new List<int>();
        for (int i = 0; i < 8; i++) giVals.Add(gi.NextGaussianInt(12, 1, 10, 14));
        var gd = new Rng(12345); var gdVals = new List<double>();
        for (int i = 0; i < 8; i++) gdVals.Add(gd.NextGaussianDouble(0.0, 1.0, 0.0, 1.0));
        var gf = new Rng(12345); var gfVals = new List<double>();
        for (int i = 0; i < 8; i++) gfVals.Add(gf.NextGaussianFloat(0f, 1f, 0f, 1f));
        // rest-count style draws used by the acts (mean 7/6, [6,7]).
        var gr = new Rng(12345); var grVals = new List<int>();
        for (int i = 0; i < 8; i++) grVals.Add(gr.NextGaussianInt(7, 1, 6, 7));
        var gaussian = new
        {
            next_gaussian_int_12_1_10_14 = new { values = giVals, counter_after = gi.Counter },
            next_gaussian_int_7_1_6_7 = new { values = grVals, counter_after = gr.Counter },
            next_gaussian_double = new { values = gdVals, counter_after = gd.Counter },
            next_gaussian_float = new { values = gfVals, counter_after = gf.Counter },
        };

        // --- PlayerRngSet: single-player slot-0 seed == run seed. Probe each
        // stream from a fresh set so first draw is measured from counter 0. ---
        string[] playerStreamNames = { "Rewards", "Shops", "Transformations" };
        var playerStreams = new Dictionary<string, object>();
        foreach (var nm in playerStreamNames)
        {
            var pset = new PlayerRngSet((uint)StringHelper.GetDeterministicHashCode("89U21BV1TZ"));
            var t = Enum.Parse<PlayerRngType>(nm);
            var probe = pset.GetType().GetMethod("GetRng",
                BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Public);
            // GetRng is the accessor used by the Rewards/Shops/Transformations
            // properties; if private, fall back to the public property.
            Rng pr = nm switch { "Rewards" => pset.Rewards, "Shops" => pset.Shops, _ => pset.Transformations };
            playerStreams[nm] = new { seed = pr.Seed, first_next_int_1000 = pr.NextInt(1000) };
        }
        var playerRngset = new
        {
            seed_str = "89U21BV1TZ",
            player_seed = (uint)StringHelper.GetDeterministicHashCode("89U21BV1TZ"),
            streams = playerStreams,
        };
```

Then add to the `root` dictionary:

```csharp
            ["gaussian"] = gaussian,
            ["player_rngset"] = playerRngset,
```

- [ ] **Step 2: Rebuild and regenerate the golden**

Run: `cd tools/rng_dump && dotnet run -c Release`
Expected: `Wrote .../test/data/rng_golden.json`. If `PlayerRngSet`/`PlayerRngType` aren't found, add `using MegaCrit.Sts2.Core.Random;` (already present) and confirm the type namespace via `grep -r "class PlayerRngSet" ../../"../Slay the Spire 2"/src` — adjust the `using` to match.

- [ ] **Step 3: Verify new keys exist**

Run: `venv/Scripts/python.exe -c "import json; d=json.load(open('test/data/rng_golden.json')); print(sorted(d)); print(d['gaussian'].keys()); print(d['player_rngset']['streams'].keys())"`
Expected: output includes `gaussian` and `player_rngset`; gaussian has the four sub-keys; player streams are Rewards/Shops/Transformations.

- [ ] **Step 4: Commit**

```bash
git add tools/rng_dump/Program.cs test/data/rng_golden.json
git commit -m "rng golden: add Gaussian + PlayerRngSet vectors for SP2"
```

---

### Task 2: Port `Rng.next_gaussian_int` (+ double/float)

**Files:**
- Modify: `sts2_rl/rng.py` (add methods to class `Rng`)
- Test: `test/test_rng.py`

**Interfaces:**
- Produces: `Rng.next_gaussian_int(mean:int, std_dev:int, min:int, max:int)->int`, `Rng.next_gaussian_double(mean,std_dev,min,max)->float`, `Rng.next_gaussian_float(...)->float`. Each iteration consumes **two** `next_double()` (counter += 2 per rejection loop).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/Scripts/python.exe -m pytest test/test_rng.py -k gaussian -v`
Expected: FAIL with `AttributeError: 'Rng' object has no attribute 'next_gaussian_int'`.

- [ ] **Step 3: Implement (add to class `Rng`, after `next_double`)**

```python
    def next_gaussian_double(self, mean=0.0, std_dev=1.0, mn=0.0, mx=1.0) -> float:
        # Rng.NextGaussianDouble: Box-Muller with COS, reject until the
        # standard-normal draw lands in [0,1], then scale to [mn,mx].
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
        # Rng.NextGaussianInt: Box-Muller with SIN (note: not Cos), round, and
        # reject until the rounded int lands in [mn,mx]. No (mx-mn) scaling.
        while True:
            d = 1.0 - self.next_double()
            num = 1.0 - self.next_double()
            z = math.sqrt(-2.0 * math.log(d)) * math.sin(2.0 * math.pi * num)
            n = _round_half_away(mean + std_dev * z)
            if mn <= n <= mx:
                return n
```

Add `import math` at the top of `rng.py` if absent, and a banker's-vs-away rounding helper matching C# `Math.Round` (MidpointRounding.ToEven is C#'s default for `Math.Round(double)`):

```python
def _round_half_away(x: float) -> int:
    # C# Math.Round(double) uses banker's rounding (MidpointRounding.ToEven).
    # Python's round() also does banker's rounding, so round() matches — but
    # be explicit for the reader.
    return int(round(x))
```

Note: `next_double()` already does `self.counter += 1`, so two calls per loop iteration give the required counter accounting for free.

- [ ] **Step 4: Run to verify it passes**

Run: `venv/Scripts/python.exe -m pytest test/test_rng.py -k gaussian -v`
Expected: PASS (4 tests). If `next_gaussian_int` values match but counters don't, the loop iterated a different number of times → the `Sin`/`Cos` or rounding is wrong; fix before proceeding.

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/rng.py test/test_rng.py
git commit -m "rng: port NextGaussianInt/Double/Float (SP2 U1)"
```

---

### Task 3: Port `PlayerRngSet` / `PlayerRngType`

**Files:**
- Modify: `sts2_rl/rng.py`
- Test: `test/test_rng.py`

**Interfaces:**
- Produces: `PlayerRngType` (`REWARDS="Rewards"`, `SHOPS="Shops"`, `TRANSFORMATIONS="Transformations"`); `PlayerRngSet(seed:int)` with `.get(t)`, `.rewards`/`.shops`/`.transformations` properties, `.counters()->dict`, `.load_counters(dict)`. Seed derivation for single-player: `PlayerRngSet(deterministic_hash_code(s) & 0xFFFFFFFF)`.

- [ ] **Step 1: Write the failing test**

```python
from sts2_rl.rng import PlayerRngSet, PlayerRngType, deterministic_hash_code

def test_player_rngset_seed_and_streams():
    pr = GOLDEN["player_rngset"]
    seed = deterministic_hash_code(pr["seed_str"]) & ((1 << 32) - 1)
    assert seed == pr["player_seed"]
    ps = PlayerRngSet(seed)
    for name, exp in pr["streams"].items():
        stream = ps.get(PlayerRngType(name))
        assert stream.seed == exp["seed"]
        assert stream.next_int(1000) == exp["first_next_int_1000"]

def test_player_rngset_snake_names():
    for member in PlayerRngType:
        # names have no consecutive-uppercase runs; snake_case == lower first char
        assert snake_case(member.value) == member.value.lower()

def test_player_rngset_counters_roundtrip():
    ps = PlayerRngSet(2221240958)
    ps.rewards.next_int(10); ps.rewards.next_int(10); ps.shops.next_int(10)
    c = ps.counters()
    assert c[PlayerRngType.REWARDS] == 2 and c[PlayerRngType.SHOPS] == 1
    ps2 = PlayerRngSet(2221240958)
    ps2.load_counters(c)
    assert ps2.counters() == c
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/Scripts/python.exe -m pytest test/test_rng.py -k player -v`
Expected: FAIL with `ImportError: cannot import name 'PlayerRngSet'`.

- [ ] **Step 3: Implement (add to `rng.py`, mirroring `RunRngType`/`RunRngSet`)**

```python
class PlayerRngType(str, Enum):
    REWARDS = "Rewards"
    SHOPS = "Shops"
    TRANSFORMATIONS = "Transformations"


class PlayerRngSet:
    """The 3 per-player RNG streams (PlayerRngSet.cs). Single-player seed ==
    run seed (deterministic_hash_code(string_seed) + slot 0)."""

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/Scripts/python.exe -m pytest test/test_rng.py -k player -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/rng.py test/test_rng.py
git commit -m "rng: port PlayerRngSet/PlayerRngType (SP2 U1)"
```

---

### Task 4: Recording parser (`.sts2replay` → structured `Recording`)

**Files:**
- Create: `sts2_rl/conformance/__init__.py` (empty)
- Create: `sts2_rl/conformance/recording.py`
- Test: `test/test_conformance_recording.py`

**Interfaces:**
- Produces:
  - `EnemyState(name:str, hp:int, max_hp:int)`
  - `Annotation(hand: list[str] | None, enemies: list[EnemyState] | None, card_name: str | None, card_id: int | None)` — `card_name`/`card_id` from `# CARD.X (id)` on `PlayCard`; `hand`/`enemies` from `|| Hand: [...] Enemies: [...]`.
  - `Command(name:str, args: list[str], comment: str, annotation: Annotation | None, lineno:int)`
  - `Recording(seed:str, acts: list[str], ascension:int, character:str, game:str, mod:str, commands: list[Command])`
  - `parse_recording(path: str | Path) -> Recording`
- `RESOURCES = Path` pointing at `RunReplays/RunReplays/Resources` (resolve relative to the repo's sibling `RunReplays`; test skips if absent).

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import pytest
from sts2_rl.conformance.recording import parse_recording, EnemyState

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")

R1 = REC / "89U21BV1TZ" / "floor_18" / "actions.sts2replay"

def test_header_parsed():
    rec = parse_recording(R1)
    assert rec.seed == "89U21BV1TZ"
    assert rec.ascension == 1
    assert rec.character == "IRONCLAD"
    assert rec.acts == ["ACT.OVERGROWTH", "ACT.HIVE", "ACT.GLORY"]

def test_first_command_and_annotation():
    rec = parse_recording(R1)
    c0 = rec.commands[0]
    assert c0.name == "ChooseEventOption" and c0.args == ["1"]
    play = next(c for c in rec.commands if c.name == "PlayCard")
    assert play.annotation.card_name == "CARD.DEFEND_IRONCLAD"
    assert play.annotation.card_id == 65198830
    assert play.annotation.hand == ["Defend", "Strike", "Defend", "Defend", "Strike"]
    assert play.annotation.enemies == [EnemyState("Fuzzy Wurm Crawler", 57, 57)]

def test_negative_and_multi_args():
    rec = parse_recording(R1)
    proceed = rec.commands[1]
    assert proceed.name == "ChooseEventOption" and proceed.args == ["-1"]
    targeted = next(c for c in rec.commands if c.name == "PlayCard" and len(c.args) == 2)
    assert targeted.args == ["1", "1"]

@pytest.mark.parametrize("d", sorted(p.name for p in REC.iterdir()))
def test_all_recordings_parse(d):
    for floor in ("floor_18", "floor_34", "floor_49"):
        rec = parse_recording(REC / d / floor / "actions.sts2replay")
        assert rec.seed == d and rec.commands
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/Scripts/python.exe -m pytest test/test_conformance_recording.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `recording.py`**

```python
"""Parse RunReplays .sts2replay logs into structured Recordings (SP2 harness)."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class EnemyState:
    name: str
    hp: int
    max_hp: int

@dataclass(frozen=True)
class Annotation:
    hand: list[str] | None = None
    enemies: list[EnemyState] | None = None
    card_name: str | None = None
    card_id: int | None = None

@dataclass(frozen=True)
class Command:
    name: str
    args: list[str]
    comment: str
    annotation: Annotation | None
    lineno: int

@dataclass
class Recording:
    seed: str
    acts: list[str]
    ascension: int
    character: str
    game: str
    mod: str
    commands: list[Command]

_HEADER = re.compile(r"^#\s*([A-Za-z]+):\s*(.*)$")
_CARD = re.compile(r"(CARD\.[A-Z0-9_]+)\s*\((\d+)\)")
_ENEMY = re.compile(r"^(.*?)\s+(\d+)/(\d+)$")

def _parse_enemies(blob: str) -> list[EnemyState]:
    blob = blob.strip()
    if not blob:
        return []
    out = []
    for part in blob.split(","):
        m = _ENEMY.match(part.strip())
        if m:
            out.append(EnemyState(m.group(1).strip(), int(m.group(2)), int(m.group(3))))
    return out

def _parse_annotation(comment: str) -> Annotation | None:
    card_name = card_id = None
    m = _CARD.search(comment)
    if m:
        card_name, card_id = m.group(1), int(m.group(2))
    hand = enemies = None
    if "||" in comment:
        state = comment.split("||", 1)[1]
        hm = re.search(r"Hand:\s*\[(.*?)\]", state)
        em = re.search(r"Enemies:\s*\[(.*?)\]", state)
        if hm:
            inner = hm.group(1).strip()
            hand = [x.strip() for x in inner.split(",")] if inner else []
        if em:
            enemies = _parse_enemies(em.group(1))
    if card_name is None and hand is None and enemies is None:
        return None
    return Annotation(hand=hand, enemies=enemies, card_name=card_name, card_id=card_id)

def parse_recording(path) -> Recording:
    text = Path(path).read_text(encoding="utf-8-sig")
    header: dict[str, str] = {}
    commands: list[Command] = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            m = _HEADER.match(line.strip())
            if m:
                header[m.group(1).lower()] = m.group(2).strip()
            continue
        code, sep, comment = line.partition("#")
        tokens = code.split()
        if not tokens:
            continue
        commands.append(Command(
            name=tokens[0], args=tokens[1:], comment=comment.strip(),
            annotation=_parse_annotation(comment), lineno=i,
        ))
    acts = [a.strip() for a in header.get("acts", "").split(",") if a.strip()]
    return Recording(
        seed=header.get("seed", ""), acts=acts,
        ascension=int(header.get("ascension", "0")),
        character=header.get("character", ""), game=header.get("game", ""),
        mod=header.get("mod", ""), commands=commands,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/Scripts/python.exe -m pytest test/test_conformance_recording.py -v`
Expected: PASS (all, incl. the 5 parametrized recording dirs). If `test_all_recordings_parse` is skipped, the `RunReplays` sibling path is wrong — fix `REC`.

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/conformance/ test/test_conformance_recording.py
git commit -m "conformance: recording (.sts2replay) parser (SP2 U4.1)"
```

---

### Task 5: `run.save` counter parser (`run.save` → `SaveOracle`)

**Files:**
- Create: `sts2_rl/conformance/save.py`
- Test: `test/test_conformance_save.py`

**Interfaces:**
- Produces:
  - `parse_save(path) -> SaveOracle`
  - `SaveOracle(run_seed:str, player_seed:int, ascension:int, acts:list[str], current_act_index:int, run_counters:dict[RunRngType,int], player_counters:dict[PlayerRngType,int], encounter_ids_by_act:list[dict[str,list[str]]], visited_coords, map_history)`
- Uses `RunRngType`/`PlayerRngType` from `sts2_rl.rng` as the counter dict keys (snake_case JSON keys → enum).

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import pytest
from sts2_rl.conformance.save import parse_save
from sts2_rl.rng import RunRngType, PlayerRngType

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays saves not present")
S1 = REC / "89U21BV1TZ" / "floor_18" / "run.save"

def test_save_rng_block():
    o = parse_save(S1)
    assert o.run_seed == "89U21BV1TZ"
    assert o.player_seed == 2221240958
    assert o.ascension == 1
    assert o.run_counters[RunRngType.UP_FRONT] == 413
    assert o.run_counters[RunRngType.UNKNOWN_MAP_POINT] == 3
    assert o.player_counters[PlayerRngType.REWARDS] == 141
    assert o.player_counters[PlayerRngType.SHOPS] == 56

def test_save_encounter_lists():
    o = parse_save(S1)
    assert o.encounter_ids_by_act[0]["normal"][0] == "ENCOUNTER.FUZZY_WURM_CRAWLER_WEAK"
    assert o.acts == ["ACT.OVERGROWTH", "ACT.HIVE", "ACT.GLORY"]

@pytest.mark.parametrize("d", sorted(p.name for p in REC.iterdir()))
def test_all_saves_parse(d):
    for floor in ("floor_18", "floor_34", "floor_49"):
        o = parse_save(REC / d / floor / "run.save")
        assert len(o.run_counters) == 12 and len(o.player_counters) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/Scripts/python.exe -m pytest test/test_conformance_save.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `save.py`**

```python
"""Parse RunReplays run.save (clean JSON) rng block into a SaveOracle (SP2)."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from sts2_rl.rng import RunRngType, PlayerRngType

@dataclass
class SaveOracle:
    run_seed: str
    player_seed: int
    ascension: int
    acts: list[str]
    current_act_index: int
    run_counters: dict
    player_counters: dict
    encounter_ids_by_act: list
    visited_coords: list = field(default_factory=list)
    map_history: list = field(default_factory=list)

_RUN_BY_SNAKE = {t.value: t for t in RunRngType}   # value is PascalCase; need snake
def _snake(s: str) -> str:
    from sts2_rl.rng import snake_case
    return snake_case(s)

def parse_save(path) -> SaveOracle:
    d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    run_counters = {}
    for t in RunRngType:
        run_counters[t] = d["rng"]["counters"][_snake(t.value)]
    prng = d["players"][0]["rng"]
    player_counters = {t: prng["counters"][_snake(t.value)] for t in PlayerRngType}
    encs = []
    for act in d.get("acts", []):
        rooms = act.get("rooms", {})
        encs.append({
            "normal": rooms.get("normal_encounter_ids", []),
            "elite": rooms.get("elite_encounter_ids", []),
        })
    return SaveOracle(
        run_seed=d["rng"]["seed"],
        player_seed=prng["seed"],
        ascension=d.get("ascension", 0),
        acts=[a.get("id") for a in d.get("acts", [])],
        current_act_index=d.get("current_act_index", 0),
        run_counters=run_counters, player_counters=player_counters,
        encounter_ids_by_act=encs,
        visited_coords=d.get("visited_map_coords", []),
        map_history=d.get("map_point_history", []),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/Scripts/python.exe -m pytest test/test_conformance_save.py -v`
Expected: PASS. If a counter key errors, print `d["rng"]["counters"].keys()` and reconcile snake_case (`CombatOrbs`→`combat_orbs`, etc.).

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/conformance/save.py test/test_conformance_save.py
git commit -m "conformance: run.save counter/oracle parser (SP2 U4.2)"
```

---

## Phase 2 — Parity wiring + runner (harness-driven TDD; planned in detail after Phase 1)

Phase 2 tasks are debug-driven parity loops whose exact per-call-site draw corrections can only be pinned by running the Phase-1 harness against the recordings and localizing divergences. They are **not** written here as fabricated code because doing so would invent draw sequences not yet verified against the dll. After Phase 1 lands, extend this plan (re-invoke writing-plans) with the concrete corrections discovered. The tasks, their files, oracles, and done-conditions:

### Task 6: Wire `RunRngSet` + `PlayerRngSet` into `RunState`
- **Files:** `sts2_rl/run.py` (`RunState.__init__`, add `string_seed` param + `rng_set`/`player_rng`); `sts2_rl/driver.py` (`play_random_run` seeds a string).
- **Done:** `RunState(string_seed="89U21BV1TZ")` exposes `rng_set`/`player_rng` seeded per Task 3; existing `self.rng` (random.Random) unchanged; full suite green. **Oracle:** unit test asserting `rng_set.seed == 2221240958`.

### Task 7: Map-layout parity onto the transient `act_N_map` Rng
- **Files:** `sts2_rl/actmap.py` (thread an injected `Rng` instead of `random.Random`; swap `stable_shuffle`→`Rng.shuffle`, `randrange`→`next_int`, gaussian counts→`next_gaussian_int`); `sts2_rl/run.py` map-gen call site (construct `Rng(rng_set.seed, name=f"act_{i+1}_map")`).
- **Source of truth:** `Slay the Spire 2/src/Core/Map/StandardActMap.cs` (`GenerateMap`, `GenerateNextCoord`, `AssignRemainingTypesToRandomPoints`), `Models/Acts/*.GetMapPointTypes`.
- **Done / oracle:** for each recording seed, the generated act-1 map's room-type grid + legal paths are consistent with the save's `map_point_history`/`visited_map_coords` and the recording's `MoveToMapCoord` sequence lands on the implied room types. (Structural — no saved counter for `act_N_map`.)

### Task 8: `UpFront` parity (encounter lists, relic bags, ancients, second boss)

**Status update (2026-07-20):** Tasks 6 & 7 are DONE and green (staged). Task 8 was
reverse-engineered against the recordings; it is a **data-fidelity rewrite**, not simple
wiring, because the sim's pools are incomplete and differently structured than the game.
The exact UpFront draw order (source: `Runs/RunManager.cs:668-692` `GenerateRooms`,
`Models/ActModel.cs:331-386` `GenerateRooms`, `Helpers/GrabBag.cs`,
`Extensions/ListExtensions.cs`) is:

1. **Run init:** shuffle the relic grab bag on `UpFront`. The game keeps **6 separate
   per-rarity lists** (common/uncommon/rare/shop/event/ancient — see
   `save.shared_relic_grab_bag.relic_id_lists`), each `UnstableShuffle`d on `UpFront`
   (~230 draws total for the full ~236-relic pool).
2. **Shared-ancient preamble:** `SharedAncients` (= `[darv]`, 1 elem ⇒ 0-draw shuffle),
   then for each act AFTER the first: `count = UpFront.NextInt(remaining+1)`; assign that
   prefix as the act's shared-ancient subset (2 draws for a 3-act run).
3. **Per act in order** `act.GenerateRooms(UpFront)`: `UnstableShuffle` events
   (`act.AllEvents ∪ ModelDb.AllSharedEvents`, epoch-filtered) → weak normals → regular
   normals (to `GetNumberOfRooms`) → 15 elites → `NextItem` boss → `NextItem` ancient.
   Encounters are drawn by `GrabBag.GrabAndRemove(rng, predicate)`.
4. **Second boss:** if final act + DoubleBoss, `UpFront.NextItem(otherBosses)`.

**PROVEN:** act-0's 31-event shuffle reproduces the save's `event_ids` **exactly** at
`UpFront` offset 232 (≈230 relic-bag + 2 subset), pool order `act.event_pool(13) +
shared(18)`, via `Rng.shuffle`. So the stream, shuffle primitive, and pool order are
correct; the blocker is pool **data** (completeness/order/structure) and the grab model.

**KEY divergence — `GrabBag.GrabAndRemove` rejection model (`GrabBag.cs:96-116`):** the game
picks `int(NextDouble()*count)` over the FULL current bag and **redraws until the predicate
`!SharesTagsWith(last) && != last` passes** (variable draw count), then removes the pick. The
sim's `_add_without_repeating_tags` (`rooms.py:224`) filters to `eligible` then does a single
`rng.choice` — different value AND draw count. Must reimplement.

Decompose into sub-tasks (each ends green; gate every parity change on `run.rng_set is not
None` so the legacy `random.Random` suite is untouched):

- **Task 8a — grab primitives.** Extend `GameRandomAdapter` (`rng.py`) with `.choice(seq)`
  → `seq[self.rng.next_int(len(seq))]` (== `Rng.NextItem`, one draw). Add a faithful
  `grab_and_remove(bag, rng, predicate)` mirroring `GrabBag.cs`:
  ```python
  def grab_and_remove(bag, rng, predicate=None):
      # GrabBag.GrabAndRemove: reject-and-redraw over the full bag until the
      # predicate passes (predicate=None => one draw). rng.next_int(len) ==
      # int(NextDouble()*count) == GrabBag.GrabIndex(rng).
      if predicate is not None and not any(predicate(x) for x in bag):
          return None
      while True:
          i = rng.next_int(len(bag))
          if predicate is None or predicate(bag[i]):
              return bag.pop(i)
  ```
  **Oracle:** unit test asserting the rejection draw-count on a hand-built bag/predicate
  (e.g. predicate rejecting the first-drawn index consumes ≥2 draws). No production behavior
  changes yet.

- **Task 8b — key→game-ID map + pool-completeness oracle (verification FIRST).** Add
  `sts2_rl/conformance/ids.py` mapping each sim encounter/event/relic key → game id.
  Events map cleanly (`"aroma_of_chaos"` → `"EVENT.AROMA_OF_CHAOS"`). Encounters do NOT
  (`"fuzzy_wurm_weak"` → `"ENCOUNTER.FUZZY_WURM_CRAWLER_WEAK"`): build an explicit dict from
  each act source (`Models/Acts/*.cs` `AllEncounters`, id = `"ENCOUNTER."+SNAKE_UPPER(className)`).
  **Oracle:** `test/test_conformance_pools.py` — for each act, `{map(k) for k in pool} ==
  set(save.acts[k].rooms.<list>)` for events/normals/elites/boss. This test will FAIL until
  8c–8e complete; it is the acceptance gate.

- **Task 8c — complete + reorder the event pools.** Add `crystal_sphere` (pos 1) and
  `war_historian_repy` (pos 16) to `events.SHARED_EVENTS` in game order (`ModelDb.cs:135-155`,
  18 total). Confirm each act's `event_pool` order matches its `Models/Acts/*.cs AllEvents`.
  **Oracle:** with `UpFront` fast-forwarded to the per-act event-shuffle offset, the shuffled
  list equals `save.acts[k].rooms.event_ids` (the offset 232 result for act 0 is already
  proven; later acts follow once 8d/8e set their offsets).

- **Task 8d — relic grab bag as 6 per-rarity UpFront lists.** Replace `RunState`'s single
  `relic_grab_bag` (shuffled on `self.rng`) with game-complete per-rarity lists
  (common/uncommon/rare/shop/event/ancient), each `UnstableShuffle`d on `rng_set.up_front`
  at run init when `rng_set` is set (source: `RelicFactory`/`RelicGrabBag`). Complete the
  relic roster to match the game (sim has 96 bag-eligible; game ~236 across the 6 lists — see
  `save.shared_relic_grab_bag.relic_id_lists` for the per-rarity membership). **Oracle:** the
  cumulative `UpFront` counter after run-init equals 232 − 2 = 230 (bag shuffle only), and
  the act-0 event shuffle lands at offset 232 with NO fast-forward.

- **Task 8e — reorder encounter pools + wire `RoomSet.generate` onto the grab model.**
  Reorder `weak_keys`/`normal_keys`/`elite_keys`/`boss_keys` for all four acts to the game's
  `AllEncounters`-filtered order (alphabetical-by-class, filtered by type — e.g. Overgrowth
  weak = FuzzyWurm, Nibbits, ShrinkerBeetle, Slimes). Replace `_add_without_repeating_tags`
  with `grab_and_remove` + the tag predicate; `boss`/`ancient` via `.choice` (== `NextItem`).
  **Oracle:** per act, `[map(k) for k in room_set.normal_keys]` and `elite_keys` equal
  `save.acts[k].rooms.normal_encounter_ids`/`elite_encounter_ids`.

- **Task 8f — generate all acts up front on `UpFront`.** When `rng_set` is set, at
  `start_run` roll the shared-ancient shuffle+subsets then every act's `RoomSet.generate` in
  order on `rng_set.up_front` (mirroring `RunManager.GenerateRooms`), and have `start_act`
  retrieve the pre-generated `RoomSet` instead of rolling lazily; move `driver._roll_shared_
  ancients` onto `rng_set.up_front` (or fold it into `start_run`). Legacy (no `rng_set`) keeps
  the lazy per-act path. **Oracle (Task 8 acceptance):** for every `Resources/*` seed, all
  three acts' `normal_encounter_ids`/`elite_encounter_ids`/`event_ids`/`boss_id`/`ancient_id`/
  `second_boss_id` match the save, and the `UpFront` counter matches at the floor boundary
  (413 for `89U21BV1TZ/floor_18`, cumulative incl. any in-run UpFront draws).

**Files:** `sts2_rl/rng.py` (8a), `sts2_rl/conformance/ids.py` + `test/test_conformance_pools.py`
(8b), `sts2_rl/events/*` (8c), `sts2_rl/run.py` + relic roster (8d, 8f), `sts2_rl/rooms.py`
(8e), `sts2_rl/driver.py` (8f). Expect churn in existing room-generation tests (they assert
the current non-faithful pool order/grab); update them to the game-faithful output per the
repo's "original means game source" convention.

### Task 9: `UnknownMapPoint` + economy (`Rewards`/`Shops`) parity
- **Files:** `sts2_rl/rooms.py` (unknown-room resolution → `rng_set.unknown_map_point` via a ported `RunOddsSet`), `sts2_rl/rewards.py` (reward rolls → `player_rng.rewards`), `sts2_rl/shop.py` (price jitter → `player_rng.shops`).
- **Source of truth:** `Odds/RunOddsSet.cs`, `Odds/UnknownMapPointOdds.cs`, reward/shop generation in `Core/Models` + `Core/Runs`.
- **Done / oracle:** `unknown_map_point`, `rewards`, `shops` counters match the save at every floor boundary; reward annotations in the recording match.

### Task 10: The conformance runner + force-win combat stub
- **Files:** `sts2_rl/conformance/runner.py`, `sts2_rl/conformance/comparators.py`, `test/test_conformance_runner.py`.
- **Behavior:** seed sim from the recording header; drive `RunDriver` translating each SP2-subset command (`MoveToMapCoord`, `ClaimReward`, `TakeCard`, event/rest/shop choices) into its `DecisionRequest` answer; answer `COMBAT` decisions with a force-win stub (end the fight, player alive); run comparators per command; diff the four SP2 counters at floor boundaries; on first mismatch emit a `Divergence(stream, command_index, expected, actual)` report.
- **Done / oracle (SP2 acceptance):** every `Resources/*` recording replays with zero map/room-type/economy-annotation mismatches and matching `UpFront`/`UnknownMapPoint`/`Rewards`/`Shops` counters across all three acts.

---

## Self-Review

- **Spec coverage:** U1 → Tasks 1–3; U2 → Task 7; U3 → Tasks 8–9; U4.1/4.2 → Tasks 4–5; U4.3/4.4 → Task 10; the RNG seam (Architecture) → Task 6. All spec sections map to a task.
- **Placeholder scan:** Phase 1 tasks contain complete code/tests. Phase 2 is explicitly deferred-with-rationale (unverified draw sequences), not vague TODOs — each carries files, source-of-truth citations, and a concrete oracle/done-condition; it will be expanded to bite-sized TDD steps after Phase 1 via a re-invocation of writing-plans.
- **Type consistency:** `RunRngType`/`PlayerRngType` enums used consistently as counter-dict keys across Tasks 3/5; `parse_recording`/`parse_save`/`Recording`/`SaveOracle`/`Annotation`/`EnemyState`/`Command` names consistent between producer and consumer tasks.
