# SpireBot damage-preview research: `damage_matrix` obs segment

**Verdict: KEEP**

The game computes the exact same fully-modified per-(card, target) damage
number that the card face displays, via a small set of plain model methods
that mod code can call directly — no UI node, no card hover, no player
input. This mirrors `sts2_rl/previews.py`'s `preview_card_damage` /
`_modified_damage` closely enough that `damage_matrix` can be treated as
"the game's own number," not a sim-only feature the mod would have to
reimplement.

## What was searched

- `c:\Users\Perry\Desktop\BaseLib-StS2\Notes.txt` — the reverse-engineering
  notes explicitly document a `DamageVar` with `BaseValue` /
  `EnchantedValue` / `PreviewValue`, and name `CardModel.UpdateDynamicVarPreview`
  as the method that fills in `PreviewValue` from hooks.
- `BaseLib-StS2\Extensions\AttackCommandExtensions.cs` — confirms the
  `AttackCommand` / `ValueProp` naming used by the live combat pipeline
  (`DamageProps` on `AttackCommand`), which lines up with `ValueProp` used
  by the preview vars.
- Decompiled source under `c:\Users\Perry\Desktop\Slay the Spire 2\src`:
  - `Core/Localization/DynamicVars/DynamicVar.cs` — base class; documents
    `PreviewValue` as "the value that should be displayed to the player…
    Do NOT use this value for performing calculations that will modify the
    game's state. It's for display only" — i.e. it's the display pipeline,
    computed the same way as the real one, but read-only/side-effect-free.
  - `Core/Localization/DynamicVars/DamageVar.cs` — `UpdateCardPreview`
    folds in enchantment additive/multiplicative, then calls the static
    `Hook.ModifyDamage(...)` with `ModifyDamageHookType.All` and stores the
    result in `PreviewValue`.
  - `Core/Localization/DynamicVars/CalculatedDamageVar.cs` — same pattern
    for calc-based cards (Body Slam, Perfected Strike): computes the base
    via `Calculate(target)` (card's own dynamic-base formula) then runs it
    through the same `Hook.ModifyDamage`.
  - `Core/Localization/DynamicVars/RepeatVar.cs` — multi-hit cards (Twin
    Strike, Pummel) store hit count as a separate, unmodified
    `DynamicVar("Repeat", times)` — no hook pass, matches
    `previews.py`'s `card.hits` treatment (static hit count × per-hit
    modified damage).
  - `Core/Localization/DynamicVars/DynamicVarSet.cs` — typed accessors
    `.Damage`, `.CalculatedDamage`, `.Block`, `.Repeat`, etc., keyed by
    var name on a `Dictionary<string, DynamicVar>`. Publicly readable.
  - `Core/Models/CardModel.cs`:
    - `public DynamicVarSet DynamicVars` (line 537) — public property,
      lazily built, on every `CardModel` instance (hand cards included).
    - `public void UpdateDynamicVarPreview(CardPreviewMode previewMode, Creature? target, DynamicVarSet dynamicVarSet)`
      (line 1451) — public instance method. Gate: `runGlobalHooks` is true
      whenever the card's `Pile.Type` is `Hand` or `Play` (or
      `UpgradePreviewType == Combat`) and `CombatState != null` — i.e. it's
      true for exactly the cards a bot would want to query (cards
      currently in hand during a live combat). No UI node is touched; it
      just loops `dynamicVarSet.Values` calling `DynamicVar.UpdateCardPreview`.
  - `Core/Hooks/Hook.cs`:
    - `public static decimal ModifyDamage(IRunState runState, ICombatState? combatState, Creature? target, Creature? dealer, decimal damage, ValueProp props, CardModel? cardSource, ModifyDamageHookType modifyDamageHookType, CardPreviewMode previewMode, out IEnumerable<AbstractModel> modifiers)`
      (line 1486) — public static, callable with a concrete non-null
      `target` Creature. When `target != null`, it skips the
      `MultiCreatureTargeting` aggregation branch entirely and calls
      `ModifyDamageInternal` once for that one target (line ~2511),
      running the additive → multiplicative → cap hook passes over
      `runState.IterateHookListeners(combatState)` — the same
      strength/vulnerable/relic/artifact hook machinery the real
      `DamageCmd`-equivalent live-combat resolution uses (this is the same
      `Hook.ModifyDamage` the intent-damage and actual `AttackCommand`
      resolution paths route through). This is exactly the
      additive/multiplicative/cap sequence `sts2_rl/previews.py._modified_damage`
      mirrors from `DamageCmd.deal`.
  - `Core/Entities/Cards/CardPreviewMode.cs` — `None` / `Normal` / `Upgrade`
    / `MultiCreatureTargeting`. `Normal` with an explicit non-null `target`
    is the correct mode for a per-(card, single-enemy) query — it's *more*
    precise than what the UI shows for AoE cards, which collapses to one
    number only when every enemy would take equal damage
    (`MultiCreatureTargeting`, `target == null`); per-target queries never
    need that collapse.
- `c:\Users\Perry\Desktop\RunReplays\RunReplays\GameStateSnapshot.cs` —
  confirms mod code already has non-UI handles to the exact objects this
  call sequence needs: `CombatManager.Instance.DebugOnlyGetState()` for
  the live `CombatState`/enemies, and `player.PlayerCombatState.Hand.Cards`
  (`CardModel` instances) for the hand. No screen/node interaction
  required anywhere in this snapshot code, which is the same style of
  access the damage-preview call would use.
- `sts2_rl/previews.py` — read for apples-to-apples comparison. Its
  `_modified_damage` (additive → multiplicative → cap, `max(0, amount)`)
  and `preview_card_damage` (base damage → props → modified) map 1:1 onto
  `DamageVar.UpdateCardPreview` / `CalculatedDamageVar.UpdateCardPreview` →
  `Hook.ModifyDamage`'s additive/multiplicative/cap passes.

## Call sequence (KEEP)

```csharp
var combat = CombatManager.Instance.DebugOnlyGetState();     // ICombatState, no UI
CardModel card = combat.Player.PlayerCombatState.Hand.Cards[i]; // must be in Hand pile
Creature target = combat.Enemies[j];                          // single enemy, non-null
card.UpdateDynamicVarPreview(CardPreviewMode.Normal, target, card.DynamicVars);
decimal perHitDamage = card.DynamicVars.ContainsKey("CalculatedDamage")
    ? card.DynamicVars.CalculatedDamage.PreviewValue   // calc-based cards (Body Slam, Perfected Strike)
    : card.DynamicVars.Damage.PreviewValue;            // fixed-base attacks
```

Preconditions:
- `card` must currently be in the `Hand` (or `Play`) pile of a live
  `CombatState` — true for exactly the cards a bot is choosing among; no
  hover/drag/mouse-over state is read anywhere in this path.
- No card is required to be "selected" or targeted through the UI; `target`
  is passed directly as a `Creature` reference pulled from
  `CombatState.Enemies`.
- For multi-hit cards, multiply by `card.DynamicVars.Repeat.BaseValue`
  (present only on cards with a `RepeatVar`; check `ContainsKey("Repeat")`
  first) — `RepeatVar` never overrides `UpdateCardPreview`, so it has no
  hook pass, matching the sim's static `hits` count.
- For cards with no damage var at all (`ContainsKey("Damage")` and
  `ContainsKey("CalculatedDamage")` both false), the card deals no damage —
  same convention `previews.py.card_base_damage` uses (returns `None`).

## Semantic caveats

- **AoE cards**: querying per-target with a non-null `target` (as above)
  is strictly more informative than the UI's own single aggregated number
  for `AllEnemies`/`RandomEnemies` cards — the UI only shows one number
  because it collapses across enemies via `CardPreviewMode.MultiCreatureTargeting`
  when `target == null`; per-target queries sidestep that collapse and
  give the true per-enemy number (matching what `previews.py` computes per
  target already).
- **Multi-hit cards**: `PreviewValue` is per-hit, not total; the mod must
  separately read `RepeatVar`/`Repeat` and multiply, exactly as
  `previews.py.preview_card_damage` returns per-hit and the caller
  multiplies by `card.hits`.
- **Block-only / non-damage cards**: use the parallel `BlockVar` /
  `CalculatedBlockVar` accessors (`DynamicVars.Block.PreviewValue`,
  `DynamicVars.CalculatedBlock.PreviewValue`) if `damage_matrix`'s sibling
  block-preview segment is ever in question — not scoped to this task, but
  the same call sequence pattern applies (`BlockVar`/`CalculatedBlockVar`
  in `Core/Localization/DynamicVars/`).
- **Orb/Defect-specific damage** (`OstyDamageVar`, `ExtraDamageVar` with
  `.FromOsty()`) exists in the var set but is out of scope — SpireBot's
  obs schema targets Ironclad per the sim's current character scope
  (see memory: `sim is Ironclad-only`); no caveat blocks Ironclad cards.
- **State mutation risk**: `UpdateDynamicVarPreview` only writes into the
  `DynamicVar` preview fields (`PreviewValue`/`EnchantedValue`), which the
  source comments explicitly mark display-only and separate from
  `BaseValue` (used for real calculations) — calling this repeatedly per
  candidate target is safe and does not touch combat state, matching the
  sim's `previews.py` module docstring guarantee ("no Cmd is called — so
  previewing can never mutate combat state").
- **Cost of calling per-target**: `Hook.ModifyDamage` iterates
  `runState.IterateHookListeners(combatState)` twice (additive +
  multiplicative) plus once for the cap — O(listeners) per (card, target)
  call. For a hand of ~10 cards × ~5 enemies this is cheap, but a live
  agent computing the full `damage_matrix` every decision should be aware
  it's re-walking hook listeners rather than reading a cached value.

## Sources consulted (file paths)

- `c:\Users\Perry\Desktop\BaseLib-StS2\Notes.txt`
- `c:\Users\Perry\Desktop\BaseLib-StS2\Extensions\AttackCommandExtensions.cs`
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Localization\DynamicVars\DynamicVar.cs`
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Localization\DynamicVars\DamageVar.cs`
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Localization\DynamicVars\CalculatedDamageVar.cs`
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Localization\DynamicVars\CalculatedVar.cs`
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Localization\DynamicVars\RepeatVar.cs`
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Localization\DynamicVars\DynamicVarSet.cs`
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Models\CardModel.cs` (lines ~490-550, ~1442-1480)
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Hooks\Hook.cs` (lines ~1486-1560, ~2511-2559)
- `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Entities\Cards\CardPreviewMode.cs`
- `c:\Users\Perry\Desktop\RunReplays\RunReplays\GameStateSnapshot.cs`
- `c:\Users\Perry\Desktop\sts2-rl\sts2_rl\previews.py`
