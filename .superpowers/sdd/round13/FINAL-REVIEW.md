# ROUND 13 — FINAL WHOLE-BRANCH REVIEW

Independent branch-level reviewer (no lane ownership). 2026-08-01, 14:28 PDT.
Branch: staged-only delta vs base commit `c9bc3374`.
**Individual lanes were NOT re-reviewed.**

> **Snapshot warning.** The controller was still folding while I audited. Every
> number below is measured at **14:28 PDT** and moved at least three times
> during the review (12 → 16 → 17 live entries; 2 → 4 live seam entries). Re-run
> the tools before quoting anything.

## VERDICT: NEEDS-FIXES

**The engineering is sound. The headline claim is TRUE. The bookkeeping is not.**

Every production change I probed is correct, the suite is green, and the new
live seam gaps are real — I reproduced them myself. What fails is the round's
*durable output*: the record and queue layer does not describe the code this
round shipped, **in both directions at once**.

- Gaps the round **created or reopened** are in the records but **absent from
  `GAP-QUEUE.md`** — including **all four** headline live seam gaps. This got
  *worse* during the fix loop, not better (8 → 13 unlocatable entries).
- Gaps the round **closed in code** (R5, the largest lane) are **still recorded
  as open**, because **R5 was never folded**.

**No production code change is required to fix any of this.** Every defect is in
records, the queue, prose, or tests.

---

## 0. PRIORITY ITEM — the hefty_tablet "regression" is REFUTED

**It is not a round-13 regression, and it is not a cross-lane interaction. It is
a measurement artifact of two sessions sharing one worktree — and the polluting
session was mine.** Please strike it from the ledger.

### Evidence

1. **Two independent full-suite runs, real collection order, ~35 min apart:**
   both `3942 passed / 6 xfailed / 2 failed`. The only failures are the two known
   `test_conformance_floor_state.py` fixture-gap failures. The second run was
   made *after* your report.
2. **The three named tests pass** — individually
   (`3 passed in 0.60s`) and inside the full-suite run.
3. **`sts2_rl/relics/hefty_tablet.py` is content-identical to HEAD.**
   `git diff HEAD` is empty; a raw byte hash differs *only* because of CRLF vs
   LF (`newline-normalised equal: True`, 2507 vs 2453 bytes). Do not be misled by
   a raw hash on Windows.
4. **The worktree is clean:** zero unstaged changes, zero `MUTATED` markers
   anywhere in `sts2_rl/`.
5. **A concurrent mutation-testing session was live in this worktree during your
   run window** — the test-quality sweep I dispatched for §4 of this review. It
   applied **53 source mutations**, and it explicitly reports mutating
   **`sts2_rl/relics/hefty_tablet.py`** (to test whether
   `test_hefty_tablet_after_obtained_never_calls_modify_card_reward_options` is
   vacuous — it is; defect D2 below). It further reports that **a concurrent
   `git add`-all staged that mutation**, which then poisoned the index its
   `git checkout --` restored from; it recovered with
   `git reset HEAD -- <file> && git checkout HEAD -- <file>`.

The failing set — three tests, *all* of them hefty_tablet's card-reward
generation — is exactly the blast radius of a mutation to that one file.

### Why it looked order-dependent (it is not)

Transient file mutation and test-order pollution are **indistinguishable from the
outside** when the only thing you vary is the test selection, because varying the
selection also varies the *run duration and wall-clock window*. A 4.5-minute
full-suite run reliably overlaps at least one of 53 mutation windows; a
10-second targeted run falls between them. That produces precisely your
observations: full suite fails, every subset passes.

To distinguish next time: re-run the **identical** command twice (flaky ⇒
transient mutation, not ordering), or hash the tree before and after.

### Your three suspects are all cleared

- **R2's `rewards.py`** — no mutable default or module-level flag leak is
  implicated; the suite is green with that code in.
- **R12's vocab registration** — `vocab.json` shows *only* the round's staged
  append; no test-time rewrite occurred (`git diff` empty). **But your instinct
  is worth recording as a latent hazard:** `frozen_ids` (vocab.py:117-119) really
  does `_save()` to disk whenever a new id appears, so importing the package with
  an unregistered purpose rewrites a **tracked** file as a side effect of import.
  That is a real footgun; it just did not fire here.
- **Card-pool caches / `_CARD_CLASSES`** — not implicated.

### Fix

**Nothing to land in code.** Remove the ledger entry. Process fix: never run
mutation testing concurrently with a staging controller in one worktree — and
note the near-miss, which is the real lesson: **`git add -A` staged a
deliberately-broken relic into the index.** A commit at that moment would have
shipped it, and the round's own rule is "stage, never commit", so the index is
exactly what a human would have committed from.

---

## 1. VERDICT ON THE HEADLINE CLAIM

> *"Round 12's '0 live entries in all six seam records' is broken; there are now
> live seam entries, confirmed by execution, none previously recorded."*

**TRUE in substance.** The seam tier was never clean; it was unmeasured. Two
clauses are wrong, and one of the four current seam entries is misfiled.

### Counts reproduce exactly (at my snapshot)

| | HEAD `c9bc3374` | branch @14:28 |
|---|---|---|
| gap entries | 372 | **360** |
| mechanisms | 349 | **339** |
| labelled LIVE | 7 | **17** |
| mechanisms with a live entry | 7 | **16** |
| live entries in seam records | 0 | **4** |
| unlabelled | 56 | **39** |

The banner's original 372→356 / 349→335 / 7→12 / 0→2 table reproduced exactly
when I measured it; it has since been superseded by the fix loop. Both original
seam live entries carry the **typed** `live: true` field rather than the
caps-token prose heuristic — the firmest footing available.

### `hook_dispatch/F3-R13` (guard10) — LIVE, verified by my own execution

I built the ending window directly (player at 0 HP ⇒ `_has_pending_loss`, `phase`
still `PLAYER_TURN`): `is_ending=True`, `is_over_or_ending=True`,
`hooks.combat_is_over=False`. The sim dispatches where `Hook.cs:53-63` yields
nothing. Separating experiment (sim gate vs. a gate patched to
`is_over_or_ending`, one `on_card_exhausted`, all four exhaust-hook relics):

```
DIVERGE ('relic', 'joss_paper')
    sim now : {'cards_exhausted': 1, ...}
    faithful: {'cards_exhausted': 0, ...}
```

Joss Paper's counter ticks where C# never yields the listener — the round's own
"commands re-gate; counters do not" insight, witnessed. The `CombatTargets` RNG
stream also advances. **Live, confirmed.**

### `creature_card_cmds/F-R13c` (guard25) — LIVE and correctly scoped

I checked the scope question specifically, since filing a driver-level defect on
a command seam would be an easy way to manufacture a "seam live" headline.
`CardSelectCmd.cs` **is** in this record's `game_sources`, and `:582`
(`Selector.GetSelectedCards(list, MinSelect, MaxSelect)`) is the C# consumer.
Legitimate. Exactly three call sites pass `min_select=0` under a non-skippable
purpose (potions.py:1013, potions.py:274, cards/neows_fury.py:74); for the first
two `count = len(hand)`, so `driver.py:372`'s force-fill is unconditional and
**zero decisions are raised**.

### `hook_dispatch/F2-R13` (guard12) — LIVE and correctly scoped. Verified.

`run.py:1161` returns `[*self.relics, *self.deck]`. `RunState.cs:548-562` adds
**deck cards first** (enchantments interleaved), *then* relics and potions — I
read the C# directly. Genuinely reversed, genuinely live, and `RunState.cs` is in
`hook_dispatch`'s `game_sources`. **Extra divergence worth adding to the entry:**
the sim's `_map_listeners` has **no potions at all**, where C# adds
`player2.Potions`.

### `creature_card_cmds/F-R13d` (guard26) — LIVE, but MISFILED. Inflates the flagship metric.

This is R2's FIND-D (NoUpgradeRoll unmodelled at ~11 non-combat creation sites) —
a real, well-evidenced live gap that deserved filing. **But it is not a
`creature_card_cmds` mechanism.** It cites `CardFactory.cs`,
`CardCreationOptions.cs`, `CardCreationFlags.cs`, `Orrery.cs`,
`LastingCandy.cs` — **none of which is in that record's `game_sources`** — and
its 11 sim sites are all `events/*.py` and `relics/*.py`, none in `sim_sources`.

R2's own report asked for a queue item named **`reward/no_upgrade_roll_flag`**.
That is the right home. **The honest seam-live count is 3, not 4.** Since "live
entries in seam records" is this round's flagship number, misfiling a
content-tier mechanism into it is the one bookkeeping error that directly
overstates the headline.

### The false clause: "neither previously recorded"

`hook_dispatch` **steps[45]** already covered the `IsOverOrEnding` gate — and
**closed it**:

> *"(3) IsOverOrEnding dispatch gate (guard G8) — **ALSO NOW CLOSED** … EXECUTED
> today: `py -m pytest test/test_combat_over_hook_gate.py -q` -> `9 passed`"*

That entry is **UNCHANGED this round** (verified byte-for-byte against
`git show HEAD:`), still says "ALSO NOW CLOSED", and is still labelled
**`live: false`**. The record now self-contradicts, and the stale half carries
the label dormancy triage reads.

Three consequences, all of which make the round's story *stronger*:

1. F3-R13 is not a discovery — it is the **reopening of a bad round-11
   closure**, a more valuable fact than "newly found".
2. That closure was argued **from a green test file**. I ran it:
   `test/test_combat_over_hook_gate.py` → **9 passed**, today, while the gap is
   live. The round-12 lesson in its purest form, sitting unclaimed in the round's
   own record.
3. Leaving `steps[45]` at `live: false` is the likeliest way for the next round
   to re-close F3-R13.

**Also contradicted:** R1's own fold line asserts *"hook_dispatch seam: … still
0 live"* — while R1 is the lane that filed **both** of hook_dispatch's live
guards.

---

## 2. CROSS-LANE INTERACTION FINDINGS

### X-1 (CRITICAL) — R5 was never folded. The largest lane shipped in code and not in the records.

The ledger marks five lanes `COMPLETE, APPROVED, FOLDED` (R1, R2, R8, R11, R12).
**R5 is marked only "IMPLEMENTED … review running" (progress.md:406) and
"interrupted a SECOND time" (:480).** `R5-review.md:14` is `NEEDS-FIXES`. There
is no fold line — yet the round published final counts and credits R5's fixes
among its headline findings.

The fold is *partial*, which is worse than absent: the record looks current.
Verified verbatim against the shipped tree:

| entry | verdict | says | tree says |
|---|---|---|---|
| `creature_card_cmds` guards[21] (**N9**) | gap | "The sim appends the played card to the **DISCARD** pile" | `player.py:129` `play_pile`; `combat.py:963` `_add_to_play_pile` |
| `creature_card_cmds` steps[84] (**step82**) | gap, **live:false** | "the sim **still has no Play pile** … still appends the played card straight to DISCARD" | `combat.py:1004` Play entry; `:1232-1265` Play-gated exit switch |
| `creature_card_cmds` steps[53] (**step51**) | gap | "The Sly keyword is **UNPORTED** — **no** `IsSlyThisTurn` analogue anywhere in sts2_rl" | `cards/base.py:528` `is_sly_this_turn`, used `cmds.py:1281` |
| `creature_card_cmds` steps[52] (step50) | deliberate-divergence | "`DiscardAndDraw` has **no sim counterpart**" | `cmds.py:1242`, both callers routed |
| `creature_card_cmds` steps[47] (step45) | deliberate-divergence | "removes the card from whichever of the **four** piles" | deleted; `auto_play_card` no longer scans piles |
| `GAP-QUEUE.md:2053` | — | "the sim has no Play pile … hold-back is **in parity mode only**" | unconditional since round 7 |

**Consequences:**

- **The published count is wrong in the direction the round does not claim.**
  `creature_card_cmds` carries 11 gap entries; **at least 3 are closed by shipped
  code**, plus one whole mechanism (`creature_card_cmds/N9`, n=2). The round's
  narrative is "the count went UP and that is honest" — but part of the count
  that went *down* did not go down far enough, for the opposite reason.
- **R5's requested new entries never opened.** `R5-report.md:1552` asks for F9
  (the `on_card_exhausted` enumeration + the Joss Paper counter class), F10
  (`CardCmd.cs:242`), F12 (`_playing_card` is now unread state), and F3-F7
  queued. `grep -rn "R5" audit/` returns **5 hits in 4 files**; `GAP-QUEUE.md`
  contains **zero**.
- A future reader greps `N9`, reads "the sim has no Play pile", and reimplements
  a pile that already exists.

### X-2 (CRITICAL) — Every entry this round created or reopened is missing from `GAP-QUEUE.md`, and the fix loop made it worse.

`py audit/tools/gap_queue.py coverage` — a gate this project ships **specifically**
to catch queue/record desync:

| | HEAD | branch (first measurement) | branch @14:28 |
|---|---|---|---|
| mechanisms not named in queue | **0** | 7 | **12** |
| entries not locatable in queue | **0** | 8 | **13** |

The missing set is almost exactly the round's own work: **all four live seam
entries** (`hook_dispatch/guard10`, `guard12`, `creature_card_cmds/guard25`,
`guard26`), **all three reopenings** (`potion/ashwater/g1`,
`potion/gamblers_brew/g1`, `relic/gnarled_hammer/g3`), R8's new
`turn_structure/guard23`, `hook_dispatch/guard11` (F-R13b), the reopened
`creature_card_cmds/G4`, and the three newly filed event live gaps
(`brain_leech/g6`, `/g7`, `trial/g17`).

The file's own header says *"Generated, not transcribed."* It was not
regenerated. The banner **prose** describes F3-R13 in its "corrections" section,
but most of the rest appear **nowhere in the file at all**. Compounding it, the
banner names them `F3-R13` / `F-R13c` while the tool's id space calls them
`hook_dispatch/guard10` / `creature_card_cmds/guard25`, so `gap_queue.py list`
will not match the banner either.

Two further queue-body staleness items, both already misleading:
- The *"Round 13 — corrections that REOPEN or WIDEN"* section covers only R11's
  four items; **R12's three reopenings are missing from it.**
- `GAP-QUEUE.md:2873` still describes `relic/_auto_keep` as `relic/kifuda/g2` +
  `/AfterObtained` — **the site that closed** — rather than gnarled_hammer, the
  site that is live.

**Net effect: the round's central achievement is mechanically invisible to the
next round's tooling.**

### X-3 (HIGH) — R5's Play pile silently closed gaps in records no lane owned; two of six were updated.

56 entries across 42 records cite the retired "resolving card is parked in the
discard / `all_cards` omits Play" premise. R5 correctly rewrote `power/smoggy`
and `power/ringing`. Four more carry the identical argument and were left:

- **`card/apotheosis` guards[0] (gap)** — the whole issue text is falsified.
  Executed: a Power card inside its own `OnPlay` reports `pile_type_of == "play"`
  and `card in player.all_cards is True`. **Closed and unrecorded.**
- **`power/dampen` hooks/AfterApplied (gap)** — same claim verbatim; `player.py:206`
  now returns all five piles.
- **`card/cascade` guards[0] + guards[3]** — rationales quote deleted code
  (`cascade.py:38-40, 59-61`); the file is now one `auto_play_from_draw_pile`
  call. Another unrecorded close.
- **`card/neows_fury` hooks/OnPlay (gap)** — calls the `c is not self` predicate
  "a CORRECT compensation for the sim's discard-pile limbo"; R5 deleted that
  predicate. **The ledger claims R12 filed a correction to this exact entry — the
  file is not in the branch's modified set at all.**
- **`relic/pen_nib` guards[1] + hooks/ModifyDamageMultiplicative (faithful)** —
  quote the `_playing_card` idiom; `pen_nib.py:77` now reads
  `card not in play_pile`. R4's headline is "**ZERO production edits needed**"
  for a file R5 then edited.

### X-4 (HIGH) — R8 proved a dormancy backstop is dead code; the engine comment still asserts the opposite, in the same tree.

`cmds.py:310` `if target.is_dead: return 0` dominates `:312`
`if not hooks.should_allow_hitting(target): return 0`. But `cmds.py:303-309`
still reads:

> *"the sim's `should_allow_hitting` hook (guard N1) … **is not made redundant by
> this** — it is the documented C#-has-no-single-hook-here divergence, kept as
> is."*

directly against `relic/charons_ashes`: *"THAT BACKSTOP DOES NOT EXIST — the line
is DEAD CODE."* `cmds.py` was outside R8's footprint, so nobody reconciled them.
**The same record asserts both**: `charons_ashes` guards[0] still cites the
backstop as its dormancy reason; `letter_opener` has the identical split.

R8 scoped this to "four entries"; **≥11 still rest on it**, including four
**`faithful` closures** (`lost_wisp`, `mercury_hourglass`, `mr_struggles`,
`screaming_flagon`) and `seam/damage_pipeline` steps[0]/guards[4]. All their line
cites (`cmds.py:48-52`) are stale — the line is `cmds.py:312`.

### X-5 (HIGH) — `HookSystem.combat_is_over`'s own docstring asserts the opposite of the round's headline finding.

hooks.py:525-533 (pre-existing, **untouched**): *"`CombatManager.IsOverOrEnding`
… `phase` is set to `COMBAT_OVER` in `_end_combat`, which is the moment the
ending begins, **so it covers both**."* That is exactly what F3-R13 refutes, and
`combat.py:1825`'s docstring says the opposite in the same tree. The round added
the correct note **1,080 lines away** at hooks.py:1605-1609 and left the false one
sitting on the function that has the gap.

This is the failure mode the ledger flagged for `player.py` and fixed there —
*"the single thing most likely to get that fix deleted later."* Same class,
different site, not caught.

### X-6 (MEDIUM) — F3-R13's cited witness was invalidated by a sibling lane.

The entry says *"ForgottenSoul dealt REAL DAMAGE (enemy 56→55)"*. Executed on the
final branch: **56 → 56**, because R5 added the `is_over_or_ending` bail to
`DamageCmd.deal` (cmds.py:474) *after* R1 wrote the text. The RNG half survives.
The entry is genuinely live — I proved it via Joss Paper — but its headline
evidence no longer reproduces, so the next owner tries it, fails, and may
conclude the gap is stale. **Replace the witness with the Joss Paper counter.**

### X-7 (MEDIUM) — R5's exhaust gate is claimed uniform and is not.

`combat.py:1242-1247` says the gate "covers this arm and **the thirteen other sim
exhaust sites alike** … **uniformly at every exhaust site**". Three sites never
call `ExhaustCmd`: `combat.py:820-826`, `combat.py:854-858` (both ethereal legs)
and `relics/toasty_mittens.py:48-51`. Executed with combat ending:

```
A ExhaustCmd while ending   -> exhaust pile: []          # correctly refused
B ethereal leg while ending -> exhaust pile: ['dazed']   # exhausted + fired the hook
```

That is exactly the Joss Paper over-credit R5 named as the reason the gate is
*not* dormant — still reachable, through a leg in the file R5 rewrote.

### X-8 (MEDIUM) — Two lanes' reward channels do not meet.

Six event records (`drowning_beacon`, `endless_conveyor`, `potion_courier`,
`the_legends_were_true`, `wellspring`, `whispering_hollow`) carry `faithful`
closes citing **`Event.offer_card_reward`**, which R2 **deleted** (0 hits
repo-wide), and `_accept_offer` line ranges R6 rewrote. Verdicts survive; the
evidence trail points at deleted code.

Separately, `Event.offer_potion`'s 8 call sites build **no `CombatRewards` at
all** (events/base.py:263-268), so R10's choke point and both backstops can never
see them — C# routes them through `RewardsCmd.OfferCustom` → `Hook.ModifyRewards`.
Dormant today, but R10's "one choke point reached from two entry points" framing
reads as complete and is not.

### X-9 (LOW) — `_accept_offer`'s docstring documents a branch the code does not contain.

events/base.py:231-247 describes a `purpose == "card_reward"` step "kept, rather
than raising". No such branch exists at :255-260. R6 wrote it for pre-R2 code;
R2's deletion landed underneath it.

### Verified clean — so the next round does not re-chase these

- **R1 × R5 pile-order consistency HOLDS.** `hooks._derive` (hooks.py:427-437)
  emits `hand, reversed(draw), discard, exhaust, play`; `player.all_cards`
  returns the same five in the same order; both match `PlayerCombatState.AllPiles`
  with Play last. The inactive-player `excluded` leg covers `play_pile`. This was
  the round's highest-risk lane pair and it was integrated deliberately.
- **`player.py`'s ActivateHooks comment IS fixed.**
- **`relics/pen_nib.py:77` — the owed line landed** and is correct. Only the
  *record* is stale.
- **`cards/neows_fury.py` WAS edited by R5** and is correct; the ledger's "NOT
  edited: another lane holds it this wave" is stale.
- **Glory shims fully removed**; a scan of all 113 `Monster` subclasses against
  all 94 dispatchers finds exactly the two intended handlers.
- **R10's "`OfferForRoomEnd` is dead code" — confirmed** (declaration + one
  `<see cref>`, zero call sites); treasure dormancy re-executed across all 8
  implementers, every one a no-op.
- **R3 × R5 interactions correct** — Dark Embrace's ethereal deferral and the
  Corruption/Rebound result-pile chain both re-executed against
  `Hook.cs:1391-1405`.
- **`can_receive_powers` / `_combat_contains_creature`** correctly filed as
  `hook_dispatch` guards[11] (F-R13b) with the honest "blocked on blast radius,
  not footprint" reason. Deferred, not broken.

---

## 3. BOOKKEEPING-HONESTY FINDINGS

### B-1 (CRITICAL) — Three records are schema-INVALID. `audit_status` exits 2 where HEAD exits 0.

The three entries R12 **reopened** flip `verdict` to `gap` but write their
reasoning into `rationale` and leave **`issue` empty**, which
`harness._check_entry` (harness.py:837) rejects:

```
INVALID audit/records/potion/ashwater.json        guards[0]
INVALID audit/records/potion/gamblers_brew.json   guards[0]
INVALID audit/records/relic/gnarled_hammer.json   guards[2]
      -> verdict 'gap' requires a non-empty issue
```

**Exactly 3 of 220 gap entries repo-wide lack `issue`, and all three are this
round's.** Consequences: `audit_status.py` **exits 2** (HEAD exits 0) and drops
them from the audited counts (potion 51→49, relic 258→257). Still unfixed at
14:28. The reasoning *content* is excellent — this is a pure field-name error —
but it is on the three entries the ledger celebrates as *"UP, and that is the
honest direction."*

**Nothing in the 3942-test suite catches this.** The only `validate_record`
sweeps in `test/` run on synthetic `tmp_path` records, never the real corpus. The
round's own lesson — a green suite is not evidence — applied to the round.

### B-2 (HIGH) — `relic/pen_nib`'s close landed on the wrong entry. Third occurrence of the label-vs-positional trap.

The ledger claims R4 stale-closed pen_nib G3. What changed is
`hooks["AfterCardPlayed"]` gap→faithful. **`guards[2]` — whose `what` literally
opens `"G3 (DORMANT): C# skips Hook.AfterCardPlayed entirely …"` — is untouched
and still `gap`.** The tell is inside the close note: it says "The old text read
that C# skips Hook.AfterCardPlayed…", but its own `The text it replaced read:`
archive is about per-play replay-doubling — a different claim. The note is
answering `guards[2]`, not the entry it was written onto.

The C# reasoning is **correct** (`CardModel.cs:1957` is the `IsInProgress` gate,
`:1959` the dispatch). G3 genuinely should close — it just didn't. Record
top-level is still `gap` and `GAP-QUEUE.md:3026` still carries
`relic/pen_nib/g3` as open. **This is the trap the round elevated to a binding
rule, biting a third time in the same round.**

### B-3 (HIGH) — `power/nostalgia/g8` is a LIVE entry whose cross-reference target no longer exists.

R3 wrote guards[7]: *"The Corruption half stays OPEN and LIVE, cross-referenced to
`power/corruption` rather than independently re-argued (binding rule 3)."* R5's
fold then closed `power/corruption` — **hook and top-level, 0 gap entries,
verdict `faithful`** (verified). Nostalgia is still `gap` and still counted LIVE.
One mechanism, two verdicts, in violation of the binding rule the entry invokes.

It is also **the only one of the live entries whose liveness is inferred from the
prose caps-token "LIVE"** rather than the typed `live` field — so it would
silently revert to dormant if reworded. Weakest entry in the headline set.

### B-4 (HIGH) — `creature_card_cmds/F-R13d` is filed in the wrong tier (see §1). Directly overstates the flagship metric.

### B-5 (MEDIUM) — The reopenings are REAL. Confirmed by execution.

Verified independently, and they hold exactly as written:

- **`relic/gnarled_hammer` N2** — `GnarledHammer.cs:30-34` is character-for-character
  Kifuda's prefs (both citations exact). Through a real `RunDriver` with a
  decline-everything policy: **3 enchanted, 3 asks, legal actions with no skip
  index**; the Kifuda control gives **0 enchanted, 1 ask, skip index present**.
  "`relic/_auto_keep` narrows, does not close" is correct.
- **`potion/ashwater` G1 / `potion/gamblers_brew` G1** — `min_select` never
  reaches the selector; `driver.py:372` force-fills. Executed: **Ashwater hand
  5 → 0, exhaust pile 5, zero SELECT_CARDS decisions raised.**
- **`creature_card_cmds` steps[20] + guards[3]** — executed both directions:
  enemies dead / phase `PLAYER_TURN` → `heal(enemy,7)` returns **7** where C#
  refuses; phase `COMBAT_OVER` → returns **0** where C# permits. **Complementary
  window, wrong in both directions**, exactly as claimed, including that
  `is_over_or_ending` would over-guard.

### B-6 (MEDIUM) — `card/breakthrough`'s new guard states its cross-file dependency honestly, but is factually wrong about its own pins (in the safe direction).

The guard does what the campaign requires: it records that the deletion "rests
ENTIRELY on `DamageCmd.deal`'s `dealer.is_dead` bail in `sts2_rl/cmds.py`" — a
different file. **The dependency is real** (`cmds.py:295`; neutering it makes
enemies take damage where C# lands nothing).

But it also claims *"the tests in this record will NOT catch it"*. Mutation says
otherwise: with the bail disabled,
`TestBreakthroughGuardDeleted::test_dying_from_the_hp_loss_lands_no_attack_on_any_enemy`
**fails**. One of the two pins *is* a regression detector; the caveat is only
true for the narrow "reordered behind a hook" case. Errs cautious, but it is a
factual error in a guard whose entire purpose is to state the dependency
precisely.

### B-7 (MEDIUM) — Close notes: reasoning-replacement discipline is genuinely good; a few characterisations are loose.

I sampled well beyond six. **The overwhelming majority state which *reasoning*
they replaced**, with an explicit `WHAT REASONING THIS REPLACES:` and a verbatim
`The text it replaced read:` archive. Verified honest, with correct C# citations:
`power/rebound` ×2, `power/retain_hand`, `relic/lizard_tail` ×2, `relic/fur_coat`
(the "divergence never existed" finding **confirmed** — whole-source grep gives
`Hook.AfterCreatureAddedToCombat` exactly one dispatch site, `CreatureCmd.cs:81`),
`relic/ruined_helmet` ×2, `power/artifact`, `event/the_future_of_potions` g15 +
the new flag guard, `seam/hook_dispatch` R1 steps 3/4/6/9/44/45 + G6,
`relic/festive_popper` G1, and `creature_card_cmds` G8 — whose **honest widening**
(`CardCmd.Exhaust` *is* `CardPileCmd.Add(…, Exhaust)`, `CardCmd.cs:242`) I
verified and which was correctly **not** landed.

**No close I checked claimed FIXED where the code only narrows.** The round's
conservatism held; where a residue existed the verdict says NARROWED (G7, G8,
`_auto_keep`). Loose characterisations only:
- `power/dark_embrace` AfterCardExhausted says "the record described the
  hard-coded draw count as the whole divergence"; the archived text actually
  opens "Two divergences. (a) … (b) THE ETHEREAL DEFERRAL IS MISSING". Verdict
  right, description of the replaced text loose.
- `relic/unsettling_lamp` — the G2 close is right, but
  `hooks["ModifyPowerAmountGivenMultiplicative"]`'s `maps_to` still carries four
  dead references to a deleted `modify_power_amount`.

### B-8 (LOW) — Accounting otherwise checks out.

Every changed record entry maps to a ledger claim except `relic/festive_popper`
(closed during the fix loop, not mentioned in ROUND 13 CLOSE). **No entry was
found silently overwritten on a wrong index**, and R12's documented recovery of
its own gnarled_hammer mis-fold verifies: `guards[2]` is the only changed entry;
`guards[1]` is byte-identical to HEAD.

---

## 4. TEST-QUALITY FINDINGS

**~100 tests mutation-tested across the three highest-risk files (53 source
mutations, each restored and verified), plus read-level analysis of the rest.
Defect rate ≈ 3% in the engine-seam files, ≈ 6-8% across all ~200 new tests,
concentrated almost entirely in the two "dormancy re-confirmation" files.**

An independent read-only AST scan of 185 new/changed tests in the high-risk files
found **zero** with no assertion at all.

### The positive — the engine-seam test layer is the strongest thing in this round

- **`test_round13_play_pile.py` — 52 of 54 killed by targeted mutation.**
  Reverting `_add_to_play_pile` to HEAD's discard-parking shape kills **30 at
  once**. Individually strong and correctly *narrow*: the Play-membership exit
  gate (kills exactly 1), the `default:`-arm `IsEnding` refusal (2), `ExhaustCmd`'s
  `IsOverOrEnding` wrapper incl. the Joss Paper run-scoped counter (3), `all_cards`'
  Play leg (3), `_derive`'s Play slot (1), result-pile-before-play-count ordering
  (1), `remove_from_current_pile`'s fifth pile (8), `pile_type_of`'s Play leg (6),
  `PileIndexSort` (2), the Sly tail's ordering and `AutoPlayType` arg (1 each).
  **The Corruption/Rebound pair is exemplary**: both directions of
  `Hook.cs:1391-1405`'s order-dependent stack are independently pinned.
- **`test_round13_listener_derivation.py` — 22 of 31 killed, 0 defects.** Every
  derivation rule independently pinned, including the subtle one: **eager
  filtering instead of the lazy per-item `Contains` kills 2 tests.** The 9
  unkilled were simply not mutated ("not sampled", not "weak"). I separately
  confirmed by reading that these pins assert *relational* properties against
  C#-derived expectations (`_ordered()[-1] is cs.enemy`, index orderings) — **not
  circular**.
- **`test_reward_dispatch_choke_point.py` — 14 of 15 killed.** Removing the
  `generated` flag kills 11 of 15; removing the two offer-time backstops kills
  exactly the 2 backstop tests. The `_CountingRelic` design (count calls, not
  totals) is the right call.

### Defects — confirmed by mutation

**D1 (HIGH) — `test/test_hook_order.py:339`
`test_card_mid_play_is_excluded_from_a_reshuffle_it_triggers` asserts its own
setup.** Replacing the *entire* body of `reshuffle_discard_into_draw`
(player.py:482) with a naive 2-line stub — no `IsOverOrEnding` gate, no
`StableShuffle`, no `AfterCardChangedPiles`, no `on_shuffle` — **still passes**.
The test does `p.play_pile.append(held)` itself, then asserts
`held not in p.draw_pile` and `p.play_pile == [held]`; the production method
never references `play_pile`. **It is cited as the seed-fact pin for step 82 and
can no longer detect anything.** (Mitigation: `test_round13_play_pile.py::
test_a_mid_play_card_is_excluded_from_its_own_reshuffle_by_construction` pins the
same fact genuinely.)

**D2 (HIGH) — `test_r13_relic2.py:255`
`test_hefty_tablet_after_obtained_never_calls_modify_card_reward_options` is
vacuous AND inverted.** Stubbing `HeftyTablet.after_obtained` to `return` leaves
**all 20 tests in the file passing**. `assert calls == []` is structurally
guaranteed — `hefty_tablet.py` contains no hook dispatch at all. Worse, the cited
spec (`CardFactory.cs:104-107`) says the game *does* dispatch there, so **closing
the gap this round declared LIVE turns this test RED**.

**D3 (LOW-MED) — `test_reward_dispatch_choke_point.py::
test_treasure_room_reward_dispatch_is_dormant_with_todays_roster`.** Deleting the
whole treasure-room dispatch block from `run.py` leaves it passing;
`assert pending_treasure_extra_rewards is None` is what "no dispatch at all"
produces.

**D4 (LOW) — `test_round13_play_pile.py::test_gambling_chip_routes_through_discard_and_draw`.**
Open-coding the discard+draw loop still passes; it asserts only
`order == ["discard","draw"]`. Its Gambler's Brew sibling *is* load-bearing.

### Divergence pins — strong tests defending known-wrong behaviour

These are the expensive kind, and the round's own banner claims three:

- **D5 — `test_r13_relic2.py:176`
  `test_festive_popper_check_win_still_ends_combat_inside_its_own_dispatch`.**
  Removing `self._check_win()` kills it, so it is *strongly* load-bearing — on the
  wrong behaviour. Its own header says C#'s `CheckWinCondition` is step 27
  (`CombatManager.cs:573`), after the turn-start dispatch. Fixing the gap breaks
  the test.
- **D6 — `test_r13_relic1.py:107` unsettling_lamp G3** — `assert factor == 1`
  while `UnsettlingLamp.cs:106-129` has no applier/target check and returns `2m`.
  Self-labelled "the still-open half of G3".
- **D7 — `test_r13_relic1.py:244` booming_conch** — asserts `energy == before + 1`
  *with `NoEnergyGainPower` applied*; the test's own comment concedes "A real
  `EnergyCmd.gain` would have been reduced to 0."

### Weak / vacuous (read-level)

`test_r13_relic2.py:724` (asserts substrings of a `__doc__`); `:315` (3 of 5
assertions are `hasattr` on base-class-declared methods — always true); `:78`
(follows from the test's own precondition); `test_kifuda_partial_enchant.py:61`
(two asserts unreachable — the driver force-fills so the callback never runs);
`test_r13_power1.py:123` (passes with `ReboundPower.modify_card_play_result_pile`
deleted entirely); `test_selectors.py:86` and `:141` (premise-pins — only `:54`
and `:108` go RED under the clamp mutation);
`test_event_offer_screens.py:459` (green under the pre-R6 `_accept_offer`, so
zero R6 coverage); `test_is_dead_early_returns.py:227` (`fresh()` is a
*single*-enemy encounter, so the "per-enemy loop" the class exists for is never
exercised — and `breakthrough.py` still contains the card-level
`if ctx.player.is_dead: break` the class name says was deleted).

### Citation drift in tests

**Every C# citation spot-checked (~45) is exact, line-for-line.** *Sim-internal*
line numbers have drifted: `test_r13_relic1.py:37-53` (`combat.py:986/863/880` →
real gate `combat.py:1140`), `test_selectors.py:88-90` (cites blank lines inside
a docstring), `test_r13_relic2.py` (`run.py:821`→866, `hooks.py:1712`→1736,
`powers.py:1094`→1108).

---

## 5. THE RL-OBSERVATION CLAIM

**The claim holds. Checkpoints load. No retraining is required.** Measured in
full, not only the schema.

### (a) "No obs schema change" — **VERIFIED**

Branch vs. a `git archive HEAD` export:

```
RUN_OBS_SCHEMA_VERSION : 6            (both)
OBS_SCHEMA_VERSION     : 3            (both)
obs vector             : (31227,) float32   (both)
N_ACTIONS              : 1385         (both)
N_PURPOSES             : 24           (both)
every named segment    : IDENTICAL    (diff produced no output)
```

The one vocabulary change **appends** `"enchant_optional"`. `N_PURPOSES` is
`vocab_capacity("purposes")` = **24**, a fixed reserved width; the list is at
**18**. `merge_frozen` is append-only and preserves every existing index.
Dimensionality unchanged, no prior index moved, **checkpoints load**.
`vocab.py:111-116` is explicit that crossing 24 *would* be a schema break —
**6 slots remain, and R12's own record already owes a sixth purpose fork.**

`combat_card_db.py:39` gained `play_pile`, but its only consumers are
`sts2_rl/conformance/*`; it does not feed the observation.

### (b) "Moves exactly two obs slots by one card" — **VERIFIED, literally exact**

Combat env, 5 seeds, identical seeded policy, HEAD vs branch, diffing the
terminal observation float-by-float against `obs_segments()`:

```
seed 0..4 | differing floats: 2 | by segment: {'player.pile_sizes': 1, 'discard_pile': 1}
```

Two floats, every time: the discard-pile **count scalar** and **one slot of the
discard composition vector**. Not approximate — precise. `play_pile` is
deliberately **not encoded anywhere** (only draw/discard/exhaust are,
full_env.py:239-241).

**One nuance the ledger does not state:** this is a small *information* change,
not merely a re-labelling — at a mid-`OnPlay` decision point the policy can no
longer see the resolving card in any pile. That is *more* faithful (it matches
what a human sees, and C#'s Play limbo) and trajectory-neutral in measurement,
but it is not "nothing changed".

### (c) "Never changes a trajectory" — **CONFIRMED at the aggregate level**

- **Combat env, 5 seeds:** 0 of 5 mid-trajectory differences. Every pre-terminal
  observation, action, reward and episode length byte-identical.
- **Run env, 30 seeds** (uniform-random-over-legal-mask, same seed stream both
  sides): **29 of 30 byte-identical** on the full obs+action hash; the one
  differing seed had **identical reward and identical step count**.

I could not attribute that seed to a lane (the branch is one staged blob), so I
neither confirm nor refute the "100% the events lane" attribution — but nothing I
measured contradicts it, and **rewards were identical on all 30**.

### (d) "Terminal observations of 3 of 5 combats differ" — **UNDERSTATED; I measure 5 of 5**

Different seeds and policy from the lane's, so not a contradiction of their run,
but the effect is *uniform*, not occasional. The structural conclusion stands: it
is a `terminated=True` observation, which PPO/GAE never bootstraps from. **The
only RL number I could not reproduce, and it errs in the safe direction.**

### (e) An RL-visible defect the round created and left in a report

`"transform_optional"` (Claws) is a **skippable** purpose that is **not** in the
obs vocab, so it encodes as `_unknown` — the policy cannot distinguish that
screen. R12 added `enchant_optional` and did not add it. The production comment
at run_env.py:189-192 literally reads *"see this round's report for that gap"* —
**production code pointing at an ephemeral lane artifact the next round will not
read.**

---

## 6. WHAT THE ROUND MISSED OR MIS-STATED

### Banner statements that are false

- **"`hook_dispatch/G7` … the Card leg is set at 2 of 3 in-combat sites" —
  FALSE, twice.** C# has exactly three `RemoveFromState()` call sites
  (`CardPileCmd.cs:79`, `:189`, `CardCmd.cs:506`); the sim sets the flag at **all
  three** (`combat.py:1166`, `cmds.py:1475`, `run.py:465`). Only two are
  in-combat at all. The record's own residue contradicts itself in one sentence
  and the banner copied the wrong half. *(The Relic leg really is machinery-only
  — declared at `relics/base.py:136`, read at `:233`, never set. That half is
  right.)*
- **Tooling: "`closer.py` now documents it as TRAP 3 and ships
  `find_labelled(local_id, label)` … Never fold a guard entry without it." — the
  tool does not exist.** `audit/tools/` has no `closer.py`; `find_labelled`
  appears in **zero** `.py` files repo-wide; `git ls-files | grep closer` is
  empty; it is absent from all four sibling worktrees. It is a per-round
  scratchpad helper. **So the TRAP-3 *fix* is lost (only the lesson survives),
  the binding rule is unenforceable next round, and progress.md's gate
  "closer.py round-trip 848/0" is unreproducible.** B-2 above is that trap biting
  a third time.
- **"Four fixes introduced new divergences … a killing-blow card leaving a pile
  C# leaves it in" — the fourth is misattributed.** That is HEAD's *pre-existing*
  behaviour, which R5's fix **removed**. The honest count is three.
- **"Three tests were defending bugs" — not supported by its own enumeration**
  (it names two, then adds a different failure class). Ironically the true count
  is at least three — D5/D6/D7 above — just not the ones named.
- **"one record cited a gap that had closed *three rounds before* that record's
  own audit date" — inverted.** `bag_of_marbles.audited = 2026-07-26`;
  `power_cmd/G6` closed 2026-07-29 — three days **after**. The banner
  contradicts the record it is summarising.
- **"A dedicated sweep is warranted (56 `is_over` reads)" — unverifiable.** R11's
  report says 56, its review says 49, a grep today returns **59**. The same
  number is repeated inside `hook_dispatch/guard10`.
- **"R9's brief is written and current" — the premise is current, the citations
  are not.** `hooks.py:1061-1090` → now `1350-1377`; `cmds.py:404-408` → now
  `450-451`. The brief self-declares the drift; the banner does not.

**Verified TRUE:** the 18 `StatusIntent` sites with 5 ported; "39 unlabelled,
down from 56"; `step56` has no production consumer (`pile_index_sort_key` is
referenced only by its own definition and a test); `creature_card_cmds/G8`
NARROWED; R7/R9 have briefs and no reports.

### Banner omissions

- **There is no "what this round DID" section at all.** The largest change —
  `player.play_pile` as a real fifth pile, the OnPlayWrapper statement order, the
  Play-gated exit switch, four `IsDead` early returns, `CardCmd.discard_and_draw`,
  `AutoPlayType` — appears only as "the Play-pile lane that blocked R7/R9".
  Combined with X-1, **the queue still tells the next round "the sim has no Play
  pile."**
- **New engine machinery a future round must know about, none of it named:**
  `HookSystem._derive`, `hook_contains()` across seven types,
  `is_active_for_hooks` + the `ActivateHooks` mirror in heal,
  `Monster.combat_removal_committed`, `Card.has_been_removed_from_state`,
  `CombatRewards.generated` + the offer-time backstop,
  `create_reward_cards(extra_flags=…)` / `CardRewardGroup.flags`.
- **A deleted public API: `Event.offer_card_reward`** (zero callers) — any future
  event port must use the `pending_rewards` → `CardRewardGroup` path. Also
  deleted: both glory listener shims.
- **`sts2_rl/vocab.json` changed** — the trained-model contract file. Harmless,
  but must be committed with the code and never reordered, and the banner asserts
  "No obs schema change" without mentioning it.
- **`live2.json` — a 49 MB observation dump is STAGED at the repo root**
  (`A live2.json`), referenced by nothing but a file list in `R12-review.md`.
  `git rm --cached` before commit.
- **Deferred items absent from "What this round did NOT do":**
  `relic/hefty_tablet/G2`'s fix (a LIVE gap, blocked on footprint); the Play-pile
  record reconciliation; `power/nostalgia/g8`'s Corruption half.

### Findings that were unfiled when I started — the controller filed several mid-review

Credit where due: R2's FIND-D, R2's FIND-A (brain_leech/trial reroll pool), R1's
F2 and the brain_leech `modify_hooks` stand-in were filed during the fix loop.
**Still unfiled and living only in lane reports** (which the next round will not
systematically read):

1. **R8's `festive_popper/G3`** — R8 reports the real divergence is
   `Relic._check_win → _end_combat` performing teardown inline where
   `CheckWinCondition` only *dispatches* it, and that **no replacement gap
   exists**. The new `turn_structure/G-R8` covers the tie-break, a different
   thing. *(This is the mechanism D5's strong test defends.)*
2. **R8's `spiked_gauntlets/G2`** — determined stale-already-fixed; record still
   `gap`.
3. **R3's F2/F3** — `power/_death_prevention_branch`'s summary may be wholly
   stale (all three named units dropped their `ShouldDie` overrides — a re-check
   could close the mechanism); `power_cmd/G5` overstates the `the_bomb` closure.
   Related: the ledger says R3 confirmed `power/the_bomb/InstanceType` LIVE, but
   **`power/the_bomb.json` was never modified and still reads dormant.**
4. **R4's systemic check over the ten deliberate `IterateCombatHookListeners`
   bypasses** — any entry reasoning "C# gates X on `IsOverOrEnding`" for one of
   those must be re-derived against the *caller-level* gate. **`hook_dispatch/
   guard10`, which orders exactly that sweep, carries no such warning**, so the
   prescribed sweep is set up to over-gate them.
5. **R11's `state_machine_probes.raise_sites()` vs `monster_state_machine/N7`** —
   the probe now buckets 8 SYM / 1 gap / 2 closed asymmetries; N7 still says "the
   FIVE symmetric sites". Record untouched.
6. **R5's RV-7** — `all_cards` walks the draw pile bottom-first where C#'s
   `AllCards` is top-first (`hooks._derive` flips it; `all_cards` does not). Real
   latent divergence, documented only in a `player.py` docstring.
7. Minor: R5's RV-9 (the `pen_nib` pin now sets *both* `play_pile` and
   `_playing_card`, so it can no longer detect the debt it guards); R10's
   `test_rng_tripwire` stale watch item.

---

## 7. GATE RESULTS

Run by me; `git archive` export of `c9bc3374` as the control.

| gate | result | verdict |
|---|---|---|
| `py -m pytest test/ -q` (×2) | **3942 passed / 6 xfailed / 2 failed** | ok — 2 = known missing fixture |
| `gap_queue.py counts` | 360 / 339 / 17 / 16, seam live 4 | ok — reproduces |
| `citation_check.py` | 848 records, 10947 citations, **MISSING 49** | ok — pre-existing, confirmed |
| `gap_queue.py cite-check` | 380 citations, 134 files, 0 problems | ok |
| **`audit_status.py`** | **EXIT 2 — 3 invalid records** | **FAIL — regression (HEAD exits 0)** |
| **`gap_queue.py coverage`** | **12 mechanisms / 13 entries missing** | **FAIL — regression (HEAD is 0/0)** |
| `closer.py` round-trip 848/0 | **tool does not exist** | **unverifiable** |

**Suite reconciles exactly.** The two failures are
`test_conformance_floor_state.py`, missing
`RunReplays/Resources/933T39V18D/floor_49/actions.sts2replay` — the known
environment gap, never to be counted or "fixed". That file collects **5** tests,
so `3942 − 3 = 3939` = the ledger's stated number. The ledger is precisely right.
Conformance subset alone: 98 passed / 6 xfailed / 2 failed.

**`citation_check` MISSING 49 is PROVEN pre-existing**, as claimed — the same
tool in a throwaway export of `c9bc3374` gives **10889 citations, the same
MISSING 49**. The branch adds 58 citations and breaks none. (The ledger's "10919"
is stale prose; the file's own header says not to trust prose counts.)

**Staleness debt created and unmentioned:** relic records stale 45 → **254**,
card 22 → **139**, event 1 → **63**, monster 46 → **79**. Expected from an
engine-editing round, but nobody restated it.

---

## RANKED FIX LIST (what would most mislead the next round)

1. **Fold R5** — reconcile `creature_card_cmds` N9/step82/step51/step50/step45 and
   the queue body at :2053; open R5's F9/F10/F12. *(X-1)*
2. **Regenerate `GAP-QUEUE.md`** until `gap_queue.py coverage` returns 0/0. *(X-2)*
3. **Add the missing `issue` field to the three reopened entries** until
   `audit_status.py` exits 0. *(B-1)*
4. **Re-file `creature_card_cmds/guard26` (F-R13d)** as
   `reward/no_upgrade_roll_flag`; restate the seam-live count as **3**. *(B-4/§1)*
5. **Correct `hook_dispatch` steps[45]** — it still says the gate is CLOSED and
   is labelled `live: false`. Reframe F3-R13 as a *reopening*, and claim the
   green-test-as-evidence lesson. *(§1)*
6. **Fix `HookSystem.combat_is_over`'s docstring.** *(X-5)*
7. **Close `relic/pen_nib` guards[2]** (the close landed on the wrong entry) and
   reconcile `power/nostalgia/g8` with the now-closed `power/corruption`.
   *(B-2, B-3)*
8. **Repair D1 and D2**, and record D5/D6/D7 as divergence pins that must flip
   when their gaps close. *(§4)*
9. **Reconcile the ≥11 records resting on the dead `should_allow_hitting`
   backstop, and the `cmds.py:303-309` comment.** *(X-4)*
10. **Correct the four false banner statements**, add a "what this round DID"
    section, and `git rm --cached live2.json`. *(§6)*
