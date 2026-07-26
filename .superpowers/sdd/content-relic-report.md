# Content audits — relics, Tier 1 pilot (batch 1)

**Date:** 2026-07-26 · **Branch:** `audit-relic` · **Commit:** `9eeede09`
**Scope of this report:** Task 11 of `docs/superpowers/plans/2026-07-24-source-audit-pipeline.md`
— the pilot batch that proves the per-unit procedure Tasks 12–16 repeat.

**Stop point reached as instructed.** The full relic sweep (242 remaining
units) has NOT been started; the prioritisation recommendation is at the end.

---

## Units audited (16)

The roster's first 15 relics alphabetically (`py tools/audit/harness.py roster
relic` → 258 sim units, 0 unmatched) plus `relic/unsettling_lamp`, swapped in
per the brief because it is the design document's worked example.

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `unsettling_lamp` | **gap** | 6 | 9 |
| `belt_buckle` | **gap** | 8 | 5 |
| `amethyst_aubergine` | **gap** | 5 | 3 |
| `big_mushroom` | **gap** | 5 | 3 |
| `astrolabe` | **gap** | 3 | 4 |
| `bag_of_marbles` | **gap** | 2 | 5 |
| `archaic_tooth` | **gap** | 2 | 5 |
| `beautiful_bracelet` | **gap** | 2 | 4 |
| `arcane_scroll` | **gap** | 2 | 4 |
| `anchor` | **gap** | 2 | 4 |
| `bag_of_preparation` | **gap** | 2 | 2 |
| `beating_remnant` | deliberate-divergence | 5 | 4 |
| `art_of_war` | deliberate-divergence | 5 | 3 |
| `bellows` | waiver | 2 | 4 |
| `akabeko` | waiver | 2 | 3 |
| `alchemical_coffer` | waiver | 3 | 2 |

`py tools/audit/harness.py validate` → **21 records, 0 invalid**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 16 · invalid 0 ·
stale 0 · gaps 11 · unaudited 242`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; audits added
no executable code (`git status` showed only `audits/relic/` and the new probe
script).

---

## Every gap, with its live/dormant determination

**Totals: 25 gap entries — 15 guard-level (5 live / 10 dormant) and 10
hook-level (6 live / 4 dormant), plus 6 hook entries that are pure rollups of
their guards per binding rule 4.** Eleven of the 16 units roll up to `gap`.

Reachability evidence for every LIVE label comes from
`tools/audit/relic_probes.py` (committed, 8 probes, re-runnable) — binding rule
6 requires proving both sides reachable with ported content, and rule 5 forbids
resting a verdict on an unexecuted unreachability claim.

### LIVE gaps

**1. `belt_buckle` G2 — the relic works in the first combat of a run only.**
The single highest-impact finding and the cheapest fix. C# clears
`DexterityApplied` in *two* places (`BeltBuckle.cs:49` `BeforeCombatStart`,
`:92` `AfterCombatVictory`); the sim clears `_applied` **nowhere**. Relic
instances live on `RunState.relics` and are re-attached to each new
`CombatState`, so combat 2 enters `_apply_if_potionless` with `_applied` already
`True`. *Evidence (`relic_probes.py buckle-potion`):* the same relic instance in
a second combat reports **Dexterity 0** where C# gives 2. Both sides ported —
Shop rarity in the transcribed grab bag, and every run has more than one combat.

**2. `belt_buckle` `AfterPotionProcured` / `AfterPotionDiscarded` — missing
entirely.** C# removes the 2 Dexterity the moment a potion is procured mid-combat
and re-applies it on a discard that empties the belt. *Evidence (same probe):*
after `player.add_potion`, the sim still reports Dexterity 2 (C#: 0). **Scope
note:** the contract defers potions, but the divergent *observable* is
Dexterity — a combat mechanic that changes every Block number for the rest of
the fight — so this is filed as a gap, not waived. The potion is only the
trigger.

**3. `unsettling_lamp` G1 — doubling survives every Replay pass.**
`CardModel.cs:1904-1963` fires `Hook.AfterCardPlayed` *inside* the play-count
loop, so `IsFinishedTriggering` is set at the end of iteration 0 and iteration 1
is not doubled. The sim calls `on_card_played` once, after the whole loop
(`combat.py:514`). *Evidence (`relic_probes.py lamp-replay`):* Lamp + Throwing
Axe on a Bash gives **8 Vulnerable** where C# gives 4 + 2 = **6**. Both sides
ported: Lamp is Rare in the grab bag, Throwing Axe is granted by the ported Tanx
shrine; Spiral/Glam enchantments and Hidden Gem reach the same play-count hook.
This is the site-specific observable of `hook_dispatch` **G4**, which that record
already labels LIVE — recorded here per the seam's ownership policy (the seam
owns the machinery, the content record owns the observable).

**4. `amethyst_aubergine` `TryModifyRewards` — +15 combat-reward gold missing.**
The port is a behaviourless stub justified by a docstring claim that is **false**:
"the sim has no gold". It has `RunState.gold`, a rewards screen that rolls and
grants it (`rewards.py:462-485`), and the exact `modify_combat_rewards` hook the
port needs (`rewards.py:499-500`), already used by five other relics. *Evidence
(`relic_probes.py aubergine-gold`):* a MONSTER screen pays `gold=19` both with
and without the relic. **Implementation note for the fix:** the gold is banked at
`rewards.py:464/485`, *before* the hook loop at 499 — mutating `rewards.gold`
alone would display the 15 without granting it.

**5. `amethyst_aubergine` `IsAllowed` — pool eligibility has no sim concept.**
`AmethystAubergine.cs:20-23` stops the relic spawning from the Act 3 treasure
chest onward (`TotalFloor < 41`). The sim's `Relic` base declares no `is_allowed`
**at all**, and the grab bag is shuffled once at run init with no per-pull
filter. The sim tracks `total_floor` already. Observable: pool composition, which
also shifts every subsequent pull. Flagged as a base-class-wide omission — the
remaining 242 relics should be swept for other `IsAllowed` overrides before a fix
is scoped.

**6. `astrolabe` G1 — unguarded `Card.upgrade()` marks curses upgraded.**
`CardCmd.Upgrade` skips cards whose `IsUpgradable` is false; the sim's
`Card.upgrade()` (`cards/base.py:146-147`) is a bare `upgrade_level += 1` and
`astrolabe.py:23` calls it directly. *Evidence (executed):* curses **are**
transformable on both sides, a transformed curse rolls another curse, and
`curse_of_the_bell` (`max_upgrade_level` 0 — 35 such cards by census) came out at
`upgrade_level 1`. Not cosmetic: `conformance/runner.py:618` compares the deck as
`(id, upgrade_level)` pairs against the save.

**7. `astrolabe` N1 — the Niche stream is not passed.** C# names
`Rng.Niche` explicitly; `run.transform_card`'s `pick_rng` defaults to `None`,
which its own docstring says "keeps the shared-rng choice" for callers "not yet
parity-wired". Live for RNG parity (any seed that takes Astrolabe at the Darv
shrine diverges in both the cards and the stream position), dormant for RL play.

**8. `big_mushroom` `AfterObtained` — +20 Max HP lives in the wrong place.**
The relic implements no `after_obtained`, justified by another false docstring
claim ("RunState has no run-level AfterObtained dispatch" — `run.py:552` calls
it, and the sibling relic from the same event uses it). *Evidence
(`relic_probes.py mushroom-hp`):* `add_relic('big_mushroom')` leaves max HP at
80; `add_relic('fragrant_mushroom')` correctly applies its own effect; the event
path is whole (80 → 100) only because the event re-applies the +20 itself. The
conformance runner grants relics by id straight through `add_relic`
(`runner.py:465, 698, 751`), so its relic resync silently loses 20 Max HP —
which DETECTOR 3's act-boundary HP assertion will report as a parity failure on
any seed that took Big Mushroom. It also defeats `undo_after_obtained`, which
exists precisely to unwind max-HP relics on a runner swap.

**9. `belt_buckle` `AfterObtained` (mid-combat pickup) — dormant-but-filed.**
Recorded as a gap rather than a waiver because "the sim has no path that grants
a relic inside a fight" is today's content, not the divergence's shape (binding
rule 1).

**10–11.** `unsettling_lamp` `BeforePowerAmountChanged` and `AfterCardPlayed`,
and `archaic_tooth` / `beautiful_bracelet` / `bag_of_marbles` / `astrolabe`
`AfterObtained` — hook-level rollups carrying their guards' worst verdict.

### DORMANT gaps (10 guard-level), each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `unsettling_lamp` G2 | sign-aware `GetTypeForAmount` + the sim's `amount <= 0` bail (= `power_cmd` G2 at its own site) | porting **Malaise** or **Resonance**, the only two C# cards that apply negative Strength to an enemy from a card |
| `unsettling_lamp` G3 | C#'s multiplicative has no target-side or applier guard; the sim applies both | a card that debuffs an enemy **and** the player in one play (6 ported cards self-debuff, none also debuffs an enemy); or a player-side minion |
| `unsettling_lamp` G4 | ambient `_in_flight` vs per-application `cardSource`; a nested auto-play clears it | a card that debuffs → auto-plays → debuffs again (3 ported cards already auto-play mid-`on_play`) |
| `unsettling_lamp` `ModifyPowerAmountGivenMultiplicative` | additive-then-multiplicative two-pass collapsed to one flat chain (= `power_cmd` G3) | a second given-side power-amount modifier whose domain overlaps debuffs |
| `bag_of_marbles` G1 | C#'s `BeforeSideTurnStart` (step 9) mapped to the sim's post-draw slot (step 23) | a ported intent whose move selection reads its own Vulnerable |
| `bag_of_marbles` G2 | `HittableEnemies` vs `living_enemies()` (distinct from `power_cmd` G6's missing backstop) | a turn-1 untargetable enemy |
| `anchor` N3 | block granted at step 14 instead of step 3 | any monster intent or `BeforeCombatStart` listener that reads player Block |
| `archaic_tooth` G1 | C# carries one upgrade level, the sim carries all of them | a transcendence target with `MaxUpgradeLevel > 1` (census: zero ported cards above 1) |
| `archaic_tooth` G2 | sim adds a `can_enchant` condition C# lacks, and **destroys** the enchantment when it fails | an enchantment whose eligibility distinguishes Bash from Break |
| `beautiful_bracelet` G1 | candidate-list filter built differently | **open question, not a claim** — settling it needs `Swift.cs` and `CardSelectCmd.cs`, which this record does not hash (flagged per binding rule 7) |
| `arcane_scroll` `AfterObtained` | deck-insertion position not stated or pinned the way siblings do | needs `run.py`, unhashed here — filed as a cheap confirm-or-fix |
| `bag_of_preparation` N1 | no `AfterModifyingHandDraw` companion event (= `turn_structure` step 20 / `power_cmd` G4) | porting any relic that implements the companion |

---

## Cross-record consistency (binding rule 3)

Four mechanisms already carried a verdict in the seam tier. All four are
reproduced with the **same** verdict, cited, and not re-derived:

- `power.IsVisible` → **waiver**, matching `power_cmd` N1, with the same
  executed basis (zero `IsVisibleInternal` overrides anywhere in the game, so
  the gate is dead code in the C# source itself, not unported content).
- sign-aware `GetTypeForAmount` → **gap**, matching `power_cmd` G2 — which
  names the Lamp's own site in its issue text.
- `ITemporaryPower` double-dip → **deliberate-divergence**, matching
  `power_cmd` N2. **Extended:** N2 verified the equivalence for
  `TemporaryStrengthPower`/`TemporaryDexterityPower`; `relic_probes.py
  lamp-temporary` establishes it is *complete* — exactly three C#
  implementers exist, both ported ones pass `applier` on **zero** of their
  three call sites, and `PiercingWailPower`/`TemporaryFocusPower` are unported.
  Residual risk recorded: the equivalence is incidental, not enforced.
- per-Replay `AfterCardPlayed` → **gap**, matching `hook_dispatch` G4.

**No cross-record disagreement was found.** One tension worth naming, recorded
in `anchor`'s hook rationale: `turn_structure` **G1** calls the unconditional
`AfterBlockCleared` loop a defect, and the sim's Anchor port *depends* on it. If
G1 is ever fixed to fire only on a real clear, Anchor breaks on turn 1 and its
verdict must be re-audited. That is a fix-ordering constraint for the gap-fix
stream, not a disagreement.

## Roster mis-resolutions

**None.** `roster relic` reports 258 sim units, **0 unmatched**, 40 unported C#
files. All 16 pilot units resolved to a real C# file on the first try, and
`tools/audit/name_overrides.json` needed no additions. Obtainability confirmed
for all 16 (`relic_probes.py pool`): 9 via the transcribed grab bag, 6 via
ported events/shrines (Orobas ×2, Neow, Darv, Nonupeipe, Hungry for Mushrooms),
`anchor` additionally via Calling Bell.

---

## Cost data

**Measurement caveat:** wall time and token counts are the session's own
estimates, not instrumented figures — no harness records them. The record
counts, gap counts, execution counts and suite timings below are exact. Treat
the two time/token rows as order-of-magnitude planning inputs.

| Measure | Value |
|---|---|
| Units audited | 16 |
| Wall time, end to end | ~95 min (of which the full suite is 4m16s, run once) |
| **Wall time per unit** | **~6 min** |
| Context consumed | ~135k tokens for the batch, including all shared setup |
| **Tokens per unit** | **~8.4k marginal** (~25k of the total was one-off: contract, spec, seam calibration, `Hook.cs`/`turn_structure` reading — that cost does not recur per batch) |
| Record entries written | 120 (56 hooks + 64 guards), avg 7.5 per unit |
| Gap rate | **11 / 16 units (69%)** roll up to `gap` |
| Gap entries | 25 — **11 live**, 14 dormant |
| **Units needing EXECUTION to settle** | **8 of 16 (50%)** |
| Probes written | 8, in `tools/audit/relic_probes.py` (committed) |

**Which units needed execution.** `belt_buckle`, `unsettling_lamp`,
`amethyst_aubergine`, `big_mushroom`, `astrolabe` (5 units where a probe *found*
or *sized* a live gap), plus `akabeko`, `art_of_war`, `bag_of_preparation`,
`bag_of_marbles`, `beating_remnant`, `bellows`, `anchor` (7 units where the
`turn-order` probe was needed to settle a hook mapping — one probe served all
seven). Reading alone would have produced **wrong `faithful` verdicts on at
least three** of them.

**Which bug classes actually fired**, from the v1 checklist:

| Class | Fired? | Where |
|---|---|---|
| 1 hook order at seams | ✔ | `anchor` N3, `bag_of_marbles` G1 |
| 2 killing-blow guards | ✔ (as a *confirm*) | `beating_remnant` `AfterDamageReceived` |
| 3 sign-aware power typing | ✔ | `unsettling_lamp` G2 |
| 4 visibility guards | ✔ | `unsettling_lamp` N1 |
| 5 temporary-power double-dip | ✔ | `unsettling_lamp` N2 |
| 6 state-machine int args | ✘ | no monsters in this batch |
| 7 pile limbo | ✘ | — |
| 8 append position | ✔ | `arcane_scroll` `AfterObtained` |
| 9 per-Replay iteration | ✔ **(live gap)** | `unsettling_lamp` G1 |
| 10 reset timing | ✔ **(live gap)** | `belt_buckle` G2; also cleared `art_of_war` and `unsettling_lamp` |

Eight of ten fired. The two that did not are monster/card-specific and will fire
in Tasks 14–15.

**Six classes the v1 checklist missed** are now `PROMPT.md` **v2**, classes
11–16 — every one drawn from a defect this batch actually found, none padded:

11. **The sim's own mapping docstrings are evidence, not truth.**
    `relics/base.py:10-18` claims `BeforeSideTurnStart → on_player_turn_start`;
    the executed order proves that slot is ~5 steps later. Two units inherited
    the error.
12. **A no-op stub usually justifies itself with a claim about the sim — check
    the claim.** Two stubs rested on false premises; both were live gaps.
13. **Missing reset ≠ gap; missing reset with nothing shadowing it = gap.**
    Three units dropped a reset; two are safe, one disables the relic.
14. **Unguarded `Card.upgrade()`** — 35 ported cards have
    `max_upgrade_level 0`.
15. **Paired hooks rarely carry the same guard set** — the sim collapses two C#
    hooks into one method and applies the *union*; that collapse is where the
    divergence hides (the Lamp's G3 and G4 both live there).
16. **Two whole C# concepts have no sim counterpart at all** — `IsAllowed` pool
    eligibility, and named-RNG-stream arguments that silently default to the
    legacy shared RNG.

Plus a "Recording lessons" procedure note: add a class only when a unit
exhibited it, and name the unit.

---

## Recommendation

### The pilot's headline: the gap rate is high and the errors are systematic

69% of units carry a gap, and — more usefully — **the live gaps cluster into
five repeating shapes**, not sixteen unique bugs: a missing per-combat reset, a
stub resting on a false premise about the sim, a hook mapped to the wrong turn
slot, an unguarded upgrade, and a missing pool-eligibility concept. That
changes what the remaining work should look like.

**1. Run three cheap mechanical sweeps FIRST, before batch 2 (~1–2 h total).**
Each targets one shape across all 258 relics at once and will cost far less than
rediscovering it 15 units at a time:
- grep every sim relic for state set in `__init__` or a hook and never reset —
  the `belt_buckle` shape;
- grep every C# relic for an `IsAllowed` override — the sim has no such concept
  at all, so this is a base-class fix plus a list;
- grep every sim relic whose body is only a docstring (a no-op stub) and check
  each stated premise against the sim — this batch found two false ones in
  three stubs.

Their output should go to the gap-queue stream as a pre-populated list, and the
per-unit batches then confirm rather than discover.

**2. Then continue relics in 15-unit batches, at ~6 min and ~8.4k tokens per
unit.** 242 units ≈ **16 batches, ~24 h wall, ~2.0M tokens**. Batches are
independent and parallelise; the shared setup cost is already paid.

**3. Order the remaining four content streams: monsters → powers → cards →
events/enchantments.** The pipeline design puts powers second, and I would swap
it. This batch showed the expensive, high-yield findings are *hook-timing and
lifecycle* ones, which is exactly where the ~18 hand-rolled monsters live —
and `monster_state_machine` bug class 6 has already produced one shipped
engine bug (TwigSlimeM/Flyconid). Powers are interaction-heavy but this batch
found the sim's power layer already well covered by the seam tier's
`power_cmd` record. Cards are the cheapest per unit and mostly numbers; they
are the natural place to parallelise widest.

**4. Two things the gap-fix stream should know before it starts.**
- `belt_buckle` G2 is the cheapest high-impact fix in the batch (reset
  `_applied` in `on_combat_start`) and should not wait for a queue.
- Fix-ordering constraint: `turn_structure` G1 must not be fixed before
  `anchor`'s port is changed, or Anchor silently stops granting block on turn 1.

**5. Budget for execution.** Half the units needed a probe to settle. Every
future batch should expect to write or extend `tools/audit/relic_probes.py`;
that is the mechanism that turned three would-be `faithful` verdicts into live
gaps, and it is the pipeline's main defence against the design's own stated
residual risk ("a wrong 'faithful' verdict is the residual risk the harness
cannot catch").
