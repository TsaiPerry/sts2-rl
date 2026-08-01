# Round 12 retro — Tier 2 dormant gaps (2026-07-31)

29 tasks, run as concurrent waves of Sonnet implementers in one worktree
(`sts2-rl-tier2`, branch `tier2-gaps`), each with a reviewer and fix loops.

## Result

| | start | end |
|---|---|---|
| gap entries | 626 | 439 |
| mechanisms | 478 | 416 |
| mechanisms with a live entry | 6 | 5 |
| **live entries in seam records** | **1** | **0** |
| suite passed | 3347 | 3766 |

The two suite failures throughout are `test_conformance_floor_state.py`
missing the `RunReplays/.../933T39V18D/floor_49` fixture. **They are an
environment gap and must never be "fixed".**

`damage_pipeline/G2` carried the last live engine verdict solely through the
PowerAmountGiven/Received edge (binding rule 3). Task 18 built that machinery,
so the mechanism dropped to dormant — **dormant, not closed**: 7 of its 9
tracked variants are still uncovered and none was re-verified this round.

## The lessons, in order of how much they cost

### 1. A green suite is not evidence of fidelity here

Two fixes **introduced** divergences and the full suite passed on both.

- **Task 20, exhaust.** The fix raised `ValueError` when a card already in the
  exhaust pile was exhausted again. `CardPileCmd.Add` captures
  `oldPile = card.Pile` (`CardPileCmd.cs:364`) and calls
  `RemoveFromCurrentPile` at `:494-496` **before** `AddInternal` at `:510`, so
  with `oldPile == targetPile == Exhaust` the `Cards.Contains` guard
  (`CardPile.cs:86-89`) tests an already-emptied slot and never fires. C#
  performs a legal no-throw reposition to the bottom. The sim would have
  thrown.
- **Task 18, power modifier phases.** Pass 1 fired both
  `AfterModifyingPowerAmount*` companion events **before** the power was
  registered or stacked, where C# runs `ApplyInternal` (`PowerCmd.cs:135`) and
  `SetAmount` (`:237`) first and dispatches after (`:148-152`, `:238-242`).
  A third facet nobody flagged: C#'s `Apply` wraps its **entire** tail —
  `ApplyInternal` through both companions — inside
  `if (target.CanReceivePowers)` (`:133-158`), so a target failing that
  re-test must get neither event.

Both were invisible to every ported listener, because a dormant mechanism by
definition has nothing that would notice. **Only reading the C# found them.**

**Practice:** when a task fixes a dormant mechanism, the reviewer must re-read
the C# control flow around the change. Running the suite proves only that
nothing already-covered broke.

### 2. The brief can be the bug

The Task 20 brief **instructed** the implementer to raise on a double-exhaust,
citing `AddInternal`'s throw. That was wrong, and the implementer followed it
and defended it in its report.

**Practice:** every review dispatch must say explicitly *"do not defer to the
brief; the C# decides"*, and name the specific claim to re-derive. The Task 20
review did, and caught it.

### 3. "Dormant" is not safer than "live"

Task 30 overturned a dormancy verdict. The record argued dormancy from a census
of two consumers (`pool_card_ids`, `curse_pool_ids`) and missed a third —
`transform_options_in_combat`'s STATUS branch, reached by ported Entropy —
which genuinely leaked four bad cards as transform options for every reachable
Status card, including `frantic_escape`, which The Insatiable really does put
in piles.

**Practice:** a dormancy argument is only as good as its consumer enumeration.
Re-execute it; don't inherit it. Ask "what else reads this flag?" not "does the
recorded consumer still hold?".

### 4. Records are wrong about their reasoning more often than their verdicts

`power_cmd/G3`'s dormancy rested on Unsettling Lamp gating on the **static**
`power_type` — a fact Task 17 had already deleted when it made Lamp sign-aware.
The conclusion (disjoint listeners) survived, but through a clause the record
never mentioned: Lamp is a **given-side** override
(`UnsettlingLamp.cs:106-129`), Ruined Helmet and Artifact are **received-side**
(`RuinedHelmet.cs:32-53`, `ArtifactPower.cs:17-36`). They were never on the same
C# hook; the sim's collapsed chain was the only thing that ever put them in a
registration-order race.

**Practice:** when closing an entry, state which *reasoning* you replaced, not
only which verdict. A future reader relying on dead reasoning draws the wrong
conclusion the moment an adjacent fact changes.

### 5. Verify "already fixed" and "no change needed" hardest

Task 31 found most of its scope already fixed by pre-existing staged work.
That is the shape a task takes when it quietly does nothing, so its reviewer
was asked to confirm the behavior held — it did, verified against
`git show HEAD:sts2_rl/run.py`.

### 6. Close conservatively; narrow instead of closing

Entries deliberately left open this round rather than closed for a better
number: `relic/bing_bong`, `relic/massive_scroll`, `relic/punch_dagger`
(genuine divergences, unreachable); `creature_card_cmds/G8` (**narrowed** — one
of four dispatch sites still unwired, pending the Play-pile work);
`relic/lantern/g1` (**narrowed** — keeps its `AfterModifyingEnergyGain`
clause); `damage_pipeline/G2` (live → dormant, still open).

**The queue went UP by one entry** when a newly discovered live gap was
recorded (`event/the_future_of_potions/g15`). A round that only ever decreases
the count is not measuring honestly.

## Parallel-execution rules that earned their place

Concurrent implementers in a single worktree work, with these constraints:

1. **Disjoint FILE footprints, not just disjoint mechanisms.** `cmds.py` and
   `hooks.py` are the contended files; only one lane may own each. Pair an
   engine lane with content lanes (`cards/`, `potions/`, `relics/`, `events/`).
2. **Implementers never touch `audit/**`.** They propose closes and queue
   annotations in their report; the controller applies them with `closer.py`.
   This is what makes concurrency safe at all.
3. **Forbid index-mutating git**, explicitly and in every dispatch:
   `commit`, `push`, `add`, `stash`, `checkout`, `reset`, `restore`.
4. **Forbid "temporarily revert the fix to see RED, then restore".** One
   implementer used it while another agent was live in the same worktree. Get
   RED by writing the test *before* the fix. (A reviewer that needs to prove a
   pre-fix leak can monkeypatch in-test instead — Task 30's reviewer did.)
5. **Scope every reviewer's diff to the reviewed task's declared paths.** A
   bare `git diff` shows all lanes plus the pre-existing staged index, and a
   reviewer will otherwise report another lane's work as a finding.

## Tooling notes

- `closer.py` must preserve each record's **`ensure_ascii` style** *and*
  **trailing-newline presence** (11 records lack one), or a one-line
  re-verdict rewrites the whole file. Round-trip proof: 848 records, 0
  mismatches.
- `gap_queue.py`'s `local_id` for a hooks-dict entry is the **first token** of
  the key (`OnUse`), not the full key
  (`OnUse (protected override, AttackPotion.cs:21-32)`). A finder must match
  by prefix.
- `GAP-QUEUE.md` is **CRLF**. Inserting LF-only text corrupts line endings;
  normalize after every programmatic edit.
- `git diff --stat` is **unreliable** for isolating one session's work in this
  worktree, because of the large pre-existing staged index.
