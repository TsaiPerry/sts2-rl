# Relic audit — batch 15 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b15` (worktree
`c:\Users\Perry\Desktop\sts2-rl-relic-b15`) · based on `audit-relic` @ `3a300d94`
**Probes:** `audit/tools/relic_probes_b15.py` (9 probes, committed, re-runnable)

`py audit/tools/harness.py validate` → **216 records, 0 invalid**.
`py audit/tools/citation_check.py audit/records/relic` → **211 records, 2632 citations,
MISSING 0, OUT-OF-RANGE 0**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 211 · invalid 0 ·
stale 0 · gaps 160 · unaudited 47`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; `git status`
showed only the 15 records, the probe module and this file.

---

## The 15 units

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `snecko_eye` | **gap** | 4 | 4 |
| `sozu` | **gap** | 3 | 4 |
| `sparkling_rouge` | **gap** | 2 | 5 |
| `spiked_gauntlets` | **gap** | 3 | 7 |
| `stone_calendar` | **gap** | 7 | 7 |
| `stone_cracker` | **gap** | 2 | 7 |
| `stone_humidifier` | **gap** | 3 | 5 |
| `strawberry` | **gap** | 3 | 3 |
| `strike_dummy` | **gap** | 2 | 6 |
| `sturdy_clamp` | **gap** | 3 | 7 |
| `sword_of_jade` | **gap** | 2 | 6 |
| `sword_of_stone` | **gap** | 4 | 7 |
| `small_capsule` | deliberate-divergence | 2 | 3 |
| `storybook` | waiver | 2 | 5 |
| `tanxs_whistle` | waiver | 2 | 5 |

12 of 15 roll up to `gap`. Obtainability proved by execution for all 15
(`b15-pool`): 5 in the transcribed grab bag (`sparkling_rouge` U,
`stone_calendar` R, `stone_cracker` U, `strawberry` C, `strike_dummy` C,
`sturdy_clamp` R), 8 via ported events (Neow ×2, Darv ×2, Tanx ×2, Tezcatara,
Sunken Statue), and `sword_of_jade` only via `sword_of_stone`'s own replacement
chain — driven end to end by `b15-swords`.

---

## LIVE gaps (5), each with its executed evidence

1. **`stone_cracker` G1 — StableShuffle is fed the draw pile BACKWARDS and
   sorted on the lowercase slug, so the wrong two cards are upgraded.** The sim
   stores the draw pile top-at-END (`player.py:264-266` reverses after every
   parity shuffle) and its canonical `CardModel.CompareTo` key is
   `(card.id.upper(), upgrade_level)` (`player.py:23-34`, whose docstring
   explains that `_` = 0x5F sorts after uppercase letters and before lowercase
   ones). `stone_cracker.py:18,29` passes `player.draw_pile` as-is and keys on
   `(c.id, c.upgrade_level)`. Equal-comparing cards keep incoming order under
   both `List.Sort` and Python's sort, and `UnstableShuffle` is order-dependent
   by construction (`ListExtensions.cs:33-45`). **Executed
   (`b15-cracker`), A/B-ing the shipped port against a `StoneCracker.cs`-faithful
   variant on the same seed and stream, plain 5-Strike/4-Defend starting deck:
   6 of 8 seeds produce a different opening hand — e.g. seed `89U21BV1TZ` port
   `['strike','defend','strike','defend','strike']` vs game
   `['strike+','defend','strike','defend+','strike']`.** The lowercase half is
   independently reachable: three ported adjacent id pairs order oppositely
   (`blood_wall`/`bloodletting`, `byrd_swoop`/`byrdonis_egg`,
   `jack_of_all_trades`/`jackpot`).
2. **`sozu` G1 — a mid-combat Alchemize gives a Sozu owner a potion the game
   refuses.** C# has exactly one procure entry point and its first statement is
   the gate (`PotionCmd.cs:31`); the sim has two, and `PlayerCombatState
   .add_potion` (`player.py:107-121`) has no gate. **Executed (`b15-sozu`):
   `RunState.add_potion` → `kept=False`, belt empty (correct);
   `PlayerCombatState.add_potion` → `kept=True`, belt
   `['fire_potion', None, None]`.** Four ported callers of the ungated path:
   `cards/colorless_skills.py:53` (Alchemize), `potions.py:1217`,
   `relics/delicate_frond.py:25`, `relics/petrified_toad.py:20`.
3. **`strawberry` G1 — `undo_after_obtained` clamps instead of subtracting.**
   Same mechanism as `mango` G1, whose issue text already names
   `strawberry.py:24-25 (7)`; verdict matched per rule 3. **Executed
   (`b15-strawberry`): 40/80 → take 47/87 → undo 47/80 (7 HP too high); 50/80 →
   57/87 → 57/80; exact only from 80/80.** The runner really calls it
   (`conformance/runner.py:461, 694`, grepped per rule 8).
4. **`sturdy_clamp` G1/G2 — cited and matched from
   `audit/records/seam/turn_structure.json` G1 and G2, both LIVE there.** G1: the sim
   fires `on_block_cleared` only when the clear happened, so holding Sturdy
   Clamp silently switches off Horn Cleat and Captain's Wheel. G2: the cap has
   no preventer test. **Re-executed (`b15-clamp`, driving `player.start_turn()`
   in isolation so the enemy's attack cannot eat the block): Barricade + Sturdy
   Clamp with 30 block → 10, where C#'s preventer is `BarricadePower` and the
   full 30 survives; a sentinel records `should_clear_block` and NO
   `on_block_cleared`.**
5. **`spiked_gauntlets` G1 — cited and matched from
   `audit/records/seam/hook_dispatch.json` G2, which names this relic as its executed
   witness** (Curious ×2 + Spiked Gauntlets on a 1-cost Power: game 1, sim 0).
   Re-confirmed at the source for this batch: `CuriousPower.cs:27-31` clamps its
   own result and `Hook.ModifyEnergyCostInCombat` (`Hook.cs:1573-1589`) clamps
   nowhere, so the divergence is purely the listener order. Isolated behaviour
   executed (`b15-misc`): Inflame 1 → 2, Strike 1 → 1.

Also live but recorded as another stream's fix: **`snecko_eye` G1** — the sim's
`ConfusedPower` draws its randomised cost from the legacy shared rng
(`powers.py:3873`) where `ConfusedPower.cs:53` names
`Rng.CombatEnergyCosts`, and the sim HAS that stream (`combat_rng.py:53`,
already used by `potions.py:1049`). The stream is consumed on both sides, once
per non-X card drawn, so it desynchronises the whole run for parity. The
defective line is in `powers.py`, so the **power stream owns the fix**; Snecko
Eye and Fake Snecko Eye are the only two ported appliers, so nothing else would
surface it.

## DORMANT gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `sparkling_rouge` G1 | C#'s `AfterBlockCleared` (step ~10) mapped to `on_player_turn_started` (step ~23) | any ported turn-start effect that READS the player's Strength/Dexterity or gains POWERED block/damage at turn start (executed census: **NONE** today; the two that mention Strength grant it) |
| `stone_cracker` G2, `sword_of_jade` G1 | `AfterRoomEntered(CombatRoom)` collapsed onto `on_combat_start` = `BeforeCombatStart` | a `BeforeCombatStart` relic/power that edits the draw pile, grants/reads Strength, or draws from a stream an `AfterRoomEntered` relic also uses |
| `spiked_gauntlets` G2 | plain vs Late phase (= `hook_dispatch` G3, `brilliant_scarf` G2) | already live-shaped with Brilliant Scarf held; labelled dormant only because I did not execute the two-relic co-occurrence |
| `spiked_gauntlets` G3 | dispatcher's `originalCost < 0` X-cost bail has no sim analogue | an X-cost POWER card (executed: 3 X-cost ported cards, **0** Powers) |
| `snecko_eye` `AfterObtained` | mid-combat pickup applies Confused in C#, nothing in the sim | any content that calls `add_relic` while a `CombatState` is live (same shape as `belt_buckle`'s `AfterObtained`) |
| `stone_humidifier` G1 | `Hook.AfterRestSiteHeal` has TWO C# dispatch sites; only `HealRestSiteOption.cs:109` is ported | porting `MendRestSiteOption` (`MendRestSiteOption.cs:135`) — multiplayer-shaped, so possibly a permanent exclusion, but filed as a gap per rule 1 |
| `strike_dummy` G1 | `props.IsPoweredAttack()` hoisted from the listener to the call site (`cmds.py:56`) — class 27 | the first `ModifyDamageAdditive` implementer that must run on UNPOWERED damage (executed: **11/11** C# implementers gate on `IsPoweredAttack`) |
| `strike_dummy` G2 | C# pays when EITHER the dealer is the owner OR the Strike card is the owner's; the port needs the dealer | a Strike-tagged card whose damage is dealt by a non-player dealer (executed: **8/8** ported strike-tagged cards pass `dealer=ctx.player`); synthetic call shows sim 6 vs C# 9 |
| `stone_calendar` G1 | three-pass `BeforeSideTurnEnd` flattened (= `turn_structure` G12) | a VeryEarly/Early turn-end listener that kills an enemy, grants enemy block, or ends the combat |
| `stone_calendar` G2 | `living_enemies()` vs `HittableEnemies` (= `bag_of_marbles` G2) | a relic-damage path that bypasses `DamageCmd` — at THIS site `cmds.py:48-49` applies the missing predicate, which is why it is closed here and live-shaped at the power site |
| `sturdy_clamp` G3 | C# skips `ClearBlock()` entirely on the player's turn 1 (`Creature.cs:681-691`); the sim caps anyway | any ported effect that gives the PLAYER block before turn 1 (executed AST census: the only combat-start block grant is `PlatingPower`, enemy-side only) |
| `sword_of_stone` G1 | `AfterCombatVictoryEarly` is a separate earlier pass (= class 25) | a second victory-side listener whose effect depends on the relic list |

---

## Things I found wrong in shared tooling or seam records
### (reported, not edited — those files are read-only to this batch)

1. **`audit/records/seam/hook_dispatch.json` G2 cites `relics/spiked_gauntlets.py:26-32`
   and the file has 31 lines.** `citation_check.py` caught it the moment I quoted
   the seam text verbatim into `spiked_gauntlets.json` (OUT-OF-RANGE 1). My
   record now says `:26-31` with the discrepancy noted inline. The seam record
   itself still carries the stale range — one line, cosmetic, but it is exactly
   the class of defect `citation_check` exists to catch, and it currently sits
   inside a record the checker does not scan (`citation_check audit/records/relic`
   reads 211 relic records; the seam records are a separate tree). **Suggest
   running `citation_check` over `audit/records/seam` too.**

2. **The batch-15 brief's pre-diagnosis for `sword_of_stone` reproduces sweep
   A's already-fixed defect 3.** The brief says "Sweep A candidate
   (`elites_defeated`; C# resets at `AfterCombatVictory`)". `AfterCombatVictory`
   does not reset the field — it INCREMENTS it (`SwordOfStone.cs:44`) — and the
   field is `[SavedProperty]`, i.e. per-run by design. The **fixed** sweep gets
   this right: re-running `py audit/tools/relic_probes.py sweep-reset` prints
   `C# resets: NONE (may be per-run by design)` for this relic. So the sweep is
   sound here and the *brief* is stale, carrying the pre-rewrite wording. Worth
   fixing in the remaining batch prompts (b16–b18) before they mislead someone
   into filing a false gap on a correct relic — exactly the `nunchaku` /
   PROMPT.md class 24 trap, arriving via the prompt instead of a docstring.

3. **Sweep D's over-report correction holds up.** `stone_cracker` appears in
   `sweep-upgrade`'s "guarded (for contrast)" bucket, and the sweeps document
   records that an earlier 3-line-window version false-flagged it. Confirmed on
   the merits: `stone_cracker.py:18` pre-filters on `is_upgradable`
   (`cards/base.py:168-170` = `CardModel.cs:785-789`). No action needed; noted
   because it is the one place a sweep's *clearance* was checked and was right.

4. **No unit in this batch was mis-resolved by the roster** and
   `audit/tools/name_overrides.json` needs no additions. All 15 PascalCase C#
   files matched on the first try, including `TanxsWhistle.cs`.

---

## New / sharpened bug-class material for PROMPT.md

**(a) A NEW class — "the sim's own canonical helper exists and the port
reimplements it wrong."** `stone_cracker` G1 is not a missing concept and not a
misread constant: `player.py:23-34` already holds the correct
`CardModel.CompareTo` key *with a docstring explaining the ordinal/underscore
trap*, and `player.py:264-266` already documents that the draw pile is stored
reversed. The port ignored both and hand-rolled `(c.id, c.upgrade_level)` over
`player.draw_pile`. The detection rule is cheap and mechanical: **whenever a
port sorts or shuffles cards, diff its key against `player._compare_to_key` and
check the pile orientation.** The sibling site
`relics/fragrant_mushroom.py:33-37` copies the same lowercase key (over the
DECK, so only the key half applies) — **not in this batch, so no verdict is
issued for it**; it belongs to whichever batch owns `fragrant_mushroom`. Both
sites plus `stable_shuffle`'s callers in `actmap.py`/`events/` are the pool-wide
shape. The memory note "StableShuffle tie order — pass piles in the game's
top-first orientation and sort on the UPPERCASE id" already states the rule;
what was missing was anyone checking the relic ports against it.

**(b) A POOL-WIDE SHAPE — the `AfterRoomEntered(CombatRoom)` → `on_combat_start`
collapse, 12 relics.** Executed census (`b15-censuses`):
`bronze_scales`, `ember_tea`, `ghost_seed`, `girya`, `gorget`,
`oddly_smooth_stone`, `philosophers_stone`, `red_skull`, `stone_cracker`,
`sword_of_jade`, `throwing_axe`, `vajra` all put an `AfterRoomEntered` combat
effect on `on_combat_start`, which IS `Hook.BeforeCombatStart` — **one dispatch
later**. `CombatRoom.cs:228` fires `AfterRoomEntered` right after
`SetUpCombat` (which has already cloned and shuffled the draw pile,
`Player.cs:802-811`), and only then does `AfterCombatRoomLoaded →
StartCombatInternal` reach `BeforeCombatStart` (`CombatManager.cs:380-403`). So
C# guarantees every `AfterRoomEntered` relic acts before every
`BeforeCombatStart` relic and the sim flattens both groups into one walk in
acquisition order. Class 20 (wrong site) × class 25 (a two-pass guarantee
destroyed). **Dormant today, and the dormancy is executed rather than assumed:**
an AST scan of all 23 sim `on_combat_start` bodies finds the only cross-group
state overlap is the draw pile (`stone_cracker` on the `AfterRoomEntered` side,
`tea_of_discourtesy` on the `BeforeCombatStart` side) and that pair is provably
order-free — Dazed has `max_upgrade_level 0` so it never enters Stone Cracker's
candidate list, Stone Cracker never changes the pile's SIZE so it cannot move
Tea's `NextInt(Cards.Count + 1)` insert positions, and the two use DIFFERENT
streams (`CombatCardSelection` vs `Shuffle`). **No two combat-start relics on
opposite sides of the collapse share an RNG stream at all.** This is also
the *sixth* place `AfterRoomEntered` has turned out to be load-bearing (sweep A
defect 6 was the same hook), so it is worth stating once in PROMPT.md rather
than rediscovering: **`AfterRoomEntered` on a CombatRoom is NOT
`BeforeCombatStart`.**

**(c) Sharpening class 29 (siblings may differ on purpose) with its converse.**
`sparkling_rouge` is the *inverse* trap: the game has exactly three
`AfterBlockCleared` relics and the other two (`CaptainsWheel`, `HornCleat`) are
ported onto the sim's `on_block_cleared` with the identical
`target is self.player and self.turn == N` shape. When N−1 siblings agree and
one does not, the odd one out is the port error — and it is the cheapest
possible evidence that the correct sim hook exists and is in use. Class 29 says
"never copy a sibling's verdict"; the complement is **"always enumerate the
siblings"**, because the disagreement itself is the finding.

**(d) An incidental observation, not mine to verdict.**
`relics/delicate_frond.py:25` uses `self.combat._rng` (the legacy shared rng)
for its potion pick even in parity mode, where `AlchemicalCoffer`/`DelicateFrond`
go through `PotionCmd.TryToProcure` and the game names
`Rng.CombatPotionGeneration`. Turned up by the `b15-censuses` stream scan while
settling `stone_cracker` G2. `delicate_frond` is not in this batch — flagged for
whichever batch owns it (class 16).

## Left unverified / out of scope

- `spiked_gauntlets` G2's Late-phase interaction with `brilliant_scarf` on a
  fifth-card turn is **arithmetically derived, not executed** — I did not build
  the two-relic combat. It is labelled dormant for that reason; the seam's own
  G3 witness (Tangled Early × Free Attack Late) is already LIVE and carries the
  mechanism, so nothing rests on this leg.
- `stone_calendar` N3 notes that `DamageCmd.deal` has no dead-DEALER bail where
  `CreatureCmd.cs:238-262` does, and no per-target `IsDead` re-check. Both are
  cross-cutting `cmds.py` properties rather than this relic's, and I did not
  chase whether another site makes them observable.
- The OnPlay fidelity of `brightest_flame` and `whistle` (granted by
  `storybook` / `tanxs_whistle`) belongs to the CARD stream; I verified only
  type, cost, upgrade ceiling and eternal-ness against the C# constructors.
