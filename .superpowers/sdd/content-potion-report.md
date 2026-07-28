# Stream 6 — `potion` content audit: report

Branch `audit-potion`, worktree `c:\Users\Perry\Desktop\sts2-rl-potion`,
2026-07-27. Six commits, none pushed, `main` untouched.

Re-run every number in this file rather than quoting it:

```
py audit/tools/audit_status.py --kind potion
py audit/tools/harness.py validate --strict-inherited
py audit/tools/citation_check.py audit/records/potion
py audit/tools/potion_probes.py                      # all sweeps
py -m pytest test/test_hook_order.py -q -k TestPotionContentPins
```

## Status

**All 51 units audited; 0 invalid; 0 stale.** `validate --strict-inherited`
is clean for the kind — no potion has a non-root base class, so there is
nothing inherited to enumerate.

| | |
|---|---|
| records | 51 |
| verdict entries | 472 — 295 `faithful`, 25 `waiver`, 152 `gap` |
| gap entries | 152: **83 live, 69 dormant, 0 unstated** |
| unit rollups | 51 × `gap` (every record carries the shared wrapper entry) |
| pins added | 4 `strict=True` xfails, all content-anchored |

`live` is populated on **every** gap entry, as the prompt asked. The kind
therefore reports 51 in `audit_status`'s `live` column — more than the rest of
the project put together — but that is an artefact of the column counting
*records with at least one live entry*, and every potion carries the shared
`W` entry. The honest per-entry number is 83 live / 69 dormant, and the
per-unit view is the table below.

## The two structural findings

### 1. `PotionModel` is unaudited by construction, and no seam covers it

`harness.py`'s `MODEL_ROOT_CLASSES` lists `PotionModel` beside `CardModel` /
`PowerModel` / `RelicModel`, so base-class following stops there and **no unit
record enumerates a single `PotionModel` member**. `audit/README.md` says that
layer "is audited once by the seam tier, not 680 times" — but the seam tier has
six seams and none of them is the potion pipeline. `PotionModel.OnUseWrapper`
(`src/Core/Models/PotionModel.cs:291-342`) is the entire use path for all 51
units and nothing in `audit/records/seam/` is a verdict on it.

Written up in **`audit/content/potion/shared-mechanisms.md`** and recorded once
per record as guard `W` (rollup `gap`, live). Two of its ten steps are live
gaps, both already owned elsewhere, so the entries **match** rather than
re-derive them (binding rule 3):

- **`Hook.BeforePotionUsed` is never dispatched.** `hooks.py` has only
  `on_potion_used`, whose own docstring says it mirrors *After*PotionUsed.
  Single C# implementer `SurroundedPower.cs:82`, ported at `powers.py:2523`.
  → `audit/records/power/surrounded.json`, gap, live.
- **`CheckForEmptyHand` is never called after a potion.** Two C# callers
  (`CardModel.cs:1992`, `PotionModel.cs:340`); the sim's only
  `on_hand_emptied` site is `player.py:197`, the end-of-turn flush
  `CombatManager.cs:880-883` explicitly excludes.
  → `audit/records/relic/unceasing_top.json` G1, gap, LIVE.

Guard `W4` (dormant) records the third: the
`BeginCardOrPotionEffect`/`EndCardOrPotionEffect` depth counter has no sim
counterpart, and Distilled Chaos is the one potion whose frame can contain a
card frame.

**Recommendation for the seam tier:** add a `potion_pipeline` seam, or extend
`creature_card_cmds` to cover `PotionModel` + `PotionCmd` + `Player`'s belt
verbs. Until then every future potion record repeats guard `W`.

### 2. The kind is invisible to `gap_queue.py`

`py audit/tools/gap_queue.py counts` still prints
`NOT AUDITED : monster (109 C# units), potion (51 C# units)` and omits potion
from the per-kind table, so **1415 gap entries** is now an undercount by 152 and
the queue has no potion mechanisms in it. The tool needs `potion` added to
whatever kind list it walks. Not fixed here — `audit/tools/` outside
`potion_probes.py` is not this stream's to edit, and `GAP-QUEUE.md` is the
gap-queue stream's.

## Every gap, per unit

Shared entries `W` (live) and `W4` (dormant) are on all 51 records and are
omitted below.

### LIVE

| unit | entry | grade | observable |
|---|---|---|---|
| `foul_potion` | G1 | B | Both out-of-combat arms unported: the shop arm (drive the merchant off + `GoldVar(100)`) and the Fake Merchant arm. The port's docstring cites `RunState.merchant_driven_off`, which **does not exist** (`grep -rin merchant_driven_off sts2_rl/` returns only that docstring). Partial credit: the Fake Merchant *event* option is ported (`events/fake_merchant.py:75-97`) but it *discards* the potion rather than using it. |
| `foul_potion` | G2 | B→A | `CombatState.Creatures` is `_allies.Concat(_enemies)` (`CombatState.cs:70`) — the thrower first. `potions.py:418` is `[*ctx.enemies, ctx.player]` — the thrower last. With the player and the last enemy both on ≤12 HP the sim **wins the fight the game loses**, because `use_potion` tests `_all_enemies_dead()` before `player.is_dead` (`combat.py:612-615`). Pinned. |
| `fairy_in_a_bottle` | ShouldDie | B | Single flat `should_die` pass vs C#'s `ShouldDie`-then-`ShouldDieLate`. This is `seam/damage_pipeline` N4, whose waiver was *corrected* because this potion is ported; witness `relic/lizard_tail` G4. |
| `fairy_in_a_bottle` | G1 | B | The automatic trigger calls `potion.use` directly instead of `OnUseWrapper`, so `Hook.AfterPotionUsed` never fires when the fairy pops. Belt Buckle and Reptile Trinket are both ported listeners. Pinned. |
| `entropic_brew` | G1 | B | Procures via `player.add_potion`, dropping `Hook.ShouldProcurePotion` (Sozu) and `Hook.AfterPotionProcured` (Belt Buckle) — `relic/petrified_toad` G1/G2 at a fourth site, and the worst of the four: up to three potions per action. |
| `entropic_brew` | G2 | B | The legacy generator applies the in-combat exclusion the source deliberately avoids (it calls `CreateRandomPotionOutOfCombat`) and picks uniformly instead of rolling a rarity. In training the brew can never produce a Fairy in a Bottle. The parity arm is correct (G3, faithful). |
| `entropic_brew` | N2 | A | The 3-vs-5 belt gap compounds into the RNG stream here: each extra slot is another `CombatPotionGeneration` draw pair. |
| `touch_of_insanity` | G1 | B | The candidate filter is an OR over `CostModifiers.Local` and `.All`; the sim tests only the local cost. Executed with Spiked Gauntlets + a free Power card: the game offers the card, the sim's candidate list is empty and the potion does nothing. Pinned. |
| `potion_of_binding`, `shackling_potion` | G(AoE-power) | B | `HittableEnemies` carries a `ShouldAllowHitting` term the sim's `not is_gone` filter does not, and `PowerCmd.apply` has no `CanReceivePowers` backstop. `seam/power_cmd` G6 at a content site — with the concrete witness that record says it lacks. Executed, pinned. |
| `ashwater`, `gamblers_brew` | G1 | B | `CardSelectorPrefs(prompt, 0, 999999999)`: MinSelect 0 means the screen is always shown and the player may confirm none. `CombatState.select_cards` has no min/max pair and both installed selectors return the full `count`, so these two potions always take the whole hand. |
| `attack_potion`, `skill_potion`, `power_potion`, `colorless_potion` | G1 | B | Outside a parity replay the sim skips `FromChooseACardScreen` entirely and takes `cards[0]`, with no skip option. The parity arm is correct. |
| `blood_potion`, `entropic_brew`, `foul_potion`, `fruit_juice` | Usage | B | `PotionUsage.AnyTime` has **no sim path at all** — one `def use_potion` in the whole sim, on `CombatState`, and the conformance layer treats `UsePotion` as combat-only. A recorded run that drinks one on the map cannot be replayed. |

### Dormant (each names its concrete trigger)

| unit | entry | trigger that would make it live |
|---|---|---|
| `attack/skill/power/colorless/orobic` | Event-rarity filter | `pool_card_ids` drops BASIC/ANCIENT but not EVENT where `CardFactory.FilterForCombat` drops all three. Executed: both pools' EVENT buckets are empty (85→78, 53→50). **Cross-stream: `cards/pool.py` is the card tier's.** |
| `fysh_oil`, `strength_potion` | N(applier) | `StrengthCmd.apply` drops the applier the C# passes — and the same potion passes it for its Dexterity half. Trigger: any listener reading a `StrengthPower`'s applier, or Strength applied to an *enemy* through `StrengthCmd`. |
| `snecko_oil` | N2 | The C# skips a card whose unmodified cost is negative; the sim clamps costs at 0 so no card can present one. Would be a **stream** desync, not a state one — the skipped card also skips a `CombatEnergyCosts` draw. |
| `snecko_oil` | N3 | `SetThisTurnOrUntilPlayed` also expires on play; `set_cost_this_turn` models only the end-of-turn half. Trigger: any ported effect returning a played card to hand within the turn. No other record verdicts this. |
| `gamblers_brew` | N2 | No Sly concept in the sim at all (one grep hit, a docstring). Trigger: porting any Sly card. |
| `gamblers_brew` | N3 | `on_card_discarded` fires *before* the pile move where C# fires it after. Executed: the sim has no `on_card_discarded` listener at all. |
| `fairy_in_a_bottle` | G2 | The sim uses the *Discard* verb where C# uses `RemoveBeforeUse`. Harmless today because `discard_potion` dispatches nothing — a defect the moment `AfterPotionDiscarded` is wired up (which `relic/belt_buckle` needs). |
| `foul_potion` | TargetType, PassesCustomUsabilityCheck | The tier's only computed `TargetType` branch and the game's **only** `PassesCustomUsabilityCheck` implementer, both unported. Dormant only because the sim has no out-of-combat use path to gate. |

## Cross-record consistency (binding rule 3)

Checked against every record the prompt named, plus the ones the work turned up.
**No disagreement found** — every shared mechanism was matched, not re-derived:

- `power/surrounded` `BeforePotionUsed` (gap, live) — matched in `W`. That entry
  was itself re-verdicted from `faithful` by the potion-scope pass; this stream
  confirms it independently by executing the grep census (one implementer).
- `relic/unceasing_top` G1/G2 — matched in `W`/`W4`.
- `relic/petrified_toad` G1/G2, `relic/belt_buckle`, `relic/sozu` — matched in
  `entropic_brew` G1; and `potion_shaped_rock` N1 defers to
  `petrified_toad` for the procurement half rather than re-verdicting it.
- `seam/damage_pipeline` N4 — matched in `fairy_in_a_bottle` `ShouldDie`. This
  is the entry the deleted potion clause protected; the correction stands.
- `seam/power_cmd` G6 — matched in `G(AoE-power)`, with the witness supplied.
- `seam/hook_dispatch` step 15 — its executed claim that `FairyInABottle.cs` is
  the only potion overriding any hook is **independently reproduced** by
  `potion_probes.py sweep-hooks`, from the other direction (it also checks the
  sim side and finds the same single unit).
- `relic/reptile_trinket` `AfterPotionUsed` (faithful at its own site) — the
  potion tier does not contradict it; `fairy_in_a_bottle` G1 is about a
  *different* path reaching that same listener.
- `power/flex_potion`, `power/speed_potion`, `power/shackling_potion`,
  `power/clarity`, `power/gigantification`, `power/radiance`, `power/buffer`,
  `power/demise`, `power/shrink`, `power/plating`, `power/regen`,
  `power/duplication` — all cited, none re-verdicted.

**No `card`/`power` entry still standing on the deleted potion clause** was
found by this stream. The prompt warned ten had waived behaviour on it; the
re-derivation pass already fixed those, and grepping the surviving records for
potion-scope language turned up only correct citations.

## Roster mis-resolutions

`py audit/tools/harness.py roster potion` → `51 sim units, 0 unmatched,
13 unported C# files`. **No mis-resolution.** One name override was already in
place and is correct: `potion/glowwater` → `GlowwaterPotion.cs`
(`audit/tools/name_overrides.json`). No new override is needed.

Two corrections to the stream prompt's own numbers, for whoever edits it:

- It says `src/Core/Models/Potions` holds **129 C# files, so expect ~78
  unported**. The directory holds **64** `.cs` files (65 with `Mocks/`), and the
  roster reports **13** unported — `BoneBrew`, `CosmicConcoction`,
  `CunningPotion`, `DeprecatedPotion`, `EssenceOfDarkness`, `FocusPotion`,
  `GhostInAJar`, `KingsCourage`, `PoisonPotion`, `PotOfGhouls`,
  `PotionOfCapacity`, `PotionOfDoom`, `StarPotion`. Cross-character and cut
  content, as expected, just far fewer of them.
- It says the sim keeps potions in "a single ~1300-line module". True
  (`sts2_rl/potions.py`, 1277 lines) — and the predicted consequence held:
  **one edit to `potions.py` stales all 51 records at once.** Nothing was
  rehashed to hide it; `audit_status` reports 0 stale because `sts2_rl/` was
  never touched.

## Tooling defects found

1. **`citation_check.py` does not consult `extra_sources`.** `_hashed_paths`
   (`audit/tools/citation_check.py:65-75`) reads only the singular
   `game_source`/`sim_source` and the plural seam lists, so every citation
   `backfill_sources.py` legitimately pinned is reported `UNHASHED`. For this
   kind that is **315 false reminders out of 1035 citations**. It over-reports
   (never under-reports), so it is a nuisance rather than a false clear — but
   `--strict` is unusable on any record that uses `extra_sources`, which is the
   mechanism `audit/README.md`'s Staleness section prescribes. The meaningful
   signals, `MISSING 0` and `OUT-OF-RANGE 0`, are green for all 51 records.
2. **`gap_queue.py` cannot see the `potion` kind** (see §2 above). It reports
   the kind as NOT AUDITED and omits 152 gap entries; it *does* already count
   the four new xfail decorators, so its pin count and its mechanism table now
   disagree with each other.
3. **`harness.py roster <kind>` prints no rows** unless a unit is unmatched, so
   getting the work list means importing the module. Minor; noted because every
   stream needs it on day one.

## Lessons for `PROMPT.md` (relic stream to fold in)

Each is drawn from a unit that actually exhibited it.

- **A C# XML `<summary>` can contradict the method body — verdict the body.**
  `CardCmd.cs:162-167` says `DiscardAndDraw` "will wait to trigger the
  discard-related hooks until after the draw is complete". The body fires
  `Hook.AfterCardDiscarded` inside the per-card loop *before* the draw
  (`CardCmd.cs:186-195`) and defers only the Sly auto-play. Trusting the summary
  would have filed a false gap against `gamblers_brew`, whose port is correct.
  This is class 24 (a docstring that misdescribes the port) pointing the other
  way — at the *source's own* documentation.
- **A port's docstring can describe the SOURCE and read as if it described the
  PORT.** `potions.py:398-403` states that out of combat Foul Potion "pays
  GoldVar(100) and drives the merchant off (`RunState.merchant_driven_off`)".
  There is no such attribute and no such code path; the sentence is a faithful
  description of `FoulPotion.cs:79-88`. Distinct from classes 12/19/24: the
  claim is *true of the C#* and false of the sim, so grepping the C# confirms it
  and grepping the sim is the only thing that catches it.
- **A boolean port of a multi-valued enum agrees with every sweep and still
  loses information.** `sweep-attrs` reports 0 mismatches over 51 units × 5
  attributes — because `TargetType` has five values and the sim models one
  boolean (`targeted`), so `AllEnemies`, `Self` and `AnyPlayer` all read
  `False` and only `AnyEnemy` is distinguished. A sweep over a lossy mapping
  cannot report a mismatch it cannot represent. Say so in the bucket label.
- **`PotionUsage` is the same shape and it *did* hide a live gap:** the sim
  models only `Automatic`, so `AnyTime`'s whole out-of-combat arm is missing for
  four ported potions and nothing in the roster or the sweeps says so.
- **A framework root with no seam is a coverage hole the harness cannot
  report.** `MODEL_ROOT_CLASSES` is a promise that the seam tier covers that
  layer. For `PotionModel` it does not, and `validate` cannot notice.
  Worth a check that every root class names its covering seam.
- **Class 18 (TestMode) confirmed again, negatively:** `SneckoOil.cs:59-66`
  forks on `TestEnergyCostOverride` and the port takes the shipping arm, unlike
  `relic/calling_bell`. The check is cheap and the trap is real.

## What I could not settle

Recorded as notes, **not** as gaps (the relic tier's "uncertainty filed as a
gap" defect was wrong 2/2):

- **Whether `CombatManager.History.PotionUsed` has any game reader.** An
  executed grep finds `PotionUsedEntry` created and never queried, and the class
  adds only a `Description` string, so it is waived as presentation. If some
  generic `CombatHistory` query counts entries by base type, that waiver is
  wrong — I could not rule that out from the decompiled source without reading
  the whole history query surface, which belongs to another seam.
- **The exact `CostModifiers.Local` / `.All` split.** The enum's members are
  used but I did not find a definition listing which modifier sources fall in
  each set. `touch_of_insanity` G1 rests on the *observed* behaviour instead —
  `set_free_this_turn` is local and Spiked Gauntlets' hook is not — which the
  probe demonstrates directly. A different global modifier could behave
  differently.
- **Grade for `foul_potion` G2.** The damage-order divergence is plainly a state
  divergence (B), and the mutual-kill case makes it decide a run, which is worse
  than B usually means. I left it B and stated the win/loss case rather than
  inventing a grade.

## Hand-offs

- **card stream:** `cards/pool.py`'s `pool_card_ids` needs the `EVENT` clause
  (`CardFactory.cs:161`). Dormant today; five potion records depend on it.
- **seam stream:** a `potion_pipeline` seam (or an extension of
  `creature_card_cmds`) for `PotionModel`/`PotionCmd`/the belt verbs; and the
  four pins in `TestPotionContentPins` are in the seam-owned file by the potion
  prompt's explicit instruction, confined to one class so they are easy to move.
- **gap-queue stream:** add `potion` to `gap_queue.py`'s kind list; the queue is
  currently missing 152 entries and 20-odd mechanisms.
- **relic stream:** the four `PROMPT.md` lessons above (folded into v7 on
  2026-07-27); the four records that still assert "POTION IS NOT AN AUDITED
  KIND" as a live premise (`alchemical_coffer`, `lost_coffer`, `phial_holster`,
  `potion_belt` — `GAP-QUEUE.md` record inconsistency 19); and 8 records to
  prune (below).
- **card (18 records), relic (8), power (1): prune the `extra_sources` entries
  under `_NEVER_HASHED`.** `backfill_sources.py` had pinned 28 hashes of
  `test/**` and `audit/tools/**` that `citation_check.py` says must never be
  hashed. The tool is fixed; the data change is each stream's, because they are
  each stream's records:

  ```
  py audit/tools/backfill_sources.py --prune --no-add --kind card
  py audit/tools/backfill_sources.py --prune --no-add --kind relic
  py audit/tools/backfill_sources.py --prune --no-add --kind power
  ```

  Nine of the 27 went stale when `TestPotionContentPins` was appended — the
  potion stream's doing, so the potion stream finished it: **they are
  re-audited and re-pinned, and the ledger reads 0 stale.** The re-audit is
  `py audit/tools/potion_probes.py pin-append`, three checks rather than a hash
  rewrite: the change is **append-only**; none of the 72 line citations across
  those records moved or changed content; and every test those records name
  still exists and is still a `strict=True` xfail. `harness.py rehash` then
  re-pinned exactly one `extra_sources` entry per record — verified against
  `--dry-run` first. **The prune is still owed for all 27**, and it is the
  durable fix: a re-pin only holds until the next pin is added to that file.
  Full per-record table: `GAP-QUEUE.md` record inconsistency 20.
- **gap-fix stream:** the highest-value single fix in this tier is
  `PowerCmd.apply`'s missing `CanReceivePowers` guard — it clears
  `seam/power_cmd` G6, both AoE-power potion sites and whatever else applies
  powers to an unhittable creature, and it has a failing pin already written.
