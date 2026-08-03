# Entity obs schema — Phase 3 (training/curriculum riders) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan
> task-by-task. NOTE: this project's protocol REPLACES the commit steps —
> NOTHING is ever committed; the controller stages approved work with
> `git add <files>`. Implementer lanes are forbidden ALL git mutation.

**Goal:** Ship phase 3 of prompts/entity-obs-schema.md — R11 (mid-run
start-state distribution for the combat env), R12 (re-measure the existing
subprocess workers), R13 (measured critic-side auxiliary head), and the
evaluation rider (run-scale micro-probes + paired-seed A/B) — with no
observation-schema impact.

**Architecture:** R11 splits into (a) widening `STS2FullCombatEnv` to pass
through the rich start-state kwargs `CombatState` already accepts, (b) a
snapshot dataclass/dataset module with lossless JSON round-trip, (c) a
harvest hook on `RunDriver` + a `harvest.py` CLI, (d) reset()-time sampling
wired into the env and `train_torch.py`. R12 is measurement-only (the
worker machinery already ships, off by default). R13 adds an optional,
flag-gated auxiliary win-probability head measured by paired-seed A/B. The
eval rider adds `run_probes.py` (fixed scenarios via `_make_run_state`
override) and a paired-seed compare layer over `evaluate_run`.

**Tech Stack:** Python 3.13 via the `py` launcher, pytest, torch (cuda),
existing sts2_rl engine/env/trainer modules.

## Global Constraints

- **NEVER commit or push.** Controller stages approved tasks with
  `git add <files>`. Lanes are forbidden `git commit/push/add/stash/
  checkout/reset/restore` — all git mutation.
- Full suite: `py -m pytest test -q --ignore=test/test_conformance_floor_state.py`.
  Baseline **4455 passed / 6 xfailed / 0 failed** (verified 2026-08-02 on
  HEAD 2dc0445). That ignored file's 2 failures are a missing fixture —
  never "fix" or count them. Controller reruns the FULL suite after every
  task; every wave boundary must be green.
- `py` launcher only (`python` is not on PATH). The decompiled game source
  (c:\Users\Perry\Desktop\Slay the Spire 2) is read-only authority.
- **The run-env step() hang is owned by the concurrent source-fidelity
  audit.** Nobody diagnoses it, nobody papers over it with
  timeout-and-truncate inside env/training semantics. The harvester's
  watchdog (Task 4) LOGS and ABORTS loudly with a reproducible
  (seed, episode, decision) record — it never silently skips an episode
  and continues, and it never truncates an episode into the dataset.
- **No old-vs-new comparisons in any form** (user decision 2026-08-01).
  All measurements are within-new-stack, one variable apart, paired seeds.
- Observation schemas are FROZEN at combat 6 / run 9 — nothing in phase 3
  may change any obs layout, width, or `OBS_SCHEMA_VERSION`.
- `models.ENTSET_HEAD_VERSION` stays 4 unless a task changes the action
  head's parameter structure or ActionLayout semantics (no phase-3 task
  should). R13's aux head is critic-side, flag-gated, and stamped
  separately (like `shared_encoder`), NOT a head_version bump.
- Test premises: lanes test the brief's premises rather than confirm them;
  the code wins over the brief. Mutation checks ("would this test fail if
  the code were wrong?") are done via **runtime monkeypatch in scratch
  scripts only** — never by editing tracked files, not even
  edit-then-restore.
- New tests must be able to fail: every invariant test needs a
  demonstrated RED (via monkeypatch mutation) recorded in the lane report.
- Windows: never create shell-redirect artifacts named `NUL`; redirect to
  scratchpad files instead.

## Locked decisions (do not re-litigate in lanes)

1. **Snapshot fidelity contract.** A snapshot stores: deck as a list of
   `{id, upgraded, enchantment, affliction}` card records (NOT bare ids —
   inv-A: upgrades/enchantments don't survive the env's id-string path);
   relics as `{id, counter}` records in acquisition order; `hp`, `max_hp`;
   the potion belt as a **fixed-size slotted list** (`id | null` per slot —
   belt gaps are load-bearing); `act` (int) and `encounter_id` (string);
   plus provenance `{seed, floor, episode_decisions}`. Ascension is
   **explicitly out of scope** — it has zero combat-engine effect today
   (inv-A refutation; monsters are hardcoded asc-0). Format: JSON Lines,
   one snapshot per line, with a file-level `#header` first line carrying
   `{"snapshot_schema": 1}`.
2. **Rebuild goes through the existing constructors.** Cards via
   `make_card(id)` + explicit field restore; relics via the relic factory +
   counter restore; encounter via a complete id→`Encounter` registry
   resolved from the monsters packages (unknown id = loud `KeyError`,
   never skip). Fidelity is proven by obs-level round-trip tests (the
   rebuilt `CombatState`'s deck/relic/potion/hp obs rows match rows built
   from the source state), not by `repr` comparison.
3. **Env seeding contract.** `STS2FullCombatEnv` gains a dedicated
   snapshot RNG: `reset(seed=s)` seeds it `random.Random(s)` **separately**
   from `self._rng` (which keeps its existing semantics untouched). In
   snapshot mode the snapshot draw comes only from the snapshot RNG; the
   non-snapshot path is byte-identical to today (same draws from
   `self._rng` in the same order). Same seed + same dataset ⇒ same
   snapshot ⇒ same episode.
4. **Harvest hook is a callback, not a subclass.** `RunDriver` gains
   `on_combat_start: Callable[[RunState, Encounter], None] | None = None`,
   invoked in `_run_combat` immediately after `create_combat` and before
   the first decision. No behavior change when None. The harvester is a
   repo-root CLI `harvest.py` (pattern: train_torch.py / eval.py) driving
   `STS2RunEnv` episodes with `masked_random_run_policy` (default) or a
   checkpoint policy (`--checkpoint`, via the existing loader), armed with
   `faulthandler.dump_traceback_later` and a per-step
   `(seed, episode, decision_count)` log. **The initial dataset will be
   masked-random and therefore shallow (act 0-1)** — recorded as a known
   property, regenerable cheaply once trained checkpoints exist; the CLI
   supporting `--checkpoint` is what makes R11 durable.
5. **R12 is measurement only.** `SerialVecEnv`/`SubprocVecEnv` +
   `--n-workers` already exist, tested and wired (inv-C refutation of the
   spec's framing). No implementation lane. The controller measures serial
   vs `--n-workers 2/4/8` arms on paired seeds and decides: flip the
   default only on a clear win; otherwise record the numbers and update
   `resolve_n_workers`'s stale docstring math (a docs-only edit).
6. **R13 aux head design.** Critic-side terminal-win prediction: a
   `Linear(critic_trunk_out, 1)` built ONLY when `aux_win=True`; BCE loss
   `--aux-win-coef` (default 0.5 when enabled) against per-step labels =
   "this step's episode terminated in a win", with steps whose episode did
   not terminate inside the rollout **masked out of the loss** (no
   bootstrapped labels). Stamped `aux_win` in checkpoint payload;
   `check_checkpoint` refuses a mismatch honestly (same pattern as
   `shared_encoder`). Actor path and action head untouched. Keep only on a
   measured paired-seed win; on a null result DELETE the code and record
   the number in the ledger (spec's own instruction).
7. **Run-probe scoring contract.** `run_probes.py` mirrors `probes.py`:
   `RunProbe(id, description, build, check)` where `build()` returns a
   ready `STS2RunEnv`-compatible env parked AT the target decision (via a
   `_make_run_state` override subclass with pinned hp/deck/gold/floor),
   the policy is invoked on that decision until it resolves (bounded), and
   `check(env)` reads the resulting run state. A scripted oracle must
   score 1.0 and a scripted anti-oracle 0.0 on every probe (the
   anti-tautology gate).

## File ownership map

| Task | Files (Create/Modify) |
|------|----------------------|
| 1 | M `sts2_rl/full_env.py`; C `test/test_full_env_startstate.py` |
| 2 | C `sts2_rl/snapshots.py`; C `test/test_snapshots.py` |
| 3 | M `sts2_rl/full_env.py`, M `train_torch.py`, M `sts2_rl/checkpoints.py` (spec only if needed); M `test/test_full_env_startstate.py`, M `test/test_train_smoke.py` |
| 4 | M `sts2_rl/driver.py`; C `harvest.py`; C `test/test_harvest.py` |
| 5 | (controller) dataset at `runs/snapshots/random-v1.jsonl`, untracked |
| 6 | C `sts2_rl/run_probes.py`; C `test/test_run_probes.py` |
| 7 | M `sts2_rl/evaluation.py`, M `eval.py`; C `test/test_paired_eval.py` |
| 8 | M `sts2_rl/models.py`, M `train_torch.py`, M `sts2_rl/checkpoints.py`; M `test/test_models.py`, M `test/test_train_smoke.py` |
| 9 | (controller) R12 measurement; M `sts2_rl/vec_env.py` docstring only |
| 10 | (controller) R13 A/B + keep/delete |
| 11 | (controller) docs: RL_ARCHITECTURE.md, project ledger, this plan's ledger |

Waves: **W1** = Tasks 1, 2, 6, 7 (disjoint). **W2** = Tasks 3, 4
(disjoint from each other). **W3** = Task 8, and controller Task 5.
**W4** = controller Tasks 9, 10. **W5** = Task 11 + final whole-branch
review. Suite gate after every task.

---

### Task 1: Combat-env start-state pass-through

**Files:** Modify `sts2_rl/full_env.py`; Create `test/test_full_env_startstate.py`

**Interfaces produced:** `STS2FullCombatEnv.__init__` gains keyword-only
`relics: Sequence[Relic] | None = None`, `max_hp: int | None = None`,
`current_hp: int | None = None`, `deck_cards: Sequence[Card] | None = None`
(full-fidelity alternative to the id-based `deck`; mutually exclusive with
it, `ValueError` if both), `potion_slots: Sequence[str | None] | None = None`
(slot-preserving alternative to `potions`, mutually exclusive with it).
`_new_state` threads them into `CombatState(...)` (which already accepts
`relics`, `max_hp`, `current_hp` — inv-A, combat.py:124-140).

**Requirements:**
- Default construction (no new kwargs) must produce byte-identical
  observations to today for a fixed seed — pin with a golden-obs test
  (build obs at seed 0 before/after is not possible in one tree; instead
  assert the new kwargs' absence leaves `CombatState` called with exactly
  the same arguments, via monkeypatch capture).
- Fresh instances per reset: like today's `make_card` path, `deck_cards` /
  `relics` templates must be **copied per reset** (a combat mutates cards
  and relic counters; episode 2 must not inherit episode 1's mutations).
  Test: run one episode that upgrades/consumes state, reset, assert
  pristine.
- New-kwarg episodes: relics appear in `_relic_rows` obs (nonzero rows),
  hp/max_hp appear in the player obs floats, potion slots preserve gaps
  (slot 0 empty / slot 1 filled reflected in obs and in potion actions'
  mask).
- Mutation-check at least: the copy-per-reset test and the
  mutual-exclusion `ValueError`s.

---

### Task 2: Snapshot module

**Files:** Create `sts2_rl/snapshots.py`; Create `test/test_snapshots.py`

**Interfaces produced:**
```python
@dataclass(frozen=True)
class CardSnap: id: str; upgraded: bool; enchantment: str | None; affliction: str | None
@dataclass(frozen=True)
class RelicSnap: id: str; counter: int
@dataclass(frozen=True)
class Snapshot:
    deck: tuple[CardSnap, ...]
    relics: tuple[RelicSnap, ...]
    hp: int; max_hp: int
    potion_slots: tuple[str | None, ...]
    act: int; encounter_id: str
    provenance: dict  # {"seed": int, "floor": int, "episode_decisions": int}

def snapshot_from_run(run: RunState, encounter: Encounter) -> Snapshot
def save_snapshots(path, snapshots: Iterable[Snapshot]) -> None   # JSONL + header line
def load_snapshots(path) -> SnapshotDataset                        # validates snapshot_schema == 1
class SnapshotDataset:  # sequence-like
    def __len__(self) -> int
    def sample(self, rng: random.Random) -> Snapshot
def build_start_state(snap: Snapshot) -> dict   # kwargs for STS2FullCombatEnv/CombatState:
    # {"deck_cards": [Card...], "relics": [Relic...], "max_hp": int,
    #  "current_hp": int, "potion_slots": [...], "encounter": Encounter}
def encounter_registry() -> Mapping[str, Encounter]  # complete id->Encounter map, all acts
```

**Requirements:**
- Verify against the code (not the brief) exactly which card fields
  `card_obs`/deck rebuild need (`upgraded`, `enchantment`, `affliction`
  are the expected set per inv-A; if the code shows more instance state
  that survives to combat start, capture it and record the finding).
- `encounter_registry()` must cover every act's encounter pools (walk the
  monsters packages the way `full_env` builds `_OVERGROWTH`, extended to
  all acts); duplicate ids = loud error at registry build.
- JSON round-trip is lossless: `load(save([s])) == [s]`.
- Obs-level fidelity: build a `CombatState` with custom
  deck/relics/hp/potions (test may construct directly, as
  test_combat_obs_v4.py does), snapshot it via an intermediate `RunState`-
  free path — where `snapshot_from_run` needs a `RunState`, test it
  against a minimal constructed `RunState` (pattern: test_driver.py) —
  then `build_start_state` + rebuild, and assert the rebuilt state's
  deck/relic/potion/hp obs rows equal the source's.
- Unknown encounter id in `build_start_state` raises `KeyError` with the
  id in the message.
- Mutation checks: field-swap (upgraded flag dropped) must fail the
  round-trip test; registry poisoned with a colliding id must fail.

---

### Task 3: Env + trainer sampling integration

**Files:** Modify `sts2_rl/full_env.py`, `train_torch.py`; Modify
`test/test_full_env_startstate.py`, `test/test_train_smoke.py`
(append-only in the test files). `sts2_rl/checkpoints.py` only if the
env-spec threading requires it.

**Interfaces produced:** `STS2FullCombatEnv(snapshots=SnapshotDataset | None)`;
`train_torch.py --start-snapshots PATH` (combat env only; error on run
envs); `vec_env.EnvSpec` threading if needed so worker processes can load
the dataset by path (datasets must be passed as a PATH through EnvSpec,
loaded per-process — a `SnapshotDataset` object must not need pickling).

**Requirements:**
- Locked decision 3's seeding contract: dedicated snapshot RNG seeded from
  `reset(seed=...)`; non-snapshot path draws from `self._rng` exactly as
  today (prove with a monkeypatch capture of `self._rng` method calls, or
  an obs-equality test at fixed seed against a no-snapshots env).
- In snapshot mode, `reset()` builds the combat from
  `build_start_state(sampled)` — deck/relics/hp/potions/encounter all from
  the snapshot; determinism test: same seed + same dataset ⇒ identical
  obs; different snapshots actually get sampled across resets (dataset of
  2 distinguishable snapshots, both observed).
- `--start-snapshots`: smoke-test appended to test_train_smoke.py driving
  real `train_torch.main()` with a 2-snapshot temp dataset (pattern
  already in that file), asserting training runs and (via a captured env)
  snapshot starts occur. Record the dataset path in the checkpoint payload
  `args` as it already records other args (no refusal logic — a resumed
  run may legitimately swap datasets).
- No pickling of live `Card`/`Relic` objects across worker boundaries:
  if `--n-workers > 0` with `--start-snapshots`, each worker loads from
  path (test may exercise `SubprocVecEnv` with 2 envs / 2 workers, or
  justify why the EnvSpec path-threading test suffices).

---

### Task 4: Harvest hook + harvester CLI

**Files:** Modify `sts2_rl/driver.py`; Create `harvest.py` (repo root);
Create `test/test_harvest.py`

**Interfaces produced:** `RunDriver.on_combat_start` callback (locked
decision 4); `harvest.py` CLI:
`py harvest.py --episodes N --seed S --out PATH [--checkpoint CKPT]
[--watchdog-secs 120] [--log PATH]`.

**Requirements:**
- Callback: `None` default, zero behavior change (existing driver tests
  stay green); invoked once per combat, after `create_combat`, before the
  first decision, with `(run, encounter)` such that
  `snapshot_from_run(run, encounter)` captures the six facts. Test: drive
  a short seeded run (or invoke `_run_combat` directly per
  test_driver.py's pattern), assert the callback observed
  deck/relics/hp/act/encounter matching direct reads off the `RunState`.
- `harvest.py`: drives `STS2RunEnv` episodes; default policy
  `masked_random_run_policy`; `--checkpoint` loads via the existing
  loader (`load_torch_policy` / `load_agent` — verify the real name);
  hooks the driver callback through the env (find the seam: the env owns
  the driver — expose or thread the callback; smallest honest mechanism,
  no monkeypatching in production code).
- Watchdog: `faulthandler.dump_traceback_later(watchdog_secs)` re-armed
  per step; per-step `(seed, episode, decision_count)` line to `--log`.
  On a watchdog trip the process dies loudly (faulthandler's default) —
  the report/log makes it reproducible; snapshots already written remain
  valid. NO timeout-and-continue.
- Snapshots stream to `--out` incrementally (append per combat, flush) so
  an abort loses nothing already harvested.
- Test: 2-episode harvest at fixed seed into tmp_path produces a loadable
  dataset whose every snapshot round-trips through `build_start_state`
  without error; snapshot count == number of combats the driver entered.
- Mutation check: break the callback threading (monkeypatch it to None)
  and assert the harvest test would catch an empty dataset.

---

### Task 5 (controller): initial dataset harvest

`py harvest.py --episodes 400 --seed 0 --out runs/snapshots/random-v1.jsonl
--log <scratchpad>/harvest-run.log` (untracked output; regeneration
documented in the ledger). Sanity checks: dataset loads; size > 400
snapshots (multiple combats per episode); act histogram and hp
distribution recorded in the ledger; spot-check 3 snapshots rebuild into
working combat envs (one full masked-random episode each). If the watchdog
trips: record (seed, episode, decision, stack) in the ledger as an audit
handoff, do NOT debug, and re-run from the next seed to fill the budget.

---

### Task 6: Run-scale micro-probes

**Files:** Create `sts2_rl/run_probes.py`; Create `test/test_run_probes.py`

**Interfaces produced:**
```python
@dataclass(frozen=True)
class RunProbe: id: str; description: str; build: Callable[[], Any]; check: Callable[[Any], bool]
RUN_PROBES: tuple[RunProbe, ...]   # >= 3 probes
def run_run_probe(probe, policy, max_actions=40) -> bool
def run_probe_accuracy(policy) -> float
```

**Requirements:**
- At least 3 probes with one clearly-right decision each, built via a
  `_make_run_state`-override subclass (locked decision 7) with pinned
  state; spec's exemplars: (a) REST at critically low HP where the
  alternative path is lethal-adjacent — check: policy rests (hp healed);
  (b) shop with exactly enough gold where buying the removal is dominant
  — check: removal purchased; (c) card reward with one on-curve card vs
  traps — check: the right card added (or an equally crisp trio the state
  machinery actually supports — the probe set may deviate from the
  exemplars if the code makes a cleaner dominant-option scenario, record
  why).
- Determinism: `build()` twice ⇒ identical first obs.
- Oracle gate: a scripted per-probe oracle policy scores 1.0, a scripted
  anti-oracle scores 0.0 (anti-tautology — proves check discriminates).
- Illegal actions / never-resolving decisions fail the probe (mirror
  `run_probe`'s contract).
- No edits to run_env.py/driver.py — probes compose existing override
  points only.

---

### Task 7: Paired-seed A/B layer

**Files:** Modify `sts2_rl/evaluation.py`, `eval.py`; Create
`test/test_paired_eval.py`

**Interfaces produced:**
```python
EVAL_SEEDS: tuple[int, ...]           # fixed canonical set, e.g. tuple(range(1000, 1200))
@dataclass(frozen=True)
class PairedRunDelta:  # per-seed floors/victory/hp deltas + aggregates
def compare_runs(policy_a, policy_b, *, seeds=EVAL_SEEDS, env_factory=...) -> PairedRunDelta
```
`eval.py --env run --compare CKPT_A CKPT_B [--episodes N]` prints per-seed
deltas (floors, win, hp_left), aggregate mean/median delta, and the
win/loss/tie seed counts.

**Requirements:**
- Reuse `evaluate_run` per seed (episodes=1 per seed, or refactor
  minimally — do not fork its logic); both arms run the SAME seed list.
- Determinism regression test: same policy both arms ⇒ all deltas exactly
  zero (this is also the mutation-sensitive test — a seed-pairing bug
  breaks it).
- CLI: `--compare` mode errors cleanly on env kinds it doesn't support;
  keep existing eval.py behavior byte-identical when `--compare` absent.
- Tests use cheap policies (masked-random with distinct seeds), tiny seed
  slices (override `seeds=`), never load a real checkpoint.

---

### Task 8: R13 auxiliary win head (flag-gated)

**Files:** Modify `sts2_rl/models.py`, `train_torch.py`,
`sts2_rl/checkpoints.py`; Modify `test/test_models.py`,
`test/test_train_smoke.py` (append-only)

**Interfaces produced:** `EntitySetActorCritic(aux_win: bool = False)`
adding `self.aux_win_head = Linear(critic_hidden_out, 1)` only when
enabled, and `aux_win_logit(obs) -> (batch,)`; `train_torch.py
--aux-win --aux-win-coef 0.5`; payload stamps `aux_win`;
`check_checkpoint` refuses mismatch (exact `shared_encoder` pattern, same
refusal ordering slot); `ModelSpec`/`make_model`/`spec_from_checkpoint`
threading.

**Requirements (locked decision 6):**
- Labels: after rollout, per-step binary "episode ended in a win", filled
  backward from each termination inside the rollout; steps belonging to
  episodes that did NOT terminate within the rollout are masked out of
  the BCE loss. Implementation lives in train_torch.py beside GAE; the
  win signal reuses the existing success bookkeeping (`successes` in
  StepBatch — verify semantics: success == combat win for the combat env).
- Loss: `aux_coef * BCE(aux_logit[mask], labels[mask])` added to the
  critic loss term only when `--aux-win`; zero interaction with the
  actor/entropy/KL terms; a rollout with NO completed episodes contributes
  zero aux loss (guard the empty mask — no NaN).
- Default-off path: model construction, parameter count, checkpoint
  payload and training trajectory are IDENTICAL to today when the flag is
  off (parameter-count equality test + smoke).
- Gradient test in test_train_smoke.py: with `--aux-win`, aux head weights
  receive nonzero grads; without, the attribute doesn't exist.
- Label-correctness unit test: hand-built tiny rollout (2 envs × few
  steps, one env wins mid-rollout, one truncates unfinished) ⇒ exact
  expected label/mask tensors. Mutation check: flip the backward-fill
  direction, test must fail.
- This task must NOT touch ENTSET_HEAD_VERSION, ActionLayout, or the
  actor path.

---

### Task 9 (controller): R12 measurement + decision

Paired-seed arms on the quiet machine (same discipline as R10's
measurement): combat env AND column env, `--device cuda`, `--n-envs 8`
and `--n-envs 32`, seeds 1/2/3, `--timesteps 16384`, arms
`--n-workers 0` vs `2` vs `4`. Decision gate: flip `resolve_n_workers`'s
default only if workers win mean sps on BOTH env kinds at the training-
realistic size (32 envs) across all seeds with no stability regression;
otherwise leave default, and in either case rewrite the stale
docstring math in `sts2_rl/vec_env.py` with the new measured numbers
(docs-only edit, controller does it inline). Record everything in the
ledger. Note: combat + snapshots interaction is Task 3's EnvSpec path —
if Task 5's dataset exists, one arm should exercise
`--start-snapshots` under `--n-workers 2` as a smoke, not a benchmark.

### Task 10 (controller): R13 A/B + keep/delete

Paired seeds 1/2/3, combat env, cuda, 8 envs, `--timesteps 16384`
(R10's exact probe shape): `--aux-win` off vs on. Compare win-rate
trajectory / final win rate / ep_ret; sps as a secondary. Combat probes
sit near ceiling (~0.95 win at this budget — R10's data), so ALSO run the
column env at the same budget as the sample-efficiency-sensitive arm
(floors reached is the metric there). KEEP only on a clear win in the
sample-efficiency metrics on the majority of paired seeds with no
regression elsewhere; on a null/negative result, dispatch one removal
lane to delete the R13 code cleanly (or controller reverts the unstaged
task if nothing else touched those files) and record the numbers either
way. The spec's instruction is explicit: delete on null, record the
number.

### Task 11 (controller): docs + final review

- RL_ARCHITECTURE.md: env layer gains the snapshot start-state paragraph
  (combat env section), trainer section gains `--start-snapshots`,
  `--n-workers` re-measured numbers, `--aux-win` outcome (present or
  "measured and deleted, numbers in ledger"), evaluation layer gains
  run probes + paired-seed compare.
- Project ledger (docs/superpowers/plans/2026-08-01-entity-obs-schema.md):
  append a "Phase 3" section in the same style as the phase-2 section:
  what shipped, decisions, defects caught by lanes, suite trajectory,
  measurement tables, R12/R13 verdicts.
- Final whole-branch review on the strongest model over the full phase-3
  diff (review package from the staged-tree state), fed the minor-findings
  roll-up from the execution ledger.
- Memory file update.

---

## Self-review notes

- Task 1 and Task 3 both modify full_env.py — sequenced in different
  waves (W1 vs W2), never concurrent.
- Task 3 and Task 8 both modify train_torch.py + test_train_smoke.py —
  W2 vs W3, sequential.
- Type consistency: `Snapshot.potion_slots` (`tuple[str | None, ...]`)
  matches Task 1's `potion_slots` kwarg; `build_start_state` returns the
  kwargs Task 1 defines; Task 4's callback signature matches
  `snapshot_from_run(run, encounter)`.
- Spec coverage: R11 = Tasks 1-5; R12 = Task 9 (+ inv-C's finding that
  implementation already exists); R13 = Tasks 8+10; eval rider = Tasks
  6-7; docs/review = Task 11. Hang gate honored via Task 4's
  watchdog/logging design and Task 5's abort protocol.
