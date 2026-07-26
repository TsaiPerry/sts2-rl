# Relic content audit — batch 12 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b12` (worktree
`c:\Users\Perry\Desktop\sts2-rl-relic-b12`) · **Units:** the roster's
`pen_nib` … `preserved_fog` run (15).

`py tools/audit/harness.py validate` → **141 records, 0 invalid**.
`py tools/audit/citation_check.py audits/relic` → **MISSING 0, OUT-OF-RANGE 0,
AMBIGUOUS 0** over 1663 citations.
`py tools/audit_status.py --kind relic` → `total 258 · audited 136 · invalid 0 ·
stale 0 · gaps 106 · unaudited 122`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; no engine
code was touched (`git status` shows only the 15 records and
`tools/audit/relic_probes_b12.py`).

All reachability evidence is reproducible from
`tools/audit/relic_probes_b12.py` (14 probes, own module per the concurrency
contract; `tools/audit/relic_probes.py` was read and re-used, never edited).

---

## The 15 units

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `pen_nib` | **gap** | 6 | 8 |
| `pendulum` | **gap** | 6 | 5 |
| `permafrost` | **gap** | 3 | 5 |
| `petrified_toad` | **gap** | 2 | 6 |
| `phial_holster` | **gap** | 3 | 5 |
| `philosophers_stone` | **gap** | 4 | 5 |
| `planisphere` | **gap** | 3 | 5 |
| `pocketwatch` | **gap** | 9 | 5 |
| `precarious_shears` | **gap** | 3 | 5 |
| `precise_scissors` | **gap** | 3 | 5 |
| `prayer_wheel` | **gap** | 2 | 4 |
| `preserved_fog` | **gap** | 2 | 6 |
| `pollinous_core` | deliberate-divergence | 7 | 5 |
| `pomander` | waiver | 2 | 5 |
| `potion_belt` | waiver | 3 | 3 |

12 of 15 roll up to `gap`. Obtainability proved for all 15 (`b12-pool`): 6 in
the transcribed grab bag, 9 through ported events (Neow ×4, Darv, Vakuu,
Colossal Flower).

---

## LIVE gaps, one line each with executed evidence

1. **`permafrost` G1 — the relic works in the first combat of a run only.**
   `_activated` is reset nowhere in the sim; C# clears `ActivatedThisCombat` in
   `AfterRoomEntered` (`Permafrost.cs:41`). *`b12-permafrost`:* the same
   instance carried into a second combat gives **block 0 → 0** on an Inflame
   play where a fresh instance gives **0 → 7**. One-line fix
   (`on_combat_start`), exactly `belt_buckle` G2's shape. **This one the shared
   sweep had cleared — see “what I found wrong in the tooling” below.**

2. **`planisphere` `AfterRoomEntered` — the 5 HP heal on a “?” node never
   lands.** *`b12-planisphere`:* walking a real act to an Unknown node leaves HP
   at **50/80** where the game gives 55, and `after_room_entered` **did** fire,
   3×, last call carrying `point_type=UNKNOWN`. The stub premise (“an
   out-of-combat map effect”) is false: the hook exists (`relics/base.py:194`),
   is dispatched (`run.py:983`) with the map point in hand, and `run.heal`
   exists.

3. **`planisphere` G2 — `IsAllowed` (`TotalFloor < 41`) has no sim concept.**
   *`b12-planisphere`:* `hasattr(Relic, 'is_allowed')` is **False** and at
   `total_floor=60` the grab bag still yields `planisphere`. Sweep B's 17-relic
   cluster; matched to `amethyst_aubergine` / `lasting_candy` under rule 3.

4. **`prayer_wheel` `TryModifyRewards` — Monster screens offer one card choice
   instead of two.** *`b12-prayer`:* `cards=3, special_cards=0` with **and**
   without the relic (ELITE unchanged, correctly). `modify_combat_rewards` is
   dispatched at `rewards.py:499-500`. **Not a one-liner:** `CombatRewards` has
   no second pick-one-of-3 field, and the extra `CardReward` must Populate
   through `create_reward_cards` or RNG parity stays broken.

5. **`pen_nib` G1 — a replayed Attack is counted once and doubled twice.**
   *`b12-pennib`:* a Throwing-Axe-replayed Strike leaves `_attacks_played=1`
   (game: 2); the replayed 10th Strike costs the enemy **24 HP** where the game
   deals **18** (12 + 6). `hook_dispatch` G4 at the site that record already
   names as its witness; pinned xfail
   `test_hook_order.py:1143`.

6. **`pen_nib` G2 — the pending 10th Attack's PREVIEWED damage is not doubled.**
   The whole `AttackToDouble == null` arm (`PenNib.cs:120-128`) is missing.
   *`b12-pennib`:* with `_attacks_played=9` and a Strike in hand,
   `preview_card_damage` = **6** where the game prints 12; the damage *dealt* is
   12 on both sides. Filed as a gap rather than presentation because
   `previews.py` feeds `full_env.py:510`'s observation vector, not a sprite.

7. **`pocketwatch` G1 — a replayed card under-counts and buys 3 cards the game
   withholds.** *`b12-pocketwatch`:* 3 plays with the first replayed leave
   `_played_this_turn=3` (game: 4); next turn `modify_hand_draw(5)` returns
   **8** for the sim's count and **5** for the game's. Same `hook_dispatch` G4
   mechanism at a new site.

8. **`pendulum` G1 — the turn-start phase collapse is order-dependent.**
   Pendulum is the plain `AfterPlayerTurnStart` pass; Bone Tea is the later
   `AfterSideTurnStart` dispatcher. *`b12-pendulum`:* with `turns_seen=2`
   (ordinary carried state), relic order `[pendulum, bone_tea]` upgrades
   `[1,1,1,1,1,1]` and `[bone_tea, pendulum]` upgrades `[0,1,1,1,1,1]` — the
   game gives all six either way. `hook_dispatch` G3 at a new site.

9. **`petrified_toad` G1 — the combat-side procure skips
   `Hook.ShouldProcurePotion`, so Sozu does not refuse the rock.**
   *`b12-toad`:* with `[petrified_toad, sozu]` the belt still reads
   `['PotionShapedRock', None, None]`; the game leaves it empty.

10. **`petrified_toad` G2 — the procure skips `Hook.AfterPotionProcured`, so
    Belt Buckle keeps its 2 Dexterity.** *`b12-toad`:* `[belt_buckle,
    petrified_toad]` opens combat at **Dexterity 2** with 1 potion; the game
    opens at 0. Matches `belt_buckle`'s already-LIVE verdict; the Toad is a
    *second* trigger that fires unconditionally every combat.

11. **`petrified_toad` G3 — `BeforeCombatStartLate` is the only Late-phase
    implementer in the game, and collapsing it makes the above order-dependent.**
    *`b12-toad`:* `[belt_buckle, petrified_toad]` → Dexterity 2,
    `[petrified_toad, belt_buckle]` → Dexterity `None`; the game gives 1 potion
    and 0 Dexterity in both orders. `hook_dispatch` G3.

12. **`phial_holster` G1 — the `CombatPotionGeneration` stream is never
    consumed and the pool is flat, not rarity-weighted.** *`b12-phial`:* the
    stream sits at **0 → 0 draws** across `add_relic('phial_holster')`, where
    `alchemical_coffer`'s 4 potions move the same stream **0 → 8**. The correct
    helper exists and the sibling with the identical C# call uses it. Live for
    RNG parity, dormant for RL — matched to `astrolabe` N1.

13. **`precise_scissors` / `precarious_shears` / `preserved_fog` G1 —
    `Hook.BeforeCardRemoved` has NO sim dispatch, so a removed Spoils Map keeps
    paying.** *`b12-cardremoved`:* after `remove_cards([spoils_map])` the
    treasure node still pays **600 gold** (`in_deck=False`, marker still
    present, gold 99 → 699); C# clears the marker via
    `SpoilsMap.BeforeCardRemoved`. See the new pool-wide shape below.

---

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `pen_nib` G3 | C# skips `AfterCardPlayed` once the combat is ending (`CardModel.cs:1957`), the sim always fires it, so a killing 10th Attack stays marked in the game and not in the sim | fixing the sim's dispatch gate (`hook_dispatch` G8) without adding a `_card_to_double` reset. **Stated as unverified in the record:** I did not execute that C#'s `IsInProgress` is already false at that instant |
| `philosophers_stone` G1 | C# skips creatures on the owner's **side**; the sim skips only the player **object**, so a player-side ally would be handed 1 Strength | porting any player-side summon or pet (the game has `Osty`, the Necrobinder's — other-character content). Same substitution as `unsettling_lamp` G3(b) |

`pollinous_core`'s rollup is `deliberate-divergence`, not a gap: the sim resets
`turns_seen` **inside** `modify_hand_draw` where C# resets it in
`AfterModifyingHandDraw`, and the two are equivalent because
`Hook.AfterModifyingHandDraw` (`Hook.cs:739-749`) is dispatched **only** to
listeners whose `ModifyHandDraw` actually changed the integer
(`Hook.cs:1684-1696`). Flagged in the record for whoever adds a hand-draw
*preview*: a second call per turn would silently consume the bonus.

---

## What I found wrong in the shared tooling (reported, not edited)

**1. Sweep A's C#-side reset census cannot see `AfterRoomEntered` — and that
false-cleared a LIVE gap.** This is the fifth sweep defect the batches have
found, and the first to have hidden a live defect rather than manufacture a
false one.

`sweep-reset` builds its “C# resets” column by brace-matching only
`BeforeCombatStart` / `AfterCombatEnd` / `AfterCombatVictory` /
`AfterCombatDefeat` (`tools/audit/relic_probes.py:735-737`). For a `CombatRoom`,
`AfterRoomEntered` is *also* a combat-boundary hook: `CombatRoom.cs:197-231`
dispatches it once the encounter's creatures are on the board and strictly
before `Hook.BeforeCombatStart` (`CombatManager.cs:403`). So the sweep printed

```
permafrost   ['_activated']
             C# resets: NONE (may be per-run by design)
```

and `content-relic-sweeps.md` left `permafrost` among the “19 candidates
[that] remain unexecuted because their C# counterpart makes no combat-boundary
assignment at all — decent evidence the state is per-run on both sides”. It is
not: `Permafrost.cs:41` assigns `ActivatedThisCombat = false` there, and the
relic is a LIVE `belt_buckle`-shape gap.

`py tools/audit/relic_probes_b12.py b12-roomreset` rescans all **298** C# relic
files and finds **11** that assign inside `AfterRoomEntered`:

```
burning_sticks   WasUsedThisCombat = false      (also AfterCombatEnd -- census caught it)
velvet_choker    _cardsPlayedThisTurn = 0       (also AfterCombatEnd -- census caught it)
permafrost       ActivatedThisCombat = false    <-- AfterRoomEntered ONLY. Missed. LIVE.
throwing_axe     UsedThisCombat = false         (port resets in on_combat_start -- fine)
lava_lamp        TookDamageThisCombat = false   (port is a Sweep C stub, batch 8)
fake_venerable_tea_set / venerable_tea_set   GainEnergyInNextCombat = true
metronome        OrbsChanneled = 0              (unported -- Defect content)
pantograph / regal_pillow / stone_calendar     base.Status only (presentation)
```

Only `permafrost` is both `AfterRoomEntered`-exclusive **and** in the sweep's
candidate list, which is why it is the sole live victim. **Recommended fix:** add
`AfterRoomEntered` to the census's hook set and re-run `sweep-reset-exec`; the
count would go 19 → 20 and the confirmed-carry list 7 → 8. Note the two tea sets
also assign there (`= true`, an *arming* write, not a reset) — the sweep's
`_is_reset_value` would reject it, which is right, but batch 17 should know the
write exists.

**2. Sweep A's “safe” framing needs one more caveat, mirroring the turn-end
one.** The rewrite correctly split `_TURN_START` from `_TURN_END`. `permafrost`
shows the third failure mode: a C# reset that lives in a hook the census does
not enumerate reads as *no reset at all*, i.e. as evidence of intended
persistence. The general rule the census should state: **a `NONE` in the C#
column means “no assignment in the four hooks I looked at”, not “no
combat-boundary reset”.**

**3. Sweep A's column is genuinely load-bearing in the other direction, and it
worked.** For `pendulum` and `pollinous_core` the fixed column showed
`AfterCombatEnd: ['base.Status = RelicStatus.Normal']` — a display flag — which
is what turns two alarming cross-combat diffs into `faithful`. Both are
confirmed by execution here, so the rewrite's stated benefit is real.

**Nothing wrong found in:** `PROMPT.md` v5 (all 23 classes checked against all
15 units; the `GetValueIfAscension` note was not needed — none of the 15 C#
files contains an ascension branch), sweep B (`planisphere` is correctly in the
17-relic cluster), sweep C (`planisphere`, `potion_belt`, `prayer_wheel` all
confirmed as false premises), sweep D (the `pomander` over-report correction is
right — the candidate list carries the `is_upgradable` filter), or any
`audits/seam/**` record. No roster mis-resolution: all 15 resolved to a real C#
file first try, `name_overrides.json` needs nothing.

---

## Candidate new bug classes (for the stream owner to fold into `PROMPT.md`)

**Class 24 — a hook with exactly one C# implementer is still a hook. Check that
the port's substitute covers every reader.**
Exhibited by `precise_scissors` / `precarious_shears` / `preserved_fog` G1.
`Hook.BeforeCardRemoved` has one dispatch site (`CardPileCmd.cs:61`) and one
implementer in the whole game (`SpoilsMap.cs:100-115`). The sim has no such hook
and `cards/spoils_map.py` substitutes an `_active_in` deck-membership test — but
only on the map-*generation* hooks. The payout reader,
`RunState._complete_map_point_quests` (`run.py:1052-1058`), iterates
`point.quests` and never consults it, so removing the card leaves the 600 gold
armed (executed). The shape: *a one-implementer hook invites “re-implement the
implementer's intent locally”, and the local version is checked at some readers
and not others.* It is broader than relics — the merchant's card-removal service
and Magic Pot take the same path — so the card stream should re-check it.
Cheap detector: for every `Hook.X` with no `sts2_rl` dispatcher, enumerate the
C# implementers and, for each, grep the sim for **every** reader of the state it
mutates.

**Class 25 — a port's docstring can misdescribe the PORT, not just the source
or the sim.** Class 12 is a false claim about what the sim can do; class 19 is a
false claim about the source's constants. This is the third direction:
`relics/pendulum.py:13-14` says “the sim's [counter] resets each combat, like
Happy Flower”, and the sim resets it *nowhere* (executed: no `on_combat_*`
member; `turns_seen` runs 1 → 2 → 0 across three combats). The behaviour is
**correct** — `TurnsSeen` is a `[SavedProperty]` and persists in the game too —
so the hazard is not a bug today but a trap: a maintainer who trusted the
docstring and added the reset it claims exists would break a working relic, and
no test crosses a combat boundary for it. `relics/happy_flower.py` carries the
identical text (batch 7 recorded it at its N1). Verdicted `faithful` at both
sites per rule 3; the fix is to delete the clause, not to touch the code.

**A pool-wide shape worth one sweep, not a class:** *three relics, one C# hook,
three different intents.* `AfterRoomEntered` is a reset in `permafrost`, the
whole effect in `planisphere`, and a combat-start effect the sim remaps to
`on_combat_start` in `philosophers_stone`. `b12-roomreset` shows 11 C# relics
assign inside it. A `sweep-roomentered` that lists every C# `AfterRoomEntered`
override against whether the sim port implements `after_room_entered` (or a
substitute) would be a cheap work list — the hook is dispatched
(`run.py:983`) and only a handful of ports use it.

---

## Cross-record consistency (rule 3)

Six mechanisms already carried a verdict and are reproduced with the **same**
one, cited, not re-derived: `hook_dispatch` G4 (per-Replay `CardPlay`) at
`pen_nib` and `pocketwatch`; `hook_dispatch` G3 (missing phase passes) at
`petrified_toad` and `pendulum`; `hook_dispatch` G8 (no `IsOverOrEnding` gate)
at `pen_nib`; sweep B's `IsAllowed` cluster at `planisphere`, matching
`amethyst_aubergine` / `lasting_candy`; `belt_buckle`'s `AfterPotionProcured` at
`petrified_toad`; `alchemical_coffer`'s `GainMaxPotionCount` potion-scope waiver
at `phial_holster` and `potion_belt`; the `happy_flower` / `fake_happy_flower`
`[SavedProperty]` carry at `pendulum` and `pollinous_core`; `astrolabe` N1's
un-passed named RNG stream at `phial_holster`; `calling_bell` N1's
`AddCurseToDeck` at `preserved_fog`; `unsettling_lamp` G3(b)'s
side-versus-identity test at `philosophers_stone`.

**One near-miss worth naming.** My first pass verdicted `pendulum`'s false
docstring a `gap`. That contradicts `happy_flower` N1's `faithful` for the
identical mechanism, so it was corrected to `faithful` before commit — the
divergence is between a port and its own comment, not between the two
codebases. Recorded here because rule 3 caught it, which is the rule working as
the gap *detector* the contract describes.

**No cross-record disagreement found.** One fix-ordering constraint for the
gap-fix stream: `pocketwatch`'s dropped `AfterCombatEnd` reset is safe **only**
because `modify_hand_draw` bails on `self.turn == 1` (executed). If an
extra-turn mechanism ever makes `combat.turn` diverge from C#'s `TurnNumber`, or
the turn-1 suppression is relaxed, that verdict must be re-derived.

---

## Left unverified / out of scope

- **`pen_nib` G3's killing-blow corollary.** I did not execute that C#'s
  `CombatManager.IsInProgress` is already false when `CardModel.cs:1957` is
  reached, so the “stale mark survives into the next combat in the game” claim
  is an unconfirmed consequence of `hook_dispatch` G8. The record says so.
- **`potion_belt`'s second-order path.** I looked for a chain from the missing
  2 slots to a *combat* number and did not find one (`belt_buckle` turns on the
  belt being **empty**, not full). Recorded as an executed negative, not a
  claim.
- **Potion-belt capacity itself** stays waived under the contract's standing
  potion exclusion, matching `alchemical_coffer`. Both `potion_belt` and
  `phial_holster` name exactly what a potion-scope re-audit must change,
  including the `undo_after_obtained` the conformance runner will need.
- **`pomander`'s / `preserved_fog`'s missing `HasUponPickupEffect`** is a
  faithful transcription of the source's own inconsistency; normalising the five
  sibling ports would introduce two defects. Recorded, not filed.
- **Not attempted:** writing the `sweep-roomentered` proposed above (out of
  batch scope), and any engine fix — no file under `sts2_rl/` was modified.
