# Rest-site actions: card-driven options, Girya/Shovel/Eternal Feather, Miniature Tent

## Problem

Rest-site actions beyond Heal/Smith/Leave are surfaced through
`Relic.modify_rest_site_options(run, options)` and picked up automatically by
the RL action space (`DecisionRequest.legal_actions()` for `DecisionKind.REST`
is fully generic over `run.rest_site_options()` — no action-space or
observation changes needed per new option). Meat Cleaver, Pumpkin Candle, and
Pael's Growth already use this hook. Four more pieces of ported content need
it and currently don't have it:

- **Byrdonis Egg** (card) — cards have no equivalent hook at all today;
  `RunState.rest_site_options()` only scans `self.relics`.
- **Girya**, **Shovel** — relics whose Python files are documented no-op
  stubs ("out-of-combat, so this is a no-op stub").
- **Eternal Feather** — also a stub, but turns out not to need this hook at
  all (see below).
- **Miniature Tent** — a stub relic that changes the rest-site *flow itself*
  (multiple actions per visit), not the option list.

## Design

### 1. Card → rest-site-option hook (foundation)

- `Card.modify_rest_site_options(self, run, options) -> None`: no-op default
  in `cards/base.py`, in a new "Run-level rest-site hook" section mirroring
  the existing map-hook section there.
- `RestSiteOption` moves from `relics/base.py` to a new neutral module
  `sts2_rl/rest_site.py` (mirrors the real game's `Entities.RestSite`
  namespace, used by both Cards and Relics). `relics/base.py` re-exports it
  so `relics/meat_cleaver.py`, `pumpkin_candle.py`, `paels_growth.py`, and
  `driver.py` need no import changes.
- `RunState.rest_site_options()`: iterate `self.deck` then `self.relics`
  (matches `IterateHookListeners`'s real order: deck cards before relics),
  calling `modify_rest_site_options` on each.

### 2. Girya — LIFT

`modify_rest_site_options` appends a `LIFT` option when `times_lifted < 3`;
`on_select` does `self.times_lifted += 1`. `on_combat_start` (already
implemented) already reads `times_lifted` to grant Strength.

### 3. Shovel — DIG

`modify_rest_site_options` appends a `DIG` option when
`run.has_available_relics()`; `on_select` calls
`run.obtain_relic_from_grab_bag()` (existing helper, already used by treasure
rooms — matches `Shovel.cs`'s `DigRestSiteOption` calling
`RelicFactory.PullNextRelicFromFront` + obtain exactly).

### 4. Eternal Feather — passive heal, not an option

`EternalFeather.cs` heals `3 × (deck_count // 5)` automatically via
`AfterRoomEntered` when entering a rest site — no player choice. Implement as
`after_room_entered(self, run, point, room_type)` checking
`room_type == RoomType.REST_SITE`, calling `run.heal(...)`. No options-list
involvement.

### 5. Byrdonis Egg — HATCH (requires porting 2 more content pieces)

`HatchRestSiteOption.cs`'s `OnSelect` calls `RelicCmd.Obtain<Byrdpip>()`.
Neither `Byrdpip` (relic) nor `ByrdSwoop` (card) exist in sts2_rl yet:

- **`ByrdSwoop`** (`cards/event_cards.py`): Attack, EVENT rarity, 0 cost,
  `TargetType.ANY_ENEMY`, 14 damage (18 upgraded) — same shape as the
  existing `PeckCard`/`UltimateStrikeCard` in that file.
- **`Byrdpip`** (new `relics/byrdpip.py`): EVENT rarity, `adds_pet = True`.
  `after_obtained(self, run)`: for every `byrdonis_egg` card in `run.deck`,
  `run.transform_card(card, into=make_card("byrd_swoop"))`. The real game's
  `BeforeCombatStart` also spawns a decorative pet creature, but
  `Monsters/Byrdpip.cs` gives it 9999 HP, a hidden health bar, and a
  do-nothing move state machine (`NOTHING_MOVE`) — purely cosmetic flavor for
  `ByrdSwoop`'s attack animation, no combat mechanics. This matches the sim's
  established convention for pet relics (Pael's Legion also models only the
  mechanical payoff, not an actual pet creature — "the sim has no pets").
- **`ByrdonisEggCard.modify_rest_site_options`**: append a `HATCH` option;
  `on_select` calls `run.add_relic("byrdpip")` (triggers `after_obtained`
  automatically via the existing `add_relic` path).

Both new ids (`byrdpip`, `byrd_swoop`) are picked up automatically by
`vocab.py`'s append-on-import mechanism — no manual vocab editing. Neither
rarity (EVENT) is eligible for the relic grab bag (`_BAG_RARITIES` excludes
it) or, by the existing pattern for other EVENT-rarity cards, normal card
reward pools — so neither can leak in from an unrelated source.

### 6. Miniature Tent — multi-action rest visits (driver change)

`MiniatureTent.cs` overrides `ShouldDisableRemainingRestSiteOptions` to
return `false`. In the real game, a rest-site visit takes one static
snapshot of options (Heal + Smith + relic/card extras) at room entry; after
each pick, the game either clears the whole list (default — one action per
visit) or, with Miniature Tent, removes only the picked option and lets the
player keep choosing until they explicitly Leave or run out of options.

- `Relic.should_disable_remaining_rest_site_options(self, run) -> bool`:
  default `True`. `RunState.should_disable_remaining_rest_site_options()` is
  `all(r.should_disable_remaining_rest_site_options(self) for r in
  self.relics)` (any relic returning `False` flips the whole result to
  `False`, matching the game's short-circuit; `all([])` is `True`, so
  behavior with no relics present is unchanged).
- `driver.py`'s `_run_rest()` becomes a loop:
  - Take **one snapshot** of `run.rest_site_options()` at visit start — not
    recomputed each iteration, so a used-up option (e.g. Meat Cleaver's Cook)
    can't be reused within the same visit even if its precondition would
    still allow it, matching the real game's static per-visit list.
  - Track whether Heal/Smith have been used this visit (`DecisionRequest`
    gains fields for the snapshot + used-flags so `legal_actions()` reflects
    per-visit state instead of recomputing fresh).
  - After each pick: remove it from the live snapshot (or, for Heal/Smith,
    mark used), then check `should_disable_remaining_rest_site_options()`. If
    `True`, return (visit over). If `False`, loop and ask again.
  - `REST_LEAVE` always ends the visit immediately, at any point in the loop.

No changes needed to `run_env.py` (already fully generic over
`legal_actions()` counts, `CHOICE_SLOTS=16` has ample headroom) or the
observation encoder (nothing keys on option names/keys).

## Testing

Following existing conventions:
- `test/test_ancients.py`: one `test_<relic>_..._option()` per relic (Girya,
  Shovel), in the shape of `test_meat_cleaver_cook_option()` — call
  `run.rest_site_options()` / `options[0].on_select(run)` directly.
- A `test_eternal_feather_heals_on_rest_entry()` in `test_ancients.py`
  exercising `run.enter_point(...)` into a rest site (or calling
  `after_room_entered` directly with `RoomType.REST_SITE`).
- `test/test_events.py`: extend the existing Byrdonis Nest / Byrdonis Egg
  tests to cover Hatch — deck transform, relic gained, `HATCH` no longer
  offered afterward.
- `test/test_driver.py`: new tests for the `_run_rest()` loop — Miniature
  Tent taking two actions in one visit (e.g. Heal then Smith), the loop
  ending on Leave, and the loop ending on Heal alone when Miniature Tent is
  absent (regression check against existing `test_rest_choices`).
