# Round 13 implementer protocol (read fully before touching anything)

Campaign: tier-2 dormant-gap fidelity campaign on the sts2-rl simulator,
round 13. You are one lane of a concurrent wave: **other agents are working
in the same worktree at the same time on different files.**

## Ground truth

- The decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2` **is the
  specification**. Non-ascension values. Cite `file:line` for every claim
  you make about it.
- Your brief can be wrong. **Do not defer to the brief; the C# decides.**
  If the brief's claim contradicts the C#, follow the C# and flag the
  contradiction prominently in your report.
- A green suite is NOT evidence of fidelity: a dormant mechanism has no
  listener that would notice a divergence your change introduces. Re-read
  the C# control flow around every change you make.

## Workspace rules

- Work ONLY in `c:\Users\Perry\Desktop\sts2-rl-tier2`.
- Touch ONLY files inside your declared footprint (in your brief). If a fix
  genuinely requires a file outside it, do NOT edit that file — mark that
  item BLOCKED-ON-FOOTPRINT in your report with what you would have done.
- Use the `py` launcher; there is no `python` on PATH.
- FORBIDDEN git operations: `commit`, `push`, `add`, `stash`, `checkout`,
  `reset`, `restore` — anything that mutates the index or moves files.
  Read-only git (`diff`, `log`, `show`, `status`) is fine.
- FORBIDDEN: "temporarily revert the fix to see RED, then restore". Get RED
  by writing the test BEFORE the fix. Another agent is live in this tree.
- NEVER edit `audit/records/**` or `audit/GAP-QUEUE.md`. You propose record
  closes and queue annotations in your report; the controller applies them.

## Method

- Test-driven: write the pinning test first, see it RED, then fix, see it
  GREEN. For a dormancy verdict (no fix), execution still applies: probe or
  test that demonstrates the enumeration's claims where feasible.
- Dormancy closes: replace silence with an **enumeration naming every
  consumer you checked** (grep patterns + files inspected). Ask "what else
  reads this?", not "does the recorded consumer still hold?" — a round-12
  dormancy verdict was overturned by a third consumer nobody had listed.
- Stale closes ("already fixed"): verify against the actual committed tree
  (`git show HEAD:<file>` or read the file), not memory or prose.
- Close conservatively: when any site of a mechanism remains unhandled,
  propose NARROWING (which sites close, which stay open) instead of closing.
- Tests to run: every test file you touched plus the tests covering your
  changed code. Report the exact command and the pass/fail counts. Do NOT
  run the full suite (the controller runs it per wave). The 2 failures in
  `test/test_conformance_floor_state.py` are a known environment gap
  (missing 933T floor_49 fixture) — never "fix" them, never count them.

## Report contract

Write your full report to the report path named in your brief. It must
contain:

1. Per queue entry: verdict (FIXED / DORMANT-ENUMERATED / STALE-ALREADY-FIXED /
   NARROWED / BLOCKED-ON-FOOTPRINT / LEFT-OPEN) with the C# citations and,
   for fixes, the sim diff summary + test names.
2. **Record-close proposals**: for each entry to close, give the record file
   (e.g. `power/foo` or `seam/hook_dispatch`), the entry key (`gN`/`stepN`/
   hook name), the proposed verdict, and a close note that states **which
   reasoning you replaced**, not only which verdict.
3. Queue-annotation proposals: one short paragraph per mechanism for
   GAP-QUEUE.md, in its established terse style.
4. Tests: files added/changed, commands run, counts.
5. Anything you found that is NOT in your brief (new gaps, stale records,
   wrong citations) — findings outrank fixes in this campaign.

Your final message must be only: status (DONE / DONE_WITH_CONCERNS /
NEEDS_CONTEXT / BLOCKED), the report path, a one-line test summary, and
concerns if any. Everything else goes in the report file.
