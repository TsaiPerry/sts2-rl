# Relic content audit — batch 13 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b13` (based on `audit-relic` @ `0cad15d3`)
**Units:** the 15 relics from `prismatic_gem` to `ruined_helmet`
**Probes:** `tools/audit/relic_probes_b13.py` (16 probes, all re-runnable; `py tools/audit/relic_probes_b13.py`)

`py tools/audit/harness.py validate` → **141 records, 0 invalid**.
`py tools/audit/citation_check.py audits/relic` → **1618 citations, MISSING 0, OUT-OF-RANGE 0**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 136 · invalid 0 · stale 0 · gaps 105 · unaudited 122`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; no engine file was touched (`git status` shows only the 15 records, the probe module and this report).

---

## Rollup verdicts

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `red_skull` | **gap** (LIVE ×1, two directions) | 6 | 5 |
| `ruined_helmet` | **gap** (LIVE ×1) | 6 | 6 |
| `regal_pillow` | **gap** (LIVE ×1) | 6 | 4 |
| `ripple_basin` | **gap** (LIVE ×1) | 7 | 4 |
| `ringing_triangle` | **gap** (LIVE ×1) | 3 | 5 |
| `royal_poison` | **gap** (LIVE ×1) | 4 | 4 |
| `royal_stamp` | **gap** (dormant ×2) | 5 | 4 |
| `punch_dagger` | **gap** (dormant ×1) | 5 | 2 |
| `red_mask` | **gap** (dormant ×2) | 4 | 5 |
| `rainbow_ring` | **gap** (dormant ×1) | 6 | 5 |
| `prismatic_gem` | **gap** (dormant ×1) | 5 | 2 |
| `pumpkin_candle` | waiver | 8 | 3 |
| `radiant_pearl` | waiver | 4 | 4 |
| `reptile_trinket` | waiver | 4 | 4 |
| `razor_tooth` | **faithful** | 2 | 5 |

11 of 15 roll up to `gap`. **6 LIVE gaps, 8 dormant gaps.** Nine of the 15 needed
execution to settle; reading alone would have produced wrong verdicts on at
least four (`red_skull`, `ruined_helmet`, `regal_pillow`, `ripple_basin`).

---

## LIVE gaps, one line each with its executed evidence

1. **`red_skull` G1 — the relic is dead from combat 2, or actively harmful.**
   `_applied` is never reset (C#: `StrengthApplied = false`, `RedSkull.cs:54`).
   Executed (`relic_probes_b13.py red-skull`): same instance at 30/80 HP gives
   Strength **3** in combat 1 and **0** in combat 2 (fresh instance: 3); and if
   the player heals to full between fights, combat 2 opens with StrengthPower
   **−3** — the sim hands the player *negative* Strength for a relic that only
   grants it. Common in the Ironclad grab bag; no second relic needed.

2. **`ruined_helmet` G1 — doubles nothing from combat 2 onward.** `_used` is
   never reset (C#: `UsedThisCombat = false`, `RuinedHelmet.cs:64`). Executed
   (`ruined-helmet`): the same instance given +2 Strength in each of two combats
   reports **4** then **2**; a fresh instance in the same combat 2 reports 4.
   Rare in the Ironclad grab bag; six ported relics and three ported cards grant
   the player Strength.

3. **`regal_pillow` G1 — the +15 rest heal has no sim hook to live in.**
   `Relic` declares no `modify_rest_site_heal_amount` and
   `RunState.rest_site_heal_amount` (`run.py:307-309`) is a bare
   `max_hp * 3 // 10` with no listener loop, where C# dispatches
   `Hook.ModifyRestSiteHealAmount` over the run
   (`HealRestSiteOption.cs:60-63`). Executed (`regal-pillow`): with the relic
   held, `rest_heal()` heals **24**, identical to a run with no relics, where C#
   heals 24 + 15 = **39**. This is a **base-class omission**, like sweep B's
   `is_allowed`, not a one-relic stub; `MendRestSiteOption.cs:58` is a second
   caller a fix in `rest_site_heal_amount` would cover for free.

4. **`ripple_basin` G1 — `turn_structure` G12 executed, as the brief asked.**
   Orichalcum's C# is deliberately two-phase (`Orichalcum.cs:44-56` snapshots
   `Block > 0` in `BeforeSideTurnEndVeryEarly`, with a source comment saying
   why); Ripple Basin is plain `BeforeSideTurnEnd`; the sim folds both onto
   `on_player_turn_end`, one flat listener walk. Executed (`ripple-basin`), 0
   block and no Attack played: `[ripple_basin, orichalcum]` → **4 Block**,
   `[orichalcum, ripple_basin]` → **10**, C# always **10**. Both Uncommon in the
   shared grab bag, so **half of all pickup orders give the wrong number** and
   the trigger is the relic's own condition. `fake_orichalcum` is the third
   member of the contention set.

5. **`ringing_triangle` G1 — `turn_structure` G4 executed at its own site.** A
   false `should_flush_hand` skips the sim's whole flush call, and
   `player.discard_hand` is the only caller of `on_hand_emptied`
   (`player.py:197`). Executed (`ringing-triangle`): five Ethereal exhausts then
   the turn-end gate — with `[joss_paper]` the draw pile goes **4 → 3** (card
   drawn, `_ethereal_pending` 0); with `[joss_paper, ringing_triangle]` it stays
   **4 → 4** and `_ethereal_pending` sticks at **5**. C# credits from
   `AfterSideTurnEnd` (`JossPaper.cs:116-120`), which fires unconditionally.
   `cards/apparition.py` supplies the Ethereal trigger with no second relic.

6. **`royal_poison` G1 — `turn_structure` G13 re-executed at its own site.** No
   `CheckWinCondition` after the turn-1 setup (C#: `CombatManager.cs:573`).
   Executed (`royal-poison`): `relics=[royal_poison]`, `current_hp=4` →
   `hp=0 is_dead=True phase=PLAYER_TURN is_over=False actions=6`. Royal Poison
   is the **only one of the four damage-dealing turn-start relics whose damage
   targets the player**, and the two that hand-roll `self._check_win()`
   (`festive_popper`, `mercury_hourglass`) do not cover player death.

---

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `punch_dagger` G1 | `AfterObtained` enchants a deck card with Momentum 5; the port is a stub whose "the sim has no enchantments" premise is FALSE (17 ported, and `beautiful_bracelet` already does this shape) | porting the **Momentum** enchantment model (`'momentum' in ALL_ENCHANTMENTS` is False) |
| `royal_stamp` G1 | same shape, RoyallyApproved 1 | porting the **RoyallyApproved** enchantment model |
| `royal_stamp` G2 | `list.UnstableShuffle(Rng.Niche)` (`RoyalStamp.cs:36`) is **consumed**, and the port draws nothing | **already live for RNG parity** the moment a recorded seed buys Royal Stamp; dormant only for RL play. A fix for G1 alone with `pick_rng=None` reproduces `astrolabe` N1 exactly |
| `red_mask` G1 | C#'s `BeforeSideTurnStart` (step 9) mapped to the sim's post-draw `on_player_turn_started` (step 23) — five steps late | a ported intent whose move selection reads its own Weak (= `bag_of_marbles` G1) |
| `red_mask` G2 | `HittableEnemies` vs `living_enemies()` | a turn-1 untargetable enemy (= `bag_of_marbles` G2) |
| `rainbow_ring` G1 | C# bumps `ActivationCountThisTurn` **after** awaiting both `PowerCmd.Apply` calls, so C# is re-entrant and the sim is not | a power/relic that auto-plays a card in reaction to *gaining Strength or Dexterity*; no ported `on_power_applied` listener plays a card |
| `prismatic_gem` G1 | `ModifyCardRewardCreationOptions` has no `Relic` base method at all; a narrowed non-colorless `CardPools` would be broadened even single-character | a second character card pool, or a reward that narrows `CardPools` without using `CustomCardPool` |
| `ruined_helmet` G2 | the received-side phase collapsed into one registration-order chain (= `power_cmd` G3) | a second given-side `modify_power_amount` listener whose domain overlaps positive Strength on the player |
| `ruined_helmet` G3 | the "mark used" side effect inlined into the modifier, so it fires before four gates C# applies first (= `power_cmd` G4 + G6) | a player-side untargetable state, or a `should_allow_hitting` implementation that can veto the player |
| `red_skull` N2 | C#'s `AfterCurrentHpChanged` has **no** `creature == Owner` check; the sim adds one | an effect that raises max HP mid-combat without changing current HP (`GainMaxHp` heals by the same amount, so it is not one) |
| `punch_dagger` / `royal_stamp` / `regal_pillow` `CanonicalVars` | the missing constants (5, 1/1, 15) | recorded so a fix does not re-derive them |

---

## NEW: a fifth defect in sweep A — the executed arm applies no stimulus

**Three of this batch's relics sit in sweep A's static "not reset before a
reader" bucket AND in `sweep-reset-exec`'s "agree with a fresh instance"
bucket. Two of the three are LIVE gaps.**

`probe_sweep_reset_exec`'s driver builds a bare `CombatState` at full HP, calls
`end_turn()` three times, and plays no cards
(`tools/audit/relic_probes.py:811-891`). Any field whose write is gated on a
stimulus that driver never produces is identical on both instances, so the diff
is empty and the relic is filed as agreeing. Executed
(`relic_probes_b13.py sweep-exec-blind`):

| Relic | Field | Stimulus the write needs | Driver supplies it | Value after the sweep's combat 1 | Truth |
|---|---|---|---|---|---|
| `red_skull` | `_applied` | player HP ≤ 50% of max | no (full HP) | `False` | **LIVE gap** |
| `ruined_helmet` | `_used` | a positive `StrengthPower` on the player | no (no cards played) | `False` | **LIVE gap** |
| `pumpkin_candle` | `kindle_count` | `after_obtained` / `after_combat_end` (RUN hooks) | no (`CombatState` only) | `0` | faithful (per-run on both sides) |

This is a **different** blind spot from the documented FROZEN CONSTRUCTOR STATE
one: there the field is never written at all, here the field is written only
under a condition the harness never creates. It is also the *dangerous*
direction, the same as batch 8's `IsAllowed` under-report — an over-report
wastes a reader's time and gets caught, a false clear silently shrinks the work
list. The sweeps file's "Known limits" section lists the turn-end and frozen
buckets as the two things the executed diff cannot see; **stimulus-gated fields
are a third**, and it currently reads as though a relic appearing in the
"agree" list has been cleared.

Suggested repair (not applied — `relic_probes.py` is read-only to this batch):
the driver should, per candidate, drive the player to half HP, apply a
`StrengthPower`, play one card of each type, and route the boundary through
`RunState.finish_combat(room_type=...)` rather than constructing a second
`CombatState` directly — or, cheaper and more honest, split the output into
"executed and agreed" versus "driver could not produce the write" and put the
relics whose field never changed value in the second bucket.

The two static buckets themselves were **right** on all five of this batch's
hits, and the corrected "C# resets" assignment column earned its keep twice: it
prevented a false gap on `pumpkin_candle` (the C# `AfterCombatEnd` body is a
*decrement*, `KindleCount = Math.Max(KindleCount - 1, 0)`, so the counter is
meant to persist) and on `ripple_basin` (the C# `AfterCombatEnd` body is only
`base.Status = RelicStatus.Normal` — there is no counter to zero).

---

## Other things found wrong in the shared tooling and seam records

**1. `audits/seam/turn_structure.json` step 9's dormancy rationale does not
cover its own named listener.** It says of `Hook.BeforeSideTurnStart`: *"DORMANT
for the player side: every ported one is a per-turn counter reset or latch that
does not read block or energy"* — and then lists **Red Mask** among the ported
overrides. Red Mask is not a counter reset or a latch: it applies 1 Weak to
every enemy (`RedMask.cs:23-30`). The **verdict survives** (the divergence is
still dormant, for `bag_of_marbles` G1's reason — no ported intent reads its own
Weak) but the stated basis is false for that listener, and `bag_of_marbles`'s
own record reaches the correct reasoning independently. Worth noting that Red
Mask is *further* out than the seam's mapping implies: the seam maps
`BeforeSideTurnStart` → `on_player_turn_start` (step 19), and Red Mask's port
sits on `on_player_turn_start**ed**` (step 23).

**2. Sweep C's evidence for `regal_pillow` names the wrong hooks.** The work
list records "`AfterRestSiteHeal` and `AfterRoomEntered` dispatched" as the
falsified premise. Both of those C# overrides are **pure presentation** —
`RegalPillow.cs:28-37` is `Flash()` + `base.Status`, and `:56-60` is
`base.Status = (room is RestSiteRoom) ? Active : Normal` — so implementing
either would change nothing. The hook that actually matters,
`ModifyRestSiteHealAmount`, belongs in sweep C's *other* list: the dropped hooks
with **no `Relic` base method**, which need a new base hook and are excluded
from the 33 actionable ones. The finding (a live gap) is right; the mechanical
evidence attached to it points at the wrong two methods, so a fix-stream reader
working from the sweep alone would implement two no-ops. **Generalisable
check:** before believing a dropped hook has a live dispatch site, read the C#
override's *body* — several relic overrides exist only to update
`base.Status`.

**3. `sts2_rl/relics/base.py:10-18`'s hook table is wrong in a second place,**
which is `PROMPT.md` bug class 11 recurring rather than a new finding. The table
maps `BeforeSideTurnStart (player) → on_player_turn_start (pre-draw)`. Three of
this batch's units have C# `BeforeSideTurnStart` overrides (`rainbow_ring`,
`ripple_basin`, `red_mask`) and only two of them landed on the slot the table
names; `red_mask` landed a slot further out. The table also does not mention
`BeforeHandDraw`, which is the C# hook that genuinely maps to
`on_player_turn_start` (`turn_structure` step 19, verdicted faithful) and which
`radiant_pearl` uses correctly. Nothing was changed (`sts2_rl/` is engine code).

Nothing else was found wrong in `PROMPT.md`. The **v5 note about
`GetValueIfAscension` argument order never fired** — not one of the 15 C# files
contains an `AscensionHelper` call, so every numeric in this batch is pinned
directly.

---

## Candidate new bug classes (for the stream owner to fold into `PROMPT.md`)

**A. `AfterRoomEntered(CombatRoom)` is a PHASE EARLIER than
`BeforeCombatStart`, and the sim collapses both onto `on_combat_start`.**
Exhibited by **`red_skull`**. `Hook.AfterRoomEntered` fires at
`CombatRoom.cs:228` — after `SetUpCombat` (creatures added, first move rolled)
but **before** `Hook.BeforeCombatStart`. Every ported relic that acts at the
start of a fight through this hook (`red_skull`, `girya`, `sling_of_courage`,
`sword_of_jade`, `vajra`) therefore runs *strictly before* all 22 C#
`BeforeCombatStart` implementers, and in the sim it interleaves with them by
registration order. Settled dormant here by enumerating all 22 and confirming
none applies or reads `StrengthPower` (the two that heal converge via
`on_hp_changed`), but it is the same *shape* as `turn_structure` G12 and it
spans five relics, so it is a sweep rather than a per-unit question. Related to
bug class 20 (wrong dispatch *site*) but distinct: the site is right, the
*phase* is one earlier.

**B. A near-miss that would have invented a gap: paired relics with
deliberately different auto-play policy.** Exhibited by **`rainbow_ring` N1**
and **`razor_tooth` N4**. `BrilliantScarf.cs:84-87` carries
`if (cardPlay.IsAutoPlay) return;` and the sim's failure to honour it is that
record's LIVE G1. `RainbowRing.cs:107-121` and `RazorTooth.cs:13-30` have **no
such clause**, so the sim counting auto-plays is *correct* for both. Copying the
sibling's verdict — which the batch-2 record makes very easy — would have filed
two false gaps. This is `PROMPT.md` class 15 ("paired hooks rarely carry the
same guard set") applied across *relics* rather than across two hooks of one
relic, and the checklist entry currently reads as being about the latter only.

**C. Verify a "clone"-style substitution the other way round too: a port that
adds behaviour the source's hook does not have.** Exhibited by
**`ripple_basin`**. `RippleBasin.AfterCardPlayed` and
`RippleBasin.BeforeSideTurnStart` are *presentation-only* in C# (`base.Status`),
because C# answers "did I play an Attack this turn?" from
`CombatManager.History.CardPlaysFinished`. The sim has no such query at this
site and substitutes a `_attack_this_turn` flag maintained from those two hooks.
Reading the C# overrides first suggests the port *added* two hooks for no
reason; the substitution is actually sound (verdicted `deliberate-divergence`
with all five history clauses checked). The lesson is procedural: when a sim
hook does real work and its C# namesake does not, look for a **history query**
elsewhere in the C# file before calling it either faithful or a divergence.

---

## Cross-record consistency (binding rule 3)

Six mechanisms already carried a verdict elsewhere. All six are reproduced with
the **same** verdict, cited, and not re-derived:

- `turn_structure` **G4** (a false `ShouldFlush` skips the flush tail) → `gap`,
  LIVE, at `ringing_triangle`'s own site — the seam names this relic.
- `turn_structure` **G12** (the three-pass `BeforeTurnEnd` flattened) → `gap`,
  LIVE, at `ripple_basin`'s own site — the seam names this relic as "the same
  shape" and records it **unexecuted**; the execution is supplied here.
- `turn_structure` **G13** (no turn-1 `CheckWinCondition`) → `gap`, LIVE, at
  `royal_poison`'s own site — the seam uses this relic for its own evidence.
- `turn_structure` step 17 (`modify_max_energy` / `should_reset_energy` order
  swapped) → `gap`, dormant, recorded on `prismatic_gem` N1 so its `faithful`
  hook verdict is not read as endorsing the surrounding order.
- `power_cmd` **G3** (given/received phases collapsed) → `gap`, dormant, at
  `ruined_helmet` G2 — `power_cmd` names this relic's own lines.
- `power_cmd` **G4** (no `AfterModifying*` companion machinery) → `gap`,
  dormant, at `ruined_helmet` G3, extended with the four gates the inlining
  jumps ahead of (`PowerCmd.cs:103-106`, `:133`, `:152`).
- `power_cmd` **N2** (the `ITemporaryPower` double-dip equivalence) →
  `deliberate-divergence`, cited on `reptile_trinket` N2, which is a new *site*
  for it: `ReptileTrinketPower` is a `TemporaryStrengthPower` and its internal
  application is applier-less, so `unsettling_lamp` skips it and
  `ruined_helmet` doubles it once — on both sides.
- `bag_of_marbles` **G1/G2** → `gap`, dormant ×2, matched exactly at
  `red_mask` G1/G2 (same C# hook, same `HittableEnemies` call, same relic
  shape).

**One disagreement found, and it is with a rationale rather than a verdict** —
`turn_structure` step 9's dormancy basis versus Red Mask, item 1 above. No
verdict conflict.

---

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file on the first try and
`tools/audit/name_overrides.json` needs no additions. Obtainability proved by
execution for all 15 (`relic_probes_b13.py pool`): 11 via the transcribed grab
bag (`punch_dagger`, `rainbow_ring`, `razor_tooth`, `red_mask`, `regal_pillow`,
`reptile_trinket`, `ringing_triangle`, `ripple_basin`, `royal_stamp` shared;
`red_skull`, `ruined_helmet` Ironclad), 4 via ported events (`prismatic_gem` and
`radiant_pearl` from Orobas, `pumpkin_candle` from Tezcatara, `royal_poison`
from Round Tea Party).

## One roster note that is not a mis-resolution

`.superpowers/sdd/content-relic-sweeps.md` assigns **`paels_tears`** to
"batch 13" in its CONFIRMED table. `paels_tears` is not in batch 13's 15 units
(this batch is `prismatic_gem`…`ruined_helmet`), so that pre-populated work item
is **still unclaimed** and whichever batch owns `paels_tears` should pick it up.
Flagged, not acted on.

## Left unverified / out of scope

- `prismatic_gem`'s `ModifyCardRewardCreationOptions` is waived on the
  Ironclad-only scope rule; the residual "narrowed non-colorless `CardPools`"
  shape (G1) is argued from `PrismaticGem.cs`'s four early-return clauses and
  **not executed**, because the sim has no reward-pool hook to execute against.
- `regal_pillow`'s pet clause (`creature.PetOwner != base.Owner`) is waived, not
  executed — the sim models no pet creature at a rest site at all.
- The truncation order for a fixed `regal_pillow` (C# adds 15 to an untruncated
  `MaxHp * 0.3m`; the sim floors first) is argued to coincide for every integer
  max HP and was **not** exhaustively enumerated.
- `royal_stamp` G2's RNG half is reasoned from `RoyalStamp.cs:36` and is not
  executed against a recorded seed — the sim consumes nothing, so there is no
  divergent draw count to print. `UnstableShuffle`'s exact draw count for a
  given list length was not measured.
