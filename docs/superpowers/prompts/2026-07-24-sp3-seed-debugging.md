# Prompt: SP3 seed debugging (DETECTOR-4 era — canonical procedure)

Paste into a fresh session. Work in `c:\Users\Perry\Desktop\sts2-rl`. This is the
**current** canonical procedure for converging a conformance seed. It supersedes
the method in `docs/superpowers/prompts/2026-07-22-sp3-seed-convergence-grind.md`
and `…-converge-act2-glory.md` — those predate the efficient-convergence tooling
(`[[sp3-efficient-convergence-tooling]]`) and their "fix the EARLIEST room first,
re-run 2–3× for noise" loop is now obsolete. Their per-seed *leads* and
*combat-parity mechanics* sections are still valid reference; their *loop* is not.

---

## What you are doing

Make the pure-Python sim reproduce the real game's RNG-driven world for a given
game **seed**, so a recorded run replays through the sim with **zero** divergence.
Ground truth is the decompiled game at `c:\Users\Perry\Desktop\Slay the Spire 2\src`
(`[[original-means-game-source]]`). A fix that changes sim behavior updates legacy
tests to the game-correct value — **never weaken a real regression guard**.

Only the two **Ironclad** seeds can converge (`[[sp3-seeds-are-5-characters]]`):
- **89U21BV1TZ** — 1st Ironclad run (Overgrowth→Hive→Glory, ascension 0).
- **933T39V18D** — 2nd Ironclad run; has all **49 per-floor saves** (richest).

The other four (DJDC/L081/QRWC/TZEK) are un-ported characters, permanently xfail.

## The tool: `py tools/converge_triage.py <SEED> floor_49 2`

One run prints four detectors. Output is **deterministic** (the conformance
runner seeds its shared rng, Task 1) — run once, trust it. `[[conformance-replay-determinism]]`
is obsolete for conformance runs.

- **[DETECTOR 1] wrong-stream draws** — any in-combat draw on the unseeded shared
  rng (a `Thrash`-class bug). Each is `file:line` + the nearest monster/card. Also
  covered continuously by the fuzz gate (`test_rng_tripwire.py`), so this is
  usually empty for ported content.
- **[DETECTOR 2] stream counter diffs** + **[2b] per-command Hand/Enemies
  mismatches** — the fine-grained combat signal (missing/extra draws; the exact
  hand/enemy annotations that don't match). 89U leans on 2b (it has only 3 saves).
- **[DETECTOR 3] player HP/max-HP** at the 3 act boundaries.
- **[DETECTOR 4] per-floor full-state deltas — THE WORK QUEUE.** With per-floor
  `run.save` checkpoints + **resync ON**, every divergent floor is surfaced in ONE
  run, and — because state (HP, gold, deck, relics, potions, all 15 RNG counters)
  is resynced to the save after each floor — **each divergent floor is an
  INDEPENDENT bug, fixable in any order.** The floor's stream names tell you the
  subsystem: `deck`→reward/transform/shop, `gold`→reward/shop prices,
  `hp`→that floor's combat pipeline, `potions`→belt/retention,
  `counter_X`→a missing/extra draw on stream X *within that one floor*.

`FULLY CONVERGED` prints only when all four detectors are clean and
`forced_combats=0`.

### Reading DETECTOR 4 correctly
- **Floor-save key is `run.total_floor + 1`** (save `floor_{N+1}` = state after
  room N resolved).
- **Stale-save guard:** some `run.save` files are whole-snapshot duplicates of the
  previous floor (the game skips re-export around shop rooms). The runner detects
  these (unchanged `current_act_index` AND non-growing `visited_coords`) and skips
  their diff+resync — so a floor that "should" diverge but shows nothing may be
  stale, not clean; the next real export re-verifies absolutely.
- Resync **masks** cross-floor interaction effects. When DETECTOR 4 is clean with
  resync ON, the true end-to-end gate still runs with resync OFF (see Gates) — a
  few ordering effects may remain there; the floor table has already localized them.

## The loop (per seed)

1. **Triage.** `py tools/converge_triage.py <SEED> floor_49 2` → read DETECTOR 4's
   divergent-floor table. That is your queue.
2. **Pick any divergent floor.** The resync makes it independent — no need to fix
   the earliest first. Prefer the class that repeats across the most floors (one
   root cause clears several rows).
3. **Localize inside that floor.** The sim entered the floor in the recorded state
   (resync guarantees it), so the bug is *inside that floor's room*. Open the
   recording's commands for that floor; read the relevant sim code and the C#
   ground truth for the subsystem the stream names point to.
4. **Fix TDD.** Failing test with a source citation first → fix → the test passes.
   Route any new RNG draw through the correct `combat.combat_rng.<stream>` in the
   game's order AND count (`[[random-card-pick-is-a-shuffle]]`: a
   `StableShuffle(...).First()` changes the *count*, not just the stream).
5. **Re-triage** (deterministic — one run). Confirm that floor's rows cleared and
   nothing regressed. Stage the diff (small, one subsystem).
6. Repeat until DETECTOR 4 is clean with resync ON, then flip to the resync-OFF
   gate (below) and clear whatever ordering residue remains.

**Priority when choosing among floors:** map/progression stops → max-HP deltas →
gold/deck → current-HP. A progression stop (`unreachable map coord` /
`no more MoveToMapCoord`) truncates the run and hides its tail — clear those first.

## Current work queue (measured 2026-07-23; re-triage to refresh)

**933T39V18D** — 49 checkpoints, was 18 divergent floors. Batch 1 fixed the
**potion belt** (now fixed-slot, `[[potion-belt-and-profile-names]]`). Residual
(each its own investigation, now cheap to localize):
- **(a) Potion retention** — sim keeps a potion the game used/discarded (933T
  floors 34 `mazaleths_gift` / 39 `blessing_of_the_forge` / 40+45 `power_potion` /
  47 2nd `explosive_ampoule`; 89U 18 `dexterity` / 34 `shackling`). Likely the
  driver not following `UsePotion`/`DiscardPotion`, or auto-keeping a skipped offer.
- **(b) Unmapped potion ids** — 933T floors 36–38/45/46 (`idmap.sim_potion_id`
  returns None → report-only; map or port the potion).
- **(c) Gold** — floors 24/29 ~200 over (shop spend not followed / reward-gold delta).
- **(d) HP drift** — floors 26/33/34/47.
- **(e) Act-2/3 progression / Mecha Knight** — the earliest true combat divergence
  is the Mecha Knight elite's turn-4 boundary (floor_49 line 578, enemy 151 vs 148
  — Mercury Hourglass / InfernoPower turn-start ordering). This carries act-1 hp +5,
  act-2 hp +13.

**89U21BV1TZ** — only 3 saves (floors 18/34/49); leans on DETECTOR 2b. Its act-2
Glory cascade + **the player DIES in the Entomancer fight** (silent player-HP
divergence) truncates the tail. act-2 max-HP is −4 (the deck's `Feed` never lands a
kill while act-2 fights force-win). See `[[sp3-89u-act1-reconcile-and-relics]]`
(batch-18 was flagged NEXT).

Force-wins are the key symptom: `forced_combats>0` means a combat's hand/enemies
diverged from the recording so real damage was never applied — its downstream HP
and counter deltas are cascade noise until that combat converges.

## Combat-parity mechanics already established — check before re-deriving

From `[[sp3-task9-convergence]]` and the older grind prompts (still valid):
- Recorded `PlayCard` targets are stable CombatId / creation-order — resolve via
  `net_id`, not `enemies[tid-1]`.
- A card mid-`OnPlay` sits in `PileType.Play` limbo, so a reshuffle it triggers
  excludes it.
- Out-of-combat card transforms APPEND at deck end (`CardCmd.cs:437`).
- Reward pool = full `GetUnlockedCards`, not `FilterForCombat`.
- Grid screens are ONE command carrying every pick (`SelectGridCard` /
  `SelectHandCards`), indexed against the unchanged grid (`[[grid-screens-are-one-command]]`).
  The multi-index out-of-combat path is **already fixed** in
  `runner.py:_answer_select_grid` — re-triage before trusting any older prompt that
  lists it as a lead.
- A killing blow skips the victim's `AfterDamageReceived` (`CreatureCmd.cs:392`).
- `[[stable-shuffle-tie-order]]`, `[[relic-rarity-rolls-on-rewards]]`,
  `[[death-does-not-mean-removal]]`, `[[monster-move-weight-vs-cooldown-bug]]`.

## Adjacent tools (run when relevant, not every cycle)
- `py tools/audit_enemy_names.py` — every recorded enemy name vs sim `name` attrs
  (all 6 seeds are ground truth; names are character-independent). Currently 0 misses.
- `py tools/audit_monster_machines.py [act]` — hand-rolled monsters whose C# uses
  `RandomBranchState` (the weight-vs-cooldown class). Currently 0 real bugs.
- `py -m pytest test/test_rng_tripwire.py -q` — 20 seeded random runs; ZERO
  in-combat shared-rng draws. Run after touching any in-combat RNG site.
- `py tools/conformance_coverage.py` — which ported content a converged seed has
  actually exercised (bucket b = the "record this next" shopping list). Note: NO
  seed is converged yet, so "seen" ≠ "verified".

## Gates & rules
- **Seed gate (resync OFF — the real end-state test):**
  `py -m pytest test/test_conformance_player_state.py -k full_run_player_state_parity -q`
- **Full suite** (~5 min): `py -m pytest test/ -q`. Baseline **2352 passed,
  3 skipped, 6 xfailed, 0 failed** (the 3 skips = tripwire's documented unimplemented
  potions). Must stay green and unregressed. Re-measure at session start.
- **Never `git commit` / `git push`** (`[[sts2-no-auto-commit]]`, CLAUDE.md rule 4).
  `git add <paths>` and stop; Perry reviews and commits in batches. **Everything
  from the efficient-convergence plan is already STAGED, uncommitted — stage on
  top, don't reset.** RunReplays is a separate repo (fixtures staged there).
- Style: `from __future__ import annotations` + lazy in-method imports.

## Definition of done (per seed)
The seed's `test_full_run_player_state_parity` case flips XFAIL→PASS: its
`_XFAIL_CONVERGENCE` entry and xfail mark removed from
`test/test_conformance_player_state.py`, with — at the resync-OFF gate — zero
`player_hp`/`player_max_hp` divergence at every act boundary, no premature stop,
and unregressed combat-stream counters. Full suite green. Stage everything, report
the staged diff to Perry, and write a memory per new fidelity gap found.

If a genuinely un-ported piece of content blocks a seed, port it if tractable;
else `xfail(reason=...)` that specific seed with an accurate reason and record the
debt as a memory.
