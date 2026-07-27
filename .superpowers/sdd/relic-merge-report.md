# Merging the relic tier — report

Branch `audit-pipeline`, 2026-07-26. Six commits, nothing pushed, `main`
untouched. `sts2_rl/` untouched: `git diff --name-only main...audit-pipeline |
grep "^sts2_rl/"` prints nothing.

```
dbca9d2f  Merge branch 'audit-relic' into audit-pipeline
b5979b72  audit(relic): repath the relic tier onto the audit/ restructure
17d08406  audit(relic): backfill extra_sources over the 258 relic records
1f7be970  audit(relic): fix pass over the review findings
29f1e631  audit: UnmovablePower x Entrench -- a LIVE gap both records missed
c67ea23c  audit: widen the gap queue and README to the relic tier
```

---

## 1. Merge resolution

One merge, as expected — every batch branch `b04`…`b18` was already contained
in `audit-relic`.

**Conflict type 1 (the 258 records) behaved as the prompt predicted.** They
conflicted only as `CONFLICT (file location)`; git's rename detection had
already relocated them to `audit/records/relic/`, and it did the same for the 17
probes (`tools/audit/` → `audit/tools/`), which the prompt expected to need a
manual `git mv`. Accepted with `git add`. Verified: 258 records, no stray
top-level `audits/` or `tools/audit/`.

**Conflict type 2 did not happen, and that was the more dangerous outcome.**
The four seam records **auto-merged with no conflict at all** — git's three-way
merge found no textual overlap between the relic stream's 15 changed lines and
the six review passes `audit-pipeline` had run over the same files. A clean
auto-merge here is worse than a conflict, because it applies pre-review edits
silently and nothing asks you to look.

So I verified all **15 cross-references by hand** against the current tree
rather than trusting them. **All 15 ported, all 15 correct:**

| # | what | verdict |
|---|---|---|
| 10 | line-range corrections — `fiddle` 26-31→26-29, `evil_eye` 37-42→37-41, `true_grit` 48-55→48-54, `spiked_gauntlets` 26-32→26-31 (×6), `orichalcum` 22-26→22-25 | every range re-read in the working tree; all correct, and the old ones over-ran their files |
| 1 | `hook_dispatch` ShouldDie guard, `waiver` → `gap` | **re-verified.** FairyInABottle *is* ported — `sts2_rl/potions.py:1242`, real `should_die` — so the waiver's "LizardTail is the only listener" rationale was false |
| 1 | `turn_structure` Whispering Earring, dormant → **ALSO LIVE** | **re-verified.** `relics/crossbow.py:21-31` does fire `on_player_turn_started` and add a card to hand |
| 3 | wording / census edits | carried |

All four seam rollups were already `gap`, so nothing broke. `harness.py validate`
reports 0 invalid.

`audit/tools/PROMPT.md`: `audit-pipeline` had v1, `audit-relic` owns the file and
had v6. The merge took v6's hardening while keeping this branch's two repathed
command lines — verified byte-for-byte against `audit-relic`'s v6 modulo those
two lines.

---

## 2. Repath counts

| item | count |
|---|---|
| batch prompts `git mv`'d to `audit/prompts/relic-batches/` | **16** (README + batches 04–18; the prompt said 19) |
| path references rewritten | **1687** across **295 files** |
| — `tools/audit/` → `audit/tools/` | 954 |
| — `audits/<kind>` → `audit/records/<kind>` | 723 |
| — `tools.audit.` → `audit.tools.` imports | 8 |
| — glob / bare forms | 2 |
| probes exiting 0 after the import fix | **16 of 16** |

By group: 1092 in relic records, 356 in batch prompts, 124 in the sdd reports,
111 in the probes, 4 in the seam records. Every touched JSON was parsed **before
and after** the rewrite, and line endings were preserved (read and write with
`newline=""`) so a CRLF checkout did not churn into a whole-file diff.

**One real bug, not just a repath.** `citation_check.py`'s bare-basename
fallback searched `_REPO/"tools"` — where the probes used to live. The move alone
turned **26 correct relic citations into MISSING** (baseline on the relic
worktree: 0). Fixed by adding `audit/tools` to its search roots, keeping `tools`.
Relic MISSING back to 0.

**New information the merge surfaced elsewhere.** `citation_check.py` arrived
with the relic stream and had never been run over the other four tiers. Its
remaining findings are **6 MISSING, 58 OUT-OF-RANGE, 2 AMBIGUOUS — all in
`card`/`event`/`power`/`enchantment`/`seam`, zero in relic.** Two are events
citing *relic* files with stale line numbers (`fragrant_mushroom.py:42` in a
40-line file, `distinguished_cape.py:26` in a 25-line file) — the same drift the
relic stream fixed in the seam records. Reported, not fixed: not this stream's
records.

---

## 3. Source-hash backfill

```
2296 citations found, 2293 resolved, 536 already covered by the singular pair,
1746 extra_sources entries added across all 258 records.  Idempotent.
```

**The staleness proof, run rather than asserted.** On a scratch copy (`audit/` +
`sts2_rl/` only, so the real `sts2_rl/` was never touched), edit `cmds.py` +
`relics/base.py` + `combat.py` and ask `audit_status.py`:

| | relic records reported stale |
|---|---|
| **before** the backfill | **0 of 258** |
| **after** the backfill | **212 of 258** |

Zero before. The tier was resting on three engine files it could not notice
changing. (The scratch run added 1740 entries rather than 1746 because the copy
omitted `test/`, so six records' `test/test_hook_order.py` citation could not
resolve there; that file was not one of the three edited, so the proof stands.)

**3 unresolvable, where prior tiers hit 0.** None is a typo or a stale path —
all three are bare basenames the resolver cannot disambiguate:

- `relic/lost_wisp` cites `lost_wisp.py` — **benign.** `sts2_rl/events/lost_wisp.py`
  also exists, but the record's own `sim_source` already pins the relic file.
- `relic/fake_happy_flower` cites `base.py:20-24` — **real hole.** It means
  `sts2_rl/relics/base.py` (verified: that is the docstring about Happy Flower's
  carry-over turn counter) and nothing else in the record pinned it.
- `relic/vajra` cites `fuzzy_wurm_crawler.py:36-40` — **real hole.**
  `sts2_rl/monsters/overgrowth/…` and `sts2_rl/monsters/…` both exist.

Plus **6 MISPATHED** citations resolving only by basename, each missing its
`src/Core/Models` prefix. All handed to the fix pass; **after it, unresolvable is
0 and MISPATHED is 0.**

---

## 4. Review — defect rate per verdict class

Four independent read-only reviewers, one per class. Each stated its own
sampling method and sizes; the tree was verified unmodified after each.

| class | population | sampled | defects | rate |
|---|---|---|---|---|
| `waiver` | 397 entries | 100 (25%); 4 of 6 buckets **exhaustive** | 5 | **5.0%** |
| LIVE gap claims | 289 entries | 22 executed + obtainability swept over **all 145** records | 0 | **0%** |
| `faithful` on unexecuted unreachability | 203 entries | 14 (10 executed) | 0 | **0%** |
| `deliberate-divergence` | 77 entries | all 77 read, **41 verified** | 10–11 | **24% of verified / 13% of class** |
| rule-3 mechanisms | 27 censused | 12 fully resolved | 5 | **42%**, 2 "neither side right" |
| delegation integrity | 278 references | all | 0 dangling | 0% |

**Two results matter more than the raw rates.**

*The `waiver` class came out better than this project's history predicted.* The
historical failure mode — a false "no ported caller" grep — **did not recur once
in 21/21 re-runs**. All five defects are a single cluster (the potion clause),
enumerable by grep rather than by sampling, so the naive 5% × 397 ≈ 20
extrapolation is wrong: outside that cluster the sampled rate is **0/95**.

*A defect class nobody had named turned up, and it is 2 for 2.* Entries where an
auditor hit a question it could not settle from its own hashed sources and
**filed the uncertainty as a `gap`**. Both (`arcane_scroll`, `beautiful_bracelet`)
were the only non-faithful entry in their record, so both wrongly flipped a whole
record's rollup — and in both cases **a later batch had already published the
executed answer** and nobody went back. The class is mechanically enumerable by
the same regex that found it, so it is cheap to keep at zero. `PROMPT.md` v6
already warns about the *sweep* version of this ("prefer reporting INCONCLUSIVE
over reporting agreement") without extending it to per-unit verdicts.

---

## 5. What the fix pass changed

43 records edited, scope held (`audit/records/relic/**` only). Verdicts:
`faithful` 1230→1243, `waiver` 397→383, `deliberate-divergence` 77→63, `gap`
604→620. **Seven rollups flipped.** The `live` column moved **0 → 12**: the first
records in the project to state liveness as data rather than prose.

- **Auto-keep cluster → `gap`** (10 entries, 8 records). `WithSkippingDisallowed`
  appears on exactly two lines in the whole C# source, so only `neows_bones` is
  genuinely non-declinable. A decline is written into run history and read back
  by `conformance/runner.py`, which already carries a bespoke workaround
  (`_reconcile_node_relics`) for this exact divergence — a divergence needing a
  replay-time patch is not an identical observable. Also a rule-3 break against
  `event/EV-4` (`gap` at 8 sites). `gambling_chip` graded **A**: the driver never
  issues a decision request for it at all.
- **`arcane_scroll` and `beautiful_bracelet` → `faithful`.** `run.add_card` does
  append; Swift declares no `can_enchant` (the record quoted *Spiral's*
  predicate — 168/203 cards eligible vs the quoted `['defend','strike']`).
- **Potion cluster → `gap`/`faithful`** (4 entries) — see the open question below.
- **`pear` → `gap`** (all five max-HP relics leak +5 HP on undo, executed),
  `fake_strike_dummy` → `gap`, `war_hammer` → `gap`, the `frozen_egg`
  `NoHookUpgrades` dormancy trigger (3 readers, **0 producers** in the source),
  the `IsVisibleInternal` vocabulary, and 9 rationale/citation corrections.

**The fixer pushed back on three review items and was right each time**, which is
the healthiest signal in this whole pass:

- `winged_boots` `IsAllowed` stays `waiver` — `Players.Count == 1` is a
  *multiplayer* gate, the canonical waiver under rule 1. Unlike
  `IsVisibleInternal` (zero overrides anywhere), a player count really can vary.
  Flipping it would have contradicted every multiplayer waiver in the tier.
- `hefty_tablet` G3 goes **further** than asked — with the false premise removed
  there is no divergence at all, so `faithful`, not "verdict survives".
- `strike_dummy`'s dormancy reason was backwards in the review.

### The new gap the fix pass found on its own

**AUTO-KEEP-REVERSE** — the sim offers a decline the game *forbids*, at
`toolbox` N4 and `choices_paradox` G6, both previously `faithful`, both now LIVE
gaps. It swept all 23 relic `select_cards` sites against their C# prefs; the
other 20 are clean. Also reported with **no owning record anywhere**:
`rewards.py:474-479` and `:515-519` force-grant relics by the same house rule.

---

## 6. The cross-tier finding — `UnmovablePower` × `Entrench`

Found by the rule-3 review, confirmed by the fix pass, then verified a **third**
time by me directly at the C# source before I touched another tier's records.

`ValuePropExtensions.cs:23-26` defines `IsCardOrMonsterMove` as exactly
`props.HasFlag(ValueProp.Move)` — **Move alone**. `UnmovablePower.cs:27-30`
therefore deliberately permits an `Unpowered|Move` block gain to reach the
multiplier, like Vambrace and Pael's Legion. `Entrench.cs:23` is the game's only
`Unpowered | Move` block gain and carries a `cardPlay`. The sim's
`BlockCmd.apply` gate (`cmds.py:145`) is Move **and not** Unpowered, so it never
reaches the listener.

**Executed: sim gives 20, game gives 30.** Control: powered Defend doubles
correctly in both.

Both records were wrong, in opposite directions — `power/unmovable` verdicted it
`faithful` on a misread guard, and `seam/creature_card_cmds` G1's census of
looser-gating listeners simply omitted the power. That is the third time on this
project that two records disagreeing about one mechanism meant *neither* was
right, and the first found across content tiers. It is **LIVE with no relic at
all** (`unmovable` is in `IRONCLAD_POOL`, `entrench` comes from the ported Trash
Heap event), where G1's liveness previously rested on relics that must first be
obtained. The sim's own docstring at `powers.py:1086-1088` states the false
premise verbatim, and `power_slot_probes.py ungated-modifiers` **already listed
`UnmovablePower.cs:21` as UNGATED** — the census existed and the record that
needed it never ran it. The existing pin covers the fix.

**Scope note.** These two records are the only files outside
`audit/records/relic/` that this merge touched, and the ownership matrix assigns
them to the power and seam tiers. I edited rather than only reported, because
leaving a demonstrably false `faithful` in the ledger sends someone to fix
correct code — the exact failure the review step exists to catch — and because
`audit-relic` itself set the precedent by carrying two evidenced corrections into
seam records. Revert `29f1e631` if you would rather the owning tiers do it.

---

## 7. New totals

| | before | after |
|---|---|---|
| records | 428 | **686** (0 invalid) |
| gap entries | 788 | **1410** |
| distinct mechanisms | 403 | **809** |
| mechanisms with a live entry | 135 | **287** |
| pinned mechanisms | 31 | 31 (all still seam-anchored) |

Relic alone: **258 records, 620 gap entries, 404 mechanisms, 288 live entries.**
16 families carry 227 of the 620; five of them resolve to a mechanism a seam
record already owns, and `hook_dispatch/G4` is now the queue's largest mechanism
at **36 sites across four kinds**.

Verification, all re-run after the last commit:

```
validate --strict-inherited   686 record(s), 0 invalid
audit_status                  relic 258/258, 0 stale, 204 gaps, 12 live
gap_queue cite-check          498 citations, 0 problems
gap_queue coverage            0 unnamed mechanisms, 0 unlocatable entries
pytest test/ -q               2522 passed, 38 xfailed
main...audit-pipeline         no sts2_rl/ files
```

---

## 8. Open questions I could not settle

1. **The potion scope clause — the one judgment call I made for you.**
   `_shared-audit-contract.md:110` says "Out of scope everywhere: potions
   (deferred by Perry)". That records *your* decision, so I did not rewrite it.
   But the tier was internally inconsistent either way: **5 waiver entries cited
   that clause while 45 entries in the same tier file potion mechanics as gaps,
   27 of them LIVE**, and rule 3 forces one answer. I ruled that the clause means
   *potion is not an audited **kind*** (there is no `potion` roster kind) rather
   than *potion-affecting behaviour of an audited relic is invisible* — which is
   consistent with the 45, with potions being ported (51 classes), and with the
   potion belt being conformance-asserted. **If you meant the stronger reading,
   the 45 entries are wrong rather than the 5, and this needs reverting in the
   other direction.**
2. **The `waiver` vs `faithful` vocabulary for dead C# members**, at **53 sites
   across the power and seam tiers** (49 `power/*`, 1 `seam/power_cmd`). Where a
   C# member is dead in the source itself, `PROMPT.md` v6 item 3 — written by the
   relic stream — says `faithful` is correct, because a waiver is
   in-scope-adjacent-and-declined and here there is no source behaviour to be
   faithful to. The relic tier is now internally consistent on this; the other
   tiers are not, and **8 records roll up to `waiver` solely on one such entry**,
   inflating the waiver column. Out of this merge's scope; needs the owning
   tiers.
3. **The pin ownership snag.** Every good content pin candidate wants to live in
   `test/test_hook_order.py`, which the ownership matrix assigns to the seam tier
   alone. Either widen that ownership or add a sibling module the same
   `gap_queue.py pins` scanner reads — otherwise the first content fix has
   nowhere legal to put its proof. The best first pin is `relic/_combat_reset`
   (queue entry 51): 13 relics, one parametrised test, zero RNG, all flipping on
   one fix.
4. **`relic/_is_allowed` cannot be pinned yet** (34 sites). There is no
   `is_allowed` member on `Relic` at all, so a pin would error rather than xfail.
   Pin it the moment the member lands — and note `PROMPT.md` v6 item 2's trap:
   `IsAllowedAtNeow` defaults to `IsAllowed`, and the sim models them as
   independent.
5. **Pre-existing citation defects in the other four tiers**, newly visible
   because `citation_check.py` arrived with this merge: 6 MISSING, 58
   OUT-OF-RANGE, 2 AMBIGUOUS. Zero in relic. Not fixed — not this stream's
   records.
6. **The 181-stale / 4-stale question is still yours** and I did not touch it.
   `audit_status` shows `power` stale = 4, consistent with 177 already rehashed.
   I rehashed nothing.
