# Finishing Tier 1 — the 140 remaining LIVE mechanisms

Paste this whole file as the opening prompt of a fresh session.

---

## Where the work stands

Round 6 (2026-07-29) worked **Tier 1 = every mechanism in `audit/GAP-QUEUE.md`
with a LIVE site** in the queue's own priority order and closed the multi-site
head: **166 entries / 25 mechanisms**. It did **not** finish the tier. Read the
round-6 banner at the top of `audit/GAP-QUEUE.md` first — it lists exactly what
shipped and why.

Measured, and reproducible right now:

```
py -m pytest test/ -q                    2 failed, 3100 passed, 6 xfailed
py audit/tools/harness.py validate       847 record(s), 0 invalid
py audit/tools/audit_status.py           0 invalid, 0 stale
py audit/tools/gap_queue.py counts       809 entries / 643 mechanisms / 140 live
py audit/tools/gap_queue.py cite-check   0 problem(s)
py audit/tools/gap_queue.py coverage     0 missing / 0 unlocatable
py audit/tools/power_census.py slots     0 mis-slotted
```

The 2 failures are environmental — a missing
`RunReplays/RunReplays/Resources/933T39V18D/floor_49/actions.sts2replay`
fixture. **Do not "fix" them.** Treat 3100 passed / those same 2 failures as the
floor.

Trajectory: 1612 → 1160 → 1014 → 975 → **809** entries; 319 → … → 165 → **140**
mechanisms with a live entry.

**Nothing is committed.** 888 files are staged. Perry commits — never run
`git commit`, `push`, `checkout`, `stash`, `reset` or `restore` (CLAUDE.md §4).

---

## The headline finding: this is 8 batches, not 141 individual jobs

The 141 remaining live entries look like a flat tail of single-site findings.
They are not. **55 of them share eight root causes**, and each root cause is one
engine or helper fix that closes its whole cluster at once. Do these first, in
this order — the clusters are listed largest-first and the early ones are
prerequisites for nothing, so they can be taken in any order you like.

### Batch 1 — `HittableEnemies` vs the sim's `is_gone` / `living_enemies` (13)

`card/bash/OnPlay`, `card/break/OnPlay`, `card/fight_me/OnPlay`,
`card/mad_science/OnPlay`, `card/mangle/OnPlay`, `card/omnislice/OnPlay`,
`card/squash/OnPlay`, `card/taunt/OnPlay`, `card/tremble/OnPlay`,
`card/uppercut/OnPlay`, `card/whistle/OnPlay`, `monster/ovicopter/g2`,
`relic/parrying_shield/g1`

`CombatState.HittableEnemies` is not "enemies that are not gone". Read the C#
property, then give the sim one helper with that name and route every site
through it. `relic/shackling_potion`'s already-closed entry
(`power/shackling_potion/g8`) is the worked example.

### Batch 2 — `CanReceivePowers` / `ShouldAllowHitting` (10)

`card/bash/OnPlay`, `card/break/OnPlay`, `card/fight_me/OnPlay`,
`card/mad_science/OnPlay`, `card/mangle/OnPlay`, `card/squash/OnPlay`,
`card/taunt/OnPlay`, `card/tremble/OnPlay`, `card/uppercut/OnPlay`,
`monster/parafright/g1`

Overlaps Batch 1 heavily — nine cards appear in both, which is why they should
be done together. `PowerCmd.apply` already has the backstop
(`power/_should_allow_hitting`); what is missing is the per-card AoE routing.

### Batch 3 — the downgrade rebuild loses printed state (9)

`card/aggression/OnUpgrade`, `card/apparition/OnUpgrade`,
`card/hello_world/OnUpgrade`, `card/juggling/OnUpgrade`,
`card/maul/AfterDowngraded`, `card/rampage/AfterDowngraded`,
`card/thrash/AfterDowngraded`, `card/wish/OnUpgrade`,
`creature_card_cmds/step52`

`Card.downgrade` (`cards/base.py`) rebuilds printed state by zeroing
`upgrade_level`, re-running `_init_vars` and re-applying upgrades. C#'s
`CardModel.DowngradeInternal` re-derives from the canonical model and then runs
`AfterDowngraded`. **`creature_card_cmds/step52` is the seam entry that owns the
machinery** — fix it there and the eight card entries follow by binding rule 3.

### Batch 4 — "the stub's premise is false" (12)

`card/guilty/AfterCombatEnd`, `card/lantern_key/ModifyUnknownMapPointRoomTypes`,
`relic/dollys_mirror/g1`, `relic/dragon_fruit/g1`,
`relic/fake_venerable_tea_set/g1`, `relic/gnarled_hammer/AfterObtained`,
`relic/gnarled_hammer/g1`, `relic/juzu_bracelet/ModifyUnknownMapPointRoomTypes`,
`relic/kifuda/g1`, `relic/venerable_tea_set/g1`, `relic/white_star/g1`,
`relic/white_star/g3`

Every one is a port that does nothing and justifies it with a claim about the
sim ("no gold system", "no enchantments", "no run-level AfterObtained
dispatch"). **Check the claim before the code** — PROMPT.md bug class 12. In
round 6 every such claim checked was false, and two of them were false about the
*source*, not the sim (see Traps below).

### Batch 5 — `TakeRandom` is `UnstableShuffle(rng).Take(n)` (5)

`card/anointed/OnPlay`, `card/discovery/OnPlay`, `card/distraction/OnPlay`,
`card/splash/OnPlay`, `relic/crossbow/AfterSideTurnStart`

`IEnumerableExtensions.cs:17-20`. Two defects per site: the wrong stream AND the
wrong algorithm (`random.sample` is not a full Fisher-Yates followed by a
slice — the draw COUNT differs, so the stream lands in a different place even
when the cards agree). `power/hello_world/g3` is the closed worked example;
copy its shape.

### Batch 6 — `CardModel.CreateClone` vs rebuild-from-id (5)

`card/anger/OnPlay`, `card/dual_wield/OnPlay`, `relic/burning_sticks/g2`,
`relic/dollys_mirror/g1`, `relic/music_box/g1`

`cards/base.py`'s `create_clone` already carries the enchantment, the affliction
and (as of round 6) `_cost_this_combat`. Work out what else `DeepCloneFields`
copies that a rebuild-from-class drops, and add it there once.

### Batch 7 — the potion procure hooks (6)

`relic/delicate_frond/BeforeCombatStart`, `relic/delicate_frond/g2`,
`relic/delicate_frond/g3`, `relic/petrified_toad/g1`,
`relic/petrified_toad/g2`, `relic/sozu/g1`

`PotionCmd.TryToProcure` consults `Hook.ShouldProcurePotion` and fires
`Hook.AfterPotionProcured` on success. The sim has TWO procure paths and only
the out-of-combat one consults the gate. One helper, six entries.

### Batch 8 — `CardCmd.Upgrade` skips a non-upgradable card (5)

`card/jackpot/OnPlay`, `relic/astrolabe/g1`, `relic/bone_tea/g1`,
`relic/neows_talisman/g1`, `relic/paels_tooth/g1`

`CardCmd.Upgrade` is a no-op when `IsUpgradable` is false; the sim's bare
`card.upgrade()` pushes an already-maxed card past its level.

### The residue — ~85 entries with no shared cause

`py audit/tools/gap_queue.py mechanisms | grep LIVE` after the batches. They are
single-unit findings: read the record, read the C#, write the failing test, fix,
close. Expect ~60 relic and ~20 card/power/event/monster.

Two seam entries sit in the tail and are worth doing early because other records
inherit them: `creature_card_cmds/step52` (Batch 3) and
`creature_card_cmds/step38a` (the rest-site heal verb).

---

## Non-negotiables

1. **The decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2` is the
   source of truth** — not the queue's paraphrase, not the record's prose, not
   the sim's docstrings. Use NON-ASCENSION values.
2. **Test-driven.** Failing test first, watch it fail *for the right reason*,
   then fix. A test that passes before your change is not a pin.
3. **Surgical.** Every changed line traces to a named queue entry.
4. **Stage freely, commit never.**
5. **"Original means game source."** When a legacy test encodes the old sim
   semantics, UPDATE THE TEST and say in a comment why it moved. Round 6 moved
   four; each says what it used to assert and which entry moved it.
6. **A verdict flips only on evidence you gathered from today's code.** Not
   because a plan says it was fixed, not because a test name sounds right.
7. **Never round-trip UTF-8 source through PowerShell `Get-Content` /
   `Set-Content`** — a prior session corrupted a test file that way. Use Python
   or the file tools.
8. Do not use subagents, workflows or deep-research unless Perry asks.

---

## The three traps, which recur EVERY round

**(a) Entries go stale.** Round 6 found two more that were closed in code or
blocked on something already closed — `relic/sai/AfterSideTurnStart` said in its
own text that it was waiting on `turn_structure/G12`, which closed in round 5.
Five rounds running. **Read the code before believing the entry.** When an entry
turns out to be stale, close it with the enumeration you did, not with a
one-liner.

**(b) Tooling defects hide in the probes**, and unit work finds them where tool
review never does. Round 6 found three in `audit/tools/event_probes.py` alone:
one expected the wrong C# value (it read the damage step and stopped before the
clamp), one counted a call that takes no RNG draw as a draw, one demanded a
literal string so a site routed to the *correct* named stream still read
off-stream. **If a probe disagrees with your reading of the C#, suspect the
probe.** Fix it with the reasoning inline and say so in the record.

**(c) A port's stated premise can be wrong about the SOURCE.** Distinguished
Cape blamed its −9 Max HP on the Vakuu option's `ThatDecreasesMaxHp(9m)`; that
method is `ThatWillKillPlayerIf(p => p.MaxHp <= value)`
(`EventOption.cs:194-197`) — a UI flag that reddens a lethal option and applies
no HP at all. Batch 4 is twelve more chances for this.

---

## Liveness is a claim you can check

Some entries are labelled LIVE on reasoning rather than on an enumeration. When
you doubt one, **enumerate the implementers** and record what you find.
`creature_card_cmds/step59` was LIVE; listing the eight `AfterCardChangedPiles`
implementers showed four filter to `PileType.Deck` (already shimmed), one sets a
music parameter, two are a run Modifier and a test mock, and one is unported.
It is now `live: false` with the enumeration written into the entry — the
verdict stayed `gap`, because the machinery really is absent.

That is the honest move when a gap is real but unobservable. **Do not
re-verdict a gap to `faithful` to get it out of Tier 1.**

---

## Closing records: the tool, and the two things that will bite you

Record edits go through a scratchpad helper. Recreate it verbatim — it encodes
two discoveries that cost real time:

```python
"""Round N closer: re-verdict audit record entries by (record, local_id)."""
import json, pathlib, re, subprocess

ROOT = pathlib.Path(r"c:\Users\Perry\Desktop\sts2-rl\audit\records")
VERDICTS = ("faithful", "waiver", "deliberate-divergence", "gap")

# TRAP 1: 27 of the 847 records were written with ensure_ascii=True and the rest
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

**Before the first write, prove the round-trip is byte-identical across all 847
records.** Round 6 did, and that is how the `ensure_ascii` split was found.

A closing note must say **what the code does now, with a C# citation and a sim
citation, and what it does NOT close**. Round 6's notes are the model. Keep the
`The text it replaced read: …` tail — the record's history is the point.

---

## Per-batch loop

1. `py audit/tools/gap_queue.py mechanisms | grep LIVE` — pick the batch.
2. Read every entry in it (`closer.gaps("<mechanism>")`) **and** the C#.
3. Write the failing test(s). Watch them fail for the right reason.
4. Fix. Re-run the touching test files.
5. Full suite (`--ignore=test/test_conformance_floor_state.py` for a ~4½-minute
   run; the full thing is ~5¼). Zero regressions before you close anything.
6. Close the records with `close_many`.
7. `harness.py validate` + `gap_queue.py counts`.

Every 2–3 batches: full gate sweep (`validate`, `rehash --all`, `audit_status`,
`counts`, `cite-check`, `coverage`, `power_census slots`), then `git add -A`.

**If you add new content** — round 6 added the Royally Approved enchantment —
`audit_status` will report it unaudited. Write its record and `rehash` it.
`card/sweep` is already unaudited and is NOT yours; leave it.

---

## Finishing

When `gap_queue.py counts` reports **0 mechanisms with a live entry**, Tier 1 is
done. Write the round banner at the top of `audit/GAP-QUEUE.md` in the
established shape: the table of what shipped, the before/after numbers, the
stale-not-open findings, the tooling defects, and an explicit **"what this round
did NOT do"**. Then update `MEMORY.md`.

Known to remain after Tier 1, and deliberately out of scope here:

- **§C Tier 2** (dormant gaps) and **§D Tier 3** (the long tail).
- **`power_cmd/G2`** — the sim's Unsettling Lamp lacks C#'s `amount <= 0` early
  bail, which is what blocks wiring the
  `ModifyPowerAmountGiven`/`ModifyPowerAmountReceived` chains into the decrement
  path (`power_cmd/G4`, and the ten unimplemented `AfterModifying*` variants
  under `damage_pipeline/G2`).
- **`card/sweep`** has no audit record.
