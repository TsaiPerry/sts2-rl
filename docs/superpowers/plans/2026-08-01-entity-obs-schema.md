# Entity observation schema — progress ledger

Execution of `prompts/entity-obs-schema.md`. **This ledger is authoritative
over anyone's recollection, including mine.** One section per phase; every
number in it was measured, and the command that measured it is written next to
it.

Phases, and the rule that orders them: the from-scratch retrain is paid exactly
once, so anything that would force a second schema bump ships inside phase 1–2,
and anything with no schema impact is deferred to phase 3.

| phase | state | what it is |
|---|---|---|
| **0 — power instances** | **DONE 2026-08-01**, staged, awaiting review | `creature.powers` holds instances; obs untouched |
| 1 — integer obs schema | not started | + riders R1–R4, R6 (R5, R7 cut/deferred) |
| 2 — encoder + tied head | not started | + riders R8–R10 |
| 3 — training/curriculum | not started | R11–R13, one report each |

---

## Baseline measurements (captured 2026-08-01, pre-phase-1)

The prompt's *Measurement* section says to capture these before tearing
anything down. Phase 0 tears nothing down — the observation is byte-identical
and every checkpoint still loads — so only the cheap half is captured here.

> **Both checkpoint-derived baselines are CUT — user decisions, 2026-08-01,
> now folded into the prompt's own "Measurement" section.**
>
> First the checkpoint score, verbatim: *"the original simulation was missing
> multiple key components. you don't have to have a baseline."* That check is
> only meaningful if the environment it measured was the same environment. It
> was not — phase 0 alone changed engine behaviour, and the fidelity rounds
> before it changed far more. A number produced by a policy trained against a
> materially different simulator cannot separate "the new representation is
> worse" from "the simulator got more correct", which is the only question the
> baseline existed to answer.
>
> Then trainer sps, verbatim: *"i've decided that the sps baseline is
> irrelevant because of a full retrain."* The one figure taken (below) was
> measured under CPU contention and is unusable; re-taking it quietly is not
> worth gating on.
>
> **What replaces them is cheaper and strictly more diagnostic**, because it
> is *representation-independent*: masked-random env statistics over a fixed
> seed set. A random policy never reads the observation, so those numbers
> depend only on the engine, the action layout, the mask and the reward —
> exactly the surfaces the restructure must not move. Captured before,
> re-run after, diffed **per seed**. See "Pre-restructure env baseline" below.

### Observation payload (measured, `env.reset(seed=0)` → `np.float32`)

| env | obs_dim | bytes/env/step | n_actions |
|---|---|---|---|
| `STS2FullCombatEnv` (hybrid) | 17,873 | 71,492 (69.8 KiB) | 79 |
| `STS2CurriculumRunEnv` | 31,227 | 124,908 (122.0 KiB) | 1,385 |

Six widest combat segments, of 17,873 floats total:

| segment | floats | share |
|---|---|---|
| `draw_pile` | 1,280 | 7.2% |
| `discard_pile` | 1,280 | 7.2% |
| `exhaust_pile` | 1,280 | 7.2% |
| `player.powers` | 864 | 4.8% |
| `enemy0.powers` | 864 | 4.8% |
| `enemy1.powers` | 864 | 4.8% |

The prompt's "~117 KB/env/step" is the run env and re-measures at 122.0 KiB;
its 17,873-float combat total reproduces exactly.

### Measurement, final form (prompt rewritten 2026-08-01)

**There is no old-vs-new comparison in this project, in any form.** The
checkpoint score and the sps baseline were cut first; the *random-policy
before/after* idea — which this ledger proposed and which I built — was then
cut too, for the stronger reason:

> The riders change the action layout (R4), the observation contents
> (R1/R2/R3) and the encodings (R6); phase 2 changes how actions are scored
> (R8/R9). A delta across that many simultaneous changes attributes nothing —
> **and it does not survive even for a policy-free measurement**, because a
> masked-random policy over a *different action space* samples a different
> distribution. "Same seed, same result" is not a property the restructure
> should have, so asserting it would be asserting something false.

So `docs/baselines/*.pre.json` and `env_baseline.py compare` were **deleted**,
not kept "just in case". Keeping them would have left a loaded gun: the next
person to see a `.pre.json` would diff against it.

Validation is against **engine ground truth** instead, in two tiers:

1. **Observation-content assertions** — the real check. Decode the new
   integer observation and assert against direct `CombatState` / `RunState`
   reads. Lives in the test suite; a wrong offset or lossy field fails
   immediately instead of surfacing as a slightly-worse training curve.
2. **Absolute sanity floors** — `env_baseline.py sanity`, rewritten. Thresholds
   are deliberately WIDE and must never be tightened into regression
   detectors: a threshold tight enough to catch a regression fails on ordinary
   variance, and there is no controlled comparison to calibrate one against.

### `env_baseline.py sanity` — what it actually asserts

Grounded in measurement, not guessed:

- **Every episode completes**; no step offers zero legal actions; reward is
  not identically zero.
- **Floor / win-rate bands**, anchored on the pre-restructure numbers
  (column floor mean 4.6, max 13; combat masked-random win rate ~0.55) and
  then opened wide in both directions.
- **Decision-kind reachability.** Measured over 40 column seeds: `map`,
  `combat`, `event`, `reward_card`, `reward_potion`, `select_cards`,
  `select_option`, `shop`, `rest` are all reached; **`reward_relic` is
  not** — random play dies in act 0 and rarely clears an elite. So it is
  *reported, never asserted*; asserting an unreachable kind would fail the
  tool for a reason unrelated to the code under test. Asserted set is the
  five that are reliably hit. The combat env has no `DecisionRequest` at all,
  so the check is skipped there rather than failing.
- **Mask expressiveness**, and this one needed a real distinction. The naive
  check ("a decision with ≥2 options must have ≥2 legal actions") fires on the
  *current* env: measured 2 cases where SELECT_CARDS offered 3 identical
  `defend`s as 3 options with 1 mask bit. That is R4's collapse, observed
  live — but it is the **benign** variety, because picking any of three
  identical cards is the same outcome. So the check compares distinct
  candidate *signatures* (id, upgrade, enchantment, affliction, cost) against
  mask bits, which is the R4 bug stated precisely: information is lost only
  when collapsed candidates actually differ. This doubles as R4's acceptance
  test — afterwards, distinct signatures must always equal mask bits.

Combat passes at 60 seeds (win 0.550). Column at **400 seeds** produces two
findings worth more than the pass/fail bit:

**1. `reward_relic` is reachable — rarity, not breakage.** 9 occurrences in 400
seeds (0 in 40). Predicted from the source before measuring: it is raised only
by `RunDriver._reward_selector` (`driver.py:414-417`), whose callers all
require already holding a specific relic (Calling Bell, Black Star, Lava Rock,
Toy Box, Small Capsule) or hitting Crystal Sphere / War Historian Repy. **No
gap-queue entry: nothing is misbehaving.** The tool now prints a
`NEVER REACHED` line for any declared-but-unseen kind so the question stays
visible rather than being normalised into the required-set constant.

**2. R4's information-losing collapse is REAL and now has witnesses.** 4
decisions across 400 seeds where distinct candidate signatures exceed the mask
bits. Two, reproduced and inspected:

| seed | purpose | the loss |
|---|---|---|
| 75 | `from_discard` | 5 candidates including a **`nimble`-enchanted `defend`** among plain `defend`s → both map to `(defend, unupgraded)`, one mask bit. **The agent cannot choose to pull the enchanted Defend.** |
| 157 | `upgrade` | a **`spiral`-enchanted `strike`** among 4 plain strikes → **the agent cannot choose to upgrade the Spiral Strike.** |

The prompt argued this from the code ("copies differing by enchantment or cost
modifier are collapsed... an outright wrong answer"). It is now measured, on
live act-0 content, with named cards. It is an *action-space* defect — the
game lets the player click any candidate — so it is not a source-fidelity gap
and does not belong in `audit/GAP-QUEUE.md`; that queue tracks engine-vs-C#
divergences and `run_env._translate` has no C# counterpart.

It also cannot be missed, which is the real reason not to file it: it is a
tracked rider **and** `env_baseline.py sanity` now fails on it by design. The
failure message says so explicitly and names R4 as the fix, so a
permanently-red tool does not train anyone to ignore it — **this is R4's
acceptance test, and it must go green when R4 lands.**

### Superseded: the pre-restructure capture

`env_baseline.py` (new, repo root — it has to be re-runnable *after* the
restructure, so it is a project artifact, not a scratch script).

    py env_baseline.py capture --env column --seeds 300 --out docs/baselines/column.pre.json
    py env_baseline.py compare docs/baselines/column.pre.json docs/baselines/column.post.json

Per seed it records `decisions`, `reward`, `max_floor`, `max_act`, `victory`,
`hp_left`, `truncated`. `compare` diffs **every one of those, per seed**, and
exits 1 on any difference — a drift is an env regression, full stop.
`obs_floats` / `obs_bytes` are recorded but deliberately **excluded from the
diff**: they are supposed to change, and they double as the payload
before/after table the deliverables ask for.

Self-check on the gate itself, run before trusting it: identical files pass
(exit 0); a file with one `max_floor` and one `victory` tampered fails with
both differences named (exit 1). A comparison harness that has never been seen
to fail is not evidence.

The run-env hang is handled without papering over it: `--step-timeout`
(default 300 s) arms `faulthandler.dump_traceback_later` per episode, so a
wedged episode dumps the spinning greenlet's frames and exits non-zero, and
the output file — rewritten after *every* episode — already holds the seeds
that completed, so the first missing seed names the culprit. **No
timeout-and-truncate result ever enters the statistics**: a timed-out process
writes no summary at all. Per the user (2026-08-01), the hang itself is owned
by the concurrent source-fidelity audit, not by this project.

Captured pre-restructure: `docs/baselines/{combat,column,run}.pre.json`,
300 seeds each.

### Trainer throughput, old schema (SUPERSEDED — do not use)

The only surviving half of the Measurement section, and the one phase 2 is
actually judged on. `py train_torch.py --env {column,combat} --arch entity
--device cuda --timesteps 82000 --fresh --save <scratchpad>`, 32 envs × 512
steps (batch 16384), RTX 3070, torch 2.13.0+cu130, 5 iterations each:

| env | sps by iteration | median |
|---|---|---|
| `column` | 732, 729, 725, 718, 703 | **725** |
| `combat` | 707, 709, 710, 671, 636 | **707** |

> **Do not quote these as a baseline, and do not re-measure them.** They were
> taken while four census subagents and a census script saturated the same
> CPU, and the monotone decay inside each run is that contention, not a trend.
> The user has since dropped the sps baseline outright (full retrain), so this
> table is kept only as a record of the command line and the order of
> magnitude. Phase 2 reports the new arch's sps as an **absolute** figure, not
> as a delta against this.

- ~~`evaluate_win_rate` / `evaluate_run` / `evaluate_probes` on the current
  best checkpoint~~ — **cut.**
- ~~re-measure sps quietly before teardown~~ — **cut.**

---

## Phase 0 — `creature.powers` holds instances  (DONE 2026-08-01)

### What changed

`Creature.powers` was `dict[str, Power]`, one slot per power id.
`PowerCmd.apply` already dispatched on `PowerInstanceType` (round 14 closed
that half of `power_cmd/G5`), but an `Instanced` application could only
**overwrite** the slot: the displaced instance stayed hook-registered and kept
ticking toward its own expiry, while nothing could read it. Nine ported powers
were already `Instanced`/`InstancedPerApplier`, so this was live state loss,
not a latent one.

`sts2_rl/creatures.py` now defines **`PowerList`** — C#'s ordered
`List<PowerModel>` (`Creature.cs:34`) with C#'s own accessors:

| sim | C# (`Creature.cs`) | answers with |
|---|---|---|
| `id in creature.powers` | `HasPower(id)` (:561) | any |
| `creature.powers[id]` / `.get(id)` | `GetPower(id)` (:571) | **FirstOrDefault — the OLDEST** |
| `.instances(id)` | `GetPowerInstances(id)` (:581) | all with that id |
| `.values()` | `Powers` (:326) | every instance, application order |
| `.add(p)` / `.discard(p)` | `ApplyPowerInternal` / `RemovePowerInternal` (:600-612, :641-650) | append / remove **by identity** |

It is deliberately not a `Mapping`: `values()`/`items()` walk every instance
(what the hook walk, the death strip and the turn-start snapshot each need),
while `__iter__`/`keys()` yield each id once so `"minion" in c.powers` and
`set(c.powers)` read as before. `len()` counts instances, matching
`_powers.Count`.

Three behaviour changes fall out, each a fidelity fix:

1. **`get`/`[]` answer with the oldest, not the newest.** The dict answered
   with the newest. Every call site that configured *the power it had just
   applied* by re-fetching it by id was therefore silently correct before and
   would have been silently **wrong** after — so all six moved onto
   `PowerCmd.apply`'s **return value**, which is what C#'s `Apply<T>` hands
   back (`PowerCmd.cs:66-87`): `cards/colorless_skills.py` (The Bomb
   `SetDamage`), `cards/event_cards.py` (Toric Toughness `SetBlock`),
   `cards/crimson_mantle.py`, `cards/inferno.py`, `monsters/glory/knights.py`
   (Dampen `add_caster`), `monsters/hive/thieving_hopper.py` (Swipe
   `StolenCard`).
2. **`INSTANCED_PER_APPLIER` searches every instance** for one sharing the
   applier, which is what `PowerCmd.cs:168` does. The old code could only test
   the one visible slot, so with two appliers on one target a third
   application by the *first* applier started a third instance instead of
   stacking onto its own.
3. **Nothing is orphaned.** `Power._expire` and `PowerList.discard` remove by
   identity; the hook walk (`CombatState.cs:416`), `RemoveAllPowersAfterDeath`
   (:667-671) and `BeforeTurnStart`'s snapshot (:673-679) each see every
   instance.

`PowerCmd.apply` returns the instance it produced. One documented narrowing vs
`Apply<T>`, which is the already-filed dormant gap `card/the_bomb/g1`: C#
returns the constructed-but-unattached model when the post-modifier amount is
0 or the `CanReceivePowers` re-test fails; the sim returns `None`, which is
what every call site's existing `if power is not None` guard already reads.

### Workarounds retired

Both existed *only* because the dict could not hold two instances, and both
would have been left as actively misleading dead weight:

- **`TheBombPower`** — the `bombs` list of `(turns_left, damage)` fuses inside
  one `NONE` power. Now `INSTANCED`, `amount` is this instance's turn counter
  (C#'s `Counter` `StackType`), `damage` is its own `DynamicVars.Damage`, and
  `BeforeSideTurnEnd` is a straight port of `TheBombPower.cs:44-57`.
- **`SwipePower`** — the `stolen_cards` bucket. Now `INSTANCED` with one
  `stolen_card`, matching `SwipePower.cs:17`. Its three readers moved with it:
  the hopper's steal takes `apply`'s result, and both the escape hand-off and
  `RunState.finish_combat`'s deck reconciliation walk `instances("swipe")`.

**Swipe was beyond the literal brief**, which names The Bomb only. It is
included because it is the same class of workaround, because leaving it would
have left `power_cmd/G5` narrowable but not closable, and because its own
docstring's stated reason for not migrating ("`finish_combat` walks
`powers.get("swipe")` alone, so any steal but the last would stay in the run
deck") is exactly the constraint this change removes.

### Verification

| check | result |
|---|---|
| Full suite, `py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py` | **4144 passed / 6 xfailed / 0 failed** |
| Observation byte-identity vs the pre-change tree | **unchanged** (3 digests, `test/test_obs_byte_identity.py`) |
| `py audit/tools/gap_queue.py coverage` | 317 mechanisms / 333 entries, 0 unlocatable |
| `py audit/tools/gap_queue.py cite-check` | 91 citations, 0 problems |
| `harness.validate_record` on the 3 edited records | all VALID |

**Byte-identity is a golden, captured from the pre-change tree before any
edit** (`test/data/obs_identity_golden.json`): SHA-256 over the entire
`(obs, action_mask, reward, terminated, truncated)` stream of masked-random
episodes — 12 combat seeds × 2 `card_obs` modes, 4 curriculum-run seeds. It
pins the engine's behaviour on those episodes, not just the encoder. It was
verified deterministic across repeated runs before being trusted (see
`docs`-adjacent lesson: out-of-combat draws on the shared rng have made triage
deltas meaningless before). It did **not** move at any point during phase 0.

Caveat, stated because a green golden is easy to over-read: those episodes
never arm two Bombs or two Swipes, so the digests prove *no unintended drift*,
not *the bomb path is covered*. The bomb and swipe paths are pinned by
dedicated tests instead (`test_r14_power_cmd.py`, `test_colorless.py`,
`test_hive.py`, `test_power_instances.py`).

**Suite-count note.** The prompt's stated baseline is 4091 passed / 6 xfailed.
The tree measured 4133 collected *before* I touched anything — the prompt's
number is ~36 tests stale, not a sign that tests were lost. Ledger of my own
additions: +3 (`test_obs_byte_identity.py`), +13 (`test_power_instances.py`),
+1 (a second Bomb test) = 4133 → 4144. **Nothing was deleted.** Eleven tests
were *rewritten* because they pinned the old semantics:

- `test_powers.py::TestPowerInstanceType` ×8 — read `powers[id]` for "the
  instance I just applied"; they address instances explicitly now, which also
  makes them assert the thing phase 0 adds (both instances are visible).
- `test_powers.py::test_the_bomb_and_swipe_are_not_migrated_to_instance_type`
  — inverted into `test_every_c_sharp_instanced_power_declares_it`.
- `test_r14_power_cmd.py::test_two_fuses_merge_into_one_power_list_entry` —
  round 14's own witness for the gap, inverted into its closure test.
- `test_colorless.py::test_the_bomb_stacks_are_independent_fuses`,
  `test_exhaust_escape_removal.py` ×4 (dict item assignment), plus
  `test_hive.py` / `test_encounter_selection_rng.py` `stolen_cards` reads.

### Audit closes

`power_cmd/G5` — **CLOSED**. Both open sites closed with it
(`power/the_bomb/InstanceType`, `power/swipe/InstanceType`). Queue: 335 → 333
gap entries, 318 → 317 mechanisms, `power` live 1 → 0.

**Closed conservatively — one residue is explicitly NOT claimed.**
`full_env.py` still writes one `(presence, fine, coarse)` triple per power id,
so the *observation* shows only the newest instance. That is the RL schema,
which has no C# counterpart at all, so it is not a `PowerCmd` divergence; it is
phase 1's job and is pinned by
`test_power_instances.py::TestObservationResidue` so it cannot be forgotten.

Records edited and re-hashed (all three re-audited against both sides first,
per `audit/README.md`'s rule that a rehash without a re-audit is a decoration):
`seam/power_cmd`, `power/the_bomb`, `power/swipe`. `Creature.cs`,
`CombatState.cs`, `creatures.py`, `run.py` and `thieving_hopper.py` were added
to the records' `extra_sources` because the new verdicts rest on them.

### Handoffs — found during phase 0, deliberately NOT fixed

1. **`event/crystal_sphere`'s two entries still read `live: true` in the
   record** while `GAP-QUEUE.md` prose declares them CLOSED 2026-08-01. They
   are now the only 2 live entries in the whole queue. Round-14 loose end:
   either the records need the close folded in, or the prose is ahead of the
   code. Not mine to settle.
2. **`GremlinMerc` / `SurprisePower` iterate `GetPowerInstances<ThieveryPower>()`**
   (`GremlinMerc.cs:89,105,118`; `SurprisePower.cs:26`) where the sim reads a
   single `.get("thievery")`. C# needs the loop because the merc applies one
   Thievery **per Player** (`GremlinMerc.cs:50-55`); the sim is single-player,
   so exactly one instance exists and the two agree. Dormant-by-multiplayer,
   now trivially fixable with `.instances(...)` if a second player ever exists.
3. **`FranticEscape.cs:40` selects its Sandpit by
   `Powers.OfType<SandpitPower>().FirstOrDefault(s => s.Target == Owner.Creature)`**
   — a filter on the power's `Target`, which the sim does not model at all
   (`cards/frantic_escape.py` takes a plain `.get("sandpit")`). Identical while
   one sandpit exists per enemy; pre-existing, unrelated to instancing.
4. **The audit ledger is broadly stale** — 762 of 847 records, mostly from
   round 14's staged edits (`enchantment` is 19/19 stale and I touched no
   enchantment code). Phase 0 added to it by editing `cmds.py`, `powers.py`,
   `creatures.py`, `hooks.py`, `run.py` and five content files. Per
   `audit/README.md` the remedy is agent re-audit, never a bulk rehash; I
   re-audited and re-pinned only the three records whose verdicts I actually
   re-derived.
5. **`PowerCmd.remove` does not fire `on_removed`**, where `PowerCmd.Remove`
   awaits `power.AfterRemoved` (`PowerCmd.cs:287-295`). Pre-existing, out of
   phase 0's scope, noted because the surrounding code was rewritten.

### Files touched

Engine: `creatures.py` (`PowerList`), `cmds.py` (`PowerCmd.apply` dispatch +
return, `PowerCmd.remove` doc), `powers.py` (`Power._expire`, `TheBombPower`,
`SwipePower`), `hooks.py` (one stale docstring line), `run.py`,
`cards/colorless_skills.py`, `cards/event_cards.py`, `cards/crimson_mantle.py`,
`cards/inferno.py`, `monsters/glory/knights.py`,
`monsters/hive/thieving_hopper.py`.
Tests: `test_power_instances.py` (new), `test_obs_byte_identity.py` (new),
`test/data/obs_identity_golden.json` (new), `test_powers.py`,
`test_r14_power_cmd.py`, `test_colorless.py`, `test_hive.py`,
`test_exhaust_escape_removal.py`, `test_encounter_selection_rng.py`.
Audit: `GAP-QUEUE.md`, `records/seam/power_cmd.json`,
`records/power/the_bomb.json`, `records/power/swipe.json`.

**Staged, not committed** (CLAUDE.md §4).

---

## Phase 1 — the integer observation schema  (IN PROGRESS, 2026-08-01)

Nothing is implemented yet. This section is the **measurement and design
record**; it exists so the sizing constants in the eventual code each trace to
a number rather than a guess, per the prompt's "never trust a count stated in
prose, including in this file. Re-measure."

### The contract (decided, not yet built)

The observation stops being a flat float `Box` and becomes
`spaces.Dict({"f": Box(0,1,(F,),float32), "i": Box(0,MAX_ID,(I,),int32)})` —
the prompt's "float array plus a parallel int array", expressed as the
standard gymnasium Dict so wrappers and `check_env` keep working. Both halves
keep a named `(segment, width)` map exactly as today, because `--zero-segments`,
`models._segment_plan` and the pin tests all key off segment names.

Two rules make the int half self-describing, so there is **no third mask
array**:

1. **Stored id = frozen-vocab index + 1; `0` means PAD/absent.** `vocab.json`
   is untouched (index *i* still means the same id forever); the +1 lives at
   encode time. Embedding tables get `capacity + 1` rows with `padding_idx=0`,
   so an absent row contributes a zero vector to a masked sum-pool — which is
   exactly the pooling semantics wanted — and takes no gradient.
2. **A padded row is `id == 0` plus all-zero floats.** "Present at amount 0"
   stays distinguishable from "absent", which is what today's explicit
   presence bit buys.

Trainer blast radius (established by reading, not guessed): `obs_buf`,
`next_obs`, `b_obs`, `b_obs[mb]`, `final_obs` and the two
`agent.get_value` / `get_action_and_value` call sites in `train_torch.py`,
plus `_EnvGroup.obs_dim` / `StepBatch.obs` / the two `np.concatenate` sites in
`vec_env.py`. Plan: a small `TensorObs` pair type implementing
`__getitem__` / `__setitem__` / `reshape` / `to`, so the PPO loop text is
nearly unchanged and the break lives in **one** documented place.

### Measured 2026-08-01 — the surface to be rewritten

`grep -rln` over `test/` for
`obs_segments|obs_slices|OBS_SCHEMA|power_triples|pile_composition|card_features|damage_matrix|enemy_row|build_combat_obs|_build_obs|observation_space|numeric_obs_indices|run_obs_seg|run_obs_slices`:

**14 files**, not the prompt's "~20" — `test/run.py`, `test_curriculum_env.py`,
`test_eval_torch.py`, `test_full_env.py`, `test_map_obs_and_migration.py`,
`test_models.py`, `test_obs_byte_identity.py`, `test_obs_pins.py`,
`test_obs_vectorization.py`, `test_power_instances.py`, `test_printed_vars.py`,
`test_probes.py`, `test_run_env.py`, `test_unplayable_cost.py`.
Non-test consumers in the main tree: **9** — `sts2_rl/{__init__,checkpoints,
env,evaluation,full_env,models,run_env,vec_env}.py` and `train_torch.py`.
(The `.worktrees/*` copies are separate branches and are not in scope.)

Note `test_obs_byte_identity.py` is phase 0's golden. **Phase 1 changes the
observation on purpose, so its digests MUST move.** It is not a regression
detector for this phase; it gets re-pointed at the *old* arch path, which
survives as the A/B arm, or retired with a written justification for every
changed digest. Deleting it quietly is the failure mode to avoid.

### Measured 2026-08-01 — pile / deck / relic sizes

`scratchpad/census_piles.py`, 8 `STS2CurriculumRunEnv` episodes,
masked-random, 584 steps / 472 in-combat steps:

| quantity | max | p99 | mean |
|---|---|---|---|
| hand | 8 | 7 | 4.0 |
| draw pile | 14 | 13 | 4.9 |
| discard pile | 13 | 11 | 3.7 |
| exhaust pile | 6 | 5 | 0.3 |
| **all cards in combat** | **22** | 21 | 13.0 |
| deck | 18 | 18 | 12.6 |
| relics held | 6 | 6 | 2.5 |
| distinct card ids in deck | 10 | 10 | 5.4 |
| enemies alive | 4 | 3 | 1.2 |

> **These are FLOORS, not worst cases.** A masked-random policy dies in
> act 0: acts 1 and 2 were never reached in any of the 8 episodes. Every
> `MAX_*` sized off this table must add a static ceiling argument on top, and
> the deep-run distribution has to come from `acts=[...]` sweeps
> (`overgrowth`, `underdocks`, `hive`, `glory`) rather than from full runs.
> This caveat applies to every empirical census in this project.

Design consequence already visible: draw + discard + exhaust + hand is bounded
by *cards in combat*, one true invariant, so the three piles should share
**one** row block with a `pile` id field rather than three independently
guessed caps. That converts three loose bounds into one honest one.

### Measured 2026-08-01 — R2, card-instance state

Read from `sts2_rl/cards/base.py:213-262` (the `Card.__init__` attribute set),
`sts2_rl/afflictions.py`, `sts2_rl/enchantments.py`, and the game source:

- **Afflictions: 7 sim classes, 7 game `.cs` files — the vocabulary is
  complete.** `ringing`, `entangled`, `smog`, `tainted`, `galvanized`,
  `hexed`, `bound`. Each carries an `amount`; two (`tainted`, `galvanized`)
  are `is_stackable`. There is **no affliction registry** in the sim (unlike
  `enchantments._ENCHANTMENT_CLASSES`) — phase 1 has to add one, or build the
  frozen vocabulary off `Affliction.__subclasses__()`.
- **Enchantments: 19 sim, 22 in the game** (23 `.cs` files minus
  `DeprecatedEnchantment`). Unported: `Inky`, `Momentum`, `SlumberingEssence`.
  Capacity must be sized to the game total, not the ported count — same rule
  as every other vocabulary.
- Per-instance card state that is player-visible and NOT in today's obs:
  `affliction` (+ its `amount`), `enchantment`, `exhaust_on_next_play`,
  `_has_single_turn_retain`, `_has_single_turn_sly`, `base_replay_count`.
  `captured_x` / `energy_value` / `current_play_index` are live only *during*
  a play and are never observable at a decision point — out of scope.
- Cost is already covered: `card_features[0]` is
  `preview_card_energy_cost`, which folds `_cost_this_turn`,
  `_cost_this_combat`, `_cost_delta_this_turn` and `_free_this_turn`.
- **R2 is load-bearing on live content, not hypothetical**: in 8 act-0
  episodes, 95 enchanted card-instance observations (`glam` 75, `nimble` 20)
  and 6 cost-override observations, every one of which the current pile
  histogram collapses onto a plain copy of the same card. Afflictions were
  never observed in act 0 (they are applied by later-act powers).

### Measured 2026-08-01 — R3, enemy-slot identity stability

An enemy's observation row is addressed by **raw list position**
(`full_env.py:724-732`, `enemies[e_i]`), and the only identity in the row is
the monster **class** one-hot — two Bowlbugs are indistinguishable. Verified
directly:

- `combat.enemies` is **never removed from**. The only three mutation sites in
  the whole package are `cmds.py:836` (`append`), `cmds.py:838`
  (`insert(index, ...)`) and `combat.py:1289` (`sort`). So **death and escape
  do not shift indices** — a corpse holds its slot.
- But `insert` and `sort` do. Reported by the subagent and consistent with
  those three sites: `ovicopter_normal`, `fabricator_normal` and
  `living_fog_normal` move a live enemy's index mid-combat (the Ovicopter
  goes 0 to 3 in a single egg-laying turn).
- **`net_id` already exists and is the right key**: `monsters/base.py:170`,
  assigned 1..N at `combat.py:227-230` and continued for mid-combat spawns at
  `cmds.py:831-834`. It appears **0 times** in `full_env.py` — verified by
  grep — so it is available to the obs builder with no plumbing.

Consequence for R3: a per-slot ring buffer would silently misattribute history
in those three encounters. Any intent history must be keyed on `net_id`.
Independently, the buffer goes *stale without any index change* for
phase-changing monsters (Test Subject, Waterfall Giant, Queen, Decimillipede,
Lagavulin Matriarch, Slumbering Beetle, Living Shield, Knowledge Demon,
ToughEgg's hatch) — a per-creature "phase epoch" is the cheaper fix there than
history invalidation. **This raises R3's cost and is a point in favour of the
prompt's own instruction to cut it if it drags.**

### Measured 2026-08-01 — the static power-stacking ceiling

The empirical half of this census is still running; the **static** half is
done and is the half that actually binds, because a masked-random policy will
never build a stacked deck.

Verified at source (all four counts re-measured by me, not taken from the
report): `ALL_POWERS` = **138** distinct ids. The sim declares **11**
`instance_type` overrides (`grep -n "instance_type = PowerInstanceType\."
sts2_rl/powers.py`, excluding the base-class `NONE` at `:69`). The game
declares **21** overrides — a whole-`src/` grep returns 22 `InstanceType =>`
lines, of which one is the base virtual at `PowerModel.cs:144`, so 21
overrides and **10 unported**.

**Only 5 of the 11 ported instanced powers can ever exceed one instance, and
all 5 are player-side**: `the_bomb`, `panache`, `automation`,
`rolling_boulder`, `toric_toughness`. The other six are structurally
one-per-creature — `thievery` (one per Merc, applied once at spawn),
`heist` (one per Fat Gremlin), `swipe` and `sandpit` (the applying move is the
initial state of a follow-up chain that never returns to it),
`withering_presence` (C# makes one per opponent; one player ⇒ one), and
`strangle` (`INSTANCED_PER_APPLIER` with the player as the only ported
applier).

> **Consequence worth stating plainly: enemies never carry duplicate-id power
> instances in the current port.** Instance duplication is a player-only
> phenomenon over exactly 5 ids. That is a real constraint on how much the
> multi-instance rewrite can buy *today* — its value is fidelity and
> future-proofing, not a large immediate observation gain. (Phase 0 was still
> right to land: the state loss it fixed was real, and the exporter reads sim
> state, not the observation.)

`the_bomb` is the only power whose instance count grows from a **single** deck
copy — it is a 2E Skill, so it goes to the discard pile and one copy can be
replayed every turn, with each instance living 3 player turns. Every other
stacking power scales with copies drawn.

Distinct-id ceiling on one creature: **player ~30-35 defensible, ~48 as a
paranoid bound** (48 permanent player-landable ids exist but come from
mutually exclusive relics/events/pools); **enemy ~12-15**.

Of the 10 unported instanced powers, **6 are `MultiplayerOnly` or dead
content** and can never be reached single-player; 4 arrive with future
character ports (Monologue/Regent, Orbit/Regent, Nightmare/Silent,
Oblivion/Necrobinder).

> **Correction, settled at source.** Two independent static derivations
> disagreed about which unported power raises the ceiling. One said
> *Monologue*; the other said *Orbit*. The game decides: `MonologuePower.cs:81-85`
> is `AfterSideTurnEnd → PowerCmd.Remove(this)`, so Monologue **cannot**
> accumulate across turns, while `OrbitPower.cs` contains no `Remove` and no
> expiry hook at all. **`Orbit` is the one new unbounded stacker**; the earlier
> Monologue claim in this ledger was wrong and is retracted. Recorded because
> "two agents agreed on the shape" is exactly the situation where a wrong
> detail survives unchallenged.

### Measured 2026-08-01 — powers per creature, empirical

Method (worth recording, because it is stronger than sampling the
observation): `PowerList.add` was subclassed and hooked at runtime, so the max
is taken **at every append** rather than at step boundaries — that catches
peaks created and destroyed inside one enemy turn, which an obs-boundary
sample would miss.

| config | episodes | samples | max instances | max distinct | p99.9 |
|---|---|---|---|---|---|
| combat env, default deck, **all 80 encounters** (incl. every elite + boss) | 20,000 | 1,103,228 | **4** | **4** | 4 |
| combat env, adversarial stress (power-heavy deck, unkillable player) | 960 | 79,287 | **28** | **25** | 24 |
| `STS2CurriculumRunEnv`, honest masked-random | 3,000 | — | **5** | 5 | 3 |
| `STS2RunEnv` invincible, full 3-act | ~60 | — | **13** | 9 | — |
| `STS2RunEnv` invincible, single-act `hive` | 160 | — | **7** | 7 | — |

**The default deck never produces a duplicate power id at all** — instances
equal distinct in every one of 1.1M samples. The max of 4 saturated early and
stopped climbing. Witness: a `GremlinMerc` holding
`['surprise','thievery','vulnerable','strength']`.

The stress witness at 28 is the player under `waterfall_giant` holding
**4× the_bomb, 4× panache, 2× automation, 2× rolling_boulder** plus 17
singletons — i.e. the duplicate-instance tail is exactly the three unbounded
player powers plus The Bomb, as the static half predicted.

**Two honest caveats from the census itself**, both of which I am recording
rather than smoothing over:

- The honest column-run max of 5 is a **floor**: 3,000 masked-random episodes
  never left act 0 (median final floor 4). Everything past act 0 needed an
  invincible-player override.
- The 3-act invincible max was **still climbing** when the job died (9 → 12 →
  13 across batches), so **13 is a lower bound, not a converged maximum**.
  Several run-env processes also hung inside a single `env.step()` for >45
  minutes, costing the final distributions for the 3-act, `glory` and
  `underdocks` configs (`underdocks` produced no data at all). That hang is
  unexplained and is a handoff.

**Decision: `MAX_POWERS_PER_CREATURE = 32`**, and — the part that matters more
than the number — **truncate deterministically, never assert.** `panache`,
`automation` and `rolling_boulder` are unbounded in principle, so an
`assert len(powers) <= MAX` would turn a legal if exotic game state into a
training crash. Truncation keeps the **first** N of `powers.values()`, which is
C#'s `List<PowerModel>` application order (oldest-first) and matches what
`GetPower` / `FirstOrDefault` already returns everywhere else in the engine.
32 clears the adversarial peak of 28 by ~15%, covers the ~30 distinct-id
ceiling, is a power of two, and absorbs `Orbit` when it lands.

### Measured 2026-08-01 — R1, relic mutable state and its visibility

**Counts (re-measured):** `ALL_RELICS` holds exactly **259** registered relic
classes. Instantiating all 259 and diffing `__dict__` against the base gives
**70 stateful** (65 in `__init__`, 5 creating `_healed` lazily) and **189 with
no mutable state at all** — for those, presence alone is already a complete
description.

**The admissibility rule is mechanical, and that is what makes this census
trustworthy.** Exactly one code path draws a number on a relic icon —
`NRelicInventoryHolder.RefreshAmount`, `NRelicInventoryHolder.cs:116-119`,
gated on `RelicModel.ShowCounter` — and `RelicModel.cs:347/349` default
`ShowCounter => false` / `DisplayAmount => 0`, so display is strictly opt-in
per relic. One further path tints the icon from `Status`
(`RelicModel.cs:487-503`) and `IsUsedUp` rewrites the hovertip (`:365-369`).
Anything not reachable through those three is hidden information. **Verified
by reading all four citations**, plus `PenNib.cs:25` (`ShowCounter => true`)
and `:33` (`AttacksPlayed % 10`).

**Result: 32 relics expose a counter, ~18 expose a flag, and 7 relics expose
both.** The prompt's own example is confirmed: Pen Nib's count *is* on the
icon, and the sim already stores it modulo 10 (`pen_nib.py:34`), so it is
publishable as-is — the leading underscore is not a visibility signal.

**Row shape: `(relic_id, counter, flag)` — two aux fields, both load-bearing.**
No relic has two simultaneously-admissible counters (the nearest misses,
Pocketwatch and Silver Crucible, each hide their second). And the flag is
*not* derivable from the counter in at least two cases: `toy_box` shows
`combats_seen % 3` while used-up needs `combats_seen >= 12`, and
`wongos_mystery_ticket` pairs a countdown with a `gave_relic` bool set by a
reward roll. So neither field collapses into the other.

**Counter scaling: /10.** The maximum *statically bounded* admissible counter
is **9**, set by the three mod-10 relics (Nunchaku, Pen Nib, Tuning Fork);
everything else bounded is ≤6. Three counters are uncapped in the source and
must be clamped: `pocketwatch` and `diamond_diadem` (raw cards-played-this-turn
— an infinite-combo turn is unbounded) and `pumpkin_candle` (+5 per kindle,
−1 per combat). Clamping discards nothing a policy needs; those three relics'
own thresholds sit at 3, 2 and 1.

**Two traps that would silently leak if implemented naively:**

1. **Publish `raw % N`, never the raw attribute.** Seven relics store a
   cumulative count the UI only ever shows modulo something —
   `book_of_five_rings`, `iron_club`, `nunchaku`, `fishing_rod`,
   `lasting_candy`, `toy_box`, `paels_wing`. Publishing `fishing_rod`'s raw
   count would reveal total combats fought all run. Likewise the displayed
   value is an *inversion* (`N − x`) for `winged_boots`, `silver_crucible`
   and `wongos_mystery_ticket`, and a `len()` for `paels_tooth`.
2. **Eight counters are in-combat-only** — Kunai, Kusarigama, Letter Opener,
   Ornamental Fan, Shuriken, Velvet Choker, Diamond Diadem, Pocketwatch gate
   `ShowCounter` on combat being in progress. They must read 0 in the **run**
   observation and carry a value only in the **combat** observation.

**The exclusion list IS the non-leak test's fixture.** 16 relics whose state
has no display path at all — `beating_remnant`, `bing_bong`,
`centennial_puzzle`, `demon_tongue`, `dusty_tome`, `fake_orichalcum`,
`orichalcum`, `fur_coat`, `golden_compass`, `lava_lamp`, `music_box`,
`paels_tears`, `permafrost`, `ruined_helmet`, `self_forming_clay`, and the
five `_healed` relics (`lees_waffle`, `looming_fruit`, `mango`, `pear`,
`strawberry`, which are a sim-only conformance artifact with no C#
counterpart) — plus 11 second-attributes on otherwise-admitted relics
(`art_of_war._attacks_last_turn`, `joss_paper._ethereal_pending`,
`pen_nib._card_to_double`, `paels_legion._affected_card`,
`pocketwatch._played_last_turn`, `rainbow_ring`'s three per-type bools,
`silver_crucible.treasure_rooms_entered`, `unsettling_lamp`'s two transients,
`vambrace._triggering_card`, and the card *identities* inside
`paels_tooth.stored_cards`).

The two that would matter most if they slipped through: **`fur_coat`'s
`marked_coords` is future map knowledge** (verified: `fur_coat.py:23,46,90`
tests `point.coord in self.marked_coords`) and `dusty_tome.ancient_card` names
a card the player has not been shown.

**Two judgement calls the census flagged rather than guessed**, both recorded
as open: `paels_tooth`'s stored card *identities* (the count is certainly
shown; whether an inspect screen lists them was not established — excluded
conservatively), and `bone_tea`, whose counter is hidden on the icon but whose
hovertip substitutes `{Combats}`. Whether hover text counts as
"displayed right now" is a policy call. Its range is 0-1, so admitting it as
a flag loses nothing either way — which is what I intend to do.

**Still unsized: `MAX_RELIC_ROWS`.** Measured max is 6, but that is the act-0
masked-random floor and is not usable. Needs the deep-run `acts=[...]` sweep
before a number is picked.

### Census status

| census | state |
|---|---|
| powers per creature (`MAX_POWERS_PER_CREATURE`) | **done**, above (counts re-measured; one claim retracted) |
| relic mutable state + UI visibility (R1) | **done**, above (3 claims spot-checked at source) |
| intent-history K (R3) | **held** — awaiting the user's call |
| select candidates (R4) | **held** — awaiting the user's call |
| R2 card-instance state | **done**, above |
| pile / deck / relic sizes | **done** (act-0 floor only), above |
| R3 slot stability | **done**, above |

Four earlier census agents were killed mid-run by a session usage limit, not
by any finding; two were resumed on the user's instruction and two are held.

### Implementation waves

Lanes are cut on **file ownership**, per the prompt's subagent-execution rule.
The contended files are `full_env.py`, `run_env.py`, `models.py`,
`checkpoints.py`, `train_torch.py`; exactly one lane owns each, and no two
concurrent lanes share a file. Every dispatch forbids `git commit/push/add/
stash/checkout/reset/restore` and forbids getting RED by reverting an
implementation (another agent is live in the tree — write the test first).

| wave | task | owns | state |
|---|---|---|---|
| 1 | **T1** obs contract (`PAD`/`oid`/`ObsLayout`/`ObsBuffer`, truncation, canonical sort) | `sts2_rl/obs.py`, `test/test_obs_contract.py` | **DONE** (+1 leak bug found in review) |
| 1 | **T2** affliction registry + affliction/enchantment vocabularies | `sts2_rl/afflictions.py`, `sts2_rl/vocab.py`, `test/test_affliction_enchantment_vocab.py` | **DONE** (+ enchantment half finished by me) |
| 1 | **T3** relic observation layer (R1 admissibility + exclusion fixture) | `sts2_rl/relic_obs.py`, `test/test_relic_obs.py` | **DONE** |
| 2 | **T4** combat observation v4 | `sts2_rl/full_env.py`, `test/test_combat_obs_v4.py`, `OBS_SCHEMA.md`, (+`__init__.py`, forced) | **DONE + reviewed + fixed** 2026-08-02 |
| 3a | **T5a** run observation v7 (R1/R2/R6) + the potion-width task 0 | `sts2_rl/run_env.py`, `test/test_run_obs_v4.py` (+`full_env.py` for task 0 only) | dispatched 2026-08-02 |
| 3b | **T5b** R4: candidate-index action space | `sts2_rl/run_env.py` (actions), `test/test_select_candidate_actions.py` | blocked on T5a |
| 4 | **T6** third `--arch` (`entset`), schema hard-fail, `TensorObs` | `sts2_rl/tensor_obs.py` (new), `models.py`, `checkpoints.py`, `vec_env.py`, `train_torch.py`, **`evaluation.py`, `eval.py`**, `test/test_tensor_obs.py` | blocked on T5b |
| 5 | stale-test rewrite | the 14 obs-touching test files, incl. `test_full_env.py` / `test_obs_pins.py` / `test_probes.py` | blocked on T6 |

**T5 was split into T5a (observation) and T5b (action space)** after writing the
briefs: one lane doing the whole run env would have been the largest single
task in the project, and the split buys a second review gate on exactly the
boundary where R4 can go wrong — the observation's candidate row order and the
action space's candidate index must agree, and they are written by different
lanes against one shared ordering helper.

**Arch name decided: `entset`** (entity-set). Not a mutation of `entity`, whose
meaning — embedding encoders over the *flat* obs — is unchanged and still
correct for the checkpoints stamped with it. The third name exists so an old
checkpoint is refused on a name rather than dying inside `load_state_dict`.

Wave 1 is three lanes with genuinely disjoint footprints, and all three are
prerequisites of `full_env.py`: T4 cannot write a row without T1's writer, an
affliction id without T2's vocabulary, or a relic row without T3's
admissibility table. Sequencing them ahead of the env lanes is what keeps the
two big contended files single-owner.

**T5 is deliberately not concurrent with T4.** `run_env.py` imports
`build_combat_obs`, `_write_pile_composition`, `_abs2` and `_clip01` from
`full_env.py`; the files are disjoint but the API is not, so running them
together would mean one lane coding against an interface the other is still
changing.

### Wave 2 — the decisions I made when writing T4's brief (2026-08-02)

Suite re-measured immediately before dispatching T4:
`py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py` →
**4257 passed / 6 xfailed / 0 failed** in 283 s. That reproduces the handoff
figure exactly, so wave 1 is green as staged.

`OBS_SCHEMA.md` leaves several things open that three lanes read, so I settled
them in the brief rather than letting each lane guess. Recorded here because
each is a decision, not a measurement:

- **The T5-facing interface is `write_combat_obs(state, buf, card_obs, *,
  prefix="")`.** It writes into a buffer the *caller* owns, addressing segments
  by `prefix + name`, so the run env allocates ONE `ObsBuffer` for its whole
  observation and splices the combat segments in under a `"combat."` prefix.
  The alternative — building a combat buffer and copying it in — would double
  the write traffic on the run env's hot path for no benefit.
  `build_combat_obs` stays as the combat env's convenience path and returns
  **copies**, because a reused buffer handed out live would alias across steps.
- **`hand`, `enemies`, `potions` are POSITIONAL blocks written with explicit
  PAD rows for empty/dead slots.** Row index *is* the action index (play =
  `1 + h*MAX_ENEMIES + e`, and `damage_matrix` shares the grid), and
  `write_rows` packs from index 0 — so omitting a dead enemy 0 would slide
  enemy 1 into row 0 and silently misalign the entire action space. `cards` is
  the only `sort=True` block.
- **`cards.ids` field order is `(pile_id, card_id, affliction_id,
  enchantment_id)`, not OBS_SCHEMA.md §5.1's `(card_id, pile_id, ...)`.**
  `write_rows(sort=True)` sorts by `(tuple(ints), tuple(floats))`, so putting
  `pile_id` first is what makes the generic sort reproduce §5.3's specified
  canonical key instead of a card-major one. The document is corrected rather
  than the code bent around it.
- **`hand.f` is 29 floats, not the document's 28** — the existing 24 plus
  affliction amount, `exhaust_on_next_play`, `_has_single_turn_retain`,
  `_has_single_turn_sly`, and `base_replay_count`. The last is in the R2
  census's own list of player-visible per-instance state missing from the obs;
  the bump is paid once, so leaving it out would re-price it later.
- **`cards.f` is 4 floats** — `(upgrade, effective_cost, affliction_amount,
  exhaust_on_next_play)`. The two single-turn flags are hand-only state cleared
  by end-of-turn cleanup, so they would be constant noise on a pile row. The
  document's "flags" field is replaced by a named boolean rather than a packed
  bitfield, which a network cannot decode from one scalar.
- **`card_obs` survives with the same two values but one layout.** `"features"`
  now writes `PAD` in place of `card_id` in the `hand.ids` rows only — today's
  `features` mode drops the hand one-hot and keeps card identity in the pile
  histograms, so blanking the `cards` block too would silently widen the
  ablation.
- **`numeric_obs_indices` / `AblatedObsEnv` are kept, re-expressed over the
  float half.** Every numeric feature lives in `f`, so this is a faithful port,
  not a redesign; deleting them would break `eval.py`, `evaluation.py` and
  `test/ablation.py` for no reason this project has.
- **Overflow floats are wired for `player.powers`, `player.relics`, `hand`,
  `enemies`, `potions`, `cards`, and each of the 6 `enemy{e}.powers`.**

### Wave 4's blast radius, re-measured 2026-08-02 (and one correction)

A read-only recon lane re-derived every site that assumes the flat-array
contract. **This corrects the "Trainer blast radius" paragraph earlier in this
ledger, which named "the two `agent.get_value` / `get_action_and_value` call
sites" in `train_torch.py`. There are four**, and the two it missed are the
ones that bootstrap a value:

1. rollout action selection, `train_torch.py:534`
2. **truncation bootstrap**, `train_torch.py:554` (`final_obs`, `.unsqueeze(0)`)
3. **GAE bootstrap**, `train_torch.py:574` (`agent.get_value(next_obs)`)
4. PPO update scoring, `train_torch.py:618`

Recorded as a correction rather than an edit-in-place, because a brief written
off the old count would have left two silently-unmigrated call sites in the
value path — where a wrong obs does not crash, it just poisons the advantages.

Other findings that change T6's shape:

- **`checkpoints.py` never validates `arch` at all.** `make_model` branches
  `if spec.arch == "entity": ... return MaskedActorCritic(...)`, so any
  unrecognised arch silently becomes the flat MLP. The only enumeration is
  `train_torch.py:108`'s `--arch choices=["mlp", "entity"]`. So "add the third
  `--arch` value" is a CLI change *plus* a real branch in `make_model`, and the
  silent-fallback default should stop being silent.
- **Four independent assumptions, not one.** Every consumer treats the obs as
  simultaneously (a) `.shape[0]`-introspectable (`vec_env.py:113`,
  `evaluation.py:117`), (b) row-assignable into `np.empty((E, obs_dim))`
  (`vec_env.py:117-144`), (c) `torch.as_tensor`-convertible in one call, and
  (d) slice-addressable by flat float offset (`models.py:222`,
  `train_torch.py:381`, `checkpoints.py:271`). `TensorObs` has to answer all
  four; no site currently branches on `isinstance(obs, dict)`.
- **`models._segment_plan` classifies segments by name SUFFIX and width**
  (`models.py:126-158`, e.g. `if last == "onehot" and width == N_CARDS`). The
  v4 names end in `.ids` / `.f`, so the plan needs new arms — this is the seam
  where phase 2's encoder will land, and phase 1 should leave it obviously
  provisional rather than clever.
- **`--zero-segments` zeroes `agent.actor[0].weight[:, start:stop]`**
  (`train_torch.py:381-382`) — first-layer *columns*. With a two-leaf obs and
  embedding tables, "zero this segment" no longer means one column range.
- **`evaluation.py` and `eval.py` break too** (`evaluation.py:78` `as_tensor`,
  `:117` `shape[0]`, `:125-135` `ablation_transform`'s flat fancy-index), so
  they join T6's ownership; the ledger's earlier lane table omitted them.
  `probes.py` is unaffected — it hands `obs` through opaquely and
  `lethal_oracle` reads `env.unwrapped._state` directly.
- **`migrate_checkpoint` (run obs v3→v4) and `migrate_ckpt.py` become dead**
  the moment the run schema goes to 7, since every pre-7 checkpoint is refused
  outright and there is no weight migration for this bump. Per CLAUDE.md §3
  they are to be *reported*, not deleted — removing pre-existing code this
  project did not write is not in scope.

**The suite cannot be green between T4 and T6, and that is structural, not a
regression.** `run_env`, `checkpoints`, `models`, `evaluation` and ~14 test
files all read the flat contract; they migrate in waves 3–5. The gate for each
intermediate lane is therefore not "green" but **"every failure is traceable to
a lane that has not run yet"** — each lane reports its own red set with a
one-line cause per file, and I verify the set shrinks monotonically and
contains nothing unexplained. Recorded because "the suite is red" is otherwise
exactly the state in which a real regression hides.

### Wave 2 — T4 landed (2026-08-02)

The v4 combat observation is implemented in `full_env.py`, with 39 new tests in
`test/test_combat_obs_v4.py`. **Absolute figures, no comparison implied or
permitted:** `f_dim` **1394**, `i_dim` **599**, **7,972 bytes/env/step**,
`MAX_OBS_ID` 640.

**Suite after T4, re-run BY ME rather than taken from the lane** (the lane's own
number is not evidence — that rule exists because both wave-1 lanes shipped
defects their own green suites missed):

    py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py \
        --continue-on-collection-errors
    -> 20 failed, 4110 passed, 6 xfailed, 10 errors in 246s

Identical to the lane's reported figure. `--continue-on-collection-errors` is
required now: without it pytest aborts before running anything, so the bare
command in the earlier briefs measures nothing once a consumer stops importing.

**The red set, audited against the rule that every failure must trace to a lane
that has not run yet.** All 30 do:

| group | count | cause | closes in |
|---|---|---|---|
| collection errors importing `run_env` | 7 files | `run_env` still imports the deleted `_write_pile_composition` | T5a |
| `test_full_env.py`, `test_obs_pins.py` | 2 files | import deleted v3 names (`ENEMY_ROW_DIM`, `obs_segments`) — the v3 pin files phase 1 supersedes | test-rewrite wave |
| `test_models.py` | 1 file | imports `obs_segments` | T6 |
| `test_vec_env.py` | 6 | `observation_space.shape[0]` on a `Dict` space | T6 |
| `test_train_io` / `test_train_stability` | 3 | drive `train_torch` through `vec_env` | T6 |
| `test_probes.py` | 8 | `_build_obs().tobytes()` — the builder returns a dict now | test-rewrite wave |
| `test_kifuda_partial_enchant` | 1 | imports `run_env` inside the test body | T5a |
| `test_power_instances::TestObservationResidue` | 1 | **pins the OLD one-row-per-id collapse on purpose** — phase 0 left it as the tripwire so the residue could not be forgotten. Its failing IS phase 1 closing that residue. | test-rewrite wave |

Nothing unexplained, so wave 2 passes its gate.

**What T4 corrected in my brief** — both recorded because the brief was wrong,
not the lane:

1. **My §3.6 premise ("if `the_bomb` is the only power with a per-instance
   number...") was false.** Five more `INSTANCED` powers carry one:
   `toric_toughness.block`, `automation.cards_left`, `panache.cards_left`
   (player-side), `thievery.gold_stolen`, `withering_presence._cards_left`
   (enemy-side). All six are now keyed explicitly by power id — not duck-typed
   on an attribute name, which is what the brief warned against and what would
   have silently picked up unrelated attributes. Two scaling buckets:
   HP/currency-like on the shared `ABS_SCALE` (/100), small countdown counters
   on /10. `swipe.stolen_card` and `strangle._amounts` hold non-numeric state
   and were left at `aux = 0.0` with the omission documented rather than given
   an invented encoding. `rolling_boulder` needs no aux — its growing value IS
   `amount`.
2. **The blast radius included `sts2_rl/__init__.py`, which my brief assigned to
   no lane.** It re-exports `obs_segments` / `obs_slices`, so deleting those
   (as the brief explicitly instructed) made `import sts2_rl` itself raise —
   breaking not "roughly a dozen test files" but *every test in the suite*,
   including T4's own. The lane made a minimal 4-line fix and flagged it as an
   out-of-scope deviation rather than burying it.

Two further findings worth keeping:

- **A power "present at amount 0" cannot be produced by any `PowerCmd` call.**
  `PowerCmd.apply`'s stacking branch removes any power whose amount nets to
  exactly 0 (C#'s `ShouldRemoveDueToAmount`), verified by experiment: Strength
  +5 then −5 empties `powers` entirely even though `allow_negative = True`. The
  padding-invariant test therefore constructs that state directly, bypassing the
  command layer — it is testing the *encoder's* response, which is what the
  invariant is about, independent of whether the engine currently produces it.
- **`evaluation.ablation_transform` imports cleanly but breaks at RUNTIME** on a
  dict observation (`obs[idx] = 0.0` assumes a flat array, `evaluation.py:132`).
  My brief only asked for an import check, so this would have reached wave 4
  undetected. Added to T6's scope along with `evaluation.py:117`'s
  `observation_space.shape[0]`.

### Wave 3a — T5a landed (2026-08-02)

The v7 run observation is built; `RUN_OBS_SCHEMA_VERSION` is 7 and `run_env`
imports again. **Absolute figures, no comparison implied or permitted:**
`f_dim` **4416**, `i_dim` **1452**, **23,472 bytes/env/step**. 58 new tests in
`test/test_run_obs_v4.py`; the combat suite grew 50 → 51 with task 0.

**Suite re-run BY ME:** 29 failed, **4218 passed**, 6 xfailed, 7 errors.
Passing grew by 97 and collection errors fell 10 → 7. I checked the cause of
every remaining error individually rather than trusting the count — **all seven
are stale imports in TEST files of names deliberately removed** (`run_obs_segments`
×3, `obs_segments` ×2, `ENEMY_ROW_DIM`, `PILE_COUNT_CAP`), not a broken module;
`import sts2_rl.run_env` and `curriculum_env` both succeed. The 29 failures are
`test_eval_torch` (11, newly *collectable* and now failing on `evaluation.py`),
`test_vec_env` (6), `test_probes` (8), `test_train_*` (3), and the deliberate
`test_power_instances` residue tripwire (1) — 20 for T6, 9 for the test-rewrite
wave. Nothing unexplained; the set is shrinking.

**T5a caught my brief being wrong, and the correction matters beyond sizing.**
I wrote "base 3 + Phial Holster's +1", so task 0 shipped `MAX_POTION_ROWS = 4`.
**Three** relics grow the belt through `RunState.add_potion_slots`
(`run.py:808-813`) — `phial_holster` +1, `potion_belt` +2, `alchemical_coffer`
+4 — so the ceiling is `3 + 7 = 10`. I re-verified all three at source. Unlike
almost every other cap in this project, this one is a **hard** bound: each relic
is unique and grants once, so 10 cannot be exceeded. That makes it better
evidence than the act-0 censuses everything else rests on. Widening it grows the
action space, so it is assigned to T5b along with the constant it feeds.

**A real pre-existing bug found and fixed on the line being rewritten.** The
fallback for an unrecognised select purpose was
`PURPOSE_INDEX.get(request.purpose, N_PURPOSES - 1)` — index 23, a slot in the
*reserved capacity tail*, when the vocabulary has a real `"_unknown"` bucket at
index 14. Every unregistered purpose was encoded as a dead slot instead of the
catch-all that exists for exactly that case. (`transform_optional` from Claws.cs
is a known live instance of an unregistered purpose, so this was reachable.)

**The select-screen question is answered.** The lane found in the game source
that the real screen **re-sorts** draw-pile candidates (by rarity/alphabet)
rather than showing raw pile order. So the canonical sort is a fidelity fix, not
merely a defensive no-op against the leak — and a future lane may not relax it
on the grounds that "the player sees pile order anyway", because they do not.

**A contradiction in my brief, correctly refused rather than papered over.** I
told T5a to reuse `full_env._pile_card_row` *and* to touch `full_env.py` for
task 0 only. It followed the ownership boundary, hand-kept a duplicate row shape
in `run_env._run_card_row`, and reported the conflict. That is the right
behaviour — but the duplicate is a live drift risk against R2's premise of one
row shape everywhere, so de-duplication is assigned to T5b.

**Open, flagged by the lane as its own weakest point:** the R6 `log1p`
denominators for gold and shop costs are *reasoned defaults, not measured*.
They are honest as encodings (monotone, non-saturating) but nothing pins them to
an observed distribution, and no act-0 census could — gold and prices past act 0
are exactly what masked-random play never reaches.

### Wave 3b — T5b landed, and R4's acceptance test is GREEN (2026-08-02)

**`py env_baseline.py sanity --env column` passes.** That tool was RED *by
design* — it compared distinct candidate signatures against mask bits and failed
on R4's information-losing collapse, naming R4 as the fix. Run by me, 300
masked-random episodes:

    observation      5898 elements / 23592 bytes
    floor            mean 4.62  median 4.0  max 13
    decision kinds   {... 'select_cards': 423 ...}
    All sanity thresholds passed.

423 `select_cards` decisions reached with **zero unaddressable candidates**. The
two witnesses the ledger recorded — seed 75's `nimble`-enchanted Defend among
plain Defends, seed 157's `spiral`-enchanted Strike among plain Strikes — are
now selectable. This is the one rider in phase 1 with a pre-existing failing
acceptance test, and it is closed.

The floor band (mean 4.62, median 4, max 13) sits inside the tool's declared
absolute thresholds. **That is the intended use and not an old-vs-new
comparison** — the thresholds are deliberately wide, anchored once, and per this
ledger's own rule must never be tightened into a regression detector.

**`N_ACTIONS` 243**, decomposing as `N_COMBAT_ACTIONS` 121 + `CHOICE_SLOTS` 16 +
`MAX_SELECT_CANDIDATES` 96 + `MAX_POTION_SLOTS` 10 — every term derived from
`full_env.MAX_POTION_ROWS = 10`, never hardcoded twice. Recorded as an absolute
figure; no ratio against the old layout is computed or implied.

**The potion-belt `IndexError` is fixed**, and task B's duplicate card-row
encoder is gone — `run_env` and `full_env` now share one row builder, which is
what R2's "one row shape everywhere" premise required.

Two things the lane surfaced:

- **A one-time-per-process warning latch bit again** — its overflow test used
  `pytest.warns`, which passed standalone and failed in the full suite because
  another test had already consumed `obs.py`'s warn-once latch. Same family as
  T2's `__subclasses__()` collision: **process-global state makes a test's
  result depend on collection order.** Fixed by asserting the `.overflow` float
  directly, which is the convention the rest of the suite already uses. Worth
  generalising: in this codebase, never assert on a once-per-process warning.
- **`checkpoints.migrate_checkpoint_actions` (v5→v6) derives its potion-block
  width from `MAX_POTION_SLOTS`**, so it now splices 10 columns where it spliced
  4. Unreachable (every pre-v7 checkpoint is refused by the schema check), but
  its tests may pin the old literal. Handed to wave 4.

It also had to touch `test/test_any_time_potion_action.py`, which hardcoded
`POTION_BASE == SELECT_BASE + 2*N_CARDS` — a formula R4 makes false by design.
One assertion updated; leaving it would have grown the failing set.

### Final whole-branch review (2026-08-02) — the seam bug four reviews missed

**The single most valuable finding of this project, and a lesson about what
per-task review structurally cannot do.**

`models.py:566` masks a row as absent on `ids[..., primary] != 0`. But
`OBS_SCHEMA.md` §2.1 defines a padded row as `id == 0` **AND all-zero floats**.
The encoder implements half the definition, so any row with a PAD id and live
floats is silently dropped. Two blocks are exactly that shape:

- **`--card-obs features` trains a policy that cannot see its own hand.**
  `full_env.py:720` writes `card_id = PAD` in that mode *by design*, and by my
  own brief's explicit instruction. Measured: the hand block's pooled
  contribution to the encoder is **0.0** in `features` mode vs **29.13** in
  `hybrid`. No error, no warning.
- **`--env run --arch entset`** — the flagship config — drops the `slot_exists`
  bit on every empty-but-existing potion slot. Measured: **833 such rows across
  5 run episodes**.

**Why four independent adversarial reviews missed it: each side of the seam was
individually correct.** The envs faithfully emit what the schema permits; the
encoder faithfully masks on the id column; `test_combat_obs_v4.py:786` even
asserts those hand rows stay "distinguishable from PAD via nonzero floats" — and
it is *right*. It proves the information is in the observation. Nothing checked
that the model reads it. A per-task reviewer holding one file cannot see a
contradiction that only exists between two.

Two consequences worth carrying into phase 2: **a schema rule stated in prose is
not enforced until something executes both halves of it**, and the join between
a producer and its consumer deserves its own test even when both sides are
reviewed.

**The `--arch entity` question is settled by measurement, not preference.**
`models._as_flat:64` concatenates `obs.i` (ids up to 640) with `obs.f` (bounded
`[0,1]`) **unnormalized**, into an orthogonal-init `Linear(std=√2)`. So it is not
merely that ids lose their categorical meaning under a linear weight — their
magnitudes **dwarf the entire float half**, drowning ~1400 genuinely numeric
features under ~600 columns of large integers. The usual argument for keeping a
no-embedding baseline runnable is a *comparison* argument, and this project has
none by explicit decision. **Decided: refuse `mlp`/`entity` against v4/v7 envs**,
the same rule already adopted one case over for unrecognised arch names.

The review also endorsed replacing the dead migration bodies with an honest
`raise` (CLAUDE.md §3 protects code that still *works*; these were broken by this
work and would `NameError` if reached) and recommended **removing** the six
orphaned private helpers — the §3 clauses only appear to collide, since those
helpers were live until this phase orphaned them.

**And it caught the phase-1 report overstating its own status:** the report said
"Staged, not committed" when only wave 1 was staged and `sts2_rl/tensor_obs.py`
was still untracked — so `git commit -a` would have shipped an unimportable
tree. Staging is the controller's job; deferring it to the end while claiming it
was done is my error, not a lane's.

Verified clean by the same pass, and worth recording so it is not re-checked:
constants are genuinely single-sourced (the one deliberately dual-declared pair,
`MAX_OBS_ID`, has a real import-time `raise`, not a strippable `assert`); the
R4 observation↔action join cannot disagree by construction; the env↔model
completeness check really fails on an undeclared segment; all **four**
`TensorObs` PPO sites are migrated including both value-path bootstraps; and
40 combat × 200 steps plus 8 run × 400 steps fuzzing found zero `Box` bound
violations.

### Audit — `power_cmd/G5`'s observation residue CLOSED by re-audit (2026-08-02)

Confirmed by an agent re-reading **both** sides (`PowerCmd.cs`, `PowerModel.cs`,
`Creature.cs` / `cmds.py`, `creatures.py`'s `PowerList`, `full_env.py`'s
`_power_rows`) and by *running* the tests, not by re-wording prose — per
`audit/README.md`'s rule that a rehash without a re-audit is a decoration.
`full_env.py` now emits one row per power **instance**; two `the_bomb` fuses land
as two rows with independent aux. Record text updated with superseded text
preserved, `full_env.py` added to `extra_sources`, re-pinned, `GAP-QUEUE.md`
corrected, validate clean.

**One dead citation was ours, not systemic.** The record cited
`test/test_obs_byte_identity.py` — which *phase 1 deleted*. The lane initially
filed it as pre-existing debt; it is not. Now closed with the reason recorded
(the golden pinned an encoding phase 1 replaced, so it had nothing left to
detect) **and the honest gap stated**: its digests also covered the
reward/terminated/truncated stream, and phase 1 supplies no replacement for that
half. `citation_check` MISSING 1 → 0. The 29 unhashed line-number citations are
genuinely systemic across ~849 records and were correctly left alone.

### Phase 1 — GREEN (2026-08-02)

    py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py
    -> 4387 passed, 6 xfailed, 0 failed, 0 errors

Re-run by me after the `checkpoints.py` fix, as after every lane. Baseline
before phase 1 was 4257 passed. **First fully-green run since wave 2 began** —
every intermediate red set was audited to trace only to lanes that had not run
yet, and it shrank monotonically at every gate.

Final absolute figures, measured on the finished tree (`env.reset(seed=0)`):

| env | schema | `f_dim` | `i_dim` | bytes/env/step | actions |
|---|---|---|---|---|---|
| `STS2FullCombatEnv` | 4 | 1401 | 606 | 8,028 | 79 |
| `STS2RunEnv` | 7 | 4434 | 1464 | 23,592 | 243 |
| `STS2CurriculumRunEnv` | 7 | 4434 | 1464 | 23,592 | 243 |

**Nothing is compared against these.** Full report:
`docs/superpowers/plans/2026-08-02-entity-obs-schema-phase1-report.md`.

The `checkpoints.py` fix closed all three bugs T7-B found, +5 tests. One
judgement call it flagged rather than took silently: it replaced the two dead
migration functions' *bodies* with an honest `raise` (keeping the definitions,
docstrings and guards) rather than leaving the old splice/append logic below the
raise as unreachable code that referenced a renamed import and would `NameError`
if it were ever reached. That, plus the six private helpers the change orphaned,
is a CLAUDE.md §3 question — the section says both "remove what YOUR change
orphaned" and "don't delete pre-existing dead code", and here both clauses point
at the same lines. Handed to the final review, then to the user.

### Wave 5 — T7-A and T7-B (2026-08-02)

**T7-A** (`test_full_env`, `test_obs_pins`, `test_obs_vectorization`): 0 → **42
passed**; all three had been dark at collection. 31 → 22 tests, every deletion
with a stated reason. **I spot-checked the load-bearing one** rather than
accepting it: the claim that `test_damage_matrix_alignment` is "superseded by a
stronger version" is true —
`test_combat_obs_v4.py:698::test_damage_matrix_cell_matches_decoded_action_with_a_dead_enemy_in_slot_0`
checks alignment against `decode_combat_action` *with a dead enemy in slot 0*,
which the v3 test did not. A false "it's covered elsewhere" is exactly how a
regression gets laundered, so that claim was worth the check.

It also added a genuinely **new** test with no v3 ancestor: driving real
multi-phase run episodes to prove the persistent `ObsBuffer` does not leak one
phase's stale data into the next phase's observation — the failure mode the
buffer-reuse design introduces. Verified by three separate runtime mutations
(buffer reuse, no-op `reset()`, aliased return), each making it go RED.

**T7-B** (`test_run_env`, `test_curriculum_env`, `test_map_obs_and_migration`):
0 → **44 passed**. The first two rewrote with no deletions — every v3 pin had a
direct v7 equivalent. It also tightened a pre-existing latent bug in a
select-phase mask test that let potion-belt actions leak into a "select" count.

**T7-B found three production bugs in `checkpoints.py` and correctly reported
rather than fixed them** (out of its lane). I reproduced the first and third
myself:

1. **`migrate_checkpoint` (run v3→v4) raises `ImportError` for EVERY input** —
   it imports `run_obs_segments`, which wave 3a renamed.
2. `migrate_checkpoint_actions` (v5→v6) raises a bare `AssertionError` on its
   one valid input (a stale `RUN_OBS_SCHEMA_VERSION == 6` guard).
3. **`check_checkpoint`'s hint text for schemas 3 and 5 still points users at
   `migrate_ckpt.py`** — a tool that now crashes with (1). This is the
   user-facing one and it is a regression phase 1 introduced: someone holding a
   v3 or v5 checkpoint is told to run a migration that cannot work.

The load path itself is sound — refusal is a clean `SystemExit` for every stale
schema — so this is about the advice, not the gate. Earlier this ledger recorded
these migration functions as "newly dead, report don't delete" per CLAUDE.md §3;
that judgement stands for *dead*, but they are now **broken**, and a broken
function the error message actively recommends is worse than either fixing or
removing it. Assigned to a final fix lane.

Its judgement call on the migration tests is recorded and I endorse it: the
fine-grained weight-splice correctness tests went (their property, "migration is
function-preserving", is no longer true of reachable code, and their fixtures no
longer type-check against `make_model`), replaced by a **parametrized test
covering every pre-v7 schema 2-6** — because the property that actually matters
now is that a stale checkpoint is refused cleanly. Confirmed non-vacuous by
monkeypatching the schema gate out and watching it go RED.

### Wave 5 — T7-C: `power_cmd/G5`'s observation residue is CLOSED (2026-08-02)

`test/test_models.py`, `test_eval_torch.py`, `test_probes.py` and
`test_power_instances.py` rewritten — **61 passed**, 0 failed.

**The residue is closed, and this is the audit-facing result of phase 1.**
Phase 0 closed `power_cmd/G5` *conservatively*: it fixed the engine state
(`creature.powers` became an ordered instance list) but explicitly did NOT claim
the observation half, because `full_env.py` still wrote one `(presence, fine,
coarse)` triple per power **id** — so the obs showed only the newest instance.
It left `TestObservationResidue` as a deliberate tripwire so this could not be
forgotten, with a docstring saying "Closing that is phase 1's integer schema."

That tripwire is now inverted into
`test_two_instances_are_two_distinct_observation_rows_with_their_own_aux`,
proving two `the_bomb` instances occupy two distinct observation rows with
independent `aux` values. **Verified genuine by mutation** — the lane reproduced
the old collapsing behaviour in a throwaway script and confirmed the new test
goes RED against it. The audit records for `power_cmd/G5` can now be closed on
the observation side too.

The other three files: `test_probes` now hashes **both halves independently**
(strictly stronger than the old single hash — a one-half-only divergence can no
longer hide), and `test_models` gained real `entset` coverage against live env
layouts, including a batch-independence tripwire verified to catch cross-talk.

**OPEN QUESTION for the final review — `--arch entity` now degenerates
silently.** The lane measured that against the v4 layout, `entity` builds **zero
embedding tables and has a parameter count identical to `mlp`**: its
`_segment_plan` keys off v3 segment names that no longer exist, so every segment
falls through to "just floats". T6 chose degenerate-but-functional over
crashing, and the lane pinned the degeneration rather than hiding it — both
defensible. But `entity`'s entire value was per-vocab embeddings, so a user
typing `--arch entity` against a v4 env silently trains an MLP. That is the same
footgun T6's own brief called out for *unrecognised* arch names ("must raise,
not silently become an MLP"), one case over. **Not decided unilaterally
mid-wave; hand it to the final whole-branch review.**

### Wave 4 — T6 landed: the whole stack runs (2026-08-02)

`TensorObs`, the `entset` arch, the schema hard-fail and the `vec_env` /
`train_torch` / `evaluation` / `eval` migration are in. Lane-reported suite:
4261 passed / 20 failed / 6 xfailed / 7 errors — the 20 remaining failures are
`test_eval_torch` (11), `test_probes` (8) and the `test_power_instances`
residue tripwire (1), all owned by the test-rewrite wave.

**The evidence that matters, run by me, not taken from the report.** This is the
first moment integer observation → embedding encoder → PPO loop execute
together:

    py train_torch.py --env combat --arch entset --fresh --timesteps 4096 \
        --n-envs 4 --n-steps 128 --device cpu
    iter 0  step  512  sps 210  ep_ret -0.294  win 0.36  ent 1.470  kl 0.0109
    iter 7  step 4096  sps 210  ep_ret  0.623  win 0.80  ent 1.002  kl 0.0076

Win rate 0.36 → 0.80 with entropy falling and KL stable: gradients flow and the
policy improves. `--env column` also completes (ep_ret ~4.5, 122 sps).
**Absolute figures. No comparison to the old stack is implied, and none is
possible** — the action layout, observation contents and encodings all moved at
once, which is exactly why the prompt forbids the delta.

**The third `--arch` value does its job**, verified directly:

    checkpoint arch 'entset' != this run's --arch 'entity'; there is no weight
    migration between architectures - pick the matching --arch or start --fresh.

Refused on a **name**, not on a shape mismatch deep inside `load_state_dict` —
which is the entire reason the prompt asked for a third name rather than
mutating `entity`.

**T6 caught a contradiction in my brief**: §1 listed `test_eval_torch.py`'s 11
failures as "yours to turn green" while §6 excluded that file from the green
bar. It traced all 11 to the test file's own `observation_space.shape[0]` calls
— test-side, not production — and correctly left them for the test-rewrite wave
rather than editing a file outside its ownership.

Judgement calls it made and documented: `mlp`/`entity` remain
degenerate-but-functional against the new envs rather than crashing;
`model.obs_dim` is overwritten post-construction to unify checkpoint bookkeeping
across archs; `entset`'s `--zero-segments` is a hard refusal (the brief's own
escape hatch, chosen over a silently-wrong ablation); and the row-presence mask
keys off the first *vocab-mapped* field rather than literally the first field.

### Wave 3b fix pass — accepted (2026-08-02)

All 9 items done. **Verified by me, not taken from the report:** the three
affected test files pass **127 in both orders** (they failed in one order
before). The full suite is deliberately deferred — wave 4 was live in the tree
at the time and running it would have raced that agent's edits.

The item-1 fix is the one worth keeping in mind for the rest of this project:
`sts2_rl/obs.py` gained `reset_warned_segments()` and a new `test/conftest.py`
holds an **autouse fixture that clears the latch before every test**. Its
docstring records all three prior instances and states why patching the failing
call site again would have left the trap armed. That is the right shape of
response to a defect that has recurred three times — retire the class, not the
instance.

Also worth noting for its method: item 4's fix was verified by *measurement*
rather than argument. The lane confirmed object-identity assertions fail
**247/500** permutations on a duplicate-bearing fixture while row-equality passes
cleanly — establishing that the test was wrong and the product was right, which
is the distinction that matters when a test starts failing on a better fixture.

Item 2's potion loop is now bounded, with the existing `run.potions.overflow`
flag serving as the signal — so the two branches of `action_masks` finally hold
the same overflow policy. Item 3's cap is pinned against the three relics' own
`POTION_SLOTS` attributes plus `PlayerCombatState.MAX_POTIONS`, so it fails if
any of them moves, rather than against a literal that would only relocate the
magic number.

### Wave 3b review findings (2026-08-02)

**Spec ✅, no Critical findings.** The reviewer verified the load-bearing
property with its own code rather than the lane's: against a 9-candidate
all-`defend` list spanning plain / `nimble` / `spiral` / afflicted / upgraded /
exhaust-flagged copies, the mask offers 9 bits, `_translate` is a **bijection**
onto the candidates, and observation row *i*'s **full 8-field signature** equals
the row of the card `SELECT_BASE + i` selects — across **400 random
permutations**, zero failures, and again past the cap. It also confirmed at C#
source that exactly three relics call `GainMaxPotionCount`
(`AlchemicalCoffer.cs:23`, `PhialHolster.cs:28`, `PotionBelt.cs:21`) and
**nothing** calls `LoseMaxPotionCount`, so 10 is the true ceiling.

**The one R4 sentence still open**, recorded so it is a deferral and not an
oversight: R4's own text says "measure the worst-case candidate count before
sizing". `MAX_SELECT_CANDIDATES` is a static 96 because the census is HELD on
the user's instruction. It is now load-bearing on **actions**, not just the
view — a candidate past the cap is unclickable, which the real game never does.

**IMPORTANT — the process-global warning latch bit for the THIRD time.** The new
test overflows `select.candidates`, consuming `obs._WARNED_SEGMENTS`, while
`test_run_obs_v4.py:679` still asserts `pytest.warns` on that same segment.
Measured: the two files pass in one order and fail in the other, and the default
alphabetical order happens to be the passing one — which is exactly why the
full-suite count matched baseline and nothing looked wrong.

That is three separate instances now (wave 1's `__subclasses__()` finding a test
double; wave 3b's own overflow test; this), each previously patched **at the call
site**, which leaves the trap armed for the next lane. The fix lane is therefore
retiring the class: an autouse `conftest.py` fixture clearing the latch per
test, so no test can inherit or steal another's. **Generalised rule for this
codebase: never assert on a once-per-process warning, and never let
process-global state decide a test's result.**

**IMPORTANT — Task A moved the crash threshold without removing the mechanism.**
`action_masks`' potion branch still indexes unguarded, so `add_potion_slots(8)`
(11 slots) raises `IndexError index 243 out of bounds`. Unreachable today, and
the constant is now right — but **two branches of one method hold opposite
policies on overflow**: twenty lines below, the SELECT branch truncates behind a
comment arguing at length that a crash mid-training must never happen.

**IMPORTANT — nothing pins the new potion cap.** Setting `MAX_POTION_ROWS = 6`
leaves every potion test green (they are all written *relative to the constant*)
while an Alchemical Coffer + Potion Belt run crashes exactly as before. Same
class as the consistency test too small to reach the cap it guarded. The fix
pins 10 against the three relics' own `POTION_SLOTS` attributes and
`PlayerCombatState.MAX_POTIONS`, so it fails if any of them moves — rather than
against a bare literal, which only relocates the magic number.

**IMPORTANT — the shuffle-invariance test is degenerate on exactly R4's input
shape.** Its fixture produces 9 rows, **9 distinct** — no ties — so the sort's
tie-breaking, the only fragile part of the invariance, is never exercised. R4
exists *because of* duplicates that differ only in aux fields. And the assertion
cannot simply be strengthened: it compares **object identity**, which fails 254
times across 50 permutations on a duplicate-bearing fixture even though the
mapping is right, because tied rows are genuinely interchangeable. The product
is fine; the test is wrong. Fixed to assert row-equality on a fixture with real
ties.

Minor: the headline regression assertion is a tautology
(`order[order.index(2)] == 2`); the agreement test checks 5 of 8 row fields,
omitting effective cost and affliction amount — precisely the fields R4 exists
to distinguish; a dead default parameter; and `OBS_SCHEMA.md` §7 now contradicts
the code by claiming every cap degrades the view rather than crashing, which is
false for the select cap. §7 is the document's own soft-spots section, so that
one matters more than its severity suggests.

### Wave 3a fix pass — accepted, verified by me (2026-08-02)

All five items landed. Suite after: **4226 passed** (+8 tests), 29 failed, 6
xfailed, 7 errors — the failing/erroring set identical **by name**.

**The lane ended its turn without filing a report**, saying it would wait for a
background suite run of its own. So there is no fix report to review and I
verified the tree directly instead, which was cheaper than resuming it:

- `_sorted_candidate_order` now truncates to `MAX_SELECT_CANDIDATES`, with the
  reasoning recorded at the site.
- Unknown-id guards restored for relics and the boss block, the latter with a
  comment explaining why it is the dangerous case (appending a PAD row consumes
  one of only `MAX_BOSS_IDS` slots and shifts every later real id).
- `OBS_SCHEMA.md` un-staled; the `python -O` no-op assert made real.
- **R6 retuned, and I checked the numbers rather than the constants.** Gold
  fine/coarse denominators are now 800/8000: the fine channel resolves to 800
  instead of saturating at 300, and the coarse channel carries 800 → 3000 as
  0.744 → 0.891, so the dual-scale pair stays informative across the range a
  real run reaches. Shop costs (denom 900) spread 0.55 → 0.98 over 40-800g, and
  500 vs 800 — which previously collided — now differ clearly.

**New failure mode for the dispatch rules: an agent blocking on its own async
work.** Every later dispatch now says explicitly that the lane must report
before ending its turn, and must wait inline for anything it starts. Recorded
because the symptom (a lane that "finished" with no report) reads like a crash
and is easy to respond to by re-running the whole task.

### Wave 3a review findings (2026-08-02)

**Spec ✅, no Critical findings** — nothing produces a wrong observation for a
reachable state. The reviewer independently *confirmed* the load-bearing
properties rather than taking them on trust, which is worth recording so they
are not re-checked: the select-candidate non-leak holds over 25 shuffles of a
heterogeneous 20-card list (11 distinct rows, 29 non-zero floats — nothing like
the degenerate fixture wave 2 shipped) and genuinely goes RED without the sort;
positional shop slots survive the two-hole case; R1's in-combat gating reads 0
through `relic_obs`; and `MAX_BOSS_IDS` is right (the largest boss
`monster_classes` across all 87 encounters is 3).

**IMPORTANT — the observation/action seam is real, and it is exactly where the
lane split was drawn.** `_sorted_candidate_order` (`run_env.py:820`) returns
**all** candidate indices, but `write_rows` sorts *then* slices to
`MAX_SELECT_CANDIDATES`. Measured at 106 candidates: rows 0-95 agree perfectly,
and **10 order entries address no observation row** — while the helper's own
docstring promises the same order as the rows written, and a comment tells the
next lane it is "the single source of that order". The natural next-lane
implementation (one mask bit per helper entry) would enable 10 actions for rows
that are all-PAD in the policy's own observation. The existing consistency test
uses 8 candidates, so it cannot see this; the shuffle tests do cover overflow but
only compare observations to each other and never call the helper.

**IMPORTANT — the potion-belt gap is a CRASH, not a degraded view, and my ledger
entry above understated it.** `run_env.py:767` sizes the mask at
`POTION_BASE + MAX_POTION_SLOTS` while `request.potion_actions()` yields one
action per belt slot. Reproduced: a run that took `add_potion_slots(2)` — Potion
Belt, **COMMON** rarity, from any ordinary relic reward — holding 5 AnyTime
potions raises `IndexError index 1385 is out of bounds` from `action_masks()`.
A single common relic can kill a training run. Pre-existing, not a wave-3
regression, but reachable; reassigned to T5b as a crash fix rather than a
sizing nicety.

**MINOR but it is R6's whole purpose — the `log1p` denominators do not
resolve.** Gold's **fine channel reads exactly 1.0 at 300, 500, 1000, 1500 and
3000**, so above ~300g the two-float encoding degenerates to one float. R6
exists *because* `gold/100` saturated; this moves the defect rather than removing
it. Shop costs have the mirror problem — the whole realistic band (40-320g)
occupies 27% of `[0,1]`, all in the upper half. Retunable without a schema
change, which is why it is Minor, but the comment at the constant claims the
fine denominator "resolves the shopping-relevant range" and for a hoarding run
it resolves nothing.

**MINOR — an unknown vocabulary id writes a row that is neither real nor pad.**
`oid(None)` yields PAD while the floats are still written from live state,
violating §2.1's "id == 0 AND all-zero floats". Pre-v7 code guarded each site
with `if idx is not None`. `run.boss` is the worst: an unrecognised class
*appends* a PAD row, consuming one of only 4 slots and shifting the real ids
after it. Unreachable today (every index derives from the `ALL_*` registries).

**MINOR — `OBS_SCHEMA.md` had gone stale as a normative contract**: the status
banner still called the run half unimplemented, §4 still listed
`MAX_SELECT_CANDIDATES` as *TBD*, and §6 still said "eight" in-combat-only relic
counters where `relic_obs` holds ten.

Two precision corrections the reviewer made to T5a's own source research, kept
because a future lane may rely on it: the select screen's effective sort key is
`(remapped rarity, localized Title, Id)` — `NCardGrid.GetCardRarityComparisonValue`
remaps Status/Curse/Event/Quest/Token — and the AI branch does *not* truly mirror
the UI (raw enum rarity, `Id` rather than `Title` as secondary). Also
`CardSelectCmd.cs:396-399` has an auto-select-everything short-circuit that
returns raw pile order. None of it affects this lane, which sorts on its own
canonical key by design — but it matters if anyone ever argues the sort can be
relaxed.

### Wave 2 review findings (2026-08-02)

The reviewer verified the *behaviour* adversarially and found no Critical
behavioural defect: positional alignment, the non-leak property itself, the
padding invariant, the `prefix=` contract, and the float/int bounds all hold
under probing. **What it found instead was a guard that does not guard** — the
same shape of failure as wave 1, and the third time in this project that a
green test has been mistaken for evidence.

**CRITICAL — the non-leak test asserted nothing, proven by mutation.**
`test_combat_obs_v4.py:273-293` used a 5-card deck whose opening hand draws all
5, so draw/discard/exhaust were *all empty* and the `cards` block was 96 PAD
rows on both builds; its overflow half then used 106 **identical** Strikes,
where which 96 survive cannot matter. The reviewer monkeypatched
`ObsBuffer.write_rows` to truncate-then-sort — T1's exact defect — and the test
**stayed green**.

Worth stating as a method lesson, because this is now a pattern: T1's leak, T2's
`__subclasses__()` collision and now this were each invisible to the lane's own
suite and each found by an independent pass. **The mutation check is what made
this one conclusive**, and it is cheap: break the invariant at runtime in a
scratch script and confirm the test notices. A test whose failure mode has never
been observed is not a guard. This is now required in the fix brief and should
be required of every future non-leak test in this project.

**IMPORTANT — `_power_aux` was scoped to the wrong set.** It swept
`PowerInstanceType.INSTANCED*` classes, which is complete *for that scope*, but
the project's own admissibility principle — a value is admissible if the game
displays it — has a direct analogue for powers in `PowerModel.DisplayAmount`,
exactly as `RelicModel.ShowCounter` governs relics. Four **ported** powers
override it with per-instance state the observation cannot express:
`hardened_shell` (`max(0, Amount − damageReceivedThisTurn)`), `sloth` and
`tender` (cards played this turn), and `slow`. Concretely: an enemy with
Hardened Shell 12 that has already absorbed 11 damage this turn is
indistinguishable from one that has absorbed none. `slow` is the worst case —
the `amount` currently encoded is a number the game never displays and the
engine never reads (its multiplier is `1 + 0.1 * _cards_this_turn`).

**IMPORTANT — three `…overflow` floats can never fire.** `_hand_rows`,
`_enemies_rows` and `_potions_rows` each build exactly `cap` rows, so
`write_rows` never sees an over-cap sequence. Measured: an 8-enemy encounter
hides 2 enemies with `enemies.overflow == 0.0`. OBS_SCHEMA §2.3's promise that
the policy "can at least see that its view is incomplete" was not being kept
precisely where the view can be incomplete.

**IMPORTANT — `damage_matrix` alignment went dark.** The v3 test covering it
lived in `test_full_env.py`, which is now uncollectable over a single
module-level import — taking ~6 unrelated non-observation tests with it
(every-encounter completion, seed determinism, terminal reward, potion
targetability).

**Minor:** the relic non-leak assertion was weakened for all 29
`EXCLUDED_RELIC_STATE` entries when the reviewer's strong-form sweep showed only
**two** need the exemption (`beating_remnant._received_this_turn`,
`vambrace._triggering_card`, both routing through real damage/block hooks); two
vacuous identity assertions over probe dummies that are deliberately outside the
monster vocabulary; no behavioural pin on `card_obs="features"`;
`AblatedObsEnv` returns the int half by reference.

**One finding OVERRULED by me, recorded so it is not re-litigated.** The
reviewer marked spec-compliance ❌ over the module docstring's "Replaces the v3
flat float `Box` (17,873 floats, ~96% of it sparse one-hot categoricals)",
reading it as a banned before/after figure. It is not: there is no "after"
beside it, no old-vs-new ratio, and no improvement claim — the ~96% is a
composition ratio *within* the old encoding. The Measurement rule bans
comparisons that attribute a **result** to the change (checkpoint scores, sps,
deltas), and the project prompt and `OBS_SCHEMA.md` §1 both state these same
motivation figures. Removing it from the code while both documents keep it would
be incoherent. The docstring stays; no new-side number may be added beside it.

**Ownership gap this review exposed.** Three files that phase 1 breaks are
assigned to **no lane** in the wave table: `sts2_rl/evaluation.py` (`:117`
`observation_space.shape[0]`, `:132` `ablation_transform`'s flat fancy-index),
`eval.py`, and `test/test_full_env.py`. The first two join T6; the third joins
the test-rewrite wave. An unowned broken file is how a lane's red set stops
shrinking without anyone noticing.

### Wave 2 fix pass — accepted (2026-08-02)

All 8 actionable findings fixed; `test_combat_obs_v4.py` 39 → **50 tests**. The
failing/erroring set is unchanged *by name*, not merely by count — the only
delta is the +11 new tests.

**I verified the Critical item myself rather than accepting the report.** Running
the lane's mutation script: with truncate-then-sort injected into `write_rows`,
the rebuilt non-leak test fails with a **12-float mismatch at real card-row
indices** — and the overflow assertion still passes, so the RED is a genuine byte
mismatch and not an artefact. The guard now guards.

Worth recording, because it is the same lesson one level up: **the fix lane
caught a flaw in its own mutation check mid-task.** Its first buggy `write_rows`
omitted the overflow warning, so the "RED" it produced was `pytest.warns` failing
with DID NOT WARN — a red result that proves nothing about the leak. It noticed,
replicated the real warn-once behaviour, and re-ran. A mutation check can itself
be vacuous; the fix is to look at *why* it went red, never just that it did.

One nice piece of reasoning worth keeping: for `slow`, C#'s `DisplayAmount` is
`raw_counter * 10` and this module's `ABS_SCALE` is 100, so `displayed /
ABS_SCALE` and `raw_counter / 10.0` are **the same float** — not two competing
scale choices. A test asserts both forms agree, so the equivalence cannot rot.

The brief's C# table for the four display-amount powers was verified correct
against all four `.cs` files. One correction the fix lane made to the earlier
report: `test_vec_env.py` contributes **7** failures, not the 6 the T4 report's
prose said; the file-level totals were always right.

**Controller decision: no second review of T4.** I independently reproduced the
Critical item's proof, the suite shape is unchanged by name, and the remaining
items were mechanical. A full re-review is folded into the final whole-branch
review instead of spending a cycle here. Recorded so it is a decision, not an
omission.

**Task 0 handed to the next lane** (`3b` in the fix brief): the combat
observation's `potions` block is `MAX_POTIONS` = 3 rows, but
`driver.py:267` masks with the **run's** `max_potions`, which `run.py:813` grows
to 4 with Phial Holster — and `player.py:136-139` really does allocate that 4th
slot. So a Phial Holster run offers the policy a legal action for a potion slot
the observation cannot show. Confirmed at source by me. v3-inherited, but v4 is
the bump and this project pays the bump once, so it is fixed in wave 3 with one
shared `MAX_POTION_ROWS` constant rather than two that must agree.

### Wave 1 review findings

**T1 shipped a real hidden-information leak, caught by reviewing rather than
by its test.** `ObsBuffer.write_rows` truncated to `cap` and *then* applied the
canonical sort. That leaves **which rows survive** a function of the caller's
order, so a card pile that overflows its cap observes differently depending on
its shuffle — precisely the draw-order leak the sort exists to prevent
(`OBS_SCHEMA.md` §5.3). Demonstrated before fixing: one 6-row multiset into a
cap-4 block produced **5 distinct observations** across 6 input orders.

The lane's own non-leak test only permuted a row list that *fit*, so it passed.
This is the concrete case for the prompt's "reviewers must not defer to the
brief or the report — a green suite is not evidence."

Fixed by sorting **before** truncating, with the asymmetry documented at the
site: `sort=True` must sort first (the retained set has to be a function of the
multiset alone), while `sort=False` must truncate the caller's sequence
directly (there the prefix *is* the meaning — powers arrive in C#'s application
order and the first `cap` are the oldest instances). Pinned by two new tests,
`test_canonical_sort_survives_truncation` and
`test_unsorted_truncation_still_keeps_the_callers_prefix`.

**T2 shipped three order-dependent tests** — green in isolation, RED under the
full suite. `_all_subclasses(Affliction)` walks `__subclasses__()`, which is
process-global and therefore also finds `_HookedAffliction`, the test double
declared at `test/test_round13_listener_derivation.py:400`. The registry
coverage test then demanded a `@register_affliction` decorator on a class that
is deliberately unregistered.

Worth naming the failure mode: a test that passes alone and fails in the suite
reads as a real regression and depends on collection order, so it costs
somebody an afternoon later. Caught here only because the lane's own
verification (its file, isolated) and mine (the whole suite) disagreed — which
is an argument for the integrator always re-running the full suite rather than
accepting a lane's green.

The *intent* was right and is preserved: discovery must be independent of the
registry or it cannot catch a missing decorator. Fixed by keeping only
subclasses declared in `Affliction`'s own module, while still walking
*through* foreign ones in case a real affliction is ever declared beneath a
test double.

**Two smaller things, both mine to own:**

- My brief for T2 listed `afflictions.py` and `vocab.py` but not
  `enchantments.py`, so the agent correctly **stopped and reported** rather
  than wiring the enchantment vocabulary into a file it did not own. I closed
  it. Frozen now: afflictions 7/16, enchantments 19/32, both in `vocab.json`.
- `OBS_SCHEMA.md` §5.1 was internally inconsistent — `.id` for one-int rows,
  `.ids` for multi-int rows. T1 resolved it to a uniform `.ids` / `.f` and the
  document has been corrected to match, so the spec and the code agree on the
  convention three later lanes read.

### RESOLVED — the `obs_mode` question is moot, do NOT build it

I had flagged that the old path could not stay runnable for A/B unless the env
could emit either shape, and proposed an `obs_mode` in `{"flat", "entity"}`
alongside `card_obs`.

**The prompt's revision dissolves it.** The third `--arch` value lost its A/B
rationale and gained a correctness one: it exists so an old arch-stamped
checkpoint is *refused on a name it no longer matches*, instead of failing on
a shape mismatch deep inside `load_state_dict`. Nothing has to run the old
observation, because there is no comparison to run.

Consequences, all simplifications — worth stating because building `obs_mode`
anyway would have been a large, permanent, and entirely wasted complication:

- **The envs emit v4 only.** No dual-path builder, no mode parameter threaded
  through `full_env` / `run_env` / `curriculum_env` / `vec_env` / `evaluation`
  / `probes`, no per-mode `OBS_SCHEMA_VERSION`.
- **The old flat builders can be deleted outright** rather than preserved
  behind a flag. `test_obs_byte_identity.py` (phase 0's golden) goes with
  them: it pins an encoding that will no longer exist, and there is nothing
  left for it to be a regression detector *for*. That is a deletion with a
  stated reason, which is the bar the prompt sets — not a test quietly
  dropped because it went red.
- **T6's checkpoint work shrinks** to a hard failure plus the new arch name.

### Engine bugs found by the censuses (not obs-schema work)

1. **FIXED — `Enchantment.modify_card_play_count` had no base-class default.**
   `EnchantmentModel.EnchantPlayCount` is `virtual … => originalPlayCount`
   (`EnchantmentModel.cs:456-459`) with exactly two overriders in the game
   (Glam, Spiral) and exactly two in the sim — but the sim shipped the
   overrides *without* the default, so `Card.enchanted_replay_count`
   (`cards/base.py:310`) raised `AttributeError` for the other **18 of 20**
   enchantments. Reachable in ordinary play: Hidden Gem's eligibility filter
   (`cards/colorless_skills.py:369`) calls it on every card in hand, so any
   run where an enchanted card met a Hidden Gem crashed. The powers census hit
   it during masked-random run play.
   Fixed in `sts2_rl/enchantments.py` with the C# default; pinned by
   `test_shared_enchantments.py::test_every_enchantment_answers_enchanted_replay_count`,
   which was written RED first (it failed on `AdroitEnchantment`, the first id
   alphabetically) and covers all 20 enchantments rather than the one that
   happened to crash. Suite after the fix: **4145 passed / 6 xfailed / 0
   failed** — phase 0's 4144 plus this one test, no regressions. Staged.
2. **OPEN, OWNED ELSEWHERE — run-env `env.step()` can hang indefinitely.**
   Several census processes wedged inside a single step for >45 minutes under
   masked-random play with an invincible player. It cost the census its
   `underdocks` and 3-act distributions. The prompt now carries this as an
   *entry gate* on the whole project; the user has assigned it to the
   concurrent source-fidelity audit ("should fix any possible infinite loops
   that cause `env.step()` to hang"), so **this project does not diagnose it**
   and must not paper over it with a timeout-and-truncate.

   Two structural facts worth keeping, both from the prompt and both
   independently true of the code as read: `max_steps` cannot catch it
   (`_steps` counts *decisions*, so engine work between two decisions is
   unbounded by construction), and nothing in-process can stop it (during the
   hang the env greenlet is not running, so `_kill_driver`'s
   `glet.throw(GreenletExit)` — which only lands on a *parked* greenlet — is
   inert). `env_baseline.py --step-timeout` therefore uses an out-of-band
   `faulthandler` watchdog, which is the one mechanism that does fire, and it
   exits rather than continuing.

---

# Post-phase-1: the two held items, settled (2026-08-02)

Both items the phase-1 report listed as "needs a user decision" are now closed.
Neither needed a code change. Three read-only censuses did the work; full
reports were written to the session scratchpad and their findings are
transcribed into `OBS_SCHEMA.md` §7, which is the durable home. Recorded here
because this ledger is authoritative.

## `MAX_SELECT_CANDIDATES` stays 96 — a cut to 32 was proposed and rejected

The R4 census R4's own text asked for was **un-held and run**. Measured max:
**17 candidates, reached by floor 13 of act 0**, over 400 masked-random
episodes on `STS2CurriculumRunEnv`.

The proposal under consideration was 32, on the assumption that this constant
sized the *enemy* list. It does not — it sizes **cards** in a `SELECT_CARDS`
screen (`run_env.py:252`, `MAX_SELECT_CANDIDATES = MAX_COMBAT_CARDS`). ~25
event/relic/shop/rest-site sites pass the entire current deck as candidates,
and nothing in the engine caps deck size (`run.deck` is a plain list, no
guard). 17 is already past half of 32 under a policy that takes almost no card
rewards, inside the first of four acts; a real policy crosses 32 before the
midgame, and every removal/upgrade/enchant/transform screen thereafter would
drop an arbitrary tail of the deck — worst for the largest-deck, most
successful runs.

**The census's own limit, stated plainly:** masked-random play never left act 0,
so this measurement can *refute* a smaller cap but cannot *certify* 96. 96
remains a static argument. What changed is that its failure mode is now
quantified instead of asserted. This is the same act-0 ceiling already recorded
against `MAX_RELIC_ROWS`/`MAX_COMBAT_CARDS`, and it reproduced exactly as
predicted — worth noting as evidence that the caveat is real and not
boilerplate.

**Hazard for any future change:** nothing asserts `N_ACTIONS == 243` (only a
docstring mentions it), and every layout constant derives symbolically from
`MAX_SELECT_CANDIDATES`. Moving it silently reflows `POTION_BASE`/`N_ACTIONS`
and invalidates a v7 checkpoint's action head with no version bump to catch it.

## R3 — deferred here, then SHIPPED later the same day

> **SUPERSEDED — read this first.** The verdict at the end of this section
> ("deferred on cost") was **reversed within the hour**, and R3 shipped. The
> analysis below is left intact because all of it is still correct and the
> shipped design rests on it — the refuted repeat premise, and the
> inadmissibility of a move id, both still hold and both still constrain what
> the feature is allowed to contain. **Only the cost verdict was wrong, and it
> was wrong because I priced the wrong design.** See "R3, actually shipped" at
> the end of this file for what changed and why.

The two arguments available on either side were tested and **both failed**,
which is the part worth keeping.

**Against building it:** "no enemy can perform the same move on two consecutive
turns, so the previous intent is inferable from the current one." **FALSE.**
`RandomBranchState.add_branch`'s default `repeat_type` is `CAN_REPEAT_FOREVER`
— consecutive repeats are the engine's default and `CANNOT_REPEAT` is opt-in
per branch. Census of all 106 registered monsters: **40 (37.7%) can show the
identical move on consecutive turns** — 30 of 79 state-machine monsters, 10 of
27 hand-rolled. Mechanisms: self-loops (`Guardbot`, `Noisebot`, `Zapbot`,
`GasBomb`), explicit budgets (`HunterKiller`'s PUNCTURE, `hunter_killer.py:45-50`,
porting `AddBranch(state, 2)` as `max_times=2`), unguarded branches
(`Fabricator`), and combat-state conditionals with no history check
(`BowlbugRock`). Includes a boss and several elites.

**For building a cheap version:** add the enemy's current **move id** as one int
per enemy row — a fraction of R3's cost, and free of the `net_id`/phase-epoch
problem because it describes *now* rather than a buffer that can stale.
**INADMISSIBLE** under §6's display-path rule. `NIntent.cs:133-136` writes a
number only for `AttackIntent` and `StatusIntent`; the other **12 of 15
`IntentType` values render as a bare numberless icon**, and the tooltip
(`AbstractIntent.cs:45,67-79`) is keyed by intent CLASS (`"BUFF.title"`), never
by move or monster — the game never displays a move name anywhere in the render
path. Corroboration that the game collapses even further than its own type
system: `IntentType.DebuffStrong` is computed (`DebuffIntent.cs:7-21`) but read
nowhere in any rendering code.

**What survives:** a history of *displayed* facts (9 `MoveType` booleans + attack
and status numbers) is genuinely admissible — a human remembers what they saw,
and that is how a player tracks a repeat budget. But its resolution is capped by
the above, so it recovers hidden budget/cooldown state only where the displayed
numbers already separate the moves. Modest value; the keying cost (`net_id` +
per-creature phase epoch, 3 reordering encounters, 9 phase-changing monsters) is
unchanged and was re-confirmed. **Deferred on cost, not on premise.**

**Free corollary — an existing design validated, no action needed.** The
admissibility check independently confirms the §5 enemy row is right to merge
Debuff/DebuffStrong/CardDebuff into one flag and Stun/Sleep into one: those
merges match the display path rather than the internal type.

## Method note

All three censuses were dispatched as read-only subagents forbidden from editing
either repo, with throwaway scripts confined to the scratchpad. Each was briefed
to *test* its premise rather than confirm it, and to count and name what it could
not analyse rather than drop it. The R3 premise came in as a confident assertion
and was refuted on the first structural check (`add_branch`'s default), which is
the argument for briefing censuses adversarially: a brief asking "verify that no
enemy repeats" would plausibly have come back agreeing.

---

# Post-phase-1, round 2: the admissible intent numbers (2026-08-02)

Follow-on from the R3 decision above. The user asked for "the type of move, and
the number if it is an attack" as a cheap substitute for the inadmissible move
id. **Both were already in the observation** — `full_env._enemy_floats` writes 9
`MoveType` booleans (fields 9-17) and 4 attack-damage fields from
`preview_incoming_damage` (fields 18-23). Reporting that plainly was the correct
first answer. But re-reading the row against the admissibility findings turned up
two real gaps, one of which was not an observation bug at all.

## Gap 1 — `StatusIntent`'s card count (observation; schema 4 → 5)

`NIntent.cs:133-136` writes a displayed number for `AttackIntent` (damage +
hits) **and** `StatusIntent` (card count). Only the former was encoded, so "will
add Dazed" and "will add 3 Dazed" were identical to the model while a human sees
the number. `enemies.f` widened 24 → 25; `full_env.OBS_SCHEMA_VERSION` 4 → 5.

**Coverage caveat, stated because the field looks more complete than it is:**
only **5 of the sim's 18 `StatusIntent` construction sites carry a count**. The
field reads 0.0 for the other 13 rather than fabricating a number — that is the
pre-existing `monster/_intent_count_lost` port gap, not a new one. The encoding
is right; two-thirds of the coverage is blocked on that gap.

## Gap 2 — `DeathBlowIntent` was an ENGINE bug, not an observation bug

Found by the same sweep, and the more valuable of the two. `full_env`'s intent
flags and `previews.preview_incoming_damage` both gate on `MoveType.ATTACK`, and
neither of the two `Intent(MoveType.DEATH_BLOW, ...)` sites passed
`also=(MoveType.ATTACK,)`. The tempting fix is to special-case DEATH_BLOW in the
observation layer. **That would have been wrong.**

The game's `MonsterModel.IntendsToAttack` (`MonsterModel.cs:241-245`) ORs
`IntentType.DeathBlow` with `IntentType.Attack` **for gameplay** — it gates
`GoForTheEyes.cs`'s targeting and effect. And `DeathBlowIntent` is a C# subclass
of `AttackIntent`, so `NIntent.cs:135`'s `is AttackIntent` test renders its damage
number like any attack. So the sim's intents were simply wrong, and **Go For The
Eyes has been silently failing against Living Fog and Waterfall Giant** —
a real gameplay defect, independent of RL.

Fixed at the two intent sites (`monsters/underdocks/living_fog.py`,
`waterfall_giant.py`). `full_env.py` and `previews.py` were correct as written and
were not touched; observation width unchanged.

**Note for the monster source-audit stream:** that stream audited all 109
monsters and declared complete, and this gap was in two of them. Nothing about it
was specific to those files — a sweep of the other `Intent(...)` sites for the
same `also=` omission is warranted.

## Gap 3 — `RUN_OBS_SCHEMA_VERSION` did not move when the run observation did

Caught by the controller re-measuring both envs rather than trusting the lanes'
reports. **The run envs embed the combat block**, so the 4 → 5 combat bump
widened run `f_dim` 4434 → **4440** while `RUN_OBS_SCHEMA_VERSION` stayed **7**.
"Schema 7" then named two incompatible contracts. Bumped 7 → **8**.

A lane had argued no bump was needed because `check_checkpoint`'s `obs_dim` shape
check would still reject a stale run checkpoint. Probably true, and beside the
point: that is the *fallback* catching it, and it surfaces as a shape mismatch
rather than the honest "predates a schema change, use `--fresh`" path the version
gate exists to produce. **A version constant that no longer identifies its
contract is the defect, regardless of what catches the symptom.**

Now pinned mechanically by `test_run_schema_version_matches_declared_dims`
(`test/test_run_obs_v4.py`), which asserts the `(version, f_dim, i_dim)` triple
so an embedded width cannot move again without a deliberate bump.

## Gap 4 — the arch-refusal safety net was silently disabled by the bump

`checkpoints._V4_GENERATION_SCHEMAS` was a `frozenset({4, 7})` **enumerating
known-good versions**, so bumping the combat schema to 5 did not error — it
**stopped refusing `mlp`/`entity`**, the safety feature added earlier the same
day. Replaced with `_V4_GENERATION_MIN_SCHEMA`, a per-`env_kind` threshold dict
checked with `>=` via `_is_v4_generation()`, which also raises loudly on an
unrecognised `env_kind`. A future bump is automatically ≥ the threshold, so the
refusal cannot lapse again; `test_make_model_refuses_future_v4_generation_schema`
pins that generically via a schema-999 monkeypatch.

## The pattern in all four

Gaps 2, 3 and 4 all lived **between** correctly-implemented parts, not inside
one: the observation layer and the intent constructors each looked right; the
combat env and the run env each looked right; the bump and the guard each looked
right. This is the same shape as phase 1's headline defect (the encoder's
presence mask vs the schema's padding rule), and it is now four for four. **The
per-lane review cannot see these by construction — only re-measuring the whole
system can.** Concretely, what caught gap 3 was the controller running both envs
and printing `(version, f_dim, i_dim)` instead of reading two green reports.

Suite across the round: 4389 → **4394 passed / 6 xfailed / 0 failed**.

---

# R3, actually shipped — and the decisions that settled with it (2026-08-02)

This section supersedes the "R3 stays deferred" verdict recorded above. It is
the durable record of every decision taken after phase 1 closed. `OBS_SCHEMA.md`
§5.4 is the normative description of what was built; this is why.

## What reversed the deferral: I priced the wrong design

The deferral rested on a cost estimate with two components — `net_id` keying so
a mid-combat reorder cannot hand one enemy's history to another, **plus** a
per-creature phase epoch for the ~9 monsters that force phase transitions.

**The phase-epoch half only ever applied to a history of MOVE IDS**, where a
phase change makes the same id mean something different. The user's reframing —
*store the previous intents, not move ids* — deletes that half outright. A
displayed intent is a record of what was on screen; a later phase change does
not retroactively make it false, any more than a human forgets being hit for 12
because the boss transformed afterwards. Only `net_id` keying survived, and that
is modest.

**The lesson is not "the estimate was too high."** It is that a cost estimate
silently inherits the design it was made against, and carrying it to a different
design is how a good feature stays dead. The premise ("no enemy repeats a move
on consecutive turns") had already been refuted by census, and the substitute
(a raw move id) had already been ruled inadmissible — so the *only* thing still
blocking R3 was a number attached to a design nobody was proposing any more.

## What shipped, and what it is allowed to contain

Per enemy, the last **3** displayed intents, keyed by `net_id`, most-recent-first,
each slot carrying an explicit `recorded` presence float.

A slot holds **exactly what the game drew**: the 9 `MoveType` flags, the attack
preview's `per_hit`/`hits`/`total`, and the `StatusIntent` card count — 15
floats. **No move id**, because `NIntent.cs:133-136` renders 12 of 15
`IntentType` values as a bare numberless icon and `AbstractIntent.cs:45,67-79`'s
tooltip is keyed by intent class, never by move or monster. That verdict is
unchanged by shipping the history: a record of admissible facts is admissible; a
record of inadmissible ones would not have been.

`post_block` was **excluded** — it combines a displayed number with the player's
own transient block at that moment, which is not retained as a discrete memory
the way the damage number is. `total` was kept, being a pure function of two
numbers co-displayed on one icon. Either call was defensible; this one is
recorded so it is not silently re-decided.

## N = 3 is a MEASUREMENT, not a static argument

Phase 1 was repeatedly, fairly criticised for caps that rested on static
arguments (`MAX_RELIC_ROWS`, `MAX_COMBAT_CARDS`, `MAX_SELECT_CANDIDATES`). N is
not one of them, because the engine defines exactly how much history matters:
a branch's `cooldown` zeroes its weight if the move appears in the **last N
logged moves**, and `CAN_REPEAT_X_TIMES(n)` caps consecutive repeats.

Census across every registered monster: **deepest `cooldown` = 3**
(`Flyconid.V_SPORES`, `FakeMerchant.ENRAGE`, `TwoTailedRat.SCREECH` — three
independent sites, nothing higher); **deepest `max_times` = 2** (five sites);
`CANNOT_REPEAT` is a 1-move window. So 3 previous intents exactly span the
deepest recency window the engine consults, and a 4th would be dead weight.

`USE_ONLY_ONCE` is **deliberately excluded** from the derivation: it is a
permanent flag, not a recency window, so **no bounded N recovers it.** Stating
that is the point — it marks the one class of hidden move-gating state this
feature does not and cannot expose, rather than leaving a reader to assume the
history is complete.

Cost: 6 × 3 × 15 = 270 floats, **19.2%** of the pre-R3 combat `f_dim`, under the
50% gate that would have required stopping to ask.

## The recording hook, because getting it wrong makes the feature lie

Snapshotting happens in `CombatState._roll_enemy_intents`, the existing
once-per-player-turn reroll pass: each living enemy's about-to-be-superseded
intent is recorded immediately **before** the reroll.

Both nearby alternatives are wrong in instructive ways. Recording inside
`current_intent` would fire on every *read*, including mid-turn observation
builds, duplicating entries. Recording *after* the reroll would capture the new
intent instead of the superseded one, shifting the whole history by a turn.
Preview numbers are computed at record time rather than derived later, because
they depend on player state that has since changed.

## Schema versions, and the propagation rule this cost us twice

Final: combat **6**, run/curriculum **9**.

Three combat bumps landed today (4 → 5 StatusIntent, 5 → 6 R3) and the run
envs followed. **The run observations embed the combat block**, so *any* combat
widening widens them too. That propagation was missed once already (the 4 → 5
bump left `RUN_OBS_SCHEMA_VERSION` at 7 while its `f_dim` moved 4434 → 4440,
leaving one version naming two contracts), which is why it is now stated as a
rule here and pinned mechanically by
`test_run_schema_version_matches_declared_dims`.

**Bumping remained free all day only because nothing has been trained for real
yet.** Phase 1's organizing rule — *the from-scratch retrain is paid exactly
once* — is what makes that true, and it stops being true the moment a real run
starts. Everything schema-affecting should land before then.

## The other two decisions, settled and recorded

- **`MAX_SELECT_CANDIDATES` stays 96.** Censused; a proposed cut to 32 was
  rejected. Full reasoning in the earlier post-phase-1 section and
  `OBS_SCHEMA.md` §7. It sizes *cards in a selection screen*, not enemies.
- **`mlp` and `entity` are refused against the modern envs**, approved by the
  user. The guard is now a per-`env_kind` threshold (`_V4_GENERATION_MIN_SCHEMA`)
  rather than an enumeration of known-good versions, because the enumeration
  silently stopped refusing at the first bump that outran it.

## The pattern worth carrying into phase 2

Five defects today lived **between** correctly-implemented parts, not inside
one: the encoder mask vs the padding rule; DeathBlow's intent vs the observation
gate; the combat bump vs the run version; the bump vs the arch guard; and the
combat row of the phase-1 report vs every lane's ownership boundary. Per-lane
review cannot see these by construction — each side is individually right. What
caught them was re-measuring the whole system: running both envs and printing
`(version, f_dim, i_dim)` rather than reading two green reports.

The corollary for how this work was run: **lanes reporting that their brief was
wrong was the single highest-value thing they did**, and it happened on nearly
every dispatch — the potion belt's true ceiling, the six per-instance powers,
`import sts2_rl` breaking outright, and here the phase-epoch cost that turned
out to belong to a design nobody was proposing.

## Verified end state (controller-measured, not lane-reported)

```
combat schema 6   f 1677  i 606   9,132 bytes/env/step   79 actions
run    schema 9   f 4710  i 1464  24,696 bytes/env/step  243 actions
curric schema 9   f 4710  i 1464  24,696 bytes/env/step  243 actions
```

Suite **4399 passed / 6 xfailed / 0 failed** (`--ignore=test/test_conformance_
floor_state.py`, whose 2 failures are a missing `933T39V18D/floor_49` fixture —
an environment gap, never counted). Baseline at phase-1 close was 4389.

**Staged, never committed** (CLAUDE.md §4); `HEAD` unchanged at `206c9bd`.
