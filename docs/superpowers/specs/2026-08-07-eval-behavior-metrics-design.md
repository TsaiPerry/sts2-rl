# eval.py behavior metrics + return histogram + CSV export

**Date:** 2026-08-07
**Status:** approved, ready to implement

## Problem

`train_torch.py` logs two behavior metrics per training window — `energy_unspent`
(mean energy left at each real end-turn) and `card_take` (fraction of card-reward
screens the agent took a card on). `eval.py` reports none of them: a checkpoint
evaluation tells you how far the policy got, not *how it played*. There is also
no view of the episode-return distribution — only its mean, buried in the
training CSV.

The env side of both metrics already exists (previous session): `run_env`
tallies them per episode and emits `ep_end_turns` / `ep_energy_unspent` /
`ep_card_offers` / `ep_card_takes` in `info` at episode end. `evaluate_run`
ignores those keys, and throws away each step's reward. Both features are
therefore additive on the eval side — no env changes.

## Scope

Run-scale envs only (`STS2RunEnv`, `STS2CurriculumRunEnv`; `--env run|column`).
The combat envs never emit the `ep_*` keys, so wiring them there would add
permanently-empty columns.

Non-goals: `--compare` (`PairedRunDelta` carries none of this; threading it
through is a separate change), `--env full|simple`, xlsx output, plotting.

## Design

### 1. Data layer — `sts2_rl/evaluation.py`

`RunEvalReport` gains five per-episode tuples next to the existing
`floors`/`acts`/`victories`/…:

| field | type | source |
|---|---|---|
| `seeds` | `tuple[int, ...]` | the seed each episode ran on (CSV rows must be reproducible) |
| `returns` | `tuple[float, ...]` | sum of `env.step()` rewards over the episode — today discarded as `_reward` |
| `end_turns` | `tuple[int, ...]` | `info["ep_end_turns"]` |
| `energy_unspent` | `tuple[float, ...]` | `info["ep_energy_unspent"]` |
| `card_offers` | `tuple[int, ...]` | `info["ep_card_offers"]` |
| `card_takes` | `tuple[int, ...]` | `info["ep_card_takes"]` |

All default to `()`, and every `ep_*` read defaults to `0`, so an env that does
not emit them still evaluates cleanly.

New properties, defined to match the training-side aggregates exactly:

- `energy_unspent_per_turn` = `sum(energy_unspent) / sum(end_turns)` — pooled
  over episodes, **not** a mean of per-episode means, because episodes have
  wildly different turn counts and `train_torch` pools the same way.
- `card_take_rate` = `sum(card_takes) / sum(card_offers)`, pooled likewise.
- `mean_return` = `float(np.mean(returns))`.
- `return_histogram` → `dict[float, int]`, **exact-value tally** (each return
  rounded to 6dp to kill float noise), sorted ascending.

Both rates return `0.0` on a zero denominator, so no report row can print `nan`.

**No binning.** The configured reward range is 0–51, so an exact tally is
bounded at ~52 distinct values — binning would blur genuinely distinct discrete
returns for no gain.

`evaluate_run` accumulates `reward` per step and reads the `ep_*` keys off the
terminal `info` (already the only `info` it keeps).

### 2. Report + export — `eval.py`

- The run-scale table gains two columns, named to match the training console
  line: `e_unspent` and `take`.
- `--reward-hist` prints the return histogram below the deaths block as an ASCII
  bar chart, one row per distinct value. Off by default — it is a multi-line
  block and the default report stays as it is.
- `--csv PATH` writes **two** files, one per logical table, so each imports into
  its own Google Sheets tab. A trailing `.csv` on `PATH` is stripped first, so
  both `--csv out` and `--csv out.csv` yield `out.episodes.csv` /
  `out.hist.csv` rather than `out.csv.episodes.csv`:
  - `<stem>.episodes.csv` — one row per episode per policy row, baselines
    included: `policy,seed,floor,act,win,truncated,hp_left,decisions,ep_return,end_turns,energy_unspent,card_offers,card_takes`
  - `<stem>.hist.csv` — `policy,ep_return,count,freq`
  Written with stdlib `csv` (the `train_torch.py` precedent; no pandas/openpyxl
  in this repo). Plain unquoted numbers and a plain header row, so Google Sheets
  types the columns on import with no cleanup. The `hist` table is chart-ready
  as-is.
- `--csv` with `--compare`, or with `--env full|simple`, is a `parser.error`.

### 3. Tests — `test/test_behavior_metrics.py`

That file already owns this metric family. Extend it with a stub run-env whose
per-step rewards and `ep_*` values are known, asserting:

- `evaluate_run` accumulates per-episode returns and carries each `ep_*` tuple
  and the seeds;
- `energy_unspent_per_turn` / `card_take_rate` equal hand-computed **pooled**
  values (a stub with unequal per-episode turn counts, so a mean-of-means
  implementation fails the test);
- both rates are `0.0`, not `nan`, when the denominator is zero;
- `return_histogram` is an exact-value tally in ascending order;
- the two CSV writers produce the headers and rows above.

## Addendum: rest-site heal / upgrade share

Added after the above shipped, same shape, **eval-only** — `run_env` tallies and
`info` carries it, but deliberately NOT wired into `vec_env.EP_METRIC_KEYS` or
the `train_torch` CSV (vec_env reads a fixed key list and ignores the extra
`info` keys, so nothing breaks).

`run_env._count_behavior` gained a REST branch and `_info` three keys
(`ep_rest_visits` / `ep_rest_heals` / `ep_rest_upgrades`); `RunEvalReport`
gained the matching tuples, the `rest_heal_rate` / `rest_upgrade_rate` pooled
properties, and three episode-CSV columns; `eval.py` gained `rest_heal` /
`rest_up` columns.

Two things make this less trivial than the card metric:

- **A rest site is a decision loop, not a screen.** `RunDriver._rest_site`
  re-asks until Leave, and Miniature Tent lets one visit both heal and smith.
  Counting per decision would let one visit contribute two or three times, so
  the tally is per **visit**, keyed on `(act, floor)` — a rest site is one room
  on one floor and its decisions are consecutive, so the key changes exactly at
  a visit boundary. Answering heal twice in a visit still credits one healed
  visit.
- **The denominator is every visit**, including Leave-only ones (user's call).
  Consequence to keep in mind when reading the number: `REST_SMITH` is illegal
  when the deck has nothing upgradable, so a low `rest_up` can mean "couldn't"
  rather than "chose not to". The alternative — dividing by visits where the
  option was legal — was considered and rejected as extra machinery.
  `rest_heal + rest_up` can exceed 100% (one visit doing both).

## Verification

`py -m pytest test/ -q` — the suite must stay at its current pass count plus the
new tests, with no new failures beyond the 4 known pre-existing `test_train_io`
failures.
