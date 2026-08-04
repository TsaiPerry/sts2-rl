# Independent review — entity-obs-schema phases 2+3 — FINDINGS

Reviewer: independent (not involved in building this). Date 2026-08-02.
Everything below was run or read by me; no number is taken from a ledger.

---

## 0. The premise the brief is written on is wrong: the work is COMMITTED

The brief says the work is "STAGED on HEAD `2dc0445`". It is not.

```
$ git log --oneline -1
baba37b observation space changes
$ git log --oneline -2 | tail -1
2dc0445 env changes and more gaps fixed
$ git diff --cached --stat        # -> empty, nothing staged
$ git status --short
?? prompts/entity-obs-schema-phase23-REVIEW.md
```

The whole of phases 2+3 is **commit `baba37b`**, a child of `2dc0445`. The
working tree is clean. `2dc0445` does not exist as a reachable-by-name HEAD
any more; it is `HEAD~1`.

I therefore reviewed the diff `2dc0445..baba37b` (37 files, +7732/−94). I
mutated nothing: HEAD is still `baba37b` and `git status` is unchanged from
the state I found it in (the one untracked file is the review brief itself).

Two consequences you should decide on:

- The final verdict question ("safe to commit as-is?") is already answered by
  someone else. The live question is whether `baba37b` is safe to **keep** /
  push, which is what I answer at the end.
- Both progress ledgers and the project ledger still end with "**Staged,
  never committed**" and cite `HEAD` as `2dc0445` / `206c9bd`. Those lines are
  now false. The commit message style (`observation space changes`, lowercase,
  terse) matches your own adjacent commits, so I read this as you committing
  it yourself rather than a lane breaching the no-commit rule — but the
  ledgers were never updated to say so.

**One thing genuinely got swept in.** `baba37b` also contains six audit-record
files that have nothing to do with entity-obs-schema and appear in no phase-2
or phase-3 "files touched" list:

```
audit/records/monster/living_fog.json
audit/records/monster/waterfall_giant.json
audit/records/power/adaptable.json
audit/records/power/illusion.json
audit/records/power/steam_eruption.json
audit/records/seam/monster_state_machine.json
```

The edits are source re-hashes belonging to the concurrent source-fidelity
audit. I checked them: `py audit/tools/gap_queue.py cite-check` reports
`91 citations, 0 problems`, and `harness.validate_record` returns VALID on
five of the six. The sixth, `audit/records/power/adaptable.json`, returns
`["unit verdict 'faithful' != rollup 'waiver'"]` — an internal inconsistency
that is now committed. It is the other audit's to settle, not this project's,
but it rode in on this commit.

---

## 1. Suite — **CONFIRMED**

```
$ py -m pytest test -q --ignore=test/test_conformance_floor_state.py
4521 passed, 6 xfailed, 2 warnings in 275.18s (0:04:35)      # exit 0
```

Exactly the claimed 4521 / 6 / 0. The two warnings are the pre-existing
`select.candidates` cap-truncation `UserWarning`s from the obs-schema backlog,
raised deliberately by two tests that assert the truncation behaviour.

Ledger arithmetic reconciles: wave-4 gate 4518 + 3 tests from the final
review's I1 potion-belt fix (`test_potion_slots_kwarg_five_slot_belt_survives_rebuild`,
`test_potion_slots_five_slot_belt_shows_up_in_potions_obs_rows`,
`test_snapshot_five_slot_potion_belt_survives_rebuild`) = 4521.

## 2. Schema freeze — **CONFIRMED**

Measured live against the real envs, not read off a constant:

```
combat schema 6  f (1677,)  i (606,)  n_actions 79   bytes 9132
STS2RunEnv        schema 9  f (4710,) i (1464,) n_actions 243  bytes 24696
STS2CurriculumRunEnv schema 9  f (4710,) i (1464,) n_actions 243  bytes 24696
ENTSET_HEAD_VERSION 4
observation_space Dict
```

Every figure matches the phase-1 close table exactly. Corroborating
structural evidence: `OBS_SCHEMA.md` is **absent** from the `baba37b` diff
entirely, which is what a genuine zero-layout-change phase looks like.
`full_env.py` and `run_env.py` do appear, but their diffs are R11 start-state
kwargs and the `on_combat_start` seam, not obs writes.

## 3. Tied head equivariance — **CONFIRMED** (tests are not tautological)

I did not trust the in-repo tests to prove themselves, so I rebuilt the
hand-swap scenario in a scratch harness and attacked it three ways.

**(a) The swap is observable.** At random init the two hand slots' play
logits differ by `2.8e-3` max — an order of magnitude above the test's
`5e-4` atol, so the assertion is comparing genuinely different quantities,
not two copies of the same number.

**(b) The head really reads its own row.** Perturbing one hand row's floats
by +0.25 moves that row's six play logits by `1.9e-3` and every other row's
by only `3e-4` (the documented `ctx` coupling). A head ignoring `src` rows
would show 0 for both.

**(c) A positional mutant is caught.** Wrapping `play_head` in an
instance-level shim that adds a per-`(src,tgt)` positional bias breaks the
property at every scale I tried:

```
positional-bias scale 0.1    residual 6.00e-01 -> test FAILS
positional-bias scale 0.01   residual 5.99e-02 -> test FAILS
positional-bias scale 0.001  residual 5.91e-03 -> test FAILS
positional-bias scale 0.0001 residual 5.14e-04 -> test FAILS
```

The property can fail, and does, on exactly the defect class it exists to
catch. `test_positional_baseline_fails_equivariance` is a real sanity check
(it asserts a ctx-only `Linear` does *not* satisfy the property).

**But the ledger's margin claim does not reproduce** — see Minor M-1.

## 4. R11 end-to-end — **CONFIRMED**

`runs/snapshots/random-v1.jsonl` is present and untracked (1.86 MB).

```
loaded: 1237
build_start_state failures: 0
distinct encounters: 37
acts: {0: 1237}
floor range: 1 - 12
belt slot widths: {3: 1184, 4: 50, 5: 3}
snapshots with >3 belt slots: 53
snapshots with a potion in slot 3+: 0
```

All 1237 load and all 1237 rebuild — including the `dense_vegetation_event`
encounter whose absence was the R12 smoke defect. The 53 / 0 belt figures
reproduce the final review's I1 numbers to the unit.

Training smoke, exactly the brief's command line:

```
$ py train_torch.py --env combat --start-snapshots runs/snapshots/random-v1.jsonl \
    --timesteps 2048 --n-steps 64 --n-envs 8 --seed 1 --fresh --save runs/review-smoke.pt
8 envs x 64 steps (batch 512) across the in-process serial path
iter 3  step 2048  sps 202  ep_ret 0.852  win 0.76 ...
Saved to runs/review-smoke.pt
```

Clean. **Note the brief's own expectation is slightly off**: at `--n-envs 8`
the auto default resolves to *serial* (`AUTO_WORKER_MIN_ENVS = 16`), so that
command does **not** exercise the worker path. Since worker-crossing is
exactly where the registry defect hid last time, I ran the real thing:

```
$ py train_torch.py --env combat --start-snapshots runs/snapshots/random-v1.jsonl \
    --timesteps 2048 --n-steps 32 --n-envs 16 --seed 3 --fresh --save <scratch>
16 envs x 32 steps (batch 512) across 4 worker processes
iter 3  step 2048  sps 268  ep_ret 0.946  win 0.79 ...
```

Datasets cross the `spawn` boundary as paths and load per-process. Clean.

**Honest limitations — documented, and pinned, not hidden:**

| limitation | where documented | pinned by |
|---|---|---|
| relic flag-state loss (~22 flag-only relics) | `snapshots.py:39-47` (deviation #3), verbatim | `test_snapshots.py:294` `test_obs_level_fidelity_round_trip_pins_flag_relic_loss` — uses `lizard_tail` latched, asserts the flag column differs and *tells the next person to flip the test* if they close the gap |
| dataset is all act-0 | phase-3 ledger + `harvest.py` docstring | measured above: `acts: {0: 1237}` |
| belt slots 3+ visible but unactionable | `full_env.py:1225-1230`, inline | `test_full_env_startstate.py:205,222,437` |

The flag-loss test is a genuine loss-demonstrating test, not a comment. That
is the strongest form of this and I am satisfied it is not hidden. One gap in
*reach*, though — see Minor M-5.

## 5. R12 numbers — **CONFIRMED** (direction and magnitude)

Spot-checked the combat pair on a quiet machine, same config as the ledger
(cuda, entset, 32 envs, n_steps 128, 32768 ts, seed 1):

| arm | my sps | ledger sps |
|---|---|---|
| `--n-workers 0` | **649** | 522 |
| `--n-workers 4` | **1001** | 818 |
| speedup | **+54%** | +57% |

Absolute numbers run higher on my pass (quieter machine), the **ratio
reproduces**. Direction and rough magnitude confirmed.

**Stronger corroboration than asked for**: every training metric is
*identical*, iteration by iteration, across the two worker arms —
`ep_ret 0.954 / win 0.93 / ep_len 18.1 / pg -0.010 / v 0.039 / ent 1.068 /
kl 0.0027 / clipfrac 0.034` at iter 7 in both. That independently confirms
the "worker arms bit-equivalent in training behavior" claim, which is the
claim that actually matters for flipping the default. And the seed-1 final
win of **0.93** matches the R13 A/B table's off-arm seed-1 entry exactly.

`--n-workers` auto default verified in code (`vec_env.py:365-369`) and by
observation: 8 envs → "the in-process serial path", 16 envs → "4 worker
processes", 32 envs → 4 workers. `AUTO_N_WORKERS = 4`,
`AUTO_WORKER_MIN_ENVS = 16`, and `min(requested, n_envs)` caps workers at the
env count. Tests at `test_vec_env.py:70-85` cover both sides of the threshold.

## 6. R13 really deleted — **CONFIRMED**

```
$ git grep -n -iE "aux_win|aux-win|auxwin" -- .        # 11 hits
$ git grep -n -iE "win_head|win_label|win_logit|win_coef" -- .   # 4 hits
```

**Zero code hits.** All 15 are in `docs/superpowers/plans/2026-08-02-entity-obs-schema-phase3.md`
— the plan document, which is supposed to retain them. `models.py`,
`checkpoints.py`, `train_torch.py` and the test files are clean: no orphaned
head, no dangling `--aux-win` argparse entry, no unused import.

## 7. Harvest safety contract — **CONFIRMED**

Read the loop (`harvest.py:186-206`). The structure is:

```python
faulthandler.dump_traceback_later(watchdog_secs, file=watchdog_fh, exit=True)
try:
    obs, _reward, terminated, truncated, info = env.step(action)
finally:
    faulthandler.cancel_dump_traceback_later()
```

There is **no `except` anywhere in the file**. The only `try` around
`env.step` carries a `finally` that cancels the timer — nothing catches, so a
watchdog trip reaches `os._exit(1)` and the process dies mid-episode.
`exit=True` is passed explicitly (the default is `exit=False`, which would
dump and keep running) and the docstring at `:43-47` explains exactly that.
Re-armed per step, not per episode. No timeout-and-continue path exists.

Live 3-episode harvest:

```
$ py harvest.py --episodes 3 --seed 4242 --out <scratch>.jsonl --log <scratch>.log
episodes played: 3
snapshots written: 7
combats entered: 7
act histogram: act 0: 3
```

Appends are `flush()` + `os.fsync()` per snapshot, so a hard abort loses
nothing already harvested.

## 8. Eval rider — **SPLIT: `compare_runs` CONFIRMED, the probes REFUTED as a measure**

**`evaluation.compare_runs` — CONFIRMED.** Same policy factory on both arms,
30 seeds of `EVAL_SEEDS` on the curriculum env:

```
floor_deltas all zero: True
hp_deltas    all zero: True
win_delta: 0   better/worse/tie: 0 0 30
floors_a == floors_b: True     wins_a == wins_b: True
```

And the check is discriminating — a genuinely different policy gives
`21/30` non-zero floor deltas, `better/worse/tie = 4/17/9`. So the all-zero
result is a property of the harness, not of a comparison that can't move.

**The three run probes — the deferred minor M1 is real, and I think it is
understated.** Measured directly:

| policy | probe results | accuracy |
|---|---|---|
| `argmin(legal)` — always the lowest legal index | `[1, 1, 1]` | **1.00** |
| `argmax(legal)` — always the highest | `[0, 0, 0]` | 0.00 |
| uniform random over legal (seed 0) | `[0, 1, 1]` | 0.67 |
| uniform random over legal (seed 7) | `[0, 0, 0]` | 0.00 |

And the reason, measured per probe by replaying each legal action in
isolation from a fresh build:

```
rest_at_low_hp         legal=[121,122,123]      winner=121  (rank 0 of legal)
card_reward_on_curve   legal=[121,122,123,124]  winner=121  (rank 0 of legal)
shop_removal_dominant  legal=[134,135]          (two-action purchase; 134 first)
```

In all three probes the correct answer is the **lowest-index legal action**.
`run_probe_accuracy` is therefore, on the current fixtures, an exact
synonym for "does this policy have a low-index bias" — it carries no
information about whether the policy understood the decision. The oracle 1.0 /
anti-oracle 0.0 gate does not detect this, because the anti-oracle is
constructed to pick the *worst* option (highest index here), so it agrees with
the degenerate policy's failure mode by coincidence.

That does not make the module wrong — the scenarios are well built, the
`_removal_bought` mid-purchase fix is correct and necessary, and
`_drive_forced_map_hop` asserting rather than assuming the hop is forced is
good practice. It makes the *metric* non-load-bearing. Ranked as Important
below, because the module docstring's stated purpose ("proves a policy makes
the single obviously correct choice") is not currently met and a reader
seeing `1.00` will read it as competence.

## 9. Refusal ladder — **CONFIRMED**, order verified end-to-end

Code order in `check_checkpoint` (`checkpoints.py:239-317`): env_kind (240)
→ obs_schema (251) → arch (264) → head_version (284) → shared_encoder (304)
→ shape (315). I did not rely on reading it. I built a valid payload, broke
one field at a time, and re-ran each case with a deliberately bad `hidden`
tuple as well:

```
baseline accepted: OK
env_kind                  -> shape-error=False  :: checkpoint was trained on the 'combat_other' env...
env_kind        +badshape -> shape-error=False
obs_schema                -> shape-error=False  :: checkpoint obs schema 3 != current 6...
obs_schema      +badshape -> shape-error=False
arch                      -> shape-error=False  :: checkpoint arch 'entity' != this run's --arch 'entset'...
arch            +badshape -> shape-error=False
head_version              -> shape-error=False  :: checkpoint head_version 3 != current 4...
head_version    +badshape -> shape-error=False
shared_encoder            -> shape-error=False  :: checkpoint shared_encoder=True != this run's...
shared_encoder  +badshape -> shape-error=False
shape only                -> shape-error=True   :: checkpoint architecture (...) != this run's ...
```

All five mismatches produce their own honest, distinct message, and every one
of them beats a simultaneously-wrong shape. Test coverage is real and split
across two files: `test_models.py:540-591` (head_version, incl. a
doubly-wrong test) and `:742-797` (shared_encoder, same pattern),
`test_models.py:244` (arch), `test_eval_torch.py:223,234` (env_kind, schema).
`test_check_checkpoint_accepts_current_head_version` correctly hardcodes the
literal `4` rather than reading the live constant — the tautology trap the
lane self-caught is genuinely avoided.

---

# Defects

### Critical

**None.** I found nothing that produces wrong training, wrong observations,
a silently-accepted bad checkpoint, or corrupt data.

### Important

**I-1 — `RL_ARCHITECTURE.md` documents the wrong head version and the wrong
refusal predicate.** Named in the brief as one of the two contracts the code
claims to honor.

- [RL_ARCHITECTURE.md:108](RL_ARCHITECTURE.md#L108) — "**Tied action head
  (phase 2, `ENTSET_HEAD_VERSION = 2`).**" The live value is **4**
  ([models.py:747](sts2_rl/models.py#L747)). The document contradicts itself:
  the bullets immediately below at :116-134 describe the R9 pair features and
  the R8 pointer heads — i.e. the changes that bumped it to 3 and then 4.
- [RL_ARCHITECTURE.md:188-189](RL_ARCHITECTURE.md#L188-L189) — "an entset
  checkpoint predating the phase-2 tied head (**stored version < 2**, missing
  key = 1) is refused". The code refuses on `!=`
  ([checkpoints.py:284](sts2_rl/checkpoints.py#L284)), not `<`, and against 4,
  not 2. A reader implementing against this doc builds a guard that accepts
  every head_version ≥ 2, i.e. exactly the stale checkpoints the gate exists
  to reject.

Both are stale-by-omission from the R8/R9 riders, which bumped the constant
twice and updated the prose in neither place.

**I-2 — `vec_env.py`'s module docstring still tells the reader workers are off
by default, and cites the number the ledger declared obsolete.**
[sts2_rl/vec_env.py:7-10](sts2_rl/vec_env.py#L7-L10):

> **It is off by default, and usually should be** — see `resolve_n_workers`
> for the numbers. Env stepping is a small slice of an iteration, so
> parallelizing it moves the needle ~4%. The machinery is here because the
> profile will shift, not because it currently pays.

Every clause is now false: workers are ON by default at 16+ envs, the measured
win is +54%/+57% not ~4%, and the profile already shifted. This is the *same
file* whose `resolve_n_workers` docstring at :354-363 carries the corrected
2026-08-02 numbers — so the file contradicts itself, with the wrong version
at the top where a reader lands first. The phase-3 ledger's claim that "the
stale docstring math was replaced with these numbers" is **half true**: the
function docstring was fixed, the module docstring was missed.
(`RL_ARCHITECTURE.md:160-164` *did* get this right, which makes the miss
narrower but no less wrong.)

**I-3 — the run probes cannot distinguish a competent policy from
`argmin(legal)`.** Evidence and reasoning in claim 8 above. Disclosed as
deferred minor M1 in the phase-3 ledger, and it is true that nothing gates on
the probes today, which is why this is Important rather than Critical. But
`run_probes.py:1-6` states the module's purpose as proving a policy "makes the
single obviously correct choice", and on the current fixtures it proves no
such thing. The cheap fix is to permute the correct option off index 0 in
`_build_card_reward` / `_build_rest_low_hp` and add a first-legal-action
policy to the anti-oracle side of the gate, so the gate itself catches the
degeneracy instead of a reader having to know about it.

### Minor

**M-1 — the equivariance atol margin is ~2.6×, not the ledger's ">20×", and
the test is unseeded.** `test_hand_swap_equivariance` never calls
`torch.manual_seed`, so its residual depends on whatever RNG state pytest
leaves behind. Measured across 40 inits, taking the worst of every assertion
the test actually makes:

```
residual over 40 inits: min 4.68e-05  median 1.12e-04  max 1.92e-04   atol 5e-4
inits exceeding atol: 0/40
margin at worst init: 2.6x
```

Nothing fails, and 2.6× is a real margin — but the phase-2 ledger's "reviewer
independently measured residual ~2e-5 (>20× margin)" is a single-init
measurement presented as a property. My median is 5.6× that figure. Not a
correctness problem; a claim that should be restated, and a candidate for
seeding the test so the margin stops being a lottery.

**M-2 — `harvest.py` silently rewrites an illegal policy action, with no
counter and no warning.**
[harvest.py:189-190](harvest.py#L189-L190):

```python
if not mask[action]:
    action = int(np.flatnonzero(mask)[0])
```

Disclosed as deferred minor M2. Harmless for the masked-random default (which
cannot emit an illegal action) and for a correctly-masked torch policy. The
risk is the `--checkpoint` path: a policy that *systematically* emitted
illegal actions would produce a first-legal-biased dataset that looks
completely normal in the summary output. A counter in the returned summary
dict would cost one line and make the failure visible.

**M-3 — `CardSnap.rebuild` maps `affliction_amount == 0` to 1.**
[snapshots.py:147](sts2_rl/snapshots.py#L147) — `self.affliction_amount or 1`.
Disclosed as M3 and called unreachable. I did not confirm unreachability:
[powers.py:3089](sts2_rl/powers.py#L3089) assigns `card.affliction.amount =
self.amount` from a power's amount, so a 0-amount power would produce it. The
current dataset contains no afflicted cards at all (act-0 only), so nothing is
affected today. `if self.affliction_amount is not None else 1` removes the
question entirely.

**M-4 — `Snapshot.act` is captured and serialized but never read by
`build_start_state`.** Confirmed at
[snapshots.py:358-376](sts2_rl/snapshots.py#L358-L376) — the returned kwargs
dict has no `act` key. Disclosed as M4; the encounter id does imply the act,
so this is dead weight rather than a bug. Worth a one-line comment saying so,
since a future reader will otherwise assume it is load-bearing.

**M-5 — the three R11 limitations are documented in module docstrings and
pinned by tests, but do not surface in `RL_ARCHITECTURE.md`'s R11 section.**
[RL_ARCHITECTURE.md:60-75](RL_ARCHITECTURE.md#L60-L75) describes the snapshot
plumbing accurately and does not mention relic flag-state loss, the all-act-0
distribution, or unactionable belt slots 3+. Someone reading the architecture
doc to decide whether to train on `--start-snapshots` gets no signal that the
dataset is act-0-only — which is the limitation most likely to mislead, since
the whole point of R11 is a *mid-run* distribution. One sentence with a
pointer to `snapshots.py` would close it.

**M-6 — `checkpoints.py`'s own summary line under-lists the ladder.**
[RL_ARCHITECTURE.md:204-206](RL_ARCHITECTURE.md#L204-L206) — "`check_checkpoint`
— refuses a mismatched env kind, schema, arch or shape". Omits `head_version`
and `shared_encoder`, both of which it now refuses. (Line :186-190 does cover
head_version, so this is redundancy drift rather than a contradiction.)

**M-7 — six unrelated audit records rode in on `baba37b`.** Listed in §0.
Five validate clean; `audit/records/power/adaptable.json` reports
`unit verdict 'faithful' != rollup 'waiver'`. Provenance hygiene: the commit
message says "observation space changes" and the commit contains someone
else's in-flight audit edits.

### Out of scope, noted because I tripped over it

`OBS_SCHEMA.md` records the run-schema bumps 7→8 and 8→9 in its correction
blocks (:415, :429) but never records the **combat** `OBS_SCHEMA_VERSION`
5 → 6 bump that R3's `intent_history` caused on the combat side — the last
combat correction it carries is 4 → 5 at :25. The live value is 6. That is a
**phase-1 R3** gap, not phases 2-3 (which touch neither the schema nor that
document), but the doc calls itself "the normative description" and is
currently one version behind on the combat half.

I also confirmed, using the repo's own tooling rather than a raw file hash,
that the broad audit-record staleness (`rehash_record` would move
`cmds.py` / `powers.py` / `hooks.py` / `combat.py` hashes in every record I
sampled) is the pre-existing repo-wide condition already recorded as phase 0
handoff #4 — **not** something these six records uniquely suffer, and not
caused by this work. I checked specifically so I would not report it as a
finding: my first raw-`sha256` comparison looked like a mismatch and was
wrong, because it did not use `harness`'s own hashing path.

---

# Verdict

**The work is sound. Nothing here blocks keeping `baba37b`.**

Every load-bearing claim I could test held up, and several held up under
adversarial testing rather than merely reproducing: the equivariance property
survives four scales of positional mutation, the refusal ladder beats a bad
shape at all five levels, the worker arms are metric-for-metric identical, all
1237 snapshots rebuild including the one that broke last time, and the
snapshot dataset crosses a real `spawn` worker boundary and trains. The suite
is 4521/6/0 on my own run. The one genuinely lossy design decision — relic
flag state — is pinned by a test that *demonstrates the loss* and instructs
the next person to flip it, which is the honest form of that.

**Nothing must change before commit — it is already committed — but three
things should be fixed before this tree is treated as a reference:**

1. **I-1** — `RL_ARCHITECTURE.md:108` and `:188-189`. A wrong version constant
   and a wrong refusal predicate in the document the project nominates as its
   model-side contract. Cheapest of the three, highest cost if trusted.
2. **I-2** — `vec_env.py:7-10`. A module docstring that tells the reader the
   opposite of what the module does, in the file that does it.
3. **I-3** — the run probes. Either fix the fixtures (move the right answer off
   index 0, add a first-legal policy to the anti-oracle gate) or downgrade the
   module's docstring so `run_probe_accuracy` is not read as evidence of
   decision quality. Do this before anything ever gates on the number.

Then either update the three ledgers' "Staged, never committed" endings to
match reality, or accept that they are historical records of a state that no
longer exists — but do not leave a future reader to discover, as I did, that
`2dc0445` is `HEAD~1`.

The four deferred minors M1-M4 were each checked. **M2, M3 and M4 are
genuinely minor and correctly triaged.** **M1 is not** — it is the
substance of I-3 above, and calling it minor is the one triage call in this
project I would overturn.

---

*Everything above was produced by running the code. Git was read-only
throughout: HEAD is `baba37b`, the working tree is clean, and the only file I
created in the repo is this one (unstaged, as instructed). Scratch scripts,
the two `.pt` files from the R12 spot-check and the 3-episode harvest output
live in the session scratchpad; `runs/review-smoke.pt` from the claim-4 smoke
was removed.*
