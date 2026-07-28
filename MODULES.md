# Module reference â€” `sts2_rl/` core

A reader's guide to the Python files that live **directly** in `sts2_rl/`
(the `cards/` and `monsters/` packages have their own many-file structure and
are only summarized here), plus the interactive demo `test/run.py`.

For the high-level architecture, the golden fidelity rule, and known gaps, see
[CLAUDE.md](CLAUDE.md); for the enemy-porting guide see [ENEMIES.md](ENEMIES.md).
This file is the file-by-file map.

## How the pieces fit together

```
                         env.py  (STS2CombatEnv â€” Gymnasium wrapper)
                            â”‚  drives
                            â–¼
   combat.py  â”€â”€ owns â”€â”€â–º  CombatState â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚                      â”‚  player      enemies       hooks    history â”‚
      â”‚                      â–¼               â–¼             â–¼          â–¼     â”‚
      â”‚               player.py        monsters/       hooks.py   history.py
      â”‚            PlayerCombatState    Monster (â€¦)    HookSystem  CombatHistory
      â”‚                      â”‚  is-a         â”‚  is-a       â–² listeners
      â”‚                      â–¼               â–¼             â”‚ register
      â”‚                  creatures.py  â”€â”€ Creature â”€â”€â”€â”€â”€â”€â”€â”€â”˜
      â”‚  every state change goes through â€¦
      â–¼
   cmds.py  (DamageCmd, BlockCmd, PowerCmd, CreatureCmd, â€¦)
      â”‚  which read damage typing from â€¦        which apply / read â€¦
      â–¼                                              â–¼
   valueprops.py (ValueProp)              powers.py (Power + ALL_POWERS)
                                          afflictions.py (card markers)
                                          potions.py (Potion + ALL_POTIONS)
                                          cards/  (Card + ~193 cards)
```

The through-line: **nothing mutates HP/block/powers directly.** Effects go
through a **Cmd** (`cmds.py`), each Cmd fires **hooks** (`hooks.py`), and every
power/card/history entry is a **listener** on the one `HookSystem`. That is
what keeps buffs, debuffs, and reactions correct no matter what triggers them.

## The files

### `__init__.py` â€” public API surface
Re-exports the engine, command, and hook layers plus the commonly used
creatures/cards/potions/powers, grouped by area with an explicit `__all__`.
The full power/potion catalogues are reached through the `ALL_POWERS` /
`ALL_POTIONS` registries rather than being individually exported; build any
card/potion by id with `make_card` / `make_potion`.

### `creatures.py` â€” `Creature`
The common base for both combatants. Holds the shared state â€” `max_hp`/`hp`,
`block`, the `powers` dict, `side` (`"player"`/`"enemy"`), and the
`stunned`/`escaped` flags the loop reads â€” plus convenience reads (`strength`,
`is_dead`, `is_gone`). Subclassed by `PlayerCombatState` and `Monster`.

### `player.py` â€” `PlayerCombatState`
The player side. Extends `Creature` with energy, the four card piles
(hand / draw / discard / exhaust), and potions. Owns the card-flow verbs:
`start_turn` (clear block â†’ reset energy â†’ turn-start hooks â†’ draw, with
turn-1 innate handling), `discard_hand` (respecting Retain),
`reshuffle_discard_into_draw`, and the low-level `_draw`. Tunables
(`ENERGY_PER_TURN`, `DRAW_PER_TURN`, `MAX_HAND_SIZE`, `MAX_POTIONS`) are class
attributes.

### `combat.py` â€” `CombatState`, `CombatCtx`, `Phase`, `CombatResult`
The top-level driver and turn loop. `CombatState` wires together the player,
enemies, shared RNG, `HookSystem`, and `CombatHistory` at construction, and
exposes the player-facing API: `play_card` / `auto_play_card` / `use_potion` /
`end_turn` / `select_cards` / `valid_actions`. It runs the turn structure
(player turn-end â†’ turn-end-in-hand cards â†’ discard â†’ per-enemy turns â†’
side-end â†’ next player turn) and decides the win/lose condition (player dead,
or every non-`minion` enemy gone). `CombatCtx` is the lightweight per-execution
context handed to cards and Cmds during resolution.

### `hooks.py` â€” `HookSystem`
The central callback registry, mirroring STS2's `AbstractModel` pattern.
Listeners register once and are called by **duck-typing** â€” a hook only invokes
listeners that define the matching method. Three families:
- **Modifier** â€” aggregate a return value: additive (summed), multiplicative
  (product), or chain (each listener transforms the value in turn).
- **Event** â€” fire-and-forget notifications (`on_card_played`,
  `on_damage_received`, `on_enemy_turn_start`, â€¦).
- **Predicate** â€” any listener returning `False` short-circuits the default
  (`should_die`, `should_clear_block`, `should_play_card`, â€¦).

`HookSystem.combat` back-references the owning `CombatState`. Some hooks
(orbs, card-retained, â€¦) are forward-looking scaffolding for features not yet
implemented â€” kept intentionally.

### `cmds.py` â€” the command layer
Namespaced `@staticmethod` verbs that mutate combat state, each taking the
`HookSystem` explicitly (no Cmd instance state):
- **`DamageCmd.deal`** â€” the full typed damage pipeline: powered modifiers â†’
  damage cap â†’ `on_attacked` â†’ block absorption â†’ `modify_hp_lost` â†’ apply â†’
  death check â†’ post-damage events.
- **`BlockCmd`** â€” block through the additive/multiplicative pipeline.
- **`CreatureCmd`** â€” heal / kill / stun / escape / add.
- **`PowerCmd`** â€” apply (with stacking + Artifact debuff interception) / remove.
- **`StrengthCmd`, `DrawCmd`, `ExhaustCmd`, `EnergyCmd`** â€” the smaller verbs.
- **`CardCmd`** â€” attach/clear afflictions.
- **`CardPileCmd`** â€” move newly generated cards into a pile (registering them
  as hook listeners).
- **`CardSelectCmd`** â€” in-combat card selection, delegated to
  `CombatState.select_cards`.

### `valueprops.py` â€” `ValueProp`, `DamageProps`
Damage/block typing flags. `ValueProp` (`UNBLOCKABLE` / `UNPOWERED` / `MOVE`)
decides which parts of the pipeline apply; `is_powered_attack` gates the
Strength/Vulnerable/Weak modifiers. `DamageProps` bundles the common flag
combinations by source (card attack, monster move, HP-loss drawback, Poison, â€¦).

### `powers.py` â€” `Power`, `PowerType`, `ALL_POWERS`
~90 buff/debuff classes plus the `ALL_POWERS` idâ†’class registry. Each subclass
overrides only the hook methods it needs. Organized into sections: **Buffs**,
**Debuffs**, **Ironclad card powers**, **Overgrowth (Act 1) enemy powers**, and
**Hive (Act 2) enemy powers**. `PowerCmd.apply` handles stacking / Artifact
interception / registration; `_tick` / `_tick_duration` handle duration decay
and `_expire` unregisters.

### `afflictions.py` â€” `Affliction` + markers
Markers attached to a single card (Ringing, Entangled, Smog, Tainted). They
carry no logic themselves â€” the power that applied them reads them back.
Applied/cleared through `CardCmd`. Ringing/Smog/Tainted gate whether a card can
be played this turn; Entangled raises an Attack card's energy cost.

### `potions.py` â€” `Potion` + `ALL_POTIONS`
Potion base plus **every potion an Ironclad run can roll** — all 45 of
`SharedPotionPool` and Ironclad4Epoch's Blood Potion / Soldier's Stew /
Ashwater — plus the event-only Glowwater, Potion-Shaped Rock and Foul Potion.
Values verified against the source models. Registered via `@register_potion`
and built by id with `make_potion` (ids are `snake_case` of the source class
name); `potion_pools.py` holds the rarity roster the reward/shop generators
draw from. `in_reward_pool=False` keeps the event-only ones out of random
potion rolls, and `random_potion` additionally skips the three
`CanBeGeneratedInCombat=false` potions (Fruit Juice / Fairy in a Bottle /
Regen Potion). The Foul Potion is the shared Fake Merchant event's key, and in
combat it damages **every** creature — the thrower included
(`CombatState.Creatures`).

Two potions need more than an `use()` body: **Fairy in a Bottle** is
`PotionUsage.Automatic`, so it is a hook listener while it sits in the belt
(`CombatState.IterateHookListeners` walks each player's `PotionSlots`) — its
`should_die`/`after_preventing_death` pair vetoes the player's death and heals
to 30% of max HP, and `automatic = True` keeps it out of `use_potion` and the
env's action mask. **Entropic Brew** refills the belt through
`PlayerCombatState.add_potion`, which registers newly procured potions as
listeners the same way. The cross-character potions (Silent/Defect/Regent/
Necrobinder pools: Ghost in a Jar, Poison Potion, Cunning Potion, Essence of
Darkness, Focus Potion, Potion of Capacity, Star Potion, King's Courage,
Cosmic Concoction, Bone Brew, Pot of Ghouls, Potion of Doom) are **not**
ported — an Ironclad run can never roll them, and most need unported systems
(orbs, Stars, Forge, Osty, Soul cards, Shivs).

### `characters.py` — `Character` + `CHARACTERS`

The character table: one frozen `Character` row per playable character
(`CharacterModel` and its five subclasses), holding starting HP/gold, max
energy, base orb slots, the starting deck and relics **in source order**, and
the character's card / relic / potion pools. `CHARACTERS` is keyed by id and
declared in `ModelDb.AllCharacters` order — that order is parity-critical
because Orobas picks the Sea Glass character with a `NextItem` over it.

`RunState(character="ironclad")` and `CombatState(character=...)` resolve a row
through `get_character`; everything character-dependent reads off it, so there
are no Ironclad literals in the run layer and no `pool=IRONCLAD_POOL` defaults
anywhere. The card and potion generators take their pool explicitly and raise
`TypeError` if it is missing, which turns a forgotten wiring into a loud
failure instead of a silent Ironclad fallback.

**Content ownership.** `Relic.character` / `Potion.character` name the pool a
class belongs to (`None` = shared). `relics/` auto-imports every module into
the global `ALL_RELICS`, so without that attribute a ported Defect relic would
be rollable in an *Ironclad* run; `RunState.owns_relic` / `owns_potion` apply
it to every registry scan (the legacy grab bag, the shop bag, the reward-potion
scans). The scans still iterate in registry order — the bag feeds a shuffle,
so re-deriving it from a pool roster would change every Ironclad relic pull
even though the membership is identical.

**Porting a character** is therefore a table row plus content, with no run-layer
edits: fill that row's `starting_deck`, `card_pool`, `relic_pool` and
`potion_pool`, add the cards/relics/potions (character relics and potions
setting `character = "<id>"`), and add the pool tuples to `cards/pool.py`,
`relic_pools.py` and `potion_pools.py`. Only Ironclad is ported; the other four
rows carry their real source-verified stats with empty pools, and
`get_character` raises `NotImplementedError` naming the missing content rather
than dealing an empty deck.

### `history.py` â€” `CombatHistory` + entry types
The combat event log, mirroring `CombatManager.History`. Records typed entries
(card played / exhausted / damage received) tagged with the turn. Registered as
the **first** hook listener so entries exist before other listeners react to
the same event, and queried by cards/powers for "did X happen this turn / this
combat" conditionals.

### `previews.py` â€” pure damage/block/cost previews
The numbers the game shows the player, as *pure reads*: each helper replays
the exact modifier stages of `DamageCmd.deal` / `BlockCmd.apply` without
calling a Cmd, so previewing can never mutate combat state.
`preview_incoming_damage` / `preview_total_incoming` mirror the intent
display (`AttackIntent.GetSingleDamage`) including post-block HP loss;
`preview_card_damage` / `preview_card_block` / `preview_card_energy_cost` /
`card_base_damage` mirror the on-card numbers. Feeds the env observation and
any policy that needs lethal math.

### `selectors.py` â€” `scripted_card_selector`
The deterministic heuristic for `CombatState.card_selector` (RL.md wiring
option 2), installed by `STS2FullCombatEnv` by default: `"upgrade"` â†’
highest-cost upgradable card, `"exhaust"` â†’ Status/Curse first,
`"to_draw_top"` â†’ cheapest attack, `"curse_of_knowledge"` â†’ the least
crippling Knowledge Demon curse, unknown purposes â†’ offered order. A pure
function of `(purpose, candidates, count)` â€” no RNG, no state reads â€” so
selection effects add no hidden stochasticity to training.

### `full_env.py` â€” `STS2FullCombatEnv` (+ obs layout, `AblatedObsEnv`)
The full-combat Gymnasium env for MaskablePPO: flat `Discrete` action space
(end turn / play cardÃ—target / potionÃ—target) with legality masks, and the
schema-v2 observation (see [OBS_PLAN.md](OBS_PLAN.md)) â€” absolute HP/block/
damage on a shared unit, pipeline-accurate intent and card previews, the
per-(hand, enemy) effective-damage matrix, full power vocabulary, enemy
identity, and pile-composition histograms. The obs dimension is measured from
a probe combat at construction so the declared space can never drift from
`_build_obs`. Also exposes the named observation layout (`obs_segments` /
`obs_slices`: segment name â†’ slice, used by the pin tests and the ablation),
`numeric_obs_indices` (every absolute-number/preview dim), and
`AblatedObsEnv` â€” the baseline ablation arm that zeroes those dims while
keeping shape, masks, and dynamics identical.

### `probes.py` â€” the lethal-arithmetic probe suite
Eight scripted micro-scenarios (`PROBES`) in four single-number pairs â€”
strike-lethal edge (enemy 6 vs 7 HP), block-or-die edge (12 vs 11 telegraphed
against 12 HP), Vulnerable present/absent, player Weak present/absent â€” where
passing both sides of a pair requires doing the exact arithmetic. Each probe
is a one-dummy combat (fixed-stat `probe_dummy` enemy, hand = [Strike,
Defend], 1 energy); a policy plays one turn and a turn-level outcome is
checked (won untouched / survived / raced). `run_probes` / `probe_accuracy`
score any `(env, obs, mask) -> action` policy; `lethal_oracle` is the
scripted numerate ceiling (8/8 by construction) and a baseline player.

### `evaluation.py` â€” win rate + probe accuracy side by side
`evaluate_win_rate` (seeded episodes over any env; reports win rate, mean
turns, mean HP left) and `evaluate_probes`, plus the policy adapters:
`masked_random_policy`, `model_policy` (MaskablePPO, with an optional obs
transform), and `ablation_transform` (the `AblatedObsEnv` zeroing as a
transform, for evaluating ablation-trained models on the raw-obs probes).
CLIs: `py eval.py MODEL --env full [--ablated] [--baselines]` prints the
metrics table; `py test/ablation.py` trains full-vs-ablated MaskablePPO arms
on identical seeds and reports win-rate curves + probe accuracy for both.

### `env.py` â€” `STS2CombatEnv`
The Gymnasium wrapper for RL training. Deliberately narrower than the engine: 3
actions (end turn / play a Strike / play a Defend) and a 17-float observation
(layout documented at the top of the file). Reward is the per-step normalized
HP delta plus 1.0 on a win; `action_masks` supports sb3-contrib's MaskablePPO.
Growing the action space to full hand indices + targets + potions is the
natural next step (the engine already supports all of it) â€” [RL.md](RL.md)
maps out every interface that work needs to cover.

## `test/run.py` â€” interactive demo
A standalone terminal client for playing a combat by hand â€” not part of the
package. Pick an encounter and deck at the top of the file, then type a card
index to play it, `e` to end the turn, and `d`/`p`/`x` to inspect the
draw/discard/exhaust piles. It installs an interactive `card_selector` on the
`CombatState` so card-selection effects (Armaments, Burning Pact, â€¦) prompt you
instead of choosing at random, and it demonstrates targeting, X-cost cards, and
intent display. Run with `py test/run.py`.
