# SP3 — Combat Parity + Combat-Card Ids Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the sim reproduce the real game's combat RNG (draw piles, monster moves, combat generation/selection/targets/energy/potion rolls) for a given string seed, port the game's per-combat card-id scheme, and drive/verify all of it against the `RunReplays` recordings.

**Architecture:** A per-purpose RNG seam splits `CombatState`'s single `random.Random` into named streams; in the parity path (run built with a `string_seed`) each maps to the matching `RunRngSet` stream via `GameRandomAdapter`, in the legacy path (all RL training/eval) they all return the one shared `random.Random` so behavior is byte-for-byte unchanged. The SP2 conformance harness's force-win combat stub is replaced by a driver that plays each recording's combat commands and asserts state + stream counters. `NetCombatCardDb` is ported so combat is driven and checked by the recorded `PlayCard {id}`.

**Tech Stack:** Python 3, `pytest`, the ported `sts2_rl.rng` (SP1), the `sts2_rl.conformance` harness (SP2). Run tests with the `py` launcher.

## Global Constraints

- **Never `git commit` or `git push`.** CLAUDE.md rule 4 + repo convention: stage with `git add` only; Perry reviews and commits. Every "commit" step below means **`git add` the listed paths and stop** — do NOT run `git commit`.
- **`from __future__ import annotations`** at the top of every new module; lazy imports inside methods to avoid circular imports (powers ↔ cmds ↔ cards), matching the existing style.
- **Legacy path must stay byte-for-byte.** Any run/combat with no `string_seed` uses the single shared `random.Random`; the full existing suite (baseline **2235 passing**) must stay green after every task.
- **Fidelity to the decompiled source** (`c:\Users\Perry\Desktop\Slay the Spire 2`) is the golden rule; when a fix changes sim behavior to match the game, update legacy tests to the game-correct behavior rather than preserving old sim semantics.
- **Full suite command:** `py -m pytest test/ -q` (takes ~3.5 min). Per-file/'-k' runs during a task; full suite before declaring a task done.
- **Recordings live in** `c:\Users\Perry\Desktop\RunReplays\RunReplays\Resources\<SEED>\floor_{18,34,49}\{actions.sts2replay,run.save}` — 5 seeds × 3 floors = 15 pairs. The floor_49 file of each seed is the whole run from Neow.

---

## File structure

**New files**
- `sts2_rl/combat_rng.py` — `CombatRng`: the per-purpose stream accessor (legacy + parity modes).
- `sts2_rl/combat_card_db.py` — `CombatCardDb`: the ported `NetCombatCardDb` id scheme.
- `sts2_rl/conformance/combat_driver.py` — `ReplayCombatDriver`: plays a recording's combat commands against a live `CombatState`, asserting annotations.
- `test/test_combat_rng.py`, `test/test_combat_card_db.py`, `test/test_conformance_combat.py` — the new suites.

**Modified files**
- `sts2_rl/rng.py` — extend `GameRandomAdapter` (`randint`, `choices`).
- `sts2_rl/combat.py` — build `self.combat_rng`; pass streams into `PlayerCombatState` / `create_monsters`.
- `sts2_rl/player.py` — draw-pile shuffle/reshuffle → `Shuffle` stream.
- `sts2_rl/run.py` — `create_combat` passes the run's combat streams in the parity path.
- `sts2_rl/monsters/state_machine.py` + hand-rolled monster modules — random move roll → `MonsterAi`, at telegraph time.
- `sts2_rl/cards/pool.py`, `combat.py`, `cmds.py`, and per-card/per-monster modules — remaining combat call sites → their streams (U3 convergence).
- `sts2_rl/conformance/comparators.py` — add the 7 combat streams to `compare_counters`.
- `sts2_rl/conformance/runner.py` — swap the force-win stub for `ReplayCombatDriver`; diff combat counters at floor boundaries.

---

## Task 1: `CombatRng` accessor (the seam scaffold)

**Files:**
- Create: `sts2_rl/combat_rng.py`
- Test: `test/test_combat_rng.py`

**Interfaces:**
- Consumes: `sts2_rl.rng.RunRngSet` (has `.shuffle/.monster_ai/.combat_card_generation/.combat_card_selection/.combat_targets/.combat_energy_costs/.combat_potion_generation` → `Rng`), `sts2_rl.rng.GameRandomAdapter(rng)`.
- Produces: `CombatRng` with read-only properties `shuffle, monster_ai, card_gen, card_selection, targets, energy, potion_gen`, each a `random.Random`-shaped object. `CombatRng.legacy(rng)` and `CombatRng.parity(rng_set)` constructors.

- [ ] **Step 1: Write the failing test**

```python
# test/test_combat_rng.py
from __future__ import annotations

import random

from sts2_rl.combat_rng import CombatRng
from sts2_rl.rng import RunRngSet

_ACCESSORS = ("shuffle", "monster_ai", "card_gen", "card_selection",
              "targets", "energy", "potion_gen")


def test_legacy_returns_the_same_random_for_every_accessor():
    r = random.Random(0)
    cr = CombatRng.legacy(r)
    for name in _ACCESSORS:
        assert getattr(cr, name) is r


def test_parity_routes_each_accessor_to_its_stream():
    rs = RunRngSet("89U21BV1TZ")
    cr = CombatRng.parity(rs)
    # each accessor is a GameRandomAdapter over the matching game stream
    assert cr.shuffle.rng is rs.shuffle
    assert cr.monster_ai.rng is rs.monster_ai
    assert cr.card_gen.rng is rs.combat_card_generation
    assert cr.card_selection.rng is rs.combat_card_selection
    assert cr.targets.rng is rs.combat_targets
    assert cr.energy.rng is rs.combat_energy_costs
    assert cr.potion_gen.rng is rs.combat_potion_generation


def test_parity_accessors_are_stable_objects():
    cr = CombatRng.parity(RunRngSet("89U21BV1TZ"))
    assert cr.shuffle is cr.shuffle  # property caches, not a fresh adapter each read
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_combat_rng.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sts2_rl.combat_rng'`.

- [ ] **Step 3: Write minimal implementation**

```python
# sts2_rl/combat_rng.py
"""Per-purpose combat RNG accessor — the SP3 combat seam.

CombatState funnels all combat randomness through one object. The real game
splits it across independent RunRngSet streams (Shuffle, MonsterAi, the Combat*
streams), each drawn in an exact order and count. `CombatRng` exposes one named
accessor per purpose:

  - legacy mode  (CombatRng.legacy): every accessor returns the ONE shared
    `random.Random`, so RL training/eval sequences are unchanged.
  - parity mode  (CombatRng.parity): each accessor is a GameRandomAdapter over
    the matching game stream, so a string-seeded run reproduces the game.
"""
from __future__ import annotations

from .rng import GameRandomAdapter, RunRngSet

_PARITY_STREAMS = {
    "shuffle": "shuffle",
    "monster_ai": "monster_ai",
    "card_gen": "combat_card_generation",
    "card_selection": "combat_card_selection",
    "targets": "combat_targets",
    "energy": "combat_energy_costs",
    "potion_gen": "combat_potion_generation",
}


class CombatRng:
    def __init__(self, accessors: dict) -> None:
        self._accessors = accessors

    @classmethod
    def legacy(cls, rng) -> "CombatRng":
        return cls({name: rng for name in _PARITY_STREAMS})

    @classmethod
    def parity(cls, rng_set: RunRngSet) -> "CombatRng":
        return cls({
            name: GameRandomAdapter(getattr(rng_set, attr))
            for name, attr in _PARITY_STREAMS.items()
        })

    shuffle = property(lambda self: self._accessors["shuffle"])
    monster_ai = property(lambda self: self._accessors["monster_ai"])
    card_gen = property(lambda self: self._accessors["card_gen"])
    card_selection = property(lambda self: self._accessors["card_selection"])
    targets = property(lambda self: self._accessors["targets"])
    energy = property(lambda self: self._accessors["energy"])
    potion_gen = property(lambda self: self._accessors["potion_gen"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_combat_rng.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Stage (do NOT commit)**

```bash
git add sts2_rl/combat_rng.py test/test_combat_rng.py
```

---

## Task 2: Extend `GameRandomAdapter` with `randint` + `choices`

The combat call sites use `random.Random` idioms the map path never did. `randint`/`choices` map 1:1 to game primitives; add them. **`sample` is deliberately NOT added** — batched `sample` sites have no single generic game analogue and are rewritten per call site in U3.

**Files:**
- Modify: `sts2_rl/rng.py` (the `GameRandomAdapter` class, ~lines 243-282)
- Test: `test/test_rng.py` (append)

**Interfaces:**
- Consumes: `Rng.next_int_range`, `Rng.weighted_next_item`.
- Produces: `GameRandomAdapter.randint(a, b)` → `next_int_range(a, b + 1)`; `GameRandomAdapter.choices(population, weights, k=1)` → list of `k` weighted picks, each one `WeightedNextItem` draw (one `NextFloat()`).

- [ ] **Step 1: Write the failing test**

```python
# append to test/test_rng.py
def test_adapter_randint_is_inclusive_next_int_range():
    from sts2_rl.rng import GameRandomAdapter, Rng
    a = GameRandomAdapter(Rng(123, name="shuffle"))
    b = GameRandomAdapter(Rng(123, name="shuffle"))
    # randint(lo, hi) == next_int_range(lo, hi+1): same value, same one draw
    assert a.randint(0, 5) == b.rng.next_int_range(0, 6)
    assert a.rng.counter == b.rng.counter == 1


def test_adapter_choices_single_weighted_matches_weighted_next_item():
    from sts2_rl.rng import GameRandomAdapter, Rng
    pop = ["A", "B", "C"]
    weights = [2, 1, 1]
    a = GameRandomAdapter(Rng(7, name="monster_ai"))
    b = GameRandomAdapter(Rng(7, name="monster_ai"))
    got = a.choices(pop, weights=weights)[0]
    exp = b.rng.weighted_next_item(pop, lambda i, x: weights[i])
    assert got == exp
    assert a.rng.counter == b.rng.counter == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_rng.py -k "adapter_randint or adapter_choices" -q`
Expected: FAIL — `AttributeError: 'GameRandomAdapter' object has no attribute 'randint'`.

- [ ] **Step 3: Write minimal implementation**

Confirm `Rng.weighted_next_item`'s signature first (`grep -n "def weighted_next_item" sts2_rl/rng.py` — it takes `(items, weight_fetcher)` where `weight_fetcher` is called per item). Then add to `GameRandomAdapter`:

```python
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
        idx_weight = lambda i, _x: weights[i]
        return [self.rng.weighted_next_item(population, idx_weight)]
```

If `weighted_next_item`'s callback is `(item)` rather than `(index, item)`, adapt the lambda to match its real signature (read the method).

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_rng.py -k "adapter_randint or adapter_choices" -q`
Expected: PASS.

- [ ] **Step 5: Run the full rng suite (guard the SP1/SP2 goldens)**

Run: `py -m pytest test/test_rng.py -q`
Expected: PASS (all existing + 2 new).

- [ ] **Step 6: Stage (do NOT commit)**

```bash
git add sts2_rl/rng.py test/test_rng.py
```

---

## Task 3: Build `CombatRng` in `CombatState` + wire `create_combat`

Give `CombatState` a `combat_rng`. It keeps taking `rng` (legacy) and gains an optional `rng_set`; when `rng_set` is passed it builds a parity `CombatRng`, else a legacy one over `self._rng`. `create_combat` passes the run's `rng_set` **only in the parity path** (`self.rng_set is not None`). Nothing routes to the new streams yet, so counters stay at 0 and the whole suite stays green — this task is pure plumbing.

**Files:**
- Modify: `sts2_rl/combat.py` (`__init__` signature + body, ~lines 71-85)
- Modify: `sts2_rl/run.py` (`create_combat`, ~lines 983-1010)
- Test: `test/test_combat_rng.py` (append)

**Interfaces:**
- Consumes: `CombatRng.legacy`, `CombatRng.parity`, `RunState.rng_set`.
- Produces: `CombatState.combat_rng: CombatRng`; `CombatState.__init__(..., rng_set: RunRngSet | None = None)`.

- [ ] **Step 1: Write the failing test**

```python
# append to test/test_combat_rng.py
def test_combatstate_builds_legacy_combat_rng_by_default():
    import random
    from sts2_rl.combat import CombatState
    c = CombatState(rng=random.Random(0))
    assert c.combat_rng.shuffle is c._rng


def test_combatstate_parity_uses_run_streams():
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    rs = RunRngSet("89U21BV1TZ")
    c = CombatState(rng_set=rs)
    assert c.combat_rng.shuffle.rng is rs.shuffle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_combat_rng.py -k combatstate -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'rng_set'`.

- [ ] **Step 3: Implement in `combat.py`**

Add `rng_set: "RunRngSet | None" = None` to `__init__`'s params. After `self._rng = rng or random.Random()` (line 85) insert:

```python
        from .combat_rng import CombatRng
        self.combat_rng = (
            CombatRng.parity(rng_set) if rng_set is not None
            else CombatRng.legacy(self._rng)
        )
```

Leave every existing `self._rng` use untouched for now (later tasks migrate them). `PlayerCombatState` and `create_monsters` keep receiving `self._rng` this task.

- [ ] **Step 4: Implement in `run.py` `create_combat`**

In the `CombatState(...)` construction, add one kwarg (right after `rng=self.rng,`):

```python
            rng_set=self.rng_set,   # None in legacy runs → legacy CombatRng
```

`self.rng_set` is `None` unless the run was built with `string_seed`, so legacy runs are unaffected.

- [ ] **Step 5: Run tests**

Run: `py -m pytest test/test_combat_rng.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Full suite (nothing should change — pure plumbing)**

Run: `py -m pytest test/ -q`
Expected: PASS (2235 + new).

- [ ] **Step 7: Stage (do NOT commit)**

```bash
git add sts2_rl/combat.py sts2_rl/run.py test/test_combat_rng.py
```

---

## Task 4: Route the `Shuffle` stream (draw piles)

Migrate the draw-pile shuffle sites to `combat_rng.shuffle`. `PlayerCombatState` currently holds `self._rng` (a `random.Random`); give it the `CombatRng` and use `.shuffle`. Legacy `.shuffle` is still the shared `random.Random`, so `random.Random(seed)` tests are unchanged. Parity runs now draw from the `Shuffle` stream.

**Files:**
- Modify: `sts2_rl/player.py` (constructor `self._rng` → store `CombatRng`; lines 50/53/114)
- Modify: `sts2_rl/combat.py` (pass `self.combat_rng` into `PlayerCombatState`)
- Modify: `sts2_rl/cards/havoc.py:41` (`ctx.combat._rng.shuffle` → `ctx.combat.combat_rng.shuffle.shuffle`)
- Test: `test/test_combat_rng.py` (append)

**Interfaces:**
- Consumes: `CombatState.combat_rng`.
- Produces: `PlayerCombatState.__init__(..., combat_rng)`; draws from `Shuffle` in parity mode.

- [ ] **Step 1: Write the failing test (parity Shuffle counter advances; legacy unchanged)**

```python
# append to test/test_combat_rng.py
def test_parity_combat_start_draws_from_shuffle_stream():
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    rs = RunRngSet("89U21BV1TZ")
    before = rs.shuffle.counter
    CombatState(rng_set=rs)  # constructs player -> initial shuffle
    assert rs.shuffle.counter > before  # the initial deck shuffle drew from Shuffle


def test_legacy_shuffle_sequence_unchanged():
    import random
    from sts2_rl.combat import CombatState
    # A fixed-seed legacy combat draws the SAME opening hand as a bare
    # random.Random(0).shuffle of the deck would — i.e. nothing rerouted.
    c = CombatState(rng=random.Random(1234))
    assert c.combat_rng.shuffle is c._rng  # still the shared Random
```

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest test/test_combat_rng.py -k "shuffle_stream or shuffle_sequence" -q`
Expected: `test_parity_combat_start_draws_from_shuffle_stream` FAILS (counter unchanged — player still uses the legacy `self._rng`).

- [ ] **Step 3: Implement — `PlayerCombatState` takes the `CombatRng`**

In `player.py` constructor: change the `rng` parameter to `combat_rng`, store `self._combat_rng = combat_rng`, and replace the three shuffle draws:
- line 53 `rng.shuffle(self.draw_pile)` → `combat_rng.shuffle.shuffle(self.draw_pile)`
- line 114 `self._rng.shuffle(self.draw_pile)` → `self._combat_rng.shuffle.shuffle(self.draw_pile)`

Keep any *non-shuffle* `self._rng` use in `player.py` (if any — grep to confirm there are none beyond shuffle) pointing at a plain rng: expose `self._rng = combat_rng.shuffle.rng`-style only if needed; prefer routing each to its purpose. Update the `combat.py` call (line 101-105) to pass `self.combat_rng` instead of `self._rng`.

- [ ] **Step 4: Implement — `havoc.py`**

`sts2_rl/cards/havoc.py:41`: `ctx.combat._rng.shuffle(player.draw_pile)` → `ctx.combat.combat_rng.shuffle.shuffle(player.draw_pile)`. (Havoc plays the top of the draw pile after a shuffle — same stream.)

- [ ] **Step 5: Run tests**

Run: `py -m pytest test/test_combat_rng.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite (legacy sequences must be identical)**

Run: `py -m pytest test/ -q`
Expected: PASS (2235 + new). Any failure here means a legacy shuffle got rerouted incorrectly — fix before proceeding.

- [ ] **Step 7: Stage (do NOT commit)**

```bash
git add sts2_rl/player.py sts2_rl/combat.py sts2_rl/cards/havoc.py test/test_combat_rng.py
```

---

## Task 5: `CombatCardDb` — port `NetCombatCardDb`

Structural (no RNG). At combat start, assign contiguous `uint` ids to every card by walking piles in `AllPiles` order (`Hand, DrawPile, DiscardPile, ExhaustPile, PlayPile`); cards added later get the next id in add order. Ids are by card *identity* (Python `id()` / object identity), stable for the combat.

The sim has no pile `ContentsChanged` event and no distinct `PlayPile`, so port as: (a) `start(combat)` walks `hand + draw_pile + discard_pile + exhaust_pile` (game order; empty hand at true start ⇒ deck in draw pile) assigning ids; (b) `refresh(combat)` re-walks and ids any not-yet-seen card, called after every command in the driver. The **card currently resolving** (the game's `PlayPile`) is handled in Task 8 against real recordings; scan order is the starting point.

**Files:**
- Create: `sts2_rl/combat_card_db.py`
- Test: `test/test_combat_card_db.py`

**Interfaces:**
- Consumes: `CombatState.player` (`.hand/.draw_pile/.discard_pile/.exhaust_pile`).
- Produces: `CombatCardDb.start(combat)`, `.refresh(combat)`, `.get(id) -> Card`, `.id_of(card) -> int`, `.ordered_piles(combat) -> list[list[Card]]`.

- [ ] **Step 1: Write the failing test**

```python
# test/test_combat_card_db.py
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.combat_card_db import CombatCardDb


def test_ids_are_contiguous_over_allpiles_order():
    c = CombatState(rng=random.Random(0))
    db = CombatCardDb()
    db.start(c)
    every = (c.player.hand + c.player.draw_pile
             + c.player.discard_pile + c.player.exhaust_pile)
    ids = sorted(db.id_of(card) for card in every)
    assert ids == list(range(len(every)))          # 0..N-1, no gaps
    # round-trips
    for card in every:
        assert db.get(db.id_of(card)) is card


def test_new_card_gets_next_id_on_refresh():
    from sts2_rl.cards.pool import make_card
    c = CombatState(rng=random.Random(0))
    db = CombatCardDb()
    db.start(c)
    n = len(c.player.all_cards)
    extra = make_card("slimed")
    c.player.discard_pile.append(extra)
    db.refresh(c)
    assert db.id_of(extra) == n                     # next id after the start set
```

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest test/test_combat_card_db.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sts2_rl.combat_card_db'`.

- [ ] **Step 3: Implement**

```python
# sts2_rl/combat_card_db.py
"""Port of NetCombatCardDb (src/Core/GameActions/Multiplayer/NetCombatCardDb.cs).

Assigns each combat card a contiguous per-combat uint id by identity, walking
piles in the game's fixed AllPiles order (Hand, DrawPile, DiscardPile,
ExhaustPile, PlayPile) at StartCombat, then id'ing newly-added cards in add
order. Consumes no RNG; it is the oracle the harness drives PlayCard by.
"""
from __future__ import annotations


class CombatCardDb:
    def __init__(self) -> None:
        self._next = 0
        self._id_to_card: dict[int, object] = {}
        self._card_to_id: dict[int, int] = {}   # keyed by id(card)

    def ordered_piles(self, combat) -> list[list]:
        p = combat.player
        # AllPiles order; the sim has no separate PlayPile (see Task 8).
        return [p.hand, p.draw_pile, p.discard_pile, p.exhaust_pile]

    def _id_if_necessary(self, card) -> None:
        if id(card) not in self._card_to_id:
            self._card_to_id[id(card)] = self._next
            self._id_to_card[self._next] = card
            self._next += 1

    def start(self, combat) -> None:
        self._next = 0
        self._id_to_card.clear()
        self._card_to_id.clear()
        self.refresh(combat)

    def refresh(self, combat) -> None:
        for pile in self.ordered_piles(combat):
            for card in pile:
                self._id_if_necessary(card)

    def get(self, card_id: int):
        return self._id_to_card[card_id]

    def id_of(self, card) -> int:
        return self._card_to_id[id(card)]
```

- [ ] **Step 4: Run to verify pass**

Run: `py -m pytest test/test_combat_card_db.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Stage (do NOT commit)**

```bash
git add sts2_rl/combat_card_db.py test/test_combat_card_db.py
```

---

## Task 6: Monster moves roll at telegraph time on `MonsterAi`

**This changes existing timing-sensitive tests — update them to the game-correct behavior.** In the game a random monster move is chosen when the intent is telegraphed (combat start + each enemy turn-start), from `MonsterAi`; the sim rolls at resolution time on `combat._rng`. This task moves both the *timing* and the *stream*.

Do it in two provable moves: first the state-machine monsters (`RandomBranchState`), then the hand-rolled `_move_key` monsters. Scope: the monsters the 15 recordings exercise (Act 1 Overgrowth roster first — Fuzzy Wurm, slimes, Shrinker Beetle, etc.).

**Files:**
- Modify: `sts2_rl/monsters/state_machine.py:152` (`roll = rng.random() * total` → weighted draw on `MonsterAi`) and the telegraph/selection call site
- Modify: hand-rolled monsters that roll a move (`monsters/overgrowth/slimes.py`, `flyconid.py`, `inklets.py`, `slithering_strangler.py`, etc.) — move the roll to telegraph time
- Modify: `sts2_rl/combat.py` — ensure enemy turn-start telegraphs before resolution (grep the enemy-turn loop, ~lines 193-230)
- Modify: existing tests that assert resolution-time move timing (surfaced by the suite)
- Test: `test/test_conformance_combat.py` (new; asserts intents match a recording — added in Task 7/8, referenced here as the parity check)

**Interfaces:**
- Consumes: `CombatState.combat_rng.monster_ai`.
- Produces: monster move selection reads `combat.combat_rng.monster_ai` at telegraph time; `MonsterAi` counter advances once per random move telegraph.

- [ ] **Step 1: Read the game's move machine** — `src/Core/MonsterMoves/MonsterMoveStateMachine.cs` and `RandomBranchState` (weight rolls) + how `MonsterAi` Rng is passed. Confirm: one `WeightedNextItem`/`NextFloat` per random branch, evaluated at telegraph. Write down the exact primitive and count.

- [ ] **Step 2: Write the failing parity test** — pick the first recording's opening fight (Fuzzy Wurm Crawler, `89U21BV1TZ/floor_18`). Its enemy has a deterministic loop, so first assert the *stream wiring* on a monster that DOES roll (a slime `TACKLE`/`GOOP` pick). Construct a parity combat with that encounter and assert `combat_rng.monster_ai.rng.counter` advanced by exactly 1 after the first telegraph, and the chosen move matches the recording's first Enemies-intent annotation.

```python
# in test/test_conformance_combat.py
def test_monster_move_rolls_once_on_monster_ai_at_telegraph():
    # Build a parity combat whose enemy uses a random branch; after
    # constructing (combat-start telegraph) exactly one MonsterAi draw happened.
    from sts2_rl.combat import CombatState
    from sts2_rl.rng import RunRngSet
    from sts2_rl.monsters.overgrowth.slimes import <ENCOUNTER_WITH_A_RANDOM_SLIME>
    rs = RunRngSet("seed")
    before = rs.monster_ai.counter
    CombatState(rng_set=rs, encounter=<ENCOUNTER>)
    assert rs.monster_ai.counter == before + 1
```

Fill `<ENCOUNTER>` from `monsters/overgrowth/ENCOUNTERS` (a slime encounter). If the enemy telegraphs its first move at construction (combat-start), the draw is at `+1`; if the roster's first move is fixed, move the assertion to after `end_turn()`.

- [ ] **Step 3: Run to verify failure**

Run: `py -m pytest test/test_conformance_combat.py -k monster_ai -q`
Expected: FAIL — counter unchanged (still rolling on `_rng` at resolution).

- [ ] **Step 4: Refactor `state_machine.py`** — route the branch roll to `combat.combat_rng.monster_ai` using the primitive from Step 1 (`weighted_next_item` for weighted branches, `next_item`/`next_int` for uniform). Ensure the roll happens when the intent is set (telegraph), storing the chosen next state so resolution just executes it. The machine already reads `rng`; thread the `CombatRng` accessor through instead of the raw `rng`.

- [ ] **Step 5: Refactor the hand-rolled rollers** — for each in scope, replace `self._rng.choice(...)` / `.choices(...)` at resolution with a telegraph-time pick on `combat.combat_rng.monster_ai`. Store the picked `_move_key` when the intent is telegraphed.

- [ ] **Step 6: Run the parity test + fix the legacy tests it breaks**

Run: `py -m pytest test/ -q -k "monster or intent or overgrowth or hive or glory or state_machine"`
For each failure caused by the timing move: if the test asserted the *old* resolution-time behavior, update it to the game-correct telegraph-time behavior (a move now chosen at turn-start, not when it fires). Do NOT weaken a test that catches a real regression.

- [ ] **Step 7: Full suite**

Run: `py -m pytest test/ -q`
Expected: PASS (with updated legacy tests).

- [ ] **Step 8: Stage (do NOT commit)**

```bash
git add sts2_rl/monsters/ sts2_rl/combat.py test/
```

---

## Task 7: `ReplayCombatDriver` + first-fight green (Hand/Enemies)

Replace the runner's force-win stub with a driver that plays a recording's combat commands against a live `CombatState`, asserting each command's **pre-state** annotation. Drive `PlayCard` by `args[0]` (the `CombatCardDb` id → card → hand index), targets by `args[1]` (enemy id). Resolve the **enemy-id mapping** against the recordings here (single-enemy fights use target `1`; multi-enemy slimes use `1,2,3` in encounter order — lock the mapping and assert it).

**Files:**
- Create: `sts2_rl/conformance/combat_driver.py`
- Modify: `sts2_rl/conformance/runner.py` (`_ForceWinDriver._run_combat` → use `ReplayCombatDriver`; keep force-win as a fallback only for un-annotated/unported fights, flagged)
- Test: `test/test_conformance_combat.py` (append)

**Interfaces:**
- Consumes: `CombatState`, `CombatCardDb`, `recording.Command` (`.name`, `.args`, `.annotation`), `comparators.Divergence`.
- Produces: `ReplayCombatDriver(combat, cursor, card_db)` with `.play() -> list[Divergence]`; `assert_hand(annotation, combat)`, `assert_enemies(annotation, combat)`, `enemy_by_target_id(combat, tid) -> Monster`.

- [ ] **Step 1: Write the failing test — the first Fuzzy Wurm fight plays clean**

```python
# test/test_conformance_combat.py
from pathlib import Path
from sts2_rl.conformance.recording import parse_recording

REC = Path(r"C:\Users\Perry\Desktop\RunReplays\RunReplays\Resources")

def test_first_overgrowth_fight_hand_and_enemies_match():
    rec = parse_recording(REC / "89U21BV1TZ" / "floor_18" / "actions.sts2replay")
    # Drive just the first Monster room's combat through the parity-sim and
    # assert zero Hand/Enemies divergences. (Helper set up in Task 8's runner
    # integration; here call ReplayCombatDriver directly on a constructed combat
    # seeded from rec.seed with the recording's first encounter.)
    divergences = drive_first_fight(rec)   # test helper defined in the test file
    assert divergences == [], "\n".join(str(d) for d in divergences)
```

Write `drive_first_fight` in the test: build `RunState(string_seed=rec.seed)`, advance to the first Monster room (reuse `ReplayRunner`'s map walk, or construct the encounter directly for this unit), create the parity combat, `CombatCardDb().start(combat)`, then run `ReplayCombatDriver`.

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest test/test_conformance_combat.py -k first_overgrowth -q`
Expected: FAIL — `ModuleNotFoundError` / `NameError: ReplayCombatDriver`.

- [ ] **Step 3: Implement `ReplayCombatDriver`**

```python
# sts2_rl/conformance/combat_driver.py
"""Play a recording's combat commands against a live parity CombatState.

Drives by the recorded NetCombatCardDb id (PlayCard arg0), asserting each
command's pre-state annotation (hand card names, enemy names + hp/maxhp) before
applying it. Produces localized Divergences on mismatch.
"""
from __future__ import annotations

from .comparators import Divergence

# Combat commands this driver consumes (others end the loop / are surplus).
_COMBAT_CMDS = {"PlayCard", "EndTurn", "UsePotion"}


def _card_display_name(card) -> str:
    ...  # the recording spells cards as "Strike", "Defend+", "Bash+", "Slimed"
         # — upgrade suffix "+" when card.upgraded. Implement against Card.


class ReplayCombatDriver:
    def __init__(self, combat, cursor, card_db) -> None:
        self.combat = combat
        self.cursor = cursor          # _CommandCursor over the recording
        self.db = card_db
        self.divergences: list[Divergence] = []

    def enemy_by_target_id(self, tid: int):
        # Enemy ids are 1-based over the encounter's creature order (validated
        # against the recordings in this task). Player is the untargeted self.
        return self.combat.enemies[tid - 1]

    def _assert(self, cmd) -> None:
        ann = cmd.annotation
        if ann is None:
            return
        if ann.hand is not None:
            live = [_card_display_name(c) for c in self.combat.player.hand]
            if live != ann.hand:
                self.divergences.append(Divergence(
                    "hand", cmd.lineno, ann.hand, live))
        if ann.enemies is not None:
            live = [(e.name, e.hp, e.max_hp)
                    for e in self.combat.enemies if not e.is_gone]
            exp = [(e.name, e.hp, e.max_hp) for e in ann.enemies]
            if live != exp:
                self.divergences.append(Divergence(
                    "enemies", cmd.lineno, exp, live))

    def play(self) -> list[Divergence]:
        while not self.combat.is_over:
            cmd = self.cursor.take(*_COMBAT_CMDS, "MoveToMapCoord",
                                   "ClaimReward")
            if cmd is None or cmd.name not in _COMBAT_CMDS:
                break   # combat's commands are exhausted for this fight
            self._assert(cmd)
            if cmd.name == "EndTurn":
                self.combat.end_turn()
            elif cmd.name == "PlayCard":
                card = self.db.get(int(cmd.args[0]))
                hand_idx = self.combat.player.hand.index(card)
                target = (self.enemy_by_target_id(int(cmd.args[1]))
                          if len(cmd.args) > 1 else None)
                self.combat.play_card(hand_idx, target=target)
            elif cmd.name == "UsePotion":
                ...  # slot arg0, optional target arg1
            self.db.refresh(self.combat)
        return self.divergences
```

Fill `_card_display_name`, the `UsePotion` branch, and confirm `CombatState.play_card`'s real signature (`grep -n "def play_card" sts2_rl/combat.py` — it may be `play_card(i, target_idx=...)`; adapt). The cursor's `take` must not consume the room-advancing `MoveToMapCoord`/`ClaimReward` — peek/rewind so the outer runner still sees them (add a `peek`/`rewind` to `_CommandCursor` if needed).

- [ ] **Step 4: Resolve + assert the enemy-id mapping**

Add a focused test that a multi-enemy fight (the slimes fight in `89U21BV1TZ/floor_18`, targets `1,2,3`) maps `enemy_by_target_id(1/2/3)` to the enemies named in the annotation (`Twig Slime (S)`, `Twig Slime (M)`, `Leaf Slime (S)`). If the order is off, fix `enemy_by_target_id` (and document the true creature-id rule from the game).

- [ ] **Step 5: Run the first-fight test**

Run: `py -m pytest test/test_conformance_combat.py -k "first_overgrowth or target_id" -q`
Expected: PASS — the first fight's hands and enemy HP reproduce (given Task 4 Shuffle + Task 6 MonsterAi are in). If a Hand mismatch appears, it localizes the first un-ported draw — fix it (Task 9's loop) before moving on.

- [ ] **Step 6: Stage (do NOT commit)**

```bash
git add sts2_rl/conformance/combat_driver.py sts2_rl/conformance/runner.py test/test_conformance_combat.py
```

---

## Task 8: Wire the driver into the runner + combat-counter diffs

Swap `ReplayRunner`'s force-win `_run_combat` for `ReplayCombatDriver`, id the combat's cards with `CombatCardDb`, collect combat divergences into the run's report, and extend `compare_counters` to diff the 7 combat streams at floor boundaries. Also resolve the `PlayPile`/resolving-card id case here (Task 5's TODO): if a `PlayCard {id}` lookup misses because the card is mid-resolution, adjust `CombatCardDb.ordered_piles` / refresh timing until every recorded id resolves.

**Files:**
- Modify: `sts2_rl/conformance/runner.py` (`_run_combat`; hold a `CombatCardDb` per combat; feed the cursor)
- Modify: `sts2_rl/conformance/comparators.py` (`SP3_COMBAT_STREAMS`; extend `compare_counters` callers)
- Test: `test/test_conformance_combat.py` (append), `test/test_conformance_runner.py` (extend)

**Interfaces:**
- Consumes: `ReplayCombatDriver`, `CombatCardDb`.
- Produces: `comparators.SP3_COMBAT_STREAMS: tuple[RunRngType, ...]`; runner reports combat `Divergence`s + combat-counter diffs.

- [ ] **Step 1: Write the failing test — combat streams compared, ids resolve**

```python
# append to test/test_conformance_combat.py
def test_first_overgrowth_floor_combat_counters_and_ids():
    rec = parse_recording(REC / "89U21BV1TZ" / "floor_18" / "actions.sts2replay")
    result = run_through_floor(rec)          # runner integration helper
    assert result.combat_divergences == []
    # every PlayCard id in the recording resolved to a card
    assert result.unresolved_play_card_ids == []
```

- [ ] **Step 2: Run to verify failure**

Run: `py -m pytest test/test_conformance_combat.py -k combat_counters -q`
Expected: FAIL.

- [ ] **Step 3: Implement runner integration** — in `runner.py`, replace `_ForceWinDriver._run_combat` body with: `combat = run.create_combat(...)`; `db = CombatCardDb(); db.start(combat)`; `ReplayCombatDriver(combat, self._cursor, db).play()`; collect divergences; then resolve rewards along the recording as today. Keep the force-win fallback for a fight with no combat annotations, flagged in `stopped_reason`.

- [ ] **Step 4: Extend `comparators.py`**

```python
SP3_COMBAT_STREAMS: tuple[RunRngType, ...] = (
    RunRngType.SHUFFLE,
    RunRngType.MONSTER_AI,
    RunRngType.COMBAT_CARD_GENERATION,
    RunRngType.COMBAT_CARD_SELECTION,
    RunRngType.COMBAT_TARGETS,
    RunRngType.COMBAT_ENERGY_COSTS,
    RunRngType.COMBAT_POTION_GENERATION,
)
```

The runner passes `run_streams=SP2_RUN_STREAMS + SP3_COMBAT_STREAMS` to `compare_counters` (or a second call with `SP3_COMBAT_STREAMS`). Keep the two sets separate so a report says which subsystem diverged.

- [ ] **Step 5: Resolve the resolving-card id case** — run the first fight; if any `PlayCard {id}` misses, inspect where the played card lives during resolution and adjust `CombatCardDb` (e.g. refresh before the hand-index lookup, or include an in-resolution slot mirroring `PlayPile`). Re-run until `unresolved_play_card_ids == []`.

- [ ] **Step 6: Run the test**

Run: `py -m pytest test/test_conformance_combat.py -k combat_counters -q`
Expected: PASS for `89U21BV1TZ/floor_18`'s Act-1 fights (later floors converge in Task 9).

- [ ] **Step 7: Stage (do NOT commit)**

```bash
git add sts2_rl/conformance/ test/test_conformance_combat.py test/test_conformance_runner.py
```

---

## Task 9: Convergence — drive all 15 recordings to green (per-stream / per-content loop)

The long pole. With the seam, MonsterAi, CombatCardDb, and the driver in place, iterate the harness over all 15 recordings; each divergence localizes one un-ported combat draw. Fix it, re-run, repeat. This is a **repeatable procedure**, not a fixed code list — the recordings dictate which of the ~40 call sites need routing and in what order.

**The loop (repeat until green):**

1. Run the parametrized harness test (Step A below). Read the first `Divergence`: its `stream` + `command_index` name the subsystem and the exact command.
2. Map the divergence to a call site:
   - `hand` mismatch after a generated card → `CombatCardGeneration` site (`cards/pool.py:93/95/141/143`, colorless card effects `cards/colorless_*.py`, `cmds.py:369`) drawing on the wrong stream or wrong primitive (`sample`/`choices` batched vs game one-at-a-time).
   - `enemies` mismatch on a random target → `CombatTargets` site (`combat.py:430`, `cards/*.py` `.choice(living)`, `thrash.py`, `sword_boomerang.py`, `true_grit.py`, `cinder.py`).
   - intent/HP mismatch from a monster move → remaining `MonsterAi` site (a hand-rolled monster not covered in Task 6).
   - a `select_cards` outcome → `CombatCardSelection`.
   - a random energy cost → `CombatEnergyCosts`; an in-combat potion → `CombatPotionGeneration`.
   - a counter-only mismatch (state matches, counter off) → a draw with the wrong *count* (batched `sample`, an extra/missing draw) — re-port to the game's exact draw sequence from the C# source for that content.
3. Open the game source for that content (paths in CLAUDE.md's fidelity table), confirm the stream + primitive + draw order + count, and rewrite the sim site: `combat.combat_rng.<accessor>` with `.shuffle/.choice/.choices/.randint/.next_item/.weighted_next_item`, or a per-site draw loop where `sample` has no generic analogue.
4. Re-run; the next divergence surfaces. Commit-stage after each fixed site (small diffs, one subsystem each).

- [ ] **Step A: Write the parametrized golden test over all 15 recordings**

```python
# append to test/test_conformance_combat.py
import pytest

SEEDS = ["89U21BV1TZ", "DJDCSAQZNR", "L081UMJX4M", "QRWCVDPZN5", "TZEKRYTSNT"]
FLOORS = ["floor_49"]   # the full-run log; add floor_18/34 as sub-run checks

@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("floor", FLOORS)
def test_recording_combat_parity(seed, floor):
    rec = parse_recording(REC / seed / floor / "actions.sts2replay")
    oracle = parse_save(REC / seed / floor / "run.save")
    result = ReplayRunner(rec, oracle).run(stop_after_act=2)  # all three acts
    combat_divs = [d for d in result.divergences
                   if d.stream in {"hand", "enemies"} or "combat" in d.stream
                   or d.stream in {"shuffle", "monster_ai"}]
    assert combat_divs == [], "\n".join(str(d) for d in combat_divs[:20])
```

(Keep SP2's map/economy asserts intact — this test adds the combat streams on top.)

- [ ] **Step B: Run and read the first divergence**

Run: `py -m pytest test/test_conformance_combat.py -k recording_combat_parity -q`
Expected: FAIL initially, with a localized `[stream] room/line N: expected … got …`.

- [ ] **Step C: Fix one site (per the loop above), re-run, repeat.** Each iteration: edit one call site, run the single failing `-k "<seed>"` case, then the parametrized test. Stage after each: `git add <edited files> test/test_conformance_combat.py`.

- [ ] **Step D: Green gate** — all 15 (5 seeds × floor_49, plus floor_18/34 sub-runs) pass with zero combat divergences and matching 7 combat-stream counters.

Run: `py -m pytest test/test_conformance_combat.py -q`
Expected: PASS (all parametrized cases).

---

## Task 10: Acceptance — full suite + all-recordings green

- [ ] **Step 1: Full suite**

Run: `py -m pytest test/ -q`
Expected: PASS — baseline 2235 (with Task-6 legacy-test updates) + all new SP3 tests. Zero failures.

- [ ] **Step 2: Confirm acceptance criteria (spec §Acceptance)**
  - Legacy `random.Random` combat path unchanged (suite green). ✓ from Step 1.
  - Monster moves roll at telegraph time on `MonsterAi`; updated legacy tests pass. ✓
  - `CombatCardDb` ids match every `PlayCard {id}` in the 15 recordings, consistent with the `# CARD.X` comment (Task 8 `unresolved_play_card_ids == []` + a name cross-check assert).
  - Runner plays every `Resources/*` recording with zero `Hand/Enemies` mismatches and matching 7 combat-stream counters at every floor boundary across all three acts (Task 9 green).

- [ ] **Step 3: Update docs**
  - `MODULES.md`: add `combat_rng.py` and `combat_card_db.py` one-liners; note the combat streams are now parity-wired.
  - CLAUDE.md "Known gaps": strike the "Single RNG stream; the game rolls monster moves at intent-display time" line and the "one shared random.Random … no seed parity" combat caveat (now resolved for the parity path); note the legacy path still collapses to one stream by design.
  - Memory: update `[[sp2-phase2-progress]]` / add an SP3 memory (combat parity shipped, streams wired, CombatCardDb ported).

- [ ] **Step 4: Stage everything (do NOT commit)**

```bash
git add -A
git status
```

Report the staged diff to Perry for review and commit.

---

## Self-review notes (author)

- **Spec coverage:** U1→seam (Tasks 1,3), adapter (Task 2), Shuffle (Task 4), MonsterAi+intent-time (Task 6), CombatCardGeneration/Selection/Targets/EnergyCosts/PotionGeneration (Task 9), NetCombatCardDb (Tasks 5,8), harness combat-driver + counters (Tasks 7,8), all-15 green (Tasks 9,10). CombatOrbs explicitly out of scope (spec Non-goals) — not wired. Every spec work unit maps to ≥1 task.
- **Iterative honesty:** Task 9 is a specified procedure, not fixed code, because the exact per-content fixes are discovered from harness divergences — the method (localize → read source → route to stream/primitive → re-run) is fully spelled out with the call-site map. This is the responsible shape for parity convergence.
- **Type consistency:** `CombatRng` accessor names (`shuffle/monster_ai/card_gen/card_selection/targets/energy/potion_gen`) are used identically in Tasks 1,3,4,6,9. `CombatCardDb.{start,refresh,get,id_of,ordered_piles}` consistent across Tasks 5,7,8. `Divergence(stream, command_index, expected, actual, detail)` matches the existing SP2 dataclass.
- **Commits:** every task stages only (`git add`), never commits — honoring CLAUDE.md rule 4.
