# Ironclad Fidelity Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "the sim behaves exactly like the real game for Ironclad" a gated claim: adjudicate the 933T39V18D floor 47/49 triage residue, promote every convergence detector into strict suite gates for both Ironclad seeds, and re-audit every stale audit record.

**Architecture:** Three phases, strictly ordered. Phase 1 (Tasks 0–4) fixes the triage *instrument* — a per-room oracle from `map_point_history`, snapshot-provenance labels, resolved final-floor resync semantics — then adjudicates each residual signal as real-gap vs harness-artifact vs capture-semantics. Phase 2 (Task 5) extracts one shared "converged" predicate and gates the suite on it so triage and pytest can never disagree again. Phase 3 (Tasks 6–9) is the stale-record sweep, last because Phase-1 engine edits would re-stale earlier re-audits.

**Tech Stack:** Python 3 (`py` launcher), pytest, the existing conformance harness (`sts2_rl/conformance/`), the audit tooling (`audit/tools/`), git plumbing for historical-blob recovery.

**Spec:** `docs/superpowers/specs/2026-08-03-ironclad-fidelity-closure-design.md`

## Global Constraints

- **Never `git commit` or `git push`. Stage only (`git add`); Perry commits.** Every task's final "Commit" step is therefore a *Stage* step. This overrides the default skill workflow (standing project rule).
- Python is invoked as `py` (Windows launcher). Full suite: `py -m pytest test/ -q` from the repo root `c:\Users\Perry\Desktop\sts2-rl`. Record the baseline count in Task 0 and never regress it.
- **Triage determinism rule:** never trust a single `converge_triage.py` delta — run it until you have seen the same output twice in a row (historically 2–3 runs; out-of-combat draws on the unseeded shared rng can vary).
- Conformance fixtures live outside the repo: recordings at `C:\Users\Perry\Desktop\RunReplays\RunReplays\Resources\<seed>\floor_N\`, 933T per-floor backups at `C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording\`. Every new test that reads them must carry the existing `pytest.mark.skipif(not REC.exists(), ...)` guard pattern (see `test/test_conformance_runner.py:34`).
- The decompiled game source (ground truth) is at `c:\Users\Perry\Desktop\Slay the Spire 2\src\`.
- **Never edit `audit/tools/harness.py`** (seam-tier-owned). New audit tooling goes in new files under `audit/tools/`.
- Audit records follow `audit/README.md`: verdict vocabulary (`faithful`/`waiver`/`deliberate-divergence`/`gap`), rollup rule, `rehash` only as the last step of a real re-audit. After any edit to `audit/GAP-QUEUE.md`, run `py audit/tools/gap_queue.py coverage` and `py audit/tools/gap_queue.py cite-check` — both must exit 0.
- Every edit to `sts2_rl/**` stales audit records. That is expected during Tasks 1–5 and is why the sweep (Tasks 6–8) runs last. Do not `rehash` anything before Task 7.

## Verified starting facts (measured 2026-08-03; re-verify in Task 0)

- `py tools/converge_triage.py 89U21BV1TZ floor_49 2` → `FULLY CONVERGED`.
- `py tools/converge_triage.py 933T39V18D floor_49 2` → `DIVERGENCES REMAIN`: DETECTOR 4 floor 47 (`floor_hp` expected 74 got 66, `floor_counter_CombatTargets` 21 vs 22) and floor 49 (`floor_hp` expected 80 got 67, `floor_counter_Shuffle` 892 vs 909, `floor_counter_CombatCardSelection` 9 vs 8); DETECTOR 2 run-end Shuffle 909 vs 892, CombatCardSelection 8 vs 9, CombatTargets 26 vs 25; DETECTOR 3 act-2 `player_hp` expected 67 got 80. Reproduced identically twice.
- The suite hard gate `test/test_conformance_player_state.py::test_full_run_player_state_parity` (resync OFF) is **green** for both Ironclad seeds.
- Both detectors already use the same sense — `Divergence(stream, index, expected=<oracle>, actual=<sim>)` (`runner.py:591`, `runner.py:678-685`). The "inversion" documented in `GAP-QUEUE.md` (search `opposite expected/got senses`) is actually two *different oracles*: DETECTOR 3 reads the run-END capture (`Resources/<seed>/floor_49/run.save`), DETECTOR 4 reads per-floor backup saves. They can legitimately disagree.
- **The third oracle disagrees with the second:** the run-end save's `map_point_history` (act 2, point index 12 = floor 47) records `current_hp: 66` — exactly what the sim produced — while the floor-47 backup save says 74. And the final act-2 point records `current_hp: 0` while the same file's `players[0].current_hp` is 67. Capture-moment semantics are unresolved; that is Task 3's job.
- `map_point_history` shape (933T end save): 3 acts × [17, 16, 15] points; each point has keys `map_point_type`, `player_stats` (list, one entry, `player_id: 1`), `rooms`. `player_stats[0]` scalar keys: `current_gold`, `current_hp`, `damage_taken`, `gold_gained`, `gold_lost`, `gold_spent`, `gold_stolen`, `hp_healed`, `max_hp`, `max_hp_gained`, `max_hp_lost`, `player_id`, `stolen_loot` (plus lists `card_choices`, `cards_gained`, `relic_choices`, `event_choices`).
- Audit ledger: 347 gap entries, all dormant, 0 live; ~843 of 954 records **stale** (`py audit/tools/audit_status.py`).

---

### Task 0: Baseline receipts

**Files:**
- Create: `docs/superpowers/plans/2026-08-03-ironclad-fidelity-closure-baseline.md`

**Interfaces:**
- Produces: the baseline numbers every later task's "no regression" check compares against.

- [ ] **Step 1: Record the suite baseline**

Run: `py -m pytest test/ -q 2>&1 | tail -3`
Expected: a pass count (last known ~4650 passed, 0 failed, some xfail/skip). Copy the exact tail line.

- [ ] **Step 2: Record triage baselines (determinism rule: twice each, must match)**

```
py tools/converge_triage.py 89U21BV1TZ floor_49 2
py tools/converge_triage.py 89U21BV1TZ floor_49 2
py tools/converge_triage.py 933T39V18D floor_49 2
py tools/converge_triage.py 933T39V18D floor_49 2
```
Expected: 89U `FULLY CONVERGED` twice; 933T `DIVERGENCES REMAIN` twice with the exact numbers listed under "Verified starting facts". If anything differs from those facts, STOP and report — the plan's premises have drifted.

- [ ] **Step 3: Record the audit baseline**

```
py audit/tools/audit_status.py
py audit/tools/gap_queue.py counts
```
Expected: per-kind stale counts summing to ~843; 347 entries / 322 mechanisms / 0 live.

- [ ] **Step 4: Write all three outputs verbatim into the baseline doc and stage**

```
git add docs/superpowers/plans/2026-08-03-ironclad-fidelity-closure-baseline.md
```

---

### Task 1: Per-room oracle — `RoomStats` parsing + DETECTOR 5

The queue calls this "the highest-leverage tooling left": `map_point_history.player_stats` carries per-room HP/gold that nobody reads. This task parses it and adds an **opt-in, report-only** per-room check to the runner.

**Files:**
- Modify: `sts2_rl/conformance/save.py` (add `RoomStats`, parse into `SaveOracle.room_stats_by_act`)
- Modify: `sts2_rl/conformance/runner.py` (add `_check_room_stats`, call it beside the existing `_check_floor_state` call; new `run()` kwarg `check_room_stats=False`)
- Modify: `tools/converge_triage.py` (pass `check_room_stats=True`, print DETECTOR 5)
- Test: `test/test_conformance_room_stats.py` (new)

**Interfaces:**
- Consumes: `SaveOracle` (`sts2_rl/conformance/save.py:19`), `Divergence(stream, command_index, expected, actual, note)` from `sts2_rl/conformance/comparators.py`, `parse_save`.
- Produces: `RoomStats` dataclass; `SaveOracle.room_stats_by_act: list[list[RoomStats]]`; `Divergence` streams `room_hp`, `room_max_hp`, `room_gold` with `command_index = run.total_floor`; `ReplayRunner.run(..., check_room_stats: bool = False)`. Task 3's probe and Task 5's gates rely on these exact names.

- [ ] **Step 1: Write the failing parsing test**

Create `test/test_conformance_room_stats.py`:

```python
"""DETECTOR 5: per-room player-state oracle from map_point_history."""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.save import parse_save

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")


def test_room_stats_parsed_per_act():
    o = parse_save(REC / "933T39V18D" / "floor_49" / "run.save")
    assert [len(a) for a in o.room_stats_by_act] == [17, 16, 15]
    st = o.room_stats_by_act[1][3]          # act 1, 4th point — known values
    assert st.current_hp == 69
    assert st.max_hp == 80
    assert st.damage_taken == 17
    assert st.hp_healed == 6
    assert st.current_gold == 345
    # every parsed point carries a map_point_type string
    assert all(p.map_point_type for act in o.room_stats_by_act for p in act)


def test_room_stats_empty_when_history_absent():
    # floor_18 truncation saves still carry history; construct absence instead
    from sts2_rl.conformance.save import SaveOracle
    o = SaveOracle(run_seed="X", player_seed=0, ascension=0, acts=[],
                   current_act_index=0, run_counters={}, player_counters={})
    assert o.room_stats_by_act == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `py -m pytest test/test_conformance_room_stats.py -v`
Expected: FAIL — `SaveOracle` has no attribute `room_stats_by_act`.

- [ ] **Step 3: Implement `RoomStats` in `save.py`**

Add after the imports, before `SaveOracle`:

```python
@dataclass
class RoomStats:
    """One resolved map point's player_stats from `map_point_history`.

    Capture-moment caveat: alignment against the per-floor backup saves is
    established empirically by tools/oracle_semantics_probe.py — do not assume
    entry-vs-resolve semantics here."""
    map_point_type: str
    current_hp: int
    max_hp: int
    damage_taken: int
    hp_healed: int
    current_gold: int
    gold_gained: int
    gold_spent: int
    gold_lost: int
    gold_stolen: int
    max_hp_gained: int
    max_hp_lost: int
```

Add the field to `SaveOracle` (beside `map_history`):

```python
    room_stats_by_act: list[list["RoomStats"]] = field(default_factory=list)
```

In `parse_save`, before the `return`, build it:

```python
    room_stats: list[list[RoomStats]] = []
    for act in d.get("map_point_history", []):
        row = []
        for pt in act:
            ps = (pt.get("player_stats") or [{}])[0]
            row.append(RoomStats(
                map_point_type=pt.get("map_point_type", ""),
                current_hp=ps.get("current_hp", 0),
                max_hp=ps.get("max_hp", 0),
                damage_taken=ps.get("damage_taken", 0),
                hp_healed=ps.get("hp_healed", 0),
                current_gold=ps.get("current_gold", 0),
                gold_gained=ps.get("gold_gained", 0),
                gold_spent=ps.get("gold_spent", 0),
                gold_lost=ps.get("gold_lost", 0),
                gold_stolen=ps.get("gold_stolen", 0),
                max_hp_gained=ps.get("max_hp_gained", 0),
                max_hp_lost=ps.get("max_hp_lost", 0)))
        room_stats.append(row)
```

and pass `room_stats_by_act=room_stats` in the `SaveOracle(...)` constructor call.

- [ ] **Step 4: Run the test; expect PASS**

Run: `py -m pytest test/test_conformance_room_stats.py -v` → 2 passed.

- [ ] **Step 5: Write the failing runner test (append to the same file)**

```python
def test_detector5_reports_room_hp_divergence_for_933t():
    """With check_room_stats=True the runner emits room_* divergences wherever
    the sim's post-room state differs from map_point_history. This is
    report-only — divergence lists elsewhere (player_hp, floor_*) are
    unchanged, and running with the flag off emits none."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner

    b = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    on = ReplayRunner(rec, oracle).run(stop_after_act=2, check_room_stats=True)
    off = ReplayRunner(parse_recording(b / "actions.sts2replay"),
                       parse_save(b / "run.save")).run(stop_after_act=2)
    room = [d for d in on.divergences if d.stream.startswith("room_")]
    assert not [d for d in off.divergences if d.stream.startswith("room_")]
    # the flag must not perturb the replay itself
    assert on.forced_combats == off.forced_combats
    # each room divergence is localized: note names act/room/point-type
    for d in room:
        assert "act " in d.note and "room " in d.note
```

Run: `py -m pytest test/test_conformance_room_stats.py::test_detector5_reports_room_hp_divergence_for_933t -v`
Expected: FAIL — `run() got an unexpected keyword argument 'check_room_stats'`.

- [ ] **Step 6: Implement `_check_room_stats` in `runner.py`**

Find the `run()` signature and the per-room call site of `_check_floor_state`:

```
grep -n "def run(\|_check_floor_state(\|_check_player_state(" sts2_rl/conformance/runner.py
```

Add `check_room_stats: bool = False` to `run()`'s signature and thread it to the same scope that calls `_check_floor_state` (the runner already knows `act_index` and the room index within the act there — the same values `_reconcile_node_relics(run, act_index, room_index, ...)` receives; reuse them). Immediately after the `_check_floor_state` call add:

```python
        if check_room_stats:
            self._check_room_stats(run, divergences, act_index, room_index)
```

Add the method beside `_check_floor_state`:

```python
    def _check_room_stats(self, run, divergences, act_index, room_in_act) -> None:
        """DETECTOR 5: diff sim player state against this room's
        map_point_history player_stats (run-END capture). Report-only —
        never resyncs, never raises. Streams: room_hp / room_max_hp /
        room_gold; command_index = run.total_floor so triage can sort by
        floor. The history is per-act, index = rooms resolved this act."""
        acts = self.oracle.room_stats_by_act
        if act_index >= len(acts) or room_in_act >= len(acts[act_index]):
            return
        st = acts[act_index][room_in_act]
        note = f"act {act_index} room {room_in_act} ({st.map_point_type})"
        for stream, exp, got in (("room_hp", st.current_hp, run.hp),
                                 ("room_max_hp", st.max_hp, run.max_hp),
                                 ("room_gold", st.current_gold, run.gold)):
            if exp != got:
                divergences.append(
                    Divergence(stream, run.total_floor, exp, got, note))
```

**Alignment check while implementing:** the history has one point per *resolved* room including the act-entry Ancient node (act 0: 17 points, 933T walks 17 rooms in act 0). If the first comparison lands off-by-one (e.g. every room diverges by exactly the previous room's value), the index to use is `room_index - 1` or the act-entry Ancient point is index 0 — resolve empirically against act 0 of 933T, where the per-room HP series `[80, 76, 74, 74, 80, 71, ...]` is known. Document the resolved alignment in the method docstring.

- [ ] **Step 7: Run the full new test file; expect PASS**

Run: `py -m pytest test/test_conformance_room_stats.py -v` → 4 passed.

- [ ] **Step 8: Wire DETECTOR 5 into `tools/converge_triage.py`**

In `main()`: pass `check_room_stats=True` to `runner.run(...)`. After the DETECTOR 4 block, add:

```python
    # ---- DETECTOR 5: per-room player-state walk (map_point_history) --------
    room_divs = [d for d in result.divergences if d.stream.startswith("room_")]
    print(f"\n[DETECTOR 5] per-room state deltas vs map_point_history "
          f"(run-END capture, resync never applied): {len(room_divs)}")
    for d in room_divs[:12]:
        print(f"  floor {d.command_index:2d} {d.stream}: expected {d.expected} "
              f"got {d.actual}  ({d.note})")
    if len(room_divs) > 12:
        print(f"  ... +{len(room_divs) - 12} more")
```

and extend the `clean` expression with `and not room_divs`.

- [ ] **Step 9: Run triage on both seeds (twice each) and the full suite**

```
py tools/converge_triage.py 89U21BV1TZ floor_49 2      # x2
py tools/converge_triage.py 933T39V18D floor_49 2      # x2
py -m pytest test/ -q
```
Expected: 89U stays `FULLY CONVERGED` with DETECTOR 5 = 0 (if not, that is a NEW finding — record the exact rooms in the task report; it feeds Task 3). 933T's DETECTOR 5 localizes its HP story to specific rooms. Suite: no regression from Task 0 baseline.

- [ ] **Step 10: Stage**

```
git add sts2_rl/conformance/save.py sts2_rl/conformance/runner.py tools/converge_triage.py test/test_conformance_room_stats.py
```

---

### Task 2: Snapshot-provenance labels + printed-sense pin

`GAP-QUEUE.md`'s standing lesson claims DETECTOR 3 and 4 print "opposite expected/got senses". Task 0's facts show both use `expected=oracle, actual=sim`; the real trap is that they compare **different captures**. Fix the trap, not a phantom bug: label every detector's oracle provenance, pin the sense with a test, and rewrite the queue lesson.

**Files:**
- Modify: `tools/converge_triage.py` (extract two pure formatting helpers; label DETECTOR 3/4 headers)
- Modify: `audit/GAP-QUEUE.md` (rewrite the "opposite expected/got senses" bullet)
- Test: `test/test_converge_triage_format.py` (new)

**Interfaces:**
- Consumes: `Divergence` from `sts2_rl/conformance/comparators.py`.
- Produces: `fmt_hp_line(d: Divergence) -> str` and `fmt_floor_line(d: Divergence) -> str` in `tools/converge_triage.py` (imported by the test via `sys.path` insertion).

- [ ] **Step 1: Write the failing test**

Create `test/test_converge_triage_format.py`:

```python
"""Pin the printed expected/got sense of the triage detectors: `expected` is
ALWAYS the oracle (save capture), `actual`/`got` is ALWAYS the sim, in every
detector. The historical confusion (GAP-QUEUE 'opposite senses' lesson) was
two different captures being compared, not an inversion — so the header must
name its capture."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sts2_rl.conformance.comparators import Divergence


def test_hp_line_names_oracle_as_expected():
    from converge_triage import fmt_hp_line
    line = fmt_hp_line(Divergence("player_hp", 2, 67, 80, "act 2 boundary"))
    assert "expected 67" in line and "got 80" in line
    assert "sim high by 13" in line


def test_floor_line_names_oracle_as_expected():
    from converge_triage import fmt_floor_line
    line = fmt_floor_line(Divergence("floor_hp", 49, 80, 67, ""))
    assert "expected 80" in line and "got 67" in line
```

- [ ] **Step 2: Run it; expect FAIL** (`cannot import name 'fmt_hp_line'`)

Run: `py -m pytest test/test_converge_triage_format.py -v`

- [ ] **Step 3: Extract the helpers in `tools/converge_triage.py`**

Add above `main()` (moving the existing inline logic from the DETECTOR 3 and DETECTOR 4 loops into them):

```python
def fmt_hp_line(d) -> str:
    delta = (d.actual - d.expected) if isinstance(d.actual, int) else "?"
    hi = isinstance(delta, int) and delta > 0
    return (f"  act {d.command_index} {d.stream}: expected {d.expected} "
            f"got {d.actual} (sim {'high' if hi else 'low'} by "
            f"{abs(delta) if isinstance(delta, int) else delta})")


def fmt_floor_line(d) -> str:
    return f"      {d.stream}: expected {d.expected!r} got {d.actual!r}"
```

Replace the corresponding `print(...)` bodies with `print(fmt_hp_line(d))` / `print(fmt_floor_line(d))`. Then change the two headers to name their captures:

- DETECTOR 3 header → `[DETECTOR 3] player-state deltas at act boundaries (oracle: run-END truncation saves Resources/<seed>/floor_{18,34,49}/run.save):`
- DETECTOR 4 header → `[DETECTOR 4] per-floor state deltas (oracle: per-floor backup saves; capture moment per tools/oracle_semantics_probe.py):`

- [ ] **Step 4: Run tests + eyeball triage output**

```
py -m pytest test/test_converge_triage_format.py -v
py tools/converge_triage.py 933T39V18D floor_49 2
```
Expected: 2 passed; triage output identical numbers to Task 0 baseline, new headers, same `DIVERGENCES REMAIN`.

- [ ] **Step 5: Rewrite the GAP-QUEUE lesson**

In `audit/GAP-QUEUE.md`, find the bullet beginning `**The triage tool prints act-boundary and per-floor HP with opposite expected/got senses.**` and replace the whole bullet with:

```markdown
- **DETECTOR 3 and DETECTOR 4 compare different captures, and used to look
  inverted.** Both always print `expected` = oracle, `got` = sim
  (`runner.py` `_check_player_state` / `_check_floor_state` both construct
  `Divergence(stream, idx, expected=oracle, actual=sim)`). The 933T
  "expected 67 got 80" vs "expected 80 got 67" pair was two *oracles*
  disagreeing — the act-boundary check reads the run-END truncation save
  while the per-floor check reads the floor-N backup save, and the run-end
  save's own `map_point_history` is a third oracle that disagrees with the
  backup at floor 47 (66 vs 74). Detector headers now name their capture,
  `test/test_converge_triage_format.py` pins the printed sense, and
  `tools/oracle_semantics_probe.py` reconciles the three oracles per floor.
```

- [ ] **Step 6: Validate the queue file**

```
py audit/tools/gap_queue.py coverage
py audit/tools/gap_queue.py cite-check
```
Expected: both exit 0. (`cite-check` verifies `runner.py` still has those method names; if it flags the new bullet, cite with explicit line numbers that resolve.)

- [ ] **Step 7: Full suite, no regression; stage**

```
py -m pytest test/ -q
git add tools/converge_triage.py test/test_converge_triage_format.py audit/GAP-QUEUE.md
```

---

### Task 3: Oracle-semantics probe → adjudicate floors 47/49 → fix resync semantics

Three oracles exist for 933T per-floor state (per-floor backup saves; the run-end save's `players[0]` block; the run-end save's `map_point_history`). They disagree at floors 47–49. This task establishes each capture's moment empirically, adjudicates every residual DETECTOR 2/3/4 signal as **capture-semantics / harness-artifact / real-gap**, and fixes the harness so artifact classes disappear.

**Files:**
- Create: `tools/oracle_semantics_probe.py`
- Modify: `sts2_rl/conformance/runner.py` (`_check_floor_state` — final-floor resync rule; possibly per-floor oracle-selection fix, per the decision table)
- Modify: `audit/GAP-QUEUE.md` (resolve the two `resync_floors` standing-lesson items)
- Test: extend `test/test_conformance_floor_state.py`

**Interfaces:**
- Consumes: `SaveOracle.room_stats_by_act` (Task 1), `parse_save`, `load_floor_saves` pattern from `tools/converge_triage.py:68`.
- Produces: a per-floor reconciliation table (probe stdout) that later tasks and the GAP-QUEUE rewrite cite; the final-floor resync rule in `_check_floor_state`.

- [ ] **Step 1: Write the probe**

Create `tools/oracle_semantics_probe.py`:

```python
r"""Reconcile the three 933T player-state oracles floor by floor.

For each floor F with a backup save, print one row:

  F | backup hp/gold/Shuffle | history[F] hp/gold | history[F-1] hp/gold
    | entry-arith hp (history[F].current_hp + damage_taken - hp_healed)

Alignment verdicts this table settles, per floor:
  backup==history[F]      -> backup captured POST-room-resolve state
  backup==history[F-1]    -> backup captured room-ENTRY state
  backup==entry-arith[F]  -> backup captured room-ENTRY state (same thing,
                             derived when F-1 is a rest/shop that healed)
  none of the above       -> mid-room capture or a divergent recording; flag.

Run:  py tools/oracle_semantics_probe.py
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
_DESKTOP = _REPO.parent

from sts2_rl.conformance.save import parse_save

REC = _DESKTOP / "RunReplays" / "RunReplays" / "Resources"
BK = (_DESKTOP / "sts2-run-backups" / "20260723-125401"
      / "933T39V18D-recording")

end = parse_save(REC / "933T39V18D" / "floor_49" / "run.save")

# Flatten map_point_history to absolute floors. Points are per act in walk
# order; absolute floor = 1 + points resolved before this one (Neow seeds
# total_floor to 1 — verify the offset against the known series: act 0 point 0
# must land on the floor whose backup hp is 80/76/74...).
flat = {}
floor = 1
for act_row in end.room_stats_by_act:
    for st in act_row:
        flat[floor] = st
        floor += 1

from sts2_rl.rng import RunRngType

print(f"{'F':>3} | {'backup hp':>9} {'gold':>5} {'Shuffle':>7} | "
      f"{'hist[F] hp':>10} {'gold':>5} | {'hist[F-1] hp':>12} | {'entry-arith':>11} | verdict")
for p in sorted(BK.glob("floor_*")):
    f = int(p.name.split("_")[1])
    if not (p / "run.save").exists():
        continue
    b = parse_save(p / "run.save")
    cur, prev = flat.get(f), flat.get(f - 1)
    arith = (cur.current_hp + cur.damage_taken - cur.hp_healed) if cur else None
    verdict = []
    if cur and b.player_current_hp == cur.current_hp:
        verdict.append("POST")
    if prev and b.player_current_hp == prev.current_hp:
        verdict.append("ENTRY(prev)")
    if arith is not None and b.player_current_hp == arith:
        verdict.append("ENTRY(arith)")
    print(f"{f:>3} | {b.player_current_hp:>9} {b.gold:>5} "
          f"{b.run_counters[RunRngType.SHUFFLE]:>7} | "
          f"{cur.current_hp if cur else '-':>10} "
          f"{cur.current_gold if cur else '-':>5} | "
          f"{prev.current_hp if prev else '-':>12} | "
          f"{arith if arith is not None else '-':>11} | "
          f"{'+'.join(verdict) or 'NONE'}")
```

Note: if `RunRngType.SHUFFLE` is not the member name, check `sts2_rl/rng.py` for the exact enum member (the save counter key is `shuffle`) and use that.

- [ ] **Step 2: Run the probe and classify**

Run: `py tools/oracle_semantics_probe.py`
Read the verdict column over all ~46 usable floors. Expected outcome: a dominant pattern (POST or ENTRY) with a small set of exceptional floors — floors 47–49 among them. Record the table in the task report verbatim.

- [ ] **Step 3: Apply the decision table to every residual 933T signal**

For each signal from Task 0's baseline, using the probe table plus DETECTOR 5 output from Task 1:

| evidence | class | action |
|---|---|---|
| backup save at floor F disagrees with BOTH history points and arithmetic; sim agrees with history | capture artifact in the backup | exclude/re-pin that floor's oracle (Step 4) |
| backup follows the dominant alignment but sim disagrees with backup AND history | **real gap** | goes to Task 4 |
| divergence exists only in the resync-ON arm and traces to a resync pin (e.g. floor-47 pin to 74 cascading into floors 48–49 and the run-end counters) | harness artifact | fixed by Step 4's oracle/final-floor rules; verify by re-running triage |
| DETECTOR 3 act-2 HP (67 vs 80) persists with resync OFF | **real gap** | Task 4 (note: the resync-OFF gate is green today, so this should NOT happen; if it does, the gate test has a hole — report it) |
| final act-2 history point `current_hp: 0` vs end-save 67 | capture semantics of the boss/death point | document in the probe docstring; DETECTOR 5 must skip or special-case the final boss point accordingly (small patch to `_check_room_stats`: compare only when the point's stats are internally consistent, i.e. `current_hp + damage_taken - hp_healed` reachable from the previous point) |

- [ ] **Step 4: Implement the harness fixes chosen by the table (TDD)**

Two known-required pieces regardless of classification details:

**(a) Final-floor resync rule.** In `_check_floor_state` (`sts2_rl/conformance/runner.py` — currently ~line 713 `if not resync_floors: return`), skip *resync* (diff still recorded) on the final checkpointed floor, where the entry-style backup pin fights the run-end capture:

```python
        if not resync_floors:
            return
        if floor == max(floor_saves):
            # Final checkpointed floor: the backup pin (room-entry capture)
            # would overwrite state the whole-run END capture is about to be
            # diffed against — the resynced arm could then never converge
            # (GAP-QUEUE `resync_floors`, resolved 2026-08-03 by
            # tools/oracle_semantics_probe.py).
            return
```

Failing test first — append to `test/test_conformance_floor_state.py`:

```python
def test_resync_skips_the_final_checkpointed_floor():
    """The final floor's backup save is an entry-style capture; pinning to it
    right before the whole-run END comparison guarantees a phantom divergence
    (GAP-QUEUE resync_floors item). The diff is still recorded; only the
    resync is skipped."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    b = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=_floor_saves(), resync_floors=True)
    # The run-end stream counters must now match exactly as they do in the
    # unresynced gate — the final-floor pin was the sole source of the
    # Shuffle 892-vs-909 phantom.
    assert [d for d in result.combat_divergences if d.command_index == -1] == []
```

Run it (expect FAIL before the fix, PASS after).

**(b) Per-floor oracle exclusions**, if Step 3 classified specific backup floors as mid-room/inconsistent captures: extend `_is_stale_floor_save` — or add a sibling `_is_inconsistent_floor_save` with the arithmetic consistency check from the decision table — with a docstring quoting the probe rows that justify each exclusion. One failing test per excluded floor asserting the floor no longer produces a phantom `floor_hp` divergence.

- [ ] **Step 5: Re-run triage until the only remaining signals are class real-gap**

```
py tools/converge_triage.py 933T39V18D floor_49 2   # x2, identical
py tools/converge_triage.py 89U21BV1TZ floor_49 2   # x2, identical
```
Expected: 89U still `FULLY CONVERGED`. 933T: every DETECTOR 2/3/4 artifact signal gone; output is either `FULLY CONVERGED` (→ Task 4 collapses to verification) or a short list of real-gap signals each localized to one room by DETECTOR 5.

- [ ] **Step 6: Resolve the GAP-QUEUE `resync_floors` items**

Rewrite the standing-lesson bullet beginning `**`resync_floors` now DEGRADES a converged replay...**` to state the resolution (final-floor resync skipped; which floors excluded and why; cite `tools/oracle_semantics_probe.py` and the new tests). Rewrite the "Per-room state oracles are unbuilt" bullet to past tense citing DETECTOR 5 (`runner.py` `_check_room_stats`). Then:

```
py audit/tools/gap_queue.py coverage && py audit/tools/gap_queue.py cite-check
```

- [ ] **Step 7: Full suite, no regression; stage**

```
py -m pytest test/ -q
git add tools/oracle_semantics_probe.py sts2_rl/conformance/runner.py test/test_conformance_floor_state.py audit/GAP-QUEUE.md
```

---

### Task 4: Real-gap bisection and engine fix (conditional)

Only runs if Task 3 Step 5 left real-gap signals. If 933T printed `FULLY CONVERGED` on both arms, do Step 6 only.

**Files:**
- Modify: whatever `sts2_rl/**` file the bisection implicates (unknown until diagnosed)
- Modify: the implicated `audit/records/<kind>/<unit>.json` + `audit/GAP-QUEUE.md`
- Test: a new `strict=True`-style pin next to the fix (module chosen by the implicated seam/kind; combat mechanics pins live in `test/test_hook_order.py` — seam-tier-owned, so a combat-seam pin goes there; content-anchored pins get a class in the fix's own test module, following the `TestPotionContentPins` precedent)

**Interfaces:**
- Consumes: DETECTOR 5 room localization + DETECTOR 2b `move_divs` (per-command Hand/Enemies mismatches) from `ReplayRunner`.
- Produces: engine fix + pin test + corrected audit record(s).

- [ ] **Step 1: Localize.** For each real-gap signal, take the room DETECTOR 5 names, re-run triage, and list DETECTOR 2b's earliest per-command mismatch inside that room. The recording's per-command `Hand:`/`Enemies:` annotations give the exact command index where sim and game part ways.

- [ ] **Step 2: Diagnose against the decompiled source.** Read only the implicated units under `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\` (the fight's monsters in `Models\Monsters\`, cards in `Models\Cards\`, the relevant `Commands\*.cs`). Follow `superpowers:systematic-debugging`. Known signature hint from the baseline (`Shuffle -17`, `CombatCardSelection +1`, `CombatTargets ±1`): one auto-play/card-AI branch — check `should_play_card` implementers and the `CombatCardSelection`/`CombatTargets` draw sites first. Treat as hypothesis, not conclusion.

- [ ] **Step 3: TDD the fix.** Failing unit test reproducing the divergent mechanic in isolation (constructed combat state, not the full replay); minimal engine fix; test passes; full suite green.

- [ ] **Step 4: Re-run triage** (both seeds × both arms, twice each). Expected: `FULLY CONVERGED` everywhere, or return to Step 1 for the next signal.

- [ ] **Step 5: Correct the audit ledger.** A real gap that survived a "0 live" queue proves a wrong verdict. Find the record that covered the mechanism (`py audit/tools/gap_queue.py refs <mechanism>` or grep `audit/records/` for the unit); determine whether it was a wrong `faithful` or a wrong `dormant`; update the record's entry (verdict, `issue`, `live` key), add the mechanism's section to `GAP-QUEUE.md` marked closed-by-this-fix (or file-and-close in one edit per the queue's "closed mechanisms are deleted" rule — i.e. file the corrected verdict in the record and do NOT add a queue section if the fix already landed), and run `coverage` + `cite-check`. Record in the task report which verdict class failed — it calibrates trust in the remaining 347 dormant labels.

- [ ] **Step 6: Write the adjudication summary.** Append to the baseline doc from Task 0: every baseline signal → its class (capture-semantics / harness-artifact / real-gap) → its resolution, one line each. This is the artifact that makes "the residue is settled" checkable later.

- [ ] **Step 7: Stage** all touched files.

---

### Task 5: One shared `converged` predicate + hard suite gates

The failure mode being closed: the suite was green while triage printed `DIVERGENCES REMAIN`, because the gate asserted a subset of the predicate. After this task the tool and the tests share one definition.

**Files:**
- Create: `sts2_rl/conformance/triage.py`
- Modify: `tools/converge_triage.py` (use the shared predicate)
- Test: `test/test_conformance_hard_gates.py` (new)

**Interfaces:**
- Consumes: `ReplayResult` (fields: `divergences`, `combat_divergences`, `forced_combats`, `unresolved_play_card_ids`), `Tripwire` (`sts2_rl/conformance/tripwire.py`, `.bug_sites()`).
- Produces: `assess(result, tripwire_bug_sites=None) -> Verdict` where `Verdict(clean: bool, reasons: list[str])` — imported by both the tool and the gate tests.

- [ ] **Step 1: Write the failing predicate test**

Create `test/test_conformance_hard_gates.py`:

```python
"""The hard gates: triage's `converged` predicate, asserted by the suite for
both Ironclad seeds, both resync arms. `sts2_rl.conformance.triage.assess` is
the ONE definition of converged — `tools/converge_triage.py` prints it and
these tests assert it, so the tool and the suite cannot disagree.

The four other-character seeds are permanently out of scope here (Ironclad-only
sim; see test_conformance_player_state.py's xfail table)."""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.recording import parse_recording
from sts2_rl.conformance.runner import ReplayRunner
from sts2_rl.conformance.save import parse_save
from sts2_rl.conformance.triage import assess

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
BK = Path(r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording")
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")

IRONCLAD_SEEDS = ["89U21BV1TZ", "933T39V18D"]


def test_assess_flags_each_component():
    from sts2_rl.conformance.comparators import Divergence
    from sts2_rl.conformance.runner import ReplayResult

    r = ReplayResult(divergences=[], rooms_walked=0, reached_act_end=True,
                     stopped_reason="", forced_combats=0)
    assert assess(r).clean
    r.forced_combats = 2
    v = assess(r)
    assert not v.clean and any("forced_combats" in s for s in v.reasons)
    r.forced_combats = 0
    r.divergences.append(Divergence("room_hp", 12, 66, 74, ""))
    assert not assess(r).clean
    r.divergences.clear()
    assert not assess(r, tripwire_bug_sites={("run.py", 1, "f", ""): 3}).clean
```

(Adjust the `ReplayResult` constructor args to its real required fields — read the dataclass at `sts2_rl/conformance/runner.py:176` and pass the minimal set.)

- [ ] **Step 2: Run; expect FAIL** (`No module named 'sts2_rl.conformance.triage'`)

- [ ] **Step 3: Implement `sts2_rl/conformance/triage.py`**

```python
"""The single definition of `converged` for a conformance replay.

`tools/converge_triage.py` prints this verdict; `test/test_conformance_hard_gates.py`
asserts it. Change it in ONE place or the tool and the suite start disagreeing
again — which is the historical failure this module closes."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Verdict:
    clean: bool
    reasons: list[str] = field(default_factory=list)


def assess(result, tripwire_bug_sites=None) -> Verdict:
    reasons: list[str] = []
    if result.forced_combats:
        reasons.append(f"forced_combats={result.forced_combats}")
    if result.unresolved_play_card_ids:
        reasons.append(f"unresolved_play_card_ids={result.unresolved_play_card_ids}")
    stream = [d for d in result.combat_divergences if d.command_index == -1]
    moves = [d for d in result.combat_divergences if d.command_index != -1]
    if stream:
        reasons.append(f"{len(stream)} stream counter diff(s): "
                       + ", ".join(d.stream for d in stream))
    if moves:
        reasons.append(f"{len(moves)} per-command mismatch(es), first: {moves[0]}")
    for prefix, label in (("player_", "act-boundary player state"),
                          ("floor_", "per-floor state"),
                          ("room_", "per-room state")):
        divs = [d for d in result.divergences if d.stream.startswith(prefix)]
        if divs:
            reasons.append(f"{len(divs)} {label} delta(s), first: {divs[0]}")
    if tripwire_bug_sites:
        reasons.append(f"{len(tripwire_bug_sites)} unseeded in-combat draw site(s)")
    return Verdict(not reasons, reasons)
```

Caveat: `player_` also prefixes nothing else in `divergences` except `player_hp`/`player_max_hp`; map/nav streams (`map_point_type`, `runner`) are covered transitively — a map desync forces combats or stops the run, both already flagged. State this in the module docstring if you verify it; otherwise add those streams explicitly.

- [ ] **Step 4: Rewire `tools/converge_triage.py`** — replace the inline `clean = (...)` expression:

```python
    from sts2_rl.conformance.triage import assess
    verdict = assess(result, tripwire_bug_sites=bugs)
    print(f"\n=== {'FULLY CONVERGED' if verdict.clean else 'DIVERGENCES REMAIN'} ===")
    for r in verdict.reasons:
        print(f"    {r}")
```

- [ ] **Step 5: Add the gate tests (same file)**

```python
def _floor_saves_for(seed):
    roots = {"933T39V18D": BK, "89U21BV1TZ": REC / "89U21BV1TZ"}
    return {int(p.name.split("_")[1]): parse_save(p / "run.save")
            for p in roots[seed].glob("floor_*") if (p / "run.save").exists()}


def _act_checkpoints(seed):
    ck = {}
    for act, fl in {0: "floor_18", 1: "floor_34", 2: "floor_49"}.items():
        f = REC / seed / fl / "run.save"
        if f.exists():
            o = parse_save(f)
            ck[act] = (o.player_current_hp, o.player_max_hp)
    return ck


def _replay(seed, resync):
    import sts2_rl.run as run_mod
    from sts2_rl.conformance.tripwire import Tripwire
    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    tw = Tripwire()
    orig = run_mod.RunState.__init__

    def patched(self, *a, **kw):
        orig(self, *a, **kw)
        tw.install(self.rng)

    run_mod.RunState.__init__ = patched
    try:
        result = ReplayRunner(rec, oracle).run(
            stop_after_act=2,
            player_checkpoints=_act_checkpoints(seed),
            resync_player=resync,
            floor_saves=_floor_saves_for(seed) if resync else None,
            resync_floors=resync,
            check_room_stats=True)
    finally:
        run_mod.RunState.__init__ = orig
    return result, tw


@pytest.mark.parametrize("seed", IRONCLAD_SEEDS)
@pytest.mark.parametrize("resync", [False, True], ids=["resync-off", "resync-on"])
def test_ironclad_seed_fully_converged(seed, resync):
    """THE hard gate: the full triage predicate, no skips, no xfails."""
    result, tw = _replay(seed, resync)
    v = assess(result, tripwire_bug_sites=tw.bug_sites())
    assert v.clean, "\n".join(v.reasons)
```

(If `run()` rejects `floor_saves=None`, pass `{}` — check the signature.)

- [ ] **Step 6: Run the gates**

Run: `py -m pytest test/test_conformance_hard_gates.py -v`
Expected: 4 passed (2 seeds × 2 arms). These MUST pass without marks — if any fails, Tasks 3/4 are not actually done; go back.

- [ ] **Step 7: Prove the gate bites**

Temporarily revert one Task-3 harness fix (e.g. comment out the final-floor resync skip), run the gate file, confirm `933T…resync-on` FAILS, restore. Note the check in the task report.

- [ ] **Step 8: Full suite, no regression; stage**

```
py -m pytest test/ -q
git add sts2_rl/conformance/triage.py tools/converge_triage.py test/test_conformance_hard_gates.py
```

---

### Task 6: Stale-sweep classifier — `audit/tools/stale_triage.py`

For each stale record, decide mechanically whether its cited evidence actually moved. Class (a): every cited line span is byte-identical at the same line numbers in the current file → eligible for fast re-audit. Class (b): anything else → full agent re-audit. Receipts make the split auditable — "looks unchanged" is not a class-(a) criterion, byte-identical is.

**Files:**
- Create: `audit/tools/stale_triage.py`
- Test: `test/test_stale_triage.py` (new)

**Interfaces:**
- Consumes: record JSON shapes (`game_source`/`sim_source` singular, `game_sources`/`sim_sources` plural, `extra_sources`), the hash normalization in `audit/tools/harness.py` (import it — reuse, do not re-implement; load by path with `importlib` since `audit/tools` is not a package: see how `audit/tools/gap_queue.py` locates its siblings and copy that mechanism), citation parsing from `audit/tools/citation_check.py` (same import mechanism).
- Produces: `py audit/tools/stale_triage.py [--kind K]` → writes `audit/stale-sweep/receipts.json` + prints summary; `classify_record(record: dict, repo_root: Path) -> dict` (pure-ish, testable). Receipt schema per record: `{"unit": str, "class": "a"|"b", "files": [{"path": str, "side": "game"|"sim", "recorded_sha": str, "current_sha": str, "historical_found": bool, "spans": [{"cite": "file:NN-MM", "identical": bool}]}], "reason": str}`.

- [ ] **Step 1: Write the failing tests**

Create `test/test_stale_triage.py`:

```python
"""stale_triage classifies stale audit records: class (a) = every cited line
span byte-identical at the same line numbers vs the text the record's hash was
taken over; class (b) = anything else. Receipts, not vibes."""
from pathlib import Path
import importlib.util

_TOOL = Path(__file__).resolve().parents[1] / "audit" / "tools" / "stale_triage.py"
spec = importlib.util.spec_from_file_location("stale_triage", _TOOL)
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)


def test_spans_identical_true_for_same_lines():
    old = "a\nb\nc\nd\n"
    new = "a\nb\nc\nd\nE\n"          # append-only
    assert st.span_identical(old, new, 2, 3)      # lines 2-3 = "b","c"


def test_spans_identical_false_when_lines_moved():
    old = "a\nb\nc\n"
    new = "X\na\nb\nc\n"             # same content, shifted one line
    assert not st.span_identical(old, new, 2, 3)


def test_classify_all_spans_identical_is_class_a():
    rec = {"unit": "relic/example",
           "sim_source": {"path": "sts2_rl/x.py", "sha256": "S"},
           "hooks": {"H": {"verdict": "faithful", "maps_to": "sts2_rl/x.py:2-3"}}}
    texts = {("sts2_rl/x.py", "S"): "a\nb\nc\nd\n"}
    current = {"sts2_rl/x.py": "a\nb\nc\nd\nE\n"}
    out = st.classify_record(rec, historical=texts.get, current=current.get)
    assert out["class"] == "a"


def test_classify_missing_historical_text_is_class_b():
    rec = {"unit": "relic/example",
           "sim_source": {"path": "sts2_rl/x.py", "sha256": "NOPE"},
           "hooks": {}}
    out = st.classify_record(rec, historical=lambda k: None,
                             current={"sts2_rl/x.py": "a\n"}.get)
    assert out["class"] == "b"
    assert "historical" in out["reason"]
```

- [ ] **Step 2: Run; expect FAIL** (file does not exist)

Run: `py -m pytest test/test_stale_triage.py -v`

- [ ] **Step 3: Implement `audit/tools/stale_triage.py`**

Core pieces (write in full; ~150 lines):

```python
r"""Classify stale audit records for the 2026-08-03 stale sweep.

Class (a): the record's hash went stale but every file:line citation it
carries is BYTE-IDENTICAL at the SAME line numbers in the current tree —
the pin-append precedent (README 'The 28 entries...') generalized. These get
the fast re-audit: verify receipt, then `harness.py rehash <unit>`.
Class (b): any span changed, moved, or the hashed historical text cannot be
recovered from git — full agent re-audit.

Usage: py audit/tools/stale_triage.py [--kind relic] [--out audit/stale-sweep/receipts.json]
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# --- reuse the harness's normalization + staleness, and citation_check's
# citation regex, via importlib (audit/tools is not a package) ---
import importlib.util
def _load(name):
    p = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
harness = _load("harness")            # for the normalize/hash helpers
citation_check = _load("citation_check")   # for the file:line regex + record walking


def span_identical(old_text: str, new_text: str, lo: int, hi: int) -> bool:
    """Lines lo..hi (1-based, inclusive) byte-identical at the same numbers."""
    old = old_text.splitlines()
    new = new_text.splitlines()
    if hi > len(old) or hi > len(new):
        return False
    return old[lo - 1:hi] == new[lo - 1:hi]


_BLOB_CACHE: dict[tuple[str, str], str | None] = {}

def historical_text(path: str, want_sha: str) -> str | None:
    """Recover the file text a record's sha256 was computed over, by walking
    this path's git history and hashing each blob with the harness's own
    normalization. None if no commit matches (uncommitted state -> class b)."""
    key = (path, want_sha)
    if key in _BLOB_CACHE:
        return _BLOB_CACHE[key]
    revs = subprocess.run(
        ["git", "rev-list", "HEAD", "--", path],
        cwd=REPO, capture_output=True, text=True).stdout.split()
    found = None
    for rev in revs:
        show = subprocess.run(["git", "show", f"{rev}:{path}"],
                              cwd=REPO, capture_output=True, text=True)
        if show.returncode != 0:
            continue
        if harness_normalized_sha(show.stdout) == want_sha:
            found = show.stdout
            break
    _BLOB_CACHE[key] = found
    return found
```

`harness_normalized_sha` must call the exact helper `harness.py` uses (grep it: `grep -n "sha256\|def _hash\|def file_hash" audit/tools/harness.py`) so normalization matches. Sim paths resolve against `REPO`; game paths against the game root `SEAM_SOURCES`/records use (read how `citation_check.py` resolves `side: game` paths and reuse it — the game tree is not in git, but the game source is frozen, so for `side: game` files skip blob recovery and only verify `current_sha == recorded_sha`; a mismatched game hash is class (b) with reason `game-source-changed`, expected count 0).

`classify_record(rec, historical, current)`: walk every source entry (singular pair, plural lists, `extra_sources`), skip `_NEVER_HASHED` paths (`test/`, `audit/tools/` — import the constant from `citation_check`), collect every `file:line`/`file:lo-hi` citation in the record's JSON strings (citation_check's regex), group citations by file, and emit the receipt dict. Class (a) requires: every hashed sim file's historical text recovered AND every citation span `span_identical` AND every hashed game file's current hash equal to recorded. `main()`: iterate `audit/records/<kind>/*.json` (all kinds or `--kind`), classify only records `audit_status` reports stale (import its staleness check the same importlib way), write receipts JSON, print `class a: N, class b: M` per kind.

- [ ] **Step 4: Run unit tests; expect PASS**

Run: `py -m pytest test/test_stale_triage.py -v` → 4 passed.

- [ ] **Step 5: Run the real classification**

Run: `py audit/tools/stale_triage.py`
Expected: a receipts file at `audit/stale-sweep/receipts.json` and a per-kind a/b split. Sanity checks: total classified == stale count from `audit_status.py`; spot-check 3 class-(a) receipts by hand (open the record, open the file, confirm the cited lines really are unchanged); spot-check 1 class-(b) receipt the same way. Record the split in the task report — it sizes Task 8.

- [ ] **Step 6: Stage**

```
git add audit/tools/stale_triage.py test/test_stale_triage.py audit/stale-sweep/receipts.json
```

---

### Task 7: Class (a) fast re-audit + rehash

**Files:**
- Modify: every class-(a) record under `audit/records/**` (hash re-pin only, via `harness.py rehash`)
- Create: `audit/stale-sweep/SWEEP-REPORT.md`

**Interfaces:**
- Consumes: `audit/stale-sweep/receipts.json` (Task 6), `py audit/tools/harness.py rehash <unit> [--dry-run]`.
- Produces: stale count reduced to the class-(b) population; the sweep report Task 8 appends to.

- [ ] **Step 1: Dry-run the rehash for every class-(a) unit**

Script it (one-off, in the scratchpad, not the repo): read `receipts.json`, for each `"class": "a"` unit run `py audit/tools/harness.py rehash <unit> --dry-run`, capture output. Expected: each dry run re-pins ONLY hashes, no verdict fields. Any unit whose dry-run output looks like more than a hash re-pin → demote to class (b) in the receipts (edit the JSON, note why).

- [ ] **Step 2: Execute the rehash**

Same loop without `--dry-run`. This is legitimate (not "decoration") **because** the receipt proves the cited evidence is byte-identical — the re-audit happened mechanically in Task 6; say exactly that in SWEEP-REPORT.md, citing the README's pin-append precedent.

- [ ] **Step 3: Verify**

```
py audit/tools/audit_status.py
py audit/tools/harness.py validate
```
Expected: stale == class-(b) count from Task 6 (plus any Task 1–5 sim edits' newly-staled records — those files (`runner.py`, `save.py`) are hashed by conformance-adjacent records, count them explicitly); validate exits 0.

- [ ] **Step 4: Write `audit/stale-sweep/SWEEP-REPORT.md`** — date, receipts pointer, counts before/after, the demotions from Step 1, and the exact commands run.

- [ ] **Step 5: Full suite green; stage**

```
py -m pytest test/ -q
git add audit/records audit/stale-sweep
```

---

### Task 8: Class (b) re-audit campaign (subagent batches)

Full agent re-audits for every record whose cited evidence actually changed. Batched by kind, dispatched as parallel read-only subagents per the established stream pattern.

**Files:**
- Modify: class-(b) records under `audit/records/<kind>/**` (verdict revisions + rehash, per batch)
- Modify: `audit/GAP-QUEUE.md` (once, at the end)
- Modify: `audit/stale-sweep/SWEEP-REPORT.md` (append per-batch results)

**Interfaces:**
- Consumes: receipts.json class-(b) list; `audit/prompts/_shared-audit-contract.md` (binding); `audit/tools/PROMPT.md` (bug-class checklist).
- Produces: 0 stale records; revised verdicts; new gap entries (queued, dormant unless proven live).

- [ ] **Step 1: Batch the class-(b) list** by kind, ~25 records per batch. Within one wave, batches must own disjoint `records/<kind>/` slices (the ownership rule that made prior campaigns merge trivially).

- [ ] **Step 2: Dispatch each batch to a subagent with this brief** (fill the placeholders per batch):

```
Re-audit these stale audit records: <unit list>.
Binding contract: audit/prompts/_shared-audit-contract.md and audit/tools/PROMPT.md.
For each record:
  1. Read the receipt for this unit in audit/stale-sweep/receipts.json — it
     names exactly which cited files/spans changed.
  2. Re-read the changed sim source against the C# it is verdicted on.
  3. Confirm or REVISE each affected verdict (hooks, guards, rollup). Rules:
     a wrong `faithful` becomes a `gap` with an `issue`; dormancy claims must
     name the concrete unported trigger; state `live:` as data on every new
     gap entry, and name WHICH driver path (RL vs conformance-replay) it is
     live on.
  4. LAST step only, after verdicts are settled:
     py audit/tools/harness.py rehash <unit>
Never edit sts2_rl/**, audit/tools/**, or another batch's records.
If you find a LIVE gap: STOP the batch, report it immediately — a live find
contradicts the green conformance gates and must be reconciled, not queued.
Report per unit: verdict changes (old -> new), new gap entries filed, or
"confirmed unchanged".
```

- [ ] **Step 3: After each wave**: `py audit/tools/harness.py validate` (exit 0), `py audit/tools/audit_status.py` (stale count strictly decreasing), spot-check one revised record per batch against its sources. Append results to SWEEP-REPORT.md.

- [ ] **Step 4: If any batch reported a live gap** — reconcile before continuing: reproduce it on the conformance path (does a gate fail? does triage flag it?); if it is genuinely live on a path the gates cover, it goes through Task 4's fix workflow; if live only on the RL-training path (no `string_seed`), file it `live: true` with the path named and continue (the gates don't claim that path).

- [ ] **Step 5: Regenerate `GAP-QUEUE.md`** for all new/changed entries (sections keyed by mechanism id; closed mechanisms deleted), then:

```
py audit/tools/gap_queue.py counts
py audit/tools/gap_queue.py coverage
py audit/tools/gap_queue.py cite-check
```
All exit 0; `counts` is the new ledger truth (record it in SWEEP-REPORT.md).

- [ ] **Step 6: Stage** — `git add audit/records audit/GAP-QUEUE.md audit/stale-sweep`

---

### Task 9: Final verification

**Files:**
- Modify: `audit/README.md` (Status section), `audit/stale-sweep/SWEEP-REPORT.md` (closing summary), `docs/superpowers/plans/2026-08-03-ironclad-fidelity-closure-baseline.md` (final numbers beside baseline numbers)

- [ ] **Step 1: The audit ledger is current**

```
py audit/tools/audit_status.py
py audit/tools/harness.py validate
```
Expected: **stale 0, invalid 0** on every kind; validate exit 0. (`--strict` still exits 1 on the queued dormant gaps — that is by design; the criterion is the stale and invalid columns, checked on the table output.)

- [ ] **Step 2: The queue is coherent**

```
py audit/tools/gap_queue.py counts && py audit/tools/gap_queue.py coverage && py audit/tools/gap_queue.py cite-check
```
All exit 0; live count is 0 unless Task 8 Step 4 filed RL-path-only lives (each naming its path).

- [ ] **Step 3: Both Ironclad seeds converge, deterministically**

```
py tools/converge_triage.py 89U21BV1TZ floor_49 2     # x3
py tools/converge_triage.py 933T39V18D floor_49 2     # x3
```
Expected: `FULLY CONVERGED` — six of six runs, all detectors, both arms.

- [ ] **Step 4: The full suite is green and the gates are load-bearing**

```
py -m pytest test/ -q
py -m pytest test/test_conformance_hard_gates.py -v
```
Expected: no regression vs Task 0 baseline count (plus the new tests); 4/4 hard gates passed with zero marks.

- [ ] **Step 5: Update `audit/README.md`'s Status section** — one short paragraph: sweep date, receipts location, the standing "re-run the commands, don't trust prose" caveat retained.

- [ ] **Step 6: Stage everything; hand the staged tree to Perry to commit.**

```
git add -A audit docs tools sts2_rl test
git status
```

---

## Self-review notes (kept for the executor)

- **Spec coverage:** Phase 1 → Tasks 0–4 (instrument: Tasks 1–2; resync semantics + adjudication: Task 3; real-gap fix + ledger correction: Task 4). Phase 2 → Task 5. Phase 3 → Tasks 6–8. Spec's verification section → Task 9 + per-task suite runs. Spec non-goals honored: no new replay capture, no dormant-queue drain (Task 8 only *files*, except lives), other characters untouched.
- **Known uncertainty, by design:** Task 3's decision table and Task 4's fix cannot be pre-written — they are evidence-gated procedures with explicit stop conditions, which is the point of fixing the instrument first. Task 5 Step 6 is the checkpoint that refuses to proceed while any residue stands.
- **Type consistency:** `RoomStats`/`room_stats_by_act`/`check_room_stats`/`room_*` streams (Task 1) are consumed by Tasks 3 and 5 under those exact names; `assess`/`Verdict` (Task 5) consumed by the tool and gates; `span_identical`/`classify_record`/receipt schema (Task 6) consumed by Task 7's scripts and Task 8's brief.
