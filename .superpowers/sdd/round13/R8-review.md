# R8 review — unlabelled batch `relic-2` (14 entries, 13 records)

Reviewer verdict: **NEEDS-FIXES**.

Every one of the 14 substantive verdicts survives review — I re-derived all of
them against the C# and today's tree and did not overturn a single one. What
fails is the layer this campaign says fails most: the **reasoning and the
evidence**. Three of the nineteen tests do not exercise the mechanism they
claim to pin (two of them pass with the mechanism deleted — I mutated and
confirmed), one close note the controller applies verbatim misattributes a
closure to this round that is present unchanged at `HEAD`, the lane's single
production edit ships a factually false sentence in the docstring it was
written to correct, and the report missed a third instance of its own headline
staleness pattern sitting inside its own manifest.

Separately I found one unrecorded divergence that outranks the task — see §0.

---

## 0. Findings that outrank the task

### 0.1 NEW (unrecorded): `Relic._check_win()` has the win/loss tie-break backwards

`sts2_rl/relics/base.py:483-488`:

```python
def _check_win(self) -> None:
    if not self.combat.is_over and self.combat._all_enemies_dead():
        self.combat._end_combat(player_won=True)
```

`CombatManager.CheckWinCondition` (`CombatManager.cs:1046-1058`) tests the
**pending loss FIRST**:

```csharp
if (_pendingLoss != null) { ProcessPendingLoss(); return true; }
if (IsEnding) { await EndCombatInternal(); return true; }
```

The sim's own port of that method has it right —
`CombatState._check_win_condition` (`combat.py:711-718`) reads
`if self._has_pending_loss: self._process_pending_loss() elif
self._all_enemies_dead(): ...`, with the comment *"CombatManager.cs:1048 — the
pending loss is tested FIRST, so it wins a tie in which the player and the last
enemy die together."* **`Relic._check_win` never got that fix.**

`seam/turn_structure.json` guard **G13**'s own close note claims the bug class
was eliminated: *"The four inline `_all_enemies_dead()/is_dead` pairs in
play_card, auto_play, use_potion and the turn tail were CheckWinCondition with
the tie-break the wrong way round; they call `_check_win_condition()` now, so a
simultaneous death resolves as a LOSS as CombatManager.cs:1048 does."* There
was a **fifth** site. It is the relic helper, and **ten relics route through
it**: `charons_ashes`, `festive_popper`, `forgotten_soul`, `kusarigama`,
`letter_opener`, `lost_wisp`, `mercury_hourglass`, `parrying_shield`,
`screaming_flagon`, `stone_calendar` (grep `_check_win()` over `sts2_rl/`).

EXECUTED (scratchpad `r8_probe4.py`), identical state (`player.hp = 0`, last
enemy `hp = 0`) fed to both:

```
A. combat._check_win_condition()  -> CombatResult(player_won=False)   # C#-correct
B. relic._check_win()             -> CombatResult(player_won=True), player hp 1
```

B also revives the player to 1 HP via `_end_combat_internal`'s
`ReviveBeforeCombatEnd` port — so the divergence is not "the result field is
wrong", it is **a lost run converted into a won combat.**

**Liveness: DORMANT today, and I established that by execution, not by
assertion.** Two candidate paths, both closed:

* *Player dies first, then a relic kills the last enemy.* Closed by
  `DamageCmd.deal`'s dead-dealer guard (`cmds.py:272-273`,
  `CreatureCmd.cs:242-245`): every one of the ten relics passes
  `dealer=self.player`, so a dead player's relic damage deals 0 and
  `_all_enemies_dead()` cannot newly become true.
* *A card kills the last enemy and the player simultaneously, then an
  exhaust-triggered relic runs `_check_win()`.* Built it for real (probe 5/6):
  player at 1 HP, `charons_ashes` held, `molten_fist` (exhausts) into a
  `Toadpole` with `ThornsPower`. Both die. Result: `player_won=False` — the
  post-card `_check_win_condition()` (`combat.py:637`) processes the loss and
  the phase gate stops the exhaust hook from ever reaching the relic. Verified
  the probe was not simply inert: the same setup with a healthy player shows
  Charon's Ashes firing normally (enemy 200 → 187 = card 10 + relic 3).
* Also checked and cleared: no `on_death` in `monsters/**`, `powers.py` or
  `relics/**` deals damage, so an enemy cannot kill the player as it dies
  inside the relic's own loop; `ThornsPower.before_damage_received`
  (`powers.py:589-607`) requires `is_powered_attack(props)`, which relic damage
  (`NON_CARD_UNPOWERED`) never is.

**Recommend filing** as a new guard on `seam/turn_structure.json` (the record
whose G13 owns the mechanism), verdict `gap`, DORMANT-ENUMERATED, with the
enumeration above. Note it also silently contradicts the "faithful" verdicts
those ten relic records give `_check_win` (`charons_ashes` N4,
`parrying_shield` N3, `mercury_hourglass` N4, `letter_opener` N1 …) — those
call it "the sim's stand-in for the CheckWinCondition that follows the game's
own commands", which is true of the win arm and false of the loss arm.

### 0.2 A THIRD cross-record staleness, inside R8's own manifest, unreported

The report's §5 headline is that dormancy arguments leaning on another
record's guard go stale when that guard closes. It found two
(`bag_of_marbles/G2 → power_cmd/G6`, `festive_popper/G3 →
turn_structure/G13`). There is a third, in the same record as the second:

`relic/festive_popper.json` guard **G1** still reads `verdict: gap`, and its
text is *"C#'s hook is AfterPlayerTurnStart, turn_structure step 22; the sim's
`on_player_turn_started` is the step-23 AfterSideTurnStart slot … The sim has
one post-draw slot for both."* Both halves are now false:

* `hooks.py:1210-1216` — `on_player_turn_started` is `Hook.AfterPlayerTurnStart`
  **alone**; its docstring says *"This used to double as the player-side
  `Hook.AfterSideTurnStart`, which is a different hook at a different point"*.
  The manifest's own hook-level text already records this ("G1, the slot, is
  CLOSED"), so the record contradicts itself.
* G1's stated residual observable — *"the Imbued enchantment's auto-play fires
  from the SAME `on_player_turn_started` dispatch … That is
  `seam/hook_dispatch.json` gap G2 and `seam/turn_structure.json` gap G8"* — is
  gone twice over: `turn_structure/G8` reads `faithful` ("CLOSED … the
  six-value PlayerTurnPhase model exists"), the sim has a real
  `after_auto_pre_play_phase_entered` dispatch (`player.py:282`,
  `hooks.py:1239-1244`) that `enchantments.py:384` (Imbued) is on, and
  `hook_dispatch.json` **has no G2 or G3 guard at all**, at `HEAD` or in the
  worktree.

The report asserts "G1 (hook slot) was already closed before this round" but
its close proposal #3 does **not** ask the controller to flip G1's verdict or
replace its reasoning. That leaves a `gap`-verdict guard standing on text every
clause of which is stale. **Add to proposal #3.**

---

## 1. Per-entry verdicts

### `relic/bag_of_marbles/BeforeSideTurnStart` (G2) — **CONFIRM (dormant)**, close note NEEDS-FIX

Verdict re-derived independently, not inherited:

* `CombatState.cs:142` `HittableEnemies => Enemies.Where(e => e.IsHittable)`;
  `Creature.cs:285-299` `IsHittable` = `!IsDead && Hook.ShouldAllowHitting`.
  `bag_of_marbles.py:22` still loops `living_enemies()`
  (`relics/base.py:470-477`, `not e.is_gone`). Call-site divergence real. ✔
* The set-coincidence proof holds, and I widened it rather than checking the
  recorded consumers: `grep -rn "def should_allow_hitting" sts2_rl/` returns
  **exactly four** hits — the dispatcher (`hooks.py:1962`) and three
  implementers (`powers.py:1996` Illusion, `:2920` Reattach, `:4175`
  Adaptable). All three are byte-identical in shape
  (`if target is self.owner and self.is_reviving: return False`), `is_reviving`
  is written **only** from `on_death` (`powers.py:1994`, `:2917`, `:4172`), and
  each revive method clears it **before** restoring HP (`:2003`, `:2929`,
  `:4181`) — so there is no window in which `is_reviving` holds and `is_dead`
  does not. `is_gone = is_dead or escaped` (`creatures.py:51-53`), and
  `is_hittable` (`cmds.py:118-123`) is `not is_gone and should_allow_hitting`,
  so `hittable_enemies ⊆ living_enemies` unconditionally and the two coincide
  for every reachable creature. ✔
* The backstop claim is real: `can_receive_powers` (`cmds.py:65-75`) is
  `not is_removed_from_combat and hooks.should_allow_hitting(target)` and
  `PowerCmd.apply` calls it at `cmds.py:841` — the faithful port of
  `PowerCmd.cs:103`'s `!target.CanReceivePowers`. ✔ **And it is load-bearing**:
  in a two-enemy combat (so `is_ending` is false) a hand-fed reviving enemy is
  refused, but neutering `can_receive_powers` to always-`True` lets Vulnerable
  land. ✔

**NEEDS-FIX (a): the pinning test does not pin.**
`test_power_cmd_apply_backstops_bag_of_marbles_against_an_unhittable_target`
uses a **one**-enemy encounter and then kills that enemy. That makes
`is_ending(hooks)` true, so `PowerCmd.apply` returns at `cmds.py:830-831`,
**before** `can_receive_powers` at `:841` is ever consulted. Mutation-verified
(`r8_probe2.py`): with `can_receive_powers` replaced by `lambda *_: True` the
assertion still passes. Fix is one character — build the encounter with two
`LeafSlimeS` (I ran it: backstop live → not applied; backstop deleted →
applied).

**NEEDS-FIX (b): the dating in the close note is backwards.** `power_cmd/G6`'s
own history is: entry guard added 2026-07-27, narrowed 2026-07-28 (rounds 3/4),
`FIXED 2026-07-29 (round 5)`. `bag_of_marbles.json`'s `audited` is
**2026-07-26**. So the fix is **after** the audit — an ordinary
"record predates the fix". The report says it three ways and all three are
incoherent: *"closed in round 4 (2026-07-28), **before** this record's own
2026-07-26 audit date reads as current"*; the close note's *"before this
record's own 2026-07-26 audit date was last revisited"*; and the queue note's
*"stale by three rounds"* (round 5 → round 13 is eight). Rewrite as: *"closed
2026-07-29 (round 5), three days after this record's 2026-07-26 audit; the
record was never revisited."*

### `relic/charons_ashes/AfterCardExhausted` (G1, G3) — **CONFIRM (verdicts)**, reasoning **OVERTURNED**

G1 dormant ✔, G3 `deliberate-divergence` ✔ (`CreatureCmd.cs:240-411` batches;
`cmds.py` still one `DamageCmd.deal` per enemy).

**OVERTURN of the stated reason.** The report says G1 is dormant "for the SAME
two reasons: the set-coincidence proof, plus the pre-existing `DamageCmd.deal`
backstop (`cmds.py:289: if not hooks.should_allow_hitting(target): return 0`)"
and calls it "the same full backstop `charons_ashes` already has". **That line
is dead code.** `DamageCmd.deal` opens (`cmds.py:287-290`):

```python
if target.is_dead:                                  # CreatureCmd.cs:256-259
    return 0
if not hooks.should_allow_hitting(target):
    return 0
```

`should_allow_hitting` can only be false when `is_reviving`, which implies
`is_dead` (proved above), so line `:289` is **dominated by line `:287` and can
never fire**. Executed (`r8_probe3.py`), two-enemy combat, `is_ending` false,
reviving target: `dealt == 0` with the hook live **and** `dealt == 0` with
`should_allow_hitting` neutered. Dormancy on the damage side therefore rests on
the set-coincidence argument **alone**; there is no second, independent leg.
This matters because the report's whole framing — *"this is no longer 'no
backstop exists,' it is 'the same full backstop `charons_ashes` already has'"*
— is what carries the strengthened close notes for four entries.

**NEEDS-FIX: `test_damage_cmd_deal_backstops_the_damage_relics_against_an_unhittable_target` is a null test.**
It asserts `dealt == 0 and enemy.hp == hp_before` on a target whose HP is
already `0` (it was killed with 9999 to arm the revive), in a one-enemy combat
where `is_ending` is true. It passes with `should_allow_hitting` deleted, with
`is_dead` deleted, and in every configuration I could build. Delete it or
rewrite it against the guard that actually refuses.

### `relic/festive_popper/AfterPlayerTurnStart` (G2, G3) — **CONFIRM (dormant)**, basis NEEDS-FIX, close proposal INCOMPLETE

G3's divergence is real and I re-derived it from the C# without leaning on the
report:

* `FestivePopper.cs:19-31` — `AfterPlayerTurnStart`, turn 1, `CreatureCmd.Damage`
  over `HittableEnemies`. No win check in the relic.
* `Hook.cs:30-45` is decisive and the report never cites it: *"The check is
  evaluated once, when enumeration begins, not per listener. A dispatch that
  begins while combat is live therefore runs every listener even if one of them
  ends combat partway through. That is intentional: **combat teardown is
  deferred to the next safe point (CheckWinCondition)**, so the state stays
  intact for the rest of the dispatch."* And `CheckWinCondition`
  (`CombatManager.cs:1046-1058`) only *dispatches* teardown; the kill path
  merely sets `IsEnding`.
* `CombatManager.cs:573` is the next such point — after
  `RunAutoPrePlayPhase`, i.e. after steps 23/24/26.
* The sim's `Relic._check_win` runs `_end_combat` → `_end_combat_internal`
  (`combat.py:754-781`) **immediately**, firing `on_combat_end()` and
  `on_combat_victory()` inside the relic's own call. That is the divergence:
  C# defers the teardown, the sim performs it mid-dispatch. ✔

**NEEDS-FIX: the report's stated basis is wrong.** It says *"Re-read
`combat.py`'s `_start_player_turn` in full: it calls `self.player.start_turn()`
and nothing else — no `_check_win_condition()` call sits between the turn-start
dispatch and the method's return."* The sim **does** have a recompute at
`CombatManager.cs:573`'s position — `combat.py:333-340` calls
`_start_player_turn()` then `_check_win_condition()`, with a comment naming
`:573` explicitly, and `turn_structure/G13`'s close note names that exact site
as one of its fixes (`:1524-1525`, `:1544-1550` are the other two). Picking the
*method* rather than its caller makes the claim technically true and
substantively misleading, and it is the sentence the queue annotation is built
on. Restate against `Hook.cs:30-45` (deferred teardown) — which is the real,
citable ground and is stronger.

**Close proposal #3 is incomplete** — it must also flip guard G1; see §0.2.

The test itself (`test_festive_popper_check_win_still_ends_combat_inside_its_own_dispatch`)
is sound: 1-HP enemy, direct `on_player_turn_started`, `cs.is_over` True on
return. It fails if `_check_win()` is removed. ✔

### `relic/gambling_chip/AfterPlayerTurnStart` (G1, G2) — **CONFIRM**, best work in the batch

Both censuses re-executed independently and both hold, wider than the tests
check:

* `grep -rn "def after_card_changed_piles" sts2_rl/` → **one** hit, the
  dispatcher (`hooks.py:1406`). Zero implementers package-wide, including
  `monsters/**`, which the test's registry scan does not cover
  (`monsters/hive/thieving_hopper.py:125` only *calls* it). The six wired call
  sites are real: `player.py:441,482,588`, `cmds.py:1346,1464`,
  `thieving_hopper.py:125`. ✔
* Sly: zero `sly = True` across `_CARD_CLASSES`, zero callers of
  `give_single_turn_sly(`. ✔
* The citation correction is right — `book_of_five_rings`/`bing_bong`/
  `darkstone_periapt`/`lucky_fysh` are `after_card_added_to_deck` listeners. ✔

One report-quality defect: §1 contains an unedited fragment — *"G3 (min-0
decline) is already `faithful`/closed (`"obtain"`… no, `"gambling_chip"` is in
`driver.py`'s `SKIPPABLE_PURPOSES`)"*. The claim happens to be true
(`driver.py:98-101` contains both), but a self-correction left in the prose of
a document the controller reads as a record source should be cleaned up.

### `relic/hefty_tablet/AfterObtained` (G2) — **CONFIRM (dormant)**, one test NEEDS-FIX

* G1 faithful re-verified: `hefty_tablet.py:35` calls
  `reward_pool_card_ids(pool=run.card_pool)` (the reward-stream helper), not
  the `FilterForCombat` mirror. ✔ G3 faithful: `"obtain"` ∈
  `SKIPPABLE_PURPOSES`. ✔
* `test_hefty_tablet_after_obtained_never_calls_modify_card_reward_options` is
  a genuine mechanism demonstration — a spy relic co-held in a real `RunState`
  sees zero calls. ✔ Implementer count 4 → 7 spot-checked. ✔

**NEEDS-FIX: `test_hefty_tablet_g2_reachability_floor0_holds_no_reward_modifying_relic` asserts nothing, and is wrong-shaped.**
`RunState(rng=...)` starts with `run.relics == []` (verified), so the `for r in
run.relics` body **never executes** and the only live assertion is
`run.total_floor == 0`. Worse: `Relic` **declares both methods on the base**
(`relics/base.py:299`, `:314`), so `hasattr(type(r), "modify_card_reward_options")`
is `True` for all 258 relics — had `run.relics` contained a single relic of any
kind the test would fail. It is simultaneously vacuous and incorrect. Either
delete it, or assert against `cls.__dict__` overrides on the relic the Neow
event actually grants alongside `hefty_tablet`.

### `relic/letter_opener/AfterCardPlayed` (G2) — **CONFIRM (dormant)**, inherits §1's reasoning defect

`letter_opener.py` loops `living_enemies()` then `DamageCmd.deal`;
`LetterOpener.cs:118` reads `HittableEnemies`. Dormant by set-coincidence. The
report's "backstopped identically" leans on the dead `cmds.py:289` line — same
correction as `charons_ashes`. Verdict unchanged.

### `relic/paper_phrog/ModifyVulnerableMultiplier` (G1, N2) — **CONFIRM**

* G1: I ran the census wider than the test does —
  `grep -rn "def modify_vulnerable_multiplier" sts2_rl/` returns the
  dispatcher (`hooks.py:1050`) and `paper_phrog.py:21`, nothing else. The test
  scans `ALL_RELICS` only, which would miss a power/card/monster implementer;
  the conclusion is nonetheless true today. Widen the test to the grep. ✔
* N2: the Brand test is real work — instrumented `DamageCmd.deal`, real
  `cs.play_card(0)`, asserts the self-hit was actually observed before
  asserting it is unpowered. Exactly the shape the round-12 lesson asks for. ✔
* C# cross-check: `VulnerablePower.cs:40-44` is the single direct
  `dealer.Player?.GetRelic<PaperPhrog>()` lookup; the sim's chain would
  double-apply with a second implementer. ✔

### `relic/philosophers_stone/AfterCreatureAddedToCombat` (G1) — **CONFIRM (dormant)**

Re-derived: `Hook.AfterCreatureAddedToCombat` is dispatched from **exactly one**
site in the whole C# codebase, `CreatureCmd.cs:81` (grepped). Notably
`CombatManager.StartCombatInternal:394-397`'s `AfterCreatureAdded(creature)`
loop is a *different, private* CombatManager method and does **not** dispatch
the hook — so starting enemies never receive it, and the sim's `combat.py:325`
(which calls `after_creature_added` without the hook) matches. The sim's only
`on_creature_added` dispatch is `cmds.py:834`, whose only destination is
`combat.enemies`; there is no allies list to place a player-side non-player
creature in (`cmds.py:80` and `hooks.py:360` reference C#'s `_allies` only as
an index-space comment). `PhilosophersStone.cs:41-48` confirms the side test.
The test is a demonstration rather than an enumeration, but the enumeration
holds. ✔

### `relic/ruined_helmet/TryModifyPowerAmountReceived` (G2, G3) — **CONFIRM STALE-ALREADY-FIXED**

Fully re-derived from the C# rather than from the seam record's date stamp:

* `RuinedHelmet.cs:32-53` — four clauses + `modifiedAmount *= 2m`;
  `:55-60` — `AfterModifyingPowerAmountReceived` sets `UsedThisCombat`.
* `Hook.cs:1915-1930` — `ModifyPowerAmountReceived` is a **single** pass of
  `TryModifyPowerAmountReceived`, each true return replacing `num` and joining
  the `modifiers` list. `Hook.cs:1888-1912` — the GIVEN side is two passes
  (additive sum, then multiplicative product).
* `PowerCmd.cs:122-126` — GIVEN gated on
  `applier != null && combatState.ContainsCreature(applier)`, RECEIVED
  unconditional; `:148-152` — both companion events **after** `ApplyInternal`.
  `:229-233` / `:238-242` — the same pair inside `ModifyAmount`, after
  `SetAmount`.
* Sim: `hooks.py:910-992` declares the three dispatchers separately;
  `cmds.py:902-918` calls them in C#'s order under C#'s gate;
  `cmds.py:933-936` fires both companions after the mutation.
  `ruined_helmet.py:27-57` is a real RECEIVED listener; `:59-62` is a real
  companion-event method.
* Predicate-order note (checked, not a divergence): the sim tests `self._used`
  first where C# tests it last; all four clauses are side-effect-free, so the
  orders are equivalent. `canonicalPower is StrengthPower` is subclass-inclusive
  in C# and `power_cls is not StrengthPower` is exact in the sim — checked:
  `StrengthPower` has zero subclasses in the sim, and C#'s
  `TemporaryStrengthPower : PowerModel` is not one either. Equivalent.

Both guards genuinely close. ✔

### `relic/ruined_helmet/AfterModifyingPowerAmountReceived` (G3) — **CONFIRM STALE-ALREADY-FIXED**

`hooks.py:1032-1049` fires only for listeners in the `modifiers` list, mirroring
`Hook.cs:811-824`. The test's load-bearing half (bare modifier returns 4 and
leaves `_used` False) is a real structural proof. Its second half
(`relic.after_modify_power_amount_received(None)` sets `_used`) is near
tautological but harmless.

**NEEDS-FIX (citation):** the test docstring says *"`PowerCmd.cs:55-60`'s own
hook"*. It is **`RuinedHelmet.cs:55-60`**. `PowerCmd.cs:55-60` is unrelated.
This campaign has a citation-accuracy gate; fix before the note is copied.

### `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — **CONFIRM the narrowing**, **OVERTURN the attribution**

The closure itself is correct and I proved it by mutation rather than by
reading:

* `Hook.cs:1574-1590` — `ModifyEnergyCostInCombat` is `if (originalCost < 0m)
  return`, then **two complete `IterateCombatHookListeners` passes**: every
  `TryModifyEnergyCostInCombat`, then every `…Late`. There is no per-creature
  grouping in this dispatcher at all, so the manifest's rollup phrase "no
  per-creature listener grouping" is G1's subject, and G1 is already `faithful`.
* Mutation (`r8_probe7.py`), the record's own worked example (Curious 2 +
  Spiked plain + Scarf Late, 1-cost `inflame`):
  `_PHASES` intact → **0**; `_PHASES` forced to `("",)` → **1**; restored → 0.
  The two-pass shape is real and load-bearing. And it is **order-independent**:
  registering the Scarf first also yields 0, which is the direct refutation of
  G2's recorded observable *("the sim gives 0 or 2 depending on which relic was
  obtained first")*. ✔
* G3 stays open, dormant: `energy_cost_x` is truthy on exactly
  `volley`/`whirlwind`/`cascade` (ATTACK/ATTACK/SKILL) — census re-run, non-vacuous. ✔

**OVERTURN: "a FRESH closure this round" is false, and it is in the close note
the controller applies verbatim.** The report says the phase machinery is what
*"`hooks.py`'s `_each` generalized this round"*. At `HEAD`:
`git show HEAD:sts2_rl/hooks.py` already has `_PHASES` at line 36, `_phased`
maintained at `:205/:278`, and the phase loop in `_each` at `:400-401`; and
`git show HEAD:sts2_rl/relics/brilliant_scarf.py:29` already defines
`modify_card_energy_cost_late`. `git diff HEAD` for both files is **empty**.
`seam/hook_dispatch.json` **had no G2 or G3 guard at `HEAD` either** — the seam
gaps this relic's G2 cites were already closed and pruned in an earlier round.
The verdict (G2 closes) stands; the note must say **STALE — closed before round
13, the record was never revisited**, not "closes this round". Same species of
error as the one the report's own §5 is about.

### `relic/stone_cracker/AfterRoomEntered` (G2) — **CONFIRM (dormant)**

`CombatRoom.cs:228` fires `AfterRoomEntered` one full dispatch before
`Hook.BeforeCombatStart`; `combat.py:327` is the sim's single
`hooks.on_combat_start()`. Divergence real, dormant. The order-independence
demonstration is a genuine behavioural comparison (two orders, identical
`(upgraded, dazed)`). Weak only in that a 10×`strike` deck makes the count the
only observable — acceptable, since card identity is degenerate there.

### `relic/sword_of_jade/AfterRoomEntered` (G1) — **CONFIRM (dormant)**, enumeration OVERSTATED

Verdict correct; the report's description of its own evidence is not. It says
the test *"scans every `on_combat_start` implementer outside the twelve
AfterRoomEntered-side relics"*. The test iterates **`ALL_RELICS` only**. I ran
the wider scan: `powers.py` has two `on_combat_start` implementers,
`vital_spark` and `galvanic` — neither reads Strength (both afflict cards), so
the verdict survives; but "every implementer" was not checked, and a sibling
lane was rejected this round for exactly this (4 named where 10 existed). Two
further narrownesses to note in the close: the test reads `cls.__dict__` (an
inherited `on_combat_start` on an intermediate relic base would be invisible),
and its `read_patterns` are four literal substrings — a Strength read through a
helper or a `StrengthPower.id` constant would not match. `sling_of_courage` is
correctly cleared; I also checked `unsettling_lamp` (the other order-sensitive
combat-start listener) and it cannot bite here — `modify_power_amount_given_multiplicative`
requires `self._in_flight is not None` (a card play) and `target is not
self.player`, and Sword of Jade's Strength is a non-card grant to the player.

### `relic/vambrace/g6` (N3) — **CONFIRM the fix is docstring-only**, content NEEDS-FIX

`git diff HEAD -- sts2_rl/relics/vambrace.py` is exactly six lines in, three
out, entirely inside the class docstring. **No behaviour change.** ✔
`test/test_r13_relic2.py` is the only other file. Footprint respected. ✔

Against `Vambrace.cs` the new docstring is right on the load-bearing points:
`AfterModifyingBlockAmount` (`:82-96`) latches `TriggeringCard` and nothing
else ✔; `AfterCardPlayed` (`:98-113`) sets `BlockGainedThisCombat` at the end
of the play ✔; `ModifyBlockMultiplicative` (`:57-80`) reads both fields ✔; both
line citations are correct ✔.

**NEEDS-FIX (a): the new docstring states something false.**
> "There is no `on_block_gained` method here or in the game"

`AfterBlockGained` is a real hook in **both** engines: `Hook.cs:143`, dispatched
from `CreatureCmd.cs:662`, overridden by `JuggernautPower.cs:17` and
`BeaconOfHopePower.cs:36`; and in the sim `hooks.py:138` maps
`"on_block_gained" → "AfterBlockGained"`, `hooks.py:1692` dispatches it,
`cmds.py:479` fires it, `powers.py:1068` implements it. The true statement is
"**Vambrace** overrides no `AfterBlockGained` hook — not in this port and not
in `Vambrace.cs`". For an entry whose entire subject is PROMPT.md bug class 24
(a docstring that misdescribes), shipping a replacement that misdescribes the
engine's hook surface is not acceptable. One-line reword.

**NEEDS-FIX (b), minor:** *"only `after_modify_block_amount`/`on_card_played`
ever WRITE those fields"* omits `__init__` (`:32-33`) and `reset_for_combat`
(`:38-39`), which write both. Say "only … write them **during a card play**".

**Test quality:** `test_vambrace_docstring_no_longer_claims_statelessness_or_on_block_gained`
asserts only the *absence* of two substrings — it passes against an empty
docstring or any wrong one. Since the entry is about a docstring, an assertion
that the text *names* the two real methods would be the pin. Not fatal; noted.

---

## 2. Record-close and queue-annotation proposals

Accurate as written, and do they say which reasoning they replace?

| # | Record / key | Accurate? | Says what it replaces? |
|---|---|---|---|
| 1 | `bag_of_marbles` `BeforeSideTurnStart` | **No** — dating incoherent (§1) | Yes |
| 2 | `charons_ashes` `AfterCardExhausted` | **No** — "no text change (still accurate)" leaves the dead-code backstop reasoning standing; and the test it cites is null | n/a |
| 3 | `festive_popper` `AfterPlayerTurnStart` | Partly — G3 handled; **G1 omitted** (§0.2); basis misstated (§1) | Yes for G3 |
| 4 | `gambling_chip` `AfterPlayerTurnStart` | Yes | Yes |
| 5 | `hefty_tablet` `AfterObtained` | Yes, but cites the vacuous test; should also ask to retire the stale hook-level rollup naming G1/G3 as open, as #11 does for `spiked_gauntlets` | Yes |
| 6 | `letter_opener` `AfterCardPlayed` | Same defect as #2 | n/a |
| 7 | `paper_phrog` | Yes | Yes |
| 8 | `philosophers_stone` | Yes | n/a |
| 9 | `ruined_helmet` `TryModifyPowerAmountReceived` + guard G2 | Yes | **Yes, exemplary** |
| 10 | `ruined_helmet` `AfterModifyingPowerAmountReceived` + guard G3 | Yes | **Yes, exemplary** |
| 11 | `spiked_gauntlets` G2 + rollup rewrite | **No** — misattributes the closure to round 13 (§1) | Yes |
| 12 | `stone_cracker` | Yes | n/a |
| 13 | `sword_of_jade` | Overstates the census breadth (§1) | n/a |
| 14 | `vambrace` N3 | Yes | Yes |

Queue annotations follow the house terse style; two carry the errors above
(`bag_of_marbles` "stale by three rounds"; `spiked_gauntlets` "CLOSES this
round").

---

## 3. Test quality

`py -m pytest test/test_r13_relic2.py -q` → **19 passed** (re-run by me, 0.94s).

| Test | Verdict |
|---|---|
| `…should_allow_hitting_false_still_coincides_with_is_gone` | ✔ real |
| `…power_cmd_apply_backstops_bag_of_marbles…` | **DEFECT** — confounded by `is_ending`; passes with `can_receive_powers` deleted |
| `…damage_cmd_deal_backstops_the_damage_relics…` | **DEFECT** — null; passes with the mechanism deleted in every configuration |
| `…festive_popper_check_win_still_ends_combat_inside_its_own_dispatch` | ✔ real |
| `…is_sly_this_turn_and_give_single_turn_sly_have_zero_consumers` | ✔ real census |
| `…after_card_changed_piles_has_zero_ported_implementers` | ✔ (narrower than my grep; same answer) |
| `…hefty_tablet_obtain_purpose_is_still_skippable` | ✔ thin but valid |
| `…hefty_tablet_after_obtained_never_calls_modify_card_reward_options` | ✔ real spy |
| `…hefty_tablet_g2_reachability_floor0…` | **DEFECT** — vacuous loop; and would fail on any relic (base declares both methods) |
| `…paper_phrog_is_still_the_sole…` | ✔ (relics-only scope; conclusion verified wider) |
| `…paper_phrog_n2_brand_self_damage…` | ✔ real play + spy; asserts the observation happened |
| `…on_creature_added_only_ever_reaches_combat_enemies` | ✔ demonstration |
| `…ruined_helmet_doubles_once_via_the_real_received_chain` | ✔ real |
| `…ruined_helmet_mark_used_lives_in_the_companion_event…` | ✔ (wrong citation in docstring) |
| `…spiked_gauntlets_g2_phase_machinery_now_generic_via_each` | ✔ **mutation-verified discriminating** |
| `…spiked_gauntlets_g3_x_cost_cards_are_still_never_powers` | ✔ non-vacuous |
| `…stone_cracker_and_tea_of_discourtesy_are_order_independent` | ✔ real comparison |
| `…sword_of_jade_g1_no_other_combat_start_listener_reads_strength` | ✔ narrower than described |
| `…vambrace_docstring_no_longer_claims…` | weak (absence-only) |

No test pins sim-against-sim by asserting a value it assigned itself.

---

## 4. Spec / protocol compliance

* **`audit/**` untouched by this lane.** ✔ The `audit/` diffs in the tree are
  `GAP-QUEUE.md`, `event/the_future_of_potions.json` and
  `tools/state_machine_probes.py` — the last is explicitly labelled
  "round 13 R11 item 4" in its own diff. None attributable to R8.
* **No git index mutation.** ✔ `vambrace.py` is unstaged ` M`;
  `test/test_r13_relic2.py` is untracked `??`.
* **Footprint.** ✔ `git status --short sts2_rl/relics/` at the start of this
  review showed `M  sts2_rl/relics/base.py` (staged by another lane, **clean
  worktree**) and ` M sts2_rl/relics/vambrace.py`. R8 left no edit in
  `relics/base.py`. (It has since gone `MM` under a concurrent lane — not R8's.)
  No other production file in the manifest's relic set is modified.
* **Test-command reporting.** ✔ Commands and counts given; full suite correctly
  not run.
* **`base.py` BLOCKED-ON-FOOTPRINT discipline.** The lane had no fix needing it
  — but §0.1's finding *does* live in `relics/base.py`, and had the lane found
  it, that is where it would have been reported. It did not find it.

---

## 5. Required fixes before this lane's proposals are applied

1. `vambrace.py` docstring: the `on_block_gained` sentence is false as written;
   scope it to Vambrace. Also scope the "only … WRITE" clause.
2. `test_power_cmd_apply_backstops_bag_of_marbles…`: build a two-enemy
   encounter so `is_ending` is false and the backstop is what refuses.
3. `test_damage_cmd_deal_backstops_the_damage_relics…`: delete or rewrite —
   the guard it names is dead code, dominated by `cmds.py:287`.
4. `test_hefty_tablet_g2_reachability_floor0…`: delete or rewrite — vacuous and
   wrong-shaped.
5. Close note #11 (`spiked_gauntlets` G2): "STALE — closed before round 13",
   not "closes this round". Evidence: `git show HEAD` on `hooks.py`,
   `brilliant_scarf.py`, `hook_dispatch.json`.
6. Close note #1 and the `bag_of_marbles` queue line: fix the dating
   (`power_cmd/G6` FIXED 2026-07-29, round 5; record audited 2026-07-26).
7. Close proposals #2 and #6: replace the "same full backstop" reasoning for
   `charons_ashes` / `letter_opener` / `festive_popper` G2 with
   set-coincidence-alone, and record that `cmds.py:289` is unreachable.
8. Close proposal #3: add the flip of `festive_popper` guard G1 (§0.2).
9. Test docstring citation `PowerCmd.cs:55-60` → `RuinedHelmet.cs:55-60`.
10. Report §1 `gambling_chip`: remove the unedited self-correction fragment.
11. **File the new gap in §0.1** (`Relic._check_win`'s inverted tie-break) on
    `seam/turn_structure.json`.

---

*Probes used, in the session scratchpad (not written into the repo):*
`r8_probe2.py` (backstop confounds + `can_receive_powers` mutation),
`r8_probe3.py` (`DamageCmd.deal` dead-code proof), `r8_probe4.py`
(`Relic._check_win` tie-break), `r8_probe5/6.py` (live-reachability attempts
with Thorns + an exhausting attack), `r8_probe7.py` (`_PHASES` mutation for
`spiked_gauntlets` G2).

---

# Re-review (2026-08-01)

**Verdict: APPROVED.** All eleven required fixes are done; every one of my §1
verdict confirmations still stands except `hefty_tablet` G2, whose liveness
flip I **independently reproduced and confirm**. I re-executed rather than
re-read: six fresh mutations of my own, an independent MRO census, an
independent end-to-end reachability search over 60,000 seeds, and independent
C# verification of the flag arithmetic the flip turns on.

## Item 1 — `hefty_tablet` G2 is **LIVE**. CONFIRMED, independently reproduced.

**The spec side is decisive, and it is stronger than the report states.**
`CardCreationFlags.cs` defines `NoUpgradeRoll = 2`, `NoHookUpgrades = 4`,
`NoModifyHooks = 8` — **and `NoUpgrades = 6`**, i.e. `NoUpgradeRoll |
NoHookUpgrades`, a combined flag that exists precisely for "no upgrades at
all". `HeftyTablet.cs:29` chooses `NoUpgradeRoll` alone and *not* the combined
one, so hook upgrades are deliberately in scope. `CardFactory.cs:104-107`
suppresses `Hook.TryModifyCardRewardOptions` only on `NoModifyHooks`, which
Hefty Tablet does not set. `ToxicEgg.cs:21-32` bails only on `NoHookUpgrades`,
then calls `EggRelicHelper.UpgradeValidCards(cardRewards, CardType.Skill,
this)`. The gap is real on the C# side beyond argument. The `NoUpgrades = 6`
point is worth adding to the record: it turns "a different flag" into "the game
has a flag for exactly what the sim assumed, and Hefty Tablet pointedly does
not use it."

**Reachability, re-derived from scratch.** `run.add_relic` (`run.py:827-834`)
appends **then** calls `after_obtained` OK; `neows_bones.after_obtained`
shuffles `neow_relic_pool` and `add_relic`s two of it OK; `hefty_tablet` and
`large_capsule` are both in that pool (`events/neow.py:46`) OK;
`large_capsule.after_obtained` calls `run.obtain_relic_from_grab_bag()` twice
(`run.py:930-935`) OK.

**Observable, reproduced on my own probe** (seed 2, Toxic Egg co-held,
`RunState.select_cards` spied):

```
SIM  offer: [('brand','SKILL',0), ('fiend_fire','ATTACK',0), ('thrash','ATTACK',0)]
GAME offer: [('brand','SKILL',1), ('fiend_fire','ATTACK',0), ('thrash','ATTACK',0)]
```

Identical to the report's, arrived at independently. A Rare Skill offered
upgraded by the game and plain by the sim — conformance-visible.

**Census: CONFIRMED at exactly ten.** My own MRO-aware scan (comparing each
class's resolved method against `Relic.modify_card_reward_options{,_late}`)
returns precisely `fresnel_lens, frozen_egg, glitter, lasting_candy, lava_lamp,
molten_egg, silken_tress, silver_crucible, toxic_egg, wing_charm`, with
`lasting_candy` the only plain-pass one. I also ran the census the first pass
never did — over `ALL_POWERS` / `ALL_POTIONS` / `ALL_ENCHANTMENTS` /
`_CARD_CLASSES`: **zero** non-relic implementers. The ten are the whole
population.

**Blocked-fix shape: CORRECT, with one refinement.** `silken_tress.py:27-38`
really does port the `IsCardReward` gate (`options.has_flag(
CardCreationFlags.IS_CARD_REWARD)`), matching `SilkenTress.cs:53-56` /
`SilverCrucible.cs:104-107` — so the report is right that the fix must build
`CardCreationOptions` with `NO_UPGRADE_ROLL` and **without** `IS_CARD_REWARD`,
and right that `scroll_boxes.py:40-51` is the in-tree precedent for
constructing one. **Refinement for whoever takes the fix:** the three-pass
chain already exists as a helper — `rewards.create_reward_cards`
(`rewards.py:300`, chain at `:410-418`: plain pass, `_late` pass, then
`after_modify_card_reward_options` for the true-returners). Reuse it rather
than hand-rolling a fourth copy.

**One honest caveat the record should carry: the live path is rare.** My
end-to-end search — 60,000 seeds of `RunState + add_relic("neows_bones")` —
gives: both relics drawn 220, `large_capsule` before `hefty_tablet` 105, an
implementer actually co-held **3**, and a divergent offer **0** in that sample
(the last step needs the three-card Rare offer to contain a card of the
implementer's own type, roughly 1 in 3, which I witnessed separately on a
forced co-hold). Every link is witnessed, but the conjunction is on the order
of 1 in 20,000 Neow's-Bones picks before counting whether Neow's Bones is even
offered. LIVE is the correct label — it is reachable on today's content, not
unreachable — but file it as *live and rare* so it prioritises correctly
against genuinely frequent gaps.

## Item 2 — the dead-code reasoning. CONFIRMED.

`cmds.py:310` (`if target.is_dead: return 0`) precedes `cmds.py:312`
(`should_allow_hitting`); the line numbers now match the report exactly after
this wave's concurrent edits. The domination argument is complete, and the
report closed the one leg I had left loose: `AdaptablePower.do_revive` only
clears the flag, and its sole caller `TestSubject._respawn`
(`monsters/glory/test_subject.py:137` `do_revive()`, then `:139`/`:142`
`_revive(form_hp)`) restores HP afterwards — verified. So `is_reviving` implies
`is_dead` at all three implementers with no window in between.

The surviving argument (set-coincidence alone on the damage side) is true, and
the **asymmetry claim is right and is the valuable part**: `PowerCmd.apply` has
no `is_dead` guard because `Creature.CanReceivePowers` (`Creature.cs:308-322`)
deliberately omits it, so there the hook really is load-bearing — confirmed
twice by my own mutations (item 3). The two close notes now say different
things, correctly, and #2 quotes the retired text verbatim.

## Item 3 — three rewritten tests. CONFIRMED discriminating, by my own harness.

I did not reuse the lane's harness. Six independent in-memory mutations:

| test | mutation | base | mutated |
|---|---|---|---|
| `...backstops_bag_of_marbles...` | `can_receive_powers` -> always True | PASS | **FAIL** |
| `...backstops_bag_of_marbles...` | `should_allow_hitting` -> always True | PASS | **FAIL** |
| `...refuses_the_damage_relics_at_the_is_dead_guard` | `Creature.is_dead` -> always False | PASS | **FAIL** |
| `...g2_a_reward_options_relic_is_reachable...` | `LargeCapsule.after_obtained` -> no-op | PASS | **FAIL** |
| `...census_is_ten_relics_not_four_or_seven` | drop `lasting_candy`'s plain override | PASS | **FAIL** |
| `...vambrace_docstring_names_the_two_real_methods...` | restore the OLD buggy docstring | PASS | **FAIL** |

The one I flagged as confounded is fixed properly: `enemy_count=2` plus an
explicit `assert cs.is_ending is False` documenting *why*, and it now fails
under both neuterings. The former null damage test is re-aimed at the guard
that actually refuses and additionally asserts the dead-code fact itself. The
former vacuous reachability test is now a precondition pin that survives the
fix.

`py -m pytest test/test_r13_relic2.py test/test_r13_relic1.py -q` -> **34
passed**; re-run with the file order swapped -> **34 passed**.

## Item 4 — the three carried-over corrections. CONFIRMED.

* **`festive_popper` G1** (report §6.3): every clause verified false against
  the tree — `on_player_turn_started` is `Hook.AfterPlayerTurnStart` alone
  (`hooks.py:1201`), Imbued is on the real `after_auto_pre_play_phase_entered`
  (`enchantments.py:384`), `turn_structure/G8` reads `faithful`, and
  `hook_dispatch.json` has no G2/G3 in the worktree **or** at `HEAD`. The flip
  is in close proposal #3. G3's basis is re-grounded on `Hook.cs:30-45`
  ("combat teardown is deferred to the next safe point"), which is the correct
  and seam-independent citation — stronger than what I asked for.
* **`spiked_gauntlets`** (§6.4): re-attribution verified myself —
  `git show HEAD` carries `_PHASES`, the `_each` phase loop and
  `brilliant_scarf.modify_card_energy_cost_late` unchanged, and
  `hook_dispatch.json` had no G2/G3 at `HEAD`. The note now reads "STALE —
  closed before round 13". Verdict unchanged.
* **`vambrace`** (§6.5): the sentence is properly scoped, and the replacement
  is itself citation-checked — `Vambrace.cs`'s overrides are exactly
  `BeforeCombatStart` (:49), `ModifyBlockMultiplicative` (:57),
  `AfterModifyingBlockAmount` (:82), `AfterCardPlayed` (:98) and
  `AfterCombatEnd` (:116), and `AfterBlockGained` is real in both engines as
  stated. The `__init__` / `reset_for_combat` clause is fixed.
  `git diff HEAD -- sts2_rl/relics/vambrace.py` is still docstring-only
  (17 added / 3 removed, all inside the triple-quote).

## Item 5 — the `_check_win` write-up. **File-ready as it stands.**

Re-verified end to end: `CombatManager.cs:1046-1058` OK; `LoseCombat` :945-951
is only a mark OK; `ProcessPendingLoss` :956-965 fires no hook and does no
revive OK; `EndCombatInternal` :978-999 does the opposite
(`ReviveBeforeCombatEnd` -> `Player.cs:821-827` heals a dead player to 1, then
`AfterCombatEnd` / `AfterCombatVictory`) OK. The ten-relic table matches
`grep -rn "_check_win()" sts2_rl/` exactly, and I confirmed each trigger hook
by dispatching it. The one-line delegate fix is correct:
`_check_win_condition` opens with the `COMBAT_OVER` early return that subsumes
`not self.combat.is_over`, and its win arm reaches the same
`_end_combat_internal`.

**The third closure is the strongest, and it holds.** Executed myself with all
ten relics registered at once:

```
BEFORE the player dies:
   on_card_exhausted      -> ['CombatHistory','CharonsAshes','ForgottenSoul']
   on_player_turn_started -> ['FestivePopper','MercuryHourglass']
   on_card_played         -> ['CombatHistory','Kusarigama','LetterOpener','LostWisp']
   after_player_turn_end  -> ['Kusarigama','ParryingShield']
   on_player_turn_end     -> ['ScreamingFlagon','StoneCalendar']

AFTER (is_dead=True, is_active_for_hooks=False, pending_loss=True,
       phase=PLAYER_TURN, is_over=False, _all_enemies_dead()=True):
   on_card_exhausted      -> ['CombatHistory']      # every relic gone
   on_player_turn_started -> []
   on_card_played         -> ['CombatHistory']
   after_player_turn_end  -> []
   on_player_turn_end     -> []
   ...and a DIRECT _check_win() on that same state -> player_won=True, hp 1
```

The gate is `Relic.hook_contains` -> `player.is_active_for_hooks`
(`relics/base.py:224-239`), the faithful port of `CombatState.cs:597`, and the
flag is dropped in `_resolve_death` (`cmds.py:206` = `Player.DeactivateHooks`,
`Player.cs:857-860`, whose own doc-comment says it fires when the player
reaches zero health, after the death-prevention hooks). I closed the one hole
the write-up leaves implicit: **every** HP-loss path reaches that deactivation
— `cmds.py:401-402` calls `_resolve_death` unconditionally on `target.hp <= 0`
immediately after the only decrementing write (`:382`), and the sole explicit
`lose_combat()` caller is `combat.py:843`, under `player.is_dead`. So there is
no reachable state with a pending loss and a live relic listener. That closure
is general — all ten relics, all five trigger hooks, one argument — where mine
covered two specific paths. It deserves to lead the liveness section, and does.

Act on the write-up's own last paragraph too: the ten relic records' `faithful`
N-guards on `_check_win` should be pointed at the new guard, since they are
true of the win arm and false of the loss arm.

## Item 6 — suite gate

Noted, no action. The `staticmethod`-descriptor restore bug is a good catch and
a generalisable one: `test_r13_relic2.py`'s own `DamageCmd.deal` spy in
`test_paper_phrog_n2...` restores with `staticmethod(original_deal)`, which is
why it never had the defect. Worth a line in PROMPT.md.

## Advisories (non-blocking, do not hold the merge)

1. **Line-drift in a committed docstring.** `vambrace.py` cites
   `hooks.py:138/:1712`; the dispatcher is now at `hooks.py:1719` and the
   implementer at `powers.py:1108` (concurrent lanes moved them after the
   report was written). `:138` is still exact. Production docstrings outlive
   line numbers — prefer a symbol anchor (`HookSystem.on_block_gained`) for the
   sim side and keep line numbers for the C# side, which is frozen.
2. Add `CardCreationFlags.NoUpgrades = 6` to the `hefty_tablet` G2 close note.
3. Add `rewards.create_reward_cards` to the blocked-fix shape.
4. State the live-path rarity in the `hefty_tablet` queue annotation.
