# Continue: entity-obs-schema phase 1, wave 2

You are the **controller** of a subagent-driven project on `sts2-rl`
(`c:\Users\Perry\Desktop\sts2-rl`). Phase 0 and wave 1 of phase 1 are done and
staged. Pick up at **wave 2**.

## Read first, in this order

1. `prompts/entity-obs-schema.md` — the project brief. Note it has been
   revised several times; read the current text, not a summary of it.
2. `docs/superpowers/plans/2026-08-01-entity-obs-schema.md` — the progress
   ledger. **It is authoritative over anyone's recollection, including mine
   and including this file.** Every sizing constant traces to a measurement
   recorded there.
3. `OBS_SCHEMA.md` — the normative contract for the new observation.
4. `CLAUDE.md` §4 — **never `git commit` or `git push` unless the user
   explicitly asks. Stage only.**

## Ground rules

- Use the `py` launcher (no `python` on PATH); `PYTHONPATH=.` when running
  scripts directly from the repo root.
- **Never trust a count stated in prose, including in this file.** Re-measure.
- Suite baseline **4257 passed / 6 xfailed / 0 failed** with
  `--ignore=test/test_conformance_floor_state.py`. That file's 2 failures are
  a missing `933T39V18D/floor_49` fixture — an environment gap. **Never "fix"
  them, never count them as regressions.**
- **No old-vs-new comparison exists in this project, in any form.** Not
  checkpoint scores, not sps, not random-policy deltas. The riders change the
  action layout, the observation contents and the encodings simultaneously, so
  a delta attributes nothing — and it fails even policy-free, because a random
  policy over a different action space samples a different distribution.
  Validation is against engine ground truth. Do not re-introduce a before/after
  figure as a blocker, deliverable, or success criterion.

## State

**Phase 0 — DONE, staged.** `creature.powers` is `creatures.PowerList`, an
ordered instance list; `power_cmd/G5` closed.

**Wave 1 of phase 1 — DONE, staged.**

| lane | file | what it gives you |
|---|---|---|
| T1 | `sts2_rl/obs.py` | `PAD`/`oid()`, `ObsLayout`, `ObsBuffer.write_rows(...)` — truncation, canonical sort, `.ids`/`.f` naming |
| T2 | `sts2_rl/afflictions.py`, `sts2_rl/vocab.py`, `sts2_rl/enchantments.py` | affliction registry; frozen vocabs (afflictions 7/16, enchantments 19/32) |
| T3 | `sts2_rl/relic_obs.py` | `relic_row(relic, *, in_combat)` and `EXCLUDED_RELIC_STATE` |

Also landed: `env_baseline.py` (absolute sanity floors), and an engine bugfix —
`Enchantment.modify_card_play_count` had no base-class default, crashing 18 of
20 enchantments through Hidden Gem's filter.

## Decisions already made — do NOT re-litigate

- **The envs emit v4 only. There is no `obs_mode`.** The third `--arch` value
  exists so an old arch-stamped checkpoint is refused *on a name* rather than
  failing on a shape mismatch inside `load_state_dict`. Nothing needs to run
  the old observation.
- Therefore **delete the old flat builders outright**, and delete
  `test/test_obs_byte_identity.py` **with the reason written down** (it pins an
  encoding that will no longer exist). A test deleted silently because it went
  red is how a real regression gets laundered; a test deleted with a stated
  reason is fine.
- Observation contract: `spaces.Dict({"f": Box(float32), "i": Box(int32)})`.
  Stored id = vocab index + 1, `0` = PAD; tables get `capacity+1` rows with
  `padding_idx=0`. No separate mask array.
- **Overflow truncates, never asserts.** Panache/Automation/Rolling Boulder are
  unbounded in principle, so an assert turns a legal game state into a training
  crash. `sort=False` keeps the caller's prefix (C# application order);
  `sort=True` sorts *before* truncating (otherwise which rows survive leaks the
  input order — this was a real bug, see the ledger).
- Sizing (measured, see ledger): `MAX_POWERS_PLAYER` 32, `MAX_POWERS_ENEMY` 16,
  `MAX_RELIC_ROWS` 48, `MAX_COMBAT_CARDS` 96. `MAX_SELECT_CANDIDATES` unsized.

## Do this next

**Wave 2 — T4, `sts2_rl/full_env.py` (one lane, sole owner).** The v4 combat
observation per `OBS_SCHEMA.md` §5: integer rows for powers / hand / enemies /
potions, the single sorted card block covering draw+discard+exhaust, the new
relic block via `relic_obs.relic_row`, `OBS_SCHEMA_VERSION` 3 → 4. Delete the
flat builders.

**Wave 3 — T5, `sts2_rl/run_env.py`.** Must follow T4, not run beside it:
`run_env` imports `build_combat_obs`, `_write_pile_composition`, `_abs2`,
`_clip01` from `full_env`, so the files are disjoint but the API is not.
Includes R1's run-side relic block, **R4** (per-candidate rows + a
candidate-index action block), **R6** (`log1p` for gold and shop prices),
`RUN_OBS_SCHEMA_VERSION` 6 → 7.

**Wave 4 — T6**: `models.py`, `checkpoints.py`, `vec_env.py`, `train_torch.py`
— the third `--arch` name, the schema hard-fail with a `--fresh` message, and
the `TensorObs` pair type so the PPO loop text is nearly unchanged.

**Then**: observation-content assertions (decode the obs, assert against direct
`CombatState`/`RunState` reads — this is the real check), the
hidden-information non-leak test (pile order + `EXCLUDED_RELIC_STATE`),
rewrite the **14** obs-touching test files, and the phase-1 report with the new
stack's **absolute** figures.

## Subagent dispatch rules

Waves of 2–4 concurrent **sonnet** implementers with disjoint file footprints.
Forbid in every dispatch: `git commit`, `push`, `add`, `stash`, `checkout`,
`reset`, `restore`, and "temporarily revert the fix to see RED" (get RED by
writing the test first). Tell each lane to re-measure any count you give it and
report where you are wrong.

**Both wave-1 lanes shipped defects invisible to their own green suites** —
T1's non-leak test only permuted rows that fit, so truncate-then-sort passed;
T2 verified its file in isolation, so a `__subclasses__()` collision with a
test double only appeared under the full suite. **Re-run the whole suite
yourself after every lane.** A lane's green is not evidence.

## Open items

- **R3 (intent history) is deferred**, pending an explicit user decision. It
  needs `net_id` keying (enemy obs rows are raw list positions and three
  encounters reorder them mid-combat) plus a phase-epoch counter for ~9
  phase-changing monsters — materially more than the prompt assumed.
- **R3 and R4 censuses are HELD** on the user's instruction. `MAX_SELECT_CANDIDATES`
  cannot be sized until R4's runs.
- **`env_baseline.py sanity --env column` FAILS BY DESIGN** on R4's
  information-losing candidate collapse (measured: a `nimble`-enchanted Defend
  the agent cannot address, seed 75; a `spiral`-enchanted Strike it cannot
  choose to upgrade, seed 157). **This is R4's acceptance test — it must go
  green when R4 lands.**
- **The run-env `env.step()` hang is owned by the concurrent source-fidelity
  audit**, not by this project. Do not diagnose it, do not paper over it with
  timeout-and-truncate.
- Every empirical census is an **act-0 floor** — masked-random play never
  leaves act 0. `MAX_RELIC_ROWS` and `MAX_COMBAT_CARDS` rest on static
  arguments and want re-validating once a policy reaches act 2.
