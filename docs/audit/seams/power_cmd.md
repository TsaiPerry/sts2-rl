# Engine seam: `power_cmd`

Audited 2026-07-25 (Task 6 of the six seam audits, Tier 2 of the
source-audit-pipeline design). Verdicts and rationale live in
`audits/seam/power_cmd.json`; this file is the durable ordering spec
extracted from the C# source that the JSON record judges the sim against.

This is the seam the whole project exists because of: the Unsettling Lamp
relic doubled a debuff that Artifact should have negated, because
`modify_power_amount` ran on the wrong side of Artifact's early-return in
`PowerCmd.apply`. That fix has landed (`sts2_rl/cmds.py:287-297`, with an
ordering comment). This audit checks the rest of the seam for siblings of
that bug.

## Source correction (Step A)

`tools/audit/harness.py`'s `SEAM_SOURCES["power_cmd"]` originally listed only
`src/Core/Commands/PowerCmd.cs`. That file is real and is the orchestration
layer (`Apply`/`ModifyAmount`/`Remove`/`FindExistingInstanceForStacking`), but
it delegates all of its actual modifier/event dispatch to static methods on
`Hook` (`ModifyPowerAmountGiven`, `ModifyPowerAmountReceived`,
`BeforePowerAmountChanged`, `AfterPowerAmountChanged`,
`AfterModifyingPowerAmountGiven`, `AfterModifyingPowerAmountReceived` —
`src/Core/Hooks/Hook.cs`), and the sign-aware typing / stacking-removal /
zero-amount-is-a-no-op rules it depends on live on `PowerModel`
(`src/Core/Models/PowerModel.cs`: `GetTypeForAmount`,
`ShouldRemoveDueToAmount`, `ApplyInternal`, `InstanceType`). The table was
corrected to hash all three files; the sim side was correspondingly widened
to `sts2_rl/cmds.py` + `sts2_rl/hooks.py` + `sts2_rl/powers.py` (the
`Power` base class and `PowerType`/`allow_negative` live in `powers.py`,
and `hooks.py`'s `modify_power_amount`/`after_modify_hp_lost`-style
machinery is the sim's `Hook.*` counterpart).

### Scope boundary with `damage_pipeline` (Task 5) and `hook_dispatch` (Task 8)

`Hook.cs` is now listed under three seams. This record only judges the
power-amount-specific dispatcher methods: `BeforePowerAmountChanged`
(`Hook.cs:1006-1016`), `AfterPowerAmountChanged` (`Hook.cs:1018-1026`),
`ModifyPowerAmountGiven` (`Hook.cs:1884-1912`), `ModifyPowerAmountReceived`
(`Hook.cs:1914-1931`), `AfterModifyingPowerAmountGiven` (`Hook.cs:796-809`),
`AfterModifyingPowerAmountReceived` (`Hook.cs:811-824`). It does not
re-audit the damage-modifier methods (`ModifyDamage`, `ModifyHpLost`,
`ShouldDie`, ...) that `damage_pipeline` already owns, nor does it judge
`Hook.cs`'s generic listener-iteration machinery (`IterateCombatHookListeners`
itself), which belongs to `hook_dispatch` (Task 8). If Task 8 finds a
power-amount-dispatch behavior this record missed, it belongs here as an
amendment, not a second verdict under a different unit id.

## Sim entry point

`sts2_rl.cmds.PowerCmd.apply(hooks, target, power_cls, amount, applier=None)`
(`sts2_rl/cmds.py:270-332`) — note the sim's signature has **no `card`/
`cardSource` parameter at all**, unlike every C# entry point below. Powers
that need to know "was this the triggering card" (Unsettling Lamp) instead
bracket the in-flight card via `before_card_played`/`on_card_played` hooks
registered independently of the power pipeline (`sts2_rl/relics/
unsettling_lamp.py`). See guard **G3**.

## Numbered ordering spec

### `PowerCmd.Apply<T>` (single target) — `PowerCmd.cs:67-89`

1. Guard: `CombatManager.Instance.IsEnding` → return `null`. `PowerCmd.cs:69-72`.
2. Guard: `!target.CanReceivePowers` → return `null`.  `CanReceivePowers`
   is `CombatState != null && Hook.ShouldAllowHitting(...)` —  the *same*
   predicate the damage pipeline uses to skip reviving/unhittable creatures
   (cross-reference `damage_pipeline`'s guard N1). `PowerCmd.cs:73-76`;
   `Creature.cs:308-322`. See guard **G6**.
3. `FindExistingInstanceForStacking(powerModel, target, applier)` — dispatches
   on `power.InstanceType`: `Instanced` → always `null` (every application is
   a brand-new, independently-tracked instance); `InstancedPerApplier` →
   match an existing instance with the same `Applier`; `None` (the default)
   → match by power id only, ignoring applier. `PowerCmd.cs:77-78, 165-174`;
   `PowerModel.cs:144`. See guard **G5**.
4. Branch: no existing instance → `power = powerModel.ToMutable()`, then run
   the "new power" `Apply(power, target, amount, applier, cardSource,
   silent)` overload (steps 6-23). An existing instance → run
   `ModifyAmount(power, amount, applier, cardSource, silent)` (steps 24-37);
   if it returns exactly `0`, the caller-visible `power` is nulled out.
   `PowerCmd.cs:79-87`.
5. Return `power as T`. `PowerCmd.cs:88`.

### `PowerCmd.Apply(power, target, amount, applier, cardSource, silent)` — "new power" pipeline, `PowerCmd.cs:101-159`

6. Guard: `CombatManager.Instance.IsEnding || amount == 0m ||
   !target.CanReceivePowers` → return. `PowerCmd.cs:103-106`.
7. Guard: `combatState == null` → return. `PowerCmd.cs:107-111`.
8. Re-check `FindExistingInstanceForStacking(power, target, applier)`; if
   found this time, delegate entirely to `ModifyAmount(...)` and return. A
   defensive re-check for direct callers of this overload (not reachable
   from `Apply<T>`, which already checked). `PowerCmd.cs:112-117`.
9. `power.AssertMutable(); power.Applier = applier`. `PowerCmd.cs:118-119`.
10. Event: `Hook.BeforePowerAmountChanged(combatState, power, amount,
    target, applier, cardSource)` — fires with the **raw, unmodified**
    `amount`. This is where `UnsettlingLamp.BeforePowerAmountChanged`
    latches its `TriggeringCard` (only if `cardSource != null`, `applier ==
    <Lamp owner>`, `target.Side != <Lamp owner>.Side`, `power.IsVisible`,
    and `power.GetTypeForAmount(amount) == Debuff`).
    `PowerCmd.cs:120`; `Hook.cs:1006-1016`; `UnsettlingLamp.cs:71-104`.
11. `modifiedAmount = amount`. `PowerCmd.cs:121`.
12. Guard: `if (applier != null && combatState.ContainsCreature(applier))`
    → `modifiedAmount = Hook.ModifyPowerAmountGiven(...)` — an
    additive-sum-then-multiplicative-product chain over every combat hook
    listener, collecting the listeners that actually changed the value into
    `givenModifiers`. This is where `UnsettlingLamp.
    ModifyPowerAmountGivenMultiplicative` doubles a debuff.
    `PowerCmd.cs:122-126`; `Hook.cs:1884-1912`; `UnsettlingLamp.cs:106-129`.
13. `modifiedAmount = Hook.ModifyPowerAmountReceived(combatState, power,
    target, modifiedAmount, applier, out receivedModifiers)` — a
    first-listener-wins-per-hit-but-loop-continues predicate chain
    (`TryModifyPowerAmountReceived`), **unconditional** (no applier-null
    guard, unlike step 12). Evaluated against the **already Lamp-doubled**
    amount. This is where `ArtifactPower.TryModifyPowerAmountReceived` and
    `RuinedHelmet.TryModifyPowerAmountReceived` intercept.
    `PowerCmd.cs:127`; `Hook.cs:1914-1931`; `ArtifactPower.cs:17-36`;
    `RuinedHelmet.cs:32-53`. **This is the exact ordering the Unsettling
    Lamp fix pins — step 12 (given/Lamp) strictly precedes step 13
    (received/Artifact).**
14. Guard: multiplayer scaling — waiver, multiplayer-only. `PowerCmd.cs:128-131`.
15. Event: `await power.BeforeApplied(target, modifiedAmount, applier,
    cardSource)` — **unconditional**, fires even when `modifiedAmount == 0`
    (a fully Artifact-blocked debuff). This is where
    `TemporaryStrengthPower`/`TemporaryDexterityPower` (Mangle, etc.)
    recursively apply their internal `StrengthPower`/`DexterityPower` via a
    **full separate `PowerCmd.Apply<T>` call**, carrying the *same*
    `applier`/`cardSource` — the call that `UnsettlingLamp.
    HasDoubledTemporaryPowerSource` exists to keep from being doubled twice.
    `PowerCmd.cs:132`; `TemporaryStrengthPower.cs:146-156`.
16. Guard: `target.CanReceivePowers` (re-checked). `PowerCmd.cs:133`.
17. `power.ApplyInternal(target, modifiedAmount, silent)` — **a complete
    no-op if `modifiedAmount == 0m`**: `Owner` is never set, the power is
    never registered on the target at all. Otherwise sets `Owner`,
    `SetAmount`, and registers via `Owner.ApplyPowerInternal`.
    `PowerCmd.cs:135`; `PowerModel.cs:564-573`.
18. Guard: `if (modifiedAmount != 0m) History.PowerReceived(...)` — waiver,
    telemetry. `PowerCmd.cs:136-139`.
19. Guard: `if (power.IsVisible && IsInProgress)` wait — waiver,
    presentation. `PowerCmd.cs:140-142`.
20. Guard: `if (target.Side == Player && power.Type == Debuff)
    power.SkipNextDurationTick = true` — **unconditional** on
    `modifiedAmount`; fires even on the discarded, unregistered power
    instance produced by a fully Artifact-blocked debuff.
    `PowerCmd.cs:144-147`.
21. Guard: `if (givenModifiers != null) await
    Hook.AfterModifyingPowerAmountGiven(combatState, givenModifiers,
    power)` — notifies only the listeners that changed the *given*-side
    amount. `PowerCmd.cs:148-150`; `Hook.cs:796-809`.
22. `await Hook.AfterModifyingPowerAmountReceived(combatState,
    receivedModifiers, power)` — notifies only listeners that changed the
    *received*-side amount. This is where `ArtifactPower.
    AfterModifyingPowerAmountReceived` calls `PowerCmd.Decrement(this)` —
    **the actual mechanism by which Artifact consumes its own stack** — and
    `RuinedHelmet.AfterModifyingPowerAmountReceived` sets `UsedThisCombat =
    true`. `PowerCmd.cs:152`; `Hook.cs:811-824`; `ArtifactPower.cs:38-41`;
    `RuinedHelmet.cs:55-60`.
23. Guard: `if (modifiedAmount != 0m) { await power.AfterApplied(...); await
    Hook.AfterPowerAmountChanged(...); }`. `PowerCmd.cs:153-157`;
    `Hook.cs:1018-1026`.

### `PowerCmd.ModifyAmount(power, offset, applier, cardSource, silent)` — "existing power" stacking pipeline, `PowerCmd.cs:215-271`

24. Guard: `CombatManager.Instance.IsEnding` → return `0`. `PowerCmd.cs:217-220`.
25. Guard: `combatState == null` → return `0`. **No `CanReceivePowers` check
    at all in this path** (C# itself lacks it here — this is a faithful
    absence, not a divergence; see the sim-comparison note below).
    `PowerCmd.cs:221-226`.
26. Event: `Hook.BeforePowerAmountChanged(combatState, power, offset, owner,
    applier, cardSource)`. `PowerCmd.cs:227`.
27. Guard: `if (applier != null && combatState.ContainsCreature(applier))`
    → `modifiedOffset = Hook.ModifyPowerAmountGiven(...)`. `PowerCmd.cs:228-233`.
28. `modifiedOffset = Hook.ModifyPowerAmountReceived(...)` — unconditional,
    same mechanism as step 13 (so Artifact/RuinedHelmet also intercept
    *re-stacking* an existing power, not just first application).
    `PowerCmd.cs:234`.
29. `History.PowerReceived(...)` — **unconditional here**, unlike step 18's
    `if (modifiedAmount != 0m)` gate. Waiver, telemetry. `PowerCmd.cs:235`.
30. `newAmount = power.Amount + (int)modifiedOffset; power.SetAmount(newAmount,
    silent)`. `PowerCmd.cs:236-237`.
31. Guard: `if (modifiers != null)
    AfterModifyingPowerAmountGiven(...)`. `PowerCmd.cs:238-241`.
32. `AfterModifyingPowerAmountReceived(...)` — same Artifact-`Decrement`/
    RuinedHelmet mechanism as step 22. `PowerCmd.cs:242`.
33. Guard: `if ((int)modifiedOffset != 0)
    AfterPowerAmountChanged(...)`. **No `BeforeApplied`/`AfterApplied` at
    all in this path** — those only fire for brand-new powers (step 15/23).
    `PowerCmd.cs:243-246`.
34. Guard: `if (power.ShouldRemoveDueToAmount()) await Remove(power)`. Sign
    logic: `AllowNegative` powers are removed only at exactly `Amount == 0`
    (and may sit negative indefinitely otherwise); non-`AllowNegative`
    powers are removed at `Amount <= 0`. `PowerCmd.cs:247-250`;
    `PowerModel.cs:478-489`.
35. Guard: monster-intent UI update — waiver, presentation. `PowerCmd.cs:251-265`.
36. Guard: `if (power.IsVisible && IsInProgress)` wait — waiver,
    presentation. `PowerCmd.cs:266-269`.
37. `return newAmount`. `PowerCmd.cs:270`.

### `PowerCmd.Remove(power)` — `PowerCmd.cs:287-295`

38. Guard: `power != null`. `PowerCmd.cs:289`.
39. `power.RemoveInternal()` — fires the `Removed` event,
    `Owner.RemovePowerInternal(this)`. `PowerCmd.cs:291`; `PowerModel.cs:575-580`.
40. Wait 0.2-0.4s — waiver, presentation. `PowerCmd.cs:292`.
41. `power.AfterRemoved(power.Owner)`. `PowerCmd.cs:293`.

### Supporting definitions cited above

- `GetTypeForAmount` — sign-aware power typing. `PowerModel.cs:460-471`:
  `if (StackType == Counter && AllowNegative && amount < 0) return Debuff;`
  `if (!AllowNegative && Type == Debuff && amount < 0) return Buff;`
  `return Type;` — e.g. `StrengthPower`/`DexterityPower` (`Type = Buff`,
  `AllowNegative = true`, `StackType = Counter`) applied with a **negative**
  amount is classified `Debuff` for both Artifact-interception and Lamp's
  own doubling gate, regardless of the power's static `Type`.
- `ShouldRemoveDueToAmount` — `PowerModel.cs:478-489` (see step 34).
- `ApplyInternal` 0-amount no-op — `PowerModel.cs:564-573` (see step 17).
- `PowerInstanceType` — `PowerCmd.cs:165-174` (see step 3, guard **G5**).

## Sim comparison (Step C summary — full verdicts in the JSON)

The sim's `PowerCmd.apply` (`sts2_rl/cmds.py:270-332`) collapses the whole
spec above into one linear function: `hooks.modify_power_amount(...)`
(collapsing steps 10-13's `BeforePowerAmountChanged` +
`ModifyPowerAmountGiven` + `ModifyPowerAmountReceived` into one chained
call — steps 10-13 ↔ `cmds.py:297`), then a hand-written, special-cased
Artifact block (steps 13/22 ↔ `cmds.py:299-306`) sitting *outside* the hook
system entirely, then the stacking-vs-new branch (step 3/4 ↔
`cmds.py:308-326`), then the player-side `SkipNextDurationTick` guard (step
20 ↔ `cmds.py:331-332`). There is no sim counterpart at all for
`ModifyAmount`'s separate pipeline (steps 24-37) — `PowerCmd.apply`'s single
code path serves both "new power" and "stack onto existing power," which
happens to reach the same steady-state result for currently-ported content
since C#'s two pipelines share the same three hook calls in the same order.

**Seed facts, verified:**

1. **`modify_power_amount` runs BEFORE the Artifact early-return in
   `PowerCmd.apply`.** Confirmed: C#'s `Hook.ModifyPowerAmountGiven`
   (`PowerCmd.cs:125`, Lamp's doubling) strictly precedes
   `Hook.ModifyPowerAmountReceived` (`PowerCmd.cs:127`, Artifact's veto) —
   spec steps 12 then 13. The sim's `cmds.py:297` call precedes the Artifact
   block at `cmds.py:299-306`, matching. Pinned by the existing
   `test_activation_spent_even_when_artifact_negates_debuff`
   (`test/test_relics.py:1163`).
2. **Debuffs intercepted by Artifact; buffs never.** Confirmed at the
   type level: `ArtifactPower.TryModifyPowerAmountReceived`
   (`ArtifactPower.cs:24`) bails unless `GetTypeForAmount(amount) ==
   Debuff`. Faithful in spirit, but see **G1** — the sign-aware half of
   "debuff" is missing from the sim's check.
3. **Power typing is sign-aware in C# (`GetTypeForAmount(amount)`) —
   negative Dexterity is a Debuff.** Confirmed; definition at
   `PowerModel.cs:460-471`, consumed at `UnsettlingLamp.cs:97,124` and
   `ArtifactPower.cs:24`. **The sim has no equivalent method at all** (grep
   confirms zero hits for `get_type_for_amount`/`GetTypeForAmount` anywhere
   under `sts2_rl/`) — see **G1**, **G2**.
4. **Power visibility (`power.IsVisible`) gates some listeners.** Confirmed
   at `UnsettlingLamp.cs:93` (Lamp's own latch) and `ArtifactPower.cs:29-33`
   (Artifact's own intercept). **Downgraded from the brief's framing**: a
   full-codebase grep for `IsVisibleInternal` overrides across
   `src/Core/Models/Powers/*.cs` returns zero matches — no power in the
   entire game (not just Ironclad-scope) currently makes `IsVisible` return
   anything but `true`. The sim's total omission of the concept is
   therefore a `waiver`, not a `gap` — see the JSON guard entry.

**`AfterModifyingPowerAmountGiven`/`AfterModifyingPowerAmountReceived`**
(the two `Hook.cs` variants the brief specifically flagged, out of the 13
Task 5's damage-pipeline audit found only one of): **both are entirely
absent from the sim.** `hooks.py`'s `modify_power_amount` (`hooks.py:170-183`)
returns a bare aggregated `int` with no out-param modifiers list at all —
unlike its sibling `modify_hp_lost`/`after_modify_hp_lost` pair
(`hooks.py:126-154`), which Task 5's re-audit found *does* now carry this
machinery. `RuinedHelmet` and `UnsettlingLamp` both hand-roll their "I
actually fired" side effect (`_used = True` / `TriggeringCard = card`)
**inside** the single `modify_power_amount` call itself instead of via a
proper two-phase try/after split — see **G4**.

**Gaps found** (full detail in the JSON `guards` entries; short form here):

- **G1 — Sign-aware power typing missing from Artifact interception, LIVE
  today.** `PowerCmd.apply`'s Artifact check (`cmds.py:299`) tests the
  static `power_cls.power_type == PowerType.DEBUFF` class attribute instead
  of C#'s sign-aware `GetTypeForAmount(amount)`. Concretely reachable
  *right now*: `the_lost_and_forgotten.py:54,99` (Glory/Act-3) and
  `lagavulin_matriarch.py:106-107` (Underdocks/Act-1) both apply **negative**
  `StrengthPower`/`DexterityPower` to the player as a Strength/Dexterity
  steal — a Buff-typed, `allow_negative = True` power applied with a
  negative amount, which C# classifies `Debuff` (`GetTypeForAmount`,
  `StackType == Counter && AllowNegative && amount < 0`). If the player
  holds Artifact, C# blocks the steal and consumes a stack; the sim's
  static check sees `power_type == BUFF` and skips the Artifact branch
  entirely, so **the steal always lands even with Artifact active.**
  Pinned with an `xfail` in `test/test_hook_order.py`.
- **G2 — Same sign-aware gap in Unsettling Lamp's own doubling condition,
  plus an `amount <= 0` early bail; dormant.**
  `unsettling_lamp.py:44-53`'s `modify_power_amount` bails immediately on
  `amount <= 0` and then checks the static `power_cls.power_type !=
  PowerType.DEBUFF`, vs. C#'s `power.GetTypeForAmount(amount) !=
  PowerType.Debuff` (`UnsettlingLamp.cs:124`), which can be `Debuff` for a
  *negative* amount on an `AllowNegative` buff. C#'s `Malaise.cs:40` and
  `Resonance.cs:33` both apply negative `StrengthPower` to an enemy
  (`applier = player`, `cardSource = this`) — exactly the shape Lamp is
  supposed to double. Neither card is ported in the sim yet, so this is
  dormant, but it would misfire (fail to double) the instant either is
  ported.
- **G3 — C#'s three ordered phases collapsed into one registration-order
  chain; Artifact bypasses the hook system entirely.** C# separates
  `BeforePowerAmountChanged` (event) → `ModifyPowerAmountGiven` (additive/
  multiplicative chain) → `ModifyPowerAmountReceived` (predicate chain) into
  three distinct calls with a fixed given-before-received order enforced by
  the call sequence itself. The sim merges all three into one
  `hooks.modify_power_amount` loop (`hooks.py:170-183`) whose only ordering
  guarantee is hook-*registration* order, and additionally special-cases
  Artifact as a direct `cmds.py:299-306` block entirely outside that loop
  (Artifact is not a `modify_power_amount` listener at all — see its own
  docstring, `sts2_rl/powers.py:315-325`). The current two general
  `modify_power_amount` listeners — Lamp (given-side, debuff-only) and
  RuinedHelmet (received-side, `StrengthPower`-buff-only, `ruined_helmet.py:
  23-39`) — happen to be domain-disjoint, so no live collision is
  demonstrated, but nothing in the sim's architecture would enforce correct
  given-before-received ordering for two future listeners that *do*
  overlap, the way C#'s fixed call sequence does today.
- **G4 — No `AfterModifyingPowerAmountGiven`/`AfterModifyingPowerAmountReceived`
  machinery at all.** See the seed-fact section above for detail. This is
  not merely a bookkeeping gap: `ArtifactPower.AfterModifyingPowerAmountReceived`
  is the method that actually calls `PowerCmd.Decrement(this)` in C# — the
  sim reimplements the *effect* (decrementing Artifact) inline in
  `cmds.py:301-305` rather than via the hook, which is faithful for
  Artifact specifically (single hard-coded listener) but means a *second*
  power wanting the same "only react on the hit(s) where I actually changed
  something" pattern for power-amount modification (as opposed to HP-loss,
  which `hooks.py:149-154` already supports) has no mechanism to hook into.
- **G5 — No `PowerInstanceType` distinction in `FindExistingInstanceForStacking`.**
  The sim's stacking check (`cmds.py:308`, `if power_cls.id in
  target.powers`) always behaves as C#'s `PowerInstanceType.None` (single
  shared instance per power id per owner). C# also has `Instanced` (every
  application creates an independently-tracked instance) and
  `InstancedPerApplier` (instances keyed by applier). Ten C# powers declare
  `Instanced`/`InstancedPerApplier`; **nine are ported in the sim**:
  `ToricToughnessPower` and `TheBombPower` explicitly document the
  approximation and hand-roll a workaround (bundling multiple logical
  "instances" inside one power's internal list/fuses — see their own
  docstrings, `powers.py:1191-1200`, `powers.py:3748-3753`). The other seven
  — `SwipePower`, `StranglePower` (`InstancedPerApplier`),
  `AutomationPower`, `HeistPower`, `PanachePower`, `RollingBoulderPower`,
  `SandpitPower`, `ThieveryPower`, `WitheringPresencePower` — do not
  acknowledge the distinction at all. No currently-demonstrated collision
  (only one copy of each is realistically active on a given owner in
  present content), but a second simultaneous instance on the same owner
  (e.g. two Thieving Hoppers' `Swipe`, or `Strangle` applied by two
  different appliers to the same target) would silently merge via
  `on_stack` in the sim where C# tracks them independently.
- **G6 — No `CombatManager.IsEnding`/`CanReceivePowers` guard backstop in
  `PowerCmd.apply`.** Structural absence, mirroring `damage_pipeline`'s G5:
  C#'s `Apply<T>` refuses to do anything at all once combat is ending (step
  1) or against a creature `CanReceivePowers` says no to (step 2 — which
  reuses `Hook.ShouldAllowHitting`, the *same* predicate
  `damage_pipeline`'s guard N1 covers for the damage path). The sim's
  `PowerCmd.apply` has neither guard. `should_allow_hitting` **is** wired
  into the sim's damage pipeline (`DamageCmd.deal`) but not into
  `PowerCmd.apply` — so a currently-unhittable creature (e.g. a mid-revival
  Decimillipede segment) could still receive a power application in the sim
  where C# would refuse it outright. No concrete broken interaction is
  demonstrated (spot-checked callers apply powers only to already-resolved
  targets), but, as with `damage_pipeline`'s G5, the pipeline itself
  provides no defense-in-depth the way `CanReceivePowers` does.

**Lower-severity / no-current-effect notes** (`deliberate-divergence` or
`waiver`, full rationale in the JSON): **N1** `IsVisible` is entirely absent
from the sim's `Power` model — `waiver`, since grep confirms it is
provably always `true` everywhere in the current C# codebase (see seed fact
4 above). **N2** `TemporaryStrengthPower`/`TemporaryDexterityPower`'s
internal wrapped-power application omits `applier` in the sim
(`powers.py:863,937` call `PowerCmd.apply(..., self._sign * amount)` with no
`applier=` kwarg) instead of replicating C#'s explicit
`HasDoubledTemporaryPowerSource` double-dip guard — verified to produce the
*same* net outcome for the currently-ported Mangle-family content (Lamp's
`applier is not self.player` gate on the internal, applier-less call
achieves the same "don't double twice" result as C#'s explicit check, by a
different mechanism) — `deliberate-divergence`. **N3** Artifact's
owner-scoping (`target != base.Owner` in C#, a hook-iteration self-filter)
vs. the sim's direct `target.powers.get("artifact")` lookup (a special
case) — architecturally different, semantically identical — `faithful`.
**N4** `ModifyAmount`'s missing `CanReceivePowers` check (step 25) is a
*faithful absence*: C# itself doesn't check it there either.

## Existing test coverage (Step D)

- **`modify_power_amount` before Artifact veto** (pin table item 1):
  `test/test_relics.py::TestUnsettlingLamp::
  test_activation_spent_even_when_artifact_negates_debuff` already covers
  this exactly, through the real card-play path (Bash's Vulnerable fully
  eaten by Artifact, Lamp's activation still spent, next debuff not
  doubled) — this is the actual historical 933T Mecha Knight regression
  reproduction. Recorded, not duplicated.
- **Artifact consumes exactly one stack per debuff** (pin table item 2):
  `test/test_powers.py::TestArtifact::test_blocks_one_debuff_per_stack` and
  `test_stacks_and_each_stack_blocks_one_debuff`. Recorded, not duplicated.
- **G1 (sign-aware Artifact interception, live gap)**: new `xfail` pin
  added: `test/test_hook_order.py::TestPowerCmdOrder::
  test_artifact_blocks_negative_signed_debuff` — applies a negative-amount
  `DexterityPower` (mirroring the Lost and Forgotten / Lagavulin Matriarch
  steal shape) to an Artifact-holding target and asserts the steal is fully
  blocked and Artifact is consumed; asserts the C#-correct behavior, marked
  `xfail` referencing G1.
- **Ordering trace** (new, not a pin-table item but demonstrates step
  12-before-13 directly at the `PowerCmd.apply` level rather than through a
  card play): `test/test_hook_order.py::TestPowerCmdOrder::
  test_modify_power_amount_runs_before_artifact_block` traces
  `modify_power_amount` and confirms it fires, then confirms the debuff is
  blocked and Artifact consumed, using a direct `PowerCmd.apply` call per
  the brief's suggested shape.
