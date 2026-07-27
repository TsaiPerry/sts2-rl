# Relic content audit — batch 16 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b16` · **Commit:** `80b796c4`
**Units:** 15 (`tea_of_discourtesy` … `unceasing_top`)
**Probes:** `audit/tools/relic_probes_b16.py` (14 probes, committed, re-runnable)

`py audit/tools/harness.py validate` → **216 records, 0 invalid**.
`py audit/tools/citation_check.py audit/records/relic` → **2667 citations, MISSING 0,
OUT-OF-RANGE 0**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 211 · invalid 0 ·
stale 0 · gaps 161 · unaudited 47`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged. No engine
code touched (`git status` showed only `audit/records/relic/` and the new probe module).

---

## Units and rollups

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `tea_of_discourtesy` | **gap** | 4 | 7 |
| `the_abacus` | **gap** | 2 | 5 |
| `the_boot` | **gap** | 3 | 6 |
| `the_courier` | **gap** | 4 | 6 |
| `throwing_axe` | deliberate-divergence | 5 | 5 |
| `tiny_mailbox` | **gap** | 3 | 5 |
| `toasty_mittens` | **gap** | 2 | 8 |
| `toolbox` | **gap** | 2 | 9 |
| `touch_of_orobas` | **gap** | 2 | 7 |
| `toxic_egg` | **gap** | 5 | 7 |
| `toy_box` | **gap** | 7 | 6 |
| `tri_boomerang` | waiver | 2 | 7 |
| `tungsten_rod` | **gap** | 3 | 7 |
| `tuning_fork` | **gap** | 4 | 9 |
| `unceasing_top` | **gap** | 3 | 7 |

12 of 15 roll up to `gap`. **16 gap entries — 8 LIVE, 8 dormant.** Nine of the
fifteen units needed execution to settle.

---

## LIVE gaps, each with its executed evidence

All evidence from `py audit/tools/relic_probes_b16.py <probe>`.

1. **`toasty_mittens` G1 — the +1 Strength per turn is not implemented at all.**
   `ToastyMittens.cs:50` applies `PowerCmd.Apply<StrengthPower>(…, 1, …)` on
   every `BeforeHandDraw`, *outside* the `if (cardModel != null)` branch that
   guards the exhaust. `toasty_mittens.py` has no `PowerCmd` call and no mention
   of Strength. *`mittens-power`:* turns 1/2/3 report player powers `[]` and
   exhaust pile 1/2/3, where the game reports Strength 1/2/3. **Half the relic
   is missing**, in the direction that keeps the drawback and drops the payoff.
   The single largest finding in the batch.

2. **`the_boot` G1 — `ModifyHpLostAfterOstyLate` is C#'s SECOND HP-loss pass.**
   `Hook.ModifyHpLost` (`Hook.cs:1742-1762`) runs `AfterOsty` over every
   listener and then `AfterOstyLate` over every listener; The Boot is one of two
   Late implementers, so its floor is applied strictly last. The sim's single
   flat walk registers relics at `combat.py:159` and powers only when applied.
   *`boot-order`:* against a Soul Fysh that has used its FADE move
   (`soul_fysh.py:76-79`), sim listener order is `['TheBoot','IntangiblePower']`
   and 4 powered unblocked damage costs the enemy **1 HP** where the game costs
   it **5**. Co-occurrence is same-act: Trash Heap is in the Underdocks pool
   (`events/__init__.py:81`) and Soul Fysh is an Underdocks monster. The probe
   also shows the divergence turns on *registration order*, not on the relic:
   Inklet/Vantom apply Slippery from `__init__` (before relics attach) and the
   sim accidentally agrees there.

3. **`tea_of_discourtesy` G1 — the two Dazed land at mirrored draw-pile
   positions.** `CardPileCmd.cs:514` resolves `CardPilePosition.Random` as an
   index into a pile whose top is 0; the sim's top is the list END, and the sim
   already has the correct port — `CardPileCmd.add_to_draw` (`cmds.py:474-497`)
   inserts at `count - p`. `tea_of_discourtesy.py:35-39` uses the raw game index.
   *`tea-position`:* 5-card pile, shuffle pinned to `NextInt → 1` → relic puts
   Dazed at sim `[1, 2]`, the helper puts them at `[4, 5]` (the top). **Seven**
   other ported sites call the helper, including `relics/blessed_antler.py:33`
   which adds Dazed to the draw pile correctly — a one-site defect.

4. **`the_courier` G1 + G2 — no discount and no restock.** No
   `modify_merchant_price` / `should_refill_merchant_entry` member on `Relic`
   and no dispatch site in `shop.py`. *`courier-price`:* the same seeded shop
   stocks costs `[50, 37, 74, 78, 79, 84, 181, 194, 201, 208, 49, 48, 51, 75]`
   with the relic, without it, and with `membership_card` — byte-identical; and
   a bought entry reports `is_stocked=False`. This is Sweep C's "larger fix"
   (new base hook), and **rule 3 binds the fix to cover `membership_card`
   (50% off) at the same time.**

5. **`tiny_mailbox` G1 — the two rest-site potion rewards are missing, and the
   stub's premise is false in four ways.** `Relic.modify_rest_site_heal_rewards`
   exists (`relics/base.py:245-249`); `RunState.rest_heal_rewards` dispatches it
   (`run.py:1097-1110`); a sibling Event relic already uses it
   (`relics/dream_catcher.py:22-25`); and `CombatRewards.special_potions`
   (`rewards.py:385-388`) is consumed by `driver.py:388-390`. *`mailbox-rest`:*
   on one seed `tiny_mailbox` yields `cards=[] special_potions=[]` where
   `dream_catcher` yields `['feel_no_pain','rampage','iron_wave']`, and
   `run.random_potion()` works.

6. **`unceasing_top` G1 — `CheckForEmptyHand` has TWO C# callers and the port
   covers one.** `CardModel.cs:1992` (after a card play) and `PotionModel.cs:340`
   (after a potion), and `CombatManager.cs:880-883` says so explicitly.
   `unceasing_top.py:21` listens on `on_card_played` only. *`top-empty`:* with
   the relic held, the ported Uncommon potion **Ashwater** (`potions.py:920-938`)
   exhausts the whole hand and the sim's hand ends at **0** where the game draws
   to 1; the card-play route is verified working in the same probe.

7. **`tuning_fork` G1 — a replayed Skill counts once instead of twice.**
   `AfterCardPlayed` fires inside C#'s play-count loop (`CardModel.cs:1961`), the
   sim's `on_card_played` once per play (`combat.py:514`). *`axe-tuning`:* with
   the counter preloaded to 9 and `throwing_axe` also held, the sim gives block
   17 / counter **0** where the game gives block 17 / counter **1**. Because the
   counter is per-run, the offset never washes out — every later trigger in the
   run is one Skill late. Third content site of `hook_dispatch` G4 after
   `unsettling_lamp` G1.

8. **`toxic_egg` G1 — `IsAllowed` (`TotalFloor < 41`) unmodelled.** *`egg-floor`:*
   at `total_floor=60` the grab bag still yields `toxic_egg`. Sweep B cluster (a),
   17 relics, matching `amethyst_aubergine`'s verdict.

---

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `tea_of_discourtesy` G2 | `CardPileCmd._enter_combat` skipped: the two Dazed are never registered as listeners and `on_card_entered_combat` never fires (executed: `card.combat=None`, not in `hooks._listeners`) | a `BeforeCombatStart`-active card-afflicting effect, or any of the 8 `on_card_entered_combat` listeners matching a Status card (today: 6 enemy powers that don't exist yet at combat start, Stomp which only reacts to itself, Ghost Seed which only matches Basic Strike/Defend) |
| `the_abacus` N4 | C# skips the whole `AfterShuffle` dispatch when the combat is over or ending (3 separate guards); the sim's `on_shuffle` has no gate | any on-death or combat-end effect that draws, or an explicit Shuffle at combat end (today the sim only reshuffles from `_draw`, and `combat.py:493-494` breaks the play loop once decided) |
| `the_boot` G2 | `props.IsPoweredAttack()` replaced by `card is None or card.is_unpowered`; the sim's `modify_hp_lost` carries no `props` | a card dealing unpowered/unblockable damage to an **enemy** with an amount not derived from a powered leg. Executed census: only `Omnislice`'s splash (`colorless_attacks.py:322`) aims at an enemy, and its amount is the first leg's post-Boot `dealt`, so it can never be in 1..4 — the other nine card-sourced non-Move sites all target the player. The real fix is to carry `props` on the hook |
| `toolbox` G1 | `Toolbox.cs:27` names `Rng.CombatCardGeneration`; `toolbox.py:25-27` uses the legacy shared `random.Random` with **no parity branch** (executed: source has no `is_parity`, no `card_gen`) | already LIVE on the conformance/parity path (offers *and* stream position diverge, shifting every later `card_gen` draw); dormant only for RL. Sibling `relics/vexing_puzzlebox.py:29-33` does it correctly, as do 7 other ported sites |
| `touch_of_orobas` G1 | `RelicCmd.Obtain` strips the obtained relic from both grab bags and stamps `FloorAddedToDeck`; the port assigns into `run.relics` directly | adding any refinement relic to a grab bag, or porting a second character's refinement pair (executed: `black_blood` is not in the bag, so there is nothing to strip) |
| `toxic_egg` G2 | `TryModifyCardRewardOptions**Late**` is C#'s second pass; the sim has one flat walk | porting a plain-phase `modify_card_reward_options` implementer that REMOVES or REPLACES a card in the offer (`LastingCandy.cs:127` / `PrismaticGem` are the C# shapes). Checked: the four ported implementers — `glitter.py:16`, `silken_tress.py:27`, `silver_crucible.py:28`, `_eggs.py:39` — all mutate in place |
| `toy_box` G2 | `RelicCmd.Melt` leaves the relic in `Player.Relics` as an inert entry; the port deletes it (executed: relic count 5,5,4,4,4,3 across six combats where the game stays 5) | porting any effect that reads the relic COUNT or LIST without an `IsMelted`/`IsTradable` filter. Today every reader filters: both hook walks exclude melted relics, and `RanwidTheElder`/`RelicTrader` filter on `IsTradable` (which itself excludes melted). The only unfiltered reader in the whole source is `ILikeShiny.cs:24`, an achievement badge |
| `tungsten_rod` G1 | The Rod is in C#'s FIRST HP-loss pass and the sim has no phase concept | a THIRD `ModifyHpLostAfterOstyLate` implementer whose domain includes the player and whose result is not a flat constant. Census: only `BufferPower` (returns flat 0, order-insensitive) and `TheBoot` (disjoint domain — requires `target != Owner`) |
| `tungsten_rod` N5 | out of combat the sim's `RunState.lose_hp` walks **relics only**; C#'s `IterateHookListeners(null)` also walks every deck card, its enchantment and the potions | porting a card or enchantment that implements `modify_hp_lost` (executed: today only powers and 3 relics do, and powers do not exist out of combat). `hook_dispatch` N5 at a content site |

---

## Cross-record disagreement under rule 3

**None found.** Six mechanisms already carried a verdict elsewhere and all six
are reproduced with the same verdict, cited, not re-derived:

- per-Replay `AfterCardPlayed` → **gap**, matching `hook_dispatch` G4
  (`tuning_fork` G1; `throwing_axe` N4 records that the Axe is the *witness*,
  not the defect).
- Late/Early phase passes → **gap**, matching `hook_dispatch` G3 (`the_boot` G1,
  `toxic_egg` G2, `tungsten_rod` G1).
- cross-listener order (powers first in the game, last in the sim) → **gap**,
  matching `hook_dispatch` G2 (`the_boot` G1).
- the run/combat dispatch split → **gap**, matching `hook_dispatch` N5
  (`tungsten_rod`'s hook entry and N5).
- `AfterHandEmptied` rerouted onto a play-time hook → **gap**, matching
  `turn_structure` G16 — which names this exact port as its dormancy reason.
  This record adds what G16 could not see from the machinery side: the reroute
  is *incomplete* (see LIVE gap 6).
- auto-keeping a `RewardsCmd.OfferCustom` relic screen →
  **deliberate-divergence**, matching `calling_bell` G3 (`toy_box` G1).
- `IsAllowed` pool eligibility → **gap**, matching `amethyst_aubergine`
  (`toxic_egg` G1).

One *tension* worth naming, not a disagreement: `turn_structure` G16 labels the
`AfterHandEmptied` mechanism DORMANT because `unceasing_top`'s reroute
reproduces C#'s gating. That is right for the *card-play* caller and wrong for
the *potion* caller, so the seam's dormancy claim is narrower than it reads.
Recorded in `unceasing_top` N1/G1; the seam record is read-only to this batch
and was not edited.

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file on the first try;
`audit/tools/name_overrides.json` needs no additions. Obtainability confirmed
for all 15 (`relic_probes_b16.py pool`): 8 from the transcribed grab bag, 7 from
ported events/shrines (Tea Master, Trash Heap, Tanx ×2, Tezcatara ×2, Orobas).

---

## Things wrong in the shared tooling and briefs

Reported here, not edited — all four files are read-only to this batch.

### 1. The brief's "Pre-diagnosed units" list quotes PRE-REWRITE sweep A, and two of its lines would have produced false gaps on working relics

This is the same defect the coordinator flagged mid-flight for batches 15 and
18; it hit batch 16 twice, and both were caught by auditing the unit on its
merits *before* the correction arrived.

- **`toy_box`** — brief: *"Sweep A candidate (`combats_seen`; C# resets at
  `AfterCombatEnd`)."* `ToyBox.AfterCombatEnd` does `CombatsSeen++`
  (`ToyBox.cs:101`). It is an **increment on a `[SavedProperty]`**, not a reset.
  Re-executed: the current `sweep-reset` prints `toy_box ['combats_seen'] …
  C# resets: NONE (may be per-run by design)` — the fixed column, which agrees
  with the source. The relic is correct; a per-combat reset would break a relic
  that melts one wax copy every third combat of the **run**.
- **`tuning_fork`** — brief: *"Sweep A flagged this for a SECOND LOOK
  (`_skills_played`)."* `TuningFork.SkillsPlayed` is a `[SavedProperty]` and
  `TuningFork.cs` has **no** `BeforeCombatStart` / `AfterRoomEntered` /
  `AfterCombatEnd` / turn-boundary override at all. Current sweep output again:
  `C# resets: NONE`. The port's per-run counter is right.

**Both are exactly sweep A's already-fixed defect 3 surviving in prose.** The
mechanism is worth stating for whoever regenerates the batch prompts: a prompt
generated by *paraphrasing* a sweep is a snapshot that never gets corrected when
the sweep is, so it becomes the last living copy of a fixed defect. Prompts
should cite the sweep command to run, not its conclusions.

### 2. Neither of my two sweep-A units is in any `sweep-reset-exec` bucket

Verified after the coordinator's note: `toy_box` and `tuning_fork` are in
`sweep-reset`'s static "NEVER RESET BEFORE A READER" bucket but **not** in the
prioritised 20, because their C# counterparts make no combat-boundary
assignment — so the executed pass says nothing at all about them. Both were
settled from the C# source instead (`[SavedProperty]` + a whole-file check for
boundary overrides), which is what that bucket requires. None of the other 13
units appears anywhere in `sweep-reset`.

### 3. Sweep C's `tiny_mailbox` row understates the finding

Sweep C reports `TryModifyRestSiteHealRewards -> Relic.modify_rest_site_heal_-
rewards EXISTS`, which is the *dispatch* half. It does not note that a **sibling
relic already implements the same hook** (`dream_catcher`) or that the
destination field for a potion reward exists and is consumed (`special_potions`
→ `driver.py:388-390`). Those two facts are what turn "premise false" into
"trivially fixable, with a working template three files away", and a sweep row
that carried them would let a batch confirm in one probe instead of four greps.
Suggestion for the sweep, not applied: for each dropped hook, also print
whether any *other* ported relic implements the same sim method.

---

## New bug classes / pool-wide shapes

Two candidates, each with the unit that exhibited it. Not folded into
`PROMPT.md` (read-only to this batch).

### Candidate class 30 — a port that RE-IMPLEMENTS a Cmd helper the sim already has, and loses the bridge the helper exists for

`tea_of_discourtesy` G1. The sim's `Cmd` layer sometimes exists *precisely* to
bridge a representation difference between the game and the sim — here
`CardPileCmd.add_to_draw` exists to convert a game draw-pile index (top = 0)
into a sim index (top = end), and its docstring says so. A port that inlines the
same three lines gets the RNG stream right and the orientation silently wrong.
This is distinct from the existing classes: the hook is right (not class 11),
the site is right (not class 20), the stream *is* consumed (not class 16), and no
docstring lies (not classes 12/19/24). The tell is textual and cheap to sweep:
**a relic/card/power that touches `player.draw_pile` / `hand` / `discard_pile`
directly instead of going through a `CardPileCmd`.** In this batch the same
question came up three times and the other two ports were right —
`toasty_mittens` N3 (draw-pile top orientation, correct) and `toolbox` N7 (uses
`add_to_draw`'s sibling `add_to_hand`, so `_enter_combat` fires) — which is what
makes the one wrong site a defect and not a house style. `tea_of_discourtesy`
also loses `_enter_combat` at the same site (its G2), so the class costs two
gaps per instance, not one.

### Candidate class 31 — a divergence whose reachability depends on WHEN a power was applied, not on which content exists

`the_boot` G1. Rule 6 normally asks "are both sides ported?", and the honest
answer here was "yes, and it still depends". The sim registers relics at
`CombatState` setup and powers only when `PowerCmd.apply` runs, so for any hook
where C# runs powers before relics (`hook_dispatch` G2) the sim **agrees** for a
power granted in a monster's `__init__` and **diverges** for the same power
granted by a move mid-combat. Executed both ways in one probe: Inklet's
constructor Slippery gives 5 HP either way, Soul Fysh's FADE Intangible gives
1 vs 5. The lesson for the reachability argument: **when a divergence rests on
listener order, name the moment the power is applied, not just the power.** An
audit that had reached for the nearest Slippery monster would have concluded
"no delta" and filed a false clear — the sweeps' worst failure direction, arrived
at without a sweep.

---

## Left unverified / out of scope

- **`toy_box` G2's melted-relic equivalence** rests on a census of C# readers of
  `Player.Relics` (grep for `Relics.Count` / `.Any` / `.Where` under
  `src/Core/Models`, `Rewards`, `Entities`). That grep cannot see a reader that
  reaches the list through a local variable, so the dormancy claim is "no reader
  found", not "no reader exists". `is_melted` being absent from the sim's `Relic`
  base is recorded either way.
- **`unceasing_top` G2** (`IsExecutingCardOrPotionEffect`): I reasoned through
  the three ported auto-play cards analytically rather than executing each, and
  concluded the net draw count matches. The mechanism is recorded; the
  per-card confirmation is not executed.
- **The scope tension on two records is stated, not resolved.** `tiny_mailbox`
  G1 and `unceasing_top` G1 both have a potion in the causal chain, and the
  shared contract defers potions. Both are filed as gaps on the `belt_buckle`
  `AfterPotionProcured` precedent (the potion is only the trigger; the divergent
  observable is a rest-site reward screen and a card draw respectively). If
  Perry wants the potion exclusion read more broadly, those two verdicts — and
  `belt_buckle`'s — should move together.
- `AfterModifyingHpLostAfterOsty` on `the_boot` and `tungsten_rod` is a bare
  `Flash()` in both, waived as presentation. I did not census the hook's other
  C# implementers, so I cannot say the sim's `after_modify_hp_lost` is complete —
  only that these two relics need nothing from it.
