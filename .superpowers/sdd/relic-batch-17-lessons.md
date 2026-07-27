# Relic content audit — batch 17 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b17` (based on `audit-relic` @ 3a300d94)
**Units:** 15 · **Records written:** 15, 0 invalid · **Probes:** 15, in `tools/audit/relic_probes_b17.py`
**Suite:** `py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged (no engine edits)
**Citations:** `py tools/audit/citation_check.py audits/relic` → 211 records, 2614 citations, **MISSING 0, OUT-OF-RANGE 0**

---

## Units and rollup verdicts

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `vambrace` | **gap** | 6 | 8 |
| `whispering_earring` | **gap** | 4 | 9 |
| `war_hammer` | **gap** | 2 | 7 |
| `venerable_tea_set` | **gap** | 4 | 5 |
| `white_star` | **gap** | 3 | 7 |
| `wing_charm` | **gap** | 2 | 7 |
| `white_beast_statue` | **gap** | 3 | 6 |
| `war_paint` | **gap** | 3 | 5 |
| `whetstone` | **gap** | 3 | 5 |
| `vexing_puzzlebox` | **gap** | 2 | 8 |
| `velvet_choker` | **gap** | 9 | 5 |
| `winged_boots` | **gap** | 7 | 7 |
| `vajra` | **gap** | 2 | 6 |
| `very_hot_cocoa` | waiver | 2 | 6 |
| `wongo_customer_appreciation_badge` | faithful | 1 | 3 |

13 of 15 roll up to `gap`. 8 units needed a purpose-built probe to settle.

---

## LIVE gaps (14), each with its executed evidence

1. **`vambrace` G1 — the relic works in the first combat of a run only.**
   C# clears `BlockGainedThisCombat` at `Vambrace.cs:52` (BeforeCombatStart) *and*
   `:119` (AfterCombatEnd); the port clears `_used` nowhere.
   *Executed (`relic_probes_b17.py vambrace`):* the same instance gives Defend =
   **10** block in combat 1 and **5** in combat 2, where C# gives 10 in both.
   Confirms sweep A's CONFIRMED-carrying row for this unit.

2. **`vambrace` G2 — an UNPOWERED card block gain is not doubled.**
   `BlockCmd.apply` gates the whole modifier dispatch on `is_powered_attack`;
   Vambrace's own C# gate is the looser `IsCardOrMonsterMove()`
   (`ValuePropExtensions.cs:23-26`). *Executed:* a powered Defend doubles 5 → 10,
   an UNPOWERED card gain of 5 stays **5** (C#: 10). Entrench is the ported
   witness. Same mechanism as `audits/seam/creature_card_cmds.json` G1 — cited,
   matched, not re-derived.

3. **`vambrace` G3 — only the FIRST block gain of a card play is doubled.**
   C# splits latch (`AfterModifyingBlockAmount`) from spend (`AfterCardPlayed`);
   the port spends on the first gain. *Executed:* two `BlockCmd.apply` calls
   carrying the same card give **10 then 5** (C#: 10 then 10). Evil Eye and
   Second Wind are the ported witnesses. Same mechanism as seam G2.

4. **`venerable_tea_set` G1 — FROZEN CONSTRUCTOR STATE; the relic can never fire.**
   Its whole trigger is `self._pending = rested` and `make_relic` passes no
   arguments. *Executed (`teaset`):* `_pending` is False, the class has no
   `after_room_entered`, turn-1 energy is **3** where C# gives 5; forcing
   `_pending=True` gives 5. Same defect as `fake_venerable_tea_set` G1 (batch 5)
   — cited and matched. Also recorded: C# arms the flag on rest-site **entry**,
   not on resting, so the port's parameter name is the wrong predicate too.

5. **`war_hammer` G1 — upgrades EVERY upgradable deck card, where C# upgrades 4.**
   `WarHammer.cs:26-27` is `.Where(IsUpgradable).StableShuffle(Rng.Niche).Take(CardsVar(4))`.
   *Executed (`warhammer`):* one Elite victory upgrades all **10** starting-deck
   cards (C#: 4); a MONSTER victory upgrades 0 on both sides. The port's docstring
   states the wrong behaviour as if it were the source's — bug class 19.
   **The largest single-unit divergence in the batch.**

6. **`war_paint` G1 — the +2 upgraded Skills never happen.** Stub whose premise
   ("out-of-combat deck edit") is false: `run.py:552` dispatches `after_obtained`.
   *Executed (`upgradestubs`):* `add_relic('war_paint')` changes **0** deck cards;
   the control `add_relic('neows_talisman')` upgrades 2 through the same dispatch.

7. **`whetstone` G1 — the +2 upgraded Attacks never happen.** Identical shape,
   Attack filter instead of Skill; same executed evidence and same control.

8. **`white_beast_statue` G1 — the forced potion never happens.** Stub; the hook
   is dispatched at `rewards.py:447-451` *and* `PotionRewardOdds.roll` already
   takes `force`. *Executed (`rewardstubs`):* 8/20 MONSTER screens carry a potion
   both with and without the relic (C# with it: 20/20). The forced hit also
   consumes a pity step, so the whole run's potion sequence shifts.

9. **`white_beast_statue` G2 / `white_star` G2 — the `IsAllowed` floor gate.**
   *Executed (`isallowed`):* `hasattr(Relic,'is_allowed')` is False; at
   `total_floor=60` the grab bag still contains both, and 13 Rare pulls at that
   floor surface `white_beast_statue`. The 17-relic cluster; verdict matched to
   `amethyst_aubergine` / `lasting_candy`.

10. **`white_star` G1 — the extra Boss-tier 3-card Elite reward never appears.**
    *Executed (`rewardstubs`):* an ELITE screen is `cards=3 special_cards=0` with
    and without it; the control `black_star` — the **same** `TryModifyRewards`
    hook at the **same** Elite gate — does add its reward. Recorded for the fixer:
    `ForRoom(RoomType.Boss)` means three **Rare** cards (`rewards.py:86`).

11. **`wing_charm` G1 — no card reward option is ever Swift-enchanted.** Both
    halves of the stub's premise are false. *Executed (`rewardstubs`):* options
    come out unenchanted with and without it; the control `glitter` — same hook —
    enchants all three; `SwiftEnchantment` is ported and `can_enchant(strike)` is
    True.

12. **`vexing_puzzlebox` G1 × `whispering_earring` G1 — one shared listener pass.**
    C# runs Puzzlebox at `Hook.AfterPlayerTurnStart` (step 22) and the Earring at
    `AfterAutoPrePlayPhaseEnteredLate` (the 3rd of 3 passes, `Hook.cs:928-955`,
    step 26). *Executed (`earring-order`):* `['vexing_puzzlebox','whispering_earring']`
    has the Earring play the generated `armaments`; reversed, it never does.
    Second independent ported pair for `turn_structure` G8 / `crossbow` G1.

13. **`whispering_earring` G2 — the port makes MANUAL plays where C# auto-plays.**
    `WhisperingEarring.cs:79-80` is `SpendResources()` + `CardCmd.AutoPlay(...,
    AutoPlayType.Default)` → `isAutoPlay: true`; the port calls
    `CombatState.play_card`. *Executed (`earring-auto`):* Brilliant Scarf's
    counter reads **5** after the Earring's turn-1 loop (C#: 0, because
    `BrilliantScarf.cs:84-87` skips `IsAutoPlay`).

14. **`whispering_earring` G3 — no card selector, so selections are random.**
    C# pushes `VakuuCardSelector` (deterministic `options.Take(n)`, no RNG draw);
    the port installs none and `select_cards` falls back to `_rng.sample`.
    *Executed (`earring-auto`):* the Earring auto-playing Armaments upgrades
    `twin_strike` on seeds 0/3 and `bash` on seeds 1/2/4, `card_selector=None`
    throughout. Two observables: wrong card, and shared-RNG draws C# never makes.

Plus four **RNG-parity-live / RL-dormant** gaps sharing one mechanism
(bug class 16, named stream never consumed, StableShuffle/NextItem always draws):
`war_hammer` N2, `war_paint` N1, `whetstone` N1, `wing_charm` N1.

---

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `vajra` G1 | +1 Strength lands at `BeforeCombatStart` (step 3) instead of `AfterRoomEntered`, which in the game precedes every enemy's first `RollMove` | a ported monster whose move selection reads the PLAYER's Strength (executed census: the three monster modules mentioning strength all read their OWN), or any ported `on_combat_start` listener that reads it (the six that touch Strength at combat start all WRITE it) |
| `velvet_choker` G1 | the counter is reset per turn only, not at the two combat boundaries; a listener asking `should_play_card` from `on_combat_start` sees the stale value (executed: **False** with a stale 6, C#: True) | any ported effect that plays or previews a card from `on_combat_start` — today the four auto-play sites are all turn- or card-scoped |
| `vexing_puzzlebox` N3 | `set_free_this_turn` implements "this turn" but not C#'s "**or until played**" (`SetThisTurnOrUntilPlayed`) | porting a "return the played card to your **hand**" effect; the sim's ported return effects go to the top of the draw pile |
| `white_star` N4 | `Hook.ModifyRewards` is a two-pass dispatcher (plain then Late) collapsed to one; `driftwood` is the ported Late implementer | fixing G1 — while White Star adds nothing it cannot contend. Doubly a fix-ordering constraint |
| `wing_charm` N2 | a fix following the C# literally needs `RunState.CloneCard`, and the sim's five clone sites are shallow rebuilds (sweep E / `burning_sticks` G3) | fixing G1 *by cloning*; the sibling `glitter` shows in-place enchanting reaches the same observable and avoids the defect |
| `wing_charm` N4 | `TryModifyCardRewardOptions` is two-pass; `lasting_candy` is the only plain-pass implementer and is **also** a stub | fixing BOTH `wing_charm` and `lasting_candy` without adding the pass structure |
| `whispering_earring` N1 | no `IsPlayerReadyToEndTurn` break condition | any asynchronous/interruptible turn model; the sim's turn-start hooks run to completion before an agent can act |
| `winged_boots` N3 | the sim charges only the FIRST free-travel granter and `break`s; C# charges each independently | porting the `Flight` run modifier (`Flight.cs:5`), the game's other `ShouldAllowFreeTravel` implementer; no run modifiers are ported |

---

## Cross-record consistency (binding rule 3)

Five mechanisms already carried a verdict elsewhere. All five are reproduced with
the **same** verdict, cited, not re-derived:

- Vambrace's unpowered-block gate → `gap`, matching `creature_card_cmds` **G1**
  (which names this relic as a C# witness and pins
  `test/test_hook_order.py::TestCreatureCardCmdsOrder::test_unpowered_card_block_still_runs_block_modifiers`
  — verified present by grep, rule 8).
- Vambrace's latch-vs-spend split → `gap`, matching `creature_card_cmds` **G2**
  (which cites `relics/vambrace.py:36-40` as its primary sim evidence; pinned test
  `test_vambrace_doubles_every_block_gain_of_one_card_play` verified present).
- The missing AutoPrePlay phase → `gap`, matching `turn_structure` **G8** and
  `audits/relic/crossbow.json` **G1**; a second ported pair added.
- `IsBeforeAct3TreasureChest` → `gap`, matching `amethyst_aubergine` and
  `lasting_candy`; two more of the 17-relic cluster recorded.
- The frozen constructor parameter → `gap`, matching
  `fake_venerable_tea_set` **G1**, whose **G2 explicitly deferred this unit to
  batch 17**; this record supplies that verdict.

**No cross-record disagreement was found.** One deliberate NON-match worth naming:
`winged_boots`'s `IsAllowed` is a **waiver**, not the `gap` its two batch-mates
carry, because the missing base member is the same mechanism but the predicate
inside it (`Players.Count == 1`) is multiplayer-only. Rule 3 binds per mechanism,
and the mechanism verdicted here is the predicate, not the absent member.

Two class-29 traps avoided (siblings differ on purpose, verified rather than
copied): `velvet_choker.ShouldPlay` **discards** its `AutoPlayType` argument, so
the sim counting auto-plays is **correct** there even though the identical
behaviour is `brilliant_scarf`'s LIVE G1; and `wing_charm` enchants exactly ONE
random option where `glitter` enchants all and `silken_tress` is one-shot.

---

## Faults found in shared tooling and seam records — reported, not edited

**1. `tools/audit/citation_check.py` mis-resolves a cited path by BASENAME,
discarding the directory — and this has already produced three false
OUT-OF-RANGE reports in the committed seam records.**
`_resolve` (`citation_check.py:78-109`) tries the path as repo-relative, then
falls back to matching the **basename** against the record's own hashed sources
and then to an `rglob`. A citation like `relics/base.py:235` in a record that
hashes `sts2_rl/monsters/base.py` therefore resolves to the *monster* file,
reports it out of range at 148 lines, and — because the hashed-source branch
returns `ambiguous=False` — does **not** get the AMBIGUOUS escape hatch that
exists for exactly this case. Executed: `py tools/audit/citation_check.py audits/seam`
reports 9 OUT-OF-RANGE, of which three are this bug
(`seam/hook_dispatch: cards/base.py:232`, `seam/hook_dispatch: relics/base.py:235`,
`seam/turn_structure: cards/base.py:269`, all "resolved" against
`sts2_rl/monsters/base.py`). Fix is one condition: prefer a candidate whose
repo-relative path **ends with** the cited path, and only then fall back to the
basename. Consequence for auditors meanwhile: cite shared sim files with their
full `sts2_rl/...` path — this batch does, which is why its own count is 0.

**2. Six genuinely stale citations in the committed seam records** (found while
matching `creature_card_cmds` G2's evidence, not by reviewing the tooling):
`seam/creature_card_cmds: cards/evil_eye.py:42` (file has 41 lines),
`cards/true_grit.py:55` (54), `relics/fiddle.py:31` (29);
`seam/hook_dispatch: relics/spiked_gauntlets.py:32` (31);
`seam/turn_structure: relics/crossbow.py:32` (31) and a MISSING
`seam/turn_structure: non-hooks.py`. All are off-by-one/two drifts, so the cited
evidence is almost certainly still correct one line up — but each one is exactly
the class of defect `citation_check` was built to catch, and they are *reported*
in the tool's output today and not acted on. `audits/seam/**` is read-only to
this batch.

**3. Sweep A re-run against the brief's paraphrase (per the coordinator's
mid-flight correction): the CURRENT output agrees with the brief on all three
pre-diagnoses, and with my own independent execution.**
`py tools/audit/relic_probes.py sweep-reset` and `sweep-reset-exec`, re-run
2026-07-26 after all seven fixes:

- `venerable_tea_set` → static bucket **FROZEN CONSTRUCTOR STATE (2)**,
  `self._pending <- rested`, other methods `['on_energy_reset']`. In the executed
  pass it lands in **INCONCLUSIVE** ("combat 1 never wrote the field"), which is
  the correct behaviour for a frozen field and is exactly why this record rests on
  a purpose-built probe (`relic_probes_b17.py teaset`) and not on the sweep.
- `vambrace` → **CARRIES STATE ACROSS THE COMBAT BOUNDARY**,
  `self._used: False -> True`, with the C# column correctly showing assignments at
  *both* `BeforeCombatStart` and `AfterCombatEnd`. Matches the brief and my probe.
- The brief's third note ("both tea sets arm their C# flag inside
  `AfterRoomEntered`, a hook that for a CombatRoom fires before
  `Hook.BeforeCombatStart`") is TRUE but **conflates two units' relevance**: the
  tea sets arm on a `RestSiteRoom` (`VenerableTeaSet.cs:41-49`,
  `RestSiteRoom.cs:25-39`), so the CombatRoom ordering fact does not bear on their
  latch at all. Where it *does* bear is `permafrost` (batch 12's finding) and, in
  this batch, `velvet_choker`, whose `AfterRoomEntered` reset fires on CombatRoom
  entry. Both halves verified independently from source; noted so a later reader
  does not look for a combat-room latch in a rest-site relic.

**Two precision points on sweep A's own reporting, neither a false clear:**

- **The bucket label "RESET AT TURN START, BEFORE ANY READER (genuinely safe:
  combat 2's turn 1 clears it first)" makes a safety claim whose stated
  justification is incomplete.** `velvet_choker` sits in that bucket. Combat 2's
  turn 1 *does* clear the field first — but `CombatState.__init__` fires
  `hooks.on_combat_start()` **before** `player.start_turn()` (`combat.py:208-209`),
  so there is a window in which the stale value is readable through the hook, and
  it is: the probe asks `hooks.should_play_card(strike)` from `on_combat_start`
  with the counter forced to 6 and gets **False** where C# answers True. The
  bucket's conclusion holds today (nothing plays a card from `on_combat_start`),
  but its reason does not, which is why this record verdicts
  deliberate-divergence rather than faithful. Per the standing rule, the bucket
  did not clear the unit — the trace did.
- **The `C# resets` column deliberately covers only combat-boundary hooks, so it
  cannot show a turn-start reset on the C# side — and for `velvet_choker` that is
  the reset that matters.** The column prints
  `AfterCombatEnd: ['_cardsPlayedThisTurn = 0']; AfterRoomEntered:
  ['_cardsPlayedThisTurn = 0']` and the adjacent field is `turn-start-reset=[...]`,
  which is the **sim's**. A reader taking the two together concludes the sim added
  a turn reset the source lacks — the exact error the port's own docstring makes
  (guard N1, bug class 24). `VelvetChoker.cs:92-101` is a `BeforeSideTurnStart`
  override that zeroes the same field. Suggested one-line improvement for whoever
  owns the sweep: include `BeforeSideTurnStart`/`AfterSideTurnStart` in the C#
  census under a separate label, so the two sides' turn resets can be compared.

`winged_boots` is worth flagging under the coordinator's other warning: it is in
the static **NEVER RESET BEFORE A READER** candidate list (`['times_used']`,
`C# resets: NONE (may be per-run by design)`) but is **not** in the prioritised 20,
i.e. statically flagged and never executed. Settled by hand here and found
`faithful`: `TimesUsed` is a `[SavedProperty]` and `WingedBoots.cs` has no
combat-boundary override at all, so per-run persistence is intended on both sides
— the `nunchaku` case, not the `belt_buckle` case.

Sweep B's classification of `winged_boots` as "(b) multiplayer player-count gate,
clean, verified" is also confirmed by execution, and it is worth recording why
that is not a counter-example to "a sweep may never clear one": the sweep's claim
was about the C# predicate, which is checkable statically; the part that needed
executing was whether the sim reaches the same answer, and that was done here.

**No sweep-A/B/C defect of the eight known kinds was found by this batch** — the
first of the eleven to report none. The two reporting imprecisions above are
offered as improvements, not as defects: neither produces a false clear.

---

## New bug class candidates for `PROMPT.md`

**Class candidate A — "the sim already has the correct helper, and the port uses
a *different* one."** Distinct from class 12 (a false claim that the sim *cannot*
do it) and class 22 (rerouting hook A onto hook B). Here the right surface exists,
is used by other ported content, and the port simply calls its neighbour.
Exhibited by **`whispering_earring` G2**: the sim has `CombatState.auto_play`
(`combat.py:423-438`, used by the Imbued enchantment) and `auto_play_card`
(`combat.py:516-546`, which passes `auto_play=True` to `should_play_card`), and
the Earring calls `play_card` — the manual path — so its 13 plays are invisible as
auto-plays (executed: Brilliant Scarf counts 5 where C# counts 0). The check is
mechanical: when a C# body names a specific *command* (`CardCmd.AutoPlay`,
`CardPileCmd.AddGeneratedCardToCombat`, `CardCmd.Upgrade`), grep the sim for that
command's counterpart and confirm the port calls **it**, not something adjacent.

**Class candidate B — "a control relic is the cheapest possible reachability
proof for a stub, and a *named sibling* is the cheapest control."** Four of this
batch's five stub gaps were settled in one probe each by running a ported relic
that implements the **same C# hook** and showing its effect does appear:
`neows_talisman` for `war_paint`/`whetstone` (`after_obtained`), `black_star` for
`white_star` (`TryModifyRewards`, same Elite gate, one letter apart in the pool),
`glitter` for `wing_charm` (`TryModifyCardRewardOptionsLate`). This is strictly
stronger than grepping for a dispatch site, because it proves the whole path from
`add_relic` to the observable, and it costs three lines. Worth stating as
procedure next to class 12: **for a stub, find the sibling that isn't one.**

**Pool-wide shape confirmed, not new:** the sim collapses `AfterPlayerTurnStart`
(step 22), `AfterSideTurnStart` (step 23) and the three-pass AutoPrePlay phase
(step 26) onto the single `on_player_turn_started` method. This batch holds
**three** listeners in that one method — `very_hot_cocoa` (step 23),
`vexing_puzzlebox` (step 22) and `whispering_earring` (step 26) — which is why the
pair-wise order dependence was demonstrable inside one batch. Any future batch
with two turn-start relics should assume they contend and check.

---

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file on the first try (`py
tools/audit/harness.py roster relic` → 258 sim units, 0 unmatched), and
`tools/audit/name_overrides.json` needs no additions. Obtainability confirmed by
execution for 14 of 15 (`relic_probes_b17.py pool`): 9 from the transcribed grab
bag, `velvet_choker`/`war_hammer`/`whispering_earring` from the ported Darv/Tanx/
Vakuu shrines, `very_hot_cocoa` additionally from Tezcatara, `winged_boots` from
the ported Neow event. The fifteenth,
`wongo_customer_appreciation_badge`, is proved **unobtainable** in the sim by
execution and is the batch's only `faithful` unit.

---

## Left unverified / out of scope

- **`whispering_earring`'s `ResourceInfo.EnergySpent = 0`.** `CardCmd.AutoPlay`
  reports 0 energy spent to `OnPlayWrapper` even though `SpendResources()` already
  spent the real amount. I verified the `Hook.AfterEnergySpent` half agrees on both
  sides (so the ported `intimidating_helmet` behaves identically) but did **not**
  chase whether any ported card's `OnPlay` reads a per-play "energy spent" value;
  that is card-stream territory.
- **`velvet_choker` / `whispering_earring` hand ORDER.** `CardPilePosition.Bottom`
  vs the sim's list append: I checked the overflow behaviour of `add_to_hand` by
  execution but not whether "bottom of the Hand pile" is the same end the Earring's
  `pile.Cards.FirstOrDefault` walks from. If it is the other end, the Earring picks
  a different card from a hand containing a generated card. Flagged rather than
  claimed.
- **Star costs** (`SetStarCostThisTurn`, `ShouldPayExcessEnergyCostWithStars`)
  waived as an unmodelled currency, on the same basis as
  `audits/relic/brilliant_scarf.json`'s `TryModifyStarCost`.
- Ascension values, multiplayer paths and relic-UI presentation waived per the
  shared contract throughout.

**Commit:** `2d97b0db` on `audit-relic-b17`.
