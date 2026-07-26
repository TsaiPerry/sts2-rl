# Relic content audit — batch 8 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b08` (based on `audit-relic` @ 4542c32f)
**Units:** the roster's `kifuda` … `lords_parasol` run (15)
**Probes:** `py tools/audit/relic_probes_b08.py` (16 probes, committed, re-runnable)

`py tools/audit/harness.py validate` → **66 records, 0 invalid**.
`py tools/audit/citation_check.py audits/relic` → **561 citations, MISSING 0, OUT-OF-RANGE 0**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 61 · invalid 0 · stale 0 · gaps 44 · unaudited 197`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; no engine code was touched.

---

## Units and rollup verdicts

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `kifuda` | **gap** | 3 | 4 |
| `kunai` | **gap** | 6 | 5 |
| `kusarigama` | **gap** | 7 | 5 |
| `lantern` | **gap** | 2 | 4 |
| `large_capsule` | **gap** | 2 | 7 |
| `lasting_candy` | **gap** | 6 | 6 |
| `lava_lamp` | **gap** | 4 | 5 |
| `lava_rock` | **gap** | 3 | 8 |
| `lead_paperweight` | waiver | 2 | 9 |
| `leafy_poultice` | **gap** | 2 | 7 |
| `lees_waffle` | **gap** | 3 | 6 |
| `letter_opener` | **gap** | 7 | 7 |
| `lizard_tail` | **gap** | 4 | 9 |
| `looming_fruit` | **gap** | 3 | 5 |
| `lords_parasol` | **gap** | 2 | 7 |

14 of 15 roll up to `gap`. Only `lead_paperweight` is clean (its worst entry is a
run-history telemetry waiver) — and it is clean because someone already did the
work of checking `mutate_pity`, `modify_hooks`, the blacklist and `canSkip`
against `CardFactory` line by line.

---

## LIVE gaps, with executed evidence

Fifteen. Every one is `py tools/audit/relic_probes_b08.py <probe>`.

1. **`lizard_tail` G2 — the relic silently fails on three ported death paths, and one of them ends the run.** `b08-lizard`: `CreatureCmd.kill` (cmds.py:192-207) calls `should_die` with no preventer, never fires `after_preventing_death` and fires no `on_damage_received`, so the port's deferred heal never lands: kill at 40/80 leaves **hp=1** with `_used=True, _heal_pending=True` (C#: hp 40), and one further point of damage then leaves the player **hp=0, dead**. Worse, `cards/breakthrough.py:49` calls `hooks.should_die(p)` after a hand-rolled self-HP-loss with **no HP floor at all**: Breakthrough (an `IRONCLAD_POOL` card) played at 1 HP with Lizard Tail held ends at `hp=0, is_dead=True, phase=combat_over`, Tail spent, where C# prevents the death and heals to 40. Ported triggers: `SandpitPower` (The Insatiable), `TheGambitPower` (`the_gambit`, in `COLORLESS_POOL`), Breakthrough.
2. **`lizard_tail` G1 — the heal is one HP too high, every time.** `b08-lizard`: at max_hp 80 a lethal hit ends at **hp=41** where C# gives 40 (81 → 41 vs 40; at 1 the cap masks it). C# heals from `CurrentHp == 0`; the sim's `DamageCmd.deal` floors a prevented death at 1 (cmds.py:109-113) and the port heals *by* 50% on top. The sibling `potions.py:1256` (Fairy in a Bottle) compensates explicitly — so this is a defect, not a house style.
3. **`lizard_tail` G3 — the charge is spent inside the predicate.** C# spends `WasUsed` in `AfterPreventingDeath`; the port sets `_used` inside `should_die`, so any caller using `should_die` as a pure query burns the relic (executed above via Breakthrough).
4. **`lizard_tail` G4 — Lizard Tail is spent while Fairy in a Bottle is held.** `b08-lizard`: listener order `['LizardTail','FairyInABottle']`, a lethal hit spends the **Tail** and leaves the fairy in the belt at hp=41; C#'s `Hook.ShouldDie` runs the whole early pass (FairyInABottle, the game's only non-mock `ShouldDie`) before the late pass (LizardTail, the game's only `ShouldDieLate`), so the Fairy is always spent first and heals to 24. **This contradicts `audits/seam/damage_pipeline.json` guard N4** — see the disagreement section.
5. **`lords_parasol` G1 — the free card removal is never taken, and the port's docstring says the game does not take it.** `b08-parasol`: entering a stocked merchant with the relic buys 7 cards, 4 relics and 3 potions for 0 gold and leaves `removal_used=False`; `LordsParasol.cs:102-107` buys `inventory.CardRemovalEntry` last with `ignoreCost: true, cancelable: false`. The deck ends at 17 where the game leaves 16 — every merchant room, every visit. Nothing needs building: `shop.py:343-353`'s `_buy` is complete and `purchase(ignore_cost=True)` already zeroes the cost.
6. **`lasting_candy` G1 — the every-other-combat Power card option is missing.** `b08-candy`: the second combat's MONSTER card reward is `['battle_trance','twin_strike','expect_a_fight']` with and without the relic; the game adds a fourth, always-Power option. The stub's premise ("a card-reward modifier that runs between combats") is false — `rewards.py:299-301` dispatches `modify_card_reward_options` over `run.relics`, and the same probe shows `silver_crucible` using it today. Second observable: the added card costs a rarity roll, an item pick and an upgrade roll on the Rewards stream that the sim never consumes.
7. **`lasting_candy` G2 — the `TotalFloor < 41` cluster is SEVENTEEN, not sixteen.** `b08-isallowed` (see the sweep correction below). Executed: `hasattr(Relic, 'is_allowed')` is False and at `total_floor=60` a bag containing `lasting_candy` still yields it, where `RelicGrabBag.RemoveDisallowedRelicsFromDeques` has removed it.
8. **`lava_lamp` G1 — a damage-free combat's card rewards are not upgraded.** `b08-lavalamp`: rewards come out `[('headbutt',0),('rampage',0),('colossus',0)]` with and without the relic, while the SAME sim hook with `silver_crucible` held yields all three at level 1. All three dropped pipelines (`after_room_entered`, `on_damage_received`, `modify_card_reward_options`) are live.
9. **`kifuda` G1 — Kifuda enchants nothing.** `b08-kifuda`: `add_relic('kifuda')` leaves all 10 deck cards at `enchantment=None` where the game attaches Adroit(3) to three. The stub's "no enchantments in the sim" premise is false — 17 enchantments are ported and the probe enumerates **12** live `run.select_cards("enchant", …)` call sites, four of them relics doing this exact shape. *Fix prerequisite, named:* `Adroit` itself is unported (`'adroit' in ALL_ENCHANTMENTS` → False), so this cannot be closed by editing `kifuda.py` alone.
10. **`leafy_poultice` G1 — the two transforms bypass the deck-add hooks.** `b08-poultice` (SP2 parity path): the Strike→`breakthrough` and Defend→`colossus` replacements arrive at `upgrade_level 0`, while `run.add_card` of the *identical* card yields 1 with `toxic_egg` (colossus, Skill) or `molten_egg` (breakthrough, Attack) held. So an Ironclad who owns an egg and then takes Leafy Poultice loses the egg's upgrade on both replacements. With `bing_bong` the deck stays at 10 across two transforms. = `creature_card_cmds` G3 at a new site.
11. **`leafy_poultice` G2 — the named `Transformations` stream is not drawn.** `b08-poultice`: `run.player_rng.transformations.counter` is **0 before and after** the pickup, where C# takes two `NextItem` draws (`CardTransformation(original)` sets no `Replacement`, so `GetReplacement(rng)` really draws — unlike `claws`). LIVE for RNG parity, dormant for RL.
12–14. **`kunai` / `kusarigama` / `letter_opener` G1 — a replayed card advances the per-turn counter by 1 instead of 2.** `b08-replay`: with Throwing Axe held, two plays leave the counter at **2** in all three cases — Kunai grants no Dexterity, Kusarigama deals no 6 damage, Letter Opener deals no AoE (`enemy_hp` 56) — where C# counts 3 and fires. = `hook_dispatch` G4 at three new sites; because the trigger is `% 3 == 0`, every later trigger in the turn is shifted by one play.
15. **`kusarigama` `AfterSideTurnEnd` — the reset is in the wrong turn-end slot, and a ported power exploits it.** `b08-kusarigama`: `end_turn` with `Stampede(2)` leaves `_attacks_this_turn=2` (C#: 0) and those 2 carry into the next turn. C#'s `AfterSideTurnEnd` is `turn_structure` step 64 (after the flush) and the auto-post-play phase is step 47; the port uses `on_player_turn_end`, which `hooks.py:297-301` documents as `BeforeTurnEnd` (step 48) — the **same** hook `StampedePower` uses to auto-play Attacks. The right slot, `after_player_turn_end`, exists and `relics/parrying_shield.py:24` uses it.

Plus three sim-only findings recorded as gaps because their observable is real:

- **`lees_waffle` N4 / `looming_fruit` N3 — `undo_after_obtained` gives back max HP but not the healed current HP.** `b08-maxhp`: a player at 40/80 who takes Lee's Waffle reaches 87/87 and the undo leaves **80/80** — 40 current HP retained; Looming Fruit leaves 71/80 — 31 retained. This defeats exactly the DETECTOR 3 act-boundary HP assertion the helper exists for. No C# counterpart (nothing un-picks a relic), so it is filed as a note on the sim's own machinery.

---

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `kifuda` G2 | `CardSelectorPrefs`' min-0/max-3 range and `Cancelable = false` vs `select_cards`' single fixed count | fixing G1 — today there is no screen to get wrong; the natural fix (copying `beautiful_bracelet`) inherits the simplification |
| `kunai` `BeforeSideTurnStart` | C# step 9 (pre-block-clear) mapped to the sim's step ~18 | = `turn_structure` step 9, which names Kunai: a `BeforeSideTurnStart` listener that reads block or energy, or an enemy-side one |
| `kunai` / `letter_opener` combat-boundary reset | C# clears the counter at a combat boundary, the sim only at a turn boundary | nothing — traced and executed clean (`b08-turn-reset`): the turn-start reset always precedes `on_card_played`. `art_of_war` shape, closed |
| `kusarigama` G2 | `HittableEnemies` vs `living_enemies()`, used as an **RNG population** | an effect that makes a *living* enemy untargetable — then `NextItem` picks a different index because `len(seq)` differs |
| `letter_opener` G2 | same set difference, used as an iteration | same, but milder: `DamageCmd.deal` applies the `should_allow_hitting` backstop (`cmds.py:50-51`) |
| `lantern` N1 | missing `AfterModifyingEnergyGain` companion | = `bag_of_preparation` N1 / `turn_structure` step 20 / `power_cmd` G4: porting any model that implements the companion |
| `large_capsule` N4 | the grab-bag pull cannot apply `RelicModel.IsAllowed` | granting Large Capsule after floor 41 (it is a Neow relic, so `total_floor` is 0 today), or porting a non-floor `IsAllowed` predicate |
| `lasting_candy` G3 | the `UnlockState.NumberOfRuns == 0` veto | a per-profile `UnlockState` with `NumberOfRuns`. **Not a waiver** — rule 1: "the sim has no such system" is a dormant gap, and unlocks are not one of the four waiver categories |
| `lasting_candy` G4 | the EARLY/LATE card-reward pass collapse | fixing G1 — this is a **fix-ordering constraint**, not a free-standing bug: the added Power option must exist before Glitter/Silken Tress/Silver Crucible/the eggs run |
| `lava_lamp` G2 | C# upgrades a `CloneCard`, the sim has no clone helper (class 17) | fixing G1 with a copy instead of an in-place mutation; the Late pass runs *after* Glitter/Silken Tress may have enchanted the option |
| `lava_rock` N4 | the `TryModifyRewards` / `…Late` pass collapse | a Late implementer that reads or rewrites `rewards.relics`; the only ported Late one is `driftwood`, whose domain is disjoint |
| `leafy_poultice` N1 | `LoseMaxHp` routes the excess HP through the damage pipeline | = `creature_card_cmds` G6. Neutralised here by arithmetic: `SetMaxHpInternal` re-clamps `CurrentHp = min(CurrentHp, MaxHp)`, so even `tungsten_rod` is washed out. Live via a relic whose `ModifyHpLost` changes run *state*, or a loss driving `newMaxHp` below 1 (C# kills, the sim floors at 1) |
| `lizard_tail` N1 | the port depends on `damage_pipeline` G4 | nothing — it is already live there. **Fix-ordering constraint:** move the heal to `after_preventing_death` before closing G4, or the relic becomes a no-op |

---

## Sweep correction: the `IsBeforeAct3TreasureChest` cluster is 17, not 16

`.superpowers/sdd/content-relic-sweeps.md` sweep B splits 20 `IsAllowed`
overrides into (a) 16 × `IsBeforeAct3TreasureChest`, (b) 3 player-count gates,
(c) `lasting_candy`, "gated on the Ironclad's `UnlockState` … likely a waiver,
but it needs the per-unit audit."

**Both halves of (c) are wrong as filed.** `LastingCandy.IsAllowed` has TWO
clauses: the unlock veto *and* `return RelicModel.IsBeforeAct3TreasureChest(runState)`
at `LastingCandy.cs:97`. It is bucket (a) *and* bucket (c), it is not a waiver
(rule 1), and the single-fix cluster is **17 relics**.

The cause is mechanical and worth carrying forward: `sweep-isallowed`'s regex is

```
public override bool (IsAllowed|IsAllowedAtNeow)\([^)]*\)\s*\{\s*(?:return\s+)?([^\n;]*)
```

— it captures only the **first statement** of the body. `py tools/audit/relic_probes_b08.py b08-isallowed`
brace-matches the whole body instead and prints 17 hits, with `lasting_candy`
flagged `<-- MULTI-CLAUSE` and the other 16 bare `return`s. It is the pool's
**only** multi-clause `IsAllowed`, so no other bucketing changes — the finding is
about the method, not a backlog of hidden units.

> **Sweep lesson (fourth over/under-report in this stream):** the previous three
> corrections were all *over*-reports caught before publication. This is the
> first **under**-report, and under-reports are more dangerous because nothing
> in the output looks wrong. A regex that reads one statement of a C# body should
> always be paired with a brace-matched confirmation pass over the same
> population.

---

## Cross-record disagreement (binding rule 3)

**`audits/seam/damage_pipeline.json` guard N4 calls the `ShouldDie` /
`ShouldDieLate` two-phase collapse "currently inert". It is not inert.**

N4's reasoning is sound for three of the sim's four `should_die` implementers —
`IllusionPower` (`powers.py:1566`), `SteamEruptionPower` (`:2016`) and
`AdaptablePower` (`:3365`) all guard `creature is self.owner` on enemies, so they
cannot collide with a relic that only vetoes the player's death. It misses the
fourth: **`FairyInABottlePotion` is ported** (`potions.py:1242`) and its
`should_die` vetoes for any player-side creature. `b08-lizard` executes the
collision — the sim spends the **Tail** and keeps the fairy; C# always spends the
fairy first, because the early pass is the fairy's and the late pass is the
Tail's, and those are the game's only two non-mock overrides of the pair.

Recorded as `lizard_tail` G4 (LIVE) and reported here per the ownership contract;
`audits/seam/damage_pipeline.json` is not mine to edit. The seam's own rule-3
note applies — the disagreement *was* hiding a live gap.

Two fix-ordering constraints also surfaced, of the kind batch 1 recorded for
`anchor` × `turn_structure` G1:

- `lizard_tail`'s port is **built on** `damage_pipeline` G4 (the killing-blow
  `AfterDamageReceived` skip the sim does not perform). Fixing G4 first makes the
  relic stop healing entirely. Move the heal to `after_preventing_death`
  (`hooks.py:596-601`) first — that single change closes G1, G2 and G3 too.
- `lasting_candy` G1 must land **with** the card-reward phase split (G4), not
  before it.

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file on the first try and
`tools/audit/name_overrides.json` needs no additions. Obtainability confirmed for
all 15 (`b08-pool`): 8 via the transcribed grab bag (`kifuda` Shop, `kunai` Rare,
`kusarigama` Uncommon, `lantern` Common, `lasting_candy` Uncommon, `lava_lamp`
Shop, `lees_waffle` Shop, `letter_opener` Uncommon, `lizard_tail` Rare), and the
rest via ported events — Neow (`large_capsule`, `lava_rock`, `lead_paperweight`,
`leafy_poultice`), Nonupeipe (`looming_fruit`, which is *also* a bag member at
Ancient rarity), Vakuu (`lords_parasol`).

---

## New bug classes and pool-wide shapes

Two candidate `PROMPT.md` classes, each with the unit that exhibited it. (Do not
bump the version header — that is the stream owner's call.)

**Class 19 — a port that reroutes an effect to a DIFFERENT hook inherits that
hook's callers, not just its timing.** Exhibited by **`lizard_tail`**. The port
declines `after_preventing_death` (which exists and which
`potions.py:1245` uses) and reroutes its heal through `on_damage_received` plus a
`_heal_pending` latch. That is not merely a timing slip: it makes the effect
depend on a *different event's* firing conditions, and there are three ported
paths where that event does not fire at all
(`CreatureCmd.kill`, `cards/breakthrough.py:49`, and any future ad-hoc
`should_die` caller). It also relocated the *charge*, so a pure predicate query
now spends the relic. **The check:** whenever a port implements C# hook A through
sim hook B, enumerate `grep`-wise every sim caller of B and every sim caller of
A, and diff the two caller sets — the divergence is in the difference, not in the
ordering. The sibling-comparison heuristic from class 12 applies too:
`fairy_in_a_bottle` uses the right hook and the right arithmetic, which is what
makes `lizard_tail` a defect rather than a house style.

**Class 20 — the sim's *own* compensating hacks must be compensated for at every
call site.** Exhibited by **`lizard_tail` G1**. `DamageCmd.deal` deliberately
floors a prevented death at 1 HP where C# leaves 0 (`cmds.py:109-113`, with a
comment saying so). `fairy_in_a_bottle` heals `heal_to - creature.hp` to absorb
that floor; `lizard_tail` heals the raw amount and is one HP high forever. Any
documented sim-side substitution creates a *silent* obligation on every consumer,
and the second consumer is where it gets missed. **The check:** when a sim
primitive's docstring says "the sim does X instead of the game's Y", grep every
caller and verify each one compensates.

Three shapes worth folding into the existing classes rather than adding new ones:

- **Class 9 (per-Replay iteration) is a POOL-WIDE shape for counter relics, not
  a one-off.** Three of this batch's fifteen units (`kunai`, `kusarigama`,
  `letter_opener`) are the same "every N cards of a type this turn" template and
  all three carry the same LIVE `hook_dispatch` G4 observable, on top of the two
  already recorded (`unsettling_lamp` G1, `pen_nib`). Every remaining relic that
  counts card plays per turn is a hit; a `sweep-cardcount` over
  `def on_card_played` implementers that increment a counter would enumerate them
  in one pass and is cheaper than five more batches.
- **Class 11 (the docstrings are evidence, not truth) extends to the TURN-END
  pair.** `hooks.py` correctly documents `on_player_turn_end` as `BeforeTurnEnd`
  and `after_player_turn_end` as `AfterTurnEnd`, and `kusarigama` still picked the
  wrong one — LIVE. The three ported relics that mix these up are worth a sweep:
  any relic whose C# hook is `AfterSideTurnEnd` but whose port uses
  `on_player_turn_end`.
- **Class 15 (paired hooks rarely carry the same guard set) CLEARED cleanly
  once.** `lava_lamp`'s two behavioural hooks carry the *same* `CurrentRoom is
  CombatRoom` guard. Recorded because the class fires often enough that a clean
  clearance is worth having on file, and because that shared guard is the concrete
  trap in the fix (the sim's `modify_card_reward_options` is also reached from
  `lead_paperweight`'s out-of-combat offer, which must NOT be upgraded).

## Left unverified / out of scope

- **Whether `cards/pool.py`'s `COLORLESS_POOL` is element-for-element the game's
  `ColorlessCardPool.GetUnlockedCards()`, and whether the `REGULAR` rarity-odds
  table matches.** Both are shared-table questions for the card stream, not
  `lead_paperweight`'s two files; `lead_paperweight` N6 says so explicitly. What
  *was* verified is that the relic passes the Colorless pool and RegularEncounter
  odds, and that three seeds' offers are all `COLORLESS_POOL` members.
- **`leafy_poultice`'s replacement CARDS are not pinned to a seed.** The transform
  pool and rarity filter were read and the ordering was executed, but no
  conformance seed was run, so "which card a real run gets" is untested — that is
  what G2 (the un-passed `Transformations` stream) makes untestable until fixed.
- **The three egg-relic upgrade witnesses for `leafy_poultice` G1 were executed
  through `add_card` as the control**, not through a live conformance replay.
- **`lasting_candy` G3's unlock clause was settled by reading, not by execution** —
  there is nothing to execute, because `grep` for `UnlockState`/`NumberOfRuns`
  over `sts2_rl/` returns nothing at all.
- **No engine code was touched and no gap was fixed.** `docs/audit/GAP-QUEUE.md`
  is the gap-queue stream's file; this report is its input.

**Commit:** `465e9e62` (`audit-relic-b08`).
