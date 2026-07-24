# SP3 Efficient Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-divergence-per-cycle convergence grind with tooling that
surfaces *every* divergence in one triage run (per-floor state oracle + resync),
kills whole bug *classes* up front (static sweeps), and makes new ground-truth
fixtures cheap — then drive both Ironclad seeds (89U21BV1TZ, 933T39V18D) to green.

**Architecture:** Three layers. (1) **Oracle upgrades** — the conformance runner
gains a per-floor full-state checkpoint (HP, max-HP, gold, deck, relics, potions,
all 15 RNG counters) read from the per-floor `run.save` files, with optional
resync so a divergence at floor N cannot cascade into floor N+1 — divergences
become independent and are all visible in a single run. (2) **Class sweeps** —
the wrong-stream tripwire becomes a permanent fuzz gate over random sim runs; an
enemy-display-name audit harvests ground truth from *all six* seeds' recordings
(names are character-independent); a monster branch-table audit diffs sim move
logic against the C# `AddBranch` declarations to catch the weight-vs-cooldown
class before any seed hits it. (3) **The grind, compressed** — with cascade
suppression, each triage cycle yields N localized bugs instead of 1, and they can
be fixed in any order (or in parallel).

**Tech Stack:** Python 3 (`py` launcher), pytest, the existing
`sts2_rl.conformance` package (recording.py / save.py / runner.py /
combat_driver.py / comparators.py), `sts2_rl.rng` (RunRngSet / PlayerRngSet,
both already have `load_counters`), PowerShell/Bash for fixture plumbing.

## Global Constraints

- **Never `git commit` / `git push`** (`[[sts2-no-auto-commit]]`, CLAUDE.md rule 4). Every "commit" step below means `git add <paths>` and stop; Perry reviews and commits in batches. RunReplays is a **separate repo** — stage its fixtures separately.
- **Ground truth = the decompiled game** at `c:\Users\Perry\Desktop\Slay the Spire 2\src` (`[[original-means-game-source]]`). A fix that changes sim behavior updates legacy tests to the game-correct value; never weaken a real regression guard.
- Full suite must stay green: `py -m pytest test/ -q` — last measured baseline **2305 passed, 6 xfailed** (re-measure before starting; record the number).
- Style: `from __future__ import annotations` + lazy in-method imports (powers ↔ cmds ↔ cards circulars).
- Only Ironclad seeds can converge (`[[sp3-seeds-are-5-characters]]`): 89U21BV1TZ and 933T39V18D. The other four (DJDC/L081/QRWC/TZEK) stay xfailed as un-ported characters — but their recordings ARE usable as name/annotation ground truth (Task 6).
- Fixture roots: recordings at `C:\Users\Perry\Desktop\RunReplays\RunReplays\Resources\<seed>\floor_N\`; 933T's complete 49-floor per-floor saves at `C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording\floor_N\` (do NOT copy all 49 into Resources — read them in place, Task 4).

## Why this is faster than the current loop (read once, then execute)

| Current cost | Cause | Task that removes it |
|---|---|---|
| Every triage re-run 2–3× before trusting a delta | out-of-combat draws ride the *unseeded* shared rng (`[[conformance-replay-determinism]]`) | Task 1 (seed it deterministically in the runner) |
| One bug per triage cycle; "fix the EARLIEST room first" | a whole-run replay cascades: floor N's divergence poisons floors N+1..49 | Tasks 2–4 (per-floor oracle + resync = cascade suppression → all divergent floors visible at once, each independently fixable) |
| HP drift only observable at 3 act boundaries | DETECTOR 3 uses only floor_18/34/49 saves | Tasks 2–4 (49 checkpoints for 933T, incl. deck/relics/gold — a divergence is localized to ONE floor + ONE subsystem by the tool, no bisecting) |
| Wrong-stream bugs found only when a seed happens to draw there | DETECTOR 1 only runs inside a recording replay | Task 5 (fuzz gate: random sim runs exercise ALL ported content) |
| Name mismatches found one force-win at a time | names checked only when a replayed combat reaches that enemy | Task 6 (harvest every name from all 6 seeds' annotations, fix in one sweep) |
| Weight-vs-cooldown misreads found one fight at a time | `[[monster-move-weight-vs-cooldown-bug]]` class, ~18 hand-rolled monsters unaudited | Task 7 (static branch-table audit vs C# source) |
| A new seed costs Perry a full manual victory run | fixtures assumed to need floor_49 + victory | Task 9 (partial runs are valid fixtures — every floor save is a checkpoint; coverage report tells Perry exactly what content the next short recording should target) |

Sequencing: Tasks 1–4 are the multiplier — build them first. Tasks 5–7 are
independent of each other and of the grind (parallelizable). Task 8 is the grind
itself, now cheap. Task 9 sets up the next fidelity increment. Task 10 is a
deferred decision for Perry.

---

### Task 1: Determinize the conformance replay (kill the re-run tax)

**Files:**
- Modify: `sts2_rl/conformance/runner.py` (in `ReplayRunner.run`, right after `RunState` construction, ~line 539)
- Test: `test/test_conformance_determinism.py` (new)

**Interfaces:**
- Consumes: `RunState.rng` (the legacy shared `random.Random`, created in `RunState.__init__`).
- Produces: bit-identical `ReplayResult`s for repeated runs of the same recording — every later task's triage numbers become trustworthy on the first run.

The shared rng is *not* on any parity stream (that's SP4 debt); seeding it doesn't
create parity, it creates **reproducibility**: identical triage output run-to-run,
so a delta after a fix is attributable to the fix.

- [ ] **Step 1: Write the failing test**

```python
"""Two identical ReplayRunner passes must produce identical results — the
conformance shared rng is seeded (runner.py), so triage deltas are real."""
from __future__ import annotations

from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"


@pytest.mark.skipif(not REC.exists(), reason="RunReplays fixtures not present")
def test_replay_runner_is_deterministic():
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / "89U21BV1TZ" / "floor_18"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    r1 = ReplayRunner(rec, oracle).run(stop_after_act=0)
    r2 = ReplayRunner(rec, oracle).run(stop_after_act=0)
    assert [repr(d) for d in r1.divergences] == [repr(d) for d in r2.divergences]
    assert [repr(d) for d in r1.combat_divergences] == [repr(d) for d in r2.combat_divergences]
    assert r1.run_counters == r2.run_counters
    assert r1.forced_combats == r2.forced_combats
```

Note the path: `test/` → parents[2] is `Desktop/`; adjust if the repo layout
differs (`converge_triage.py` derives the same root as `_REPO.parent`).

- [ ] **Step 2: Run it to verify it fails (or flakes)**

Run: `py -m pytest test/test_conformance_determinism.py -q` **three times.**
Expected: at least one FAIL across the three runs (the unseeded rng makes it
flaky — if all three pass, the divergence lists happened to match; the seeding
change is still correct and the test locks it in).

- [ ] **Step 3: Seed the shared rng in `ReplayRunner.run`**

In `sts2_rl/conformance/runner.py`, immediately after
`run = RunState(string_seed=rec.seed)`:

```python
        # Determinism, not parity: the legacy shared rng (SP4 debt) is seeded
        # so repeated triage runs are bit-identical and a post-fix delta is
        # attributable to the fix ([[conformance-replay-determinism]] is now
        # obsolete for conformance runs). Any in-combat draw from it is still
        # a wrong-stream bug (DETECTOR 1 / Task 5's tripwire gate).
        run.rng.seed(f"conformance:{rec.seed}")
```

- [ ] **Step 4: Run the test 3× to verify it passes every time**

Run: `py -m pytest test/test_conformance_determinism.py -q` (×3). Expected: PASS ×3.

- [ ] **Step 5: Re-baseline the conformance gate + full suite**

Run: `py -m pytest test/test_conformance_player_state.py -q` then `py -m pytest test/ -q`.
Expected: same pass/xfail counts as the pre-task baseline (the seeding may shift
which *specific* noisy values appear inside still-xfailed cases — that's fine;
any newly FAILING test must be investigated before proceeding).

- [ ] **Step 6: Stage**

```bash
git add sts2_rl/conformance/runner.py test/test_conformance_determinism.py
```

---

### Task 2: Full player-state oracle from `run.save`

**Files:**
- Modify: `sts2_rl/conformance/save.py`
- Test: `test/test_conformance_save.py` (extend if it exists — check with `ls test/ | grep save`; else create)

**Interfaces:**
- Consumes: the run.save JSON schema (verified 2026-07-23 against `933T39V18D-recording/floor_20/run.save`): `players[0].gold: int`, `players[0].deck: [{id: "CARD.X", current_upgrade_level?: int, ...}]`, `players[0].relics: [{id: "RELIC.X", ...}]`, `players[0].potions: [{id: "POTION.X", slot_index: int}]`.
- Produces: `SaveOracle.gold: int`, `SaveOracle.deck: list[tuple[str, int]]` (game card id, upgrade level, **in save order**), `SaveOracle.relic_ids: list[str]` (game relic ids, in save order), `SaveOracle.potion_slots: dict[int, str]` (slot → game potion id). Task 3 consumes all four.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"


@pytest.mark.skipif(not REC.exists(), reason="RunReplays fixtures not present")
def test_save_oracle_carries_full_player_state():
    from sts2_rl.conformance.save import parse_save

    o = parse_save(REC / "89U21BV1TZ" / "floor_18" / "run.save")
    assert o.gold > 0
    assert len(o.deck) >= 10                      # starter deck + act-1 picks
    assert all(cid.startswith("CARD.") for cid, _ in o.deck)
    assert all(isinstance(up, int) for _, up in o.deck)
    assert o.relic_ids and o.relic_ids[0] == "RELIC.BURNING_BLOOD"
    assert all(isinstance(s, int) and pid.startswith("POTION.")
               for s, pid in o.potion_slots.items())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `py -m pytest test/test_conformance_save.py -q -k full_player_state`
Expected: FAIL — `AttributeError: 'SaveOracle' object has no attribute 'gold'`
(or TypeError on the dataclass).

- [ ] **Step 3: Extend `SaveOracle` + `parse_save`**

In `sts2_rl/conformance/save.py`, add to the dataclass (after `player_max_hp`):

```python
    gold: int = 0
    # (game card id, upgrade level) in save order — order matters for parity
    # (out-of-combat transforms APPEND, CardCmd.cs:437).
    deck: list[tuple[str, int]] = field(default_factory=list)
    relic_ids: list[str] = field(default_factory=list)   # game ids, save order
    potion_slots: dict[int, str] = field(default_factory=dict)
```

and in `parse_save`'s return call (after `player_max_hp=...`):

```python
        gold=player.get("gold", 0),
        deck=[(c["id"], c.get("current_upgrade_level", 0))
              for c in player.get("deck", [])],
        relic_ids=[r["id"] for r in player.get("relics", [])],
        potion_slots={p.get("slot_index", i): p["id"]
                      for i, p in enumerate(player.get("potions", []))},
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py -m pytest test/test_conformance_save.py -q -k full_player_state` → PASS.

- [ ] **Step 5: Run the full conformance file + stage**

Run: `py -m pytest test/test_conformance_save.py test/test_conformance_player_state.py -q` — no regressions.

```bash
git add sts2_rl/conformance/save.py test/test_conformance_save.py
```

---

### Task 3: Per-floor checkpoints + resync in the runner (the multiplier)

**Files:**
- Create: `sts2_rl/conformance/idmap.py` (save-id → sim-id mapping)
- Modify: `sts2_rl/conformance/runner.py` (`ReplayRunner.run` + a new `_check_floor_state` method)
- Test: `test/test_conformance_floor_state.py` (new)

**Interfaces:**
- Consumes: `SaveOracle.gold/deck/relic_ids/potion_slots` (Task 2); `RunRngSet.load_counters` / `PlayerRngSet.load_counters` (`sts2_rl/rng.py:368/414` — both re-init + `fast_forward_counter`, handling over- AND under-draws); `run.total_floor` (bumped per `enter_point`; the runner seeds it to 1 for the Neow node and +1 per act entry); the existing relic reconcile machinery (`_reconcile_node_relics` pattern: `run.relics.remove` + `relic.undo_after_obtained(run)` / `run.add_relic`).
- Produces:
  - `ReplayRunner.run(..., floor_saves: dict[int, SaveOracle] | None = None, resync_floors: bool = False)`.
  - New `Divergence` streams, all with `command_index = floor`: `floor_hp`, `floor_max_hp`, `floor_gold`, `floor_deck`, `floor_relics`, `floor_potions`, `floor_counter_<StreamName>` — appended to `ReplayResult.divergences`.
  - `idmap.sim_card_id(save_id) -> str | None`, `idmap.sim_relic_id(save_id) -> str | None`, `idmap.sim_potion_id(save_id) -> str | None` (None = unported/unmapped; the caller reports, never crashes).
- Task 4 wires this into `converge_triage.py` as DETECTOR 4.

**Semantics — read before coding:**
- **Checkpoint point:** floor N's save is compared *after the room on floor N is
  fully resolved* (post-combat rewards taken, post-event, post-reconcile). This
  matches how floor_18/34/49 already serve as act-boundary checkpoints (post-boss
  HP). Step 3 verifies the offset empirically before anything depends on it.
- **Resync scope (when `resync_floors=True`):** hp, max_hp, gold, deck
  (rebuild), potion slots (rebuild), rng counters (`load_counters` with the
  save's counters), relics (reconcile against `oracle.relic_ids`). Resync happens
  *after* recording the divergences, so the report shows what was wrong AND the
  next floor starts clean. Unmapped save cards/relics/potions are recorded as
  part of the divergence detail and skipped in the rebuild (better a missing card
  than a crash — conformance reports, it does not raise).
- **Deck compare is ordered** (save order vs `run.deck` order) because pile
  order feeds Shuffle parity; report the first mismatching index plus the two
  full lists in the divergence detail.

- [ ] **Step 1: Build the id maps (`sts2_rl/conformance/idmap.py`)**

First check the card registry's exported name:

Run: `py -c "import sts2_rl.cards as c; print([n for n in dir(c) if n.isupper()][:10])"`
Expected: a registry dict name (by convention with `ALL_RELICS` / `ALL_POWERS` it
is `ALL_CARDS`; if it's something else, substitute it below). Same check for
`sts2_rl.potions`.

```python
"""Map RunReplays save ids (CARD.X / RELIC.X / POTION.X) to sim registry ids.

Default rule: strip the prefix, lowercase. Exceptions are collected empirically
(Task 3 Step 2 dumps unmapped ids) — keep this table SMALL and evidence-based;
a missing mapping is reported as part of a floor divergence, never a crash."""
from __future__ import annotations

_CARD_EXCEPTIONS = {
    "strike_ironclad": "strike",
    "defend_ironclad": "defend",
}
_RELIC_EXCEPTIONS: dict[str, str] = {}
_POTION_EXCEPTIONS: dict[str, str] = {}


def _key(save_id: str) -> str:
    return save_id.split(".", 1)[-1].lower()


def sim_card_id(save_id: str) -> str | None:
    from ..cards import ALL_CARDS
    k = _CARD_EXCEPTIONS.get(_key(save_id), _key(save_id))
    return k if k in ALL_CARDS else None


def sim_relic_id(save_id: str) -> str | None:
    from ..relics import ALL_RELICS
    k = _RELIC_EXCEPTIONS.get(_key(save_id), _key(save_id))
    return k if k in ALL_RELICS else None


def sim_potion_id(save_id: str) -> str | None:
    from ..potions import ALL_POTIONS
    k = _POTION_EXCEPTIONS.get(_key(save_id), _key(save_id))
    return k if k in ALL_POTIONS else None
```

- [ ] **Step 2: Empirically fill the exception tables**

```python
# scratch (run with: py -c "..." or a throwaway script)
from pathlib import Path
from sts2_rl.conformance.save import parse_save
from sts2_rl.conformance import idmap
root = Path(r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording")
unmapped = set()
for save in sorted(root.glob("floor_*/run.save")):
    o = parse_save(save)
    unmapped |= {c for c, _ in o.deck if idmap.sim_card_id(c) is None}
    unmapped |= {r for r in o.relic_ids if idmap.sim_relic_id(r) is None}
    unmapped |= {p for p in o.potion_slots.values() if idmap.sim_potion_id(p) is None}
print(sorted(unmapped))
```

Also run against `Resources/89U21BV1TZ/floor_*/run.save`. For each unmapped id:
if the content is ported under a different sim id, add an exception entry; if
genuinely unported, leave it (it will be report-only). Expected end state: the
printed list contains ONLY genuinely-unported content (record that list in the
task notes).

- [ ] **Step 3: Calibrate the floor↔save offset**

Pick a floor in 933T where the recording shows a `TakeCard N` (a card entered
the deck). Verify which save first contains it:

```python
from pathlib import Path
from sts2_rl.conformance.save import parse_save
root = Path(r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording")
prev = None
for n in range(1, 50):
    o = parse_save(root / f"floor_{n}" / "run.save")
    ids = [c for c, _ in o.deck]
    if prev is not None and ids != prev:
        print(f"deck changed at floor_{n}: +{[c for c in ids if c not in prev] }")
    prev = ids
```

Cross-check 2–3 change floors against the recording's command log (the `TakeCard`
comment names the card). Expected: `floor_N`'s save reflects state AFTER floor
N's room resolved (matching how floor_18 = post-act-1-boss). **If the offset is
actually N−1, adjust the lookup in Step 5 to `floor_saves.get(run.total_floor)`
vs `... + 1` accordingly and note it here.**

- [ ] **Step 4: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
BK = Path(r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording")


def _floor_saves():
    from sts2_rl.conformance.save import parse_save
    return {int(p.name.split("_")[1]): parse_save(p / "run.save")
            for p in BK.glob("floor_*") if (p / "run.save").exists()}


@pytest.mark.skipif(not (REC.exists() and BK.exists()), reason="fixtures absent")
def test_floor_checkpoints_and_resync_run_to_completion():
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    saves = _floor_saves()
    assert len(saves) == 49
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=saves, resync_floors=True)
    floor_divs = [d for d in result.divergences if d.stream.startswith("floor_")]
    # Not asserting zero (the seed hasn't converged); asserting the MECHANISM:
    # checkpoints fired across the whole run and resync kept the replay alive
    # to the recorded end instead of dying to cascade damage.
    assert result.stopped_reason.startswith("reached act 2")
    checked_floors = {d.command_index for d in floor_divs}
    assert all(1 <= f <= 49 for f in checked_floors)
```

- [ ] **Step 5: Run it to verify it fails**

Run: `py -m pytest test/test_conformance_floor_state.py -q`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'floor_saves'`.

- [ ] **Step 6: Implement `_check_floor_state` + wire it into the walk loop**

In `sts2_rl/conformance/runner.py`, add to `ReplayRunner`:

```python
    def _check_floor_state(self, run, divergences, floor_saves,
                           resync_floors) -> None:
        """Diff (and optionally resync) the FULL player state + all 15 stream
        counters against this floor's run.save. command_index = floor number.
        Report-only for anything unmapped — conformance reports, never raises."""
        from ..rng import PlayerRngType, RunRngType
        from . import idmap
        from .comparators import Divergence

        oracle = floor_saves.get(run.total_floor)
        if oracle is None:
            return
        floor = run.total_floor

        def diff(stream, expected, actual, note=""):
            if expected != actual:
                divergences.append(
                    Divergence(stream, floor, expected, actual, note))
                return True
            return False

        diff("floor_hp", oracle.player_current_hp, run.hp)
        diff("floor_max_hp", oracle.player_max_hp, run.max_hp)
        diff("floor_gold", oracle.gold, run.gold)

        exp_deck = [(idmap.sim_card_id(cid), up) for cid, up in oracle.deck]
        live_deck = [(c.id, c.upgrade_level) for c in run.deck]
        diff("floor_deck", exp_deck, live_deck,
             "ordered (save order == game deck order); None = unported id")

        exp_relics = [idmap.sim_relic_id(r) for r in oracle.relic_ids]
        diff("floor_relics", exp_relics, [r.id for r in run.relics])

        exp_potions = {s: idmap.sim_potion_id(p)
                       for s, p in oracle.potion_slots.items()}
        live_potions = {i: p.id for i, p in enumerate(run.potions)
                        if p is not None}
        diff("floor_potions", exp_potions, live_potions)

        live_rc = run.rng_set.counters()
        for t in RunRngType:
            diff(f"floor_counter_{t.value}", oracle.run_counters[t], live_rc[t])
        live_pc = run.player_rng.counters()
        for t in PlayerRngType:
            diff(f"floor_counter_{t.value}",
                 oracle.player_counters[t], live_pc[t])

        if not resync_floors:
            return
        run.hp = oracle.player_current_hp
        run.max_hp = oracle.player_max_hp
        run.gold = oracle.gold
        run.rng_set.load_counters(oracle.run_counters)
        run.player_rng.load_counters(oracle.player_counters)
        self._resync_deck(run, oracle)
        self._resync_relics(run, oracle)
        self._resync_potions(run, oracle)
```

and the three resync helpers:

```python
    def _resync_deck(self, run, oracle) -> None:
        """Rebuild run.deck to the save's ordered contents. Unmapped ids are
        skipped (reported by the floor_deck diff). Upgrades applied by level."""
        from . import idmap
        from ..cards import make_card

        new_deck = []
        for cid, up in oracle.deck:
            sim_id = idmap.sim_card_id(cid)
            if sim_id is None:
                continue
            card = make_card(sim_id)
            for _ in range(up):
                card.upgrade()
            new_deck.append(card)
        run.deck[:] = new_deck

    def _resync_relics(self, run, oracle) -> None:
        """Reconcile run.relics to the save's list, reusing the node-relic
        pattern (undo_after_obtained on drops so max-HP side effects unwind —
        harmless here because hp/max_hp are re-pinned right before this)."""
        from . import idmap

        want = [idmap.sim_relic_id(r) for r in oracle.relic_ids]
        want_set = {w for w in want if w is not None}
        for relic in list(run.relics):
            if relic.id not in want_set:
                run.relics.remove(relic)
                relic.undo_after_obtained(run)
        owned = {r.id for r in run.relics}
        for rid in want:
            if rid is not None and rid not in owned:
                run.add_relic(rid)
                owned.add(rid)
        run.hp = oracle.player_current_hp      # re-pin after relic hooks
        run.max_hp = oracle.player_max_hp

    def _resync_potions(self, run, oracle) -> None:
        from . import idmap
        from ..potions import make_potion

        slots = [None] * len(run.potions)
        for s, pid in oracle.potion_slots.items():
            sim_id = idmap.sim_potion_id(pid)
            if sim_id is not None and s < len(slots):
                slots[s] = make_potion(sim_id)
        run.potions[:] = slots
```

**Before coding, verify the actual attribute names** used above against
`sts2_rl/run.py` (`run.deck`, `run.potions` — list-of-slots vs list?, `run.gold`,
`make_potion`'s exported name, `card.upgrade()` vs `card.upgrade_level = n`).
Adjust the helpers to the real API — the shapes above are the contract, the
attribute names must come from run.py.

Wire the check into the walk loop in `run()` — signature first:

```python
    def run(self, stop_after_act: int = 0,
            player_checkpoints: "dict[int, tuple[int, int]] | None" = None,
            resync_player: bool = False,
            floor_saves: "dict[int, SaveOracle] | None" = None,
            resync_floors: bool = False) -> ReplayResult:
```

then, inside the `while not run.at_run_end:` loop, immediately after
`self._reconcile_node_relics(run, run.act_index, room_index, n_relics_before)`:

```python
            if floor_saves:
                self._check_floor_state(
                    run, divergences, floor_saves, resync_floors)
```

- [ ] **Step 7: Run the new test**

Run: `py -m pytest test/test_conformance_floor_state.py -q`
Expected: PASS. If `stopped_reason` isn't `reached act 2 boss`, debug the resync
(most likely: the floor offset from Step 3, or a run.py attribute-name mismatch).

- [ ] **Step 8: Verify no regression in the old modes + full suite**

Run: `py -m pytest test/test_conformance_player_state.py test/test_conformance_determinism.py -q` then `py -m pytest test/ -q`.
Expected: baseline counts (no floor_saves passed = zero behavior change).

- [ ] **Step 9: Stage**

```bash
git add sts2_rl/conformance/idmap.py sts2_rl/conformance/runner.py test/test_conformance_floor_state.py
```

---

### Task 4: DETECTOR 4 in `converge_triage.py` (the new daily driver)

**Files:**
- Modify: `tools/converge_triage.py`

**Interfaces:**
- Consumes: `ReplayRunner.run(floor_saves=..., resync_floors=...)` (Task 3); the per-seed floor-save locations.
- Produces: `[DETECTOR 4]` output — a per-floor table of every state/counter divergence over the whole run, each localized to one floor + one subsystem. This replaces "fix the EARLIEST room first, re-run" with "here are ALL the bugs".

- [ ] **Step 1: Add per-seed floor-save discovery**

In `tools/converge_triage.py`, after the `REC`/`SRC` constants:

```python
# Per-floor run.save directories (richer than Resources' 3 act boundaries).
# 933T has all 49 floors in the capture backup; other seeds fall back to
# whatever floor_N dirs exist under Resources (89U: 18/34/49).
_FLOOR_DIRS = {
    "933T39V18D": _DESKTOP / "sts2-run-backups" / "20260723-125401"
                  / "933T39V18D-recording",
}


def load_floor_saves(seed: str) -> dict:
    root = _FLOOR_DIRS.get(seed, REC / seed)
    out = {}
    for p in sorted(root.glob("floor_*")):
        f = p / "run.save"
        if f.exists():
            out[int(p.name.split("_")[1])] = parse_save(f)
    return out
```

- [ ] **Step 2: Pass them into the runner + print DETECTOR 4**

In `main()`, change the `runner.run(...)` call to:

```python
        floor_saves = load_floor_saves(seed)
        result = runner.run(stop_after_act=stop_after_act,
                            player_checkpoints=checkpoints,
                            resync_player=True,
                            floor_saves=floor_saves,
                            resync_floors=True)
```

and after the DETECTOR 3 block:

```python
    # ---- DETECTOR 4: per-floor full-state deltas (resynced => independent) --
    floor_divs = [d for d in result.divergences
                  if d.stream.startswith("floor_")]
    by_floor: dict[int, list] = {}
    for d in floor_divs:
        by_floor.setdefault(d.command_index, []).append(d)
    print(f"\n[DETECTOR 4] per-floor state deltas "
          f"({len(floor_saves)} checkpoints, resync ON — each floor's deltas "
          f"are INDEPENDENT bugs): {len(by_floor)} divergent floor(s)")
    for floor in sorted(by_floor):
        streams = ", ".join(d.stream.removeprefix("floor_")
                            for d in by_floor[floor])
        print(f"  floor {floor:2d}: {streams}")
        for d in by_floor[floor][:4]:
            print(f"      {d.stream}: expected {d.expected!r} "
                  f"got {d.actual!r}")
```

Also update the `clean` computation to include `and not floor_divs`.

- [ ] **Step 3: Smoke-run both seeds**

Run: `py tools/converge_triage.py 933T39V18D floor_49 2` and
`py tools/converge_triage.py 89U21BV1TZ floor_49 2`.
Expected: DETECTOR 4 prints per-floor tables (933T: up to 49 checkpoints; 89U: 3).
Run each twice — output must be **identical** (Task 1). Save both outputs; this
is the work-queue for Task 8.

- [ ] **Step 4: Stage**

```bash
git add tools/converge_triage.py
```

---

### Task 5: Wrong-stream tripwire as a permanent fuzz gate

**Files:**
- Create: `sts2_rl/conformance/tripwire.py` (extracted from `tools/converge_triage.py:86-135`)
- Modify: `tools/converge_triage.py` (import from the new module instead of local copies)
- Test: `test/test_rng_tripwire.py` (new)

**Interfaces:**
- Consumes: `sts2_rl.driver.play_random_run` (check its exact signature first: `Grep "def play_random_run" sts2_rl/driver.py -A 5` — adapt the test's call accordingly); `RunState`.
- Produces: `Tripwire` class — `tw = Tripwire(); tw.install(rng); tw.bug_sites() -> dict[(file,line,func,owner), count]` — and a pytest gate that fails on ANY in-combat shared-rng draw across seeded random runs. This finds every wrong-stream site reachable by random play (all ported content), not just what two recordings touch — e.g. `mad_science.py:142` would have been caught here without a recording.

- [ ] **Step 1: Extract the tripwire into `sts2_rl/conformance/tripwire.py`**

Move `_PUBLIC`, `_PLUMBING`, `_innermost_combat_site`, and `_wrap` from
`tools/converge_triage.py` into a class (same logic, state on the instance
instead of module globals):

```python
"""RNG tripwire: record every draw on a wrapped random.Random that happens
while a combat.py frame is on the stack. In a parity combat every legitimate
draw goes through combat.combat_rng — a shared-rng draw in combat is a
wrong-stream bug by construction (converge_triage DETECTOR 1, now also a
standalone fuzz gate in test_rng_tripwire.py)."""
from __future__ import annotations

_PUBLIC = ("random", "choice", "choices", "sample", "shuffle",
           "randint", "randrange", "uniform")
_PLUMBING = ("\\rng.py", "\\combat_rng.py", "\\hooks.py",
             "/rng.py", "/combat_rng.py", "/hooks.py")


class Tripwire:
    def __init__(self) -> None:
        self.hits: dict[tuple, int] = {}
        self._depth = 0

    # _innermost_combat_site: verbatim from tools/converge_triage.py:90-114,
    # as a method (self unused beyond namespacing).

    def install(self, rng) -> None:
        for meth in _PUBLIC:
            orig = getattr(rng, meth, None)
            if orig is None:
                continue

            def make(orig):
                def wrapper(*a, **kw):
                    if self._depth == 0:
                        site = self._innermost_combat_site()
                        if site is not None:
                            self.hits[site] = self.hits.get(site, 0) + 1
                    self._depth += 1
                    try:
                        return orig(*a, **kw)
                    finally:
                        self._depth -= 1
                return wrapper
            setattr(rng, meth, make(orig))

    def bug_sites(self) -> dict[tuple, int]:
        """Everything except the benign constructor-HP bucket."""
        return {k: v for k, v in self.hits.items() if k[2] != "__init__"}
```

Update `tools/converge_triage.py` to `from sts2_rl.conformance.tripwire import Tripwire`
and use one instance where it used the module globals (`_hits` → `tw.hits`,
`_wrap` → `tw.install`, bug filtering → `tw.bug_sites()`).

- [ ] **Step 2: Write the fuzz gate**

```python
"""Fuzz gate: N seeded random full runs must make ZERO in-combat draws on the
legacy shared rng. Every hit is a wrong-stream parity bug with an exact
file:line — fix by routing the site through the correct combat_rng stream
(see converge_triage.STREAM_SRC for the stream->source-of-truth table)."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("i", range(20))
def test_no_wrong_stream_draws_in_random_run(i):
    from sts2_rl.conformance.tripwire import Tripwire
    from sts2_rl.driver import play_random_run   # check signature; adapt below
    import sts2_rl.run as run_mod

    tw = Tripwire()
    orig_init = run_mod.RunState.__init__

    def patched(self, *a, **kw):
        orig_init(self, *a, **kw)
        tw.install(self.rng)

    run_mod.RunState.__init__ = patched
    try:
        play_random_run(seed=i)   # ADAPT to the real signature (Step 2 grep);
                                  # the run must be a real full run with a
                                  # string_seed so combat_rng streams exist.
    finally:
        run_mod.RunState.__init__ = orig_init
    assert not tw.bug_sites(), (
        "wrong-stream in-combat draws:\n" + "\n".join(
            f"  {n}x {f}:{ln} ({fn}) near={own or '?'}"
            for (f, ln, fn, own), n in sorted(
                tw.bug_sites().items(), key=lambda kv: -kv[1])))
```

- [ ] **Step 3: Run the gate; triage its finds**

Run: `py -m pytest test/test_rng_tripwire.py -q`
Expected: some FAILs — each failure message lists exact `file:line` sites.
For each site: read the corresponding game source (which stream does the game
draw on? `STREAM_SRC` in converge_triage maps stream→file), move the draw onto
`combat.combat_rng.<stream>` with a source citation comment, and check whether
the source is a `StableShuffle(...).First()` (`[[random-card-pick-is-a-shuffle]]`
— that changes the draw COUNT, not just the stream). Known outstanding instance
to expect here: `sts2_rl/cards/mad_science.py:142` (`_play_skill` chaos rider —
Lead 2 of `docs/superpowers/prompts/2026-07-23-sp3-converge-act2-glory.md`;
ground truth `Core/Models/Cards/MadScience.cs` + `Core/Models/Events/TinkerTime.cs`).
Each fix gets its own focused unit test in the suite file where that content is
tested (match existing test placement conventions).

- [ ] **Step 4: Run to green + full suite**

Run: `py -m pytest test/test_rng_tripwire.py -q` → all 20 PASS.
Run: `py -m pytest test/ -q` → baseline + new tests, no regressions.
If a site is genuinely unfixable right now (needs unported plumbing), add it to
a module-level `_ALLOWLIST: set[tuple[str, int]]` in the test with a comment
citing the debt — the assert filters allowlisted `(file, line)` pairs. Keep the
allowlist empty if at all possible.

- [ ] **Step 5: Stage**

```bash
git add sts2_rl/conformance/tripwire.py tools/converge_triage.py test/test_rng_tripwire.py <any fixed content files + their tests>
```

---

### Task 6: Enemy display-name sweep (all six seeds are ground truth)

**Files:**
- Create: `tools/audit_enemy_names.py`
- Modify: whichever `sts2_rl/monsters/**/*.py` the audit flags (name fixes only)

**Interfaces:**
- Consumes: `parse_recording` (annotation `.enemies` entries are `(name, hp, max_hp)` tuples — same shape `combat_driver._live_enemy_states` produces); the four act rosters' monster classes (`sts2_rl.monsters.{overgrowth,underdocks,hive,glory}`).
- Produces: a report of every enemy name appearing in ANY recording that no sim monster carries — enemy names are character-independent, so the four non-Ironclad recordings (DJDC/L081/QRWC/TZEK) contribute ground truth here even though they can never replay. Each name mismatch found later in a replay costs a force-win + a full triage cycle; this kills the class in one sweep.

- [ ] **Step 1: Write the audit script**

```python
r"""One-shot audit: every enemy display name in EVERY recording's
`|| ... Enemies: [...]` annotations vs the names the sim's monster classes
carry. A mismatch ('Corpse Slug' vs 'CorpseSlug') costs a force-win during
replay — fix the sim class's `name` to the recorded spelling (the game's
localized Title is the ground truth the mod recorded).

Usage: py tools/audit_enemy_names.py
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
REC = _REPO.parent / "RunReplays" / "RunReplays" / "Resources"

from sts2_rl.conformance.recording import parse_recording  # noqa: E402


def sim_names() -> set[str]:
    import importlib
    import inspect
    from sts2_rl.monsters.base import Monster

    names = set()
    for act in ("overgrowth", "underdocks", "hive", "glory"):
        mod = importlib.import_module(f"sts2_rl.monsters.{act}")
        pkg = Path(mod.__file__).parent
        for py in pkg.glob("*.py"):
            m = importlib.import_module(f"sts2_rl.monsters.{act}.{py.stem}")
            for _, cls in inspect.getmembers(m, inspect.isclass):
                if issubclass(cls, Monster) and cls is not Monster:
                    n = getattr(cls, "name", None)
                    if isinstance(n, str):
                        names.add(n)
    return names


def recorded_names() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for log in sorted(REC.glob("*/floor_49/actions.sts2replay")):
        seed = log.parent.parent.name
        rec = parse_recording(log)
        for cmd in rec.commands:
            ann = getattr(cmd, "annotation", None)
            enemies = getattr(ann, "enemies", None) if ann else None
            if not enemies:
                continue
            for entry in enemies:
                name = entry[0] if isinstance(entry, (tuple, list)) else entry
                name = re.sub(r" #\S+$", "", name)   # Test Subject #C71 etc.
                out.setdefault(name, []).append(seed)
    return out


def main() -> None:
    have = sim_names()
    missing = {n: seeds for n, seeds in recorded_names().items()
               if n not in have}
    print(f"sim monster names: {len(have)}   "
          f"recorded names missing from sim: {len(missing)}")
    for name, seeds in sorted(missing.items()):
        close = difflib.get_close_matches(name, have, n=1)
        hint = f"  (closest sim name: {close[0]!r})" if close else ""
        print(f"  {name!r}  [seen in {', '.join(sorted(set(seeds)))}]{hint}")


if __name__ == "__main__":
    main()
```

**Verify the annotation attribute names first** (`Grep "enemies" sts2_rl/conformance/recording.py -n`)
and adapt `recorded_names` to the parser's real object shape (the combat driver
reads `ann.enemies` as `(name, hp, max_hp)`).

- [ ] **Step 2: Run it**

Run: `py tools/audit_enemy_names.py`
Expected: a (hopefully short) list. Names with a close sim match = spelling fixes
(edit the sim class's `name` attr to the recorded spelling — recorded is ground
truth). Names with NO close match = unported monsters (fine for non-Ironclad-act
content; note them, don't port speculatively).

- [ ] **Step 3: Fix the spelling mismatches + guard**

For each spelling fix, update the monster class's `name` and any test that
asserted the old spelling. Re-run the audit → only genuinely-unported names
remain. Then run `py -m pytest test/ -q` → green.

- [ ] **Step 4: Stage**

```bash
git add tools/audit_enemy_names.py sts2_rl/monsters/ <touched tests>
```

---

### Task 7: Monster branch-table audit (weight-vs-cooldown class)

**Files:**
- Create: `tools/audit_monster_machines.py`
- Modify: flagged `sts2_rl/monsters/**/*.py` (port to `MachineMonster` or fix branch args)
- Test: per-monster move tests alongside the existing ones (`test/test_hive.py` pattern — see the TwigSlimeM/Flyconid fixes)

**Interfaces:**
- Consumes: the C# move declarations (`Slay the Spire 2/src/Core/Models/Monsters/*.cs` and `src/Core/MonsterMoves/**`), the sim's monster modules.
- Produces: a report listing, per sim monster, (a) whether its source uses `RandomBranchState`/`ConditionalBranchState`, (b) whether the sim implements it as a hand-rolled `_move_key` pattern, and (c) the source's raw `AddBranch(...)` argument lists. Hand-rolled + RandomBranchState = a flagged monster: the exact class of `[[monster-move-weight-vs-cooldown-bug]]` (int args after the weight are **cooldown/maxRepeats**, not weights — misreading them corrupts both move choice AND MonsterAi draw counts).

- [ ] **Step 1: Establish the C# `AddBranch` signature(s)**

Run: `Grep "AddBranch" "c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\MonsterMoves" -n -A 2 --head_limit 20`
and read the `RandomBranchState` class definition to enumerate its overloads
(weight-only, weight+cooldown, weight+repeat-rule, lambda weights). Write the
overload table into the audit script's docstring — it is the decoder for
Step 2's regex output.

- [ ] **Step 2: Write the audit script**

```python
r"""Static audit: which sim monsters hand-roll moves whose game source uses
RandomBranchState/ConditionalBranchState, and what the source's exact branch
args are. Output is a review table, not an auto-fix — the human (or the fixing
session) reads each flagged monster's source and ports/corrects it.

Usage: py tools/audit_monster_machines.py [act]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
SRC = _REPO.parent / "Slay the Spire 2" / "src"
MON = SRC / "Core" / "Models" / "Monsters"
MOVES = SRC / "Core" / "MonsterMoves"

_BRANCH = re.compile(r"AddBranch\s*\(([^;]*?)\)\s*;", re.S)


def source_for(cls_name: str) -> Path | None:
    for cand in (cls_name, cls_name.rstrip("SM"), cls_name[:-1]):
        f = MON / f"{cand}.cs"
        if f.exists():
            return f
    return None


def branch_table(cs: Path) -> list[str]:
    text = cs.read_text(encoding="utf-8", errors="replace")
    # Follow the move-machine type referenced by the monster into MonsterMoves/.
    for m in re.finditer(r"new\s+(\w+MoveStateMachine|\w+Moves?)\s*\(", text):
        extra = list(MOVES.rglob(f"{m.group(1)}.cs"))
        if extra:
            text += extra[0].read_text(encoding="utf-8", errors="replace")
    return [" ".join(b.split()) for b in _BRANCH.findall(text)]


def main(act_filter: str | None) -> None:
    import importlib
    import inspect
    from sts2_rl.monsters.base import Monster
    from sts2_rl.monsters.state_machine import MachineMonster

    for act in ("overgrowth", "underdocks", "hive", "glory"):
        if act_filter and act != act_filter:
            continue
        mod = importlib.import_module(f"sts2_rl.monsters.{act}")
        pkg = Path(mod.__file__).parent
        for py in sorted(pkg.glob("*.py")):
            m = importlib.import_module(f"sts2_rl.monsters.{act}.{py.stem}")
            for cname, cls in inspect.getmembers(m, inspect.isclass):
                if not (issubclass(cls, Monster) and cls is not Monster):
                    continue
                if cls.__module__ != m.__name__:
                    continue
                cs = source_for(cname)
                if cs is None:
                    continue
                branches = branch_table(cs)
                hand_rolled = not issubclass(cls, MachineMonster)
                if branches and hand_rolled:
                    print(f"[FLAG] {act}.{cname}  ({cs.name}) — hand-rolled "
                          f"but source has {len(branches)} AddBranch calls:")
                    for b in branches:
                        print(f"    AddBranch({b})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
```

**Verify the class names** (`MachineMonster`, module paths) against
`sts2_rl/monsters/state_machine.py` before running; adapt.

- [ ] **Step 3: Run the audit; fix flagged monsters, Hive/Glory first**

Run: `py tools/audit_monster_machines.py hive` then `... glory` then the act-1 acts.
For each flagged monster: read its `.cs` + the overload table from Step 1;
either (a) port it to `MachineMonster` (the CLAUDE.md-preferred fix — Byrdonis/
Fogmog/Mawler are the exemplars) or (b) at minimum correct any int arg
misread as a weight. Every fix follows TDD: a failing move-sequence test first
(drive the monster N turns with a seeded `monster_ai` stream, assert the move
sequence the source's machine produces — copy the structure of the TwigSlimeM/
Flyconid tests referenced in `[[monster-move-weight-vs-cooldown-bug]]`), then
the fix, then green. **Draw-count parity matters as much as move choice:**
`RandomBranchState.GetNextState` always draws one `NextFloat` per transition,
even when a repeat rule forces a single branch (STREAM_SRC's MonsterAi rule).

- [ ] **Step 4: Full suite + stage**

Run: `py -m pytest test/ -q` → green, no regressions.

```bash
git add tools/audit_monster_machines.py sts2_rl/monsters/ test/
```

---

### Task 8: Grind 89U21BV1TZ + 933T39V18D to green (with the new tooling)

**Files:**
- Modify: whatever the triage implicates (engine/content files + their tests)
- Modify at the end: `test/test_conformance_player_state.py` (drop the two `_XFAIL_CONVERGENCE` entries as each seed converges)

**Interfaces:**
- Consumes: DETECTOR 1–4 triage (`py tools/converge_triage.py <seed> floor_49 2`); the canonical method docs — `docs/superpowers/prompts/2026-07-22-sp3-seed-convergence-grind.md` (procedure) and `docs/superpowers/prompts/2026-07-23-sp3-converge-act2-glory.md` (per-seed leads; **note its Lead 1, the multi-index `SelectGridCard`, is ALREADY FIXED in `runner.py:_answer_select_grid` — re-triage before touching anything it claims**; Lead 2, `mad_science.py:142`, falls out of Task 5).
- Produces: both Ironclad seeds' `test_full_run_player_state_parity` cases at PASS (xfail marks removed): zero `player_hp`/`player_max_hp` divergence at every act boundary, `forced_combats=0`, no premature stops, unregressed stream counters.

The loop, updated for the new tooling:

- [ ] **Step 1: Fresh triage on both seeds; snapshot the DETECTOR 4 tables**

Run: `py tools/converge_triage.py 933T39V18D floor_49 2 > scratch/933T.txt` and the same for 89U (fewer checkpoints — 3 floors — until/unless more of its per-floor saves surface; its DETECTOR 2b per-command diffs remain the fine-grained signal there).

- [ ] **Step 2: Fix per-floor, in any order (they're independent under resync)**

For each divergent floor in the DETECTOR 4 table: the streams named tell you the
subsystem (`deck` → reward/transform/shop; `gold` → reward/shop prices; `hp` →
that floor's combat pipeline; `counter_X` → a missing/extra draw on stream X
*within that one floor*). Reproduce with a **floor-local** mindset: the resync
guarantees the sim entered the floor in the recorded state, so the bug is inside
that floor's room. Fix earliest-per-floor, not earliest-per-run. Combat-parity
mechanics already established are in
`[[sp3-task9-convergence]]` / the grind prompt §"Combat-parity mechanics" —
check them before re-deriving (net_id targeting, PileType.Play limbo,
transform-append, reward pool = GetUnlockedCards, grid screens are one command,
killing-blow skips AfterDamageReceived, `[[relic-rarity-rolls-on-rewards]]`,
`[[potion-belt-and-profile-names]]`, `[[stable-shuffle-tie-order]]`).
Every behavior fix: failing test with a source citation → fix → suite. Stage per
subsystem (small diffs).

**Parallelization option (Perry's call, not default):** because resynced floors
are independent, divergent floors can be batched by subsystem and dispatched to
parallel worker sessions/worktrees (superpowers:dispatching-parallel-agents) —
merge order doesn't matter as long as each batch keeps the full suite green.

- [ ] **Step 3: Converge, then tighten**

When DETECTOR 4 shows zero divergent floors WITH resync on, re-run with
`resync_floors=False` (edit the call or add a CLI flag) — the true end-to-end
gate. Remaining divergences at this stage are ordering/interaction effects the
resync masked; they'll be few and localized by the floor table anyway.

- [ ] **Step 4: Flip the gates**

For each converged seed: remove its `_XFAIL_CONVERGENCE` entry + mark in
`test/test_conformance_player_state.py`.
Run: `py -m pytest test/test_conformance_player_state.py -k full_run_player_state_parity -q` → PASS (not XPASS).
Run: `py -m pytest test/ -q` → green.

- [ ] **Step 5: Stage everything; report to Perry**

```bash
git add <all touched files>
git status   # include in the report: staged diff summary + fidelity gaps found (memory each)
```

---

### Task 9: Coverage report + cheap-fixture strategy (set up the NEXT increment)

**Files:**
- Create: `tools/conformance_coverage.py`

**Interfaces:**
- Consumes: `SaveOracle.encounter_ids_by_act` / `relic_ids` / `deck` / `potion_slots` (+ `events_seen` — add it to `parse_save` the same way Task 2 added gold: `d.get("events_seen", [])`); the sim registries (`ENCOUNTERS` per act, `ALL_RELICS`, `ALL_POTIONS`, the event registry).
- Produces: a three-bucket report per content type — **(a)** exercised by a converged Ironclad seed (trusted), **(b)** ported but never exercised (untested fidelity risk — the next recording should target these), **(c)** appearing in any recording but unported (known debt). Bucket (b) is the recording shopping list.

- [ ] **Step 1: Write the tool**

```python
r"""Conformance coverage: which ported content has actually been verified by a
converged seed, which is untested, and which recorded content is unported.

Usage: py tools/conformance_coverage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
REC = _REPO.parent / "RunReplays" / "RunReplays" / "Resources"

from sts2_rl.conformance import idmap                      # noqa: E402
from sts2_rl.conformance.save import parse_save            # noqa: E402

CONVERGED = ["89U21BV1TZ", "933T39V18D"]   # update as seeds go green


def main() -> None:
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.potions import ALL_POTIONS

    seen_relics, seen_potions, seen_encounters = set(), set(), set()
    for seed in CONVERGED:
        f = REC / seed / "floor_49" / "run.save"
        if not f.exists():
            continue
        o = parse_save(f)
        seen_relics |= {idmap.sim_relic_id(r) for r in o.relic_ids}
        seen_potions |= {idmap.sim_potion_id(p)
                         for p in o.potion_slots.values()}
        for act in o.encounter_ids_by_act:
            seen_encounters |= set(act["normal"]) | set(act["elite"])
            seen_encounters |= {act["boss"], act["ancient"]} - {None}

    untested_relics = sorted(set(ALL_RELICS) - seen_relics - {None})
    untested_potions = sorted(set(ALL_POTIONS) - seen_potions - {None})
    print(f"relics  verified {len(seen_relics - {None})} / ported {len(ALL_RELICS)}")
    print(f"potions verified {len(seen_potions - {None})} / ported {len(ALL_POTIONS)}")
    print(f"encounters seen in converged saves: {len(seen_encounters)}")
    print("\nUNTESTED relics (recording shopping list):")
    print("  " + ", ".join(untested_relics))
    print("\nUNTESTED potions:")
    print("  " + ", ".join(untested_potions))


if __name__ == "__main__":
    main()
```

(Encounter-registry cross-referencing needs the per-act `ENCOUNTERS` id
convention — extend the tool to diff against them once the save's encounter-id
spelling is confirmed against one act's `ENCOUNTERS` keys; card coverage is
noisier and can wait.)

- [ ] **Step 2: Run it; write the recording guidance into the report**

Run: `py tools/conformance_coverage.py`. Deliverable to Perry alongside the
output — the new fixture economics:

> A fixture no longer needs to be a full victory run. Every floor's `run.save`
> is a checkpoint, so a **20-minute act-1-only Ironclad recording is a complete,
> immediately-usable fixture** (its per-floor saves slot straight into
> DETECTOR 4). Record short runs that deliberately pick the UNTESTED content
> from this report (shop-heavy runs, untested relics/potions, unexercised
> events). Copy the full per-floor folder (like `933T39V18D-recording/`) —
> not just the act-boundary floors.

- [ ] **Step 3: Stage**

```bash
git add tools/conformance_coverage.py sts2_rl/conformance/save.py
```

---

### Task 10 (deferred decision, no implementation): in-game auto-validation

The final acceptance (design doc §Acceptance 2) still ends with "the exported
replay plays on the real game", verified manually. If the remaining manual step
becomes the bottleneck, the highest-ROI follow-up is a small RunReplays-mod
addition: auto-load a replay on launch, run at max speed, dump per-command
annotations to a log (the mod already produces exactly these annotations when
recording). That would close the loop sim→game→diff with zero manual play. It
contradicts the design's "no C# changes to RunReplays" non-goal, so it is
**Perry's call** — present it, don't build it.

---

## Self-review notes (done at write time)

- **Spec coverage:** the design doc's SP3 green criterion ("Hand/Enemies
  annotations match through full fights") is Task 8's DoD; SP4-adjacent state
  (gold/deck/relics per floor) rides the same Task 3 oracle, which is
  deliberately broader than SP3 because the saves give it for free. SP5
  (exporter) is out of scope here and unblocked by Task 8's green.
- **Known API-verification points** (each has an explicit in-task check step,
  because this plan was written against read code but not executed): run.py
  attribute names in Task 3 Step 6; `play_random_run` signature in Task 5;
  `recording.py` annotation shape in Task 6; `AddBranch` overloads in Task 7.
- **Type consistency:** `SaveOracle.deck: list[tuple[str, int]]` produced in
  Task 2 = consumed by Task 3 `_check_floor_state`/`_resync_deck` and Task 9;
  `Tripwire.install/bug_sites` produced in Task 5 Step 1 = consumed by Step 2
  and by the converge_triage refactor; `floor_saves: dict[int, SaveOracle]`
  produced by Task 4 `load_floor_saves` = the Task 3 `run()` kwarg.
