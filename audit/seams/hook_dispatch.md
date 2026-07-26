# Engine seam: `hook_dispatch`

Audited 2026-07-25 (Task 9 of the six seam audits, Tier 2 of the
source-audit-pipeline design). Verdicts and rationale live in
`audits/seam/hook_dispatch.json`; this file is the durable ordering spec
extracted from the C# source that the JSON record judges the sim against.

This seam is the **generic dispatch machinery**: how listeners are enumerated
and ordered, how the combat/run guards decide who is eligible, the multi-pass
(`VeryEarly` / `Early` / plain / `Late`) phase structure, the aggregation
semantics of each modifier family, the per-listener call protocol, and the
registration/unregistration lifecycle — plus every `Hook.cs` dispatcher that
none of the four earlier seams claims.

## Source correction (Step A)

`tools/audit/harness.py`'s `SEAM_SOURCES["hook_dispatch"]` listed **two** game
files (`src/Core/Hooks/Hook.cs`, `src/Core/Models/AbstractModel.cs`) and **one**
sim file (`sts2_rl/hooks.py`). All three are real and all three are genuinely
part of the unit — but **neither `Hook.cs` nor `AbstractModel.cs` decides which
listeners exist or in what order**, and that ordering is this seam's central
claim (seed fact 1). `Hook.cs` delegates every walk to
`ICombatState.IterateHookListeners` / `IRunState.IterateHookListeners`, whose
only implementations are in `CombatState.cs` and `RunState.cs`; the sim's
counterpart registry is spread across six modules, none of which was listed.

The table is now **27 game files + 31 sim files** (19 + 15 after the first
pass; see "Fix pass — sources swept" below). Added on the game side:

- **`src/Core/Combat/CombatState.cs`** — `IterateHookListeners` (410-493), the
  **only** statement of combat listener order in the game, and `Contains`
  (549-599), the per-item liveness re-filter it yields through. Steps 1-13 and
  gaps **G1**, **G5**, **G6**, **G7** rest on it. Already listed under
  `turn_structure`, for its side/round accessors — split by method, see the
  boundary section.
- **`src/Core/Runs/RunState.cs`** — `IterateHookListeners` (545-596), the run
  side: deck cards always, relics/potions/modifiers/badges only outside a
  combat, then delegation to the combat list. Steps 14-18; guard **N5**.
- **`src/Core/Entities/Players/Player.cs`** — `IsActiveForHooks` (112, set at
  272 and 438, cleared/restored at 859-870), the per-player gate both
  iterators consult. Steps 4, 15; guard **G7**.
- **`src/Core/Entities/Players/PlayerCombatState.cs`** — `AllPiles` (70-80).
  The card listeners are ordered **Hand, Draw, Discard, Exhaust, Play** and the
  list is **re-derived on every dispatch**, so a card's listener position moves
  when it changes pile. Step 9; **G1**. Already listed under `turn_structure`
  for its energy/turn-number members — split by method.
- **`src/Core/Models/MonsterModel.cs`** (51), **`AfflictionModel.cs`** (146),
  **`EnchantmentModel.cs`** (120), **`BadgeModel.cs`** (10-13) — the
  `ShouldReceiveCombatHooks` declarations and the four listener categories the
  sim's flat list does or does not have. Steps 3, 9, 10; **G5**, **G6**, **N4**.
- **`src/Core/Models/CardModel.cs`** (1895-1965) — the per-Replay `CardPlay`
  loop that constructs a fresh `CardPlay` and fires `Hook.BeforeCardPlayed`
  **and** `Hook.AfterCardPlayed` once per iteration. Primary evidence for
  **G4**. Already listed under `turn_structure` for its turn-end-in-hand
  wrapper — split by method.
- **`src/Core/Models/Powers/BufferPower.cs`** (18-27) — the source comment
  that states outright why the `Late` phase is load-bearing ("We use Late
  because other effects may reduce damage taken to 0 too, and it's more
  player-friendly for them to trigger first so that this power doesn't have to
  decrement"). Evidence for **G3**.
- **`Powers/TangledPower.cs`** (16-22 + the `TryModifyEnergyCostInCombat`
  override), **`Powers/FreeAttackPower.cs`** (14-40),
  **`Powers/CuriousPower.cs`** (12-32), **`Relics/SpikedGauntlets.cs`**
  (27-39), **`Relics/BrilliantScarf.cs`** (56-63) — the ported early-phase and
  `Late`-phase `TryModifyEnergyCostInCombat` implementations that make **G2**
  and **G3** LIVE.
- **`Relics/ThrowingAxe.cs`** and **`Relics/PenNib.cs`** — the ported pair that
  makes **G4** LIVE.

Added on the sim side (`hooks.py` is only the dispatch **bodies**; the listener
**registry** lives elsewhere entirely):

- **`sts2_rl/combat.py`** — `CombatState.__init__`'s registration sequence
  (106-166) is the sim's whole answer to `CombatState.IterateHookListeners`,
  and `_resolve_card_play` (441-514) is **G4**'s sim half.
- **`sts2_rl/cmds.py`** — `PowerCmd.apply`'s `hooks.register(power)` (326),
  `PowerCmd.remove`'s `hooks.unregister` (341-345), and the card
  register/unregister pair (446, 460).
- **`sts2_rl/player.py`** — the potion-belt `register`/`unregister`
  (`add_potion` 120, `detach_potion` 130-134) and `all_cards` (100-103), the
  sim's frozen analogue of `AllPiles`.
- **`sts2_rl/powers.py`** — `Power._expire` (87-92), the other unregister site,
  and the four `modify_card_energy_cost` implementers (597, 1147, 1486, 2883)
  that **G2** and **G3** are proved on.
- **`sts2_rl/history.py`** — `CombatHistory`, the sim's listener #0, which has
  no C# counterpart in the listener list at all (**N3**).
- **`sts2_rl/relics/base.py`** — `Relic.attach` (153-155).
- **`sts2_rl/monsters/base.py`** and **`sts2_rl/afflictions.py`** — where the
  two **missing** listener categories would be (**G5**, **G6**).
- **`relics/spiked_gauntlets.py`**, **`relics/brilliant_scarf.py`**,
  **`relics/pen_nib.py`**, **`relics/throwing_axe.py`**,
  **`cards/unrelenting.py`**, **`monsters/overgrowth/vine_shambler.py`** — the
  live gaps' sim halves, each cited with line numbers.

The rule applied is Task 8's: *if a verdict's liveness or dormancy argument
cites a file with line numbers, that file is part of the audited unit's
evidence and must be hashed.*

### Fix pass — sources swept

The rule above was **stated and then only half-applied**, for the third task
running. The fix pass swept it mechanically instead: every `.py`/`.cs` token in
`audits/seam/hook_dispatch.json` **and** in this file was extracted, resolved
against the real trees, and checked against `SEAM_SOURCES["hook_dispatch"]`.
Ten files were cited and unhashed, and the fix pass's own corrected evidence
cites ten more; all twenty are now in the table (the record's `game_sources` /
`sim_sources` were **regenerated** through `harness._hash_sources`, not
hand-edited, and the sweep was re-run afterwards until only the documented
exclusions remained):

- game: **`Models/Afflictions/Hexed.cs`** (the only C# affliction overriding a
  hook — **G6**'s whole dormancy argument), **`Relics/WhiteBeastStatue.cs`**,
  **`Relics/WingedBoots.cs`**, **`Models/Modifiers/Flight.cs`** (step 37's
  dormancy) and **`Relics/Fiddle.cs`** (the sole `AfterPreventingDraw`
  implementer, step 35).
- sim: **`cards/mad_science.py`** and **`events/tanx.py`** (the content that
  grants **G2**'s and **G4**'s witnesses), **`relics/daughter_of_the_wind.py`**
  (**G8**), **`rewards.py`** (step 37), **`previews.py`**, **`env.py`** and
  **`cards/base.py`** (step 39), **`relics/paels_eye.py`** (**N3**) and
  **`enchantments.py`** (**G4**).
- added by the fix pass's own corrected evidence, hashed under the same rule:
  game — **`Monsters/KinPriest.cs`** and **`Monsters/Vantom.cs`** (the two
  already-ported members of **G5**'s corrected list) and
  **`Potions/FairyInABottle.cs`** (step 15); sim —
  **`events/tinker_time.py`** + **`events/__init__.py`** (**G2**'s
  co-occurrence proof), **`monsters/overgrowth/the_kin.py`** (**G5**'s
  contended trigger), **`monsters/overgrowth/shrinker_beetle.py`** +
  **`potions.py`** (**G9**'s Shrink witness), and **`cards/whirlwind.py`** +
  **`full_env.py`** (step 39).

Two citation errors surfaced in the sweep and are corrected in the record:
`Modifiers/Flight.cs` was cited as `src/Core/Modifiers/Flight.cs`, **a path
that does not exist** (it is `src/Core/Models/Modifiers/Flight.cs`); and
**N3** named `relics/whispering_earring.py` as a second `CombatHistory`
reader when it reads no history at all (`grep -n history` on it returns
nothing), so that file is *not* hashed here.

What is deliberately **not** hashed, and is the only thing the sweep still
reports: `test/*.py`, `tools/audit/harness.py`,
`tools/audit/dormancy_probes.py`, `tools/audit/stale_listener_plugin.py`, and
`relics/whispering_earring.py`. The first four are the record's *pins* and its
*own machinery*, not evidence about the audited unit — a test edit that broke
a pin fails loudly on its own, hashing the harness would make every record
stale whenever any seam's source list changes, and a probe is re-runnable by
definition. `whispering_earring.py` is named only to record that it is **not**
what the first pass said it was, a negative citation with nothing to go stale.

### Scope boundary — READ BEFORE TASK 10 (`monster_state_machine`)

**`src/Core/Hooks/Hook.cs` is split by method across five seams.** Counted
programmatically off the file (`py tools/audit/dormancy_probes.py
hook-buckets`), it declares **147** public dispatchers plus two private helpers
(`IterateCombatHookListeners` 53-63, `ModifyDamageInternal` 2511-2558).

> **The 147/146 discrepancy, resolved (fix pass).** `grep -c '^\tpublic
> static'` gives **147**, but the name-capturing regex the first pass used —
> return type as a run of word/generic characters, `^\tpublic static
> [\w<>\?\[\],\.\s]+?\s(\w+)\(` — matches only **146**. The one declaration it
> misses is **`ModifyCardPlayResultPileTypeAndPosition` (`Hook.cs:1391`)**,
> whose return type is a **tuple**, `(PileType, CardPilePosition)`: the
> parentheses and the comma fall outside the character class. It is a real
> dispatcher and it is counted in the 147. `dormancy_probes.py hook-buckets`
> now runs both regexes and prints the miss, so the number cannot drift again.

The four earlier seams claim **53** of the 147 by name:

| seam | count | claim |
|---|---|---|
| `turn_structure` | 27 | listed by name in its boundary section |
| `damage_pipeline` | 16 | `AfterBlockBroken`, `AfterCurrentHpChanged`, `AfterDamageGiven`, `AfterDamageReceived`, `AfterDeath`, `AfterModifyingDamageAmount`, `AfterModifyingHpLostAfterOsty`, `AfterModifyingHpLostBeforeOsty`, `AfterPreventingDeath`, `BeforeDamageReceived`, `BeforeDeath`, `ModifyDamage`, `ModifyHpLost`, `ModifyUnblockedDamageTarget`, `ShouldCreatureBeRemovedFromCombatAfterDeath`, `ShouldDie` (+ the private `ModifyDamageInternal`) |
| `power_cmd` | 6 | the six power-amount dispatchers, listed in its boundary section |
| `creature_card_cmds` | 4 | `BeforeBlockGained`, `AfterBlockGained`, `AfterModifyingBlockAmount`, `ModifyBlock` |

**This record owns the remaining 94 dispatchers plus both private helpers.**
None of the 53 is re-verdicted *as a site* here — see the ownership policy in
"Cross-seam consequences" below, which the fix pass had to make explicit
because the JSON and this file previously disagreed about it.

Nothing in this seam is shared with `monster_state_machine` (Task 10) except
one negative fact worth knowing: **`MonsterModel` is a hook listener in the
game (`CombatState.cs:420`, `MonsterModel.cs:51`) and is not one in the sim**
(`monsters/base.py:78-81` stores `_hooks` but never calls `register`). That is
gap **G5** here, recorded as **dormant** because an executed scan finds zero
sim `Monster` subclasses defining any `HookSystem` hook name. Task 10 should
start from the **12** C# monster models that actually override an
`AbstractModel` hook (`py tools/audit/dormancy_probes.py cs-monster-hooks`) —
and note that **`KinPriest.cs:81-108`'s `AfterDeath` is already contended**:
its all-followers-dead `AllFollowerDeathResponse` has no counterpart in the
ported sim `KinPriest` (`monsters/overgrowth/the_kin.py:67-110`). **That
missing behaviour is Task 10's content finding**, not a second verdict here;
what this record owns is that the sim has no listener category to hang it on.

### Cross-seam consequences and the ownership policy

**The policy, stated once (fix pass).** This record owns the generic dispatch
**machinery** — listener order, the phase passes, `Contains`, and the
*aggregation-family shapes* — wherever that machinery appears, including at
dispatchers another seam owns. It does **not** issue a second verdict on
another seam's *site-specific observable*. Because governing rule 3 says the
same mechanism carries **one** verdict at every site **including across
records**, a machinery entry here and the owning record's entry for the same
mechanism must show the **identical** verdict and cross-reference each other.
The earlier text ("no verdict issued here") described steps 31/33/36 as
verdict-free, which the JSON never was and could not be — the harness requires
a verdict on every entry. Doc and JSON now agree on the policy above.

- `turn_structure` **G2** (Sturdy Clamp is not the `ShouldClearBlock`
  preventer) and **G8** ("the sim registers relics before powers") both rest on
  step 2 of this spec. Their observable belongs to `turn_structure`; the
  ordering rule itself is **G2** *of this record*.
- `turn_structure` **G12** (Orichalcum's `BeforeSideTurnEndVeryEarly` snapshot)
  is one instance of **G3** of this record, in a turn dispatcher
  `turn_structure` owns.
- **The additive/multiplicative running-value chain — now gap G9 at both
  sites.** C# threads the *running* value through the listeners and folds each
  contribution in immediately, in `decimal` (`Hook.cs:1320-1337`,
  `2515-2538`); the sim hands every listener the *pre-step base* and
  aggregates afterwards (`hooks.py:52-78`, `98-122`), applying the aggregate
  once (`cmds.py:57-58`, `145-147`). The fix pass **settled this by
  execution** rather than by argument (step 31 carries the evidence): the
  base-vs-running *argument* is inert — nothing on either side reads the value
  it is handed — but the *aggregation shape* is not, because the sim
  multiplies the factors together in float before applying them. Shrink
  (×0.7) + Vulnerable (×1.5) on a 20-damage attack: **sim 20, game 21**. So
  it is a **gap**, and by rule 3 `damage_pipeline`'s guard **N3** was raised
  from `deliberate-divergence` to `gap` in the same pass, with the same
  evidence and a cross-reference each way.
  **Closed 2026-07-26 (fix pass 2):** the **block** site was confirmed to have
  the identical shape on both sides (`Hook.cs:1320-1337` — two sequential
  loops folding `num += num2` then `num *= num3` into a running `decimal`, the
  same as `2515-2538` — vs `hooks.py:98-122` + `cmds.py:145-147`) and now
  carries the same **gap** verdict as clause (c) of `creature_card_cmds`' step
  13, cross-referenced to G9 and N3. **Rule 3 is satisfied at all three
  sites.** It is *dormant* there, unlike the damage site: every ported block
  multiplier returns a binary-exact factor (`{0.0, 0.75, 2.0}` — Frail,
  Unmovable, No Block, Vambrace, Pael's Legion), so the float product equals
  the sequential decimal fold (executed: Vambrace ×2 + Frail ×0.75 on 5 block
  gives 7 in both; exhaustive sweep of all 15 ordered subsets × bases 0–999,
  0 mismatches). Its named trigger is a block multiplier with a non-dyadic
  factor — the only one in the source is `MultiplayerScalingModel.cs:52-68`,
  waived here under **N1**.
- **Cap family** (step 33) and the **OR-with-first-`True` predicate** shape
  (step 36) live at `damage_pipeline`'s and `turn_structure`'s dispatchers.
  Both are `faithful` here and `faithful` in the owning record's treatment of
  the same mechanism (`damage_pipeline` step 4's cap clause;
  `turn_structure`'s gaps at `ShouldTakeExtraTurn` are about *when* it is
  evaluated, not the aggregation shape), so the records agree.

## Seed facts, verified

1. **"Sim dispatch is registration-order over one flat listener list; determine
   the game's cross-listener ordering."** Confirmed on both sides, and the
   answer is that they are close to **reversed**. The sim keeps one
   `list[Any]` and appends (`hooks.py:38, 43-44`); every dispatcher walks
   `list(self._listeners)` in that order. Executed against a live combat
   (`CombatState(relics=[pen_nib, orichalcum], potions=[block_potion])` plus one
   applied power) the categories come out
   `['history', 'cards'×9, 'relics'×2, 'potions', 'powers']`. The game groups
   **per creature**, allies before enemies, and within a player walks
   **Powers → Relics → PotionSlots → Orbs → cards** (`CombatState.cs:413-467`).
   Powers are first in the game and last in the sim; cards are last in the game
   and first in the sim. Gap **G2**.
2. **"No Early/Late hook phases in the sim."** Confirmed, and — overturning the
   brief's stated expectation of `deliberate-divergence` or per-listener
   waivers — recorded as gap **G3**. `AbstractModel.cs` declares **27**
   phase-suffixed hooks (`VeryEarly` / `Early` / `Late`) and **24** `Hook.cs`
   dispatchers run more than one complete pass. The phases change observable
   outcomes: `BufferPower.cs:18-19` carries a source comment saying the Late
   phase exists precisely so other reducers run first, and the ported pair
   `TangledPower` (early) / `FreeAttackPower` (Late) produces a different
   energy cost in the sim depending on application order (executed below).
3. **"`before_card_played` fires once per play, not per Replay iteration."**
   Confirmed and recorded as gap **G4**, not merely "the divergence it is":
   `CardModel.cs:1904-1965` builds a **fresh `CardPlay` per iteration** and
   fires `Hook.BeforeCardPlayed` (1929) *and* `Hook.AfterCardPlayed` (1959)
   inside the loop; `combat.py:466` and `combat.py:514` fire the sim's
   `before_card_played` / `on_card_played` once, outside the `for _ in
   range(play_count)` loop at 477-494. Executed: with Throwing Axe + Pen Nib,
   one doubled Strike advances Pen Nib's counter by **1**, where the game
   advances it by 2.
4. **"Modifier families: additive=sum, multiplicative=product, chain=fold;
   predicate short-circuits on any False."** Verified against `Hook.cs` and
   **incomplete in three ways**: the additive/multiplicative loops are
   *sequential* — each listener sees the running value and the fold happens in
   `decimal`, which is gap **G9**, not a stylistic note; the cap family is a
   fourth shape (min, step 33); and the predicate family has **three**
   variants, not one — AND with first-`False` short-circuit (14 dispatchers
   here, step 35), OR with first-`True` short-circuit (**5**:
   `ShouldAllowSelectingMoreCardRewards` 2161, `ShouldPayExcessEnergyCostWith
   Stars` 2346 and `ShouldRefillMerchantEntry` 2423 here, plus
   `ShouldStopCombatFromEnding` 2442 and `ShouldTakeExtraTurn` 2457, which are
   `turn_structure`'s — step 36), and OR **without** short-circuit, which calls
   every listener even after one returns true (`ShouldForcePotionReward`
   2472-2480, `ShouldAllowFreeTravel` 2485-2493, step 37). The sim's docstring
   (`hooks.py:28-34`) names only three families.
   *Fix-pass correction:* the first pass put those three OR-first-`True`
   dispatchers in the AND bucket. All 27 `public static bool Should*` bodies
   are now classified mechanically (see step 35).

## Numbered ordering spec

### The combat listener list — `CombatState.IterateHookListeners` (`CombatState.cs:410-493`)

1. Allocate `new List<AbstractModel>(Players.Count * 50)` and walk `_allies`
   then `_enemies` as **one index space**: `i < _allies.Count ? _allies[i] :
   _enemies[i - _allies.Count]`. Allies (the players) always come before
   enemies, and within each side it is list order. `CombatState.cs:412-415`.
2. Per creature, **first**: `list.AddRange(creature.Powers)`. A creature's
   powers precede everything else that creature owns, including its relics.
   `CombatState.cs:416`. See **G2**.
3. If `creature.Player == null` the creature is a monster: `list.Add(creature.
   Monster)` — the `MonsterModel` itself is a listener.
   `CombatState.cs:417-421`; `MonsterModel.cs:51`. See **G5**.
4. Otherwise, guard: `if (!player.IsActiveForHooks) continue;` — skips that
   player's relics, potions, orbs and cards, but **not** the powers already
   added at step 2. `CombatState.cs:424-427`; `Player.cs:112, 272, 438,
   859-870`. See **G7**.
5. Player's relics in `player.Relics` order, skipping `IsMelted` ones.
   `CombatState.cs:428-435`.
6. Player's `PotionSlots` in **slot** order, skipping null slots — so an empty
   belt slot leaves a hole rather than compacting. `CombatState.cs:436-443`.
7. Guard: `if (player.PlayerCombatState == null) continue;` — out of combat a
   player contributes only relics and potions. `CombatState.cs:444-447`.
8. `list.AddRange(player.PlayerCombatState.OrbQueue.Orbs)`.
   `CombatState.cs:448`. Waiver — orbs are the **Defect's**, i.e. a
   **character-scope** exclusion (**N7**). *Fix pass: this used to cite
   **N1**, "multiplayer plumbing", which it is not.*
9. Every card in `AllPiles` order — **Hand, Draw, Discard, Exhaust, Play**
   (`PlayerCombatState.cs:70-80`) — and for each card, the card, then its
   `Affliction`, then its `Enchantment`. The list is rebuilt on **every**
   dispatch, so a card's listener position tracks the pile it is currently in.
   `CombatState.cs:449-467`. See **G1**, **G6**.
10. After every creature: `Modifiers`, then `BadgeModels`, then
    `MultiplayerScalingModel` if non-null. `CombatState.cs:470-481`. Waiver —
    run modifiers are custom/daily-run configuration and badge models are
    meta-progression stat trackers (**N4**).
11. Yield phase: `foreach (item in list) if (Contains(item)) yield return
    item;` — the list is built eagerly, but `Contains` is evaluated **lazily,
    per item, at the moment the enumerator reaches it**. A listener that a
    *previous* listener in the same dispatch removed is therefore skipped.
    `CombatState.cs:482-488`. See **G7**.
12. `Contains` (`CombatState.cs:549-599`) by type: a **PowerModel** passes on
    `Owner.CombatState != null && (Owner.Player?.IsActiveForHooks ?? true)` —
    note it does **not** check that the power is still on its owner, so a power
    removed mid-dispatch still fires; **relics**, **potions**, **cards**,
    **afflictions**, **enchantments** and **orbs** all additionally require
    `!HasBeenRemovedFromState` (and their owner's `IsActiveForHooks`); a
    **monster** requires `Creature.CombatState != null`; achievements, badges,
    modifiers and the multiplayer scaling model always pass; anything else
    **throws** `ArgumentOutOfRangeException`.
13. Finally `ModHelper.IterateAllCombatStateSubscribers(this)` — mod-provided
    listeners, always last and never `Contains`-filtered.
    `CombatState.cs:489-492`. Waiver — no modding surface in the sim (**N2**).

### The run listener list — `RunState.IterateHookListeners` (`RunState.cs:545-596`)

14. For each `IsActiveForHooks` player: every card in `player.Deck.Cards`, and
    immediately after each card its `Enchantment` if any. **Deck cards are run
    listeners even while a combat is running.** `RunState.cs:548-562`.
15. Only when `childCombatState == null`: each active player's non-melted
    relics, then that player's `Potions`, then `Modifiers`, `BadgeModels` and
    `MultiplayerScalingModel`. In combat these come from the *combat* walk
    instead, which is why relics are not double-dispatched.
    `RunState.cs:563-576`. The sim's run-scoped hooks walk `run.relics` only
    (`relics/base.py:205-235`) and never the belt, so the `faithful` verdict
    needs the potions leg to be empty of run listeners — **executed**
    (`py tools/audit/dormancy_probes.py cs-potion-run-hooks`): of 65 files
    under `src/Core/Models/Potions`, exactly one overrides any
    `AbstractModel` hook (`FairyInABottle.cs`: `ShouldDie`,
    `AfterPreventingDeath`), and both are dispatched off
    `runState.IterateHookListeners(combatState)` — they enter through the run
    iterator but delegate to the combat list whenever a combat is live, and
    neither is among the **44** hooks dispatched off
    `runState.IterateHookListeners(null)`, the genuinely run-scoped ones.
16. Yield with the same lazy `Contains` filter. `RunState.cs:577-583`.
17. `ModHelper.IterateAllRunStateSubscribers(this)`. `RunState.cs:584-587`.
18. If `childCombatState != null`, append the whole combat list by delegation.
    So an in-combat run-level dispatch order is **deck cards → mod subscribers
    → combat listeners**. `RunState.cs:588-595`. See **N5**.

### The combat eligibility guard — `Hook.IterateCombatHookListeners` (`Hook.cs:53-63`)

19. `if (CombatManager.Instance.IsOverOrEnding && !CombatManager.Instance.
    IsStarting) yield break;` — a dispatch that *begins* after combat has
    started ending reaches **nobody**. `Hook.cs:55-58`. See **G8**.
20. The 21-line summary comment (`Hook.cs:31-51`) is normative and states three
    things: the check is evaluated **once**, when enumeration begins, not per
    listener, so a dispatch that begins while combat is live runs every
    listener even if one of them ends combat partway through; combat **setup**
    is exempt (`IsStarting`), because `IsInProgress` is still false then and
    the initial shuffle must still reach listeners; and a few hooks bypass the
    guard deliberately.
21. Bucketed programmatically over brace-matched bodies
    (`py tools/audit/dormancy_probes.py hook-buckets`): **73** of the 147
    dispatchers go through this guard; **63** call
    `runState.IterateHookListeners` directly (that iterator never consults the
    guard); **10** are combat-side dispatchers that bypass it deliberately by
    calling `<x>.IterateHookListeners()` themselves — `AfterBlockBroken` (107),
    `AfterCardPlayed` (278), `AfterCreatureAddedToCombat` (362),
    `AfterDamageGiven` (389), `AfterDiedToDoom` (484),
    `ModifyKeywordsInCombat` (1595), `ModifyUnblockedDamageTarget` (2048),
    `ShouldCreatureBeRemovedFromCombatAfterDeath` (2214),
    `ShouldStopCombatFromEnding` (2442) and `ShouldPowerBeRemovedOnDeath`
    (2495), each of which documents its reason and is a variant of "this is
    part of the kill, death, or combat-end sequence itself"; and **1**
    enumerates nothing of its own — `ModifyDamage` (1486), which delegates its
    whole walk to the private, run-side `ModifyDamageInternal` (2511).
    **73 + 63 + 10 + 1 = 147.**
    *Fix-pass reconciliation:* the first pass wrote 73/64/10, which is also
    147 but silently counts `ModifyDamage`'s delegated walk as run-side; a
    reviewer's independent count came out 72/64/9 + 1 unclassified. The
    difference from 72/9 is `ShouldPowerBeRemovedOnDeath` (2495), which
    iterates `power.CombatState.IterateHookListeners()` — a direct bypass that
    a regex keyed on the identifier `combatState` misses. Both readings of
    `ModifyDamage` are stated so the arithmetic checks either way; the
    73-through-the-guard figure that **G8** rests on is unaffected.

### Per-listener call protocol

22. Base shape: `foreach (model in <iterator>) { await model.<Hook>(args);
    model.InvokeExecutionFinished(); }`. `AbstractModel.InvokeExecutionFinished`
    (`AbstractModel.cs:191-194`) raises the `ExecutionFinished` event, which
    the class doc calls "a little unreliable, so you should only use it for UI
    things". Waiver — presentation (**N2**).
23. Choice-context variant: `choiceContext.PushModel(model)` … `PopModel(model)`
    around the await (e.g. `AfterCardDiscarded` 186-195, `AfterCardExhausted`
    237-246, `AfterCardPlayed` 278-294). Waiver — multiplayer (**N1**).
24. Hook-owned-context variant: the dispatcher reads `LocalContext.NetId` and
    **returns without calling anyone if it is null** (`AfterDeath` 452-456,
    `AfterDiedToDoom` 486-490, `BeforeFlush` 534-538, `BeforeHandDraw`,
    `AfterPlayerTurnStart`, `AfterAutoPre/PostPlayPhaseEntered`, `BeforeTurnEnd`,
    `AfterTurnEnd`), then builds a `HookPlayerChoiceContext` per listener and
    `await`s `AssignTaskAndWaitForPauseOrCompletion(task)`. Waiver —
    multiplayer/async pausing (**N1**).
25. Grouped-await variant: the pause-aware dispatchers collect
    `playerChoiceContext.WaitForCompletion()` into `tasksToAwait` and finish
    with `await Task.WhenAll(tasksToAwait)` (`BeforeFlush` 539-556,
    `BeforeTurnEnd` 1236-1263, `AfterTurnEnd` 1269-1292). The *pass* boundary is
    therefore not a hard barrier for the listeners' side effects, only for the
    dispatcher's return. Waiver — async plumbing (**N1**).
26. Every hook is a `virtual` no-op on `AbstractModel` returning
    `Task.CompletedTask` / the unmodified value, so "does not implement this
    hook" and "implements it as identity" are the same thing to the dispatcher
    — the loop calls **every** listener, always. `AbstractModel.cs:199-2440`.
    Contrast the sim's `hasattr` gate (step 45).

### Multi-pass phase structure

27. **24 of the 147 dispatchers run more than one complete listener pass**, and
    each pass is complete before the next begins: 20 run two passes and four
    run three or more — `AfterPlayerTurnStart` (882-908: Early → plain → Late),
    `AfterAutoPrePlayPhaseEntered` (928-958), `BeforeTurnEnd` (1232-1265:
    `VeryEarly` → `Early` → plain) and `ModifyHpLost` (1717-1769, four
    phase-flag-gated passes).
28. `AbstractModel.cs` declares **27** phase-suffixed hooks. Nine of them
    belong to dispatchers this record owns: `AfterCardChangedPilesLate` (359),
    `AfterCardDrawnEarly` (384), `AfterCardPlayedLate` (474),
    `ModifyCardRewardCreationOptionsLate` (1525), `ModifyGeneratedMapLate`
    (1627), `TryModifyCardBeingAddedToDeckLate` (1951),
    `TryModifyCardRewardOptionsLate` (1988), `TryModifyEnergyCostInCombatLate`
    (2016), `TryModifyRewardsLate` (2122). See **G3**.
29. The phases are **load-bearing, not cosmetic**. `BufferPower.cs:17-19`
    states it: *"We use Late because other effects may reduce damage taken to 0
    too, and it's more player-friendly for them to trigger first so that this
    power doesn't have to decrement."* A Late listener that zeroes a value must
    see every earlier reducer's result.
30. A pass is over the **freshly re-enumerated** listener list — each
    `foreach` calls `IterateCombatHookListeners(combatState)` again, so pass 2
    sees listeners added or removed during pass 1 (subject to steps 11-12 and
    19).

### Aggregation families

> **How coverage is established (fix pass).** The name lists below are now
> **complete for the family**, not illustrative — but they are complete
> *because of a census, not because someone enumerated from memory*. The census
> is: take the 147 declarations from `dormancy_probes.py hook-buckets`, subtract
> the 53 the other four seams claim by name, and classify each of the remaining
> **94** off its brace-matched body. That yields **46 event, 20 chain, 9
> try-chain, 14 predicate-AND, 3 predicate-OR-short-circuit, 2
> predicate-OR-no-short-circuit** (94). Coverage of this seam is therefore
> established **by family**: every one of the 94 falls in exactly one bucket
> and every bucket is verdicted. The **event** bucket is the one the record
> does not name exhaustively — 46 names for a single `faithful`
> fire-and-forget verdict (step 40) would be noise — and it is explicitly
> non-exhaustive; the other five buckets are named in full below. The first
> pass left 36 of the 94 unnamed with no statement either way.

31. **Additive** (`num += item.ModifyXAdditive(target, num, …)`) and
    **multiplicative** (`num *= item.ModifyXMultiplicative(target, num, …)`):
    a sequential chain in which each listener receives the **running** value
    and each contribution is folded in immediately, in `decimal`. The two
    sites are `Hook.ModifyBlock` (`Hook.cs:1320-1337`, `creature_card_cmds`')
    and `Hook.ModifyDamageInternal` (`2515-2538`, `damage_pipeline`'s). The
    sim aggregates in parallel instead and applies the aggregate once — **gap
    G9**, settled by execution in the fix pass and carried with the identical
    verdict at `damage_pipeline`'s guard **N3**. See "Cross-seam
    consequences".
32. **Chain**: `x = item.ModifyX(…, x)`, fold over the listeners, no
    change-tracking. All **20** this record owns:
    `ModifyAttackHitCount` (1297-1305), `ModifyCardPlayCount` (1372),
    `ModifyCardRewardCreationOptions` (1429-1440),
    **`ModifyCardRewardUpgradeOdds` (1473)**, `ModifyEnergyGain` (1606),
    `ModifyGoldGained` (1626), `ModifyExtraRestSiteHealText` (1646-1653),
    `ModifyGeneratedMap` (1658) / `ModifyGeneratedMapLate` (1671),
    `ModifyMerchantCardPool` (1794) / `ModifyMerchantCardRarity` (1806) /
    `ModifyMerchantPrice` (1818), `ModifyNextEvent` (1830),
    `ModifyOddsIncreaseForUnrolledRoomType` (1843),
    **`ModifyOrbPassiveTriggerCount` (1855 — chain *plus* a notification list,
    step 38)**, `ModifyOrbValue` (1874), `ModifyRestSiteHealAmount` (1936),
    `ModifySummonAmount` (2032), `ModifyUnknownMapPointRoomTypes` (2061),
    `ModifyXValue` (2071). The two in bold were missing from the first pass.
    (`ModifyStarCost` 2015 moved to try-chain, where its body puts it.)
33. **Cap**: track a running minimum and clamp (`Hook.cs:2539-2555`). The site
    is `damage_pipeline`'s; the **shape** is this record's and is `faithful`
    (`hooks.py:80-93` takes the min and `cmds.py:60-63` applies it), which is
    the same verdict `damage_pipeline` gives the cap clause of its step 4.
34. **Try-chain**: the listener is asked `bool TryModifyX(…)` and the
    dispatcher either threads an out-value or records that it changed
    something. All **9** this record owns, in three shapes:
    *value-threading* — `ModifyEnergyCostInCombat` (1574-1590, two passes) and
    **`ModifyStarCost` (2015-2027)**, both literally
    `item.TryModifyX(card, modifiedCost, out modifiedCost)`;
    *value-threading with a modifier list* — `ModifyCardBeingAddedToDeck`
    (1345-1367, two passes, `newCard != null` also required);
    *collect-only*, where the listener mutates the collection it is handed and
    the dispatcher **returns** the listeners that reported a change —
    `ModifyCardRewardAlternatives` (1413-1424), `TryModifyCardRewardOptions`
    (1445-1467, two passes), **`ModifyRestSiteOptions` (1949-1960)**,
    **`ModifyRestSiteHealRewards` (1965-1976)**, `ModifyRewards` (1981-2002);
    and *try-shaped event* — **`ModifyKeywordsInCombat` (1595-1601)**, whose
    `TryModifyKeywordsInCombat` return value is discarded outright. The four in
    bold were missing from the first pass, which also filed `ModifyStarCost`
    under chain. The collect-only four plus `ModifyCardBeingAddedToDeck` are
    step 38's notification lists.
35. **Predicate, AND with first-`False` short-circuit**, some with an
    `out preventer`/`out modifier` naming the vetoing listener. All **14** this
    record owns: `ShouldAddToDeck` (2084), `ShouldAfflict` (2101),
    `ShouldAllowAncient` (2116), `ShouldAllowHitting` (2131),
    `ShouldAllowMerchantCardRemoval` (2146), `ShouldAllowTargeting` (2176),
    `ShouldDisableRemainingRestSiteOptions` (2254), `ShouldDraw` (2269),
    `ShouldGenerateTreasure` (2316), `ShouldGainStars` (2331), `ShouldPlay`
    (2361), `ShouldProceedToNextMapPoint` (2393), `ShouldProcurePotion` (2408),
    `ShouldPowerBeRemovedOnDeath` (2495).
    **Short-circuit means the vetoing listener's identity is
    order-dependent**, which is why step 2's ordering has teeth.
    *Fix-pass correction:* `ShouldAllowSelectingMoreCardRewards` (2161),
    `ShouldPayExcessEnergyCostWithStars` (2346) and `ShouldRefillMerchantEntry`
    (2423) were listed here and do not belong — all three are `if
    (item.ShouldX(…)) return true;`. All 27 `public static bool Should*` bodies
    were re-classified mechanically to catch it.
36. **Predicate, OR with first-`True` short-circuit** — **5**, complete:
    `ShouldAllowSelectingMoreCardRewards` (2161-2171),
    `ShouldPayExcessEnergyCostWithStars` (2346-2356) and
    `ShouldRefillMerchantEntry` (2423-2433), which this record owns, plus
    `ShouldStopCombatFromEnding` (2442-2452) and `ShouldTakeExtraTurn`
    (2457-2467), which are `turn_structure`'s. The **shape** is `faithful`
    where the sim has it (`hooks.py:662-671` `should_take_extra_turn`, exercised
    by the ported Pael's Eye); the record makes **no** faithfulness claim about
    the four dispatchers with no sim counterpart, cross-referencing
    `turn_structure`'s **G10** and this record's **N5** instead. Noted here
    because the seed fact's "predicate short-circuits on any False" does not
    cover the shape at all.
37. **Predicate, OR with no short-circuit** — `flag = flag ||
    item.ShouldX(...)`, so **every** listener is still called after one returns
    true: `ShouldForcePotionReward` (2472-2480) and `ShouldAllowFreeTravel`
    (2485-2493), and those are the **only two** in `Hook.cs`. Any side effect
    in such a listener fires regardless. Dormancy rests on there being no
    second implementer to skip: `src/Core/Models/Relics/WhiteBeastStatue.cs`
    and `src/Core/Models/Relics/WingedBoots.cs` are the only ones outside the
    run-modifier set, `src/Core/Models/Modifiers/Flight.cs` being the second
    `ShouldAllowFreeTravel` implementer and a run modifier (**N4**).
38. **Modifier-notification lists**: the chain and try-chain dispatchers that
    report **which** listeners actually changed the value, so the caller can
    fire the matching `AfterModifying*` event over exactly that subset. All
    **10** this record owns. Via an `out modifiers` parameter, added only on a
    real change: `ModifyEnergyGain` (1610-1618) and `ModifyGoldGained`
    (1630-1638) compare with an **integer** cast, `(int)num2 != (int)num`, so a
    sub-1 decimal change does not count; `ModifyCardPlayCount` (1376-1384),
    `ModifyCardPlayResultPileTypeAndPosition` (1396-1405),
    `ModifyCardBeingAddedToDeck` (1350-1364) and
    **`ModifyOrbPassiveTriggerCount` (1855-1869)** track it exactly. And by
    **returning** the list instead of using an out-param:
    `TryModifyCardRewardOptions` (1445-1467), **`ModifyRestSiteOptions`
    (1949-1960)**, **`ModifyRestSiteHealRewards` (1965-1976)** and
    `ModifyRewards` (1981-2002), each collecting the listeners whose `bool
    Try*` returned true. The three in bold were missing from the first pass.
39. **Dispatcher-level guards** outside the loop: `ModifyEnergyCostInCombat`
    returns `originalCost` untouched when it is negative (X-cost cards,
    `Hook.cs:1576-1579`); `ShouldPowerBeRemovedOnDeath` returns `true` when
    `power.Owner.CombatState == null` (2497-2500); the `LocalContext.NetId`
    early return of step 24. The sim has **no** negative-cost arm in
    `modify_card_energy_cost` (`hooks.py:196-201`), and the equivalence rests
    on the sim's **different X representation**, not on luck: X is a separate
    boolean `Card.energy_cost_x` (`cards/base.py:87`; Whirlwind is
    `energy_cost = 0, energy_cost_x = True`, `cards/whirlwind.py:29,33`, and
    `powers.py:3868` comments the mapping "`EnergyCost.Canonical < 0`"), and
    every consumer short-circuits on it **before** reaching the chain —
    `combat.py:400-408`, `combat.py:547`, `combat.py:697-701`,
    `previews.py:179-181`, `full_env.py:354-355`. Independently, the only
    producer of the argument at all seven call sites is `Card.energy_cost`
    (`cards/base.py:222-232`), which already returns `max(0, base + delta)`.
    So the negative branch is unreachable **by construction**.
40. **Event dispatchers return no value** and ignore listener output
    entirely; there is no cancellation and no ordering feedback. This is the
    largest bucket — **46** of the 94 — and the one the record does not
    enumerate by name (see the census note above).

### The sim's registry — `sts2_rl/hooks.py` + five other modules

41. `HookSystem.__init__`: one flat `self._listeners: list[Any]` and a
    `self.combat` back-reference. `hooks.py:37-41`.
42. `register(listener)` appends; `unregister(listener)` is
    `self._listeners.remove(listener)`, which raises `ValueError` when absent
    — every caller wraps it in `try/except ValueError` (`cmds.py:341-345`,
    `cmds.py:445-448`, `player.py:130-134`, `powers.py:89-92`). No sim model
    defines `__eq__`, so `list.remove` is identity removal, matching the game's
    reference semantics.
43. Registration order in `CombatState.__init__`: `self.history`
    (`combat.py:112`) → every card in `player.all_cards` with its enchantment
    immediately after it (`combat.py:124-133`) → relics via `Relic.attach`
    (`combat.py:158-159`, `relics/base.py:153-155`) → belt potions
    (`combat.py:164-166`). Powers join later, as they are applied
    (`cmds.py:326`); mid-combat cards join at `cmds.py:460`; mid-combat potions
    at `player.py:120`. Monsters never register (`monsters/base.py:78-81`).
44. `all_cards` is `hand + draw_pile + discard_pile + exhaust_pile`
    (`player.py:100-103`), evaluated **once** at combat start — the order is
    frozen for the rest of the combat and does not follow the piles.
45. Each of the **66** `HookSystem` dispatchers is
    `for l in list(self._listeners): if hasattr(l, "<hook>"): l.<hook>(...)`.
    Two consequences: the `list(...)` copy makes the walk a
    **snapshot**, so a listener registered during a dispatch is not called and
    one unregistered during it still is (step 11's opposite); and the `hasattr`
    gate means a misspelled hook name on a listener is silently a no-op where
    C# would be a compile error.
46. There is **no** phase concept, no `preventer` for most predicates (only
    `should_die` 582-594 and, via a list out-param, `modify_hp_lost` 126-147),
    no `Contains` re-check, no `IsOverOrEnding` gate, no per-listener choice
    context, and no run-level `HookSystem` at all — run-scoped hooks are
    duck-typed directly over `run.relics` (`relics/base.py:205-235`).

## Sim comparison (Step C summary — full verdicts in the JSON)

The sim's dispatch is **structurally simpler in exactly five ways**, and each
one is a recorded gap:

- **One list instead of a per-creature walk** (**G1**, **G2**). The sim cannot
  express "this creature's powers, then this creature's relics"; it has
  registration order, and registration order groups by *category* in almost the
  reverse of the game's.
- **One pass instead of up to four** (**G3**). Twenty-four dispatchers lose
  their phase structure.
- **One dispatch per logical event instead of one per `CardPlay`** (**G4**).
- **No eligibility filtering** — no `Contains`, no `IsActiveForHooks`, no
  `IsOverOrEnding` (**G7**, **G8**).
- **Parallel aggregation instead of a sequential running-value chain**
  (**G9**, added in the fix pass).

and it is missing two listener **categories** entirely (`MonsterModel` **G5**,
`AfflictionModel` **G6**) while having one the game does not
(`CombatHistory`, **N3**).

**Verdict counts**, recomputed programmatically from
`audits/seam/hook_dispatch.json` (`collections.Counter` over `steps + guards`),
are **55 entries: 30 gap, 10 faithful, 12 waiver, 3 deliberate-divergence** —
46 steps (27 gap / 9 faithful / 8 waiver / 2 dd) and 9 guards (3 gap /
1 faithful / 4 waiver / 1 dd). The unit verdict is the rollup `gap`.
(First pass: 52 entries, 27/11/11/3 over 46 steps and 6 guards. The fix pass
turned step 31 from `faithful` to `gap` (**G9**), and added three guards —
**N7** the orb/character-scope waiver split out of **N1**, and **G4** and
**G6**, which the doc and the pin table both carried while the record carried
no entry for either.)

Every one of the 12 waivers is multiplayer (**N1**), presentation/modding
(**N2**), run-configuration/meta-progression (**N4**) or character scope
(**N7**) — out-of-scope categories, as the vocabulary rules require. Nothing a
single-player Ironclad run or a replay could observe is verdicted `waiver`;
the "no ported content triggers this" cases (**G1**, **G5**, **G6**) and the
"the C# side is unported" cases (**G6**, part of **G8**) are recorded as
**dormant gaps**, not waivers.

### Gaps found

**Four are LIVE on currently-ported content and pinned with strict xfails** —
**G2**, **G3**, **G4**, **G9**. **Five are dormant** — **G1**, **G5**, **G6**,
**G7**, **G8** — each with its concrete unported (or un-contended) trigger
named and its dormancy argument **executed**, not asserted, and each executed
by a probe committed under `tools/audit/` so the next auditor can re-derive
the number rather than trust it.

- **G1 — the card listener block is re-derived per dispatch in pile order and
  frozen at combat start in the sim. DORMANT.** `CombatState.cs:449-467` walks
  `AllPiles` = Hand, Draw, Discard, Exhaust, Play (`PlayerCombatState.cs:70-80`)
  every time a dispatch begins, so a card that moves from the draw pile to the
  hand moves *earlier* in the listener list. The sim registers
  `player.all_cards` once at `combat.py:124` in the fixed order
  `hand + draw + discard + exhaust` (`player.py:100-103`) and never reorders.
  Dormancy evidence (**executed**, reproducible: `py
  tools/audit/dormancy_probes.py card-hooks` — an MRO-aware scan of all **203**
  classes in `_CARD_CLASSES` against `HookSystem`'s **66** hook names, ignoring
  anything defined on the `Card` base): sim card classes implement exactly six
  hooks, and none of the six can observe cross-card order —
  `on_card_entered_combat` (1 implementer: Stomp), `on_card_exhausted`
  (1: Drum of Battle), `on_energy_spent` (1: Stomp),
  `on_player_turn_start` (2: Bolas and Thrumming Hatchet, both of which only
  call `_return_to_hand_if_played_last_turn(self)` on themselves),
  `on_player_turn_end` (2: Howl from Beyond, which auto-plays *itself* out of
  the exhaust pile, and Regret, which snapshots the hand size — neither reads
  state the other writes, and the auto-play does not change the hand), and
  `should_play_card` (3: Clash, Enthralled, Normality — an AND predicate whose
  sim dispatcher, `hooks.py:690-694`, has no `preventer` out-param, so the
  vetoing listener's identity is unobservable). Concrete trigger: porting a
  card whose hook reads state another card's hook writes, or giving
  `should_play_card` a preventer out-param — at which point two such cards in
  different piles would fire in the wrong relative order.
- **G2 — cross-listener order. The game groups per creature and runs
  Powers → Relics → Potions → Orbs → Cards; the sim runs
  History → Cards → Relics → Potions → Powers. LIVE.** `CombatState.cs:413-467`
  vs `combat.py:106-166` + `cmds.py:326`. The two most consequential
  inversions are **powers before relics** (game) versus **relics before
  powers** (sim), and **cards last** (game) versus **cards first** (sim).
  Live and executed with two ported relics/powers on one dispatcher this record
  owns, `Hook.ModifyEnergyCostInCombat` (`Hook.cs:1574-1590`): **Curious**
  (`CuriousPower.cs:12-32`, ported at `powers.py:2883-2889` and applied by the
  ported Mad Science card, `cards/mad_science.py:174-177`) reduces a Power
  card's cost with a floor of 0, and **Spiked Gauntlets**
  (`SpikedGauntlets.cs:27-39`, ported at `relics/spiked_gauntlets.py:26-32`,
  from the ported Tanx shrine `events/tanx.py:13`) raises it by 1. Both are
  early-phase, so the *only* thing that decides the result is listener order.
  With Curious at 2 stacks on a 1-cost Power card the game computes
  `max(0, 1-2) = 0` then `+1 = 1`, and the sim computes `1+1 = 2` then
  `max(0, 2-2) = 0` — **executed: the sim returns 0 where the game charges 1**.
  **Rule-6 co-occurrence, stated rather than implied:** Mad Science comes from
  the ported Act-3 (Glory) event **Tinker Time**
  (`events/tinker_time.py:74`; `"tinker_time"` is in `GLORY_EVENTS`,
  `events/__init__.py:99-107`) and Spiked Gauntlets from the ported Act-3 Glory
  Ancient **Tanx** (`events/tanx.py:13`, `OPTION_POOL`). Same act, different
  node types — a `?` room and the Ancient node — and the Mad Science card stays
  in the deck once added, so a single run can hold both and the witness is
  *reachable*, not merely constructible.
  This is also the mechanism behind `turn_structure`'s already-pinned **G2**
  (Barricade, a power, is the game's `ShouldClearBlock` preventer; Sturdy Clamp,
  a relic, is the sim's) and **G8**.
- **G3 — the Early / VeryEarly / Late phase passes do not exist in the sim.
  LIVE.** Twenty-four `Hook.cs` dispatchers run 2-4 complete listener passes
  (step 27) and `AbstractModel.cs` declares 27 phase-suffixed hooks (step 28);
  `hooks.py` has a single walk per hook and folds the phases away
  (`hooks.py:673-680` says so outright for `on_extra_turn`: "the sim has no
  Early hook phases"). **The brief expected `deliberate-divergence` or
  per-listener waivers; that is wrong** — a missing phase changes the observable
  outcome, so it is a gap. Live and executed on
  `Hook.ModifyEnergyCostInCombat`: **Tangled**
  (`TangledPower.cs`'s `TryModifyEnergyCostInCombat`, the **early** pass;
  ported at `powers.py:1486-1502`, applied by the ported Act-1 monster Vine
  Shambler at `monsters/overgrowth/vine_shambler.py:42-43`) adds 1 to an
  Entangled Attack's cost, and **Free Attack**
  (`FreeAttackPower.cs:14-40`, `TryModifyEnergyCostInCombatLate`, the **Late**
  pass; ported at `powers.py:1133-1155`, applied by the ported Ironclad card
  Unrelenting at `cards/unrelenting.py:40`) sets an Attack's cost to 0. The game
  always runs Tangled first and Free Attack last, so the next Attack is free.
  Executed on the sim: applying Free Attack *before* Tangled leaves the Strike
  at cost **1**; applying Tangled first leaves it at **0** — the sim's answer
  depends on the order the two powers happened to land, and half the time the
  "free" attack is not free. `BrilliantScarf.cs:56-63`
  (`TryModifyEnergyCostInCombatLate`, ported at `relics/brilliant_scarf.py:29`)
  and `SpikedGauntlets.cs:27` are the same shape one category up, and
  `turn_structure`'s **G12** (Orichalcum's `BeforeSideTurnEndVeryEarly`) is this
  gap in a turn dispatcher.
- **G4 — the per-`CardPlay` bracket. LIVE.** `CardModel.cs:1904-1965` loops
  `for (int i = 0; i < playCount; i++)`, constructs a **fresh `CardPlay`** with
  `PlayIndex = i` each iteration (1919-1928), and fires
  `Hook.BeforeCardPlayed(combatState, cardPlay)` at 1929 and
  `Hook.AfterCardPlayed(combatState, choiceContext, cardPlay)` at 1959 **inside**
  the loop. `combat.py:466` fires `before_card_played` once *before* the
  `for _ in range(play_count)` loop (477-494) and `combat.py:514` fires
  `on_card_played` once *after* it. Live with two ported relics: **Throwing
  Axe** (`ThrowingAxe.cs`, ported at `relics/throwing_axe.py:30-36`, granted by
  the ported Tanx shrine, `events/tanx.py:13`) makes the first card of a combat
  play twice, and **Pen Nib** (`PenNib.cs`, ported at `relics/pen_nib.py:30-35`)
  counts Attack plays in `before_card_played` and doubles every 10th. Executed:
  one Throwing-Axe-doubled Strike advances the sim's Pen Nib counter by **1**,
  where the game advances it by 2 — so from the very first combat the sim
  doubles a *different* Attack than the game does. The 4 ported enchantment /
  power replay sources (`enchantments.py:167`, `enchantments.py:232`,
  `powers.py:966` One-Two Punch, `powers.py:3919` Duplication) all widen it, as
  does every one of the sim's 48 `on_card_played` listeners.
- **G5 — `MonsterModel` is not a listener in the sim. DORMANT** (as a
  *machinery* gap). `CombatState.cs:420` adds `creature.Monster` to the
  listener list and `MonsterModel.cs:51` declares `ShouldReceiveCombatHooks =>
  true`. The sim's `Monster.__init__` stores `self._hooks`
  (`monsters/base.py:78-81`) and never calls `register`.
  **Fix-pass correction — the game-side number was wrong.** The first pass said
  **71** monster models override at least one `AbstractModel` hook. Re-derived
  with `py tools/audit/dormancy_probes.py cs-monster-hooks` (every `public
  override <name>` in the 127 files under `src/Core/Models/Monsters`
  intersected with `AbstractModel.cs`'s 181 `public virtual` methods), it is
  **12**: `Aeonglass` (`AfterCardGeneratedForCombat`, `AfterDeath`), `Crusher`
  (`AfterCurrentHpChanged`, `BeforeDeath`), `DecimillipedeSegment`,
  `KinPriest`, `LagavulinMatriarch` (`AfterDamageReceived`, `AfterDeath`),
  `Queen`, `Rocket` (`AfterCurrentHpChanged`, `BeforeDeath`), `SoulFysh`
  (`AfterCardChangedPilesLate`, `AfterDeath`), `TestSubject`,
  `TheInsatiable`, `Vantom`, `WaterfallGiant`. The 71 counted every `public
  override` in those files — 123 `MinInitialHp`/`MaxInitialHp`, 84
  `TakeDamageSfxType`, 82 `GenerateAnimator`, 65 `AfterAddedToRoom` and so on,
  none of which is an `AbstractModel` hook.
  Sim-side dormancy evidence (executed: `py tools/audit/dormancy_probes.py
  monster-hooks`): across **113** sim `Monster` subclasses, **0** define any of
  `HookSystem`'s 66 hook names and the base never calls `hooks.register`.
  Concrete trigger, **already contended in ported content**:
  `KinPriest.cs:81-108`'s `AfterDeath` calls `AllFollowerDeathResponse` when
  the last `KinFollower` dies, and the ported sim `KinPriest`
  (`monsters/overgrowth/the_kin.py:67-110`) has no counterpart anywhere. That
  missing **behaviour** is Task 10's content finding to record; what *this*
  record owns is that the sim has no listener category to hang it on.
  (`Vantom.cs:97-105`'s `AfterDeath` is presentation only — a music parameter.)
- **G6 — `AfflictionModel` is not a listener in the sim. DORMANT.**
  `CombatState.cs:458-461` adds `cardModel.Affliction` immediately after its
  card and `AfflictionModel.cs:146` declares `ShouldReceiveCombatHooks => true`;
  the sim registers the card and its `enchantment` (`combat.py:127-133`) and
  never the affliction. Dormancy evidence, executed at both ends:
  `py tools/audit/dormancy_probes.py affliction-hooks` finds **0** of the 7 sim
  `Affliction` subclasses defining any `HookSystem` hook name, and
  `cs-affliction-hooks` finds that of the 10 files under
  `src/Core/Models/Afflictions` exactly **one** overrides an `AbstractModel`
  hook — `Hexed.cs`, with `AfterCardEnteredCombat` — and Hexed is unported
  (`afflictions.py:72-79` is a data-only stub). Concrete trigger: porting
  Hexed's `AfterCardEnteredCombat`, or any future affliction with a hook
  override; at that point the affliction must register *immediately after its
  own card*, which the sim's frozen registration order (**G1**) cannot express
  either.
- **G7 — no per-item liveness re-check and no `IsActiveForHooks`. DORMANT.**
  C# yields `if (Contains(item))` **lazily, per item** (`CombatState.cs:482-488`)
  and `Contains` (549-599) drops any relic / potion / card / affliction /
  enchantment / orb whose `HasBeenRemovedFromState` is set or whose owning
  player is not `IsActiveForHooks`; the sim iterates a `list(self._listeners)`
  snapshot with no re-check (`hooks.py:61`, and the same line in all 66
  dispatchers). Dormancy evidence (**executed**, not argued, and — fix pass —
  **reproducible from the committed tree**, which it previously was not
  because the instrumentation was a throwaway script):

  ```
  py -m pytest test/ -q -p tools.audit.stale_listener_plugin
  ```

  `tools/audit/stale_listener_plugin.py` shadows every listener's bound hook
  method for the duration of one dispatch with a probe that re-checks
  `listener in hooks._listeners` **at the moment the dispatcher calls it** —
  exactly C#'s lazy `Contains` — so a listener removed by an *earlier* listener
  in the same walk is caught. (The obvious cheaper instrumentation, comparing
  the pre-dispatch snapshot with the post-dispatch list, over-reports badly:
  it flags all 68 listeners that unregister *themselves* mid-dispatch, none of
  which was called while absent.) Over the whole suite — **2476 passed / 30
  xfailed** at the baseline, **191,270 instrumented listener calls** — the only
  hit is `on_enemy_side_end` → `IntangiblePower` (×10, Nemesis removing
  Intangible mid-dispatch) — and **C# makes that same call**, because the
  `PowerModel` arm of `Contains` (`CombatState.cs:599`) checks only
  `Owner.CombatState != null`, never that the power is still on its owner. No
  ported *relic*, *potion* or *card* is removed from inside a dispatch it
  listens to. Concrete trigger: a hook whose listener melts a relic, discards a
  potion, or removes a card from combat while a *later* listener of the same
  category is still pending in that dispatch; the `IsActiveForHooks` half needs
  a second player, i.e. multiplayer, and is the only part of this gap that is
  out of scope.
- **G8 — no `IsOverOrEnding` gate on combat dispatches. DORMANT.**
  `Hook.IterateCombatHookListeners` (`Hook.cs:53-63`) yields **nothing** to a
  dispatch that begins after combat started ending; 73 of the 147 dispatchers
  go through it (step 21). The sim has no such gate — `combat.py` flips
  `Phase.COMBAT_OVER` only inside `_end_combat`, and no dispatcher consults the
  phase. Executed: a combat with the ported relic Daughter of the Wind
  (`relics/daughter_of_the_wind.py:23-33`) and a lethal Strike shows the sim
  granting its 1 Block from `on_card_played` **after** `_all_enemies_dead()` is
  already true — the game reaches no listener there (and `CardModel.cs:1957`
  guards the call site as well). Dormant because every effect currently
  reachable on that path is combat-scoped state the combat then discards:
  block, per-combat relic counters, and powers on creatures that are about to
  be torn down. Concrete trigger: porting a listener on a guarded dispatcher
  that mutates **run-level** state — HP, gold, or the deck — from
  `AfterCardPlayed`, `AfterCardDrawn`, `AfterCardExhausted`, `AfterShuffle` or
  `AfterEnergySpent`; the conformance exporter is the near-term risk, since
  extra listener side effects after the deciding blow can perturb the recorded
  combat state.
- **G9 — the sim aggregates additive/multiplicative modifiers in parallel
  where C# threads a running value. LIVE.** *(New in the fix pass; the first
  pass verdicted this shape `faithful` at step 31 on the grounds that no
  dispatcher this record owns uses it, and `damage_pipeline`'s guard **N3**
  called it a `deliberate-divergence`. Both were wrong, and rule 3 was
  violated across the two records into the bargain.)* C# folds each
  contribution into a running `decimal` as it goes —
  `num += item.ModifyDamageAdditive(target, num, …)`, then
  `num *= item.ModifyDamageMultiplicative(target, num, …)`
  (`Hook.cs:2515-2538`; `ModifyBlock` 1320-1337 is the same). The sim hands
  **every** listener the same pre-step base and aggregates the returns
  (`hooks.py:52-64` sum, `66-78` product, `98-122` for block), and the caller
  applies the aggregate once: `amount = amount +
  hooks.modify_damage_additive(...)` then `amount = int(amount *
  hooks.modify_damage_multiplicative(...))` (`cmds.py:57-58`; `145-147` for
  block). **Settled by execution, in three parts:**
  1. The base-vs-running *argument* is inert. `py
     tools/audit/dormancy_probes.py cs-running-value` finds **0 of 46** C#
     `Modify{Damage,Block}{Additive,Multiplicative}` overrides — and 0 of the
     9 `Enchant*` ones — reading the value they are handed; `sim-running-value`
     finds **0 of 31** sim implementations reading theirs. Not "no *ported*
     one": none in the whole decompiled source.
  2. The **additive** family is therefore exactly equal —
     `base + Σaᵢ == (((base + a₁) + a₂) + …)` over integers, 0 mismatches in an
     exhaustive sweep.
  3. The **multiplicative** family is **not**, because the sim multiplies the
     *factors together in float* before applying them. **LIVE:** Shrink
     (×0.7 on the dealer, `powers.py:1366-1387`, applied by the ported Act-1
     **Shrinker Beetle**, `monsters/overgrowth/shrinker_beetle.py:39-40`, and
     by the Shrink Potion, `potions.py:718-722`) plus Vulnerable (×1.5 on the
     target, `powers.py:403-417`, applied by the ported Bash) on a 20-damage
     powered attack: `1.5 * 0.7 == 1.0499999999999998`, `20 * that ==
     20.999999999999996`, `int(...) == 20` — the game computes `20m × 1.5m =
     30m`, `30m × 0.7m = 21m`. **Executed: the sim deals 20 where the game
     deals 21**; base 40 gives 41 vs 42. A control that keeps the sim's float
     arithmetic but threads it sequentially returns 21, so this is the
     **aggregation shape**, not float-vs-decimal representation.

  Because the outcome can and does differ, it is a **gap**, not a
  `deliberate-divergence`. Carried at **all three** recorded sites with the
  same verdict and cross-references (rule 3): step 31 here,
  `damage_pipeline`'s guard **N3** (raised in the same pass), and — since
  2026-07-26, fix pass 2 — clause (c) of `creature_card_cmds`' step 13, the
  **block** site, where the shape is identical but the gap is *dormant*
  because every ported block factor is binary-exact. See
  "Cross-seam consequences".

### Notes and waivers

- **N1 — multiplayer plumbing.** `PlayerChoiceContext` push/pop (step 23),
  `HookPlayerChoiceContext` + `AssignTaskAndWaitForPauseOrCompletion` and the
  `LocalContext.NetId` early return (step 24), the grouped `Task.WhenAll`
  (step 25), and `MultiplayerScalingModel` (step 10). Genuinely out of scope:
  one local player, no async pausing, no net identity. *Fix pass: the
  `OrbQueue` listener block (step 8) used to be filed here and is not
  multiplayer — it moved to **N7**.*
- **N2 — presentation and modding.** `InvokeExecutionFinished` /
  `ExecutionFinished` (step 22; `AbstractModel.cs:64-68` says it is
  "a little unreliable, so you should only use it for UI things") and the
  `ModHelper.IterateAll*Subscribers` tails (steps 13, 17).
- **N3 — `CombatHistory` is a sim-only listener.** `combat.py:111-112`
  registers it first, before anything else, so it observes every event before
  any relic or power. The game has no history listener: `CombatManager.History`
  is written by explicit calls (`CardModel.cs:1930`, `1956`), not by hooks.
  Deliberate divergence — the observable is identical because `CombatHistory`
  only records, and being first is exactly what makes the recording complete
  when a later listener reads it (`relics/paels_eye.py:27-34` is one such
  reader; `grep -rn "combat.history" sts2_rl/` finds nine reader modules —
  `paels_eye`, `powers.py` and seven card modules). *Fix pass: the record used
  to name `relics/whispering_earring.py` as the second reader. It reads no
  history at all — corrected, and not hashed.*
- **N4 — `Modifiers` and `BadgeModels`.** `Modifiers` are custom/daily-run
  mutators loaded from `save.Modifiers` (`RunState.cs:296, 344`) and empty in a
  standard run; `BadgeModels` are cloned into every run (`RunState.cs:332`) but
  `BadgeModel.cs:3-9` says they exist to "keep track of stats for badges", and
  an executed scan (`py tools/audit/dormancy_probes.py cs-badge-hooks`) finds
  that of the 29 files under `src/Core/Models/Badges/` only two override any
  `AbstractModel` hook at all (`CccComboModel`: `AfterCardPlayed`,
  `AfterSideTurnStart`; `DebufferModel`: `AfterPowerAmountChanged`) and **none**
  overrides a `Should*`/`Modify*`/`TryModify*` hook — they are pure event
  listeners. Both are out of scope for the same reason ascension values are.
- **N5 — the run/combat delegation split.** In combat, a run-level dispatch
  visits deck cards first and then the whole combat list (steps 14-18). The sim
  has no run-level `HookSystem`; run-scoped hooks are duck-typed directly over
  `run.relics` (`relics/base.py:205-235`) and deck cards are never run
  listeners. Recorded as a gap in the record's steps 14 and 18 rather than a
  waiver, because a deck card with a run-level hook override would never fire.
- **N6 — `ShouldReceiveCombatHooks` has no consumer.**
  `AbstractModel.cs:62`
  declares it abstract and 19 model classes override it, but a whole-source
  grep finds **zero** reads. It documents intent (`CardModel.cs:1045`:
  `Pile?.IsCombatPile ?? false`) and the real filtering is done structurally by
  which lists `IterateHookListeners` walks. Faithful by vacuity — the sim has
  no counterpart and needs none.
- **N7 — character scope (new in the fix pass).** The `OrbQueue` listener block
  (step 8, `CombatState.cs:448`) and the orb-shaped dispatchers that go with it
  (`ModifyOrbValue` 1874, `ModifyOrbPassiveTriggerCount` 1855,
  `AfterOrbChanneled` 844, `AfterOrbEvoked` 858,
  `AfterModifyingOrbPassiveTriggerCount` 784). Orbs are the **Defect's**
  mechanic and the sim implements one character, the Ironclad, so there is no
  orb queue to place in the listener order and no orb listener whose position
  could be wrong. That is a **character-scope** exclusion of the same kind as
  ascension values — **not** multiplayer, which is why it no longer sits under
  **N1** and why the split was worth making: reading step 8 as "waived because
  multiplayer" was simply false. It becomes a real ordering question the moment
  a second character is ported, at which point the slot is between
  `PotionSlots` and the cards (`CombatState.cs:436-449`) and **G2** already
  covers getting it wrong.

## Pins (Step D)

The brief's pin table lists one behaviour, *listener-order determinism*, with
"grep `test/` for `register` order in `test_new_features.py`". Grepped:
`test/test_new_features.py` contains **no** occurrence of `register`, and a
tree-wide `grep -rn "_listeners\|hooks.register" test/` finds only three
incidental `_listeners` lookups (`test/test_ancients.py:747`, `:788`, `:953`,
each fishing a single relic instance out of the list) and one registration in
`test/test_hive.py:562`. **No equivalent coverage exists**, so the pin was
added.

All pins live in `test/test_hook_order.py::TestHookDispatchOrder`, alongside the
module-level helper `listener_categories`.

| test | kind | pins |
|---|---|---|
| `test_dispatch_order_is_registration_order_grouped_by_category` | passing | the sim's cross-listener ordering rule, both as the composition of `_listeners` and as the order a real dispatch visits them in |
| `test_powers_modify_energy_cost_before_relics_do` | strict xfail | **G2** |
| `test_late_energy_cost_modifiers_run_after_early_ones` | strict xfail | **G3** |
| `test_before_card_played_fires_once_per_replay_iteration` | strict xfail | **G4** |
| `test_no_listener_runs_after_the_combat_starts_ending` | strict xfail | **G8** (dormant) |
| `test_multiplicative_damage_modifiers_chain_sequentially` | strict xfail | **G9** (added in the fix pass) |

`test_hook_order.py` therefore holds **25** xfails where it held 24, and the
suite baseline moves from 2476 passed / 30 xfailed to 2476 passed / 31 xfailed.

The passing pin is deliberately **not** a two-listener spot check: it builds a
combat holding all five listener categories the game walks (9 cards, 2 relics,
1 belt potion, 2 powers — one on the player and one on the enemy), asserts the
whole category sequence, and then asserts that an actual dispatch visits
`_listeners` in exactly that order. A future change to registration order, or a
replacement of the flat `_listeners` list with anything structural, fails here.

**G1**, **G5**, **G6**, **G7** and **N5** are not pinned because they are not
pinnable today: each needs a listener that does not exist in the sim (a second
contending card hook, a monster or affliction hook implementer, a relic/potion
removed mid-dispatch, a deck card with a run-level hook). Their dormancy
arguments are executed instead, and each names the concrete thing that would
make it both live and pinnable.
