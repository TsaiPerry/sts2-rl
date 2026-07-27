# Relic content audit — batch 11 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b11` (worktree `sts2-rl-relic-b11`,
based on `audit-relic` @ `0cad15d3`)
**Batch:** the Pael shrine cluster (`paels_blood` … `paels_wing`) plus
`pandoras_box`, `pantograph`, `paper_phrog`, `parrying_shield`, `pear`.
**Probes:** `audit/tools/relic_probes_b11.py` (15 probes, all re-runnable;
`py audit/tools/relic_probes_b11.py` runs them all).

`py audit/tools/harness.py validate` → **141 records, 0 invalid**.
`py audit/tools/citation_check.py audit/records/relic` → **136 records, 1653 citations,
MISSING 0, OUT-OF-RANGE 0**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 136 · invalid 0 ·
stale 0 · gaps 101 · unaudited 122`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; no engine
code was touched.

---

## The 15 units

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `paels_eye` | **gap** | 8 | 8 |
| `paels_legion` | **gap** | 11 | 8 |
| `paels_tears` | **gap** | 4 | 6 |
| `paels_tooth` | **gap** | 7 | 6 |
| `paels_wing` | **gap** | 5 | 5 |
| `paper_phrog` | **gap** | 2 | 6 |
| `parrying_shield` | **gap** | 2 | 7 |
| `pear` | deliberate-divergence | 4 | 3 |
| `paels_claw` | waiver | 2 | 5 |
| `paels_flesh` | waiver | 8 | 4 |
| `paels_growth` | waiver | 3 | 5 |
| `pandoras_box` | waiver | 3 | 5 |
| `pantograph` | waiver | 3 | 4 |
| `paels_blood` | faithful | 2 | 3 |
| `paels_horn` | faithful | 2 | 4 |

7 of 15 roll up to `gap` (47%, below the pilot's 69%). Obtainability was proved
by execution for all 15 (`relic_probes_b11.py pool`): 10 Pael-shrine Ancients,
`pandoras_box` from the Darv shrine, and 4 Uncommons in the transcribed grab bag.
**No roster mis-resolution** — all 15 matched a C# file on the first try and
`audit/tools/name_overrides.json` needs no additions.

---

## LIVE gaps (10), each with its executed evidence

1. **`paels_eye` G1 — the relic works in the FIRST combat of a run only.**
   `used_this_combat` is never reset (C# clears it at `PaelsEye.cs:145`).
   *Executed (`eye-reset`):* the same instance in combat 2 reports
   `used_this_combat=True` / `should_take_extra_turn=False` where a fresh
   instance in the identical combat reports `True`. Confirms sweep A.

2. **`paels_eye` G3 — the sim's extra-turn path SKIPS THE ENTIRE TURN-END PASS.**
   C# consults `Hook.ShouldTakeExtraTurn` LAST (`CombatManager.cs:1366`), after
   `Hook.BeforeTurnEnd` (:1179), `DoTurnEnd` (:1191), the hand flush (:1296) and
   `Hook.AfterTurnEnd` (:1307). The sim asks FIRST and `return`s
   (`combat.py:648-652`). *Executed (`eye-turnend`):* a sentinel listener records
   `['on_player_turn_end', 'on_hand_emptied', 'after_player_turn_end']` without
   the relic and `['NONE']` with it, on the same `end_turn` call. **This is the
   batch's biggest finding** — it is a defect in `combat.py`'s `end_turn`, not in
   `paels_eye.py`, but Pael's Eye is the sim's only `should_take_extra_turn`
   listener so the observable belongs to its record. Two ported consumers already
   lose behaviour to it (`parrying_shield` G2, `paels_tears` G2).

3. **`paels_eye` G2 — auto-plays count as "cards played this turn".**
   `PaelsEye.cs:156` filters on `!e.CardPlay.IsAutoPlay`; the sim's history has
   no auto-play flag at all. *Executed (`eye-autoplay`):* with HellraiserPower
   active (`powers.py:706-713`, auto-plays any Strike on DRAW, so before the
   player can act), 5 auto-plays and 0 manual plays give
   `_any_cards_played_this_turn=True` / `should_take_extra_turn=False` where C#
   gives `False`/`True` — the sim silently loses the extra turn.

4. **`paels_legion` G1 — the pet stays asleep across the combat boundary
   (NEW; sweep A cleared this unit).** `cooldown` is never reset; C# clears it at
   `PaelsLegion.cs:214` `AfterCombatEnd`, which is its ONLY reset —
   `BeforeCombatStart` (:129-132) merely summons the pet. *Executed
   (`legion-reset`):* one Defend in combat 1 leaves `cooldown=2`; combat 2 turn 1
   with the same instance gives `cooldown=1` and a Defend for **block 5** where a
   fresh instance gives **10**.

5. **`paels_legion` G2 — UNPOWERED card block is doubled in C# and not in the
   sim.** `Hook.ModifyBlock` (`Hook.cs:1310-1340`) is dispatched with **no props
   gate**; PaelsLegion's own filter is `props.IsCardOrMonsterMove()` = just
   `HasFlag(Move)` (`ValuePropExtensions.cs:23-26`). The sim gates the whole
   dispatch on `is_powered_attack(props)` (`cmds.py:145-147`). *Executed
   (`legion-unpowered`):* **Entrench** (`MOVE | UNPOWERED`,
   `cards/trash_heap_cards.py:170-177`) on 10 block gives 20 with and without the
   relic, where C# gives 30 and starts the cooldown; control in the same probe
   shows a Defend IS doubled, so the port is not simply inert.

6. **`paels_tears` G1 — combat 2 opens with +2 free energy on turn 1.**
   `had_leftover_energy` is never reset (C# clears it at `PaelsTears.cs:59`).
   *Executed (`tears-reset`):* combat 2 turn 1 energy **5** on the carried
   instance vs **3** on a fresh one. Confirms sweep A's pre-diagnosis.

7. **`paels_tears` G2 / `parrying_shield` G2 — consumers of G3.** On a Pael's Eye
   extra turn the sim never fires `on_player_turn_end` (so `had_leftover_energy`
   is stale when the extra turn reads it) nor `after_player_turn_end` (so
   Parrying Shield's 6 damage and its `CombatTargets` draw are lost). Same
   executed evidence as G3; recorded as one mechanism with one verdict per
   binding rule 3, owned by `paels_eye` G3.

8. **`paels_tooth` G1 — the candidate filter drops `IsUpgradable`.**
   `PaelsTooth.cs:83` selects through `FromDeckForRemoval(..., filter: c =>
   c.IsUpgradable)`, and `FromDeckForRemoval` ANDs `IsRemovable`
   (`CardSelectCmd.cs:621-625`); the sim passes `run.removable_cards()` alone.
   *Executed (`tooth-filter`):* on `[strike+1, strike, strike, defend, bash,
   regret]` the sim offers 6 candidates and C# offers 4, and the sim's own
   `after_obtained` stores `strike+1` and `regret` — cards C# would never accept.
   Reachable with no extra content: any rest-site smith produces a max-level card
   and 35 of 203 ported cards have `max_upgrade_level 0`.

9. **`paels_tooth` G2 — the stored order is not sorted, and the store is what the
   Rewards RNG indexes.** C# `.OrderBy(c => c.Id.Entry, StringComparer.Ordinal)`
   before appending (`PaelsTooth.cs:83`), then
   `PlayerRng.Rewards.NextItem(SerializableCards)` (:99). *Executed
   (`tooth-filter`):* the same five picks store as `[strike+1, regret, …]` in the
   sim and `[regret, strike+1, …]` sorted — a different card for index 0. Live
   for RNG/deck parity (`conformance/runner.py:618` compares
   `(id, upgrade_level)` pairs), dormant for RL play. Note the sort key must be
   the **uppercased** id: Ordinal puts `_` (0x5F) after `Z` but before `a`.

10. **`paels_wing` G1 — the SACRIFICE alternative reaches combat rewards only.**
    C# adds it in `CardRewardAlternative.Generate(CardReward)` (:53-73, hook at
    :68), i.e. to **every** `CardReward`; the sim hangs it off
    `modify_combat_rewards`, dispatched from one place (`rewards.py:499-500`).
    *Executed (`wing-rewards`):* `RunState.rest_heal_rewards`
    (`run.py:1097-1110`) builds a `CombatRewards`, runs
    `modify_rest_site_heal_rewards`, and never runs `modify_combat_rewards` — so
    a **Dream Catcher** rest-site card choice (`DreamCatcher.cs:22` is a real
    `new CardReward(...)`; `relics/dream_catcher.py:22-25`) carries
    `sacrifice_relic = None`. A missed sacrifice is a missed relic AND a missed
    `PullNextRelicFromFront` draw, which shifts every later pull.
    `LostCoffer.cs:20` is a second `new CardReward` with the same exposure.

11. **`parrying_shield` G1 — `HittableEnemies` vs `living_enemies()`, LIVE at
    this site.** Same mechanism as `bag_of_marbles` G2 and the same `gap` verdict
    (binding rule 3) — but that record labels it **dormant** because Bag of
    Marbles fires only during turn-1 setup. Parrying Shield fires at every player
    turn end, right after the player's own attacks. *Executed
    (`shield-hittable`):* an Eye with Teeth (`monsters/overgrowth/fogmog.py:24-35`,
    act 1) driven to lethal reports `is_dead=False is_gone=False
    is_reviving=True` and `should_allow_hitting=False`; the sim's candidate list
    is 3 and C#'s `HittableEnemies` is 2, and 6 damage aimed at the reviving one
    moves HP from 1 to 1. Both the lost damage and the differently-sized
    `CombatTargets` draw diverge.

(Counting as the records do: 10 distinct LIVE gap entries across 6 units, of
which 2 are the same `paels_eye` G3 mechanism observed at two consumer sites.)

## DORMANT gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `paels_eye` N1 | the Whispering Earring turn-1 short-circuit (`PaelsEye.cs:152-155`) has no sim clause; the sim only reaches the same answer because the Earring's plays land in the history | a turn-1 hand with **zero** playable cards while holding both Ancients — needs content that fills the opening hand with unplayable cards; the 18 ported Curses arrive one at a time |
| `paels_legion` G3 | C#'s `ModifyBlockMultiplicative` has **no target check**; the sim adds `target is not self.player` | a player card that grants Block to an enemy, or a player-side summon a card could shield (all 20 ported card block sites target `ctx.player`) |
| `paels_legion` G4 | the latch. C# latches in `AfterModifyingBlockAmount` behind `modifiedAmount > 0` and "a different play already latched"; the sim latches inside the multiplicative with neither | (a) a card that gains 0 block, or negative Dexterity — whose only C# sources, Malaise and Resonance, are unported (the same pair `unsettling_lamp` G2 names); (b) a card that gains block, auto-plays a card that gains block, then gains block again |
| `paper_phrog` G1 | C# looks the relic up ONCE on the dealer; the sim folds a hook chain, so N copies each add +0.25 | any path that puts two Paper Phrogs in one run — Toy Box's wax copies are the only candidate, and `toy_box` is unaudited on this branch |
| `paper_phrog` N2 | `target == base.Owner.Creature` bail is missing | a POWERED, Move-flagged self-attack. *Executed (`phrog-selfhit`):* all 17 ported sites that damage the player are unpowered/HP-loss or monster-dealt; **zero** are both powered and player-dealt |

`pear`'s `undo_after_obtained` is verdicted **deliberate-divergence** (extra
behaviour the game has no counterpart for, unreachable from play — its only
caller is the conformance runner's relic resync), not a gap.

---

## Faults found in the shared tooling and seam records

Four of the five previous batches found something in the sweeps; this one found
two things, one of them a **false clear** rather than an over- or under-report.

### 1. `sweep-reset-exec` never PLAYS A CARD, so it silently clears every relic whose state is written only from a card-play hook

**This is a false clear, the same dangerous direction as batch 8's
`IsAllowed` under-report.** The driver
(`audit/tools/relic_probes.py`, `probe_sweep_reset_exec`) builds a
`CombatState` and calls `end_turn()` up to three times. It never calls
`play_card`. Any candidate whose fields are only reachable through
`modify_*`/`on_card_played` therefore settles identically on the carried and the
fresh instance and lands in the "agrees with a fresh instance" bucket.

`paels_legion` is the founding example, and the sweep's own **static** output
already contained the evidence:

```
paels_legion  ['_affected_card', 'cooldown']
              written by: _affected_card<-['modify_block_multiplicative', 'on_card_played'];
                          cooldown<-['__init__', 'on_card_played', 'on_player_turn_start']
              C# resets: {'AfterCombatEnd': [... 'Cooldown = 0' ...]}
```

`on_player_turn_start` only **decrements**, so with no card play the cooldown
never leaves 0. Reproduced side by side as
`py audit/tools/relic_probes_b11.py legion-sweep`:

```
sweep driver (end_turn x3, no card play): cooldown=0 _affected_card=None  -> looks clean
one Defend played:                        cooldown=2 -> carries into combat 2
```

**Suggested fix for the sweep owner** (not applied here — `relic_probes.py` is
read-only to this batch): after the turn loop, play the first playable card in
hand before snapshotting, and re-check the other candidates whose written-by
lists are card-play-only. From the current static output those are at least
`nunchaku`, `pen_nib`, `burning_sticks` and `red_skull`. This is a **fifth**
defect in sweep A, on top of the four the rewrite fixed, and it belongs in the
same "known limits" section: the sweep's own limits list already says the
executed diff cannot see the turn-end and frozen buckets — it should also say it
cannot see card-play-only state.

### 2. Sweep E over-reports at `paels_growth.py:39`

Sweep E lists five shallow-rebuild sites; `relics/paels_growth.py:39` is one, and
at that site the rebuild has **no observable**. The input set is filtered to
Clone-enchanted RUN-DECK cards, and all five clone-carried fields are accounted
for: upgrade level is replayed under an `is_upgradable` guard, the Clone
enchantment is re-created with the original's amount, a card holds at most one
enchantment, afflictions cannot reach a run-deck object (`run.create_combat`
deep-copies the deck, `run.py:1136`), and the only ported permanent keyword/cost
edits are performed **by** enchantments — which the one-enchantment rule
excludes. *Executed (`growth-clone`):* an upgraded, `Clone(4)`-enchanted Bash
clones to `lvl=1 ench=clone/4 affl=None cost=2 exhausts=False`, identical on
every field. Not a defect in the probe's detection logic (the site really does
use the shallow idiom) — it is a triage gap: the sweep's table should mark this
row settled rather than leaving it as work.

### 3. Two bookkeeping errors worth correcting, neither in the sweeps' code

- **The batch-11 brief (and, before its rewrite, sweep A's reading) states that
  `paels_legion`'s C# resets at BOTH `BeforeCombatStart` and `AfterCombatEnd`.**
  It does not. `PaelsLegion.cs:129-132` `BeforeCombatStart` is `await
  SummonPet()` and nothing else; `AfterCombatEnd` (:211-219) is the only reset.
  The **fixed** sweep A output has this right (`C# resets: {'AfterCombatEnd':
  [...]}` only), so this is a brief error, not a sweep error — but it matters,
  because a redundant `BeforeCombatStart` reset is exactly what makes
  `unsettling_lamp`'s dropped reset safe and `belt_buckle`'s unsafe.
- **`paels_tears` is assigned to batch 13 by
  `.superpowers/sdd/content-relic-sweeps.md` and to batch 11 by the batch-11
  brief.** It is audited here. Batch 13 should skip it (or reconcile with this
  record) rather than write a second one.

**Nothing was found wrong in `audit/records/seam/**`.** One cross-record interaction was
checked and is consistent rather than conflicting: `bag_of_marbles` G2 and
`parrying_shield` G1 are the same mechanism with the same `gap` verdict, and the
live/dormant labels differ only because the two relics fire in different turn
slots — which is how the pilot handled `unsettling_lamp` G2 vs `power_cmd` G2.

---

## Candidate new bug classes (for the stream owner to fold into `PROMPT.md`)

Both were exhibited by units in this batch; neither is padding.

### A. A control-flow decision moved to the wrong POINT IN THE SEQUENCE drops every hook between the old and new positions

Bug class 20 covers a hook dispatched from the wrong *branch*; class 11 covers
the wrong turn *slot*. This is a third variety: the sim asks a **predicate**
earlier than the game does and takes an early return, so an entire block of
unrelated dispatches never runs. `combat.py:648-652` consults
`should_take_extra_turn` before `on_player_turn_end`, where
`CombatManager.SwitchFromPlayerToEnemySide` consults it after the whole turn-end
pass — silently deleting `Hook.BeforeTurnEnd`, `DoTurnEnd`, the hand flush and
`Hook.AfterTurnEnd` for that turn. The tell is a `return` in a control-flow
method rather than in a content method. **Method:** for any sim method with an
early `return` on a hook predicate, find the C# call site of that predicate and
list every hook the game fires *between* the sim's position and the game's.
**Unit:** `paels_eye` G3, with `parrying_shield` G2 and `paels_tears` G2 as
already-ported casualties.

### B. A props/eligibility filter hoisted from the LISTENER to the DISPATCHER changes which listeners run

`Hook.ModifyBlock` (`Hook.cs:1310-1340`) applies no props filter at all — every
listener applies its own, and they are **not** the same filter:
Dexterity/Frail use `IsPoweredCardOrMonsterMoveBlock`, Pael's Legion uses the
strictly looser `IsCardOrMonsterMove`. The sim hoisted the *strict* filter into
`BlockCmd.apply` (`cmds.py:145-147`), which is right for the majority listener
and wrong for the outlier. The same shape is available on the damage side
(`DamageCmd.deal` hoists `is_powered_attack` at `cmds.py:56-58`) and happens to
be safe there — `paper_phrog` N1 checks it and every C# listener under that
dispatcher uses the same predicate. **Method:** when the sim gates a hook
dispatch on a props predicate, enumerate the C# listeners of that hook and check
that they *all* use the same predicate; one looser listener is a live gap.
**Unit:** `paels_legion` G2 (LIVE, Entrench); cleared at `paper_phrog` N1.

Two existing classes fired usefully and are worth noting as confirms rather than
new entries: class 15 (paired hooks collapsed onto one sim method, guard sets
differ) is `paels_legion` G4's whole shape, and class 13's "trace to the first
reader" is what turned three unreset flags in this batch into three different
verdicts.

---

## Left unverified / out of scope

- **`paper_phrog` G1's duplicate-relic reachability** depends on whether Toy Box
  can produce a wax copy of an already-held relic. `relic/toy_box` is unaudited
  on this branch, so the gap is filed **dormant** rather than live. Settling
  `toy_box` may promote it.
- **`paels_wing` G1's other exposures.** `LostCoffer.cs:20` builds a real
  `new CardReward`, so `relic/lost_coffer` is very likely a second instance of
  the same omission; `relics/lead_paperweight.py` and `events/brain_leech.py`
  also generate card choices in the sim, but their C# counterparts were not read
  and they are not counted here.
- **`paels_claw` N4 (Goopy's run-level Amount growth).** The sim's
  `GoopyEnchantment` grows `Amount` within a combat only, where
  `Goopy.AfterCardPlayed` also increments `Card.DeckVersion.Enchantment.Amount`
  so the growth persists across combats. The divergence belongs to the
  **enchantment** kind, which is audited on the separate `audit-event` branch and
  is not present in this worktree, so it is named in the record and NOT verdicted
  here (binding rule 3 wants one verdict at the owning site).
- **`paels_legion`'s `AfterSideTurnStart` slot** is verdicted
  `deliberate-divergence` on the grounds that no ported path can gain **card**
  block between the pre-draw and post-draw turn-start slots. That was established
  by inspecting the two ported draw-time auto-play sources
  (`HellraiserPower`, strike-tagged only; `MayhemPower`, which runs at
  `on_player_turn_started`, after both slots) rather than by a probe. If either
  is extended, the verdict must be re-audited as a gap.
- **`paels_growth`'s card-selection screen prefs** (`CardSelectorPrefs`,
  sort orders, prompts) were treated as presentation throughout and not
  enumerated.
- No engine code, shared probe module, `PROMPT.md`, sweep file, report file or
  seam record was modified, per the concurrency contract.
