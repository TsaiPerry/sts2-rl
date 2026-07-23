# SP3 Player-State Parity (DETECTOR 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make player HP/max-HP a first-class asserted oracle in the conformance harness, grant the missing starting relic, and drive every recording's full run to completion with player state matching `run.save` at each floor boundary.

**Architecture:** Three isolated additions plus one content fix. (1) `RunState.start_run` grants the character's starting relic (`burning_blood`) — the verified dominant HP bug. (2) `SaveOracle` parses the player's `current_hp`/`max_hp`. (3) The runner asserts player state at act boundaries against per-act checkpoints built from the sibling `floor_18/34/49` saves, with an opt-in parity-only resync that pins sim HP/max-HP after asserting so one act's bug can't cascade. (4) `converge_triage.py` prints these as DETECTOR 3. Then converge all 5 seeds in aggregate.

**Tech Stack:** Python 3, `pytest`, the `sts2_rl.conformance` harness (SP2/SP3), the `py` launcher. Decompiled game source at `c:\Users\Perry\Desktop\Slay the Spire 2\src` is ground truth.

## Global Constraints

- **Never `git commit` or `git push`.** CLAUDE.md rule 4 + `[[sts2-no-auto-commit]]`: every "Stage" step means **`git add` the listed paths and stop** — do NOT run `git commit`. Perry reviews and commits.
- **`from __future__ import annotations`** at the top of every new/edited module; lazy imports inside methods to avoid circular imports, matching existing style.
- **Legacy path stays byte-for-byte EXCEPT the deliberate starter-relic fidelity fix.** The starter relic is granted in ALL runs (Perry's decision 2026-07-22) because the game always grants it (`[[original-means-game-source]]`); update the legacy tests that encoded the relic-less start. Everything else in a no-`string_seed` run is unchanged. The harness resync is parity-only.
- **Full suite command:** `py -m pytest test/ -q` (~3.5 min). **Baseline at HEAD: 2260 passed.** After Task 1 the count changes only by the starter-relic test updates; report the delta.
- **Fidelity to source** (`Slay the Spire 2\src`) is the golden rule; when a fix changes sim behavior to match the game, update legacy tests to the game-correct behavior.
- **Recordings live in** `c:\Users\Perry\Desktop\RunReplays\RunReplays\Resources\<SEED>\floor_{18,34,49}\{actions.sts2replay,run.save}` — 5 seeds × 3 floors. Each floor's `run.save` is that truncation's terminal snapshot (its `players[0].current_hp`/`max_hp` is the HP at that floor). Seeds: `89U21BV1TZ, DJDCSAQZNR, L081UMJX4M, QRWCVDPZN5, TZEKRYTSNT`.

---

## File structure

**Modified files**
- `sts2_rl/run.py` — `start_run` grants `burning_blood` (the starting relic).
- `sts2_rl/conformance/save.py` — `SaveOracle` gains `player_current_hp`, `player_max_hp`.
- `sts2_rl/conformance/comparators.py` — new `Divergence` stream-name constants for player state (documentation only; strings).
- `sts2_rl/conformance/runner.py` — `run()` gains `player_checkpoints` + `resync_player`; asserts/resyncs player state at act boundaries.
- `tools/converge_triage.py` — DETECTOR 3 (player-state deltas) + build checkpoints from sibling saves.

**New files**
- `test/test_conformance_player_state.py` — the new suite (oracle parse, assertion, resync, the 5-seed convergence gate).

---

## Task 1: Grant the starting relic in `start_run`

The run never grants the character's starting relic. Game source: `Core/Models/Characters/Ironclad.cs:57` (`StartingRelics => BurningBlood`), granted at `Core/Entities/Players/Player.cs:739 PopulateStartingRelics()` on player init. `sts2_rl/relics/burning_blood.py` already implements the +6-HP `on_combat_end` heal; it is simply never obtained. The `run.save` relic list confirms `RELIC.BURNING_BLOOD` at `floor_added_to_deck: 1` (before Neow relics).

**Files:**
- Modify: `sts2_rl/run.py` (`start_run`, ~line 573, at the top of the body)
- Test: `test/test_conformance_player_state.py` (create)

**Interfaces:**
- Consumes: `RunState.add_relic(relic_id: str) -> Relic` (run.py:477).
- Produces: after `RunState.start_run(...)`, `run.relics[0].id == "burning_blood"`.

- [ ] **Step 1: Write the failing test**

```python
# test/test_conformance_player_state.py
from __future__ import annotations

from sts2_rl.run import RunState


def test_start_run_grants_the_starting_relic_first():
    # Ironclad.cs:57 StartingRelics => BurningBlood, granted at run init
    # (Player.cs:739 PopulateStartingRelics), before any Neow relic.
    run = RunState(string_seed="89U21BV1TZ")
    run.start_run(acts=["overgrowth", "hive", "glory"], ascension=0)
    assert run.relics, "run should have at least the starting relic"
    assert run.relics[0].id == "burning_blood"
    assert sum(r.id == "burning_blood" for r in run.relics) == 1  # exactly once
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_conformance_player_state.py::test_start_run_grants_the_starting_relic_first -q`
Expected: FAIL — `AssertionError` (relics empty or `relics[0].id != "burning_blood"`).

- [ ] **Step 3: Write minimal implementation**

In `sts2_rl/run.py`, at the very top of `start_run`'s body (before the `if acts is None:` block, ~line 573), insert:

```python
        # Character starting relics (CharacterModel.StartingRelics, granted at
        # run init by Player.PopulateStartingRelics). This single-character sim
        # is Ironclad, whose only starting relic is Burning Blood
        # (Ironclad.cs:57). Granted in every run (the game always grants it);
        # heals 6 HP after each won combat (relics/burning_blood.py).
        if not any(r.id == "burning_blood" for r in self.relics):
            self.add_relic("burning_blood")
```

(The idempotence guard keeps a re-entered `start_run` or a run pre-seeded with the relic from double-granting.)

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_conformance_player_state.py::test_start_run_grants_the_starting_relic_first -q`
Expected: PASS.

- [ ] **Step 5: Run the conformance runner smoke check (the death is gone)**

Run:
```bash
py tools/converge_triage.py 89U21BV1TZ floor_18 0
```
Expected: still `FULLY CONVERGED` (RNG unaffected) — Burning Blood consumes no RNG.

Then confirm the act-2 death is gone:
```bash
py -c "from pathlib import Path; from sts2_rl.conformance.recording import parse_recording; from sts2_rl.conformance.runner import ReplayRunner; from sts2_rl.conformance.save import parse_save; b=Path.home()/'Desktop'/'RunReplays'/'RunReplays'/'Resources'/'89U21BV1TZ'/'floor_49'; r=ReplayRunner(parse_recording(b/'actions.sts2replay'), parse_save(b/'run.save')).run(stop_after_act=2); print(r.stopped_reason, r.rooms_walked)"
```
Expected: `reached act 2 boss 45` (was `player died 23`).

- [ ] **Step 6: Full suite — update legacy tests that encoded the relic-less start**

Run: `py -m pytest test/ -q`
Expected: A handful of failures in tests that asserted a run's starting relic set or starting behavior WITHOUT `burning_blood` (e.g. relic-count assertions, run-setup fixtures). For each: confirm the failure is *only* the newly-present starting relic, then update the expectation to the game-correct state (relic present). Do NOT weaken a test that catches an unrelated regression. Re-run until green. Report the new passing count vs the 2260 baseline.

- [ ] **Step 7: Stage (do NOT commit)**

```bash
git add sts2_rl/run.py test/test_conformance_player_state.py
# plus any legacy test files updated in Step 6
```

---

## Task 2: Parse player HP/max-HP into `SaveOracle`

**Files:**
- Modify: `sts2_rl/conformance/save.py` (`SaveOracle` dataclass + `parse_save`)
- Test: `test/test_conformance_player_state.py` (append)

**Interfaces:**
- Consumes: the `run.save` JSON `players[0].current_hp` / `players[0].max_hp` (verified present: e.g. `89U21BV1TZ/floor_18` → 56/71, `floor_34` → 51/93, `floor_49` → 33/111).
- Produces: `SaveOracle.player_current_hp: int`, `SaveOracle.player_max_hp: int`.

- [ ] **Step 1: Write the failing test**

```python
# append to test/test_conformance_player_state.py
from pathlib import Path
from sts2_rl.conformance.save import parse_save

REC = Path.home() / "Desktop" / "RunReplays" / "RunReplays" / "Resources"


def test_save_oracle_parses_player_hp():
    o = parse_save(REC / "89U21BV1TZ" / "floor_18" / "run.save")
    assert o.player_current_hp == 56
    assert o.player_max_hp == 71
    o49 = parse_save(REC / "89U21BV1TZ" / "floor_49" / "run.save")
    assert (o49.player_current_hp, o49.player_max_hp) == (33, 111)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_conformance_player_state.py::test_save_oracle_parses_player_hp -q`
Expected: FAIL — `AttributeError: 'SaveOracle' object has no attribute 'player_current_hp'`.

- [ ] **Step 3: Write minimal implementation**

In `sts2_rl/conformance/save.py`, add two fields to `SaveOracle` (after `player_counters`):

```python
    player_current_hp: int = 0
    player_max_hp: int = 0
```

In `parse_save`, after `prng = d["players"][0]["rng"]`, read them from the same player dict and pass into the `SaveOracle(...)` return:

```python
    player = d["players"][0]
    ...
    return SaveOracle(
        ...
        player_counters=player_counters,
        player_current_hp=player.get("current_hp", 0),
        player_max_hp=player.get("max_hp", 0),
        ...
    )
```

(`player` replaces the local you read `rng` from — `prng = player["rng"]`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_conformance_player_state.py::test_save_oracle_parses_player_hp -q`
Expected: PASS.

- [ ] **Step 5: Guard the SP2 save-parse suite**

Run: `py -m pytest test/ -q -k "save or conformance"`
Expected: PASS (existing save/conformance tests unaffected — pure additive fields).

- [ ] **Step 6: Stage (do NOT commit)**

```bash
git add sts2_rl/conformance/save.py test/test_conformance_player_state.py
```

---

## Task 3: Assert player state at act boundaries in the runner

Add player-state divergence reporting to `run()`. No resync yet (Task 4). Checkpoints are keyed by the act index that just completed: `{0: floor_18 hp, 1: floor_34 hp, 2: floor_49 hp}`.

**Files:**
- Modify: `sts2_rl/conformance/comparators.py` (add stream-name constants)
- Modify: `sts2_rl/conformance/runner.py` (`run()` signature + act-boundary check)
- Test: `test/test_conformance_player_state.py` (append)

**Interfaces:**
- Consumes: `RunState.hp: int`, `RunState.max_hp: int` (plain attributes, set in `finish_combat`); `Divergence(stream, command_index, expected, actual, detail)`.
- Produces: `ReplayRunner.run(stop_after_act=0, player_checkpoints: dict[int, tuple[int, int]] | None = None, resync_player: bool = False)`; player-state `Divergence`s in `result.divergences` with `stream` in `{"player_hp", "player_max_hp"}`, `command_index = act_index`.

- [ ] **Step 1: Add the stream-name constants**

In `sts2_rl/conformance/comparators.py`, near the `Divergence` class, add:

```python
# SP3 player-state parity: floor-boundary HP oracle (DETECTOR 3). command_index
# carries the completed act index; expected/actual are (hp) or (max_hp) ints.
PLAYER_HP_STREAM = "player_hp"
PLAYER_MAX_HP_STREAM = "player_max_hp"
```

- [ ] **Step 2: Write the failing test**

```python
# append to test/test_conformance_player_state.py
from sts2_rl.conformance.recording import parse_recording
from sts2_rl.conformance.runner import ReplayRunner


def test_runner_reports_player_hp_divergence_at_act_boundary():
    # With a checkpoint one HP off the sim's real floor-18 value, the runner
    # must emit a player_hp Divergence for the completed act (index 0).
    b = REC / "89U21BV1TZ" / "floor_18"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    runner = ReplayRunner(rec, oracle)
    # First get the sim's real floor-18 hp with a correct checkpoint (no div).
    base = runner.run(stop_after_act=0,
                      player_checkpoints={0: (oracle.player_current_hp,
                                              oracle.player_max_hp)})
    hp_divs = [d for d in base.divergences if d.stream == "player_hp"]
    # Now feed a deliberately wrong checkpoint and require a divergence.
    bad = ReplayRunner(rec, oracle).run(
        stop_after_act=0,
        player_checkpoints={0: (oracle.player_current_hp + 999,
                                oracle.player_max_hp)})
    bad_divs = [d for d in bad.divergences if d.stream == "player_hp"]
    assert len(bad_divs) == 1
    assert bad_divs[0].command_index == 0
    assert bad_divs[0].expected == oracle.player_current_hp + 999
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -m pytest test/test_conformance_player_state.py::test_runner_reports_player_hp_divergence_at_act_boundary -q`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'player_checkpoints'`.

- [ ] **Step 4: Implement — runner signature + helper**

In `sts2_rl/conformance/runner.py`, change the `run` signature (line 422):

```python
    def run(self, stop_after_act: int = 0,
            player_checkpoints: "dict[int, tuple[int, int]] | None" = None,
            resync_player: bool = False) -> ReplayResult:
```

Add a helper method on `ReplayRunner` (near `run`):

```python
    def _check_player_state(self, run, divergences, act_index,
                            player_checkpoints, resync_player) -> None:
        """Assert sim HP/max-HP against the completed act's floor snapshot
        (from the sibling run.save), then optionally resync so an act's bug
        can't cascade. Parity oracle only — no effect when checkpoints omit
        this act. Streams: player_hp / player_max_hp; command_index = act."""
        if not player_checkpoints or act_index not in player_checkpoints:
            return
        exp_hp, exp_max = player_checkpoints[act_index]
        if run.hp != exp_hp:
            divergences.append(Divergence(
                "player_hp", act_index, exp_hp, run.hp,
                f"act {act_index} boundary"))
        if run.max_hp != exp_max:
            divergences.append(Divergence(
                "player_max_hp", act_index, exp_max, run.max_hp,
                f"act {act_index} boundary"))
        if resync_player:
            run.hp = exp_hp
            run.max_hp = exp_max
```

- [ ] **Step 5: Implement — call it at the act boundary**

In `run()`, inside `if run.at_act_end:` (line 491), add the check as the FIRST statement (so the terminal act is checked before the `break`, and mid-run acts before `advance_act`):

```python
            if run.at_act_end:
                reached_act_end = True
                self._check_player_state(
                    run, divergences, run.act_index,
                    player_checkpoints, resync_player)
                if run.act_index >= stop_after_act:
                    reason = f"reached act {run.act_index} boss"
                    break
                run.advance_act()
                run.total_floor += 1
                driver._maybe_run_ancient()
                reached_act_end = False
```

(Leave the existing `run.total_floor += 1` and comment where they are; only the `_check_player_state` line is new.)

- [ ] **Step 6: Run the test**

Run: `py -m pytest test/test_conformance_player_state.py::test_runner_reports_player_hp_divergence_at_act_boundary -q`
Expected: PASS.

- [ ] **Step 7: Regression — existing conformance callers unaffected**

Run: `py -m pytest test/ -q -k conformance`
Expected: PASS (the new kwargs default to off; callers that don't pass checkpoints see no new divergences).

- [ ] **Step 8: Stage (do NOT commit)**

```bash
git add sts2_rl/conformance/comparators.py sts2_rl/conformance/runner.py test/test_conformance_player_state.py
```

---

## Task 4: Opt-in resync + build checkpoints from sibling saves

The resync is already implemented in `_check_player_state` (Task 3, Step 4). This task adds the checkpoint-builder helper and proves resync lets the whole run replay without a cascade death.

**Files:**
- Modify: `test/test_conformance_player_state.py` (append the helper + resync test)

**Interfaces:**
- Consumes: `parse_save`, `ReplayRunner.run(..., player_checkpoints, resync_player)`.
- Produces: test-local `player_checkpoints(seed) -> dict[int, tuple[int, int]]` reading the three sibling saves.

- [ ] **Step 1: Write the helper + failing test**

```python
# append to test/test_conformance_player_state.py
_ACT_FLOORS = {0: "floor_18", 1: "floor_34", 2: "floor_49"}


def player_checkpoints(seed: str) -> dict[int, tuple[int, int]]:
    """Per-act HP checkpoints from the three sibling truncation saves."""
    ck: dict[int, tuple[int, int]] = {}
    for act_index, floor in _ACT_FLOORS.items():
        f = REC / seed / floor / "run.save"
        if f.exists():
            o = parse_save(f)
            ck[act_index] = (o.player_current_hp, o.player_max_hp)
    return ck


def test_resync_lets_full_run_replay_without_cascade_death():
    seed = "89U21BV1TZ"
    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2,
        player_checkpoints=player_checkpoints(seed),
        resync_player=True)
    # The run reaches the act-2 boss; it does not die mid-run.
    assert result.stopped_reason == "reached act 2 boss"
    assert result.rooms_walked >= 45
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `py -m pytest test/test_conformance_player_state.py::test_resync_lets_full_run_replay_without_cascade_death -q`
Expected: PASS (Task 1's starter relic already lets 89U reach the act-2 boss; resync keeps it there and, on seeds where an act-1 residual would otherwise kill the player, prevents the cascade). If it FAILS with `player died`, that is a genuine remaining act-1 HP bug for this seed — record it for Task 6, do not weaken the test; temporarily `xfail` with a reason naming the seed.

- [ ] **Step 3: Stage (do NOT commit)**

```bash
git add test/test_conformance_player_state.py
```

---

## Task 5: DETECTOR 3 in `converge_triage.py`

Print per-act player-state deltas alongside DETECTOR 1/2, mapped to a likely source class, and pass checkpoints + resync so the tool exercises the full run.

**Files:**
- Modify: `tools/converge_triage.py`

**Interfaces:**
- Consumes: `parse_save`, `ReplayResult.divergences` (now carrying `player_hp`/`player_max_hp`).
- Produces: a `[DETECTOR 3]` block; the tool runs with resync on so later acts are reachable.

- [ ] **Step 1: Build checkpoints + pass them to the runner**

In `tools/converge_triage.py` `main()`, before `runner.run(...)`, build checkpoints from the sibling saves and pass them:

```python
    # DETECTOR 3: per-act HP checkpoints from the sibling truncation saves.
    _ACT_FLOORS = {0: "floor_18", 1: "floor_34", 2: "floor_49"}
    checkpoints = {}
    for act_index, fl in _ACT_FLOORS.items():
        f = REC / seed / fl / "run.save"
        if f.exists():
            o = parse_save(f)
            checkpoints[act_index] = (o.player_current_hp, o.player_max_hp)
```

Change the `runner.run(...)` call to:

```python
        result = runner.run(stop_after_act=stop_after_act,
                            player_checkpoints=checkpoints,
                            resync_player=True)
```

- [ ] **Step 2: Add the DETECTOR 3 printout**

After the DETECTOR 2 block (before DETECTOR 1), add:

```python
    # ---- DETECTOR 3: player-state deltas (HP / max-HP fidelity) ----
    hp_divs = [d for d in result.divergences
               if d.stream in ("player_hp", "player_max_hp")]
    print(f"\n[DETECTOR 3] player-state deltas at act boundaries: {len(hp_divs)}")
    _HP_SRC = {
        "player_hp": "damage/heal pipeline (DamageCmd/BlockCmd, relic heals "
                     "like BurningBlood on_combat_end, rest-site heal).",
        "player_max_hp": "max-HP-changing content (max-HP events, rest-site, "
                         "relics like Meat on the Bone / Black Blood).",
    }
    for d in hp_divs:
        delta = (d.actual - d.expected) if isinstance(d.actual, int) else "?"
        print(f"  act {d.command_index} {d.stream}: expected {d.expected} "
              f"got {d.actual} (sim {'high' if isinstance(delta,int) and delta>0 else 'low'} "
              f"by {abs(delta) if isinstance(delta,int) else delta})")
        print(f"      -> {_HP_SRC[d.stream]}")
```

Also update the `clean` line to include player state:

```python
    clean = (not bugs and not stream_divs and not move_divs and not hp_divs
             and result.forced_combats == 0
             and not result.unresolved_play_card_ids)
```

- [ ] **Step 3: Run it**

Run: `py tools/converge_triage.py 89U21BV1TZ floor_49 2`
Expected: prints `[DETECTOR 3]` with the max-HP (act 2 ≈ −34) and current-HP deltas; the run now reaches the act-2 boss (resync on). No traceback.

- [ ] **Step 4: Stage (do NOT commit)**

```bash
git add tools/converge_triage.py
```

---

## Task 6: Convergence — drive all 5 seeds' player state to green (the loop)

The long pole, in aggregate. With DETECTOR 3 and resync live, each act's HP/max-HP delta is isolated and reported for every seed in one pass. Fix each divergence class against source, re-run, repeat. This is a **repeatable procedure**, not a fixed code list — the recordings dictate which content diverges.

**Files:**
- Modify: `test/test_conformance_player_state.py` (add the parametrized gate)
- Modify: various `sts2_rl/` content modules as divergences dictate (events, relics, rest-site, damage pipeline, map/travel)

**The loop (repeat until green), priority order:**

1. **Map/runner stops first** — a seed whose `stopped_reason` is `"unreachable map coord"` / `"no more MoveToMapCoord"` (L081 room 35, DJDC room 17, QRWC room 20) halts before the end, hiding its tail. Triage each: reproduce with `py tools/converge_triage.py <SEED> floor_49 2`, read the `[runner]`/map divergence, open the map/travel/act-transition code (`run.py` `enter_point`/`travelable_points`, `actmap.py`, `rooms.py`) and the source (`RunManager`/act models), fix the fidelity gap so the run travels the recorded coord. If it is genuinely unported content, flag it in the test with an `xfail(reason=...)`.
2. **max-HP deltas** (`player_max_hp`) — find the max-HP-changing content the sim misses/mis-applies. Candidate sources: max-HP events (search `events/` for `max_hp`), rest-site options, relics (`meat_on_the_bone`, `black_blood`, boss/act relics). Confirm the exact amount/trigger against the source file (CLAUDE.md fidelity table), fix, re-run.
3. **current-HP deltas** (`player_hp`) — damage/heal-pipeline drift (sim takes too little damage / over-heals; several seeds end at full HP). Localize to the earliest diverging act (resync isolates acts). Inspect that act's combats: per-combat sim HP loss vs. the matched enemy intents; audit `DamageCmd`/`BlockCmd`/relic heals/`on_combat_end` against source. Fix earliest act first.

After each fix: re-run the single seed, then the parametrized gate; stage the edited files (small diffs, one subsystem each).

- [ ] **Step A: Write the parametrized convergence gate**

```python
# append to test/test_conformance_player_state.py
import pytest

SEEDS = ["89U21BV1TZ", "DJDCSAQZNR", "L081UMJX4M", "QRWCVDPZN5", "TZEKRYTSNT"]


@pytest.mark.parametrize("seed", SEEDS)
def test_full_run_player_state_parity(seed):
    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2,
        player_checkpoints=player_checkpoints(seed),
        resync_player=False)  # resync OFF for the gate: real end-state must match
    # (1) the run replays to the recording's end (no premature stop)
    assert result.stopped_reason == "reached act 2 boss", result.stopped_reason
    # (2) player HP/max-HP match at the final floor boundary
    hp_divs = [d for d in result.divergences
               if d.stream in ("player_hp", "player_max_hp")]
    assert hp_divs == [], "\n".join(str(d) for d in hp_divs)
    # (3) combat-stream RNG parity is not regressed
    combat_counter_divs = [d for d in result.combat_divergences
                           if d.command_index == -1]
    assert combat_counter_divs == [], "\n".join(str(d) for d in combat_counter_divs)
```

Note: the gate runs with `resync_player=False` so the sim's *own* end-state must match — resync is a triage aid (Tasks 4/5), not a way to pass the gate.

- [ ] **Step B: Run and read the first divergence**

Run: `py -m pytest test/test_conformance_player_state.py -k full_run_player_state_parity -q`
Expected: FAIL initially — map stops and HP deltas per the table. Use `py tools/converge_triage.py <SEED> floor_49 2` to localize each.

- [ ] **Step C: Fix one divergence (per the loop above), re-run, repeat.** Each iteration edits the minimal content/map/pipeline site, re-runs the single `-k "<seed>"` case then the parametrized gate. Stage after each fixed site.

- [ ] **Step D: Green gate** — all 5 seeds pass `test_full_run_player_state_parity` with zero player-state divergences, no premature stop, and unregressed combat-stream counters.

Run: `py -m pytest test/test_conformance_player_state.py -q`
Expected: PASS (all parametrized cases).

---

## Task 7: Acceptance — full suite + docs + memory

- [ ] **Step 1: Full suite**

Run: `py -m pytest test/ -q`
Expected: PASS — 2260 baseline (± the Task-1 legacy-test updates) + all new player-state tests. Zero failures.

- [ ] **Step 2: Confirm acceptance criteria (spec §Acceptance)**
  - `start_run` grants the starting relic; suite green. ✓ Step 1.
  - Harness asserts `player_hp`/`player_max_hp` at floor boundaries; `converge_triage.py` prints DETECTOR 3. ✓ Tasks 3, 5.
  - With resync on, all 5 seeds replay every room to the recording's end (no `player died` / `unreachable map coord` / `no more MoveToMapCoord`). ✓ Task 6.
  - `player_hp`/`player_max_hp` match `run.save` at floors 18/34/49 for all 5 seeds; combat-stream counters unregressed. ✓ Task 6 gate.

- [ ] **Step 3: Update docs**
  - `MODULES.md`: note `SaveOracle` now carries player HP; the runner asserts player state at act boundaries (DETECTOR 3).
  - CLAUDE.md "Known gaps": strike the implication that a run starts relic-less; note the harness now verifies player HP/max-HP.
  - Memory: update `[[sp3-task9-convergence]]` (RNG routing clean; blocker was the missing starter relic + player-HP blind spot; DETECTOR 3 added) and add a note that player-state parity is the active workstream.

- [ ] **Step 4: Stage everything (do NOT commit)**

```bash
git add -A
git status
```

Report the staged diff to Perry for review and commit.

---

## Self-review notes (author)

- **Spec coverage:** U1→Task 1 (starter relic); U2→Tasks 2 (oracle parse) + 3 (assertion); U3→Task 4 (resync + checkpoints); DETECTOR 3→Task 5; U4→Task 6 (map stops → max-HP → current-HP convergence loop); acceptance→Task 7. Every spec work unit maps to ≥1 task.
- **Iterative honesty:** Task 6 is a specified procedure, not fixed code, because the per-content fixes are discovered from DETECTOR 3 divergences — the method (localize → read source → fix → re-run) is spelled out with the call-site/source map, mirroring SP3 Task 9's shape.
- **Type consistency:** `player_checkpoints: dict[int, tuple[int, int]]` and `resync_player: bool` are used identically in Tasks 3, 4, 5, 6. `SaveOracle.player_current_hp`/`player_max_hp` consistent across Tasks 2, 4, 5, 6. `Divergence(stream, command_index, expected, actual, detail)` matches the existing SP2 dataclass; streams `"player_hp"`/`"player_max_hp"` consistent throughout. `RunState.hp`/`max_hp` are the attributes set in `finish_combat`.
- **Commits:** every task stages only (`git add`), never commits — honoring CLAUDE.md rule 4 + `[[sts2-no-auto-commit]]`.
- **Legacy safety:** the only deliberate legacy change is the starter-relic grant (Perry's decision, fidelity-driven); the resync/oracle are parity-only or additive. Full suite is the guard.
