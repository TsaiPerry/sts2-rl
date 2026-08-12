# v7 Training Plan: Reward Redesign + Ascension 10 + Card Exposure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrain the run-scale Ironclad policy at ascension 10 with a reward function that values long-term power (upgrades, elites, removals, deeper acts), broad card exposure, and full behavior instrumentation.

**Architecture:** Three phases. **Phase A** implements the 8 missing ascension mechanics in the sim (levels 2–9; levels 1 and 10 already exist) behind a per-run/per-combat ascension value so asc-0 behavior is bit-identical. **Phase B** adds the v7 reward terms, behavior counters (potions/upgrades/removes/elites), per-card take metrics, and a deck-randomization curriculum knob to `STS2RunEnv` — all off by default so existing tests and conformance are untouched. **Phase C** is the staged training run (asc 0 → 4 → 7 → 10) resuming from the v6 checkpoint, with eval gates per stage.

**Tech Stack:** Python (raw-PyTorch PPO in `train_torch.py`), the `sts2_rl` simulator package, pytest, PowerShell driver scripts. All paths relative to `c:\Users\Perry\Desktop\sts2-rl` unless noted; game source citations are under `c:\Users\Perry\Desktop\Slay the Spire 2\src\`.

## Why these changes (eval evidence, `runs/eval_v6_iter1110.episodes.csv`, 150 episodes, greedy)

| Observed problem (Perry, live game) | Eval evidence | v7 fix |
|---|---|---|
| Rests every rest site, never upgrades | 726 heals vs **2 upgrades** in 728 visits | `--reward-upgrade 0.5` + act-scaled floor rewards (upgrades compound into later, higher-value floors) |
| Forces one archetype, over-skips cards | take rate 72.9% (≈ random's 71%) | deck randomization (`--deck-random-prob`) for card exposure + per-card offer/take CSV to measure it |
| Can't play gimmick fights (Decimillipede, The Insatiable) | 39 deaths on floor 31, 35 on floor 16 (boss walls) | asc 8/9 monster port hardens all fights; dedicated combat-env gimmick probes measure progress |
| Drinks every potion instantly | no metric existed at all | new `ep_potions_obtained/used` counters (env → train CSV → eval CSV); no potion reward shaping (hack risk) — difficulty pressure + measurement |
| Misses lethal, ends turns with energy | 0.23 energy unspent per end-turn | measured gate; deadlier enemies raise the cost of a wasted turn. Honest expectation: partial improvement — this is capability, not incentive |
| No long-term vs short-term concept | win bonus was 3.0 vs ~51 floor return | floors: +1.0/+1.5/+2.0 by act, win bonus 12.0, elite +0.5, remove +0.25 |

## Global Constraints

- **Reward numbers (Perry's spec):** +1.0 per act-1 floor, +1.5 per act-2 floor, +2.0 per act-3 floor; +0.5 per upgrade; +0.5 per elite; +0.25 per card remove. Win bonus 12.0 (scaled from 3.0 to stay proportional to the inflated floor return; Perry did not specify — flag-tunable).
- **Ascension 10** is the training target. Ascension levels are CUMULATIVE (asc N = levels 1..N), mirroring `AscensionManager.HasLevel` (`src/Core/Entities/Ascension/AscensionManager.cs:45-48`).
- **Asc-0 bit-identity:** every sim change must be gated on ascension level so the full pytest suite AND both Ironclad conformance seeds (89U, 933T) stay byte-identical at asc 0. Run `python -m pytest -q -x` after every task.
- **No obs schema change.** `RUN_OBS_SCHEMA_VERSION` stays 11. Stages train at a FIXED ascension, so the policy needs no ascension input (difficulty is visible implicitly: enemy HP, attack previews, belt slot_exists flags, the Bane card in deck). This lets v7 resume the v6 checkpoint with no migration.
- **All new env kwargs / reward terms default OFF** (0.0 / None) — `STS2RunEnv()` with no args must behave exactly as today.
- **"Original behavior" = the decompiled game source.** Cite `File.cs:line` in a comment at every ported value.
- **Git: stage only, never commit** (repo policy). The plan's "commit" steps therefore say `git add` only.
- **Subagents (wave tasks): dispatch on sonnet.**
- Venv: `.venv\Scripts\python.exe` (no pandas anywhere — stdlib csv only in tools).

## File Structure

- `sts2_rl/run.py` — RunState: store ascension, `has_ascension()`, TightBelt, AscendersBane injection, Poverty gold
- `sts2_rl/hooks.py` — `HookSystem.ascension` (combat-side ascension carrier)
- `sts2_rl/monsters/base.py` — asc-aware HP roll + `asc_value()` helper
- `sts2_rl/monsters/**/*.py` — per-monster Tough/Deadly values (wave)
- `sts2_rl/events/ancient.py` — WearyTraveler heal
- `sts2_rl/rewards.py` — Scarcity rarity/upgrade odds
- `sts2_rl/run_env.py` — reward terms, behavior counters, deck randomization
- `sts2_rl/vec_env.py` — `EnvSpec` fields, `EP_METRIC_KEYS`
- `sts2_rl/evaluation.py`, `eval.py` — new metrics, cards CSV, `--ascension`
- `train_torch.py` — new CLI flags
- `train_curriculum_v7.ps1` — stage driver (new)
- `test/test_ascension.py`, `test/test_v7_rewards.py` — new test files

---

# Phase A — Ascension mechanics in the sim

> **STATUS 2026-08-09: PHASE A IS COMPLETE (Tasks 1–5 all done, staged, review-clean).**
> 100/100 monsters gated + cited, 195 ascension tests green in `test/test_ascension.py`.
> Seams now available to Phase B: `RunState.ascension` / `run.has_ascension(level)`,
> `HookSystem.ascension`, `asc_value(hooks, level, asc_val, base)` in `monsters/base.py`,
> `Monster.min_hp_asc/max_hp_asc`, **`CombatState(ascension=...)`** (`combat.py:141,180` —
> seeds `hooks.ascension` BEFORE `create_monsters`, so HP rolls see it; a review-caught
> ordering bug — never set `hooks.ascension` after construction), `EnvSpec.ascension`
> (`vec_env.py:64,90,95`), `--ascension` on both `train_torch.py` (:154) and `eval.py` (:380),
> and a WARN-only checkpoint ascension stamp (`checkpoints.check_ascension`, deliberate —
> the curriculum ramps ascension across resumes).
> The task text below is retained as the historical record of what was built.

Current state (verified before implementation): `AscensionLevel` enum exists (`sts2_rl/actmap.py:58-77`). Only level 1 (SwarmingElites, 8 elites — `actmap.py:80-82`) and level 10 (DoubleBoss — `run.py:1197,1287`) are implemented. Levels 2–9 have **zero** sim implementation. Effects, from source:

| Lvl | Name | Effect | Source |
|---|---|---|---|
| 2 | WearyTraveler | Ancient-event heal is 80% of missing HP | `AncientEventModel.cs:180-183` |
| 3 | Poverty | combat gold × 0.75 | `EncounterModel.cs:75-97`, `AscensionHelper.cs:12` |
| 4 | TightBelt | max potion slots − 1 | `AscensionManager.cs:56-59` |
| 5 | AscendersBane | curse added to deck at run start | `AscensionManager.cs:60-65`, `Cards/AscendersBane.cs` |
| 6 | Inflation | shop card removal 100 base / +50 per use (vs 75/+25) | `MerchantCardRemovalEntry.cs:20-22` |
| 7 | Scarcity | worse card rarity odds; upgraded-card odds halved | `CardRarityOdds.cs:13-41`, `CardFactory.cs:23` |
| 8 | ToughEnemies | per-monster HP up | ~109 monster files |
| 9 | DeadlyEnemies | per-monster damage up | same files |

### Task 1: Ascension plumbing (run-side + combat-side)

**Files:**
- Modify: `sts2_rl/run.py` (RunState stores ascension; `has_ascension`)
- Modify: `sts2_rl/hooks.py` (`HookSystem.ascension` attribute)
- Modify: `sts2_rl/monsters/base.py` (`asc_value` helper)
- Test: `test/test_ascension.py` (new)

**Interfaces:**
- Produces: `RunState.ascension: int` (set by `start_act`, default 0), `RunState.has_ascension(level: AscensionLevel) -> bool`, `HookSystem.ascension: int` (default 0, set by `RunState.create_combat`), `asc_value(hooks, level, asc_val, base)` in `sts2_rl/monsters/base.py`. Every later Phase-A task consumes these.

- [ ] **Step 1: Write the failing tests**

```python
# test/test_ascension.py
"""Ascension plumbing: cumulative level checks reach run- and combat-side code."""
import random

from sts2_rl.actmap import AscensionLevel
from sts2_rl.run import RunState


def _run(asc: int) -> RunState:
    run = RunState(rng=random.Random(0))
    run.start_act(0, ascension=asc)
    return run


def test_run_stores_ascension_and_cumulative_check():
    run = _run(4)
    assert run.ascension == 4
    assert run.has_ascension(AscensionLevel.SWARMING_ELITES)      # level 1
    assert run.has_ascension(AscensionLevel.TIGHT_BELT)           # level 4
    assert not run.has_ascension(AscensionLevel.ASCENDERS_BANE)   # level 5


def test_ascension_defaults_to_zero():
    run = RunState(rng=random.Random(0))
    run.start_act(0)
    assert run.ascension == 0
    assert not run.has_ascension(AscensionLevel.SWARMING_ELITES)
```

Note: check the exact member names in `sts2_rl/actmap.py:58-77` before writing — the enum was ported already; use its spelling (e.g. `SWARMING_ELITES` vs `SwarmingElites`). Check `start_act`'s signature at `run.py:1253` — `ascension` is already a parameter; the task is to STORE it on `self` (today it is only threaded to map generation).

- [ ] **Step 2: Run tests, verify they fail** — `.venv\Scripts\python.exe -m pytest test/test_ascension.py -x -q` → AttributeError (`ascension`/`has_ascension` missing).

- [ ] **Step 3: Implement.** In `run.py`:
  - In `RunState.__init__`: `self.ascension: int = 0`.
  - In `start_act` (`run.py:1253`): `self.ascension = ascension` (first thing, before map generation — later tasks read it during act setup).
  - Add method:

```python
def has_ascension(self, level: "AscensionLevel") -> bool:
    """AscensionManager.HasLevel (AscensionManager.cs:45-48): levels are
    cumulative — asc N grants every level <= N."""
    return self.ascension >= int(level)
```

  - In `create_combat` (grep `def create_combat` in `run.py`): after the combat's `HookSystem` exists, set `hooks.ascension = self.ascension`.

  In `hooks.py`: add `self.ascension: int = 0` in `HookSystem.__init__` with a comment: combat-side mirror of `RunManager.Instance.HasAscension` — per-combat instance, NOT a module global, because multiple envs at different ascensions interleave in one process.

  In `monsters/base.py`:

```python
def asc_value(hooks, level, asc_val, base):
    """AscensionHelper.GetValueIfAscension (AscensionHelper.cs:22-47): the
    ascension value when the run has `level`, the base value otherwise."""
    return asc_val if hooks.ascension >= int(level) else base
```

- [ ] **Step 4: Run the new tests AND the full suite** — `.venv\Scripts\python.exe -m pytest -q` → all green (plumbing is inert at asc 0).
- [ ] **Step 5: Stage** — `git add sts2_rl/run.py sts2_rl/hooks.py sts2_rl/monsters/base.py test/test_ascension.py`

### Task 2: Economy/map levels 2–7

**Files:**
- Modify: `sts2_rl/events/ancient.py:25` (WearyTraveler), `sts2_rl/run.py` (Poverty gold, TightBelt, AscendersBane), shop removal-cost site (Inflation — grep `75` near removal in `sts2_rl/` shop/merchant module), `sts2_rl/rewards.py` (Scarcity), `sts2_rl/cards/` (AscendersBane card if not already ported — grep `class AscendersBane` first)
- Test: `test/test_ascension.py` (extend)

**Interfaces:**
- Consumes: `run.has_ascension(AscensionLevel.X)` from Task 1.
- Produces: gameplay effects only; no new API.

Implement each level as a `run.has_ascension(...)` gate at the sim site mirroring the cited source line. Per level:

1. **WearyTraveler** — `events/ancient.py:25`: the entering-an-Ancient heal computes `amount = max_hp - hp`; gate `amount *= 0.8` (source multiplies the DECIMAL amount before healing, `AncientEventModel.cs:180-183`; match the sim's rounding convention for heals — check how the sim heal cmd rounds and mirror the C# decimal → int path).
2. **Poverty** — combat gold: find the sim's port of `EncounterModel` gold (`GOLD_REWARD_RANGES` consumer near `driver.py:564` / `rewards.py`); multiply rolled combat gold by 0.75 (`EncounterModel.cs:75-97`). Read the source block first: the multiplier applies to the rolled amount (both the min-max roll and the boss/elite paths at both cited sites) — put the gate where the source has it, not downstream, so rounding matches.
3. **TightBelt** — `run.py:239` (`self.max_potions = self.MAX_POTIONS`): after ascension is known. Careful: `max_potions` is set in `__init__` but ascension arrives at `start_act`. Apply in `start_act` on the FIRST act only (`AscensionManager.ApplyEffectsTo` runs once at run start): `if first_act and self.has_ascension(AscensionLevel.TIGHT_BELT): self.max_potions -= 1; self.potions = self.potions[:self.max_potions]` (belt is `[None]*max_potions` at that point; assert all-None before truncating).
4. **AscendersBane** — grep `class AscendersBane` in `sts2_rl/cards/`; the curse may already be ported (it is in `CurseCardPool.cs:22`, and the sim ported curse pools). If missing, port `Cards/AscendersBane.cs` (curse, unplayable, ethereal — read the source file; `max_upgrade_level = 0`). Then in `start_act` (first act only, after TightBelt): create the card and add it to the deck silently with `floor_added_to_deck = 1`, mirroring `AscensionManager.cs:60-65`. Use the same deck-add API events use (grep an event that adds a curse, e.g. the Cursed-run modifier path, and copy its call).
5. **Inflation** — find the sim's shop removal-cost constants (grep `removal` in the shop/merchant module; base 75, increase 25): `base = 100 if asc else 75`, `increase = 50 if asc else 25` via `run.has_ascension(AscensionLevel.INFLATION)` (`MerchantCardRemovalEntry.cs:20-22`).
6. **Scarcity** — `rewards.py` ports `CardRarityOdds`. Replace each of the 7 constants with an ascension-conditional pair exactly as `CardRarityOdds.cs:13-41` has them (regular common 0.615/0.6, rarity growth 0.005/0.01, regular rare 0.0149/0.03, elite common 0.549/0.5, elite rare 0.05/0.1, shop common 0.585/0.54, shop rare 0.045/0.09) plus `CardFactory.cs:23` upgraded-card odd scaling 0.125/0.25. These are read at reward-generation time where `run` is in scope — thread `run.has_ascension` in; if a constant is module-level today, convert it to a function of the run.

- [ ] **Step 1: Write failing tests** — one per level in `test/test_ascension.py`. Pattern (repeat for each level; exact assertions per effect):

```python
def test_tight_belt_shrinks_belt():
    assert _run(4).max_potions == _run(3).max_potions - 1

def test_ascenders_bane_in_starting_deck():
    deck5 = [type(c).__name__ for c in _run(5).deck]
    assert "AscendersBane" in deck5
    assert "AscendersBane" not in [type(c).__name__ for c in _run(4).deck]

def test_weary_traveler_heal_reduced():
    # damage the run, then fire an Ancient event heal at asc 1 vs asc 2 and
    # compare healed amounts (asc2 == floor of 0.8 * missing, per the sim's
    # heal rounding). Build via the driver or call the ancient's
    # before-event hook directly — mirror an existing ancient.py test.
    ...
```

For Poverty/Inflation/Scarcity, test the VALUE the site produces (rolled gold with a seeded rng at asc 2 vs 3; removal cost at asc 5 vs 6; rarity odds table at asc 6 vs 7) rather than a full run. For each, find an existing test of the same site (grep the test dir for the constant, e.g. `0.03` or `75`) and mirror its setup.

- [ ] **Step 2: Verify each fails** — `.venv\Scripts\python.exe -m pytest test/test_ascension.py -x -q`.
- [ ] **Step 3: Implement all six gates** (as specced above, source citation comment at each).
- [ ] **Step 4: Full suite green + conformance spot-check** — `.venv\Scripts\python.exe -m pytest -q`. Both Ironclad seeds run at asc 0, so any suite/conformance diff means a gate leaked — fix before proceeding.
- [ ] **Step 5: Stage** — `git add -A sts2_rl test`

### Task 3: ToughEnemies/DeadlyEnemies pathfinder (Chomper, worked example)

**Files:**
- Modify: `sts2_rl/monsters/base.py` (asc-aware HP roll), `sts2_rl/monsters/hive/chomper.py`
- Test: `test/test_ascension.py` (extend)

**Interfaces:**
- Consumes: `hooks.ascension`, `asc_value` (Task 1).
- Produces: the per-monster port pattern the Task 4 wave repeats: class attrs `min_hp_asc`/`max_hp_asc` (Tough) + per-value `asc_value(hooks, AscensionLevel.DEADLY_ENEMIES, x, y)` at BOTH the intent build and the damage execution site (Deadly).

- [ ] **Step 1: Failing test**

```python
def _spawn_chomper(asc: int):
    from sts2_rl.hooks import HookSystem
    from sts2_rl.monsters.hive.chomper import Chomper
    hooks = HookSystem()          # match the suite's existing construction
    hooks.ascension = asc
    return Chomper(hooks, random.Random(0))

def test_chomper_tough_hp():
    assert 60 <= _spawn_chomper(0).hp <= 64      # Chomper.cs:28-30 base
    assert 63 <= _spawn_chomper(8).hp <= 67      # ToughEnemies values
    assert 60 <= _spawn_chomper(7).hp <= 64      # asc 7 < ToughEnemies(8)

def test_chomper_deadly_damage():
    m0, m9 = _spawn_chomper(0), _spawn_chomper(9)
    assert m0.machine.initial.intent.damage == 8     # Chomper.cs:32
    assert m9.machine.initial.intent.damage == 9
```

Adjust accessor spellings (`hp`, `machine.initial.intent`) to the real base-class API — read `monsters/base.py` and `monsters/state_machine.py` first; the assertions' VALUES are the spec.

- [ ] **Step 2: Verify fails.**
- [ ] **Step 3: Implement.** In `monsters/base.py`, find the initial-HP roll (it reads class attrs `min_hp`/`max_hp` with the monster's rng). Add optional class attrs and gate:

```python
class Monster:
    min_hp_asc: int | None = None   # ToughEnemies (asc 8+) HP range; None = unchanged
    max_hp_asc: int | None = None
```

and in the roll: use `min_hp_asc/max_hp_asc` instead of `min_hp/max_hp` when `hooks.ascension >= int(AscensionLevel.TOUGH_ENEMIES)` and the asc attrs are not None. **The rng draw must happen exactly once either way** (same `randint` call, different bounds) so asc-0 RNG streams are untouched.

In `chomper.py`:

```python
_CLAMP_DMG = 8          # Chomper.cs:32 base; 9 at DeadlyEnemies (asc 9+)
_CLAMP_DMG_ASC = 9

class Chomper(MachineMonster):
    min_hp = 60          # Chomper.cs:28-30
    max_hp = 64
    min_hp_asc = 63
    max_hp_asc = 67

    def _clamp_dmg(self) -> int:
        return asc_value(self.hooks, AscensionLevel.DEADLY_ENEMIES,
                         _CLAMP_DMG_ASC, _CLAMP_DMG)
```

and use `self._clamp_dmg()` at BOTH sites: the `Intent(...)` in `build_machine` and the `self._execute_attack(...)` in `_clamp`. (Source reads the `ClampDamage` property dynamically at both — `Chomper.cs:58,69`.) Adjust to however the base class exposes `hooks` on the instance.

- [ ] **Step 4: New tests pass + full suite green** (asc-0 identical — same rng draws, same values).
- [ ] **Step 5: Stage.**

### Task 4: Monster wave — port Tough/Deadly for every remaining monster

**Files:**
- Modify: every file in `sts2_rl/monsters/` whose source counterpart calls `AscensionHelper` (~108 monsters, ~380 sites)
- Test: `test/test_ascension.py` (spot tests per batch)

**Interfaces:**
- Consumes: exactly the Task 3 pattern. No new API.

Protocol (this is a dispatch campaign, run after Task 3 is staged):

- [ ] **Step 1: Build the worklist.** `Grep 'GetValueIfAscension|HasAscension\(AscensionLevel' 'c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Models\Monsters' --count` → one row per monster file with site count (~111 files; Chomper done). Save as `docs/superpowers/plans/v7-monster-wave-worklist.md` with a checkbox per monster.
- [ ] **Step 2: Dispatch in batches of ~12 monsters, one sonnet subagent per batch** (parallel, read the worklist file for assignment). Each subagent brief:
  - For each assigned monster: read `src/Core/Models/Monsters/<Name>.cs`, find every `AscensionHelper` call; port per the Task 3 pattern (HP → `min_hp_asc`/`max_hp_asc`; damage/block/counts → `asc_value(...)` used at intent AND execution sites; cite `File.cs:line` at each value).
  - Some sites are ToughEnemies HP on SUMMONED/spawned minions, per-move block, or status counts — port them all; the level named in the source call decides the gate, nothing else.
  - Add ONE spot test per monster to `test/test_ascension.py` (HP range at asc 8, one damage value at asc 9 — the Chomper test pattern).
  - Run `.venv\Scripts\python.exe -m pytest test/test_ascension.py -q` and the monster's own existing tests; report per-monster: sites found / sites ported / citations.
  - Beware the known bug class: hand-rolled machines have misread `AddBranch` int args before (weight vs cooldown) — do not "fix" move machines in passing; port ONLY ascension values.
- [ ] **Step 3: Coverage gate.** After all batches: re-grep the source Monsters dir, count sites; grep the sim for `asc_value|_asc` in `sts2_rl/monsters/`; every source site must map to a sim site or a written justification (e.g. cosmetic-only value, unported monster). Record the tally in the worklist file.
- [ ] **Step 4: Full suite green.** `.venv\Scripts\python.exe -m pytest -q`
- [ ] **Step 5: Stage.**

Also in this task (small, same pattern, non-monster): `EncounterModel.cs` has 2 non-Poverty ascension reads (check what they gate — likely ToughEnemies encounter HP multipliers) and `AncientEventModel.cs` beyond the heal — port whatever the citations show, same gating rules.

### Task 5: Ascension flag plumbing (train + eval)

**Files:**
- Modify: `sts2_rl/vec_env.py:54-101` (EnvSpec + build_env), `train_torch.py` (flag + `env_spec()` at :362-373), `eval.py:114-121` (`make_run_env`) + its argparser
- Test: `test/test_train_io.py` or nearest CLI-spec test (grep `EnvSpec(` in `test/`)

**Interfaces:**
- Produces: `EnvSpec.ascension: int = 0`; CLI `--ascension N` on both `train_torch.py` and `eval.py` (run/column envs only; reject for `--env combat` like `--acts` does at `train_torch.py:283-284`).

- [ ] **Step 1: Failing test** — extend the existing EnvSpec/CLI test: `EnvSpec(kind="run", ascension=10)` builds an env whose `_ascension == 10`; default spec builds `_ascension == 0`.
- [ ] **Step 2: Verify fails.**
- [ ] **Step 3: Implement.** Add `ascension: int = 0` to `EnvSpec`; pass `ascension=spec.ascension` to BOTH `STS2CurriculumRunEnv` and `STS2RunEnv` in `build_env` (the kwarg already exists on the env, `run_env.py:692` — it just was never fed); add `ap.add_argument("--ascension", type=int, default=0, ...)` to both CLIs, threading through `env_spec()` and `make_run_env()`; guard `args.env == "combat" and args.ascension` → SystemExit. Checkpoints: stamp `ascension` into the checkpoint meta next to `env_kind` (grep how `env_kind` is stamped in `sts2_rl/checkpoints.py`) — WARN on mismatch at resume (print, don't refuse: v7 deliberately resumes across ascensions).
- [ ] **Step 4: Tests + suite green.**
- [ ] **Step 5: Stage.**

---

# Phase B — Reward terms, behavior metrics, deck randomization

### Task 6: v7 reward terms in STS2RunEnv

**Files:**
- Modify: `sts2_rl/run_env.py` (`__init__` :688-735, `reset` :813-854, `step` :856-889, `_count_behavior` :891-931, `_info` :1443-1465)
- Test: `test/test_v7_rewards.py` (new)

**Interfaces:**
- Consumes: `run.deck` (cards with `upgrade_level`, `cards/base.py:214,289`), `run.potions` fixed-slot list (`run.py:240`), `request.rewards.room_type` (`driver.py:472`, used like `run_env.py:916`), `RoomType` from `sts2_rl.rooms`.
- Produces: env kwargs `floor_rewards_by_act: tuple[float, ...] | None = None`, `reward_upgrade: float = 0.0`, `reward_remove: float = 0.0`, `reward_elite: float = 0.0`; info keys `ep_upgrades, ep_removes, ep_elites_won, ep_potions_obtained, ep_potions_used` (episode-end, like the existing tallies). Tasks 7–9 and Phase C consume these names exactly.

- [ ] **Step 1: Failing tests** (drive the real env; seeds make these deterministic — pick seeds by probing once, then pin):

```python
# test/test_v7_rewards.py
"""v7 reward terms. All default OFF: a default-constructed env must be
bit-identical to v6 behavior (the whole existing suite is that regression
test). These tests only exercise the opted-in terms."""
import random
import numpy as np
from sts2_rl.run_env import STS2RunEnv


def _roll(env, seed, steps=400):
    obs, _ = env.reset(seed=seed)
    total = 0.0
    for _ in range(steps):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        obs, r, term, trunc, info = env.step(a)
        total += r
        if term or trunc:
            break
    return total, info


def test_act_scaled_floor_rewards_match_scalar_when_flat():
    r_flat, _ = _roll(STS2RunEnv(), seed=3)
    r_tuple, _ = _roll(STS2RunEnv(floor_rewards_by_act=(1.0, 1.0, 1.0)), seed=3)
    assert r_flat == r_tuple            # (1,1,1) tuple == scalar 1.0


def test_upgrade_reward_fires_on_smith():
    # Env whose scripted policy smiths at the first rest site; assert the
    # ep_upgrades tally and that return includes +0.5 * ep_upgrades vs the
    # same trajectory with reward_upgrade=0. Script it by preferring the
    # REST_SMITH choice action when legal (CHOICE_BASE+1) over first-legal.
    ...


def test_default_env_reward_unchanged():
    r_a, _ = _roll(STS2RunEnv(), seed=7)
    r_b, _ = _roll(STS2RunEnv(floor_rewards_by_act=None, reward_upgrade=0.0,
                              reward_remove=0.0, reward_elite=0.0), seed=7)
    assert r_a == r_b
```

- [ ] **Step 2: Verify fails** (TypeError: unexpected kwarg).
- [ ] **Step 3: Implement.**

`__init__` — add the four kwargs, store as `self._floor_rewards_by_act` (as tuple or None), `self._reward_upgrade`, `self._reward_remove`, `self._reward_elite`.

`reset` — after the existing tallies (`run_env.py:824-835`) add:

```python
self._ep_upgrades = 0
self._ep_removes = 0
self._ep_elites_won = 0
self._ep_potions_obtained = 0
self._ep_potions_used = 0
self._elite_reward_key: tuple[int, int] | None = None
```

and AFTER `self._switch(None)` (the run is set up, Neow pending — deck/belt are their true episode-start selves):

```python
self._deck_upgrade_base = sum(c.upgrade_level for c in run.deck)
self._deck_len_base = len(run.deck)
self._belt_base = sum(1 for p in run.potions if p is not None)
```

`step` — three insertions.

(a) Floor reward, replacing the flat line at `run_env.py:876`:

```python
if self._floor_rewards_by_act is not None:
    act_i = max(0, min(run.act_index, len(self._floor_rewards_by_act) - 1))
    reward += self._floor_rewards_by_act[act_i] * (run.total_floor - floor_before)
else:
    reward += self._floor_reward * (run.total_floor - floor_before)
```

(b) Elite: snapshot `elites_before = self._ep_elites_won` just before the `self._count_behavior(...)` call, then after the reward accumulation: `reward += self._reward_elite * (self._ep_elites_won - elites_before)`. Detection goes in `_count_behavior` (any request carrying a rewards screen from an elite room, deduped per room like rest visits):

```python
rewards = getattr(request, "rewards", None)
if rewards is not None and rewards.room_type == RoomType.ELITE:
    key = (request.run.act_index, request.run.total_floor)
    if key != self._elite_reward_key:
        self._elite_reward_key = key
        self._ep_elites_won += 1
```

(c) Deck/belt deltas, after the terminal-bonus block (`run_env.py:879-886`), measured only between decisions with no live combat (in-combat temporary upgrades and mid-combat deck adds are ignored; permanent changes get credited at the first out-of-combat step):

```python
if self._request is None or self._request.kind != DecisionKind.COMBAT:
    up_now = sum(c.upgrade_level for c in run.deck)
    if up_now > self._deck_upgrade_base:
        gained = up_now - self._deck_upgrade_base
        reward += self._reward_upgrade * gained
        self._ep_upgrades += gained
    self._deck_upgrade_base = up_now
    n_now = len(run.deck)
    if n_now < self._deck_len_base:
        removed = self._deck_len_base - n_now
        reward += self._reward_remove * removed
        self._ep_removes += removed
    self._deck_len_base = n_now
belt_now = sum(1 for p in run.potions if p is not None)
if belt_now > self._belt_base:
    self._ep_potions_obtained += belt_now - self._belt_base
elif belt_now < self._belt_base:
    self._ep_potions_used += self._belt_base - belt_now
self._belt_base = belt_now
```

Known accepted wrinkles (document in the docstring): an upgraded card taken from a reward counts as +upgrade_level upgrades (it IS acquired power); a transform (remove+add in one step) nets zero removals; a potion SOLD counts as "used". None of these are worth extra machinery.

`_info` — add the five new keys to the episode-end block (`run_env.py:1457-1464`).

- [ ] **Step 4: New tests + full suite green.**
- [ ] **Step 5: Stage** — `git add sts2_rl/run_env.py test/test_v7_rewards.py`

### Task 7: Thread new tallies through training (EnvSpec, EP_METRIC_KEYS, train CSV, CLI)

**Files:**
- Modify: `sts2_rl/vec_env.py` (`EnvSpec`, `build_env`, `EP_METRIC_KEYS` :109-110), `train_torch.py` (arg parsing near :190-288, `env_spec()` :362-373, and the CSV/logging consumer of `EP_METRIC_KEYS` — grep `energy_unspent` in `train_torch.py`)
- Test: extend the Task 5 EnvSpec test

**Interfaces:**
- Produces: `EnvSpec` fields `floor_rewards_by_act: tuple[float, ...] | None = None`, `reward_win_run: float | None = None`, `reward_upgrade: float = 0.0`, `reward_remove: float = 0.0`, `reward_elite: float = 0.0`, `deck_random_prob: float = 0.0`; CLI flags `--floor-rewards A B C`, `--reward-win X`, `--reward-upgrade X`, `--reward-remove X`, `--reward-elite X`, `--deck-random-prob P` (run/column only, same guard pattern as `--branch-prob` at `train_torch.py:285-287`); `EP_METRIC_KEYS += ("ep_upgrades", "ep_removes", "ep_elites_won", "ep_potions_obtained", "ep_potions_used")` and matching train-CSV columns `upgrades, removes, elites, potions_got, potions_used`.

- [ ] **Step 1: Failing test** — EnvSpec with `reward_upgrade=0.5, floor_rewards_by_act=(1.0, 1.5, 2.0)` builds an env with `_reward_upgrade == 0.5` etc.
- [ ] **Step 2: Verify fails.**
- [ ] **Step 3: Implement.** `build_env` passes all six to both run-scale envs (`reward_win_run` maps to the env's existing `reward_win` kwarg only when not None, so the default stays 3.0). `EP_METRIC_KEYS` is consumed positionally by `StepBatch.metrics` — extend the tuple and follow every consumer (grep `EP_METRIC_KEYS` across the repo; the aggregation in `train_torch.py` mirrors how `energy_unspent`/`card_take` are pooled today — copy that pattern for the five new columns). `--floor-rewards` takes `nargs=3, type=float`.
- [ ] **Step 4: Tests + suite green; smoke-run** `.venv\Scripts\python.exe train_torch.py --env column --n-envs 2 --n-steps 32 --timesteps 2048 --save runs/_v7_smoke.pt --fresh --reward-upgrade 0.5 --floor-rewards 1 1.5 2` → CSV has the new columns; delete `runs/_v7_smoke.*`.
- [ ] **Step 5: Stage.**

### Task 8: Eval metrics — potions/upgrades/elites columns + per-card offer/take CSV

**Files:**
- Modify: `sts2_rl/run_env.py` (`_count_behavior` REWARD_CARD branch + `_info`), `sts2_rl/evaluation.py` (`evaluate_run` :346-431, `RunEvalReport` :~200-344), `eval.py` (episodes-CSV writer + report printer — grep `episodes.csv` / `hist.csv` in `eval.py`)
- Test: `test/test_v7_rewards.py` (extend), plus the existing evaluation test file (grep `RunEvalReport` in `test/`)

**Interfaces:**
- Consumes: info keys from Task 6.
- Produces: episodes CSV gains columns `upgrades, removes, elites, potions_got, potions_used`; a NEW `eval_<tag>.cards.csv` with rows `policy,card,offered,taken,take_rate`; `RunEvalReport` properties `potion_use_rate` (used/obtained pooled) and `card_take_counts: dict[str, tuple[int, int]]`.

- [ ] **Step 1: Failing tests** — (a) run-env test: after an episode where a card reward was taken, `info["ep_card_offer_ids"]` is a dict mapping card class-name → count and the taken card's name appears in `info["ep_card_take_ids"]`; (b) `RunEvalReport` aggregation test with hand-built tallies asserting `potion_use_rate` pooling (0.0 when nothing obtained) and cards-CSV row content.
- [ ] **Step 2: Verify fails.**
- [ ] **Step 3: Implement.** In `_count_behavior`'s REWARD_CARD branch (`run_env.py:914-918`): tally `self._ep_card_offer_ids[type(card).__name__] += 1` for every offered card, and the taken card's name into `self._ep_card_take_ids` (init both as `collections.Counter()` in `reset`; surface as plain dicts in `_info`'s episode-end block; class name, not display id — guaranteed unique per card class). These dict tallies are eval-only: do NOT add them to `EP_METRIC_KEYS` (flat float batching). `evaluate_run` collects them per episode; `RunEvalReport` merges. `eval.py` writes the cards CSV next to the episodes CSV and prints the 10 most-offered-never-taken cards (the archetype-forcing signal) plus `potion_use_rate` in the summary block.
- [ ] **Step 4: Tests + suite green.**
- [ ] **Step 5: Stage.**

### Task 9: Deck randomization (card exposure)

**Files:**
- Modify: `sts2_rl/run_env.py` (`__init__`, `reset`)
- Test: `test/test_v7_rewards.py` (extend)

**Interfaces:**
- Consumes: `reward_pool_card_ids` (`sts2_rl/cards/pool.py`, imported by `rewards.py:49`) and the card-id→instance construction `rewards.py` uses (read `rewards.py:319-370` and reuse its exact path); `EnvSpec.deck_random_prob` from Task 7.
- Produces: env kwargs `deck_random_prob: float = 0.0`, `deck_random_cards: tuple[int, int] = (4, 14)`.

Rationale: the policy only ever learns cards it drafts, and greedy drafting collapses to one archetype (72.9% take rate, one build). Randomized starting decks are domain randomization: every card gets combat playtime regardless of drafting policy, so card values are learned before drafting relies on them.

- [ ] **Step 1: Failing tests** — (a) `deck_random_prob=1.0` env: over 20 reset seeds, decks differ from the starter deck and from each other, sizes within starter+4..starter+14, every non-starter card's class appears in the Ironclad reward pool, upgraded copies only where `max_upgrade_level > 0`; (b) `deck_random_prob=0.0` (default): deck is byte-identical to a plain env's across 5 seeds, and — critical — the SAME rng stream: `env.reset(seed=5)` obs equals a default env's `reset(seed=5)` obs exactly (the `prob > 0.0` short-circuit must draw no rng, same trick as `branch_prob` at `curriculum_env.py:238-244`).
- [ ] **Step 2: Verify fails.**
- [ ] **Step 3: Implement.** In `reset`, after `self._run = self._make_run_state()` and BEFORE the driver greenlet starts:

```python
if self._deck_random_prob > 0.0 and self._rng.random() < self._deck_random_prob:
    self._randomize_deck(self._run)
```

`_randomize_deck`: draw `k = rng.randint(*self._deck_random_cards)` ids (with replacement) from the character's reward pool ids, build each card by the same id→class path `rewards.py` uses, upgrade each with probability 0.25 (`card.upgrade()` once, only if `card.max_upgrade_level > 0`), and append to `run.deck` with the plain deck-add used at run setup (the silent path AscendersBane uses in Task 2 — no hooks fire; there is no combat yet). Use `self._rng` for every draw.
- [ ] **Step 4: Tests + suite green.**
- [ ] **Step 5: Stage.**

### Task 10: Gimmick-fight probes (Decimillipede, The Insatiable, Test Subject)

**Files:**
- Modify: `sts2_rl/full_env.py` (`ascension` kwarg → `hooks.ascension`), `eval.py` (a `--gimmick-probes` mode), `sts2_rl/vec_env.py` (EnvSpec.ascension already flows; combat env gets it too, replacing the Task 5 combat-env rejection with real support)
- Test: extend `test/test_ascension.py`

**Interfaces:**
- Consumes: the three gimmick encounters, importable BY CONSTANT from the top-level package: `from sts2_rl.monsters import DECIMILLIPEDE_ELITE, THE_INSATIABLE_BOSS, TEST_SUBJECT_BOSS` (`monsters/__init__.py:136,149,199`). Do NOT resolve them through `vec_env.build_env`'s `ENCOUNTERS` dict — that one is `sts2_rl.monsters.overgrowth`'s registry only, and these three live in the hive (`"decimillipede"`, `"the_insatiable"`) and glory (`"test_subject"`) registries.
- Produces: `eval.py --gimmick-probes` → per-encounter win rate + mean HP lost over 100 seeded combats at the checkpoint's ascension, appended to the eval summary.

- [ ] **Step 1: Failing test** — `STS2FullCombatEnv(encounter=<decimillipede key>, ascension=9)` spawns monsters whose hooks report ascension 9 (assert via a spawned monster's asc-gated HP once Task 4 lands its values).
- [ ] **Step 2: Verify fails.**
- [ ] **Step 3: Implement.** Combat env: add an `ascension: int = 0` kwarg to `STS2FullCombatEnv` and pass it straight through to the `CombatState(...)` construction at `full_env.py:1430-1435` — **`CombatState` already accepts `ascension` and seeds `hooks.ascension` before `create_monsters` (`combat.py:141,180`, landed by Phase A). Do NOT set `hooks.ascension` yourself after construction; that ordering bug was already caught once in review** (HP rolls read it at spawn). Also relax `eval.py:452-453`, which currently rejects `--ascension` for `--env combat`, so the probe path can pass one. `eval.py --gimmick-probes`: for each of the three encounter keys, build the combat env at `args.ascension`, roll 100 seeded episodes with the loaded policy (reuse the existing combat-eval path — grep `evaluate(` in `eval.py`), print `encounter, win_rate, mean_hp_lost`. These fights were chosen because Perry watched the bot fail their mechanics specifically; the probe turns "couldn't understand the gimmick" into a tracked number.
- [ ] **Step 4: Tests + suite green.**
- [ ] **Step 5: Stage.**

---

# Phase C — The v7 training run

### Task 11: `train_curriculum_v7.ps1`

**Files:**
- Create: `train_curriculum_v7.ps1` (model on `train_curriculum.ps1:1-153` — same resume/handoff logic: a stage seeds from the previous stage's checkpoint only when its own file doesn't exist)
- Modify: none

**Interfaces:**
- Consumes: every flag from Tasks 5/7/9.
- Produces: checkpoints `runs/sts2_run_torch_v7_s1.pt` … `_s5.pt`; per-stage CSVs.

Stage table (all stages: `--env run --arch entset --shared-encoder --n-envs 64 --n-steps 512 --floor-rewards 1.0 1.5 2.0 --reward-win 12 --reward-upgrade 0.5 --reward-elite 0.5 --reward-remove 0.25`):

| Stage | Asc | `--deck-random-prob` | Steps | Extra flags | Purpose |
|---|---|---|---|---|---|
| s1 | 0 | 0.50 | 4M | `--lr 6e-4 --critic-warmup 40` | reward re-baseline on known difficulty; seeds from a COPY of `runs/sts2_run_torch_v6.pt` |
| s2 | 4 | 0.50 | 5M | `--lr 6e-4 --critic-warmup 15` | map/economy ascensions (8 elites, 80% heal, −gold, −1 belt slot, Bane) |
| s3 | 7 | 0.25 | 5M | `--lr 6e-4 --critic-warmup 15` | + inflation, scarcity |
| s4 | 10 | 0.25 | 8M | `--lr 3e-4 --critic-warmup 15` | + tough/deadly enemies, double boss |
| s5 | 10 | 0.00 | 10M | `--lr 3e-4 --ent-coef 0.01 --ent-coef-final 0.004` | polish: on-policy decks only, entropy anneal |

Design notes (encode as script comments):
- Fixed ascension per stage — no obs field, so mixed-asc sampling would be unobservable noise. Difficulty is implicitly visible (enemy HP, previews, belt size, Bane).
- `--critic-warmup` at EVERY boundary: s1 because the reward scale roughly triples (`train_torch.py:226-233` exists precisely for this), s2–s4 because each asc bump shifts the return distribution down.
- `--reward-win 12` ≈ 15% of a full-clear return (~78), vs v6's 6% — dying to the final boss must actually sting.
- Same `env_kind="run"` throughout — checkpoints resume freely; the ascension stamp only WARNS (Task 5).
- v6's stage-5 checkpoint is the seed: 35M steps of asc-0 competence (act 3 in 22% of episodes) is a far better prior than `--fresh`, and the reward change mostly REORDERS good behaviors rather than redefining them. Fallback if s1 collapses (rule below): restart s1 `--fresh` and accept the longer schedule.

- [ ] **Step 1: Write the script** (clone v6's structure: per-stage checkpoint naming, first-run handoff copy, `--timesteps` per stage, same PowerShell 5.1 constraints).
- [ ] **Step 2: Dry-run gate** — run s1 with `--timesteps 65536` against a scratch save path; confirm resume-from-v6 handoff message, new CSV columns, no crash; delete scratch files.
- [ ] **Step 3: Stage the script** — `git add train_curriculum_v7.ps1`

### Task 12: Launch, gates, and rollback rules

**Files:** none created — this is the operating procedure. Record results in `docs/superpowers/plans/v7-run-log.md` (create on first gate).

- [ ] **Step 1: Launch s1.** Before launching: full suite green, Tasks 1–11 staged.
- [ ] **Step 2: Per-stage eval gate.** After each stage:

```powershell
.venv\Scripts\python.exe eval.py --env run --episodes 150 --baselines --ascension <stage asc> `
  --load runs/sts2_run_torch_v7_s<N>.pt --csv runs/eval_v7_s<N> --gimmick-probes
```

Gates (advance only when met; otherwise extend the stage by 2M steps once, then stop and reassess):
- **s1:** `rest_upgrade_rate ≥ 0.15` (v6: 0.003 — THE headline fix), `win_rate ≥ 0.03` (parity with v6 at asc 0), cards CSV shows ≥ 60% of pool cards taken at least once across 150 episodes.
- **s2–s4:** `ep_ret` recovered to ≥ 70% of the previous stage's final `ep_ret` (raw returns aren't comparable across asc, so the criterion is within-stage recovery: the dip after the asc bump must be regained before advancing); training-CSV `upgrades` per episode not declining stage-over-stage.
- **s5 (final):** at asc 10 — `rest_upgrade_rate ≥ 0.25`, `energy_unspent per end-turn ≤ 0.15` (v6: 0.23), `potion_use_rate` reported (baseline it — no target yet, first-ever measurement), gimmick-probe win rates strictly above the v6 checkpoint's on all three, and win_rate reported honestly (no target: nobody has ever trained this sim at asc 10).
- **Rollback rule (any stage):** if `ep_ret` drops > 50% from the stage's start value and hasn't recovered within 100 iterations, stop; restart the stage from the previous stage's checkpoint with `--critic-warmup` doubled and lr halved. (The obs-v4 incident showed one bad epoch can cost more than the warmup ever would — `train_torch.py:307-329`.)
- [ ] **Step 3: Final deliverables.** `eval_v7_s5.{episodes,hist,cards}.csv`, run log with every gate's numbers, and a v6-vs-v7 comparison table at asc 0 AND asc 10 (run the v6 checkpoint through the same eval commands for the asc-0 side).

---

## Explicitly out of scope (and why)

- **Ascension in the observation** — needless schema migration; stages are fixed-asc. Revisit only if a single checkpoint must serve multiple ascensions.
- **Potion-use reward shaping** — "+X for drinking at the right time" is unspecifiable without solving the game; measurement + difficulty pressure first. Revisit after s5 numbers exist.
- **Missed-lethal detector** — needs forward search over card orderings; a metric this expensive doesn't belong in the hot path. `energy_unspent` + gimmick probes are the proxies.
- **Asc-10 conformance seed** — no captured asc-10 run exists to replay; asc mechanics are covered by unit tests + citations instead. Capturing one in-game (any Ironclad asc-10 run) would upgrade Phase A to replay-grade verification — worth doing, not blocking.

## Execution notes

- Original task order: 1 → 2 → 3 → (4 wave ∥ 5, 6, 7, 8, 9) → 10 → 11 → 12. **Superseded: Tasks 1–5 are done.** Remaining order is 6 → 7 → 8 → 9 → 10 → 11 → 12.
- Task 7 no longer needs to add `EnvSpec.ascension` or the `--ascension` flags — Phase A's Task 5 landed both. Add only the v7 reward/deck-randomization fields and flags alongside them.
- Phase B (Tasks 6–9) fixes the rest-site pathology and card exposure independently of ascension, so it is verifiable at asc 0 before any asc-10 training.
