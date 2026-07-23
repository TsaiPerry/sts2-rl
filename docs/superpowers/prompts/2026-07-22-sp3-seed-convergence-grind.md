# Prompt: SP3 per-seed convergence grind (drive Task 6 to green)

Paste this into a fresh session to continue converging the 5 conformance seeds
after the SP3 player-state-parity infrastructure landed
(`docs/superpowers/plans/2026-07-22-sp3-player-state-parity.md`, Tasks 1–5 done;
Task 6 is this grind). Work in `c:\Users\Perry\Desktop\sts2-rl`.

---

## The prompt

You are continuing the SP3 conformance convergence workstream. The
player-state-parity infrastructure is already merged/staged: `start_run` grants
`burning_blood`; `SaveOracle` carries `player_current_hp`/`player_max_hp`; the
runner asserts player HP/max-HP at act boundaries (`player_hp`/`player_max_hp`
`Divergence`s, `command_index = completed act index`) with an opt-in
`resync_player`; and `tools/converge_triage.py` prints `[DETECTOR 3]`.

**Goal:** drive `test/test_conformance_player_state.py::test_full_run_player_state_parity`
to green for all 5 seeds — each seed's full act-1+2 replay must reach the act-2
boss with **zero** `player_hp`/`player_max_hp` divergence and **unregressed**
combat-stream counters. Each seed is currently `xfail(strict=False)` in that
file (`_XFAIL_CONVERGENCE`); as a seed converges it flips to XPASS — drop its
mark and remove its `_XFAIL_CONVERGENCE` entry then.

**Ground truth:** the decompiled game source at
`c:\Users\Perry\Desktop\Slay the Spire 2\src` (`[[original-means-game-source]]`).
When a fix changes sim behavior to match the game, update legacy tests to the
game-correct behavior — never weaken a test that catches a real regression.

**Never `git commit` / `git push`** (`[[sts2-no-auto-commit]]`, CLAUDE.md rule 4).
Every "stage" step is `git add <paths>` and stop; Perry reviews and commits in
batches. Use `from __future__ import annotations` + lazy in-method imports.

### Tooling
- Per-seed triage: `py tools/converge_triage.py <SEED> floor_49 2`
  - `[DETECTOR 1]` in-combat draws from the UNSEEDED shared rng (wrong-stream).
  - `[DETECTOR 2]` per-stream counter diffs (missing/extra draws) + `[2b]`
    per-command Hand/Enemies mismatches — **fix the EARLIEST room first**.
  - `[DETECTOR 3]` player-state HP/max-HP deltas at act boundaries.
  - Runs with `resync_player=True` so later acts are reachable during triage;
    the **gate** runs `resync_player=False` (real end-state must match).
- The gate: `py -m pytest test/test_conformance_player_state.py -k full_run_player_state_parity -q`
- Full suite (~3.5 min, baseline 2262 passed + 5 xfailed):
  `py -m pytest test/ -q`

### The loop (repeat per seed until green), priority order
1. **Map/progression stops first** — a seed whose `stopped_reason` is
   `unreachable map coord` / `no more MoveToMapCoord` halts before the end and
   hides its tail. Reproduce, read the `[runner]` divergence (the exact
   `(col,row)`), open the map/travel/act-transition code (`run.py`
   `enter_point`/`travelable_points`/`advance_act`, `actmap.py`, `rooms.py`) and
   the source (`RunManager`/act models). Fix the fidelity gap so the recorded
   coord is travelable. If genuinely un-ported content, `xfail(reason=...)`.
2. **max-HP deltas** (`player_max_hp`) — max-HP-changing content the sim
   misses/mis-applies. Candidates: max-HP events (`grep max_hp events/`),
   rest-site options, relics (`meat_on_the_bone`, `black_blood`, boss/act
   relics), Neow drawbacks. Confirm the exact amount/trigger against source, fix.
3. **current-HP deltas** (`player_hp`) — damage/heal-pipeline drift, mostly
   downstream of **forced combats** (a combat the driver force-won because the
   sim's hand/enemies diverged from the recording, so real combat damage was
   never applied). Localize to the EARLIEST diverging act (resync isolates
   acts), then the earliest diverging combat (`[DETECTOR 2b]`), and converge
   that combat: match enemy display names, deck/draw (Shuffle stream), card
   effects, potions, and enemy intents against source. Fix earliest first.

After each fix: re-run the single seed's triage, then the `-k full_run_player_state_parity`
gate, then stage the edited files (small diffs, one subsystem each).

### Combat-parity mechanics already established (from prior batches, `[[sp3-task9-convergence]]`)
- Recorded `PlayCard` targets are stable CombatId / creation-order — resolve via
  `net_id`, not `enemies[tid-1]`.
- A card mid-`OnPlay` sits in `PileType.Play` limbo, so a reshuffle it triggers
  excludes it.
- Out-of-combat card transforms APPEND at deck end (`CardCmd.cs:437`).
- Reward pool = full `GetUnlockedCards`, not `FilterForCombat`.
- `SelectHandCards` / `SelectCards` replay commands are ported (Armaments-style
  full-hand upgrades = one command with all indices).
- Ovicopter egg-SLOT placement `[Egg,Egg,Egg,Ovicopter]` with per-slot Niche HP.
- Enemy name mismatches (e.g. `'Corpse Slug'` vs sim `'CorpseSlug'`) flag a
  divergence and trigger a force-win — fix the display name to match the save.

### Current landscape (2026-07-22, resync OFF, from DETECTOR 3)
- **89U21BV1TZ** — reaches act-2 boss. `act1 player_max_hp` −16, `act2 player_hp`
  (sim high, ~+60), `act2 player_max_hp` −18; 4 combat-stream counter divs.
  Act-1 combats converged (floors 18/34 green in prior batches); act-2 combat
  parity is the remaining pole. **Start here — it's the closest.**
- **TZEKRYTSNT** — reaches act-2 boss; large `player_hp` deltas (sim under-takes
  combat damage; `forced=22`). Broad combat-parity gaps across both acts.
- **DJDCSAQZNR** — stops room 17 `unreachable map coord` (`col=1,row=1`, the
  act1→2 transition); combat diverges from room 11 (`Corpse Slug` name + hand
  draws). Fix the act-transition map first, then its combats.
- **L081UMJX4M** — stops room 36 `unreachable map coord` (`col=3,row=5`).
- **QRWCVDPZN5** — stops room 20 `no more MoveToMapCoord`.

### Definition of done
`py -m pytest test/ -q` green with all 5 `test_full_run_player_state_parity`
cases XPASS→PASS (marks removed), zero player-state divergences, no premature
stops, unregressed combat-stream counters. Stage everything; report the staged
diff to Perry for review + commit.
