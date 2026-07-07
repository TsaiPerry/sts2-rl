# Module reference — `sts2_rl/` core

A reader's guide to the Python files that live **directly** in `sts2_rl/`
(the `cards/` and `monsters/` packages have their own many-file structure and
are only summarized here), plus the interactive demo `test/run.py`.

For the high-level architecture, the golden fidelity rule, and known gaps, see
[CLAUDE.md](CLAUDE.md); for the enemy-porting guide see [ENEMIES.md](ENEMIES.md).
This file is the file-by-file map.

## How the pieces fit together

```
                         env.py  (STS2CombatEnv — Gymnasium wrapper)
                            │  drives
                            ▼
   combat.py  ── owns ──►  CombatState ──────────────────────────────────┐
      │                      │  player      enemies       hooks    history │
      │                      ▼               ▼             ▼          ▼     │
      │               player.py        monsters/       hooks.py   history.py
      │            PlayerCombatState    Monster (…)    HookSystem  CombatHistory
      │                      │  is-a         │  is-a       ▲ listeners
      │                      ▼               ▼             │ register
      │                  creatures.py  ── Creature ────────┘
      │  every state change goes through …
      ▼
   cmds.py  (DamageCmd, BlockCmd, PowerCmd, CreatureCmd, …)
      │  which read damage typing from …        which apply / read …
      ▼                                              ▼
   valueprops.py (ValueProp)              powers.py (Power + ALL_POWERS)
                                          afflictions.py (card markers)
                                          potions.py (Potion + ALL_POTIONS)
                                          cards/  (Card + ~110 cards)
```

The through-line: **nothing mutates HP/block/powers directly.** Effects go
through a **Cmd** (`cmds.py`), each Cmd fires **hooks** (`hooks.py`), and every
power/card/history entry is a **listener** on the one `HookSystem`. That is
what keeps buffs, debuffs, and reactions correct no matter what triggers them.

## The files

### `__init__.py` — public API surface
Re-exports the engine, command, and hook layers plus the commonly used
creatures/cards/potions/powers, grouped by area with an explicit `__all__`.
The full power/potion catalogues are reached through the `ALL_POWERS` /
`ALL_POTIONS` registries rather than being individually exported; build any
card/potion by id with `make_card` / `make_potion`.

### `creatures.py` — `Creature`
The common base for both combatants. Holds the shared state — `max_hp`/`hp`,
`block`, the `powers` dict, `side` (`"player"`/`"enemy"`), and the
`stunned`/`escaped` flags the loop reads — plus convenience reads (`strength`,
`is_dead`, `is_gone`). Subclassed by `PlayerCombatState` and `Monster`.

### `player.py` — `PlayerCombatState`
The player side. Extends `Creature` with energy, the four card piles
(hand / draw / discard / exhaust), and potions. Owns the card-flow verbs:
`start_turn` (clear block → reset energy → turn-start hooks → draw, with
turn-1 innate handling), `discard_hand` (respecting Retain),
`reshuffle_discard_into_draw`, and the low-level `_draw`. Tunables
(`ENERGY_PER_TURN`, `DRAW_PER_TURN`, `MAX_HAND_SIZE`, `MAX_POTIONS`) are class
attributes.

### `combat.py` — `CombatState`, `CombatCtx`, `Phase`, `CombatResult`
The top-level driver and turn loop. `CombatState` wires together the player,
enemies, shared RNG, `HookSystem`, and `CombatHistory` at construction, and
exposes the player-facing API: `play_card` / `auto_play_card` / `use_potion` /
`end_turn` / `select_cards` / `valid_actions`. It runs the turn structure
(player turn-end → turn-end-in-hand cards → discard → per-enemy turns →
side-end → next player turn) and decides the win/lose condition (player dead,
or every non-`minion` enemy gone). `CombatCtx` is the lightweight per-execution
context handed to cards and Cmds during resolution.

### `hooks.py` — `HookSystem`
The central callback registry, mirroring STS2's `AbstractModel` pattern.
Listeners register once and are called by **duck-typing** — a hook only invokes
listeners that define the matching method. Three families:
- **Modifier** — aggregate a return value: additive (summed), multiplicative
  (product), or chain (each listener transforms the value in turn).
- **Event** — fire-and-forget notifications (`on_card_played`,
  `on_damage_received`, `on_enemy_turn_start`, …).
- **Predicate** — any listener returning `False` short-circuits the default
  (`should_die`, `should_clear_block`, `should_play_card`, …).

`HookSystem.combat` back-references the owning `CombatState`. Some hooks
(orbs, card-retained, …) are forward-looking scaffolding for features not yet
implemented — kept intentionally.

### `cmds.py` — the command layer
Namespaced `@staticmethod` verbs that mutate combat state, each taking the
`HookSystem` explicitly (no Cmd instance state):
- **`DamageCmd.deal`** — the full typed damage pipeline: powered modifiers →
  damage cap → `on_attacked` → block absorption → `modify_hp_lost` → apply →
  death check → post-damage events.
- **`BlockCmd`** — block through the additive/multiplicative pipeline.
- **`CreatureCmd`** — heal / kill / stun / escape / add.
- **`PowerCmd`** — apply (with stacking + Artifact debuff interception) / remove.
- **`StrengthCmd`, `DrawCmd`, `ExhaustCmd`, `EnergyCmd`** — the smaller verbs.
- **`CardCmd`** — attach/clear afflictions.
- **`CardPileCmd`** — move newly generated cards into a pile (registering them
  as hook listeners).
- **`CardSelectCmd`** — in-combat card selection, delegated to
  `CombatState.select_cards`.

### `valueprops.py` — `ValueProp`, `DamageProps`
Damage/block typing flags. `ValueProp` (`UNBLOCKABLE` / `UNPOWERED` / `MOVE`)
decides which parts of the pipeline apply; `is_powered_attack` gates the
Strength/Vulnerable/Weak modifiers. `DamageProps` bundles the common flag
combinations by source (card attack, monster move, HP-loss drawback, Poison, …).

### `powers.py` — `Power`, `PowerType`, `ALL_POWERS`
~90 buff/debuff classes plus the `ALL_POWERS` id→class registry. Each subclass
overrides only the hook methods it needs. Organized into sections: **Buffs**,
**Debuffs**, **Ironclad card powers**, **Overgrowth (Act 1) enemy powers**, and
**Hive (Act 2) enemy powers**. `PowerCmd.apply` handles stacking / Artifact
interception / registration; `_tick` / `_tick_duration` handle duration decay
and `_expire` unregisters.

### `afflictions.py` — `Affliction` + markers
Markers attached to a single card (Ringing, Entangled, Smog, Tainted). They
carry no logic themselves — the power that applied them reads them back.
Applied/cleared through `CardCmd`. Ringing/Smog/Tainted gate whether a card can
be played this turn; Entangled raises an Attack card's energy cost.

### `potions.py` — `Potion` + `ALL_POTIONS`
Potion base plus the implemented potions (Fire / Block / Strength / Blood /
Weak), values verified against the source models. Registered via
`@register_potion` and built by id with `make_potion`.

### `history.py` — `CombatHistory` + entry types
The combat event log, mirroring `CombatManager.History`. Records typed entries
(card played / exhausted / damage received) tagged with the turn. Registered as
the **first** hook listener so entries exist before other listeners react to
the same event, and queried by cards/powers for "did X happen this turn / this
combat" conditionals.

### `previews.py` — pure damage/block/cost previews
The numbers the game shows the player, as *pure reads*: each helper replays
the exact modifier stages of `DamageCmd.deal` / `BlockCmd.apply` without
calling a Cmd, so previewing can never mutate combat state.
`preview_incoming_damage` / `preview_total_incoming` mirror the intent
display (`AttackIntent.GetSingleDamage`) including post-block HP loss;
`preview_card_damage` / `preview_card_block` / `preview_card_energy_cost` /
`card_base_damage` mirror the on-card numbers. Feeds the env observation and
any policy that needs lethal math.

### `selectors.py` — `scripted_card_selector`
The deterministic heuristic for `CombatState.card_selector` (RL.md wiring
option 2), installed by `STS2FullCombatEnv` by default: `"upgrade"` →
highest-cost upgradable card, `"exhaust"` → Status/Curse first,
`"to_draw_top"` → cheapest attack, `"curse_of_knowledge"` → the least
crippling Knowledge Demon curse, unknown purposes → offered order. A pure
function of `(purpose, candidates, count)` — no RNG, no state reads — so
selection effects add no hidden stochasticity to training.

### `full_env.py` — `STS2FullCombatEnv` (+ obs layout, `AblatedObsEnv`)
The full-combat Gymnasium env for MaskablePPO: flat `Discrete` action space
(end turn / play card×target / potion×target) with legality masks, and the
schema-v2 observation (see [OBS_PLAN.md](OBS_PLAN.md)) — absolute HP/block/
damage on a shared unit, pipeline-accurate intent and card previews, the
per-(hand, enemy) effective-damage matrix, full power vocabulary, enemy
identity, and pile-composition histograms. The obs dimension is measured from
a probe combat at construction so the declared space can never drift from
`_build_obs`. Also exposes the named observation layout (`obs_segments` /
`obs_slices`: segment name → slice, used by the pin tests and the ablation),
`numeric_obs_indices` (every absolute-number/preview dim), and
`AblatedObsEnv` — the baseline ablation arm that zeroes those dims while
keeping shape, masks, and dynamics identical.

### `probes.py` — the lethal-arithmetic probe suite
Eight scripted micro-scenarios (`PROBES`) in four single-number pairs —
strike-lethal edge (enemy 6 vs 7 HP), block-or-die edge (12 vs 11 telegraphed
against 12 HP), Vulnerable present/absent, player Weak present/absent — where
passing both sides of a pair requires doing the exact arithmetic. Each probe
is a one-dummy combat (fixed-stat `probe_dummy` enemy, hand = [Strike,
Defend], 1 energy); a policy plays one turn and a turn-level outcome is
checked (won untouched / survived / raced). `run_probes` / `probe_accuracy`
score any `(env, obs, mask) -> action` policy; `lethal_oracle` is the
scripted numerate ceiling (8/8 by construction) and a baseline player.

### `evaluation.py` — win rate + probe accuracy side by side
`evaluate_win_rate` (seeded episodes over any env; reports win rate, mean
turns, mean HP left) and `evaluate_probes`, plus the policy adapters:
`masked_random_policy`, `model_policy` (MaskablePPO, with an optional obs
transform), and `ablation_transform` (the `AblatedObsEnv` zeroing as a
transform, for evaluating ablation-trained models on the raw-obs probes).
CLIs: `py eval.py MODEL --env full [--ablated] [--baselines]` prints the
metrics table; `py test/ablation.py` trains full-vs-ablated MaskablePPO arms
on identical seeds and reports win-rate curves + probe accuracy for both.

### `env.py` — `STS2CombatEnv`
The Gymnasium wrapper for RL training. Deliberately narrower than the engine: 3
actions (end turn / play a Strike / play a Defend) and a 17-float observation
(layout documented at the top of the file). Reward is the per-step normalized
HP delta plus 1.0 on a win; `action_masks` supports sb3-contrib's MaskablePPO.
Growing the action space to full hand indices + targets + potions is the
natural next step (the engine already supports all of it) — [RL.md](RL.md)
maps out every interface that work needs to cover.

## `test/run.py` — interactive demo
A standalone terminal client for playing a combat by hand — not part of the
package. Pick an encounter and deck at the top of the file, then type a card
index to play it, `e` to end the turn, and `d`/`p`/`x` to inspect the
draw/discard/exhaust piles. It installs an interactive `card_selector` on the
`CombatState` so card-selection effects (Armaments, Burning Pact, …) prompt you
instead of choosing at random, and it demonstrates targeting, X-cost cards, and
intent display. Run with `py test/run.py`.
