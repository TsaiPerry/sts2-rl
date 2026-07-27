# Relic content audit — batch 14 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b14` (from `audit-relic` @ `3a300d94`)
**Probes:** `tools/audit/relic_probes_b14.py` (18 probes, all executed)
**Checks:** `harness.py validate` → 216 records, 0 invalid ·
`citation_check.py audits/relic` → 2661 citations, MISSING 0, OUT-OF-RANGE 0 ·
`audit_status.py --kind relic` → 211 audited, 0 invalid, 0 stale ·
`pytest test/ -q` → **2476 passed, 31 xfailed** (baseline, unchanged)

---

## The 15 units

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `runic_pyramid` | gap | 2 | 4 |
| `sai` | gap | 2 | 4 |
| `sand_castle` | **gap (LIVE ×1 + RNG)** | 3 | 6 |
| `screaming_flagon` | **gap (LIVE ×1)** | 2 | 6 |
| `scroll_boxes` | gap | 3 | 8 |
| `sea_glass` | gap | 4 | 5 |
| `seal_of_gold` | **gap (LIVE ×1)** | 2 | 6 |
| `self_forming_clay` | **gap (LIVE ×2)** | 2 | 7 |
| `sere_talon` | gap (RNG) | 3 | 7 |
| `shovel` | **gap (LIVE ×1)** | 3 | 6 |
| `shuriken` | deliberate-divergence | 6 | 6 |
| `signet_ring` | gap | 2 | 5 |
| `silken_tress` | **gap (LIVE ×1)** | 5 | 7 |
| `silver_crucible` | **gap (LIVE ×1)** | 9 | 9 |
| `sling_of_courage` | gap | 2 | 5 |

14 of 15 roll up to `gap`; `shuriken` is the one clean-ish unit
(deliberate-divergence on two slot moves, both proved unobservable).

---

## LIVE gaps, one line each with the executed evidence

1. **`sand_castle` G1 — the relic upgrades the WHOLE deck, not 6 cards.**
   `SandCastle.cs:24-25` is `.Where(IsUpgradable).StableShuffle(Rng.Niche).Take(CardsVar(6))`;
   `sand_castle.py:16-18` has no `Take`. Executed (`relic_probes_b14.py sand-castle`):
   `add_relic('sand_castle')` upgrades **10 of 10** starting-deck cards where the game
   upgrades 6. The port's own docstring asserts the wrong rule ("upgrade ALL upgradable
   cards"). Sibling `fragrant_mushroom` implements the identical C# idiom correctly.

2. **`self_forming_clay` G1 — pending Block crosses the combat boundary.**
   C# banks it in a `SelfFormingClayPower` that dies with the combat
   (`SelfFormingClayPower.cs:19-25`); the sim banks it on the relic instance, which lives on
   `RunState.relics`. Executed with ported content only (`clay-carry`): Hemokinesis as the
   killing blow leaves `_pending_block = 3`, and the next combat opens **turn 1 with 3
   Block** where a fresh instance gives 0.

3. **`self_forming_clay` G2 — the payout slot moved from `AfterBlockCleared` to
   `on_player_turn_started`.** Executed (`clay-slot`): with `[royal_poison,
   self_forming_clay]` the sim opens turn 1 with **block 3**, with
   `[self_forming_clay, royal_poison]` with **block 0**; C# gives 0 in both cases because
   Royal Poison's self-damage (`RoyalPoison.cs:18`, step 22) lands after the block clear.

4. **`seal_of_gold` G1 — gold gained IN combat is invisible to the relic.**
   `seal_of_gold.py:25` computes `player_gold - gold_stolen - gold_spent` and omits
   `combat.gold_gained`; `powers.py:1660` (Thievery) computes the same balance and includes
   it. Executed (`seal-gold`): entering with 4 gold and banking Hand of Greed's +20 leaves
   turn 2 at **energy 3, gold_spent 0**, where C# gives 4 energy and spends 5.

5. **`silver_crucible` G1 / `silken_tress` G1 — both relics drop C#'s
   `IsCardReward` flag gate.** The flag is set by `CardReward`'s constructors only
   (`CardReward.cs:113-115`, `:134`); the sim's `modify_hooks` parameter is `NoModifyHooks`,
   a different flag. Executed (`card-reward-flag`): Lead Paperweight's pickup offers
   `[('restlessness', 1, 'glam'), ('impatience', 1, 'glam')]` and moves
   `times_used 0→1` / `is_used False→True`, where C# offers two unmodified level-0 Colorless
   cards and spends neither charge. Brain Leech's SHARE_KNOWLEDGE fires wrongly too, and its
   RIP arm — a real `new CardReward` in C# — **fails to fire** (the two arms are inverted).

6. **`shovel` G1 — the `TotalFloor < 41` pool gate is unmodelled.**
   C# enforces `IsAllowed` in the *pull* path (`RelicGrabBag.GetAvailableDeque` →
   `RemoveDisallowedRelicsFromDeques`, `RelicGrabBag.cs:218-225`), not at population.
   Executed (`shovel`): `hasattr(Relic, 'is_allowed')` is False, shovel is still in the bag
   at `total_floor = 60`, and 400 post-floor-41 pulls returned it once. Confirms sweep B
   cluster (a) and adds the enforcement point sweep B did not name.

7. **`screaming_flagon` G2 — Pael's Eye deletes the Flagon's whole trigger.**
   `combat.py:648-652` asks `ShouldTakeExtraTurn` *first* and returns; C# asks it *last*
   (`CombatManager.cs:1366`). Executed (`flagon`): empty hand, 200-HP enemy →
   `[screaming_flagon]` leaves 180, `[paels_eye, screaming_flagon]` leaves **200**; C# deals
   20 either way. The two triggers *co-occur by construction* — Pael's Eye fires when you end
   a turn having played no cards, which is the likeliest way to end it with an empty hand.

8. **`runic_pyramid` G1 — cited, not re-derived.** `audits/seam/turn_structure.json` G4
   already names `relics/runic_pyramid.py:16-17` as a ported witness and labels the mechanism
   LIVE (Joss Paper's deferred Ethereal credit stranded, next hand 5 vs 6). Confirmed the
   port's own half by execution (`pyramid`): hand 5→10 with the relic, `should_flush` False.

**RNG-parity-only LIVE gaps** (live for the conformance harness, dormant for RL play — the
`astrolabe` N1 precedent): `sand_castle` G2 (`Rng.Niche` unconsumed, executed niche counter
0→0 where the sibling moves 0→9), `sere_talon` N1 (same, and `rng.sample` is not
`NextItem`+`Remove`), `sea_glass` G1 (15 `CreateForReward` Rewards draws unconsumed, executed
counter 0→0).

---

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `sai` G1, `seal_of_gold` G2 | `AfterSideTurnStart` is C#'s *second* turn-start pass; the sim runs one flat walk (seam G12) | an `AfterPlayerTurnStart` listener that reads player **Block** (Sai) or **gold/energy** (Seal of Gold) — none of the 12 ported ones does; or an `AfterSideTurnStartLate` reader (SandpitPower is already in the flat pass) |
| `screaming_flagon` G1 | plain `BeforeSideTurnEnd` is C#'s *third* turn-end pass (seam G12) | fixing G2 makes it live **immediately** — once the pass runs, C# exhausts the hand in the Early pass and the Flagon then sees an empty hand. Fix-ordering constraint. |
| `scroll_boxes` G1 | both `Hook.ModifyCardRewardCreationOptions` dispatches dropped | porting `DingyRug`'s or `PrismaticGem`'s option rewrite (both relics are ported, neither implements that arm) |
| `sea_glass` N1 | the 15-card cross-character grid pick | **waived**, not dormant: `Orobas.cs:190` always assigns a character *other* than the player's, so it is genuine other-character scope (rule 1) |
| `self_forming_clay` N3 | the sim has no `SelfFormingClayPower`, so the banked Block is not a visible/removable/doubleable player power | any buff-stripping enemy move, any "double your Buffs" effect, or any listener that reads player Buff amounts |
| `shovel` G2 | the sim suppresses the DIG option on an empty bag; C# always offers it and grants `FallbackRelic` | a relic sink that drains the 122-relic bag, or content that empties a single rarity deque (C# then escalates Shop→Common→Uncommon→Rare; the sim `pop(0)`s regardless of rarity) |
| `signet_ring` N2 | `Hook.AfterModifyingGoldGained` has no sim counterpart | porting any relic that reacts to having modified a gold gain (same shape as `bag_of_preparation` N1) |
| `silken_tress` G2, `silver_crucible` G2 | `TryModifyCardRewardOptions` runs as **two** passes; the sim runs one | porting `LastingCandy`'s Power-card substitution — the game's only non-`Late` implementer, and its port is a stub |
| `silver_crucible` G3 | a suppressed treasure room still pays **Spoils Map's 600 gold** in the sim | executed: act 1's treasure row is *all* TREASURE columns so it always eats the suppression, and Spoils Map targets act 2 — needs a mid-run Silver Crucible grant, a second `ShouldGenerateTreasure` implementer, `SpoilsActIndex 0`, or a skippable treasure row |
| `sling_of_courage` N1 | the Strength lands *inside* the `on_combat_start` pass, not before it | a combat-start effect that **reads** player Strength (executed: zero of the 23 ported `on_combat_start` bodies read a power). Two-site fix — `girya` G2 goes live at the same moment |

---

## A SEVENTH sweep-A defect, and the fourth of the false-clear kind

`sweep-reset`'s bucket **"RESET AT TURN START, BEFORE ANY READER (art_of_war shape —
genuinely safe)"** makes a safety claim it does not test. It checks *which method* writes a
field; it never checks whether the write precedes the read **inside** that method.

`self_forming_clay` is in that bucket and is a LIVE gap:

```
def on_player_turn_started(self, player):
    if self._pending_block:
        BlockCmd.apply(...)        # <- the READ (the payout)
        self._pending_block = 0    # <- the "reset", AFTER it
```

That is a **consume-then-clear**, not a clear-then-read. The stale value is *spent* on the
first turn of combat 2 before it is zeroed. Executed:
`py tools/audit/relic_probes_b14.py clay-carry` → carried instance opens combat 2 with
`block=3`, fresh instance with `block=0`.

The other 12 units in that bucket were not re-checked by this batch, and the same shape can
hide in any of them. The mechanical test the bucket needs: for each field, compare the AST
statement index of the reset against the first read *within the resetting method*, and refuse
to call the field safe when the reset comes second. `shuriken` (also in the bucket) passes
that test — its reset is an unconditional bare `self._attacks_this_turn = 0` — and this batch
verified it by execution rather than by the bucket label.

That makes **seven** sweep-A defects across the stream and **four** false clears
(`red_skull`, `ruined_helmet`, `pumpkin_candle` from batch 13's unstimulated driver;
`self_forming_clay` from the static bucket's untested safety claim). The pattern from
PROMPT.md v6 item 1 holds exactly: every one was found by a batch auditing a unit on its
merits, and false clears are the direction nothing downstream re-checks.

**Sweep B was right about this batch's three units** (`shovel` → live cluster (a),
`silver_crucible` → clean multiplayer gate, `scroll_boxes` → needed a per-unit verdict), and
sweep C's `sea_glass` entry was right that `after_obtained` has a live dispatch site — though
the interesting half of that unit turned out to be the unconsumed Rewards draws, not the
missing card grant.

---

## New bug classes / pool-wide shapes

**Class candidate A — a flag the sim collapsed into a DIFFERENT flag.**
`silver_crucible` and `silken_tress` both gate on `CardCreationFlags.IsCardReward`; the sim's
`create_reward_cards(modify_hooks=...)` models `CardCreationFlags.NoModifyHooks` instead, and
those are not the same flag — one decides *whether the hook is dispatched at all*, the other
decides *whether this listener acts*. Because one identifier is doing two jobs, its four
ported callers are right or wrong by accident: two fire when C# would not
(`lead_paperweight`, `brain_leech` SHARE_KNOWLEDGE) and one does not fire when C# would
(`brain_leech` RIP). This is distinct from class 27 (a filter hoisted from listener to
dispatcher) because here the filter was *substituted* rather than moved. **Pool-wide
follow-up:** every C# guard of the form `!options.Flags.HasFlag(X)` should be swept —
`DingyRug.cs:23` and `PrismaticGem.cs:38` carry the same `IsCardReward` clause and are the
next two places to get it wrong.

**Class candidate B — a gate whose PAYLOAD differs between the two codebases.**
`silver_crucible` G3: both sides consult `ShouldGenerateTreasure` with the same predicate and
the same all-must-agree dispatcher, but C#'s gate encloses the Spoils Map payout
(`OneOffSynchronizer.cs:130-146`) and the sim's does not (`run.py:1001` vs `:1020`). Reading
the predicate, the dispatcher and the relic all match; the divergence is one indentation
level in the *consumer*. The method that finds these is to read the C# gate's whole enclosing
block, not just the call — a sibling of class 20 (wrong dispatch *site*) pointed at gates
rather than hooks.

**Shape confirmation — `AfterRoomEntered` → `on_combat_start` is a two-relic family.**
`sling_of_courage` and `girya` re-host the identical C# hook the identical way, and
`girya`'s G2 already verdicts it a dormant gap. Recorded so the fix stream treats it as one
change at two sites rather than two findings. `velvet_choker` and both tea sets also assign
inside C#'s `AfterRoomEntered` (sweep A defect 6's rescan) — a third variant of the same
family, still unaudited.

**Shared-machinery divergence found in passing, not verdicted (not this batch's unit).**
`run.pull_relic_from_front`'s empty-rarity fallback is `relic_grab_bag.pop(0)` — the front of
the bag regardless of rarity (`run.py:595`) — where C#'s `GetAvailableDeque` escalates
`Shop → Common → Uncommon → Rare` and only then falls back to the multiplayer deque
(`RelicGrabBag.cs:227-241`). Every relic-pull caller inherits this. Recorded here for the
gap-queue stream; `shovel` G2 names it in passing but the defect belongs to the pull path.

---

## Cross-record agreement (binding rule 3)

Six mechanisms already carried a verdict elsewhere; all six are reproduced with the **same**
verdict, cited, not re-derived. **No cross-record disagreement was found.**

- `ShouldFlush`'s skipped flush tail → **gap**, matching `turn_structure` G4 (`runic_pyramid`).
- the flattened `BeforeTurnEnd` / `AfterSideTurnStart` sub-phases → **gap**, matching
  `turn_structure` G12 (`sai`, `seal_of_gold`, `screaming_flagon`).
- `ShouldTakeExtraTurn` asked too early → **gap**, matching `turn_structure` G3 /
  PROMPT.md class 26 (`screaming_flagon`).
- `AfterRoomEntered` → `on_combat_start` → **dormant gap**, matching `girya` G2, which itself
  matches `anchor` N3 (`sling_of_courage`; this is what forced the unit rollup from
  deliberate-divergence to gap).
- a named RNG stream that is never consumed → **gap, live for parity only**, matching
  `astrolabe` N1 (`sand_castle` G2, `sere_talon` N1, `sea_glass` G1).
- `BeforeSideTurnStart` used for a pure counter reset → **deliberate-divergence**, matching
  `brilliant_scarf` and `beating_remnant` (`shuriken`).

One verdict deliberately *differs* from a sibling record and says so in place:
`screaming_flagon` N1 verdicts `HittableEnemies` vs `living_enemies()` **faithful** where
`bag_of_marbles` G2 verdicts it a dormant gap. Not a conflict — `bag_of_marbles` applies a
*power* and `PowerCmd.apply` has no `should_allow_hitting` backstop (`power_cmd` G6), while
the Flagon deals *damage* and `DamageCmd.deal` applies the predicate itself
(`cmds.py:51-52`), so the final target set is identical. PROMPT.md class 29's warning in
action: the sibling's verdict was re-derived, not copied. The same check went the other way on
`shuriken` N1 — C# has **no** `IsAutoPlay` exclusion, so counting auto-plays is correct there
and copying `brilliant_scarf` G1 would have filed a false gap.

## Roster mis-resolutions

**None.** All 15 units resolved to the right C# file on the first try; `roster relic` still
reports 258 sim units, 0 unmatched. `tools/audit/name_overrides.json` needs no additions.
Obtainability confirmed for all 15 by execution (`relic_probes_b14.py pool`): 5 from the
transcribed grab bag (`screaming_flagon` Shop, `self_forming_clay` Uncommon, `shovel` Rare,
`shuriken` Rare, `sling_of_courage` Shop) and 10 from ported events (Darv, Tanx, Orobas ×2,
Neow ×3, Tezcatara, Vakuu, Nonupeipe).

## Left unverified

- The other 12 units in sweep-reset's "safe at turn start" bucket were not re-checked for the
  consume-then-clear shape; only `self_forming_clay` (a hit) and `shuriken` (a pass) were.
- `scroll_boxes` N4: whether `RunState.CreateCard` has a side effect that would make the
  six-vs-three card materialisation observable. Read as side-effect-free; not executed.
- `silken_tress` N3 leans on the sim's shared `Enchantment.can_enchant` (`enchantments.py`),
  which this record does not hash — the enchantment stream owns that mechanism.
- `sea_glass` G1's exact C# draw count (15) is read from `CardFactory.CreateForReward`'s
  structure, not executed against the game; the sim side (0 draws) *is* executed.
- No fix was applied anywhere. `sts2_rl/` is untouched; the suite is at its baseline.
