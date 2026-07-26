# Pool-wide relic sweeps — pre-populated findings for batches 2+

**Date:** 2026-07-26 · **Branch:** `audit-relic`
**Companion to:** [`content-relic-report.md`](content-relic-report.md) (the Tier 1 pilot)
**Reproduce:** `py tools/audit/relic_probes.py sweep-reset` · `sweep-reset-exec` ·
`sweep-isallowed` · `sweep-stubs` · `sweep-stub-premises`

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

| Bucket | Count |
|---|---|
| Relics holding no state at all | 200 |
| Reset every mid-combat field at a combat boundary | 5 |
| Reset only at a **turn** boundary (`art_of_war` shape) | 21 |
| **Never reset at a combat boundary** | **32** |
| …of those, C# *does* reset at a combat boundary → executed | **16** |
| **…of those, confirmed carrying state into combat 2** | **3** |

### CONFIRMED — carry state across the combat boundary

| Relic | Field | Observed | C# reset site | Obtainable via |
|---|---|---|---|---|
| `belt_buckle` | `_applied` | player powers `[('dexterity', 2)]` → `[]` in combat 2 | `BeforeCombatStart` + `AfterCombatEnd` + `AfterCombatVictory` | Shop, grab bag |
| `centennial_puzzle` | `_used_this_combat` | `False` → `True` at combat-2 start | `CentennialPuzzle.cs:AfterCombatEnd` | **Common**, grab bag |
| `paels_eye` | `used_this_combat` | `False` → `True` at combat-2 start | `PaelsEye.cs:142-145 AfterCombatEnd` | ported Pael shrine |

`belt_buckle` was already recorded in the pilot (`audits/relic/belt_buckle.json`
guard G2). **`centennial_puzzle` and `paels_eye` are new** and share the defect
exactly: each is a once-per-combat relic that latches after its first use and
never fires again for the rest of the run. Centennial Puzzle draws 3 cards on
first HP loss; Pael's Eye grants an extra turn. Both are the cheapest possible
fix (clear the flag in `on_combat_start`).

Note the pilot's field-only diff would have **missed `belt_buckle`** — its stale
flag settles at `True` on both instances and the divergence is in the *player's*
Dexterity. The probe therefore snapshots player powers/block/energy/HP/hand and
enemy powers alongside the relic's fields. Any future use of this sweep must
keep that.

### NOT confirmed, but not cleared either

- **13 of the 16 executed candidates agreed** with a fresh instance — their
  fields are genuine per-run counters (Girya's lifts, Toy Box's combat count,
  Fishing Rod, Sword of Stone, Pumpkin Candle, Wongo's ticket, …).
- **16 candidates were not executed** because their C# relic has no
  combat-boundary reset at all, which is decent evidence the state is per-run on
  both sides: `bone_tea`, `dusty_tome`, `girya`, `golden_compass`, `iron_club`,
  `lava_rock`, `lizard_tail`, `maw_bank`, `nunchaku`, `paels_wing`, `pen_nib`,
  `permafrost`, `silken_tress`, `silver_crucible`, `tuning_fork`,
  `winged_boots`. **`nunchaku`, `pen_nib`, `permafrost`, `tuning_fork` and
  `iron_club` deserve a second look** in their own batches — all five hold
  attack/card counters whose names read per-combat.
- **The 21 turn-boundary-only relics are NOT cleared.** `art_of_war` was
  verdicted safe in the pilot only after tracing to the first *reader* of the
  stale field (PROMPT.md bug class 13); the other 20 have had no such trace.
  They are listed in the probe output and each needs that trace in its own
  batch.

---

## Sweep B — `IsAllowed` pool gates have no sim counterpart

**Executed facts.** `sts2_rl.relics.base.Relic` defines `is_allowed_at_neow`
(True) but **no `is_allowed` member at all**, and
`relic_pools.populate_relic_grab_bags` shuffles the pool once at run init with
no per-pull filter.

**20 ported relics override `RelicModel.IsAllowed`.** They split three ways:

**(a) 16 relics — `IsBeforeAct3TreasureChest(runState)` = `TotalFloor < 41`.
Entirely unmodelled → live pool-composition gap.**

`amethyst_aubergine`, `book_of_five_rings`, `bowler_hat`, `dragon_fruit`,
`frozen_egg`, `girya`, `juzu_bracelet`, `lucky_fysh`, `meal_ticket`,
`molten_egg`, `old_coin`, `planisphere`, `shovel`, `toxic_egg`,
`white_beast_statue`, `white_star`.

These sixteen stay pullable for the whole run where the game stops offering them
at floor 41. The sim already tracks `RunState.total_floor` (event gates use it),
so this is **one base-class member plus one filter in the pull path** — the
single highest-leverage fix the sweeps found. A wrong pull also shifts every
subsequent pull, so it is not a one-relic error.

**(b) 3 relics — multiplayer player-count gates. Clean, verified.**
`massive_scroll` (`Players.Count > 1` → never allowed in single-player) is not
in the transcribed grab bag and its only grant path, the ported Neow event,
already filters on `is_allowed_at_neow=False`. `silver_crucible` and
`winged_boots` (`Players.Count == 1`) are always allowed in single-player.

**(c) 1 relic — `lasting_candy`, gated on the Ironclad's `UnlockState`.**
An unlock/progression gate; the sim assumes full unlocks. Likely a waiver, but
it needs the per-unit audit to say so — flagged, not decided.

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
