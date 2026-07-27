# Relic content audits — batch 9 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b09` (based on `audit-relic` @ `0cad15d3`)
**Units:** the 15 relics from `lost_coffer` to `mr_struggles`
**Probes:** `audit/tools/relic_probes_b09.py` (11 probes, committed, re-runnable)

`py audit/tools/harness.py validate` → **141 records, 0 invalid**.
`py audit/tools/citation_check.py audit/records/relic` → **MISSING 0, OUT-OF-RANGE 0**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 136 · invalid 0 ·
stale 0 · gaps 108 · unaudited 122`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; no engine code
was touched (`git status` shows only the 15 records, the probe module and this
file).

---

## Units and rollups

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `lost_coffer` | gap | 3 | 5 |
| `lost_wisp` | **gap (LIVE)** | 2 | 8 |
| `lucky_fysh` | **gap (LIVE ×3)** | 4 | 6 |
| `mango` | **gap (LIVE)** | 3 | 2 |
| `massive_scroll` | gap (dormant) | 3 | 4 |
| `maw_bank` | **waiver** | 5 | 5 |
| `meal_ticket` | **gap (LIVE ×2)** | 3 | 5 |
| `meat_cleaver` | gap (dormant) | 2 | 6 |
| `meat_on_the_bone` | **gap (LIVE)** | 4 | 5 |
| `membership_card` | **gap (LIVE)** | 2 | 4 |
| `mercury_hourglass` | **gap (LIVE mechanism)** | 2 | 6 |
| `miniature_cannon` | gap (dormant) | 2 | 6 |
| `miniature_tent` | gap (dormant) | 2 | 4 |
| `molten_egg` | **gap (LIVE ×2)** | 5 | 9 |
| `mr_struggles` | **gap (LIVE)** | 2 | 6 |

14 of 15 roll up to `gap`; `maw_bank` is the only unit whose port is behaviourally
complete (its worst entry is a presentation waiver). 5 of the 15 are
behaviourless stubs, and **every stub premise that could be tested was false** —
consistent with sweep C's headline.

---

## LIVE gaps, each with its executed evidence

1. **`meat_on_the_bone` G1 — the heal is skipped because Burning Blood heals
   first. NEW; no sweep or seam record reaches it.**
   `Hook.AfterCombatVictory` (`Hook.cs:340-351`) makes **two** complete passes:
   every `AfterCombatVictoryEarly` listener, then every `AfterCombatVictory`
   listener. Meat on the Bone is the **only** `AfterCombatVictoryEarly`
   implementer in the entire game, so its `HP <= 50% max` test always sees the
   pre-heal HP. The sim has one flat `on_combat_end` pass in `RunState.relics`
   order. *Executed (`b09-meat-bone`):* at 38/80 (threshold 40) the relic alone
   heals to 50; `[burning_blood, meat_on_the_bone]` gives **44** and
   `[meat_on_the_bone, burning_blood]` gives **56**, where C# gives 56 either
   way — **12 HP from listener order alone**. And the losing order is the one
   that happens: Burning Blood is the starter relic, so it is index 0 of
   `RunState.relics`.

2. **`membership_card` G1/G2 — every shop price in the sim is double.**
   `MerchantEntry.Cost` (`MerchantEntry.cs:19-29`) runs
   `Hook.ModifyMerchantPrice` on every read; the sim has **no such hook at all**
   (`git grep modify_merchant_price sts2_rl/` → 0 hits) and all four
   `_calc_cost` methods pin `self.cost` with no relic pass. *Executed
   (`b09-membership`):* the same stocked inventory reports the identical 14 entry
   costs with and without the relic. G2 is filed separately because C#'s `Cost`
   is a live property (a mid-shop pickup retro-discounts the shelf) that
   truncates with `(int)`, so a fix that multiplies `self.cost` in `_calc_cost`
   would be wrong twice.

3. **`meal_ticket` G1 — 15 HP per shop never healed.** Stub premise
   ("out-of-combat MerchantRoom effect") false: `after_room_entered` is
   dispatched at `run.py:983` **with the RoomType**, and `RoomType.SHOP` is the
   MerchantRoom. *Executed (`b09-meal-ticket`):* 40 HP → 40 on a shop entry;
   C# → 55.

4. **`lucky_fysh` G1 — 15 gold per deck add never granted.** Stub premise ("no
   gold system in the sim") false: `RunState.gold`, `gain_gold` and the
   `after_card_added_to_deck` dispatch all exist. *Executed (`b09-fysh`):* two
   `add_card` calls leave gold at 99; C# → 129.

5. **`lucky_fysh` G3 = `molten_egg` G2 — `RunState.transform_card` fires
   NEITHER deck-add hook.** One mechanism, two sites (rule 3). `CardCmd.Transform`
   on a Deck pile fires `Hook.ModifyCardBeingAddedToDeck` (`CardCmd.cs:427-434`)
   **and** `Hook.AfterCardChangedPiles` (`CardCmd.cs:447`); `transform_card`
   (`run.py:406-465`) bypasses `run.add_card` entirely. *Executed:* with
   `molten_egg` held, `add_card(bash)` → `upgrade_level 1` (correct) but
   `transform_card(→ bash)` → `upgrade_level 0`; with `lucky_fysh` held,
   `transform_card` grants 0 gold. Reachable via `astrolabe`, `pandoras_box` and
   the ported Wood Carvings content, and `conformance/runner.py:618` diffs the
   deck as `(id, upgrade_level)` pairs, so it is a **parity** failure, not just a
   strength one. **Fix is one call pair in `transform_card`, not two relic fixes.**

6. **`lucky_fysh` G2 = `meal_ticket` G2 = `molten_egg` G1 — the
   `IsBeforeAct3TreasureChest` floor gate** (sweep B's 17-relic cluster,
   confirmed not re-derived). *Executed (`b09-isallowed`):* `hasattr(Relic,
   'is_allowed')` is `False`, and at `total_floor=60` the grab bag still yields
   all three on seeds 0/1/2.

7. **`lost_wisp` G1 — per-Replay `AfterCardPlayed`.** `CardModel.cs:1961` fires
   the hook *inside* the play-count loop; `combat.py:514` fires it once after it.
   *Executed (`b09-wisp-replay`):* Lost Wisp + Throwing Axe on a Power card deals
   **8** where C# deals **8 + 8 = 16**. Same mechanism as `unsettling_lamp` G1 /
   `hook_dispatch` G4, matched per rule 3.

8. **`mr_struggles` G1 — the port omits the `_check_win()` its identical sibling
   performs.** *Executed (`b09-struggles`):* on the extra-turn path with the last
   enemy at 2 HP, `mercury_hourglass` ends the combat
   (`phase=COMBAT_OVER, player_won=True`) and `mr_struggles` does **not**
   (`phase=PLAYER_TURN, result=None`) with `all_enemies_dead()` True. Site
   observable of `turn_structure` G13, which already names `mr_struggles.py:22`.
   **Scope stated honestly:** a CONTROL row shows the ordinary `end_turn` path is
   covered for both relics by `combat.py:681-685`, and the turn-1 window needs an
   enemy already below the tick (lowest ported enemy max HP is 6), so the
   **extra-turn window** (`combat.py:648-652`, no win check at all) is the
   reachable one — reached with `paels_eye` (ported, Pael shrine).

9. **`mango` G1 — `undo_after_obtained` gives back the max HP but not the heal.**
   *Executed (`b09-simple`):* 50/80 → grant → 64/94 → undo → **64/80**, 14 HP too
   high, and the port's own comment says it gives back "the heal that came with
   it". Live because `conformance/runner.py:461` and `:694` really call it (rule
   8, grepped) on the speculative-grant-then-swap path — exactly the DETECTOR 3
   act-boundary HP assertion. **Pool-wide: all five undo relics share the bug**
   (see the new-shape section).

10. **`mercury_hourglass` G1 = `mr_struggles` G2 — the two-pass turn-START
    collapse (NEW pool-wide shape; mechanism LIVE).** See below.

---

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `meat_cleaver` G2 | `CookRestSiteOption`'s removal screen is `Cancelable = true` and a cancel is a full no-op (`CookRestSiteOption.cs:45-54`); the sim always removes 2 and grants 9 | a `run.select_cards` protocol that can **decline** — none of its selectors can today, so no ported content reaches the C# arm |
| `miniature_cannon` G1 | `dealer != Owner && cardSource.Owner != Owner` is an **AND**; the port keeps only the first disjunct | a player-side minion/summon, or reflected damage that keeps the `cardSource` but changes the dealer. *Executed:* the `upgraded card, dealer=None` row returns 10 vs C#'s 13, but all four ported `card=`-without-`dealer=` calls use `CARD_HP_LOSS` (UNPOWERED), which never reaches the additive hook |
| `miniature_tent` G1 | C# aggregates the hook over **all** hook listeners; `run.py:1079-1082` walks `self.relics` only | any card/power/modifier implementing `ShouldDisableRemainingRestSiteOptions`. *Executed:* the whole game source has exactly one implementer (this relic) plus the dispatcher, default and single caller |
| `molten_egg` G4 | `EggRelicHelper.UpgradeValidCards` has **no** upgrade-level check, so C# re-upgrades an already-upgraded Attack on the reward/merchant paths; the sim applies `ONLY_UNUPGRADED` to all three | a ported card with `MaxUpgradeLevel >= 2`. *Executed census:* **0** ported cards exceed 1, so a level-1 card is never `IsUpgradable` and both sides skip it. Same population `archaic_tooth` G1 waits on |
| `molten_egg` N4 | one flat `modify_card_reward_options` pass vs C#'s `TryModifyCardRewardOptions` + `…Late` two-pass (`Hook.cs:1445-1468`) | a plain-phase listener that **replaces** a reward card's identity; the ported ones only upgrade/enchant/append. = `hook_dispatch` G3 at a second site |
| `lost_coffer` N2 | `CardCreationFlags.IsCardReward` is set by `CardReward`'s ctor and the sim has no flag concept | porting Prismatic Gem or Dingy Rug (the flag's named consumers) |
| `massive_scroll` N4 | the port is a stub, not a guarded no-op, so it would silently do nothing if ever reachable | multiplayer, permanently out of scope; filed so the stub-ness stays visible to sweep C's census |

---

## Waivers, and why they are waivers and not dormant gaps

- **`massive_scroll` `IsAllowed` / `AfterObtained`** — `Players.Count > 1`; the
  relic is multiplayer-**only** and its card pool is filtered to
  `MultiplayerOnly` cards. Multiplayer is out of scope *by name* under rule 1, so
  the divergence's **shape** is out of scope, not merely today's content.
  Unreachability is EXECUTED, not asserted (`b09-pool`): not in either grab bag
  (Ancient rarity is structurally excluded), filtered out of Neow's options on
  **0 of 400 seeds**, `merchant_cost` is the Ancient sentinel, and the only
  literal id occurrence outside its own file is the Neow pool it is filtered from.
- **`molten_egg` G3 (`NoHookUpgrades`)** — dead code in C# *itself*, the same
  basis as `unsettling_lamp` N1 and `calling_bell` G4. `Flags` has a private
  setter writable only via `WithFlags`; all **29** `WithFlags` call sites were
  enumerated and `NoHookUpgrades` has **0 producers / 3 readers**, as do the
  composite `NoUpgrades` and `NoModifications`.
- **`lost_coffer` G2 (PotionReward)** — both halves of the divergence (the pool
  identity and the `PlayerRng.Rewards` stream) are inside the potion domain the
  contract defers. Contrast `belt_buckle`, where a potion-*triggered* divergence
  was filed as a gap because its observable was Dexterity.
- **`maw_bank`** — its only non-`faithful` entries are presentation
  (`ShouldFlashOnPlayer`, `Flash`, `RelicStatus.Disabled`).

---

## NEW: two pool-wide shapes and one new bug class

### Shape 1 — C#'s two-pass hook dispatch is collapsed at **three** hook pairs, not one

`audit/records/seam/turn_structure.json` guard **G12** records this for the Late/VeryEarly
**sub-phases of one hook**. This batch found the same machinery biting at two
places G12 does not cover, and both are *different C# hooks* rather than
sub-phases — a much wider blast radius:

- **Turn START:** every `Hook.AfterPlayerTurnStart` listener (step 22) finishes
  before any `Hook.AfterSideTurnStart` listener (step 23). *Executed census:* **9**
  ported relics on step 22 and **14** on step 23 land on the *same* sim method
  `on_player_turn_started`. **Mechanism LIVE, executed:** Gambling Chip (step 22,
  mulligans the hand) × Bone Tea (step 23, upgrades the hand) — sim relic order
  `[gambling_chip, bone_tea]` gives post-mulligan hand levels `[1,1,1,1,1]` and
  `[bone_tea, gambling_chip]` gives `[0,0,0,0,1]`, with Bone Tea's single charge
  spent either way; C# always gives the first.
- **Combat VICTORY:** `AfterCombatVictoryEarly` then `AfterCombatVictory`
  (`Hook.cs:340-351`) — LIVE at `meat_on_the_bone`, 12 HP (finding 1 above).
- **Card rewards:** `TryModifyCardRewardOptions` then `…Late`
  (`Hook.cs:1445-1468`) — dormant at `molten_egg`.

**Suggested method for the next batches, and for the card/power streams:** for any
hook you verdict, `grep` the `Hook.<Name>` dispatcher body and count how many
`foreach` passes it makes. Two passes means the sim's single duck-typed loop has
flattened a guarantee, and the question is which ported listeners land on both
sides of the seam. This is cheap and mechanical, and it is how three of this
batch's findings were located.

### Shape 2 — `undo_after_obtained` clamps where it must subtract (all 5 sites)

Every relic with a sim-only `undo_after_obtained` uses the identical
`run.lose_max_hp(N); run.hp = min(run.hp, run.max_hp)` — a **clamp**, so the heal
that `gain_max_hp` performed survives the undo whenever post-heal HP is at or
below the restored max: `mango.py:24-25` (14), `pear.py:24-25` (10),
`strawberry.py:24-25` (7), `looming_fruit.py:24-25` (31) and `lees_waffle.py:24-25`
(7, which also heals to full in `after_obtained` and so leaks more). Only `mango`
is in this batch and only `mango` is verdicted; the other four batches should cite
this rather than re-derive. **One shared helper fixes all five.** The observable is
a player-state parity failure of up to 31 HP on any recorded run whose relic node
was offered one of these and declined — i.e. a DETECTOR 3 act-boundary HP failure.

### New bug class candidate (for the stream owner to fold into `PROMPT.md`)

> **24. A C# `Hook.X` dispatcher that makes TWO `foreach` passes is an ordering
> GUARANTEE the sim's single duck-typed loop destroys — and the two passes are
> often two different hook NAMES, not just `X` and `X`Late.** Class 15 covers two
> C# hooks collapsed onto one sim *method*; this is about two C# *passes*
> collapsed into one sim *loop*, which turns a guarantee into
> `RunState.relics`-order luck. Found as `meat_on_the_bone` G1 (LIVE, 12 HP:
> `AfterCombatVictoryEarly` is the game's only implementer and Burning Blood, the
> index-0 starter relic, heals first) and as the turn-start pass pair (LIVE,
> executed on Gambling Chip × Bone Tea). Method: read the `Hook.<Name>` body and
> count its `foreach` loops before verdicting any hook mapping.

---

## Cross-record consistency (rule 3)

Six mechanisms already carried a verdict elsewhere; all six are reproduced with
the **same** verdict, cited, and not re-derived:

| Mechanism | Prior record | This batch |
|---|---|---|
| per-Replay `AfterCardPlayed` | `hook_dispatch` G4 / `unsettling_lamp` G1 — gap, LIVE | `lost_wisp` G1 — gap, LIVE |
| missing post-turn-setup `CheckWinCondition` | `turn_structure` G13 — gap, LIVE (and it names `mr_struggles.py:22`) | `mr_struggles` G1 — gap, LIVE |
| `IsAllowed` pool eligibility | `amethyst_aubergine` / sweep B — gap, LIVE | `lucky_fysh` G2, `meal_ticket` G2, `molten_egg` G1 |
| missing `Late` phase on a reward/cost hook | `hook_dispatch` G3 / `brilliant_scarf` G2 — gap | `molten_egg` N4 — gap, dormant |
| a C# guard with **zero** overrides anywhere = dead code in C# → waiver | `unsettling_lamp` N1, `calling_bell` G4 | `molten_egg` G3 (`NoHookUpgrades`, 0 producers) |
| auto-keeping a skippable reward screen | `calling_bell` G3 — deliberate-divergence | `lost_coffer` G1 |

**One tension worth naming, not a disagreement.** `bag_of_marbles` guard G2 files
`HittableEnemies` → `living_enemies()` as a **gap**; this batch files the same
substitution as **faithful** at three sites (`lost_wisp` N4,
`mercury_hourglass` N3, `mr_struggles` N3). They are consistent because the
mechanism under verdict differs: Bag of Marbles routes through `PowerCmd.apply`,
which has **no** `should_allow_hitting` backstop (`power_cmd` G6), whereas
`DamageCmd.deal` applies the predicate itself at `cmds.py:51-52`, so for a damage
call site the two enemy sets are observationally identical. Every one of the four
records now says so explicitly, so a future reader does not "fix" the
consistency in the wrong direction.

**One fix-ordering constraint** (`massive_scroll` N2). `RelicModel.IsAllowedAtNeow(player)`
**defaults to `IsAllowed(player.RunState)`** (`RelicModel.cs:443-446`) — one member
with an override point, not two independent gates. The sim has
`Relic.is_allowed_at_neow` and **no** `is_allowed`, so `massive_scroll` hard-codes
the Neow flag to express a gate C# expresses on `IsAllowed`. Same observable
today (checked: the 17 floor-gated relics are all allowed at Neow anyway since
`TotalFloor` is 1 there; `silver_crucible`/`winged_boots` gate on
`Players.Count == 1`, true in single-player; `kaleidoscope`/`scroll_boxes`
override `IsAllowedAtNeow` itself). **But when the `Relic.is_allowed(run)` fix
lands, `is_allowed_at_neow` must be made to DELEGATE to it**, or Neow's filter
silently keeps consulting a stale independent flag.

---

## Things found wrong in the shared tooling (reported, not edited)

1. **Sweep C mis-classifies `ModifyDamageAdditive` as needing a new base hook.**
   `.superpowers/sdd/content-relic-sweeps.md`'s last paragraph lists
   "`ModifyDamageAdditive` on `mystic_lighter`" among hooks that "have no `Relic`
   base method *and* are not `HookSystem` hooks", and **excludes** it from the 33
   one-relic-fix stubs on that basis. That is wrong in the more dangerous
   direction — it *shrinks* the work list. `modify_damage_additive` **is** a live
   `HookSystem` hook (`hooks.py:52-63`), it is consumed at three real dispatch
   sites (`cmds.py:57`, `previews.py:56`, `cards/thrash.py:46`), and **three
   relics already implement it** — `miniature_cannon.py:22` (audited faithful in
   this batch), `strike_dummy.py:23` and `fake_strike_dummy.py:24`. Relics are
   duck-typed hook listeners (`relics/base.py:152-154`), so no base-class
   declaration is needed. `mystic_lighter` is therefore a **one-relic fix**, not
   a "larger" one, and its stub premise ("the sim has no enchantments") is false
   for the same reason sweep C already records for six other relics —
   `enchantments.py` is ported. Recommend moving it into the 33 (→ 34) and
   re-checking the other six names in that paragraph the same way: the test
   should be "is it dispatched by `hooks.py` or `run.py`", not "does `Relic`
   declare it". *(I verified `ModifyMerchantPrice` the hard way and sweep C is
   right about that one: `git grep modify_merchant_price sts2_rl/` → 0 hits.)*

2. **Sweeps A and B are sound at this batch's units.** Sweep B's 17-relic cluster
   membership for `lucky_fysh` / `meal_ticket` / `molten_egg` is confirmed by
   execution, and its `massive_scroll` "verified CLEAN" verdict survives an
   independent check — though the reason it is clean is subtler than the sweep's
   note implies (see the `IsAllowedAtNeow`-delegates-to-`IsAllowed` constraint
   above; the sweep says "Neow already gates it" without noting that in C# the
   Neow gate *is* `IsAllowed`). Sweep A correctly places `maw_bank` in no bucket:
   its `has_item_been_bought` is `[SavedProperty]` run-level state on both sides,
   and C# has no combat-boundary override for the sim to have dropped — the fixed
   "actual assignments" column is what makes that legible.

3. **Conformance tooling note (not a fidelity finding).**
   `conformance/runner.py:180`'s `_REST_BY_KEY` maps only `HEAL` / `SMITH` /
   `REST`, so a recorded `ChooseRestSiteOption COOK` (or `DIG` / `LIFT` / `CLONE`)
   falls through to `REST_LEAVE`. Relic-provided rest-site options are therefore
   not replayable at all today, which is worth knowing before anyone treats
   `meat_cleaver` G1's omit-vs-disable positional concern as urgent.

---

## Left unverified / out

- **`meat_cleaver`'s cancel path (G2) is filed as a dormant gap, not waived**,
  and the call is arguable: the trigger is a UI affordance (which the contract
  excludes) but the divergent *consequence* is state (2 deck cards, 9 Max HP,
  and whether the rest visit is spent). If the stream owner prefers the UI
  exclusion, this is the entry to flip.
- **`mercury_hourglass` G1 / `mr_struggles` G2** carry the turn-start collapse's
  `gap` verdict, and the LIVE proof is on the `gambling_chip` × `bone_tea` pair,
  **not** on these two relics' own observables. I did not search all 9 × 14
  step-22 × step-23 pairs for a Mercury- or Struggles-specific witness; each
  record says so in as many words.
- **`molten_egg` G5** (clone vs in-place upgrade) is a `deliberate-divergence` on
  the grounds that mutating in place preserves strictly more state than
  `ClonePreservingMutability` could and the deck comparison is `(id,
  upgrade_level)`. I did not enumerate every consumer of card *identity* across
  the sim, so if something keys on object identity across a deck-add this should
  be revisited.
- **Potions stayed out of scope** (`lost_coffer` G2), including the
  `PlayerRng.Rewards`-vs-shared-rng stream half, which is a real bug-class-16
  instance the moment potions come into scope.
- No unit was mis-resolved by the roster: all 15 matched a real C# file on the
  first `skeleton` call, and **`audit/tools/name_overrides.json` needs no
  additions**.
