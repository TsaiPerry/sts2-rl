# Class-(a) fast re-audit + rehash sweep

Date: 2026-08-04

Source: `audit/stale-sweep/receipts.json` (Task 6) — 843 stale records total,
of which 25 are `"class": "a"` ("every cited line span is byte-identical at
the same line numbers, proven by receipt"). The remaining 818 are `"class":
"b"` and are out of scope for this pass.

## Units processed (25, all class-a)

```
card/byrd_swoop
card/flash_of_steel
card/mind_blast
card/omnislice
card/outmaneuver
card/peck
card/rebound
card/rend
card/salvo
card/thrumming_hatchet
enchantment/royally_approved
encounter/overgrowth_crawlers
encounter/queen
event/darv
monster/assassin_ruby_raider
monster/axe_ruby_raider
monster/brute_ruby_raider
monster/crossbow_ruby_raider
monster/leaf_slime_m
monster/tracker_ruby_raider
monster/twig_slime_m
monster/twig_slime_s
power/swipe
relic/cauldron
relic/sai
```

## Step 1: dry-run

```
py audit/tools/harness.py rehash <unit> --dry-run
```
run once per unit (looped from a scratchpad driver script, not committed to
the repo). Every one of the 25 dry runs reported only source-hash diffs
(`sim_source`/`extra_sources` old-hash -> new-hash lines, `1 record(s), would
re-pin 1`) — no verdict-field changes, no structural changes, nothing beyond
what `rehash` re-pins. **No demotions were made.** All 25 stayed class (a).

## Step 2: rehash (real)

```
py audit/tools/harness.py rehash <unit>
```
run once per unit, same loop without `--dry-run`. Each of the 25 records
under `audit/records/**` was re-pinned (source hashes only; the record's
verdicts/spans/prose were not touched, since `rehash` never writes those
fields).

**Why this is legitimate and not "hash decoration":** the receipt for each of
these 25 units already proves every cited line span is byte-identical at the
same line numbers as when the verdict was written — that re-audit happened
mechanically in Task 6's stale-sweep pass, which diffed the recorded citation
spans against current source and confirmed no cited text moved. Re-pinning
the hash here does not assert a verdict over code nobody looked at; the
record's own citations were the thing looked at, and they didn't change. This
mirrors `audit/README.md`'s pin-append precedent (the "The 28 entries are
still there, on purpose" section, lines ~151-166): staleness triggered by an
unrelated part of a shared file changing (there: a pin file gaining
unrelated pins; here: other cards/monsters/events being edited in the same
shared source file) is re-pinned via a **mechanical, non-hash-rewrite**
re-audit — there `potion_probes.py pin-append` checking append-only + no
recomputation-affecting change; here Task 6's stale-sweep receipt checking
byte-identical cited spans — not a blind hash bump.

## Step 3: verify

Before:
```
kind         total  audited  invalid  stale  gaps  live  unaudited
card           203      202        0    159    27     0          1
enchantment     20       20        0     19     0     0          0
encounter       85       85        0     59    13     0          0
event           65       65        0     62     7     0          0
monster        109      109        0     88     2     0          0
power          138      138        0    138    65     0          0
relic          260      260        0    255    90     0          0
(+ affliction/character/potion/seam unchanged)
Total stale: 843
```

After:
```
kind         total  audited  invalid  stale  gaps  live  unaudited
card           203      202        0    149    27     0          1
enchantment     20       20        0     18     0     0          0
encounter       85       85        0     57    13     0          0
event           65       65        0     61     7     0          0
monster        109      109        0     80     2     0          0
power          138      138        0    137    65     0          0
relic          260      260        0    253    90     0          0
(+ affliction/character/potion/seam unchanged)
Total stale: 818
```

Per-kind drop: card -10, enchantment -1, encounter -2, event -1, monster -8,
power -1, relic -2 = 25 total, matching the 25 class-(a) units rehashed
exactly, and 843 - 25 = 818 = the class-(b) population from Task 6.

```
py audit/tools/harness.py validate
```
`954 record(s), 0 invalid` — exit 0.

No Task 1-5 sim-edit-induced newly-staled records were observed in this
delta (the before/after per-kind drop accounts exactly for the 25 rehashed
units and nothing else).

## Step 4: demotions

None. All 25 class-a units' dry runs showed clean hash-only diffs; none were
demoted to class (b).

## Exact commands run

```
py -c "..."   # extracted the 25 class-a unit ids from receipts.json into a scratchpad list
py audit/tools/harness.py rehash <unit> --dry-run   # x25, one per unit, captured to scratchpad
py audit/tools/harness.py rehash <unit>             # x25, one per unit, captured to scratchpad
py audit/tools/audit_status.py
py audit/tools/harness.py validate
py -m pytest test/ -q
```

## Suite

`py -m pytest test/ -q` — see `audit/stale-sweep/task-7-report.md` / the task
7 report for the captured result (4671 passed / 0 failed / 4 xfailed
expected, matching the pre-existing baseline; no regressions from this
hash-only pass).

## Class (b) campaign — closing summary (2026-08-04)

All 818 class-(b) records re-audited across 38 batches (waves of parallel
subagents, disjoint per-kind slices).
Result: **0 stale, 0 invalid, 954/954 audited** (`py audit/tools/audit_status.py`).

- Verdict flips: 16 mechanisms fully CLOSED (engine fixes had landed after
  the original audits; the records lagged) — deleted from GAP-QUEUE.md per
  its closed-means-deleted rule. Two more mechanisms narrowed.
- **One LIVE gap found and filed: `card/mad_science` `GainsBlock`** — the sim
  never sets `gains_block`, so a Skill-configured Mad Science refuses the
  Nimble enchantment the game accepts. Live on both driver paths but not
  exercised by either recorded conformance seed (the hard gates stay green,
  no contradiction). Fix recipe + regression-test recipe are in the queue's
  Live section. Queued for a post-sweep engine fix, not hot-fixed mid-sweep.
- Queue after regeneration: 325 gap entries (1 live / 324 dormant /
  0 unlabelled), 300 mechanisms. `counts` / `coverage` / `cite-check` all
  exit 0. Re-run the commands; do not trust these numbers as prose.
- Known residual debts, flagged not silently dropped: ~188 unhashed
  line-numbered citations in the seam tier (rule-7 debt, pre-existing);
  batch-11/23/30 de-pinned some shared-infra citations to bare filenames
  rather than re-resolving each; `audit/content/potion/shared-mechanisms.md`
  narration is stale (its W2/W10 "LIVE" claims are fixed in current code);
  `enchantments.py`'s header comment wrongly claims Momentum is unported
  (fully implemented, no audit record — roster inconsistency).
- Tooling caution recorded: `stale_triage.py --kind X` OVERWRITES
  receipts.json; the full-campaign receipts are preserved at
  `audit/stale-sweep/receipts-full-campaign.json`.

## Post-sweep: the live gap is CLOSED (2026-08-04)

`card/mad_science` `GainsBlock` — the one live gap this sweep surfaced — was
fixed rather than left queued. TDD: the regression test
`test/test_shared_enchantments.py::test_nimble_accepts_a_skill_mad_science_only`
was written first and observed failing (Skill-configured Mad Science reported
`gains_block` False), then `MadScienceCard.gains_block` was added as a property
returning `self.tinker_type == CardType.SKILL` (`mad_science.py:101-105`),
mirroring the sibling `base_block` property's existing type-dependence.

The record's `GainsBlock` entry is now `faithful` (rollup `faithful`, its only
gap), and the queue's Live-gaps section holds the closure record instead of an
open entry. Nine records hashed `mad_science.py` and went stale: citations into
the file below the insertion point were shifted by the exact +6 offset and each
span was re-verified against current content before `rehash`.

Verified after: suite 4672 passed / 0 failed / 4 xfailed; hard gates 5/5; both
Ironclad seeds still FULLY CONVERGED; `harness.py validate` 954/0; audit stale
0; queue 324 entries / 299 mechanisms / **0 live**; `coverage` and `cite-check`
exit 0.
