# R12 — kifuda / `relic/_auto_keep`: partial-confirm out-of-combat card selection

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding). Maps scouted
2026-08-01; several waves have landed since — re-verify line numbers, and
read `R6-report.md` (driver selector work) plus `R10-report.md` first.

## Premise correction (the record prose is stale — flag it in your report)

`relic/kifuda/AfterObtained`'s rollup text says "the port does nothing at
all". FALSE today: `relics/kifuda.py:1-29` implements the pickup —
`has_upon_pickup_effect` `:12`, CARDS=3 `:14`, ADROIT_AMOUNT=3 `:15`,
`AdroitEnchantment.can_enchant` filter `:24`,
`run.select_cards("enchant", candidates, 3)` `:25`, attach Adroit-3
`:26-28`. The LIVE gap is exactly `relic/kifuda/g2` (mechanism
`relic/_auto_keep`): the selection cannot be partially confirmed.

## The divergence

C# `Kifuda.cs:24-37`: `new CardSelectorPrefs(EnchantSelectionPrompt, 0,
Cards.IntValue)` `:26` with `Cancelable = false` `:28`,
`RequireManualConfirmation = true` `:29` → MinSelect 0, MaxSelect 3: the
player may confirm 0, 1, 2 or 3 enchants but may NOT back out. Screen
semantics: `NDeckEnchantSelectScreen.cs` — cancel gated on `Cancelable`
(`:120`, `:214`), confirm enabled once `MinSelect != MaxSelect &&
selected >= MinSelect` (`:176`). Range-ctor derivation
`RequireManualConfirmation = MinSelect >= 0 && MinSelect != MaxSelect`
(`CardSelectorPrefs.cs:68-78`, at `:77`). NOTE the deck-enchant overload
`CardSelectCmd.FromDeckForEnchantment` (`CardSelectCmd.cs:547-...`) has
its auto-resolve shortcut at `:576` on `cards.Count <= prefs.MinSelect`
and — unlike the `:287/:343/:396/:653/:708` overloads — does NOT consult
RequireManualConfirmation; deck-order sort at `:568-574`.

Sim: `run.select_cards(purpose, candidates, count)` (`run.py:488-507`)
has NO min_select; the driver's `_card_selector` (`driver.py:329-350`)
keys skippability on PURPOSE (`SKIPPABLE_PURPOSES`, `driver.py:93-96` —
"enchant" NOT in it) and force-fills when not skippable (`:332-333`). So
Kifuda always enchants exactly 3.

The in-combat twin already solved this: `CombatState.select_cards`
(`combat.py:1134-1246`) HAS `min_select` (`:1139`), derives
require_manual_confirmation at `:1210` (citing CardSelectorPrefs.cs:77),
models the shortcut `:1212-1214`, floor-aware selectorless fallback
`:1238-1246`. **Port those semantics up to RunState.**

## The fix

- `run.py::select_cards`: add `min_select` (default preserving today's
  behavior for every existing caller — there are many "enchant" sites:
  `relics/beautiful_bracelet.py:26`, `events/field_of_man_sized_holes.py:47`,
  `events/grave_of_the_forgotten.py:46`,
  `events/waterlogged_scriptorium.py:52`, `events/wood_carvings.py:65`,
  `events/symbiote.py:44`, `events/spiraling_whirlpool.py:45`,
  `events/stone_of_all_time.py:74` — their C# counterparts may or may not
  be 0..N ranges; do NOT change their behavior in this task, only
  Kifuda's; note any that look like the same _auto_keep shape for the
  report).
- `driver.py::_card_selector`: make skippability min-select-aware (a
  per-pick decline when picked >= min_select), preserving the
  purpose-keyed behavior for all existing purposes. Scouted alternative:
  a new optional purpose — your call; derive from how the driver's
  decision protocol best expresses "confirm with fewer". Mind
  `test/test_rng_tripwire.py:15` (driver.py line pins).
- `relics/kifuda.py:25`: pass min_select=0 (and whatever the new surface
  needs).
- RL/purpose vocab: "enchant" is already in `vocab.json:846`; a NEW
  purpose id would bucket to `_unknown` unless registered
  (`run_env.py:174-188`, `:760`) — avoid needing a vocab change if you
  can; if you add one, say why.

## Tests

RED first: a pin proving today's Kifuda force-fills 3, flipping to
partial-confirm (e.g. scripted driver confirms after 1). Cover: min==max
unchanged (exact-count screens), min_select=0 with selectorless fallback
(bare RunState — today's fallback `rng.sample`s exactly count; derive
what C#'s selectorless equivalent is from `:576`'s shortcut and the
`Selector.GetSelectedCards(list, MinSelect, MaxSelect)` call `:582`),
cancel NOT possible (the screen is not skippable as a whole — distinct
from confirming 0: C# separates "confirm with fewer" from "back out").
Run: `test/test_driver.py`, `test/test_false_premise_stubs.py:218-221`,
`test/test_relics.py:141` area, every file you touch.

## Footprint (yours alone this wave)

`sts2_rl/run.py` (`select_cards`), `sts2_rl/driver.py`
(`_card_selector` + SKIPPABLE_PURPOSES region), `sts2_rl/relics/kifuda.py`,
optionally `sts2_rl/run_env.py` (+`vocab.json` only with justification),
plus tests. NOT yours: `events/**` (report, don't fix, other _auto_keep
shapes), `rewards.py`, `combat.py`, `hooks.py`, `powers.py`, `cmds.py`,
other relics, `audit/**`.

## Entries to settle (propose; controller applies)

`relic/kifuda/g2` (mechanism `relic/_auto_keep` — LIVE) and
`relic/kifuda/AfterObtained` (carved out of the triage batches for you;
its "does nothing at all" premise is stale — the close must state the
replaced reasoning). If the fix lands, `relic/_auto_keep` may drop from
the live list entirely — say whether any other site shares the mechanism
(the "enchant" sites above) before claiming a full close; narrow if so.

Report path: `.superpowers/sdd/round13/R12-report.md`.
