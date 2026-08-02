# Observation schema v4 — the integer/entity contract

The normative description of what the training environments emit: what each
segment is, which half it lives in, what the padding means, and why each size
is the size it is. Companion to `OBS_PLAN.md` (which is the *history* of the
observation design) and `RL_ARCHITECTURE.md` (the model side).

Executed from `prompts/entity-obs-schema.md`, phase 1. Progress and the
measurements behind every number here live in
`docs/superpowers/plans/2026-08-01-entity-obs-schema.md`, which is
authoritative if the two ever disagree.

> **Status: BOTH halves are IMPLEMENTED.** The COMBAT half (§5, §6) —
> `sts2_rl/full_env.py` (T4, 2026-08-02), pinned by
> `test/test_combat_obs_v4.py`. **Correction (T5a fix pass, 2026-08-02):**
> the RUN half — `sts2_rl/run_env.py` (T5a, 2026-08-02), pinned by
> `test/test_run_obs_v4.py` — is ALSO implemented; see §5A. The line
> previously here ("still SPECIFICATION, not yet implemented") was stale by
> the time of the fix-pass review.
> Every constant below traces to a measurement recorded in the ledger; nothing
> here is a guess. Where a number is *not* yet backed by a measurement it says
> so in the sizing table, rather than being quietly rounded up.
>
> **Correction (2026-08-02, StatusIntent card-count gap):** `full_env.
> OBS_SCHEMA_VERSION` moved **4 → 5** — the combat half's `enemies.f` row
> widened 24 → 25 to admit StatusIntent's displayed card count, which the T4
> build left out (§5.2's `enemies.f` row documents the field). This document
> keeps the "v4" name as the contract's historical identity (the way `OBS_
> PLAN.md` keeps its own era names) rather than being renamed on every later
> field addition; §4's sizing constants and §5's tables are the current
> source of truth regardless of the title's version number.

---

## 1. Why the flat `Box` had to go

Measured on the pre-change tree (`env_baseline.py`, and reproduced
independently three times):

| env | observation | bytes/env/step |
|---|---|---|
| `STS2FullCombatEnv` | 17,873 floats | 71,492 (69.8 KiB) |
| `STS2RunEnv` / `STS2CurriculumRunEnv` | 31,227 floats | 124,908 (122.0 KiB) |

Of the combat observation, hand card one-hots are 6,400 (35.8%), power triples
6,048 (33.8%), pile histograms 3,840 (21.6%) and enemy identity one-hots 864
(4.8%). **~96% of the payload is sparse categorical data written as dense
float blocks**; ~4% is genuinely numeric.

That single representational choice causes three separate problems — transport
cost, an inability to express two instances of one power, and a positional
action space that learns per-slot rather than per-card. A design that fixed
only one of them would be the wrong design.

---

## 2. The contract

```python
observation_space = spaces.Dict({
    "f": spaces.Box(0.0, 1.0, shape=(F,), dtype=np.float32),
    "i": spaces.Box(0, MAX_ID, shape=(I,), dtype=np.int32),
})
```

`reset()` / `step()` return `{"f": ndarray, "i": ndarray}`.

**Why a Dict of exactly two leaves**, rather than the alternatives:

- *Not* a single float array with integer-valued entries. float32 would in
  fact hold every id exactly (all indices are far below 2²⁴), so this would
  work — but it makes the declared `Box(0,1)` bounds a lie, and it leaves ids
  one careless normalization or `--zero-segments` ablation away from silent
  corruption. The type system should carry the distinction the encoder
  depends on.
- *Not* a deeply nested Dict (one key per entity kind). Every extra leaf
  multiplies the rollout-buffer, vec-env-transport and minibatch-indexing
  plumbing. Two leaves is the smallest split that keeps ids integral.
- Two leaves also leaves the door open for R12: the int half can drop to
  int16 (max id ≪ 32767) without touching the float half.

**Both halves keep a named `(segment, width)` map**, exactly as today —
`obs_segments()` / `obs_slices()` become `obs_segments_f()` /
`obs_segments_i()`. This is not cosmetic: `--zero-segments`,
`models._segment_plan`, `checkpoints.model_obs_segments` and the pin tests all
address the observation *by segment name*, and all of them keep working.

**Naming convention (uniform, no exceptions).** A logical block `name` splits
into `f"{name}.ids"` in the int half (width `cap × n_int`) and `f"{name}.f"` in
the float half (width `cap × n_float`). Always `.ids`, even where a row
carries a single int — an earlier draft of this document used `.id` for
one-int rows and `.ids` for multi-int rows, which would have made the lookup
rule in `ObsBuffer.write_rows` carry an exception for no benefit. The tables
in §5 use the uniform form.

### 2.1 Padding: `id == 0` means absent

Two rules, applied uniformly, remove the need for any separate mask array:

1. **Stored id = frozen-vocab index + 1. `0` is reserved for PAD.**
   `vocab.json` is untouched — index *i* still means the same id forever, and
   the append-only guarantee is unaffected. The `+1` lives at encode time.
   Embedding tables get `capacity + 1` rows with `padding_idx=0`, so an absent
   row contributes a zero vector to a masked sum-pool (the correct pooling
   semantics) and accumulates no gradient.
2. **A padded row is `id == 0` *and* all-zero floats.**

This preserves the one thing today's explicit presence bit buys: a power
*present at amount 0* (`id != 0`, amount float 0) stays distinguishable from a
power that is *absent* (`id == 0`).

### 2.2 What breaks, deliberately

`models.py`'s module docstring currently claims envs and the PPO loop are
untouched by architecture changes. **Phase 1 breaks that claim on purpose.**
The break is confined to one place: a `TensorObs` pair type implementing
`__getitem__` / `__setitem__` / `reshape` / `to`, so `obs_buf[t] = next_obs`,
`b_obs.reshape(...)` and `b_obs[mb]` in `train_torch.py` read unchanged. The
PPO mathematics is not touched at all.

Blast radius, established by reading rather than estimated:
`train_torch.py` — `obs_buf`, `next_obs`, `b_obs`, `b_obs[mb]`, `final_obs`,
and the two `get_value` / `get_action_and_value` call sites.
`vec_env.py` — `_EnvGroup.obs_dim`, `StepBatch.obs`, and the two
`np.concatenate` sites.

### 2.3 Overflow: truncate deterministically, never assert

Padded blocks have caps. Some of the underlying quantities are **unbounded in
principle** — `panache`, `automation` and `rolling_boulder` each add one
permanent power instance per play, with nothing in the engine or in C#'s
`List<PowerModel>` capping the list.

So an `assert len(rows) <= MAX` would convert a legal, if exotic, game state
into a training crash. Instead:

- **Keep the first N rows** of the source sequence. For powers that is
  `powers.values()`, i.e. C#'s application order, oldest-first — the same
  order `GetPower` / `FirstOrDefault` returns everywhere else in the engine,
  so the truncated view is a *prefix of the engine's own ordering* rather than
  an arbitrary subset.
- **Log loudly, once per process per block**, with the block name, the cap and
  the observed count.
- Set the block's `…overflow` float to 1.0 so the policy can at least see that
  its view is incomplete.

---

## 3. Vocabularies

Unchanged, and still governed by `vocab.py`'s two rules — frozen append-only
ordering persisted in `vocab.json`, and reserved *capacity* rather than live
count, so porting content appends rows instead of reshaping weights.

| kind | game total | capacity | status |
|---|---|---|---|
| cards | 577 | 640 | existing |
| relics | 298 | 336 | existing |
| powers | 260 | 288 | existing |
| monsters | 121 | 144 | existing |
| potions | 64 | 80 | existing |
| events | 68 | 96 | existing |
| purposes | (sim: 18) | 24 | existing |
| **afflictions** | **7** | **16** | **new** |
| **enchantments** | **22** | **32** | **new** |

Both new vocabularies are sized to the **game** total, not the ported count —
7 of 7 afflictions are ported, but only 19 of 22 enchantments are (`Inky`,
`Momentum`, `SlumberingEssence` are not). Sizing to 19 would force a schema
bump the day one of them lands, which is exactly the mistake `vocab.py`
exists to prevent.

`afflictions.py` has **no registry** today (unlike `enchantments.py`'s
`_ENCHANTMENT_CLASSES`). Phase 1 adds one, so the frozen vocabulary has a
deterministic source that does not depend on `__subclasses__()` import order.

---

## 4. Sizing constants

Every one of these traces to a measurement; the ledger holds the method.

| constant | value | evidence |
|---|---|---|
| `MAX_POWERS_PLAYER` | 32 | 1.1M samples: default deck peaks at **4**; adversarial power-stacked deck peaks at **28**; distinct-id ceiling ~30 |
| `MAX_POWERS_ENEMY` | 16 | enemies **never carry duplicate-id instances** in the current port; measured enemy max 4, static distinct ceiling 12–15 |
| `MAX_RELIC_ROWS` | 48 | ⚠️ **static argument only** — the empirical max reachable by masked-random is 6 (act-0 floor). Deep-run distribution not captured; see §7 |
| `MAX_COMBAT_CARDS` | 96 | draw+discard+exhaust+hand measured max 22 (act-0 floor); bounded by deck size + in-combat generation. ⚠️ also static beyond act 0 |
| `MAX_SELECT_CANDIDATES` | 96 | **correction (T5a fix pass):** set equal to `MAX_COMBAT_CARDS` — ⚠️ **static argument only**, not a measurement; the R4 census that would measure this properly is HELD on the user's instruction (see §7) |
| `MAX_HAND` | 10 | existing (`PlayerCombatState.MAX_HAND_SIZE`) |
| `MAX_ENEMIES` | 6 | existing |
| `MAX_POTIONS` / `MAX_POTION_SLOTS` | 3 / 10 | **correction (T5b):** `MAX_POTION_SLOTS` follows `MAX_POTION_ROWS`, below — see that row. `MAX_POTIONS` (3, `STS2FullCombatEnv`'s own belt default) is unrelated and unchanged |
| `MAX_POTION_ROWS` | 10 | **correction (T5b):** T5a flagged this as undersized (4) but left it, believing widening it out of scope. That deferral was a live CRASH, not just an undersized ceiling: `run_env.action_masks` writes one mask cell per ACTUAL belt slot `request.potion_actions()` yields, uncapped, so a run holding just the Potion Belt relic (a single COMMON, +2 slots) already grows the belt to 5 and raised `IndexError` the first time `action_masks()` ran with 5 AnyTime potions held. Widened to the exhaustive true worst case — base 3 + Phial Holster's 1 + Potion Belt's 2 + Alchemical Coffer's 4 (re-verified at source; each relic is unique and grants once) — same numeric value as `MAX_POTION_SLOTS`, sourced from one place (`full_env.py`); `run_env.MAX_POTION_SLOTS`/`N_COMBAT_ACTIONS`/`POTION_BASE`/`N_ACTIONS` are all references onto/derived from this constant, not independent declarations |
| `MAX_INTENT_HISTORY` | 3 | **new (R3, 2026-08-02, `monsters/base.py`)** — an exhaustive census of every `RandomBranchState.add_branch` call (state-machine monsters) plus every hand-rolled monster reimplementing the same primitive: deepest `cooldown` is 3 (`Flyconid`/`FakeMerchant`/`TwoTailedRat`), deepest `CAN_REPEAT_X_TIMES` is `max_times=2` (five sites), `CANNOT_REPEAT` is a 1-move window. `USE_ONLY_ONCE` excluded — a permanent flag, not a recency window, so no history depth recovers or needs to recover it. See §5.4. |

**Why the player and enemy power caps differ.** The census established that
only 5 ported powers can ever exceed one instance and *all 5 are player-side*;
the six enemy-side instanced powers are structurally one-per-creature. Sizing
both at 32 would spend 6 × 16 = 96 rows of padding on a case the engine cannot
produce. This is the single largest block in the combat observation, so the
asymmetry is worth its second constant.

---

## 5. Combat observation

> **T4 corrections (implemented in `sts2_rl/full_env.py`, 2026-08-02):** the
> tables below were edited post-implementation to match what was actually
> built, per the T4 brief §7. Each correction is called out inline rather
> than silently overwritten. No sizing constant or admissibility rule
> changed — only field order, block names, and two widths the plan-stage
> draft had wrong.

### 5.1 Int half

| segment | rows × fields | notes |
|---|---|---|
| `player.powers.ids` | 32 × 1 | vocab `powers` |
| `player.relics.ids` | 48 × 1 | vocab `relics` — **new**, the combat obs had no relic segment at all |
| `hand.ids` | 10 × 3 | `(card_id, affliction_id, enchantment_id)` — **correction:** one block named `hand`, not a per-slot `hand{h}` block; row *h* is hand slot *h* (positional) |
| `enemies.ids` | 6 × 1 | vocab `monsters`; was a 144-wide one-hot — **correction:** one block named `enemies`, not `enemy{e}.identity`; row *e* is enemy slot *e* (positional) |
| `enemy{e}.powers.ids` | 6 × 16 | one segment PER enemy slot (`enemy0.powers.ids` … `enemy5.powers.ids`), each 16 × 1 — kept per-slot, unlike `hand`/`enemies` above |
| `potions.ids` | 10 × 1 | **correction:** one block named `potions`, not `potion{p}`; row *p* is potion slot *p* (positional). **Final review fix-pass correction:** cap is `MAX_POTION_ROWS` (10, `full_env.py:312`), not 3 — this table pre-dates T5b's belt-widening fix (§4); §4's own row already said 10, so this table contradicted it. |
| `cards.ids` | 96 × 4 | `(pile_id, card_id, affliction_id, enchantment_id)` — **correction:** field order is `(pile_id, card_id, ...)`, not `(card_id, pile_id, ...)`. `ObsBuffer.write_rows(sort=True)` sorts by `(tuple(ints), tuple(floats))`; putting `pile_id` first in the int tuple is what makes that generic sort reproduce the canonical per-pile ordering. `pile_id` (`1`=draw, `2`=discard, `3`=exhaust) is a LITERAL, not a vocab index. See §5.3. |

### 5.2 Float half

Per-row floats accompany each int block at the same row index, so row *r* of a
block is `(ints[r], floats[r])`. Scalars keep the existing shared absolute
unit (fine `/100` + coarse `/500`) and the existing `_signed` mapping.

| segment | width | notes |
|---|---|---|
| `player.hp_ratio` / `hp_abs` / `max_hp_abs` / `block_abs` / `energy` / `strength` / `dexterity` / `pile_sizes` / `turn` / `incoming_post_block` / `cards_played_this_turn` / `attacks_this_turn` / `damage_taken` | 1+2+2+2+1+1+1+4+1+2+1+1+2 = 21 | the pre-v4 player scalar segments, **names and encodings unchanged verbatim** — **correction:** these are NOT one `player.vitals` block; each keeps its own pre-existing segment name (`--zero-segments` and the pin tests address them individually) |
| `player.powers.f` | 32 × 3 | `(amount_fine, amount_coarse, aux)` — `aux` carries the one per-instance numeric field beyond `amount` a handful of powers need. **Correction:** not just The Bomb's `damage` — five more ported `INSTANCED*` powers carry such a field (`toric_toughness.block`, `automation.cards_left`, `panache.cards_left` on the player side; `thievery.gold_stolen`, `withering_presence._cards_left` on the enemy side). See `full_env._power_aux`'s docstring for the full table and the two scaling buckets used. **Fix-pass correction (2026-08-02):** four more powers are admitted via their C# `PowerModel.DisplayAmount` override rather than the `INSTANCED*` sweep — `hardened_shell` (remaining absorb cap, ABS_SCALE bucket), `sloth` and `tender` (cards played this turn, /10.0 bucket), `slow` (displayed `SlowAmount * 10`, which lands in the /10.0 bucket because ABS_SCALE is 100). None of the four can ever produce more than one row for the same id — the admissibility test for `aux` is "the game displays it" (the same rule §6 already applies to relics), not "the power can multi-row"; `_power_aux`'s docstring corrects the narrower framing this document previously implied. |
| `player.relics.f` | 48 × 2 | `(counter/10, flag)` — see §6 |
| `hand.f` | 10 × 29 | **correction:** width is **29**, not left open-ended — the existing 24 card features (fields 0..23, unchanged) plus 5 new R2 fields: affliction amount, `exhaust_on_next_play`, `_has_single_turn_retain`, `_has_single_turn_sly`, and `base_replay_count` (the plan-stage draft named only 4 of these 5; `base_replay_count` is the 5th, added because the R2 census lists it among the player-visible per-instance state missing from the observation and this schema bump is paid once) |
| `enemies.f` | 6 × 25 | vitals + 9 intent flags + 6 intent-preview floats + 1 StatusIntent card-count float — **correction:** block is named `enemies.f`, not `enemy{e}.f` — one block, positional rows, not a per-slot block. **v5 correction (2026-08-02):** field 24 (status count) is NEW — `NIntent.cs:133-136` writes a displayed number for `StatusIntent` (card count) exactly as it does for `AttackIntent` (damage+hits), but only the latter was encoded; `intent.status_count` publishes `_clip01(count / 10.0)` (same bucket as the `hits` field; the C# source's `StatusIntent(N)` sites range 1..10) when the STATUS_CARD flag is set and the count is known, else 0.0 — 13 of the sim's 18 `StatusIntent` construction sites don't carry a count yet (`monster/_intent_count_lost`, a separate, already-tracked port gap), so this field reads 0.0 for those rather than fabricating a number. This was previously "unchanged contents" from v3; it no longer is. **Second v5-era correction (2026-08-02, no width change):** the ATTACK flag (field 9) and the 6 preview floats (fields 18-23) now also fire for a **death blow**. `DeathBlowIntent` is a `SingleAttackIntent` subclass in the game source, so `NIntent.cs:135`'s `is AttackIntent` test renders its damage number like any attack, and `MonsterModel.IntendsToAttack` (`MonsterModel.cs:241-245`) ORs `IntentType.DeathBlow` with `IntentType.Attack` for *gameplay* (it gates `GoForTheEyes.cs`). The sim's two `Intent(MoveType.DEATH_BLOW, ...)` sites lacked `also=(MoveType.ATTACK,)`, which was an **engine fidelity bug, not an observation bug** — Go For The Eyes was missing those two enemies entirely. Fixed at the intent sites (`monsters/underdocks/living_fog.py`, `waterfall_giant.py`); `full_env.py` and `previews.py` were correct as written and unchanged. |
| `enemy{e}.powers.f` | 6 × 16 × 3 | one segment per enemy slot (`enemy0.powers.f` … `enemy5.powers.f`), each 16 × 3 |
| `enemy{e}.intent_history.f` | 6 × 3 × 15 | **new (v6, R3, 2026-08-02):** one segment per enemy slot, `MAX_INTENT_HISTORY` (3) rows of 15 floats each, most-recent-first. No `.ids` half — see §5.4. |
| `damage_matrix` | 60 | unchanged, still aligned 1:1 with the play actions |
| `potions.f` | 10 × 1 | targeted flag — **correction:** block named `potions.f`, not `potion{p}.f`. **Final review fix-pass correction:** cap is `MAX_POTION_ROWS` (10, `full_env.py:350`), matching `potions.ids` above, not 3. |
| `cards.f` | 96 × 4 | **correction:** the four fields, named exactly: `(upgrade, effective_cost, affliction_amount, exhaust_on_next_play)`. This block deliberately does NOT carry `_has_single_turn_retain` / `_has_single_turn_sly` — those are hand-only state cleared by end-of-turn cleanup — but DOES carry `exhaust_on_next_play`, genuine per-instance state that survives the card leaving hand. |
| `player.powers.overflow`, `player.relics.overflow`, `hand.overflow`, `enemies.overflow`, `potions.overflow`, `cards.overflow`, `enemy{e}.powers.overflow` (× 6) | 1 each | **correction, made explicit per §2.3/T4 brief §3.5:** exactly these 12 blocks carry an overflow flag — every block with a `cap`. Set to `1.0` iff `ObsBuffer.write_rows` truncated that block this step. |

### 5.3 Piles — the hidden-information rule

**The draw pile's *order* is hidden and must stay hidden.** Its *composition*
is not: the player can inspect the draw pile in-game, and today's histogram
already exposes the full multiset. The risk phase 1 introduces is that an
integer list preserves order **for free**, handing the agent information the
real game never gives it.

The rule: the three non-hand piles share **one** block, and its rows are
**sorted canonically** before writing — deterministic and order-independent by
construction. **Correction:** the sort is not a hand-rolled key over that
exact field tuple; it is `ObsBuffer.write_rows(sort=True)`'s generic
`(tuple(ints), tuple(floats))` sort, i.e. `((pile_id, card_id, affliction_id,
enchantment_id), (upgrade, effective_cost, affliction_amount,
exhaust_on_next_play))`. This is why §5.1 puts `pile_id` before `card_id` in
the int tuple — the generic two-tuple sort reproduces the intended per-pile,
per-card-id ordering that way, with every remaining field breaking ties. The
result is still a pure function of the row's full content, so it is still
order-independent; only the exact field grouping (which tuple each field sits
in) differs from the plan-stage draft above.

One block rather than three, because `hand + draw + discard + exhaust` is
bounded by *cards in combat* — a single true invariant — where three separate
caps would be three separate guesses, each loose, and each able to overflow
while the others sat empty.

**Pinned by test**: shuffle any pile, rebuild the observation, and the bytes
must be identical. This is the non-leak test the deliverables require, and it
extends to R2's aux fields — an enchanted Strike and a plain Strike sort
differently, so the sort key has to include the aux fields or two distinct
multisets could collide.

### 5.4 R3 — per-enemy intent history (v6, 2026-08-02)

**Ships what §7's R3 entry previously said stayed deferred.** That decision
was made on COST grounds, not an admissibility objection — this section
records the sizing measurement that reopened it and the design that shipped.
§7 keeps the original deferral writeup in place (struck through in spirit,
not deleted) with a note pointing here, per this document's own convention
of correcting in place.

**What it stores, and why each field survives the admissibility rule
(§6's "decided by the game's own display path, not by usefulness"):** a
history SLOT holds exactly the fields the *current* intent already
contributes to the enemy row (§5.2's `enemies.f`) — the 9 `MoveType`
booleans (`intent_flags`, shared by both the current-intent encoder and the
history recorder so they can't independently drift) and the `StatusIntent`
card count, both already justified in §5.2's own row. The attack-preview
floats are **narrowed to 4 of the current row's 6**: `per_hit`, `hits` and
`total` (a pure function of the two numbers already co-displayed on one
icon) are kept; `post_block` is **excluded** — it is a derived combination
of a displayed number (damage) and the player's OWN block at that fleeting
moment, which a player reconstructs trivially in the instant but does not
retain as a discrete remembered fact the way "it hit me for 12" is retained.
Either choice is defensible (the brief that specified this section says so
explicitly); this is the one that shipped, and `monsters.base.
IntentHistoryEntry`'s docstring carries the same reasoning.

A history slot carries **no id** — there is nothing to look up, only the
facts above — so `enemy{e}.intent_history` has no `.ids` counterpart at all,
the first block in this schema with only a float half. Since a padded row's
usual tell (`id == 0` **and** all-zero floats, §2.1) needs an id that
doesn't exist here, each slot carries an explicit `recorded` presence float
(field 0) instead. Field layout (15 floats, `full_env._N_ENEMY_HISTORY_
SCALARS`):

| offset | field |
|---|---|
| 0 | `recorded` (presence) |
| 1–9 | `attack, defend, buff, debuff, status_card, summon, escape, heal, stun` (`intent_flags` order — `debuff` merges Debuff/DebuffStrong/CardDebuff, `stun` merges Stun/Sleep, exactly as the current-intent row does) |
| 10–11 | `per_hit` (`/ABS_SCALE`), `hits` (`/10.0`) |
| 12–13 | `total` (`_abs2`: fine, coarse) |
| 14 | `status_count` (`/10.0`) |

**Sizing `MAX_INTENT_HISTORY` = 3, by measurement, not by taste.** History's
value is recovering hidden state the current intent alone doesn't show:
repeat budgets and cooldowns (`sts2_rl/monsters/state_machine.py`'s
`RandomBranchState` — `cooldown` zeroes a branch's weight if it appears in
the last N *logged* moves; `CAN_REPEAT_X_TIMES(max_times)` zeroes it after N
in a row). A census of every `add_branch` call across every registered
monster (79 state-machine monsters plus the hand-rolled monsters that
reimplement the identical primitive via `weighted_branch_pick` —
`Flyconid`, `TwigSlimeM`) found:

- deepest `cooldown`: **3** — `Flyconid`'s `V_SPORES` (cooldown 3),
  `FakeMerchant`'s `ENRAGE` (cooldown 3), `TwoTailedRat`'s `SCREECH`
  (cooldown 3, `underdocks/two_tailed_rat.py`);
- deepest `CAN_REPEAT_X_TIMES` budget: **2** — `Knights`' SOUL_SLASH,
  `ScrollOfBiting`'s CHEW, `FlailKnight`'s FLAIL and RAM, `HunterKiller`'s
  PUNCTURE, `FossilStalker`'s repeated move;
- `CANNOT_REPEAT` is a 1-move window by definition;
- `USE_ONLY_ONCE` is **excluded from this measurement on purpose** — it
  gates on "has this move ever happened this combat" (a permanent flag),
  not a recency window; no bounded history depth reconstructs it, and none
  is expected to.

3 is therefore the deepest window any ported repeat/cooldown gate needs to
be reconstructable from what the player has actually seen; a larger N would
be dead weight. (Everything else in every other `add_branch` call ships at
the library default, `CAN_REPEAT_FOREVER`/cooldown 0 — no history window at
all.) The full citation, with file:line-level detail, lives in
`monsters/base.py`'s `MAX_INTENT_HISTORY` docstring.

**Cost check** (the brief's own gate, §1's motivating table style): `MAX_
ENEMIES(6) × MAX_INTENT_HISTORY(3) × 15 = 270` floats, **19.2% of the
pre-R3 combat `f_dim`** (1407 → 1677) — comfortably under the 50% ceiling
that would have required stopping to report rather than implement. `i_dim`
is unchanged (606) — no ids added.

**Correctness rules, each pinned by a mutation-checked test
(`test/test_intent_history.py`):**

1. **Keyed by `net_id`, not row position.** `CombatState._intent_history`
   is a `dict[net_id, deque(maxlen=3)]`; the observation writer re-resolves
   `net_id` from whichever creature currently occupies a row on every
   build. Verified against a REAL reordering encounter — `LivingFog`'s
   BLOAT move spawns a `GasBomb` that is inserted ahead of it in the enemy
   list — not a synthetic scenario.
2. **Recorded once per player turn, at exactly one hook.** `CombatState.
   _roll_enemy_intents` — the player-turn-start pass that rerolls every
   enemy's intent — snapshots each living enemy's *about-to-be-replaced*
   `current_intent` into its history the instant before rerolling it, and
   only if `enemy.performed_first_move` (i.e. it has already had a whole
   turn's worth of display, not merely been rolled). This is the same
   method that already owns "what does this enemy show next"; recording
   inside `current_intent` itself would fire on every read (including
   mid-turn observation builds) and record values never held for a full
   turn, and recording after the reroll would record the NEW intent
   instead of the superseded one.
3. **No phase-epoch machinery.** A previously-displayed intent stays a true
   historical record even after a moveset change (a monster's phase
   transition, a stun) — nothing invalidates or re-tags old entries.
4. **Padding is explicit, not positional.** `recorded` is a real field, not
   inferred from all-zero floats — the exact defect class §2.1 exists to
   prevent. A gone/absent enemy slot reads **fully unrecorded** at
   observation-build time (matching how `_enemies_rows` already blanks that
   row's current fields) even though the *internal* buffer is deliberately
   NOT cleared on death (a revived creature keeps its history) — the two
   are different data with different lifetimes, on purpose.
5. **Order is most-recent-first**, `deque.appendleft` — pinned directly by
   test, mutation-checked (an `append`-instead-of-`appendleft` mutant fails
   the ordering assertion).
6. **Resets per combat.** `_intent_history` is instance state on
   `CombatState`, constructed fresh in `__init__`; verified explicitly
   against the SAME `net_id` recurring in a brand-new combat (the counter
   restarts at 1 every time), which a dict scoped incorrectly (e.g. a class
   attribute, or accidentally shared across resets) would fail.

**No `.overflow` flag on this block** — alone among every capped block in
this schema. Every other overflow flag guards a real, externally-sized game
quantity that *could* exceed its cap (powers, relics, cards, ...); this
buffer is a `deque(maxlen=MAX_INTENT_HISTORY)` the recorder itself
maintains, so it is physically incapable of holding more than the cap.
§2.3's "truncate rather than assert" framing has nothing to truncate here.

---

## 5A. Run observation (v7)

> **Added (T5a fix pass, 2026-08-02):** this section describes
> `sts2_rl/run_env.py`'s `STS2RunEnv` at the same level of detail as §5
> describes the combat half — it did not exist when §5 was written because
> the run half was still spec. Pinned by `test/test_run_obs_v4.py` (66
> tests). Absolute sizes as built: `f_dim` = 4434 floats, `i_dim` = 1464
> ints, 23,592 bytes/env/step (float32 + int32). **Final review fix-pass
> correction:** these figures pre-date the potion-belt widening
> (`MAX_POTION_SLOTS`/`MAX_POTION_ROWS` 4 → 10); re-measured directly on the
> finished tree (`run_obs_layout().f_dim`/`.i_dim`) rather than assumed.
>
> **Correction (defect fix, 2026-08-02, `RUN_OBS_SCHEMA_VERSION` 7 → 8):**
> the figures above are now stale a second time, and by a different cause —
> this env's observation EMBEDS the combat block verbatim (§5A's own next
> paragraph: `full_env.combat_obs_segments_{f,i}()` folded in under a
> `"combat."` prefix), so §5.2's v5 `enemies.f` widening (24 → 25 floats,
> the StatusIntent card-count field) propagated into this env's `f_dim` too:
> **`f_dim` = 4440** floats (+6 = 6 enemy slots × 1 new float), `i_dim`
> unchanged at 1464 ints, **23,616 bytes/env/step** (`(4440 + 1464) × 4`).
> `RUN_OBS_SCHEMA_VERSION` was bumped 7 → 8 to restore "one version number,
> one `(f_dim, i_dim)` contract" — it had briefly stayed 7 across the width
> change, which is the defect this correction records, not a further layout
> change of this module's own. Pinned by
> `test_run_schema_version_matches_declared_dims` in `test/test_run_obs_v4.py`.
>
> **Correction (R3, 2026-08-02, `RUN_OBS_SCHEMA_VERSION` 8 → 9):** §5.4's
> per-enemy intent history embeds through the same `combat.*` fold, widening
> `f_dim` by `MAX_ENEMIES(6) × MAX_INTENT_HISTORY(3) × 15 = 270`: **`f_dim`
> = 4710** floats, `i_dim` unchanged at 1464 ints, **24,696 bytes/env/step**
> (`(4710 + 1464) × 4`). Bumped in the SAME change this time — the v8
> correction above exists precisely because that discipline was missed once
> already.

The run observation is **one `ObsLayout`/`ObsBuffer`** (`run_obs_layout()`):
this module's own segments (`run_obs_segments_f`/`_i`, below) followed by
`full_env.combat_obs_segments_{f,i}()` folded in verbatim under a
`"combat."` name prefix — outside combat every `combat.*` row reads PAD
id / zero float, exactly as `ObsBuffer.reset()` leaves it (§2.1).

**Always-visible run state** (every phase, not just one decision):

| segment | shape | notes |
|---|---|---|
| `phase` | `N_PHASES` floats | one-hot over `DecisionKind` — not a vocab.py vocabulary, kept a plain float one-hot (§2.2) |
| `run.hp_ratio` / `hp_abs` / `max_hp_abs` | 1 / 2 / 2 | unchanged pre-v7 encodings |
| `run.gold` | 2 floats, R6 log1p | `(fine, coarse)` — `GOLD_LOG_FINE_DENOM=800`, `GOLD_LOG_COARSE_DENOM=8000`; **T5a fix-pass retune** — see the note at the end of this section |
| `run.act` / `run.floor` | 3 / 1 | act one-hot, floor `/50` clipped |
| `run.potions` | `MAX_POTION_SLOTS`(10) × (1 id, 2 floats) | R1-shaped rows: `(present, slot_exists)`; positional by belt slot, `sort=False`. **Final review fix-pass correction:** `MAX_POTION_SLOTS` is 10 (`run_env.py:208`, following `MAX_POTION_ROWS` post-T5b), not 4 — this row pre-dates that widening. |
| `run.deck` | `MAX_DECK_ROWS`(96, = `MAX_COMBAT_CARDS`) × (4 ids, 4 floats) | R2 card-instance rows (`_run_card_row`), `sort=True` — a multiset, not hidden order, but sorted so the block is canonical the same way `cards` is in combat |
| `run.relics` | `MAX_RELIC_ROWS`(48) × (1 id, 2 floats) | R1 rows via `relic_obs.relic_row(in_combat=False)`, acquisition order, `sort=False` |
| `run.boss` | `MAX_BOSS_IDS`(4) × 1 id (zero-width `.f`) | the act boss's `monster_classes`, known from act entry like the boss icon; `next_boss_encounter` switches under DoubleBoss |
| `run.map.grid` / `run.map.meta` | `MAP_GRID_ROWS`(15) × `_MAP_WIDTH` × `MAP_GRID_NODE` / 2 | the WHOLE act map, visible every step like the map screen — unchanged floats (topology, not a frozen vocabulary), §2.2 |

**Phase-specific blocks** (populated only when `request.kind` matches; PAD/zero otherwise):

| phase | segment(s) | notes |
|---|---|---|
| `MAP` | `map{m}` (× `MAP_SLOTS`=7) | the CURRENT decision's 1-ply option preview, action-aligned; distinct from the always-visible `run.map.grid` above |
| `EVENT` | `event.present/page/ids`, `event.options` | `event.ids` is a single scalar id (no cap to overflow, so a direct write not a `write_rows` call) |
| `SHOP` | `shop.cards`(7) / `shop.relics`(3) / `shop.potions`(3) / `shop.removal` | id+float rows, R6 log1p costs (`SHOP_COST_LOG_DENOM=900`, T5a fix-pass retune); unstocked slots are explicit PAD rows (positional, `sort=False`) |
| `REWARD_CARD` | `reward.cards`(3) | R2 rows (`_run_card_row`), positional — an unresolvable card id becomes an explicit PAD row IN PLACE, never a dropped/shifted slot (§2.1) |
| `REWARD_POTION` | `reward.potion.ids/.f` | single scalar id + presence float |
| `SELECT_CARDS` / `SELECT_OPTION` | `select.purpose.ids`, `select.count`, `select.skippable`, `select.candidates`(`MAX_SELECT_CANDIDATES`=96) | `select.candidates` is the ONLY other sorted run-level block besides `run.deck` — `from_draw` candidates arrive in draw-pile order, which the real game's own select screen does not show either (confirmed at source, `NCombatPileCardSelectScreen.UpdatePileContents`); `_sorted_candidate_order` computes the identical sort key independently, capped and id-filtered exactly like the write, so the two can never disagree (R4's action-space seam, T5b) |

**Overflow flags**: `run.potions`, `run.deck`, `run.relics`, `run.boss`,
`select.candidates` each carry a `.overflow` float (§2.3) — every run-level
block with a cap.

**Padding invariant guards (T5a fix pass):** `run.deck`, `select.candidates`
and `run.relics` SKIP a row whose id cannot be resolved to a vocab index
rather than writing a PAD id with live floats; `run.boss` skips rather than
appending a PAD row (which would otherwise waste one of only `MAX_BOSS_IDS`
slots and shift later ids); `reward.cards` is positional, so it substitutes
an explicit all-PAD row in place instead of skipping. Unreachable via real
content today (every vocab index is built from the same registry every real
id comes from) — restored because a spec that only holds "as long as nothing
drifts" isn't holding the invariant, it's assuming it.

**R6 log1p retune (T5a fix pass):** the constants first shipped
(`GOLD_LOG_FINE_DENOM=300`, `GOLD_LOG_COARSE_DENOM=3000`,
`SHOP_COST_LOG_DENOM=2000`) moved R6's original defect rather than removing
it — the fine gold channel saturated at exactly 300g (every value at or
above it read identically 1.0), and the coarse channel saturated at 3000g,
so a genuinely hoarding run had no resolution at all above that. Retuned to
800 / 8000 / 900 respectively so the fine channel resolves further into a
normally-shopping range and the coarse channel resolves the whole "a few
thousand gold" hoarding ceiling with headroom; the shop/removal denom
trades off a hard mathematical constraint (a single log1p denom cannot both
spread a narrow price band across all of `[0,1]` and keep an unbounded
quantity resolvable arbitrarily far out) toward more spread while keeping
500g-vs-800g removal comfortably resolvable. All three remain **reasoned
defaults, not measurements** — no act-0 census reaches these balances or
prices (§7) — pinned by `test_gold_realistic_band_resolves_without_plateau`
and `test_shop_cost_realistic_band_spreads_more_than_the_old_defect`.

---

## 6. Relics (R1)

New in both observations. The combat observation had **no relic segment at
all**; the run observation was a presence-only 336-wide multi-hot.

Row: `(relic_id, counter, flag)`. The census established this is exactly
sufficient — no relic carries two simultaneously-*visible* counters — and that
both aux fields are load-bearing, because the flag is not derivable from the
counter (`toy_box` displays `combats_seen % 3` while used-up needs `>= 12`).

**Admissibility is decided by the game's own display path, not by usefulness.**
A relic's state enters the observation only if it is drawn on the relic icon:
`NRelicInventoryHolder.RefreshAmount` (`NRelicInventoryHolder.cs:116-119`),
gated on `RelicModel.ShowCounter`, which `RelicModel.cs:347` defaults to
`false` — display is strictly opt-in per relic. Status tinting
(`RelicModel.cs:487-503`) and `IsUsedUp`'s hovertip (`:365-369`) are the only
other paths. Of 259 relics, **70 carry mutable state; 32 expose a counter and
~18 a flag.** The other 189 are fully described by presence alone.

Three implementation rules, each of which would otherwise leak silently:

1. **Publish the *displayed* value, never the raw attribute.** Seven relics
   store a cumulative count the UI only ever shows modulo something —
   publishing `fishing_rod`'s raw counter would reveal total combats fought
   this run. Three more display an inversion (`N − x`), and `paels_tooth`
   displays a `len()`.
2. **Ten counters are in-combat-only** (they gate `ShowCounter`/`DisplayAmount`
   on combat being in progress) and must read 0 in the run observation.
   **Correction (T5a fix pass):** this table originally said "eight" —
   `relic_obs._IN_COMBAT_ONLY_COUNTERS` holds ten; `brilliant_scarf` and
   `paels_legion` are the two additional relics (see that module's own
   docstring, which already documented "the eight — now ten" correction).
3. **20 relics are fully excluded, plus a second attribute on 9 more, are
   excluded outright** (`relic_obs.EXCLUDED_RELIC_STATE`: 29 keys, 36
   attributes total — **final review fix-pass correction:** this point
   previously said "16 relics and 11 second-attributes"; `test_combat_obs_
   v4.py:466` already said 29). That list is the non-leak test's fixture,
   not just documentation. The two that matter most: `fur_coat.marked_coords`
   is *future map knowledge*, and `dusty_tome.ancient_card` names a card the
   player has not been shown.

---

## 7. Known gaps in the evidence

Recorded here rather than smoothed over, because a spec that hides its soft
spots is worse than one that names them.

- **Every empirical census is an act-0 floor.** A masked-random policy dies in
  act 0 — across 300 seeds on each run-scale env, `max_act` was 0 every time
  and the best floor reached was 13. So `MAX_RELIC_ROWS` and
  `MAX_COMBAT_CARDS` rest on static arguments, not on observed deep-run
  distributions. Both are generously sized and both truncate rather than
  assert, so the failure mode is a degraded view, not a crash — but they
  should be re-validated once a trained policy can reach act 2.
- **`MAX_SELECT_CANDIDATES` IS 96** (§4). **Correction (2026-08-02): the R4
  census is no longer held — it was run, and it settles the value at 96.**
  Measured max over 400 masked-random episodes on `STS2CurriculumRunEnv`: **17
  candidates, by floor 13 of act 0.** That is an act-0 floor, not a ceiling
  (same limitation as the bullet above), so the census can *refute* a smaller
  cap but cannot *certify* 96 — which is exactly what it was asked to do. A
  proposal to cut the cap to 32 was **rejected on this evidence**: ~25
  event/relic/shop/rest-site sites pass the ENTIRE current deck as candidates
  (`remove`/`upgrade`/`enchant`/`transform` — the shop removal service,
  rest-site Smith, `Astrolabe`, `Biiig Hug`, `Gnarled Hammer`, ~20 events),
  nothing in the engine caps deck size (`run.deck` is a plain list with no
  guard), and masked-random play — which takes almost no card rewards — is
  already at 17 inside the first of four acts. A real policy crosses 32 well
  before the midgame, and the cost lands hardest on the largest-deck (most
  successful) runs. So 96 remains a **static argument**, but the failure mode
  below is now quantified rather than merely asserted. Unlike
  `MAX_RELIC_ROWS`/`MAX_COMBAT_CARDS`, the "truncate rather than assert,
  so the failure mode is a degraded view, not a crash" framing above does
  **not** hold for this cap once T5b (R4) wired the SELECT_CARDS action
  block onto the SAME cap (`run_env.py`'s `_translate`/`action_masks`,
  `SELECT_BASE`): overflow here does not just degrade the observation, it
  makes a real, choosable candidate unclickable — an action-space narrowing,
  by `action_masks`' own comment (the SELECT_CARDS branch, `run_env.py`, ~ll.
  850-866) — which is strictly worse than a degraded view and something the
  actual game never does. Unreachable at today's content census (§4), but
  the gap in the evidence is real.
- **R3 (intent history) is not in this spec.** ~~The slot-stability census
  found that enemy rows are addressed by raw list position and that three
  encounters (`ovicopter_normal`, `fabricator_normal`, `living_fog_normal`)
  move a live enemy's index mid-combat, so any history buffer must be keyed
  on `net_id` — and it additionally goes stale, with no index change at
  all, for ~9 phase-changing monsters. That is materially more machinery
  than the prompt assumed.~~

  **Superseded (2026-08-02): R3 shipped — see §5.4.** The cost argument
  below was re-run with an actual measurement (§5.4's census settles
  `MAX_INTENT_HISTORY` at 3) rather than an estimate, and the resulting
  width (270 floats, 19.2% of the pre-R3 combat `f_dim`) came in well under
  the cost ceiling that would have blocked it. The `net_id`-keying
  requirement this bullet identified was real and is exactly what §5.4's
  rule 1 implements and tests against a live reordering encounter; the
  "goes stale for ~9 phase-changing monsters" concern is addressed by §5.4
  rule 3 (a displayed intent stays true history regardless of a later phase
  change — no phase-epoch machinery needed, matching this document's own
  "what survives" paragraph below). The analysis in the rest of this bullet
  (why a move-id substitute is inadmissible, and the repeat-on-consecutive-
  turns census) is left in place because it is still correct and is what
  the shipped design's field selection rests on — only the final "modest
  value at unchanged cost → deferred" verdict changed, because the cost
  turned out not to be what blocked it once actually measured.

  **Original decision (2026-08-02, superseded above): R3 stays deferred, on
  COST grounds — and the two arguments people reach for on either side are
  both wrong, so record them here before they get re-litigated.**

  *The argument FOR skipping it was refuted.* "No enemy can perform the same
  move on two consecutive turns, so the previous intent is inferable from the
  current one" is **false**. `RandomBranchState.add_branch`'s default
  `repeat_type` is `CAN_REPEAT_FOREVER` (`monsters/state_machine.py`, the
  `add_branch` signature) — consecutive repeats are the engine's DEFAULT and
  `CANNOT_REPEAT` is opt-in per branch. A census of all 106 registered monsters
  found **40 (37.7%) can show the identical move on two consecutive turns**: 30
  of 79 state-machine monsters and 10 of 27 hand-rolled ones, via self-loops
  (`Guardbot`, `Noisebot`, `Zapbot`, `GasBomb`), explicit repeat budgets
  (`HunterKiller`'s PUNCTURE ports `AddBranch(state, 2)` as
  `CAN_REPEAT_X_TIMES`/`max_times=2`, `monsters/hive/hunter_killer.py:45-50`),
  unguarded branches (`Fabricator`'s FABRICATE/STRIKE), and combat-state
  conditionals with no history check (`BowlbugRock`'s HEADBUTT). A boss and
  several elites are among them.

  *The obvious cheap substitute is INADMISSIBLE.* Adding the enemy's current
  **move id** as one int per enemy row — which would be a fraction of R3's cost,
  with no `net_id`/phase-epoch problem, since it describes now rather than a
  buffer that can stale — fails the §6 display-path test. `NIntent.cs:133-136`
  writes a number only for `AttackIntent` (damage + hits) and `StatusIntent`
  (card count); the other **12 of 15 `IntentType` values render as a bare icon
  with no number**, and the hover tooltip (`AbstractIntent.cs:45,67-79`) is
  title+description keyed by intent CLASS (`"BUFF.title"`), never by move or
  monster. **The game never displays a move name anywhere in the render path.**
  So a move id would reveal which power a generic buff icon applies, and its
  amount — invisible to a human. Decisive corroboration: `IntentType.
  DebuffStrong` is computed from `DebuffIntent`'s `_strong` flag
  (`DebuffIntent.cs:7-21`) but is **read nowhere in any rendering code**, so the
  game's own 15-value type already collapses on screen. A move id is finer than
  `IntentType` and therefore leaks strictly more.

  *What survives.* A history of DISPLAYED facts (the 9 `MoveType` booleans plus
  the attack/status numbers) is genuinely admissible — a human remembers what
  they saw, and that is how a player tracks a repeat budget. But its resolution
  is capped by the above, so it recovers cooldown state only where the numbers
  already separate the moves. **Modest value at unchanged cost → deferred.**

  *Free corollary, no action needed.* This check independently VALIDATES the
  existing enemy row (§5): merging Debuff/DebuffStrong/CardDebuff into one flag,
  and Stun/Sleep into one, matches the display path exactly rather than the
  internal type. That merge was correct.
