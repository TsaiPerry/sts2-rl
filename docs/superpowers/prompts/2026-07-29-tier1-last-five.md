# Finishing Tier 1 — the last 5 LIVE mechanisms

> **SUPERSEDED 2026-07-29.** This prompt was executed in the same session that
> wrote it. All five mechanisms are closed and Tier 1 has ZERO live entries — see
> the round-8 banner at the top of `audit/GAP-QUEUE.md`. Kept for its record of
> what each of the five turned out to be, and because its per-unit loop,
> non-negotiables, traps and closer helper are the template for the Tier 2
> campaign.

Paste this whole file as the opening prompt of a fresh session.

---

## Where the work stands

Round 7 (2026-07-29) worked the Tier 1 tail — every mechanism in
`audit/GAP-QUEUE.md` with a LIVE site — and closed **137 entries / 136
mechanisms**, taking the tier from 140 live mechanisms to **5**. Read the
round-7 banner at the top of `audit/GAP-QUEUE.md` first; it lists what shipped,
the nine stale findings, and these five by name.

Measured, and reproducible right now:

```
py -m pytest test/ -q                    2 failed, 3281 passed, 6 xfailed
py audit/tools/harness.py validate       848 record(s), 0 invalid
py audit/tools/audit_status.py           0 invalid, 0 stale; unaudited: card 1
py audit/tools/gap_queue.py counts       672 entries / 507 mechanisms / 5 live
py audit/tools/gap_queue.py cite-check   0 problem(s)
py audit/tools/gap_queue.py coverage     0 missing / 0 unlocatable
py audit/tools/power_census.py slots     0 mis-slotted
```

The 2 failures are environmental — a missing
`RunReplays/RunReplays/Resources/933T39V18D/floor_49/actions.sts2replay`
fixture. **Do not "fix" them.** The one unaudited record is `card/sweep`, which
is **not yours** — leave it.

Trajectory: 1612 → 1160 → 1014 → 975 → 809 → **672** entries; 319 → … → 165 →
140 → **5** mechanisms with a live entry.

**Nothing is committed.** 1001 files are staged. Perry commits — never run
`git commit`, `push`, `checkout`, `stash`, `reset` or `restore` (CLAUDE.md §4).

---

## The five, and what today's code actually says about them

This is the tail, so there is no batching left: five independent jobs. But the
work is **not** five equal units — I read each one's code while writing this
prompt, and **three of the five look STALE or much smaller than their entry
claims.** Verify before building. Numbers below are what I saw on 2026-07-29;
re-derive them.

### 1. `relic/wongos_mystery_ticket/TryModifyRewards` — probably STALE

The entry says the divergence is that "`rewards.py:440-441` returns before the
loop on the final act's boss, so a ripe ticket silently pays nothing there
while C# pays its three".

Those line numbers no longer point at anything, and the final-act branch is now
`rewards.py`'s `generate_combat_rewards` at the `room_type == RoomType.BOSS and
run.is_final_act` guard — which **calls `apply_reward_modifiers(run, rewards)`
before returning**, and `apply_reward_modifiers` IS the TryModifyRewards +
TryModifyRewardsLate dispatch loop. Its comment already argues the exact point
the entry wanted (`AmethystAubergine.cs:33-35`'s explicit final-act guard would
be dead code if the hooks did not fire there).

**Check first:** drive a ripe ticket (`GaveRelic` set, `5 - CombatsFinished >
0`) into a final-act boss screen and count the relics. If it pays three, this
is a one-note closure with an executed witness. The rollup carries G1, N2, N5,
N6, N7, N10 and N13 — the entry records the other six as already matching, so
confirm that too rather than assuming it.

### 2. `relic/lizard_tail/g3` — the stated blocker looks stale

The residue is real and small: `relics/lizard_tail.py`'s `should_die_late`
mutates `self._used = True` and `self._heal_pending = True` **inside the
predicate**, where `LizardTail.ShouldDieLate` (LizardTail.cs:40-51) is pure and
the charge is spent in `AfterPreventingDeath` (:56). A `should_die` call that is
only a query therefore burns the relic.

But the entry's FIX-ORDERING CONSTRAINT — "moving the heal to
`after_preventing_death` … also means `DamageCmd.deal` must pass a preventer
list on every path — `CreatureCmd.kill` currently does not" — reads stale twice
over:

* `cmds._resolve_death` already builds `preventer: list = []`, passes it to
  `hooks.should_die(target, preventer)` and calls
  `hooks.after_preventing_death(preventer, target)` on the else-arm;
  `CreatureCmd.kill` routes through `_resolve_death`.
* `lizard_tail.py` already implements `after_preventing_death` and heals there.
* The entry's named LIVE witness was `cards/breakthrough.py`'s
  `if p.hp <= 0 and ctx.hooks.should_die(p)` — **round 7 deleted that**, because
  `card/breakthrough/OnPlay` now routes the self-damage through `DamageCmd.deal`.

**Enumerate every `hooks.should_die(` caller** (I count exactly one in
`sts2_rl/`: `cmds.py`'s `_resolve_death`, plus an unrelated run-level
`should_die` callable in `run.py`). If `_resolve_death` is the only caller and
it always continues to the prevention path, then the mutation-in-a-predicate is
currently unobservable — which is a `live: false` relabel with the enumeration
recorded, **not** a re-verdict to `faithful` (see "Liveness is a claim you can
check"). Moving the assignment to `after_preventing_death` anyway is correct and
cheap; do it, and say in the note which of the two dispositions the enumeration
supports.

### 3. `power/burrowed/AfterBlockBroken` — two halves, one of them small

`BurrowedPower.cs:24-36` is, in order: `tunneler.GetStunned()`, then
`CreatureCmd.Stun(base.Owner, tunneler.StillDizzyMove, "BITE_MOVE")`, then
`PowerCmd.Remove<BurrowedPower>(base.Owner)`. `powers.py`'s `on_block_broken`
calls `self.owner.get_stunned()`, then `self._expire()`, then zeroes the block.

* **ORDER (the live half).** C# stuns FIRST and removes the power SECOND, and it
  is `AfterRemoved` that dumps the block (`LoseBlock(999999999)`), so the stun
  happens while the block is still there and the sim's after it is gone.
* **The follow-up state.** C#'s `Stun` names both the state handler
  (`tunneler.StillDizzyMove`) and the resume move id (`"BITE_MOVE"`). Note what
  the source actually declares: `Tunneler.cs:75` builds ONE state whose id is
  `"DIZZY_MOVE"` and whose handler is `StillDizzyMove`
  (`Tunneler.cs:134`), and `Tunneler.cs:176` refuses transitions out of
  `"DIZZY_MOVE"`. The sim's `monsters/hive/tunneler.py` has a `DIZZY_MOVE`
  state with `dizzy.follow_up = bite`, i.e. it already encodes "resume at BITE".
  So decide by reading, not by the entry's prose: is anything actually missing
  beyond routing this through `CreatureCmd.stun` (which takes a
  `next_move_key`) instead of the monster's own `get_stunned`? The entry flags
  it as "the same shape as FlutterPower's", where the follow-up-state re-roll
  turned out to be a live wrong-stream gap — so check whether `force_current_state`
  takes a draw that `CreatureCmd.stun` would not.

### 4. `enchantment/EG2` (`enchantment/perfect_fit`) — a real engine job

The residual is a listener-ORDER key, and it is the deepest of the five.

`PerfectFit.cs:10-16` overrides **`ModifyShuffleOrder`**, which is not a
notification: `Hook.ModifyShuffleOrder(combatState, player, cards,
isInitialShuffle)` (`Hook.cs:2004-2010`) hands each listener the mutable list
mid-shuffle, and Perfect Fit does `Remove` + `Insert(0)`. It has exactly two
dispatch sites — `CardPileCmd.cs:877` (the mid-combat shuffle,
`isInitialShuffle: false`) and `CardPile.cs:73` (the combat-start
randomization, `isInitialShuffle: true`) — and Perfect Fit early-returns on the
initial one.

The sim maps it onto **`on_shuffle` = `AfterShuffle`**, a different hook, and
orders listeners by `HookSystem._ordered()`'s registration-based key. C#
re-enumerates `AllPiles` per dispatch (`CombatState.cs:410-467`, enchantment
added at `:462-465`) and `CardPileCmd.Shuffle` fires the hook while the discard
pile still holds all its cards — so the instance sitting LATER IN THE DISCARD
fires last and ends on top, where the sim's registration-latest listener (always
a mid-combat copy) wins. The entry's executed witness is the natural Anger case:
C#'s discard is `[clone, original]` and the ORIGINAL is drawn first; the sim
gives `[original, clone]` and draws the CLONE.

The fix shape is a real `modify_shuffle_order` dispatcher called from inside
`PlayerCombatState._shuffle_draw_pile`, carrying `is_initial_shuffle`, with the
listeners for THAT hook ordered by pile position. Two cautions: this is
`hook_dispatch`'s cross-listener-order machinery, so **cite rather than
re-derive** whatever `audit/records/seam/hook_dispatch.json` already verdicts;
and the sim appends a played card to the discard BEFORE `OnPlay` where C# holds
it in `PileType.Play`, which is what makes its discard order differ in the Anger
case — round 7's unconditional `_playing_card` hold-back is the machinery to
reuse there.

### 5. `event/war_historian_repy/g1` — the largest, and the cleanest

`Hook.ModifyNextEvent` **does not exist in the sim at all**. Both halves of the
Lantern Key's deferred port are wanted:

* `LanternKey.cs:21-27` — `ModifyUnknownMapPointRoomTypes` returns
  `{ RoomType.Event }` when `CurrentActIndex == 2`, narrowing every "?" node.
  The sim ALREADY dispatches this hook over `[*self.relics, *self.deck]`
  (`RunState._map_listeners`, consumed in the unknown-map-point pass), and
  `relics/golden_compass.py` is a working implementer — so this is an override
  on `LanternKeyCard`, nothing more.
* `LanternKey.cs:29-36` — `ModifyNextEvent` returns
  `ModelDb.Event<WarHistorianRepy>()` for that act. The dispatcher is
  `Hook.cs:1830-1836` and its ONE call site is `ActModel.PullNextEvent`
  (`ActModel.cs:437-443`): `EnsureNextEventIsValid`, then
  `Hook.ModifyNextEvent`, then **`AddVisitedEvent(eventModel)` on the MODIFIED
  event**. The sim's counterpart is the `RoomType.EVENT` arm of
  `RunState`'s room resolution (`ensure_next_event_is_valid` →
  `next_event_id` → `make_event` → `visited_event_ids.add`), so the hook goes
  between the pull and the add, and the visited-set bookkeeping must follow the
  modified event — that interacts with [[ancient-node-is-an-event-room]].

`IsAllowed => false` on the event is not an obstacle: the injection is the whole
point, and the ported event and the ported card both already exist
(`events/the_lantern_key.py` hands the card over as a reward extra). Under rule 1
an unported C# side is a gap, never a waiver.

---

## Non-negotiables

1. **The decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2` is the
   source of truth** — not the queue's paraphrase, not the record's prose, not
   the sim's docstrings. Use NON-ASCENSION values.
2. **Test-driven.** Failing test first, watch it fail *for the right reason*,
   then fix. A test that passes before your change is not a pin. If you apply a
   fix before running the test, prove the pin is load-bearing by reverting the
   fix in a scratch script and showing both numbers — round 7 had to do this
   twice.
3. **Surgical.** Every changed line traces to a named queue entry. When a fix
   would spill into another record's territory, stop at the boundary and say so
   in the note — round 7 backed a `ModifyGeneratedMapLate` change out for
   exactly this reason and fixed Fur Coat a narrower way.
4. **Stage freely, commit never.**
5. **"Original means game source."** When a legacy test encodes the old sim
   semantics, UPDATE THE TEST and say in a comment why it moved. Round 7 moved
   thirteen; each says what it used to assert and which entry moved it.
6. **A verdict flips only on evidence you gathered from today's code.**
7. **Never round-trip UTF-8 source through PowerShell `Get-Content` /
   `Set-Content`** — a prior session corrupted a test file that way. Use Python
   or the file tools. Bash heredocs are also flaky here: prefer writing a
   scratchpad `.py` and running it with `py`.
8. Do not use subagents, workflows or deep-research unless Perry asks.

---

## The three traps, which recur EVERY round

**(a) Entries go stale.** Round 7 found **nine** — the largest crop in six
rounds — and three of the five below already look stale to me. The recurring
shape: an entry blames a `should_die` override that no longer exists and never
existed in C#, or cites line numbers that have moved. **Re-execute the entry's
own witness before believing it.** When one turns out stale, close it with the
enumeration you did, not a one-liner.

**(b) Tooling defects hide in the probes**, and unit work finds them where tool
review never does. **If a probe disagrees with your reading of the C#, suspect
the probe.** Fix it with the reasoning inline and say so in the record.

**(c) A port's stated premise can be wrong about the SOURCE.** Round 7's Batch 4
was twelve ports that did nothing and justified it with a false claim about the
sim; two were false about the source instead.

**(d) — new, from round 7.** *Executing a record's own claims finds defects that
reading does not.* Writing the Adroit record's four-verb COPY guard crashed the
sim (`create_clone` nulled a back-reference the game derives from `_owner`), and
routing Havoc through the real `AutoPlayFromDrawPile` exposed an infinite
recursion. Both were found by running the sentence I was about to write down.
When you claim a behaviour in a note, run it.

---

## Liveness is a claim you can check

Some entries are labelled LIVE on reasoning rather than on an enumeration. When
you doubt one, **enumerate the implementers/callers and record what you find.**
Three entries now sit at `live: false` with the verdict kept `gap`:
`creature_card_cmds/step59` (round 6), `power/improvement/g1` and
`relic/fake_strike_dummy/g4` (round 7 — the additive-chain ordering question at
a site whose listener returns a CONSTANT, which rule 3 does not force to stay
live, because rule 3 binds the VERDICT and liveness is a per-site claim).

That is the honest move when a gap is real but unobservable. **Do not re-verdict
a gap to `faithful` to get it out of Tier 1.** `relic/lizard_tail/g3` is the
candidate here.

---

## Closing records: the tool, and the two things that will bite you

Record edits go through a scratchpad helper. Recreate it verbatim — it encodes
two discoveries that cost real time:

```python
"""Round N closer: re-verdict audit record entries by (record, local_id)."""
import json, pathlib, re, subprocess

ROOT = pathlib.Path(r"c:\Users\Perry\Desktop\sts2-rl\audit\records")
VERDICTS = ("faithful", "waiver", "deliberate-divergence", "gap")

# TRAP 1: 27 of the records were written with ensure_ascii=True and the rest
# with False. Preserve each file's own style or a one-line re-verdict rewrites
# every line of the file.
_ASCII_MODE = {}

def _dump(rec, ascii_mode):
    return ((json.dumps(rec, indent=2, ensure_ascii=ascii_mode) + "\n")
            .replace("\n", "\r\n").encode("utf-8"))

def load(rel):
    p = ROOT / (rel if rel.endswith(".json") else rel + ".json")
    raw = p.read_bytes()
    rec = json.loads(raw.decode("utf-8"))
    _ASCII_MODE[p] = _dump(rec, True) == raw
    return p, rec

def _entries(rec):
    out = []
    for v in rec.values():
        if isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            out += list(v.values())
        elif isinstance(v, list) and v and all(
                isinstance(x, dict) and "verdict" in x for x in v):
            out += v
    return out

def save(p, rec):
    rec["verdict"] = max((e["verdict"] for e in _entries(rec) if "verdict" in e),
                         key=VERDICTS.index, default="faithful")
    p.write_bytes(_dump(rec, _ASCII_MODE.get(p, False)))
    return rec["verdict"]

# TRAP 2: gap_queue derives local_id four different ways. Verbatim from
# audit/tools/gap_queue.py:668-669 and :693.
_ID_STEP  = re.compile(r"^\s*(\d+(?:\.\d+)?[a-z]?)[.:]?\s+")
_ID_GUARD = re.compile(r"^\s*([GN]\d+)\b")
_ID_TAG   = re.compile(r"^\s*((?:EV|EG|BR)-?[A-Z]?\d+[a-z]?)\b")

def find(rec, local_id):
    for key, rx, pre in (("guards", _ID_TAG, ""), ("guards", _ID_GUARD, ""),
                         ("steps", _ID_STEP, "step")):
        for e in rec.get(key) or []:
            m = rx.match(e.get("what", "") or "")
            if m and pre + m.group(1) == local_id:
                return e
    for key in ("guards", "steps"):
        seq = rec.get(key) or []
        prefix = "g" if key == "guards" else "step"
        if local_id.startswith(prefix):
            tail = local_id[len(prefix):]
            if tail.isdigit() and 1 <= int(tail) <= len(seq):
                return seq[int(tail) - 1]
    if local_id in (rec.get("hooks") or {}):
        return rec["hooks"][local_id]
    raise KeyError(local_id)

def close(entry, note, stamp="Closed 2026-07-XX (round N):"):
    entry["verdict"] = "faithful"
    entry.pop("live", None)
    old = entry.pop("issue", None) or entry.get("rationale") or ""
    entry["issue"] = f"{stamp} {note}  The text it replaced read: {old}"
    entry.pop("rationale", None)

def close_many(pairs, note, stamp="Closed 2026-07-XX (round N):"):
    by_record = {}
    for rel, lid in pairs:
        by_record.setdefault(rel, []).append(lid)
    for rel, lids in sorted(by_record.items()):
        p, rec = load(rel)
        for lid in lids:
            close(find(rec, lid), note, stamp)
        save(p, rec)

def gaps(mechanism=None):
    repo = r"c:\Users\Perry\Desktop\sts2-rl"
    out = subprocess.run(["py", repo + r"\audit\tools\gap_queue.py", "json"],
                         capture_output=True, text=True, cwd=repo).stdout
    d = json.loads(out)
    return [e for e in d if mechanism is None or e["mechanism"] == mechanism]

def pairs(mechanism):
    # gap_queue reports a seam record as the bare seam name; the file is under seam/.
    return [(e["record"] if "/" in e["record"] else "seam/" + e["record"],
             e["local_id"]) for e in gaps(mechanism)]
```

**Before the first write, prove the round-trip is byte-identical across all 848
records.** Two further gotchas round 7 hit: `close_many` is NOT idempotent —
running it twice nests the `The text it replaced read:` tail, so if you re-run a
close script, collapse the duplicate stamp afterwards. And a note written before
the fix is finalized can end up describing a fix you then changed; re-read your
own closing notes against the final diff.

A closing note must say **what the code does now, with a C# citation and a sim
citation, and what it does NOT close**. Round 7's notes are the model. Keep the
`The text it replaced read: …` tail — the record's history is the point.

---

## Per-unit loop

1. `py audit/tools/gap_queue.py mechanisms | grep LIVE` — pick one of the five.
2. Read the entry (`closer.gaps("<mechanism>")`) **and** the C# **and** today's
   sim code. Expect the entry to be behind the code.
3. Write the failing test(s). Watch them fail for the right reason.
4. Fix. Re-run the touching test files.
5. Full suite (`--ignore=test/test_conformance_floor_state.py` for a ~6-minute
   run; the full thing is ~6¼). Zero regressions before you close anything —
   and when a legacy test moves, move it per non-negotiable 5.
6. Close the record with `close_many`.
7. `harness.py validate` + `gap_queue.py counts`.

Every 2–3 units: full gate sweep (`validate`, `rehash --all`, `audit_status`,
`counts`, `cite-check`, `coverage`, `power_census slots`), then `git add -A`.

**If you add new content**, `audit_status` will report it unaudited. Write its
record and `rehash` it — round 7 added the Adroit enchantment and its record.
`card/sweep` is already unaudited and is NOT yours.

---

## Finishing

When `gap_queue.py counts` reports **0 mechanisms with a live entry, Tier 1 is
done** — the first time that has been true. Write the round banner at the top of
`audit/GAP-QUEUE.md` in the established shape: the table of what shipped, the
before/after numbers, the stale-not-open findings, the tooling defects, and an
explicit **"what this round did NOT do"**. Say plainly in the banner that Tier 1
is closed and what the next tier is. Then update `MEMORY.md`.

If one of the five turns out to need machinery you cannot land safely — the
`ModifyShuffleOrder` ordering key is the likeliest — **finish the other four in
full, close them, and say exactly what is left and why.** Do not half-build it
to reach zero.

Known to remain after Tier 1, and deliberately out of scope here:

- **§C Tier 2** (dormant gaps) and **§D Tier 3** (the long tail). This is the
  natural next campaign, and the 443 dormant-labelled entries are where it
  starts.
- **`power_cmd/G2`** — the sim's Unsettling Lamp lacks C#'s `amount <= 0` early
  bail, which is what blocks wiring the
  `ModifyPowerAmountGiven`/`ModifyPowerAmountReceived` chains into the decrement
  path (`power_cmd/G4`, and the ten unimplemented `AfterModifying*` variants
  under `damage_pipeline/G2`).
- **`Hook.AfterModifyingCardPlayCount`** — no sim dispatcher at ANY site,
  including the normal play path; recorded as NOT CLOSED on
  `card/drum_of_battle/AfterCardExhausted`.
- **`card/sweep`** has no audit record.
- **`card/spoils_map` vs `Hook.ModifyGeneratedMapLate`** — the sim dispatches a
  Late map pass whose only game caller is the save-load branch
  (`RunManager.cs:740`), because Spoils Map folds its Treasure-coord recording
  into that hook and needs it on a fresh generation. Round 7 documented the
  mismatch at the dispatch site in `RunState._generate_map` and left the
  reconciliation to the card stream. It is a live-looking gap with no entry yet.
