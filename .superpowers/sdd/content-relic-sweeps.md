# Pool-wide relic sweeps — pre-populated findings for batches 2+

**Date:** 2026-07-26 · **Branch:** `audit-relic`
**Companion to:** [`content-relic-report.md`](content-relic-report.md) (the Tier 1 pilot)
**Reproduce:** `py tools/audit/relic_probes.py sweep-reset` · `sweep-reset-exec` ·
`sweep-isallowed` · `sweep-stubs` · `sweep-stub-premises` · `sweep-upgrade` ·
`sweep-clone`

The pilot batch found that its live gaps cluster into a few repeating **shapes**
rather than sixteen unique bugs. These five sweeps chase three of those shapes
across all **258** relics at once, so batches 2–17 confirm rather than
discover. Nothing here is an audit verdict — no record is written for an
unaudited unit. This is a work list.

**These are findings, not fixes.** No engine code was touched; the suite is
unchanged.

---

## Sweep A — per-combat state the sim never resets (`belt_buckle` shape)

**The shape.** Sim relic instances live on `RunState.relics` and are re-attached
to every new `CombatState`, so a field set during combat 1 and never cleared is
still set in combat 2. C# clears such fields in `BeforeCombatStart` and/or
`AfterCombatEnd`/`AfterCombatVictory`.

**Method.** `sweep-reset` is an MRO-aware AST scan: for each relic, collect
every `self.X` write, split by the method that performs it, and flag fields
written *during* combat that no combat-boundary hook re-assigns. `sweep-reset-exec`
then **executes** each candidate — run one instance through a combat, start a
second combat with the same instance, and diff both the relic's own fields *and*
the player/enemy state against a freshly-constructed instance entering its first
combat.

### REWRITTEN 2026-07-26 after batches 4–8 — the first version was unsound

**Every one of batches 4, 5, 6 and 7 independently faulted this sweep**, on four
distinct grounds. All four were confirmed at the source and all four are now
fixed. Read this before trusting any earlier sweep-A output:

1. **Turn-*end* resets were pooled with turn-*start* resets.** The old output
   filed 21 relics as "reset only at a turn boundary — safe only if the turn
   reset runs before any reader" and then *never tested that condition*; the
   prioritisation step ran the executable check on a different bucket entirely.
   A turn-start reset really is safe (combat 2's turn 1 clears the field before
   any reader). A turn-**end** reset is not: `CombatState.end_turn` opens with
   `if self.phase != Phase.PLAYER_TURN: return` (`combat.py:639-642`), so the
   turn that WINS the fight skips the whole turn-end pass and the field crosses
   into the next combat. `_TURN_START` and `_TURN_END` are now separate sets and
   turn-end-only resets are flagged, not cleared. Found by batch 4
   (`diamond_diadem`), which remains the only turn-end-only relic in the pool.
2. **Increments were counted as resets.** `self.turns_seen = self.turns_seen + 1`
   is an `ast.Assign` like any other, so `happy_flower` was filed as
   "reset at a turn boundary" when the field never returns to 0. `_is_reset_value`
   now requires a fresh zero-ish constant and rejects any RHS that references the
   attribute. Found by batch 7.
3. **The "C# resets" column was an override census, not a reset census.** It came
   from `list_overrides`, which proves only that the relic *overrides*
   `BeforeCombatStart`/`AfterCombatEnd` — never that the body assigns anything.
   It therefore credited `fishing_rod` and `fur_coat` with resets they do not
   perform. The column now brace-matches the body and prints the **actual
   assignments**; an override with no assignment reports `NONE`. Found by batch 6.
4. **A never-written constructor field was invisible.** The sweep diffs a field
   across two combats, so a field nothing ever writes looks identical on both
   instances and gets cleared — but `make_relic` (`relics/base.py:74`) passes no
   arguments, so such a field is frozen at its default for the whole run. New
   `FROZEN CONSTRUCTOR STATE` bucket. Found by batch 5.
5. **`sweep-reset-exec` applied NO STIMULUS, so it false-*cleared* relics the
   static pass had correctly flagged.** Found by batch 13, *after* defects 1–4
   were fixed — the rewrite corrected the static classification and left the
   execution driver alone. The driver built a `CombatState`, called `end_turn`
   three times, and never damaged the player, never played a card, never granted
   a power, never supplied run context. Any field whose write is gated on a
   trigger the driver does not produce therefore reads identical on **both**
   instances, so the executed pass reported "agrees with a fresh instance" and
   **overrode the static bucket's correct warning**. It false-cleared
   `red_skull`, `ruined_helmet` and `pumpkin_candle`.

   The driver now applies stimulus (damage to ~38% HP, +2 Strength, one card
   played) to combat 1 **and to both sides of combat 2**, samples the relic's
   fields at every step rather than only at the end, and — most importantly —
   **checks whether combat 1 latched anything at all**. If it did not, the relic
   is reported `INCONCLUSIVE`, never as agreement.

   **The residual, stated plainly: the fixed driver still cannot clear a unit.**
   Its no-delta bucket is *known* to contain live gaps — `diamond_diadem`, whose
   stale count is only read after a WON combat 1 (and the driver breaks out
   before `end_turn` once the fight is over, so it can never produce that), and
   `paels_legion`, whose stale `cooldown` changes what a Defend *does* (block 5
   vs 10) rather than what any field reads. The bucket is therefore labelled
   "SHOW NO DELTA UNDER THIS STIMULUS" and prints both known false clears, so it
   cannot be read as a clean bill. **`sweep-reset-exec` escalates candidates; it
   never clears one.** Only a purpose-built probe does.

   A false clear is strictly worse than a false hit: nothing downstream
   re-checks a unit the sweep called clean. Both sweep failures that survived
   the first rewrite — B's under-report and A's false clears — were in that
   direction, and batch 9 then found a third of the same kind in sweep C.

   `red_skull` is why this matters. Its un-reset `_applied` makes combat 2 at
   full HP open with **Strength −3** — the relic subtracts a bonus it never
   granted. The static pass flagged it; the unstimulated exec pass cleared it.

Defect 3 cuts both ways, and that is the most useful thing to come out of the
rewrite. `happy_flower` and `pendulum` both carry `turns_seen` into combat 2, and
the old column said "C# resets: `AfterCombatEnd`" — implying a reset the sim
drops. The new column shows what that override actually assigns:
`base.Status = RelicStatus.Normal`, a display flag. The counter is **meant** to
persist on both sides. So the fixed column prevents false gaps as well as
catching false clears; batch 5's `faithful` on `fake_happy_flower` N1 was right
and now has mechanical backing.

| Bucket | Old (unsound) | Fixed |
|---|---|---|
| Relics holding no state at all | 200 | 200 |
| Reset every mid-combat field at a combat boundary | 5 | 5 |
| Reset every field at **turn start** — genuinely safe | 21 *(mixed)* | **13** |
| **Frozen constructor state — relic cannot fire** | *(invisible)* | **2** |
| **Not reset before a reader** | 32 | **38** |
| …executed by `sweep-reset-exec` | 16 | **19** |
| **…confirmed carrying state into combat 2** | 3 | **10** |
| …**inconclusive** — driver never latched the field | *(reported as clean)* | **9** |

### CONFIRMED — carry state across the combat boundary

| Relic | Field | Observed | C# boundary assignment | Status |
|---|---|---|---|---|
| `belt_buckle` | `_applied` | player powers `[('dexterity', 2)]` → `[]` | `DexterityApplied = false` ×2 | pilot G2 |
| `centennial_puzzle` | `_used_this_combat` | `False` → `True` | `UsedThisCombat = false` | recorded |
| `paels_eye` | `used_this_combat` | `False` → `True` | `AfterCombatEnd` | recorded |
| `diamond_diadem` | `cards_played_this_turn` | stale `3` read at combat-2 turn 1 | turn-END only | batch 4, LIVE |
| `venerable_tea_set` | `_pending` | frozen `False`, relic never fires | n/a | **UNAUDITED** (batch 17) |
| `fake_venerable_tea_set` | `_pending` | turn-1 energy 3 vs 4 | n/a | batch 5, LIVE |
| `paels_tears` | `had_leftover_energy` | player energy `3` → `5` | `AfterCombatEnd` | **UNAUDITED** (batch 11) |
| `red_skull` | `_applied` | combat 2 at full HP opens **Strength −3** | `RedSkull.cs:54` | batch 13, LIVE |
| `ruined_helmet` | `_used` | Strength 4 then 2 across two combats | `RuinedHelmet.cs:64` | batch 13, LIVE |
| `vambrace` | `_used` | `False` → `True` at combat-2 start | `AfterCombatEnd` + `BeforeCombatStart` | **UNAUDITED** (batch 17) |

Three of the ten are still unaudited and are pre-populated work for their
batches: **`venerable_tea_set`** and **`vambrace`** (both batch 17) and
**`paels_tears`** (batch 11 — an energy divergence, not just a flag).
`red_skull` and `ruined_helmet` were found by batch 13 auditing them on their
merits *after* the unstimulated exec driver had cleared them; the fixed driver
now reproduces both, and `vambrace` is the one it turned up that no batch has
reached yet.

`happy_flower`, `fake_happy_flower` and `pendulum` also diff across the boundary
but are **intended persistence on both sides** — see the `base.Status` note
above. `pendulum` is unaudited; its batch should cite this rather than file a gap.

Note the pilot's field-only diff would have **missed `belt_buckle`** — its stale
flag settles at `True` on both instances and the divergence is in the *player's*
Dexterity. The probe therefore snapshots player powers/block/energy/HP/hand and
enemy powers alongside the relic's fields. Any future use of this sweep must
keep that.

### Known limits of the fixed sweep

- The executed diff **cannot see** the turn-end and frozen buckets — the harness
  breaks out before `end_turn` when the combat is over, and a frozen field is
  identical on both instances by construction. That is *why* both are separate
  static buckets, and why a static hit there must be settled by a purpose-built
  probe (batches 4 and 5 both wrote one).
- 19 candidates remain unexecuted because their C# counterpart makes no
  combat-boundary assignment at all — decent evidence the state is per-run on
  both sides, not proof. `nunchaku`, `pen_nib`, `permafrost`, `tuning_fork` and
  `iron_club` still deserve a second look in their own batches; all five hold
  attack/card counters whose names read per-combat.
- A cross-combat diff is a **candidate**, never a verdict. PROMPT.md bug class 13
  still requires tracing to the first reader of the stale field.

---

## Sweep B — `IsAllowed` pool gates have no sim counterpart

**Executed facts.** `sts2_rl.relics.base.Relic` defines `is_allowed_at_neow`
(True) but **no `is_allowed` member at all**, and
`relic_pools.populate_relic_grab_bags` shuffles the pool once at run init with
no per-pull filter.

**20 ported relics override `RelicModel.IsAllowed`.** They split three ways:

> **CORRECTED 2026-07-26 (batch 8): the cluster is 17, not 16.** The first
> version of this sweep captured `([^\n;]*)` after the method's opening brace —
> the **first line only**. `LastingCandy.IsAllowed`
> (`LastingCandy.cs:80-98`) opens with a multi-line
> `runState.Players.Any(delegate(Player p) {...})` unlock test and only
> *returns* `RelicModel.IsBeforeAct3TreasureChest(runState)` at the very end, so
> the sweep saw the unlock clause and never reached the floor gate. It is now
> brace-matched, every clause is summarised, and multi-clause bodies are marked
> `**` in the output.
>
> This was the stream's **first under-report**, and it is the more dangerous
> direction. An over-report wastes a reader's time and gets caught; an
> under-report silently shrinks the work list and nothing downstream notices.
> Batch 8 found it only because it audited `lasting_candy` on its merits.

**(a) 17 relics — `IsBeforeAct3TreasureChest(runState)` = `TotalFloor < 41`.
Entirely unmodelled → live pool-composition gap.**

`amethyst_aubergine`, `book_of_five_rings`, `bowler_hat`, `dragon_fruit`,
`frozen_egg`, `girya`, `juzu_bracelet`, **`lasting_candy`**, `lucky_fysh`,
`meal_ticket`, `molten_egg`, `old_coin`, `planisphere`, `shovel`, `toxic_egg`,
`white_beast_statue`, `white_star`.

These seventeen stay pullable for the whole run where the game stops offering
them at floor 41. The sim already tracks `RunState.total_floor` (event gates use
it), so this is **one base-class member plus one filter in the pull path** — the
single highest-leverage fix the sweeps found. A wrong pull also shifts every
subsequent pull, so it is not a one-relic error.

**(b) 3 relics — multiplayer player-count gates. Clean, verified.**
`massive_scroll` (`Players.Count > 1` → never allowed in single-player) is not
in the transcribed grab bag and its only grant path, the ported Neow event,
already filters on `is_allowed_at_neow=False`. `silver_crucible` and
`winged_boots` (`Players.Count == 1`) are always allowed in single-player.

**(c) `lasting_candy` carries BOTH gates** — the Ironclad `UnlockState` clause
*and* the floor gate, which is why it also appears in (a). Batch 8 settled it:
the unlock clause is a waiver (the sim assumes full unlocks; `grep UnlockState`
over `sts2_rl/` returns nothing), the floor gate is the same live gap as the
other sixteen. Executed: at `total_floor=60` the grab bag still yields
`lasting_candy`.

**`IsAllowedAtNeow` (2 overrides).** `kaleidoscope` matches
(`is_allowed_at_neow=False`). **`scroll_boxes` does not**: C# gates on
`CanGenerateBundles(player)` and the sim leaves the flag at `True`. Needs a
per-unit audit.

---

## Sweep C — behaviourless ports whose premise is false

**The shape.** A port with no methods at all, justified by a docstring claim
about what the sim cannot do. Binding rule 1: "the sim has no such system" is a
dormant **gap**, not a waiver — and the pilot found two such claims that were
not merely dormant but **false today**.

**Method.** `sweep-stubs` finds every relic whose class *and every ancestor
below `Relic`* defines no method, and lists the non-declarative C# overrides it
drops. `sweep-stub-premises` then answers the load-bearing question
mechanically: for each dropped hook, is there a live **dispatch site** in the
sim outside `sts2_rl/relics/`?

> **Correction worth carrying forward.** The first version of this sweep read
> only each class's own body and flagged all three egg relics, whose ports are
> complete — they inherit from `relics/_eggs.py`'s `EggRelic`. All three sweeps
> are now MRO-aware. A sweep that over-reports is worse than useless as a work
> list.

**Result: 37 behaviourless ports of 258; 35 drop at least one C# behavioural
hook; 33 dropped hooks across 30 relics have a LIVE sim dispatch site.
ZERO have no pipeline.**

That is the headline: **every stub premise the sweep could test is false.** The
sim already calls these methods on every relic in the run; the stubs simply
decline to implement them. None of these can be waived under rule 1.

By premise family:

| Premise as written | Reality | Relics |
|---|---|---|
| "no gold system in the sim" | `RunState.gold`, `gain_gold`, and `modify_gold_gained` dispatched from `run.py` | `amethyst_aubergine` (pilot, confirmed live), `bowler_hat`, `old_coin`, `dragon_fruit` |
| "out-of-combat pickup effect, stub" | `after_obtained` dispatched by `run.py:552` | `cauldron`, `dollys_mirror`, `orrery`, `potion_belt`, `war_paint`, `whetstone`, `sea_glass`, `kaleidoscope`, `punch_dagger`, `royal_stamp`, `gnarled_hammer`, `kifuda`, `old_coin`, `massive_scroll` |
| "the sim has no enchantments" | `enchantments.py` is ported and `relic/beautiful_bracelet` attaches Swift through it | `punch_dagger`, `royal_stamp`, `gnarled_hammer`, `kifuda`, `fresnel_lens`, `wing_charm` |
| "out-of-combat reward modifier" | `modify_combat_rewards` / `modify_card_reward_options` / `should_force_potion_reward` dispatched from `rewards.py` | `prayer_wheel`, `white_star`, `white_beast_statue`, `lava_lamp`, `fresnel_lens`, `wing_charm` |
| "map-only effect" | `modify_unknown_map_point_room_types` dispatched from `run.py` | `juzu_bracelet` |
| "out-of-combat rest-site effect" | `after_rest_site_heal` / `modify_rest_site_heal_rewards` dispatched from `run.py` | `regal_pillow`, `tiny_mailbox` |
| "deck edits happen out of combat" | `after_card_added_to_deck` dispatched from `run.py` | `book_of_five_rings`, `lucky_fysh` |
| "out-of-combat merchant effect" | `modify_merchant_card_results` dispatched from `shop.py` | `fresnel_lens`, `molten_egg`-family shop paths |

**2 stubs drop no behavioural hook at all** and are genuinely complete ports.

A handful of dropped hooks have no `Relic` base method *and* are not
`HookSystem` hooks — `ModifyMerchantPrice`, `ShouldRefillMerchantEntry`,
`ModifyCardRewardCreationOptions`, `ShowCounter`, `AfterGoldGained`,
`ModifyExtraRestSiteHealText`, `ModifyDamageAdditive` on `mystic_lighter`.
Those need a new base hook, so they are larger than a one-relic fix and are
excluded from the 33 above.

---

## Sweep D — unguarded `Card.upgrade()` (added after batch 2)

**The shape.** C#'s `CardCmd.Upgrade` skips any card whose `IsUpgradable` is
false (`CurrentUpgradeLevel < MaxUpgradeLevel`, `CardModel.cs:785-789`). The
sim's `Card.upgrade()` (`cards/base.py:146-147`) is a bare
`upgrade_level += 1`, so every caller must supply its own filter. Bug class 14
fired in batch 1 (`astrolabe`) and again in batch 2 (`bone_tea`) — two
instances in two batches is a shape, so it was swept.

**Population.** An executed census puts **35 of 203** ported cards at
`max_upgrade_level == 0`: 18 Curse, 14 Status, 3 Quest.

**Result** (`sweep-upgrade`): 23 functions under `sts2_rl/relics/` call
`.upgrade()`; **7 do so with no `is_upgradable` / `upgradable_cards` filter
anywhere in the enclosing function.**

| Site | Status |
|---|---|
| `astrolabe.py:19` `after_obtained` | **LIVE**, recorded (batch 1) — curses are transformable and roll into curses |
| `bone_tea.py:31` `on_player_turn_started` | **LIVE**, recorded (batch 2) — statuses reach the opening hand; executed `[strike, dazed, burn]` → `[1, 1, 1]` vs C#'s `[1, 0, 0]` |
| `_eggs.py:39` `modify_card_reward_options` | **dormant** — the egg relics filter to Attack/Skill/Power and every level-0 card is Curse/Status/Quest |
| `_eggs.py:47` `modify_card_being_added_to_deck` | **dormant**, same reason |
| `burning_sticks.py:24` `on_card_exhausted` | unaudited — batch work |
| `dusty_tome.py:50` `after_obtained` | unaudited — batch work |
| `neows_talisman.py:29` `after_obtained` | unaudited — batch work |

15 relics guard correctly, including `bellows` — whose port is otherwise
identical to `bone_tea`'s and which is exactly why `bone_tea` is a defect
rather than a house style.

> **Third over-reporting correction.** The first version used a 3-line window
> to look for the guard and flagged `fishing_rod`, `pomander`, `yummy_cookie`,
> `stone_cracker` and `fragrant_mushroom` — all five build a pre-filtered
> candidate list several lines earlier. The sweep now scopes the search to the
> enclosing function via AST. Three sweeps, three over-reports caught before
> publication; assume the next one over-reports too.

---

## Sweep E — shallow card "clones" (added after batch 3)

**The shape.** C#'s `CardModel.CreateClone()` is `CardScope.CloneCard(this)` →
`ClonePreservingMutability()` (`CardModel.cs:2168-2179`;
`CombatState.cs:188-193`) — a full model clone that carries the card's upgrade
level, its **enchantment**, its **affliction**, its keyword edits and its local
**energy-cost modifiers**. The sim has no clone helper at all. Every port
reconstructs the card from its id or class and replays the upgrades, so *only*
the upgrade level survives. Found as `burning_sticks` G3 in batch 3; swept
because the idiom is copy-pasted across three kinds.

**Result** (`sweep-clone`): **12 C# content files / 16 sites** clone a card,
against **5 sim sites** using the shallow rebuild:

| Sim site | Kind | C# counterpart |
|---|---|---|
| `relics/burning_sticks.py:30` | relic | `BurningSticks.cs:49` — **LIVE, recorded (batch 3)** |
| `relics/music_box.py:46` | relic | `MusicBox.cs` — unaudited |
| `relics/paels_growth.py:39` | relic | unaudited |
| `cards/trash_heap_cards.py:18-24` (`_clone`, Dual Wield's copier) | card | `DualWield.cs` — card stream |
| `powers.py:827` | power | `JugglingPower.cs` / `NightmarePower.cs` — power stream |

**Executed evidence.** A Defend carrying Swift, a Ringing affliction and a
`set_cost_this_combat(0)` is rebuilt as:

```
enchantment   original=Swift       clone=None
affliction    original=Ringing(1)  clone=None
energy_cost   original=0           clone=1
```

**Why it is reachable without a second relic.** Afflictions are applied to
cards *in hand* by ported enemy powers — Ringing, Entangled, Smog, Tainted and
Galvanized all call `CardCmd.afflict` from `powers.py` (`:1332`, `:1477`,
`:1742`, `:2420`, `:3022`) — so a single combat can put per-instance state on a
card that is then cloned. Enchantments need `relic/beautiful_bracelet` (ported,
Ancient) or the `Imbued` enchantment.

**This crosses streams.** Two of the five sites belong to the card and power
streams, and the C# side includes `Anger.cs`, `AdaptiveStrike.cs`,
`HeirloomHammer.cs`, `Undeath.cs`, `NightmarePower.cs` and `JugglingPower.cs`.
The probe is in `tools/audit/relic_probes.py` (relic stream owns the file), but
the card and power streams should re-run it rather than rediscover the shape —
`py tools/audit/relic_probes.py sweep-clone`.

**The fix is one helper**, not five: a `Card.clone()` on `cards/base.py` that
copies upgrade level, enchantment, affliction and cost modifiers, and five call
sites switched to it.

---

## What this changes for the remaining work

**1. Three fixes are now specified well enough to queue** (the gap-queue stream
owns `docs/audit/GAP-QUEUE.md`; this file is the input, per the ownership
contract — I did not edit it):

- `centennial_puzzle` and `paels_eye`: clear the once-per-combat flag in
  `on_combat_start`. Same fix as `belt_buckle`. All three are one-line changes
  with an obvious failing-then-passing test (two combats, assert the relic
  fires in the second).
- `Relic.is_allowed(run)` + a filter in the grab-bag pull path, then the
  `TotalFloor < 41` predicate on 16 relics.

**2. Batches 2+ get cheaper and more accurate.** Every unit in the 32/21/37
lists arrives at its batch with the mechanical question already answered, so the
per-unit audit spends its budget on the reader-trace and the reachability
argument — the parts a script cannot do.

**3. The sweeps are re-runnable regression checks.** Each is a single command
and none touches engine code, so they can be re-run after any relic fix lands to
confirm the class is closed rather than the instance.

**4. Scale estimate for the stub family.** 30 relics × a real port is *not* an
audit-stream job — it is a porting job that the audit surfaces. The audit
records for those units will each carry a `gap`; whether Perry wants them
*fixed* is a separate call from whether they are *recorded*.
