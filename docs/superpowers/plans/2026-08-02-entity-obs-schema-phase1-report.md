# Entity observation schema — phase 1 report

Execution of `prompts/entity-obs-schema.md` phase 1, 2026-08-02. The blow-by-blow
record, every measurement, and every decision's reasoning live in the ledger,
`docs/superpowers/plans/2026-08-01-entity-obs-schema.md`, **which is
authoritative if the two ever disagree.** This file is the readable summary.

`OBS_SCHEMA.md` is the normative contract for what was built.

**Staged, not committed** (CLAUDE.md §4) — `HEAD` unchanged at `206c9bd`. (The
file count that used to sit here — 158 at phase-1 close, then 160, then 163 —
went stale three times in one day and is deliberately gone: `git diff --cached
--stat` is authoritative and always current, so a hand-copied number here is
pure liability. This line was also *false* when first written: only wave 1 was staged and
`sts2_rl/tensor_obs.py` was still untracked, so a `git commit -a` would have
shipped an unimportable tree. The whole-branch review caught it; staging is the
controller's job and deferring it while claiming otherwise was my error.)

---

## What phase 1 did

Replaced the flat float `Box` observation — in which categorical facts were
written as wide one-hot float blocks — with an integer/float `Dict`, across both
environments, plus the four observation riders that had to ship inside the same
schema bump.

The organizing rule throughout: **the from-scratch retrain is paid exactly
once.** Anything that would have forced a second schema bump shipped now;
anything with no schema impact was deferred to phase 3.

## The contract

```python
observation_space = spaces.Dict({
    "f": spaces.Box(0.0, 1.0, shape=(F,), dtype=np.float32),
    "i": spaces.Box(0, MAX_ID, shape=(I,), dtype=np.int32),
})
```

Stored id = frozen-vocab index + 1; **`0` is PAD**. A padded row is `id == 0`
*and* all-zero floats, so "present at amount 0" stays distinguishable from
"absent" — which is what the old explicit presence bit bought. Embedding tables
get `capacity + 1` rows with `padding_idx=0`, so an absent row contributes a zero
vector to a masked sum-pool and takes no gradient. **There is no separate mask
array.**

`vocab.json` is untouched: index *i* still means the same id forever, and the
`+1` lives at encode time.

Both halves keep named `(segment, width)` maps, so `--zero-segments`, the model's
segment plan and the pin tests still address the observation by name.

## Absolute figures

Measured on the finished tree (`env.reset(seed=0)`, dtype × shape):

| env | schema | `f_dim` | `i_dim` | elements | bytes/env/step | actions |
|---|---|---|---|---|---|---|
| `STS2FullCombatEnv` | 4 | 1401 | 606 | 2007 | 8,028 | 79 |
| `STS2RunEnv` | 7 | 4434 | 1464 | 5898 | 23,592 | 243 |
| `STS2CurriculumRunEnv` | 7 | 4434 | 1464 | 5898 | 23,592 | 243 |

**These are absolute figures and nothing is compared against them.** Per the
prompt's Measurement section and an explicit user decision, **there is no
old-vs-new comparison in this project, in any form.** The riders changed the
action layout, the observation contents and the encodings simultaneously, so a
delta would attribute nothing — and it fails even policy-free, because a random
policy over a different action space samples a different distribution.

> **Correction (2026-08-02, R3 shipped — the CURRENT figures):** both
> corrections below are themselves now superseded. R3 (per-enemy intent
> history, `OBS_SCHEMA.md` §5.4) added 6 × 3 × 15 = 270 floats to the combat
> block, which the run envs embed. Re-measured on the finished tree:
>
> | env | schema | `f_dim` | `i_dim` | bytes/env/step | actions |
> |---|---|---|---|---|---|
> | `STS2FullCombatEnv` | **6** | **1677** | 606 | **9,132** | 79 |
> | `STS2RunEnv` / `STS2CurriculumRunEnv` | **9** | **4710** | 1464 | **24,696** | 243 |
>
> The two corrections below are kept rather than deleted because the sequence
> is the point: three combat bumps landed in one day and the run figures had to
> be chased twice. That is why the propagation rule ("any combat widening
> widens the run envs") is now stated in the plan and pinned by
> `test_run_schema_version_matches_declared_dims`.
>
> **Correction (2026-08-02, StatusIntent card-count gap): the
> `STS2FullCombatEnv` row above is ALSO stale.** `enemies.f` widened 24 → 25
> per enemy slot to admit `StatusIntent`'s displayed card count, so:
> schema **5**, **`f_dim` = 1407**, `i_dim` unchanged at 606, elements **2013**,
> **8,052 bytes/env/step** (`(1407 + 606) × 4`), actions unchanged at 79.
> (This row was missed when the run rows below were corrected — it sat outside
> every lane's file ownership, which is exactly how the run-version defect
> below arose too.)
>
> **Correction (defect fix, 2026-08-02, `RUN_OBS_SCHEMA_VERSION` 7 → 8):** the
> `STS2RunEnv` / `STS2CurriculumRunEnv` rows above are stale. Both envs embed
> `full_env`'s combat block verbatim under a `"combat."` prefix, so the later
> same-day combat bump (`OBS_SCHEMA_VERSION` 4 → 5, the `enemies.f` row's new
> StatusIntent card-count float) widened their `f_dim` too, +6 (6 enemy
> slots × 1 float) — without `RUN_OBS_SCHEMA_VERSION` moving, which is the
> defect. Corrected, re-measured on the finished tree: **`f_dim` = 4440**,
> `i_dim` unchanged at 1464, elements 5904, **23,616 bytes/env/step**
> (`(4440 + 1464) × 4`), schema **8**, actions unchanged at 243. See
> `OBS_SCHEMA.md` §5A for the normative correction and
> `test_run_schema_version_matches_declared_dims`
> (`test/test_run_obs_v4.py`) for the pin.

## Riders

| rider | outcome |
|---|---|
| **R1** relic block with per-relic mutable state | **shipped**, both observations. The combat obs had no relic segment at all; the run obs was presence-only. Admissibility is decided by the game's own display path (`RelicModel.ShowCounter`, status tint, `IsUsedUp`), never by usefulness. |
| **R2** card-instance aux fields everywhere | **shipped**, one shared row builder (`card_instance_row`) for piles, deck, reward cards and select candidates — everywhere except `hand`, which builds its own 3-int/29-float row (`full_env._hand_rows`) rather than the shared 4-int/4-float shape, since a hand slot carries the R2 card-instance-aux fields PLUS the pre-existing 24-field feature row `card_instance_row` has no room for. Afflictions and enchantments got new frozen vocabularies (7/16 and 22/32, sized to the *game* total, not the ported count). |
| **R3** per-enemy intent history | **DEFERRED**, pending an explicit user decision — see Open items. |
| **R4** select candidates as instance rows + true candidate actions | **shipped**, and its pre-existing failing acceptance test is green. |
| **R5** character id + ascension | **CUT** before phase 1 (recorded in the ledger): both are constants until a second character exists, and that port brings its own retrain. |
| **R6** log1p for unbounded scalars | **shipped**, then retuned after review — see below. |
| **R7** watched-history statistics | **DEFERRED** (lowest value; pity was cut outright as hidden information). |

## Deliverables

- **The schema document** — `OBS_SCHEMA.md`, corrected in place at each wave
  with the corrections marked rather than silently overwritten.
- **The hidden-information non-leak test** — pile order and select-candidate
  order are unobservable, pinned including *past* the truncation cap, and
  `EXCLUDED_RELIC_STATE` is the fixture for relic state that must never reach
  the tensor.
- **Observation-content assertions** — the real check the prompt asked for:
  decode the integer observation back to facts and assert against direct
  `CombatState` / `RunState` reads.
- **`power_cmd/G5`'s observation residue is CLOSED.** Phase 0 closed the engine
  half conservatively and left a deliberate tripwire test asserting the
  observation still collapsed power instances to one row per id. Phase 1 closes
  it: two `the_bomb` fuses are now two rows with independent aux. The tripwire is
  inverted into a closure test, verified by reproducing the old collapse and
  watching the new test go RED against it.

## Validation

Against **engine ground truth**, never against the old environment.

- **Suite: 4389 passed / 6 xfailed / 0 failed / 0 errors** (`--ignore=test/test_conformance_floor_state.py`,
  whose 2 failures are a missing `933T39V18D/floor_49` fixture — an environment
  gap, never counted). Baseline before phase 1 was 4257 passed. **Final
  fix-pass correction:** this line said 4382, already stale by the time of
  the whole-branch review (4387 immediately pre-review); the review's own
  fixes (item 1's two new regression tests) landed the count at 4389.
  **Post-phase-1 (2026-08-02):** the rounds recorded at the end of the ledger
  (the two held items settled, then the admissible intent numbers, then R3)
  took it to **4399 passed / 6 xfailed / 0 failed**, verified by the controller
  re-running the whole suite after every lane rather than trusting any lane's
  green.
- **`env_baseline.py sanity --env column` passes**, 300 masked-random episodes:
  423 `select_cards` decisions reached with **zero unaddressable candidates**.
  This tool was RED *by design* and named R4 as its fix.
- **The stack trains end to end.** `--env combat --arch entset --fresh`, 4096
  steps: win rate 0.36 → 0.80, entropy 1.47 → 1.00, KL stable ~0.01. `--env
  column` also completes. Gradients flow and the policy improves; these are
  absolute observations about the new stack, not a comparison.
- **An old arch-stamped checkpoint is refused on its name**, not on a shape
  mismatch inside `load_state_dict` — the reason the prompt asked for a third
  `--arch` value rather than mutating `entity`.

## What the whole-branch review changed after the waves closed

The final pass found one defect that no per-task review could have seen, because
**each side of the seam was individually correct**:

**The encoder implemented half of the padding rule.** `OBS_SCHEMA.md` §2.1 says a
padded row is `id == 0` **and** all-zero floats; `models.py` masked on the id
column alone. So any row with a PAD id and live floats was silently dropped:

- `--card-obs features` writes `card_id = PAD` *by design*, so the hand block's
  pooled contribution to the encoder was **0.0** (vs 29.13 in `hybrid`) — a
  policy that could not see its own hand, with no error;
- `--env run --arch entset`, the flagship config, dropped the `slot_exists` bit
  on every empty potion slot (833 rows across 5 episodes).

There was even a test asserting those hand rows stay "distinguishable from PAD
via their nonzero floats". It was right — it proved the information was *in* the
observation. Nothing checked that the model read it. **A schema rule written in
prose is not enforced until something executes both halves of it, and the join
between a producer and its consumer deserves its own test even when both sides
have been reviewed.**

Two decisions followed from measurement rather than preference:

- **`mlp` and `entity` are now REFUSED against v4/v7 envs.** `models._as_flat`
  concatenated raw ids (up to 640) with `[0,1]`-bounded floats *unnormalized*,
  so the ids did not merely lose their categorical meaning — their magnitudes
  drowned the ~1400 genuinely numeric features under ~600 columns of large
  integers. The usual reason to keep a no-embedding baseline runnable is to
  compare, and this project has no comparison by explicit decision.
- **`--arch` now defaults to `entset`** (as does `ModelSpec.arch`), because the
  refusal above made the previous `mlp` default fail immediately — and a bare
  `py train_torch.py` is the documented entry point. The backward-compatibility
  read `ckpt.get("arch", "mlp")` deliberately still says `mlp`: that describes
  what old unstamped checkpoints genuinely *are*, which is a different question
  from what new work should default to.

Also closed: the dead `migrate_checkpoint` / `migrate_checkpoint_actions` bodies
(broken by this work, so replaced with an honest `raise` rather than left as
unreachable code claiming a migration exists), the six private helpers that
change orphaned, and five stale figures in `OBS_SCHEMA.md`.

## Open items

- ~~**R3 is deferred and needs a user decision.**~~ **SETTLED 2026-08-02 —
  stays deferred, on cost grounds.** Full reasoning and citations in
  `OBS_SCHEMA.md` §7; the short form is that *both* of the tempting arguments
  turned out to be wrong. The premise for skipping it — "no enemy repeats a move
  on consecutive turns, so history is inferable" — is **false**:
  `add_branch`'s default repeat rule is `CAN_REPEAT_FOREVER`, and **40 of 106
  monsters** can repeat consecutively. And the cheap substitute — one
  **move-id** int per enemy row — is **inadmissible**: the game renders 12 of 15
  intent types as a bare numberless icon and never displays a move name, so a
  move id reveals what a human cannot see. What remains admissible is a history
  of *displayed* facts only, whose resolution is capped at the 9 `MoveType`
  booleans plus attack/status numbers — modest value, unchanged cost. The
  keying cost (`net_id` + per-creature phase epoch, 3 reordering encounters, 9
  phase-changing monsters) is unchanged and was re-confirmed by the census.
- ~~**`MAX_SELECT_CANDIDATES` is a static 96, not a measurement.**~~ **SETTLED
  2026-08-02 — stays 96; the census was run and a proposed cut to 32 was
  rejected.** Measured max **17 candidates by act-0 floor 13** over 400
  masked-random episodes — under a policy that takes almost no card rewards,
  already past half of 32 inside the first of four acts. ~25 sites pass the
  whole deck as candidates and nothing caps deck size, so 32 would silently
  drop a tail of the deck at every shop and campfire, worst for the
  largest-deck runs. It remains a **static argument** — an act-0 census can
  refute a smaller cap but cannot certify 96 — and it is still load-bearing on
  *actions*: a candidate past the cap is unclickable, which the real game never
  does. Note for any future change: **nothing asserts `N_ACTIONS == 243`**, and
  every layout constant derives symbolically from this one, so moving it
  reflows `POTION_BASE`/`N_ACTIONS` silently and would invalidate a v7
  checkpoint's action head without a version bump to catch it.
- **Every empirical census is an act-0 floor.** Masked-random play dies in act 0,
  so `MAX_RELIC_ROWS` and `MAX_COMBAT_CARDS` rest on static arguments and want
  re-validating once a trained policy reaches act 2. The one exception is the
  potion ceiling: 10 = base 3 + Phial Holster 1 + Potion Belt 2 + Alchemical
  Coffer 4, a **hard** bound, since each relic is unique and grants once and
  nothing in the game shrinks the belt.
- **R6's `log1p` denominators are reasoned defaults, not measured.** They are
  honest encodings — monotone, non-saturating across the realistic band — but
  nothing pins them to an observed distribution, and no act-0 census could.
- **`--arch entity` now degenerates silently** against v4: zero embedding tables
  and a parameter count identical to `mlp`, because its segment plan keys off v3
  names. The degeneration is pinned by a test rather than hidden, but someone
  typing `--arch entity` trains an MLP without being told. Handed to the final
  review.
- **The run-env `env.step()` hang** remains owned by the concurrent
  source-fidelity audit, not by this project.

## Process notes worth keeping

**A green suite is not evidence, and this project proved it five times.** Every
one of these was invisible to the implementing lane's own passing tests and was
caught only by an independent pass:

1. wave 1 truncated a row block and *then* sorted it — a hidden-information
   leak whose own non-leak test passed because it only permuted rows that fit;
2. wave 1 shipped tests that were green alone and red under the full suite,
   because `__subclasses__()` also found a test double;
3. wave 2's non-leak test compared two identical **all-padding** blocks, because
   its 5-card deck drew every card into the opening hand;
4. wave 3b's overflow test and another file fought over a **once-per-process
   warning latch**, passing in one file order and failing in the other;
5. wave 3b's shuffle-invariance test had **no duplicate candidates at all** — on
   the rider that exists precisely because duplicates were being collapsed.

Two habits came out of that and are now standard here:

- **Mutation-check every invariant test.** Break the invariant at runtime in a
  throwaway script and confirm the test goes RED. It is cheap, and it is the only
  thing that distinguishes a guard from decoration. It caught (3) conclusively —
  and one lane then caught a flaw in *its own* mutation check, where the RED came
  from a missing warning rather than the byte mismatch it claimed to prove.
- **Never let process-global state decide a test's result.** `test/conftest.py`
  now clears the warning latch before every test, which retires the whole class
  rather than patching the third call site.

**Briefs were wrong repeatedly, and lanes reporting that was the most valuable
thing they did.** The potion belt grows by 7, not 1. Five powers beyond
`the_bomb` carry per-instance numbers. Deleting two names broke `import sts2_rl`
outright, not "a dozen test files". One brief contradicted itself on ownership
and a lane correctly refused to resolve it by violating the boundary. Every
dispatch asked for this explicitly, and every lane delivered it.
