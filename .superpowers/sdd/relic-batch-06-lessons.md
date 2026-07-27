# Relic content audit — batch 6 lessons and report

**Date:** 2026-07-26 · **Branch:** `audit-relic-b06` (based on `audit-relic` @ `4542c32f`)
**Probes:** `py tools/audit/relic_probes_b06.py` (9 probes, committed, re-runnable)
**Gates:** `harness.py validate` → 66 records, **0 invalid** ·
`citation_check.py audits/relic` → 707 citations, **MISSING 0, OUT-OF-RANGE 0** ·
`audit_status.py --kind relic` → total 258 · audited **61** · invalid 0 · stale 0 ·
gaps 43 · unaudited 197 · `pytest test/ -q` → **2476 passed, 31 xfailed** (unchanged)

No engine code was touched. `git status` shows only the 15 records, this file and
`tools/audit/relic_probes_b06.py`.

---

## The 15 units

| Unit | Rollup | Hooks | Guards | LIVE gaps |
|---|---|---|---|---|
| `fiddle` | **gap** | 4 | 6 | 1 |
| `fishing_rod` | deliberate-divergence | 4 | 5 | 0 |
| `forgotten_soul` | **gap** | 2 | 6 | 0 |
| `fragrant_mushroom` | **gap** | 3 | 7 | 1 |
| `fresnel_lens` | **gap** | 4 | 6 | 1 |
| `frozen_egg` | **gap** | 5 | 9 | 1 |
| `fur_coat` | **gap** | 5 | 9 | 2 |
| `gambling_chip` | **gap** | 2 | 8 | 0 |
| `game_piece` | **gap** | 3 | 6 | 1 |
| `ghost_seed` | **gap** | 3 | 7 | 0 |
| `girya` | **gap** | 6 | 8 | 1 |
| `glass_eye` | **gap** | 2 | 11 | 4 |
| `glitter` | **gap** | 2 | 7 | 0 |
| `gnarled_hammer` | **gap** | 3 | 6 | 1 |
| `golden_compass` | waiver | 5 | 6 | 0 |

13 of 15 roll up to `gap`. Guard counts include the per-record R7 bookkeeping
entry (see "Rule 7" below).

---

## LIVE gaps — 13, one line each with its executed evidence

1. **`fiddle` G1 — every off-turn draw is silently vetoed.** C#'s `ShouldDraw`
   returns *true* when the current side is not the owner's (`Fiddle.cs:34-37`);
   `fiddle.py:26-29` is `return from_hand_draw` and reads no side.
   *Executed (`fiddle-draw`):* Fiddle + Centennial Puzzle, the player is hit on
   the enemy's turn → the first enemy-side `should_draw` returns **False** and the
   player enters turn 2 with **7** cards where C# gives 3 + (5+2) = **10**.
2. **`fragrant_mushroom` G1 — the wrong cards get upgraded.** The `StableShuffle`
   key is the sim's lowercase slug where `CardModel.CompareTo` compares the
   UPPERCASE ModelId Entry ordinally, and `_` (0x5F) sorts after uppercase letters
   but before lowercase ones. *Executed (`mushroom-sort`):* a deck holding
   `blood_wall` + `bloodletting` (both Ironclad Common, both upgradable) upgrades a
   **different pair from the game on 8 of 8** Niche seeds.
3. **`fresnel_lens` G1 — the whole relic is missing on a false premise.** The stub
   says "the sim has no enchantments or deck edits". *Executed (`b06-stubs`):*
   `NimbleEnchantment` is ported (`enchantments.py:412-433`),
   `NimbleEnchantment.can_enchant(Defend)` is **True**, and
   `run.add_card(Defend)` with the relic held leaves `enchantment=None` — the sim
   drops +2 Block on every Block card the player ever gains.
4. **`gnarled_hammer` G1 — same shape, same false premise.** *Executed
   (`b06-stubs`):* `SharpEnchantment` is ported (`enchantments.py:387-410`),
   `add_relic('gnarled_hammer')` with a selector installed leaves **zero**
   enchanted deck cards, and Sharp accepts **6** of the 10 starting-deck cards.
5. **`frozen_egg` G1 / 6. `girya` G1 — `IsAllowed` (`TotalFloor < 41`) is
   unmodelled.** *Executed (`b06-isallowed`):* `'is_allowed' in dir(Relic)` is
   **False** while `is_allowed_at_neow` exists; the grab bag is shuffled once at
   run init (`relic_pools.py:186-198`); the only per-pull predicate in the pull
   path is `is_allowed_in_shops` (`run.py:592, 614, 626`); both relics are Rare in
   the bag and `RunState.total_floor` already exists. Confirms sweep B's 16-relic
   cluster; same verdict as `amethyst_aubergine` per rule 3.
7. **`fur_coat` G1 — the 1-HP effect never fires in a later act, and in the game
   it does.** `FurCoat.BeforeCombatStart` (`FurCoat.cs:116-120`) tests coord
   membership with **no act check**; `fur_coat.py:75` adds one. *Executed
   (`fur-coat-acts`):* of 7 act-0 marked coords, **1 / 5 / 7 / 4** still exist on
   the act-1 map on seeds 7 / 11 / 23 / 42, several as MONSTER and ELITE points.
8. **`fur_coat` G2 — the sim runs `ModifyGeneratedMapLate` where the game does
   not.** `Hook.ModifyGeneratedMapLate` has exactly ONE caller in the whole game,
   `RunManager.cs:740`, inside the **save-load** branch of `GenerateMap`; the
   fresh-generation branch (`:745-747`) runs only `ModifyGeneratedMap` and
   `AfterMapGenerated`. `run.py:857-860` runs it on every generation. *Executed
   (`b06-misc`):* Fur Coat + Golden Compass in the same act re-rolls the marks
   `(1,2)(2,6)(3,12)(3,13)(4,12)(5,6)(6,13)` → `(3,1)(3,3)(3,5)(3,13)(3,15)` and
   burns an extra Fur Coat rng shuffle. **New pool-wide shape — see below.**
9. **`game_piece` G1 — a replayed Power draws 1 card instead of 2.** *Executed
   (`piece-replay`):* Game Piece + Throwing Axe + Inflame gives **Strength 4**
   (proving two resolutions) and **1** card drawn. Same mechanism as
   `hook_dispatch` G4 / `unsettling_lamp` G1, new observable.
10–13. **`glass_eye` G1–G4 — four independent live gaps on one hook.**
   *Executed (`glass-eye`):*
   - **G1:** `PlayerRng.Rewards` counter 0 → **15** where the game reaches **30** —
     `RollForUpgrade`'s `rng.NextFloat()` fires *before* the `IsUpgradable` test
     (`CardFactory.cs:288-304`), so 15 draws are never consumed and every later
     reward roll in the run is shifted (same family as `calling_bell` G2).
   - **G2:** the port's "never upgraded" docstring is **false** — odds are
     `act_index * 0.25` for non-Rares (`GetValueIfAscension(level, ascension,
     fallback)` → the non-ascension arm is 0.25, matching `rewards.py:112`), so from
     act 1 on the game upgrades them and the sim never can.
   - **G3:** `CardFactory.CreateForReward` fires `Hook.TryModifyCardRewardOptions`
     (**both** phases, `CardFactory.cs:104`, `Hook.cs:1445-1468`); the port never
     dispatches `modify_card_reward_options`. With Glitter in the run, all five
     granted cards came out `enchantment=None`.
   - **G4:** the candidate pool is `pool_card_ids()` (FilterForCombat) where a
     reward uses `GetUnlockedCards`; reward-eligible ids it drops are exactly
     **`feed` and `not_yet`, both Rare** — permanently absent from Glass Eye's
     Rare screen. `reward_pool_card_ids()` already exists for this.

---

## DORMANT gaps — each with the concrete unported thing that would make it live

| Unit | Gap | What would make it live |
|---|---|---|
| `fiddle` G2 | `ModifyHandDraw`**Late** collapsed into one flat pass | a second CLAMPING or multiplicative hand-draw modifier; today only MindRot clamps, and it needs amount ≥ 6 against a base of 5 |
| `forgotten_soul` G1 | `HittableEnemies` vs `living_enemies()` (= `bag_of_marbles` G2) | a longer-lived untargetable state, or a second `should_allow_hitting` implementer — the only one, `IllusionPower.is_reviving`, needs another live enemy beside it |
| `fragrant_mushroom` G2 | `CreatureCmd.Damage` replaced by `RunState.lose_hp` (no run-level notification pipeline; = `hook_dispatch` step 46) | porting a relic that REACTS to out-of-combat HP loss rather than modifying it |
| `frozen_egg` G2 | `CardCreationFlags.NoHookUpgrades` bail dropped; the sim has no flags concept (executed: `'CardCreationFlags' in dir(hooks)` = False) | porting any C# caller that creates cards `WithFlags(NoHookUpgrades)` |
| `frozen_egg` G3, `glitter` G1 | `CloneCard` vs in-place mutation (class 17) | a stackable enchantment, or an effect holding a handle on a card across `add_card` / across the reward pick |
| `frozen_egg` G4, `glitter` G2 | `TryModifyCardRewardOptions`**Late** collapsed | a **plain**-phase reward-option listener whose decision reads the upgrade level or the enchantment; today upgraders and enchanters commute |
| `fur_coat` G3 | raw `enemy.hp = 1` vs `CreatureCmd.SetCurrentHp`, which fires `Hook.AfterCurrentHpChanged` | a player- or power-side `on_hp_changed` listener that reads enemy HP (today the only one is `red_skull`, player-only), or fixing `hook_dispatch` G5 so monsters are listeners (Crusher/Rocket override it) |
| `gambling_chip` G1 | `DiscardAndDraw` auto-plays every discarded **Sly** card after the draw (`CardCmd.cs:188, :201-204`) | porting the Sly keyword — executed: `git grep -in 'is_sly\|CardKeyword.Sly' -- sts2_rl` returns **zero** hits |
| `gambling_chip` G2 | raw list mutation vs `CardPileCmd.Add` | porting an `AfterCardChangedPiles(Late)` listener (`SoulFysh.cs` is the ported-monster example) |
| `ghost_seed` G1, `girya` G2 | the effect lands at `BeforeCombatStart`, two dispatch points after C#'s `AfterRoomEntered` (`CombatRoom.cs:228` → `CombatManager.cs:394-403`) | anything in the `AfterCreatureAddedToCombat` window that reads card keywords (ghost_seed) or player Strength (girya); executed censuses found every Ethereal reader at turn end and every combat-start Strength toucher a writer, not a reader |
| `ghost_seed` G2 | `GetKeywordsWithSources(Local)` vs one boolean | a Basic Strike/Defend entering combat while **Hexed** (`HexPower`, ported, applied by Spectral Knight) — Hex's removal restores the stashed flag and would take Ethereal back where C#'s local keyword survives |
| `glass_eye` G5 | C# populates all five screens before offering; the sim interleaves populate → pick → `add_card` | a reward-option listener whose candidate set depends on deck contents |
| `fresnel_lens` G2 | the (unimplemented) site would inherit class 17 | recorded pre-emptively so a fix that enchants in place is a stated choice |

---

## New bug classes / pool-wide shapes

### A. A dropped-in sim hook can be dispatched from the WRONG SITE, not just the wrong slot (`fur_coat` G2)

Bug class 11 warns that the sim's docstring mapping may put a hook in the wrong
*turn slot*. `fur_coat` is a different failure: the sim dispatches
`modify_generated_map_late` on **every** fresh map generation
(`run.py:857-860`), while `Hook.ModifyGeneratedMapLate` has exactly **one**
caller in the shipping game — `RunManager.cs:740`, inside the branch that
deserializes a **saved** map. The fresh-generation branch (`:745-747`) runs the
plain pass and `AfterMapGenerated` only. So the hook's real purpose is to
re-attach state to a loaded map, and a sim that runs it eagerly re-derives state
the game preserves.

**Method that finds it, and it is cheap:** for any phase-suffixed or
lifecycle hook, `grep -rn <HookName> src/` **excluding `AbstractModel.cs` and
`Hook.cs`** and read every dispatch site's enclosing branch — not just its
existence. Two implementers here, and the second one, `Cards/SpoilsMap.cs:63`,
has the identical exposure: **reported for the card stream, not verdicted.**

### B. `StableShuffle` over cards must sort on the UPPERCASE id — three ported pairs invert (`fragrant_mushroom` G1)

`ModelId.CompareTo` is an **ordinal** compare over the game's uppercase Entry
(`ModelId.cs:42-50`). `_` is 0x5F, uppercase A–Z are 0x41–0x5A and lowercase
a–z are 0x61–0x7A, so any two ids that first differ at a `_`-versus-letter
position sort the opposite way in the two cases. An executed census over all 203
ported card ids finds exactly **3** inverting pairs — `blood_wall`/`bloodletting`
(both Ironclad Common, both upgradable, so co-present), `byrd_swoop`/`byrdonis_egg`,
`jack_of_all_trades`/`jackpot`.

The sim **already has the right key**: `player.py:23-35`'s `_compare_to_key`
returns `(card.id.upper(), card.upgrade_level)` and its docstring names two of
the three pairs. So this is a defect, not a house style. Sites passing a
lowercase key:

| Site | Status |
|---|---|
| `relics/fragrant_mushroom.py:35` | **LIVE**, recorded (this batch) |
| `relics/stone_cracker.py:29` | same defect, `CombatCardSelection` stream — **reported, not verdicted** (another batch's unit) |

The fix is one argument per site. Any kind whose ports StableShuffle cards should
grep for `key=lambda c: (c.id` before auditing.

### C. "The sim has no X" stubs remain the highest-yield shape, and the enchantment premise is now proven false twice

`fresnel_lens` and `gnarled_hammer` both rest on "no enchantments in the sim".
Nimble, Sharp **and** Glam are all ported with faithful `can_enchant` bodies. That
makes **four** false-premise stubs found by per-unit audits (Amethyst Aubergine,
Big Mushroom, plus these two), all LIVE. Sweep C's headline — *every* stub premise
it could test is false — held on both units in this batch without exception.

### D. Two calibration corrections worth carrying into `PROMPT.md`

- **`AscensionHelper.GetValueIfAscension(level, ascensionValue, fallbackValue)`
  puts the ASCENSION value FIRST** (`AscensionHelper.cs:40-47`). So
  `GetValueIfAscension(Scarcity, 0.125m, 0.25m)` has a non-ascension value of
  **0.25**, not 0.125. I nearly filed `rewards.py:112`'s
  `UPGRADED_CARD_ODD_SCALING = 0.25` as a wrong constant on that misreading; the
  sim is correct. The contract's "take the non-ascension branch" instruction needs
  the argument order spelled out.
- **The `sweep-reset` table's "C# resets: [Hook]" column is an AST fact about
  which combat-boundary hooks the C# relic OVERRIDES, not about what those hooks
  do.** It produced two false positives in this batch — `FishingRod.AfterCombatEnd`
  *increments* the counter and `FurCoat.BeforeCombatStart` *applies the effect*;
  neither resets anything, and both fields are `[SavedProperty]`, i.e. per-run by
  design. The batch brief inherited the misreading ("`fishing_rod` — Sweep A
  candidate; C# resets at `AfterCombatEnd`"). Both settled by execution; the
  column should be renamed something like "C# combat-boundary overrides".

### E. A rule-15 observation that cuts across records, not within one (`game_piece` N1)

Bug class 15 says paired hooks on ONE unit rarely carry the same guard set. The
same C# hook on TWO relics also carries different guard sets:
`BrilliantScarf.AfterCardPlayed` bails on `cardPlay.IsAutoPlay` and
`GamePiece.AfterCardPlayed` does not. The sim counts auto-plays in both — which
is `brilliant_scarf`'s LIVE gap G1 and `game_piece`'s **correct** behaviour. When
a batch meets a hook a previous batch already audited, diff the C# guard sets
before reusing the earlier verdict.

---

## Pre-diagnosed units — all seven settled

| Unit | Sweep said | Settled as |
|---|---|---|
| `fiddle` | `hook_dispatch` step 35: sole `AfterPreventingDraw` implementer, presentation-only body | **confirmed** — waiver, citing and matching the seam per rule 3. The real gap is elsewhere in the same relic (G1, LIVE) |
| `fishing_rod` | Sweep A candidate, "C# resets at `AfterCombatEnd`" | **corrected** — the reading is wrong (see D); `combats_seen` is per-run on both sides, executed |
| `fresnel_lens` | Sweep C stub; "no enchantments" is FALSE | **confirmed and executed** — 3 LIVE hook gaps |
| `frozen_egg` | Sweep B `IsAllowed`, 16-relic cluster | **confirmed and executed** — LIVE |
| `fur_coat` | Sweep A candidate (`_armed`/`act_index`/`marked_coords`); settle by execution | **cleared by execution** — `_armed` is unconditionally re-derived at every room entry (`fur_coat.py:74`, `run.py:981-983`), the other two are per-run; the relic's two real LIVE gaps are unrelated to the reset question |
| `girya` | Sweep B `IsAllowed`, 16-relic cluster | **confirmed and executed** — LIVE |
| `gnarled_hammer` | Sweep C stub; "no enchantments" is FALSE | **confirmed and executed** — LIVE |

## Cross-record consistency (binding rule 3)

Seven mechanisms already carried a verdict elsewhere; all seven are reproduced
with the **same** verdict, cited, not re-derived: `AfterPreventingDraw`
(`hook_dispatch` step 35), per-Replay `AfterCardPlayed` (`hook_dispatch` G4 /
`unsettling_lamp` G1), missing Early/Late phase passes (`hook_dispatch` G3),
`HittableEnemies` vs `living_enemies()` (`bag_of_marbles` G2), `IsAllowed`
(`amethyst_aubergine`), shallow clones (`burning_sticks` G3), the hook-slot shape
(`anchor` N3), and the auto-keep player-choice model (`calling_bell` G3).

**No cross-record disagreement was found.** Two tensions worth naming:

- **`game_piece` N1 vs `brilliant_scarf` G1** — the same C# hook, opposite guard
  sets, so the sim is right on one and wrong on the other. Not a disagreement,
  but a fixer who "fixes" auto-play counting globally would break Game Piece.
- **`gambling_chip` G2** — the sim's two discard sites disagree with each other:
  `gambling_chip.py:33-35` appends to the discard pile then fires
  `on_card_discarded` (the C# order), where `player.discard_hand`
  (`player.py:188-196`) fires the hook first. Recorded on the relic; the
  `discard_hand` half is engine code and belongs to whoever owns `player.py`.

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file on the first `skeleton` call,
and `py tools/audit/relic_probes_b06.py b06-pool` confirms all 15 are registered
and obtainable — 5 from the transcribed grab bag (`frozen_egg`, `gambling_chip`,
`game_piece`, `girya` Rare; `ghost_seed`, `gnarled_hammer` Shop; `fresnel_lens`
Event) and the rest from ported events/shrines (Vakuu, Neow, Grave of the
Forgotten, Hungry for Mushrooms, Drowning Beacon, Nonupeipe ×2, Orobas,
Tezcatara). **No `name_overrides.json` entry is needed.**

## Rule 7 (unhashed citations)

Each record ends with an `R7` bookkeeping guard listing **every** third-party file
it cites by line and does not hash, so `citation_check`'s UNHASHED reminder is
answered explicitly rather than only for the individually load-bearing ones (which
are also named inline in the entry that leans on them). Counts range from 3
(`fishing_rod`) to 20 (`fiddle`).

## Left out / unverified — stated plainly

- **Verdicts reported, not applied, in files this batch does not own:**
  `relics/stone_cracker.py:29` (shape B, another batch's unit),
  `Cards/SpoilsMap.cs` (shape A, card stream), `player.discard_hand`'s hook order
  (engine). The three shared files that every batch would conflict on
  (`relic_probes.py`, `PROMPT.md`, `content-relic-sweeps.md`,
  `content-relic-report.md`) were read but **not edited**, per the concurrency
  contract.
- **`glass_eye` G2's act-1 upgrade was NOT executed as a divergence**, only as
  arithmetic: the probe drives an act-0 run, where the odds are 0 on both sides
  and the two agree. The C# odds formula and the sim's total absence of the roll
  are both executed facts; the *observed* difference in a specific act-1 run is
  not. Labelled LIVE anyway because both sides are reachable and act 0 is the one
  act where the numbers coincide.
- **`fur_coat` G1's cross-act firing was demonstrated by coordinate overlap, not
  by walking a run into act 1 and entering the marked node.** The probe proves the
  coords survive and that the sim's act guard refuses to arm; it does not drive a
  full two-act run.
- **`enchantments.py`'s own fidelity was spot-checked, not audited.** Nimble,
  Sharp and Glam were read in full and their `can_enchant` bodies compared against
  `EnchantmentModel.CanEnchant`; one narrowing was found (the sim refuses an
  Unplayable card in ANY pile where C# only refuses one in the Deck pile) and is
  **recorded but not verdicted** (`glitter` N3) because `audits/enchantment/**`
  belongs to the event+enchantment stream and is not on this branch.
- **`gambling_chip`'s `CardPileCmd.Add` chain was read but the sim's combat-pile
  hook surface was not exhaustively censused** — the dormancy argument rests on
  `after_card_added_to_deck` being the sim's only pile-change hook and on
  `hook_dispatch` owning `AfterCardChangedPiles`.
- **No potion interactions were audited** (out of scope per the contract); none of
  the 15 units touches potions.
