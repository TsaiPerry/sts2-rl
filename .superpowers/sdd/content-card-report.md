# Stream 3 — card content audits

Branch `audit-card`, worktree `c:\Users\Perry\Desktop\sts2-rl-card`.
Records under `audit/records/card/**`; probes under `audit/tools/card_probes.py`.

**Status: COMPLETE.** All 202 auditable units of the 203-unit roster are
audited; the 203rd (`card/sweep`) has no C# counterpart and is resolved in §7.

---

## 1. Result

```
py audit/tools/audit_status.py --kind card
kind    total  audited  invalid  stale  gaps  unaudited
card      203      202        0      0   109          1
```

| | count |
|---|---|
| Records | 202 |
| Unit rollups | **109 gap**, 89 faithful, 3 deliberate-divergence, 1 waiver |
| Verdict entries (hooks + guards) | 1074: 918 faithful, **149 gap**, 5 dd, 2 waiver |

Counts as of the review fix pass (§10), which raised six `faithful` guards to
`gap`. Before it: 107 gap rollups / 143 gap entries.

`py -m pytest test/ -q` was run after every batch and never moved: **2476
passed, 31 xfailed**, the same as before the stream started. Audits add no
executable code; the only non-record file added is `audit/tools/card_probes.py`.

Fourteen batches, one commit each: `10946560`, `716f023e`, `2c8b3c35`,
`935bc8da`, `6cd22260`, `f5e3e3e8`, `437c0134`, `708a6a37`, `7f45ec85`,
`218d7458`, `50eb0d52`, `d700872d`, `b5b6e211`, `2e1a5a97`.

**Reading the 53% gap rate.** It is a rollup number: one `gap` entry anywhere in
a unit makes the unit a gap. 149 of 1074 entries (14%) are gaps, and a large
share of those are three pool-wide DORMANT families — the `-1` canonical cost on
unplayable cards, a printed DynamicVar with no stored counterpart, and the
`is_gone` liveness guards. The genuinely card-specific live defects are the ~25
in §4.

---

## 2. Cost data

Reported after batches 1–2 as requested, and now over all 14.

| Metric | Batch 1 | Batch 2 | Steady state (3–14) |
|---|---|---|---|
| Units | 15 | 15 | 15 (7 in batch 14) |
| Gap rate (unit rollups) | 53% | 67% | 33–73%, mean 53% |
| Units needing EXECUTION to settle | 5 | 1 | 0–2 |
| Test-suite run | 250 s | 253 s | 208–216 s |

**Wall time.** Batch 1 took roughly 2× batch 2 because it paid the one-off
costs: reading `cards/base.py` and the `CardModel` surface in full, reading the
`creature_card_cmds` and `hook_dispatch` gap lists, establishing what
`CalculatedVar` / `CardEnergyCost` / `CreateClone` / `CardSelectCmd` /
`AttackCommand` actually do, and writing the probe script. Steady state settled
at roughly **1.5–2 minutes of wall time per unit** excluding the fixed
~3.5-minute suite run, dominated by reading the two sources rather than by
writing records.

**Tokens.** Roughly **4–5 k per unit including the record**, and it did trend
down. Cards are small (C# models 20–120 lines, sim classes 30–50), and read in
bulk — 7–8 C# files per `cat -n` call, one sim module per call — a 15-unit batch
costs ~25–30 k tokens of source. Cross-file investigation (the greps into
`CreatureCmd.cs`, `PowerCmd.cs`, `CardEnergyCost.cs`, `AttackCommand.cs`,
`DamageResult.cs`, `hooks.py`, `powers.py` that one suspicious line forces) cost
about as much again in the early batches and almost nothing by batch 8, because
each answer was reusable.

**What made it cheap.** Three things, all worth copying:

1. **Pool-wide probes.** Five probe functions answered five questions once for
   all 203 units instead of 203 times (§3). The downgrade probe alone found five
   live gaps that a static read of each file would have missed.
2. **Shared finding texts.** Each recurring mechanism has one paragraph, reused
   verbatim across every unit that exhibits it, so rule 3 (one verdict per
   mechanism) is satisfied by construction rather than by memory.
3. **Emitting records from a data script** rather than hand-writing 202 JSON
   files, with the rollup computed from the entries so it can never disagree
   with `harness.py`'s.

**What was expensive.** The suite run (~3.5 min × 14 ≈ 50 minutes of pure wall
time) for a result that is invariant by construction, and the fact that
accumulated cross-file knowledge — the thing that makes later batches cheap — is
also what fills the context window.

---

## 3. Pool-wide findings (executed)

Every number below is reproducible with `py audit/tools/card_probes.py`, which
is committed.

### 3.1 `downgrade()` does not restore upgrade-toggled keywords — 5 cards, LIVE

`Card.downgrade` (cards/base.py:150-165) rebuilds printed state by zeroing
`upgrade_level`, re-running `_init_vars` and re-applying upgrades. A card whose
`_on_upgrade` writes a KEYWORD flag that `_init_vars` does not re-seed keeps
that flag forever. C# `CardModel.DowngradeInternal` rebuilds the whole keyword
set from canonical (`_keywords = cardModel.GetKeywordsWithSources(
KeywordSources.Local).ToHashSet()`, CardModel.cs:2143).

```
downgrade: 5 of 203 sim cards do not restore
  aggression:  innate:      False -> True
  apparition:  is_ethereal: True  -> False
  hello_world: innate:      False -> True
  juggling:    innate:      False -> True
  wish:        retain:      False -> True
```

LIVE — `downgrade()` has three ported callers acting on arbitrary deck cards:
`events/reflections.py:40` (registered `events/__init__.py:104`),
`events/welcome_to_wongos.py:90` (registered `events/__init__.py:135`) and
`powers.py:3171` (DampenPower, which downgrades every upgraded card in AllCards
IN COMBAT). One line each fixes them; `anointed`, `discovery`, `entropy`,
`gold_axe`, `prolong`, `scrawl`, `secret_technique` and `thinking_ahead` all
show the correct pattern of re-seeding the flag in `_init_vars`.

**A second, distinct downgrade defect the probe cannot see.** Three cards
override `AfterDowngraded` in C# specifically to restore a value the downgrade
would otherwise destroy, and all three are unported: `maul` (damage accumulated
from other Mauls' plays), `rampage` (damage accumulated from its own plays) and
`thrash` (damage absorbed from exhausted Attacks). C# tracks each total in a
private field — Rampage.cs:24-26 says why in a comment: *"Required so we can
restore the extra damage amount after a downgrade (ie Magiknight)"*. The sim
mutates `_damage` in place and tracks nothing, so `_init_vars` resets it. These
are LIVE through DampenPower, which downgrades **in combat**, exactly when the
accumulation exists. The probe misses them because it compares a FRESH card
against upgrade+downgrade and never plays the card. `wither` shows the fix
shape: it recomputes its damage from a re-seeded counter instead of mutating.

### 3.2 Gap G1's blast radius (block gained with `Unpowered`) — ONE ported card

```
unpowered-block: 3 C# card(s) gain block with Unpowered
  Entrench.cs [PORTED as card/entrench]: GainBlock(Owner.Creature,
      Owner.Creature.Block, ValueProp.Unpowered | ValueProp.Move, cardPlay)
  PillarOfCreation.cs [not ported]: 3m, ValueProp.Unpowered
  Shroud.cs        [not ported]: 2m, ValueProp.Unpowered
```

`creature_card_cmds` G1 — `BlockCmd.apply` gating the whole block-modifier
dispatch on `is_powered_attack` (cmds.py:145-147) — touches exactly
**card/entrench** among ported cards, which is the seam's own named witness. Two
unported cards would join it. Every one of the other 21 block-gaining cards
audited uses a plain `BlockVar(n, ValueProp.Move)` and is correctly doubled by
Vambrace on both sides, including the three largest: `the_gambit` 50,
`impervious` 30, `panic_button` 30.

### 3.3 Gap G4's blast radius (play count > 1)

```
sts2_rl/cards/colorless_skills.py:322  card.base_replay_count += self._replay   (Hidden Gem)
sts2_rl/potions.py:1072                card.base_replay_count += 1
sts2_rl/enchantments.py:167, 232       modify_card_play_count                   (Spiral, Glam)
sts2_rl/powers.py:966, 3919            modify_card_play_count
sts2_rl/relics/throwing_axe.py:30      modify_card_play_count
sts2_rl/cards/drum_of_battle.py:48     play_count = ...modify_card_play_count(self, None, 1)
sts2_rl/combat.py:469-470              play_count = ...(card, enemy, 1 + card.base_replay_count)
```

Two card units are in it. **`hidden_gem` is the SOURCE** — it raises another
card's `base_replay_count`, which the sim's normal play path correctly feeds
into the hook as `1 + base_replay_count`, matching C#'s
`GetEnchantedReplayCount() + 1`. **`drum_of_battle` is the one CONSUMER that
reads it wrong**, passing a bare `1` and so ignoring `base_replay_count`
entirely. Every other card is affected only passively, via Throwing Axe, Spiral,
Glam or the two powers — i.e. the blast radius is "any playable card", which the
seam's Throwing Axe + Pen Nib witness already pins.

### 3.4 Cards drawing on the unseeded shared RNG — 21 flagged, 13 real

```
shared-rng: 21 sim card class(es) touch combat._rng
  cinder · jackpot · seeker_strike · volley · alchemize · anointed · beat_down
  discovery · hidden_gem · jack_of_all_trades · splash · metamorphosis · havoc
  infernal_blade · mad_science · stoke · sword_boomerang · thrash
  distraction · rip_and_tear · true_grit
```

`CombatRng` already exposes the named parity accessors (`shuffle`,
`card_selection`, `targets`, `card_gen`, `energy`, `potion_gen`, `monster_ai` —
combat_rng.py:17-56), and in legacy mode they all alias the same shared
`random.Random`, so switching is behaviour-preserving for RL. Under a
string-seeded parity run each misuse is a stream desync.

**Eight are FALSE POSITIVES** — they branch on `crng.is_parity` and use the
named accessor, touching `combat._rng` only in the legacy branch:
`alchemize` (potion_gen), `cinder`, `thrash`, `true_grit`, `mad_science`'s Chaos
rider (card_selection / card_gen), `infernal_blade`, `stoke` (card_gen) and
`sword_boomerang` (targets). These are the reference implementations.

**Thirteen are real gaps**, by stream:

| Stream C# names | Cards |
|---|---|
| `Rng.CombatCardSelection` | `anointed`, `hidden_gem`, `seeker_strike` |
| `Rng.Shuffle` | `beat_down` (also missing StableShuffle's stabilising pre-sort) |
| `Rng.CombatCardGeneration` | `discovery`, `distraction`, `jack_of_all_trades`, `jackpot`, `metamorphosis`, `splash` |
| `Rng.CombatTargets` | `havoc`, `rip_and_tear`, `volley` |

### 3.5 Liveness guards C# does not have — 41 classes

`py audit/tools/card_probes.py dead-target-guards` lists 41 sim card classes
testing `is_gone` / `is_dead`. They fall into four kinds and only two diverge:

1. **`if ctx.player.is_dead: return` mid-card** — the sim bails between two
   effects where C# keeps going. Dormant everywhere: a genuinely dead player has
   already lost the combat on both sides (the sim floors a death-prevented
   creature at 1 HP, cmds.py:106-112). On `blood_wall`, `bloodletting`, `brand`,
   `hemokinesis`, `offering`, `thunderclap`.
2. **`if not target.is_gone:` before applying a POWER — a real divergence.**
   `Creature.CanReceivePowers` (Creature.cs:308-321) explicitly allows powers on
   DEAD creatures and refuses only for a REMOVED one. Ordinary kills agree (Kill
   removes the creature inside `CreatureCmd.Damage`, CreatureCmd.cs:409,
   523-525), but a corpse whose removal was vetoed
   (`ShouldCreatureBeRemovedFromCombatAfterDeath`; the sim's
   `retained_after_death`, cmds.py:100-104) stays powerable in C#. LIVE via
   **`card/vicious`**, whose ViciousPower draws on any Vulnerable its owner
   applies with no liveness test on the target (ViciousPower.cs:19-26; sim port
   powers.py:1160-1179). On `bash`, `break`, `fight_me`, `mad_science`,
   `mangle`, `squash`, `taunt`, `tremble`, `uppercut`.
3. **`if not target.is_gone:` before a STUN** — `card/whistle` only, and the same
   finding with a sharper observable: `CreatureCmd.Stun` has no liveness guard
   whatsoever (CreatureCmd.cs:870-903 is a bare `StunInternal` plus a VFX
   wrapper), and a retained corpse still takes turns, so the game skips that
   turn and the sim does not.
4. **`[e for e in enemies if not e.is_gone]`** — mirrors C#'s `HittableEnemies` /
   `where c.IsAlive`. Faithful. `card/breakthrough` is the one card that writes
   `is_dead` here instead, so an escaped-but-alive enemy is still struck
   (dormant — no ported monster escapes while a sibling lives).

`card/molten_fist` is the one member of family 2 that is FAITHFUL, because C#
writes the `IsAlive` test itself (MoltenFist.cs:38).

---

## 4. Live gaps, grouped by what they teach

### 4.1 A whole engine verb reimplemented or skipped

| Unit | Gap |
|---|---|
| **`havoc`** | The worst port defect in the pool. C# is one line (`AutoPlayFromDrawPile(..., 1, Top, forceExhaust: true)`); the sim reimplements the verb inline AND calls `card.on_play()` directly instead of `CombatState.auto_play_card`, skipping the entire play bracket (combat.py:441-513): `on_energy_spent` (so Free Attack — which `card/unrelenting` grants — never fires), `before_card_played`, the `modify_card_play_count` replay loop (a Spiral or Hidden-Gem'd card plays once instead of twice), the `before/after_attack` bracket (Akabeko's Vigor is not consumed), and `captured_x` (a Havoc'd `whirlwind` or `volley` does nothing). It also rolls the random target on `combat._rng`. `cascade` reimplements the same verb correctly and `howl_from_beyond` routes through `auto_play_card` — both are the fix shape. |
| **`debt`** | `HasTurnEndInHandEffect` and the whole `OnTurnEndInHand` gold loss are absent. The docstring's *"the sim has no gold"* is false: `RunState.gold` + `RunState.lose_gold` (run.py:335-337), and ported events spend gold routinely. |
| **`guilty`** | `AfterCombatEnd` absent, so Guilty never removes itself from the deck after 5 combats. *"The sim doesn't model the persistent deck"* is false — `RunState.deck` is it. |
| **`lantern_key`** | `ModifyUnknownMapPointRoomTypes` not overridden even though the sim's `Card` base HAS the hook (cards/base.py:296-299) and `spoils_map` already drives the same pipeline. *"The sim has no map"* is false. (`ModifyNextEvent` is dormant with a named blocker: no `modify_next_event` listener category and no WarHistorianRepy event.) |
| **`spoils_map`** | `BeforeCardRemoved` absent and the sim's `Card` base has no such hook, so removing Spoils Map at a shop during Act 2 leaves a dangling quest marker on the treasure node. `RunState.remove_cards` (run.py:356-358) is the ported removal verb. |
| **`maul`, `rampage`, `thrash`** | `AfterDowngraded` absent — see §3.1. |
| **`breakthrough`** | Hand-rolls its 1 HP self-loss (`p.hp = max(0, p.hp - 1)` + a bare `on_hp_changed`) instead of `DamageCmd`, so `on_damage_received` never fires and **`card/rupture`** does not trigger. Also skips the Intangible cap and Buffer. |
| **`primal_force`** | Bypasses `CardCmd.Transform`, swapping the hand slot directly, so no transform hook fires and an enchantment on the transformed Attack is destroyed. Dormant — the in-combat sibling of seam gap G3, which is live only for the deck case. |

Three of these "not modelled" claims rest on a **false premise about the sim's
own capabilities**. That is the single most transferable lesson from the stream:
a docstring asserting the sim lacks a subsystem is a claim to verify, not a
reason to stop.

### 4.2 Wrong quantity

| Unit | Gap |
|---|---|
| **`fisticuffs`**, **`omnislice`** | Both use `DamageCmd.deal`'s return value, which is `hp_lost`, where C# uses `DamageResult.TotalDamage + OverkillDamage` = blocked + hp lost + overkill (DamageResult.cs:64, Creature.cs:445-457) — the ENTIRE post-modifier damage. Fisticuffs against a 5-HP enemy hit for 7 grants 7 block in the game and 5 in the sim; against an enemy holding 10 block, 7 vs 0. Omnislice's splash is the same. |
| **`feed`**, **`hand_of_greed`** | Both Fatal cards drop the power-veto half of the test. C# requires `Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())` as well as `WasTargetKilled`. `MinionPower` vetoes unconditionally (MinionPower.cs:20-23) and `ReattachPower` unless every other segment is dead; both are ported, and MinionPower is applied by three ported monsters (Fabricator bots, Queen, Ovicopter eggs). `hand_of_greed`'s docstring asserts no power vetoes fatal — false. |
| **`drum_of_battle`** | Feeds a bare `1` into `modify_card_play_count` where C# feeds `GetEnchantedReplayCount() + 1` (CardModel.cs:1129-1132, 2015-2021), dropping `base_replay_count`. Hidden Gem + Drum of Battle pays twice in the game, once in the sim. |
| **`hidden_gem`** | The already-replaying filter checks only for a spiral/glam enchantment; C#'s `GetEnchantedReplayCount() < 1` returns `BaseReplayCount` on the null branch, so any already-replaying card is excluded. Two Hidden Gems can stack on one card in the sim (5 plays) where the game must pick two. |
| **`enlightenment`** | Writes a RELATIVE delta where C# registers an ABSOLUTE `LocalCostModifier` of 1 (CardEnergyCost.cs:197-203). They diverge once the card's base cost changes in the same turn, which `armaments` and `apotheosis` both do to cards in hand. `Card.set_cost_this_turn` is the right primitive and already exists. |
| **`frantic_escape`** | `AddThisCombat(1)` implemented as `self._energy_cost += 1`, mutating the BASE cost, which `reset_combat_state` never clears — the bump leaks into later combats. |

### 4.3 Wrong hook

| Unit | Gap |
|---|---|
| **`clash`** | `IsPlayable` routed through `should_play_card`. C# reads `IsPlayable` only in `CardModel.CanPlay` (CardModel.cs:1759-1762), the MANUAL path; `CardCmd.AutoPlay` checks only the Unplayable keyword and `Hook.ShouldPlay` (CardCmd.cs:57-71), neither of which Clash implements. So an auto-played Clash fires in the game regardless of hand contents, and the sim discards it unplayed. Four ported auto-play sources reach it: `beat_down`, `havoc`, `catastrophe`, `cascade`. Fix shape: `if auto_play: return True`. `enthralled` and `normality` show what a real `ShouldPlay` port looks like. |
| **`normality`** | Right hook, wrong counter: C# counts plays STARTED (`History.CardPlaysStarted`), the sim counts `CardPlayedEntry`, appended at the END of resolution. Play two cards then Havoc: C# blocks Havoc's auto-play (3 started), the sim allows it (2 finished). |
| **`mad_science`** | `GainsBlock` is TYPE-dependent in C# (`Type == Skill`) and never set at all in the sim, so Nimble refuses a Skill Mad Science. Notable because the parallel `base_block` type-dependence WAS handled. |
| **`feel_no_pain`** | Stores the POWER's block-per-exhaust amount in `_block`, the attribute `base_block` reads, so the sim reports a card granting 3 block on play. `cards/base.py:65-69` warns about this exact confusion by name. `eternal_armor` and `stone_armor` store the same shape correctly, in `_plating`. |

### 4.4 RNG stream and draw-count divergences

The 13 wrong-stream cards of §3.4, plus three draw-COUNT divergences at
auto-play and pile-add boundaries:

- **`catastrophe`** — the sim breaks its pick loop on combat-over; C# has no
  loop-level bail and does the StableShuffle pick BEFORE `AutoPlay`'s own
  `IsOverOrEnding` return, so C# burns a full StableShuffle per remaining
  iteration and the sim burns none.
- **`beat_down`** — the sim rolls its target INSIDE `auto_play_card`, after the
  playability check, while C# rolls before calling AutoPlay, so a hook-blocked
  play costs C# a draw and the sim none. (Dormant: BeatDown's own filter
  excludes Unplayable cards and no ported `ShouldPlay` preventer fires on an
  auto-played Attack.)
- **`metamorphosis`** — adds its generated Attacks at `CardPilePosition.Random`
  in C# (one CombatCardSelection draw each); the sim appends to the top of the
  draw pile and takes no draw at all, so the cards are scattered through the
  game's pile and stacked on top of the sim's.

### 4.5 Other live gaps

- **`anger`**, **`dual_wield`** — their copies are fresh instances, not
  `CreateClone` deep clones (CardModel.cs:1193-1216), so an enchanted card
  duplicates as vanilla. Live via Spiral (`enchantments.py:372-375` accepts any
  Attack; `events/spiraling_whirlpool.py:46` attaches it).
- **`bolas`**, **`thrumming_hatchet`** — share a return-to-hand helper that
  searches only draw and discard; C# returns the card from ANY non-hand pile via
  `CardPileCmd.Add`, so an EXHAUSTED copy never comes back. The two C# files are
  byte-identical, so the finding transfers verbatim.
- **`entrench`** — the entire ported blast radius of seam gap G1 (§3.2).
- **`aggression`, `apparition`, `hello_world`, `juggling`, `wish`** — the five
  downgrade-sticky keyword cards (§3.1).

---

## 5. Dormant gaps (pool-wide families)

Each is recorded per unit with the trigger that would make it live.

| Family | Count | Trigger that makes it live |
|---|---|---|
| **`-1` canonical cost mapped to 0.** `CardEnergyCost.GetWithModifiers` returns early on `_base < 0` (CardEnergyCost.cs:100-103), so the game's unplayable card is immune to every cost modifier; the sim runs a base of 0 through the full chain. `GetAmountToSpend()` clamps to 0 on both sides, so only READS diverge. | **29** unplayable curses/statuses/quests | Any effect reading an unplayable card's cost without a `> 0` filter. The three ported readers all filter (`mummified_hand.py:25`, `potions.py:168`, `event_cards.py:328`) and `infested_automaton.py:35` filters `pool_card_ids()`, which holds no curses/statuses/quests. |
| **A printed DynamicVar with no stored counterpart**, so `base_damage` / `base_block` / `base_hp_loss` / `magic_number` report the default and `full_env.card_features` (full_env.py:455-489) encodes the card wrongly for the policy. | **23** — 22 with the number MISSING, plus `feel_no_pain`, which stores a wrong one (§4.3) | Nothing for game fidelity — the dealt number is always right. Already LIVE for the RL observation encoder. |
| **`is_gone` liveness guards** (§3.5 families 2–3). | 10 | Already LIVE via `card/vicious`. |
| **Per-enemy AoE fan-out.** C# passes the whole valid-target list to ONE `CreatureCmd.Damage` call per hit (AttackCommand.cs:650), computing every DamageResult before any `Kill`; the sim issues one call per enemy, so deaths interleave. | 8: conflagration, dramatic_entrance, exterminate, howl_from_beyond, pacts_end, stomp, thunderclap, whirlwind | A ported monster whose on-death effect changes a sibling's incoming damage or block, or whose death spawns an enemy mid-attack. |
| **`CanBeGeneratedInCombat` mapped to the wrong flag** — the sim's `_ChoosableCurse` base sets `can_be_generated_by_modifiers = False`, which C# leaves true, and leaves the flag C# does override at its default. | 4: disintegration, mind_rot, sloth, waste_away (+ frantic_escape independently) | One base-class fix corrects all four. Live if an in-combat generator is pointed at a pool including statuses. Contrast `feed`, `hand_of_greed`, `hidden_gem`, `not_yet`, `soot`, which map it correctly, and `neows_fury`, which relies on rarity instead. |
| **`?.` after `PowerCmd.Apply`** — C# skips its follow-up call when Apply returns null; the sim re-fetches the power by id and cannot distinguish a zeroed apply from a successful one. | 3: crimson_mantle, inferno, toric_toughness | A ported power-amount modifier that can zero a self-applied BUFF (Artifact intercepts only debuffs). `the_bomb` is the INVERSE: C# uses a bare `.` and would throw where the sim safely skips. |
| **`if ctx.player.is_dead: return` mid-card** (§3.5 family 1). | 6 | A ported listener that acts after the player's death. |
| **`MinSelect 0` selection ranges** — C# prefs allow taking FEWER than the cap; the sim's fixed `count` cannot express a range. The min/max half of seam guard N10, at a card site. | 2: neows_fury, purity | A conformance replay of a run where the player declined part of a selection. |
| **`canSkip: true` not modelled** — `select_cards` always returns a card. | 2: discovery, splash | A replay command encoding a declined choice. |
| **Direct pile mutation instead of a pile verb**, so no `AfterCardChangedPiles` fires. | 2: anointed, neows_fury | The sim has no `after_card_changed_piles` listener at all; live once one is ported. |
| **`rend`'s ITemporaryPower exclusion** approximated by one class where C# has five implementers. | 1 | A negative TemporaryDexterity / TemporaryFocus / SleightOfFlesh on an enemy would inflate Rend by 5. |

The one **waiver** in 202 records is `card/alchemize`, whose entire OnPlay is
potion procurement — explicitly out of scope per the shared contract. Its record
still states that the sim uses the correct `combat_potion_generation` stream and
reproduces the create-then-maybe-drop ordering, so nothing hides behind it.

There are **5 deliberate-divergence ENTRIES across 5 units**, of which only 3
roll a unit up to `deliberate-divergence`; each spells out the same-observable
argument.

| Unit | dd entry | Unit rollup |
|---|---|---|
| `cascade` | guard: pull-phase pile bookkeeping | deliberate-divergence |
| `inflame` | OnPlay: `StrengthCmd` vs `PowerCmd.Apply` | deliberate-divergence |
| `prowess` | OnPlay: same `StrengthCmd` verb, first half | deliberate-divergence |
| `fight_me` | guard: both Strength applications routed through `StrengthCmd`, so the player's strength-given modifiers also run over the ENEMY's buff — which C# reaches via `ModifyPowerAmountGiven` anyway | **gap** (a gap elsewhere in the unit dominates) |
| `stomp` | AfterCardEnteredCombat: clone-seeding | **gap** (ditto) |

---

## 6. Cross-record disagreement (rule 3)

**`creature_card_cmds` guard G6 is labelled DORMANT and is actually LIVE.**

The seam's verdict (`gap`) is correct and is not disputed; only its dormancy
argument is. G6 reasons:

> Dormant: the two in-combat callers are Brightest Flame
> (cards/brightest_flame.py:37) and PaperCutsPower (powers.py:2959), neither of
> which reaches a fatal magnitude, and the isFromCard Move flag exists for cards
> that are not ported.

That covers two of the three consequences of not routing through the damage
pipeline (the kill, and the `Move` flag) and misses the live one:

- C# `CreatureCmd.LoseMaxHp` deals the overflow as real damage —
  `Damage(choiceContext, creature, CurrentHp - newMaxHp, isFromCard ?
  (Unblockable|Unpowered|Move) : (Unblockable|Unpowered), null, null)`
  (CreatureCmd.cs:826) — which fires `Hook.AfterDamageReceived`.
- The sim's `CreatureCmd.lose_max_hp` (cmds.py:179-189) only clamps HP and calls
  `on_hp_changed`.
- `RupturePower.AfterDamageReceived` (RupturePower.cs:44-57) applies Strength on
  ANY unblocked damage its owner receives, and its `cardSource == null` branch
  (line 48) is exactly the branch LoseMaxHp's null cardSource takes.
- **Rupture is ported**: `sts2_rl/cards/rupture_card.py`, power at
  powers.py:272-289, listening on `on_damage_received`.

Repro: play Brightest Flame at full HP holding Rupture. `newMaxHp < CurrentHp`,
so the game deals 1 damage and Rupture grants Strength; the sim grants none.
Both halves are ported Ironclad content.

Recorded as a guard entry on `audit/records/card/brightest_flame.json`.
**`audit/records/seam/**` is not edited** — this is for the seam owner to fold in. Note
that `card/breakthrough`'s independently-found gap has the same shape and the
same witness, which is corroboration rather than coincidence: any code path that
loses HP without going through `DamageCmd` is invisible to Rupture.

No other card-level verdict contradicts a prior record. Where a card sits in a
seam's blast radius, the card record cites the seam's verdict rather than
reaching its own (`armaments`, `headbutt`, `not_yet`, `purity`, `thinking_ahead`,
`true_grit`, `wish`, `dual_wield`, `secret_technique`, `brand`, `burning_pact`).

---

## 7. Roster problem: `card/sweep`

`py audit/tools/harness.py roster card` reports
`UNMATCHED card/sweep -> expected src\Core\Models\Cards\Sweep.cs`. **This is not
a name-resolution problem and `name_overrides.json` cannot fix it.**

- There is no Sweep card in the game. `src/Core/Models/Cards` has `LegSweep.cs`
  (2-cost Uncommon Skill, 11 block + 2 Weak), `SweepingBeam.cs` and
  `SweepingGaze.cs`, none of which is a 1-cost BASIC 4-damage all-enemies
  Attack, and **no BASIC card in the source targets AllEnemies** (checked by
  intersecting `CardRarity.Basic` with `TargetType.AllEnemies` over the whole
  Cards directory — the intersection is empty).
- `SweepCard` (sts2_rl/cards/sweep.py) is a **sim-only test fixture**: it is
  absent from `cards/pool.py`, so it is in no generation or reward pool, and its
  only consumers are the four multi-enemy routing tests at
  `test/test_multi_enemy.py:253-280` (imported at `test_multi_enemy.py:11`).
  Two further grep hits are NOT consumers, checked rather than assumed:
  `test/run.py:3` names "1 × Sweep (AoE)" in the demo's module docstring, but
  the demo's actual `DECK` (run.py:41-46) builds strike / defend /
  breakthrough / armaments / whirlwind / bash / anger / burning_pact and no
  sweep — the docstring is stale; and `test/test_driver.py:54` is the English
  verb ("Sweep seeds for a victorious run"), not the card. So removing the
  fixture would touch exactly one test file plus the two export lists
  (`cards/__init__.py:18,259`, `sts2_rl/__init__.py:76,266`).

Because `harness.validate_record` requires an existing `game_source` path, no
valid record can be written for it, so the pool is **202 auditable units plus
this one**. The fix belongs in `harness.py` (seam-owned): the roster should
exclude sim-only fixtures, or the harness should let a unit be marked
`no-counterpart` so it stops showing as unaudited work. Reported, not applied.

---

## 8. Lessons for `audit/tools/PROMPT.md`

The card stream does not own `PROMPT.md`. These are offered for the relic stream
to fold in and version-bump.

1. **The skeleton under-enumerates by design, and the prompt does not say so.**
   `harness.py list_overrides` matches `public\s+override` only
   (harness.py:51-55). Card models put almost everything behind
   `protected override`: `OnPlay`, `OnUpgrade`, `OnTurnEndInHand`,
   `CanonicalVars`, `CanonicalTags`, `ExtraHoverTips`, `IsPlayable`,
   `ShouldGlowGoldInternal`, `AfterDowngraded`, `HasEnergyCostX`. **Five of the
   fifteen units in batch 1 generated an EMPTY `hooks` map**, and a card like
   Bash — whose entire audit is its OnPlay and OnUpgrade — validates as complete
   with zero entries. Suggested text: *"The skeleton's `hooks` map lists only
   `public override` members. Before you start, add an entry by hand for the
   constructor and for every `protected override`. An empty or short `hooks` map
   is a bug in the skeleton, not a small unit."* Also note that interface
   members (`KnowledgeDemon.IChoosable.OnChosen`) and plain public methods
   (`SpoilsMap.OnQuestComplete`, `Wither.FakeUpgrade`) are invisible to the scan
   and carry real behaviour.
2. **Add "printed value vs modelled value" to the bug-class checklist.** 22
   cards declare a `DynamicVar` the sim never stores, inlining the literal at the
   use site. The dealt number is right, so a behaviour-only read passes it — but
   the sim's printed-number API (`base_damage`, `base_block`, `base_hp_loss`,
   `magic_number`, cards/base.py:191-220) then lies, and
   `full_env.card_features` encodes it into the RL observation.
   `card/feel_no_pain` is the sharp version: it stores a POWER's amount in
   `_block`, so the API reports a wrong number rather than a missing one.
   Checklist line: *"Every canonical var must have a stored counterpart, in the
   right slot — not just a correct number at the call site."*
3. **Add "downgrade round-trip" to the checklist.** Bug class 10 covers per-turn
   and per-combat reset timing but not upgrade→downgrade.
   `CardCmd.Downgrade` → `DowngradeInternal` rebuilds vars, cost AND keywords
   from canonical (CardModel.cs:2135-2148), and any port that mutates state on
   upgrade — or accumulates state during play — must be checked for restore.
   This found eight gaps across two distinct shapes (§3.1).
4. **Say what to do with presentation.** The prompt lists animation/SFX as out of
   scope but not how to record it. Giving each `TriggerAnim` / `HoverTip` /
   `VfxCmd` its own `waiver` entry drags the unit rollup to `waiver` (rule 4) and
   makes clean units look scoped-out — three otherwise-faithful cards rolled up
   `waiver` on nothing but animation triggers before this stream changed policy
   mid-batch-1. Recommend: name presentation inside the owning hook's rationale;
   reserve `waiver` entries for units where an out-of-scope area is the SUBSTANCE
   of the behaviour (`card/alchemize` is the only one in 202).
5. **`-1` is a sentinel, not a number.** `CardEnergyCost` short-circuits every
   modifier on `_base < 0` (CardEnergyCost.cs:100-103). Any port mapping a -1
   canonical cost to 0 silently makes the card modifiable. Worth a line under
   "numeric constants" — and note the X-cost exception, where
   `Canonical = ((!CostsX) ? canonicalCost : 0)` (CardEnergyCost.cs:86) makes 0
   correct.
6. **Prefer a pool-wide probe to N per-unit reachability claims.** Rule 5 demands
   execution behind any unreachability claim. Written per unit that is 200
   scripts; written once per QUESTION it is five functions that answer for all
   203 — and the downgrade probe found five gaps a static read misses. Tell
   agents to write the probe at the level of the question, not the unit.
7. **Verify docstring claims about the sim's own capabilities.** Three separate
   cards justify an unported hook with a false premise — `debt`'s "the sim has no
   gold", `guilty`'s "the sim doesn't model the persistent deck",
   `lantern_key`'s "the sim has no map" — and all three subsystems exist. A
   comment explaining why something is absent is a claim to check, and the check
   is one grep. Two more (`hand_of_greed`, `feed`) assert "no implemented power
   vetoes fatal" when two do.
8. **A "same mechanism" file is worth writing before batch 2.** Recurring
   mechanisms (the -1 cost, the inlined var, the `is_gone` guard, the AoE
   fan-out) want one paragraph reused verbatim across every unit. That satisfies
   rule 3 by construction instead of by memory, and it makes the report's
   grouping fall out for free.

---

## 9. Deliverables

- `audit/records/card/*.json` — 202 records, 0 invalid, 0 stale.
- `audit/tools/card_probes.py` — five reproducible pool-wide probes
  (`downgrade`, `dead-target-guards`, `unpowered-block`, `replay`,
  `shared-rng`), committed so every executed number here is re-derivable.
- This report.
- No engine code was touched: `sts2_rl/**` is unmodified and the suite is
  unchanged at 2476 passed / 31 xfailed.

**Highest-value fixes, in order** (all in the gap-fix stream's court, none
applied here): `havoc`'s bypassed play bracket; the three unported
`AfterDowngraded` overrides; the 13 wrong-stream RNG cards (the pattern is
already written eight times over in `alchemize`, `cinder`, `infernal_blade`,
`mad_science`, `stoke`, `sword_boomerang`, `thrash`, `true_grit`); `fisticuffs`
and `omnislice`'s block quantity; `feed` and `hand_of_greed`'s Fatal veto;
`clash`'s hook; `normality`'s counter; the five one-line downgrade re-seeds; and
the three false-premise omissions in `debt`, `guilty` and `lantern_key`.

---

## 10. Review fix pass

Applied after review of the completed tier. The review's own framing held up:
upgrade-value coverage 100 %, 0 false LIVE in 20 sampled entries, keyword census
202/202, all rollups correct, both waivers legitimate. These are five targeted
corrections, not a re-audit. Every count below was recomputed from
`audit/records/card/*.json`, not carried over.

### Fix 1 — six `faithful` entries were dormant gaps or rule-3 breaks

Found by a **census over all 924 `faithful` entries** for dormancy / unported
language, so the list is complete for that marker rather than sampled.

| Unit | Entry | Why it is a gap |
|---|---|---|
| `apotheosis` | guard, `AllCards` self-exclusion | The sim's `all_cards` has no Play pile, so the two sets differ when a POWER card is mid-play. Rule 1: "no ported card does this" is dormancy, not equivalence. Trigger: a ported Power card that auto-plays another card. **Rollup faithful → gap.** |
| `pillage` | guard, `player.hand[-1]` | The sim infers the drawn card from list order where C# reads Draw's return value. Trigger: a ported draw-time listener that adds to the hand. **Rollup faithful → gap.** |
| `omnislice` | guard, zero-damage early return | Wrote "Dormant:" verbatim while verdicting faithful. Trigger: a before/after-damage-received listener that fires on a 0 amount. |
| `expect_a_fight` | guard, skipped zero-energy gain | "No ported `modify_energy_gain` listener … so the two agree today" is a dormancy argument. The energy-side twin of `creature_card_cmds/N5`. |
| `neows_fury` | guard, `CardPileCmd.Add` | Rule 3: its own rationale said *"Same structural point as card/anointed's guard"*, and `card/anointed` carries `gap`. Also inside §5's "Direct pile mutation" family. |
| `thunderclap` | guard, mid-card `player.is_dead` | Rule 3: all five siblings (`blood_wall`, `bloodletting`, `brand`, `hemokinesis`, `offering`) carry `gap`, and §3.5 family 1 already files thunderclap with them. |

Each rewritten entry states the dormancy, names the concrete trigger and
cross-references the sibling record. Both rule-3 cases had been contradicting
this report as well as the sibling records.

**Recomputed tier** (`py audit/tools/harness.py validate` → 0 invalid):

| | before | after |
|---|---|---|
| gap entries | 143 | **149** |
| faithful entries | 924 | **918** |
| gap rollups | 107 | **109** |
| faithful rollups | 91 | **89** |

`deliberate-divergence` (5 entries / 3 rollups) and `waiver` (2 / 1) unchanged.

### Fix 2 — every probe citation was an unrunnable path

The `tools/audit/*` → `audit/tools/*` restructure left every card record naming
the old location. Swept all 202: **27 occurrences across 26 records** —
24 × `card_probes.py`, 2 × `name_overrides.json`, 1 × `PROMPT.md`. Text-only;
no verdict or reasoning changed. The same stale prefix appeared 7 times in this
report and is fixed here too, along with `audits/card/**` →
`audit/records/card/**` and `audits/seam/**` → `audit/records/seam/**`.

**Still broken, and not ours to fix:** the path is now right but the script is
not runnable — `audit/tools/card_probes.py:41` does
`from tools.audit.harness import DEFAULT_GAME_ROOT`, which raises
`ModuleNotFoundError: No module named 'tools.audit'`. `audit/tools/` belongs to
the tools stream.

### Fix 3 — `card/beckon`'s faithful rationale was false

It claimed `is_unpowered` "only steers `DamageCmd.deal`'s prop inference … so
the flag is never read". The flag has **nine** readers: `cmds.py:46-50`,
`powers.py:116, 1260, 1385, 1911, 3965`, `relics/the_boot.py:37`,
`previews.py:157`, `cards/thrash.py:44`.

The `faithful` verdict survives, and rule 5 wants the executed reason rather
than a false claim of no readers. Each site is independently unreachable **for
this card**:

- the three modifier readers are dispatched only inside
  `if is_powered_attack(props):` (cmds.py:56-58), and
  `is_powered_attack(CARD_HP_LOSS)` is `False` — `CARD_HP_LOSS` carries
  `UNPOWERED` (valueprops.py:38, 47-49);
- the two `before_attack` readers fire only from combat.py:476-479, gated on
  `card_type == ATTACK`; Beckon is a STATUS whose damage comes from
  `on_turn_end_in_hand`, not a play;
- `the_boot` returns at `dealer is not self.player or target is self.player`
  (the_boot.py:34-35) — Beckon deals dealerless damage to the player, so both
  disjuncts hold;
- `preview_card_damage` returns at `base is None` (previews.py:154-156); Beckon
  declares neither `_damage` nor `calc_damage`;
- `thrash`'s victim is filtered to ATTACK cards (thrash.py:58);
- the prop-inference branch needs `props is None`, and Beckon passes
  `CARD_HP_LOSS` explicitly (beckon.py:39).

### Fix 4 — report count drift (the ledger was right, the prose was stale)

Each re-derived here rather than taken on trust:

- **§5 `-1` cost family: 27 → 29.** 29 records cite `CardEnergyCost.cs:100-103`.
  Cross-checked against the source: 31 C# card models call `base(-N, …)`; `Void`
  is unported (there is no `card/void` record), leaving 30 ported negative-cost
  cards, of which `cascade` is the legitimate X-cost exception —
  `Canonical = ((!CostsX) ? canonicalCost : 0)` (CardEnergyCost.cs:86) makes the
  sim's 0 correct there. 30 − 1 = 29.
- **§5 inlined-DynamicVar family: 22 → 23.** 22 records carry the
  missing-stored-var shape; `feel_no_pain` carries the same family's sharper
  form (a WRONG number in the `_block` slot rather than a missing one) and is
  the 23rd. It stays listed in §4.3 as well, now cross-referenced.
- **§5's dd list omitted `card/fight_me`.** Corrected to a table: **5 dd entries
  across 5 units** — `cascade`, `inflame`, `prowess`, `fight_me`, `stomp` — of
  which only 3 roll up `deliberate-divergence`, because `fight_me` and `stomp`
  each carry a `gap` elsewhere that dominates. (The review said 4 units; it is
  5.)
- **§7's `sweep` consumer list — the review's two additions are NOT consumers,**
  which is why the list is now explicit about them rather than extended.
  `test/run.py:3` names "1 × Sweep (AoE)" in the demo's module docstring, but
  the demo's real `DECK` (run.py:41-46) contains no sweep — the docstring is
  stale. `test/test_driver.py:54` is the English verb ("Sweep seeds for a
  victorious run"), not the card. The four executable consumers at
  `test/test_multi_enemy.py:253-280` stand, plus the import at
  `test_multi_enemy.py:11` and the two export lists.

§1's result block was also stale on all four numbers and is updated.

### Fix 5 — rule 8 was vacuous: 0 test citations in 202 records

**18 added**, every path grep-verified before it was written; no test file was
touched and nothing was invented. Gaps with no obvious existing test were left
uncited.

| Count | Gap | Test |
|---|---|---|
| 13 | the wrong-stream RNG family (§3.4) | `test/test_rng_tripwire.py:33` — `test_no_wrong_stream_draws_in_random_run`, 20 seeded full runs asserting ZERO in-combat draws on `RunState.rng`. `CombatState` receives that same object as `_rng` (run.py:1146-1148, combat.py:88). **Executed:** playing this family's shape under a `Tripwire` produces a hit at the `card.on_play` frame (combat.py:490), so the gate really does cover these sites; it is green today because its 20 seeds never reach them. |
| 1 | `entrench` (seam G1's whole ported blast radius) | `test/test_hook_order.py:296-320` — a **strict** xfail that builds `make_card("entrench")` with a Vambrace. Flips to an unexpected pass the moment G1 is fixed. |
| 1 | `apotheosis` (premise only) | `test/test_hook_order.py:259-279` pins the `_playing_card` limbo the NON-Power half rests on. Labelled premise-only: the Power half — the actual divergence — is unpinned, which is exactly why it is dormant rather than equivalent. |
| 1 | `mad_science`'s unset `gains_block` | `test/test_shared_enchantments.py:52-61` — the existing Nimble / `gains_block` gate. No Mad Science case yet; the fix should add one there. |
| 1 | `feel_no_pain`'s `_block` slot | the same gate (it already asserts `not make_card("feel_no_pain").gains_block`) plus `test/test_ironclad_cards.py:666-669`, which pins the applied amount at 3. They bracket the fix. |
| 1 | `primal_force` (sibling half only) | `test/test_hook_order.py:345-365`, seam G3's DECK-case strict xfail. The in-combat case this record covers has no pin — which is why it is recorded at the card rather than deferred. |

### Verification

```
py audit/tools/harness.py validate      428 record(s), 0 invalid
py audit/tools/audit_status.py          card  203  202  0  0  109  1
py -m pytest test/ -q                   2521 passed, 38 xfailed
git diff --name-only main...audit-pipeline | grep "^sts2_rl/"   (nothing)
```

`sts2_rl/**` is untouched by this branch; the suite total moved from the
review's expected 2478 only because concurrent streams added tests — zero
failures, zero regressions.
