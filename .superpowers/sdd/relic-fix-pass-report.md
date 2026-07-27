# Relic content-tier FIX PASS — report

**Branch** `audit-pipeline` · **Date** 2026-07-26 · **Write scope** `audit/records/relic/**` only

43 relic records edited. `sts2_rl/` untouched (`git status --porcelain sts2_rl/` empty).
Nothing committed; everything is left in the working tree.

## Verification (run, not asserted)

| command | result |
|---|---|
| `py audit/tools/harness.py validate --strict-inherited` | `686 record(s), 0 invalid` |
| `py audit/tools/audit_status.py` | relic `258 / 258 audited, 0 invalid, 0 stale, 204 gaps, 12 live, 0 unaudited` |
| `py audit/tools/citation_check.py` | **0** relic rows under MISSING / OUT-OF-RANGE / AMBIGUOUS BASENAME |
| `py audit/tools/backfill_sources.py --kind relic` | MISPATHED **6 → 0**, unresolvable **3 → 0**; 145 `extra_sources` entries added across 30 records |
| `py -m pytest test/ -q` | `2522 passed, 38 xfailed` — unchanged |
| `git status --porcelain sts2_rl/` | empty |

`harness.py rehash` was **not** run. No hash was re-pinned.

### Counts

| | before | after |
|---|---|---|
| entries `faithful` | 1230 | **1243** |
| entries `waiver` | 397 | **383** |
| entries `deliberate-divergence` | 77 | **63** |
| entries `gap` | 604 | **620** |
| records `faithful` | 7 | **8** |
| records `waiver` | 39 | **38** |
| records `deliberate-divergence` | 11 | **8** |
| records `gap` | 201 | **204** |

Seven record rollups flipped — the six the review predicted, plus `pear`:

```
alchemical_coffer   waiver                -> gap
arcane_scroll       gap                   -> faithful
beautiful_bracelet  gap                   -> waiver
black_star          deliberate-divergence -> gap
pear                deliberate-divergence -> gap
potion_belt         waiver                -> gap
small_capsule       deliberate-divergence -> gap
```

The `live` column moves 0 → 12 for relic: this pass is the first to populate the
optional `live` boolean, on every gap entry it wrote.

---

## PART A — verdict changes

### A1 — the auto-keep cluster (accepted in full; 10 entries, 8 records)

Independently re-derived. `grep -rn WithSkippingDisallowed src/` returns exactly
**two** lines in the whole game source: the definition (`RewardsSet.cs:115`) and
its single caller (`NeowsBones.cs:43`). Every other relic offer —
`CallingBell.cs:31`, `ToyBox.cs:96`, `SmallCapsule.cs:15`, `LostCoffer.cs:22`,
`Orrery.cs:27`, `GlassEye.cs:32`, and the ordinary reward screen `BlackStar.cs:23`
/ `LavaRock.cs:61` / `WongosMysteryTicket.cs:101` append to — is a plain
skippable `RewardsCmd.OfferCustom` (`RewardsCmd.cs:47-50`).

Two independent observables, both verified:

1. **A decline is written into run history.** `RelicReward.OnSkipped`
   (`RelicReward.cs:117-123`) writes `RelicChoices.Add(…, wasPicked: false)`, and
   `sts2_rl/conformance/runner.py:429-432` reads that exact field.
   `runner.py:435-466 _reconcile_node_relics` exists solely to delete relics the
   sim auto-granted that the save says were not picked. A divergence that needs a
   replay-time workaround is not an identical observable (binding rule 2).
2. **Pickup effects fire unconditionally.** C# runs `AfterObtained` inside
   `RelicReward.OnSelect` (`RelicReward.cs:109-115`); `run.add_relic`
   (`sts2_rl/run.py:546-553`, call at `:552`) fires it at screen-generation time.
   Executed at `toy_box`: a seeded run obtains four wax relics and
   `potion_belt`'s `after_obtained` has already run.

Flipped to `gap` (LIVE): `black_star` `TryModifyRewards`; `calling_bell` G3;
`lava_rock` `TryModifyRewards` + N1; `small_capsule` `AfterObtained` + G1;
`toy_box` `AfterObtained` + G1; `wongos_mystery_ticket` N2; `gambling_chip` G3;
`lost_coffer` G1 (narrowed to the potion half — see below).

**`gambling_chip` G3 — executed, and the finding is stronger than the review
stated.** `GamblingChip.cs:20` builds `CardSelectorPrefs(prompt, 0, 999999999)`
(min 0) and `:21` guards the payload with `if (list.Count != 0)`. The sim calls
`combat.select_cards('gambling_chip', hand, len(hand))`, and `'gambling_chip'` is
not in `sts2_rl/driver.py:77 SKIPPABLE_PURPOSES`. I drove
`RunDriver._card_selector` directly with an `_ask` that raises:

```
gambling_chip hand=3 count=3 -> ['a','b','c']   (no DecisionRequest ever issued)
card_reward        -> DECISION ISSUED
obtain             -> DECISION ISSUED
transform_optional -> DECISION ISSUED
```

The driver never asks, so the whole hand is mulliganed with no way to decline —
graded **A** (stream desync: N unnecessary draw-pile draws every combat).

**`lost_coffer` G1 narrowed.** The CARD half is fine and stays faithful:
`sts2_rl/relics/lost_coffer.py:22` uses purpose `card_reward`, which IS skippable.
The POTION half (`:23`, a bare `run.add_potion(run.random_potion())`) is the gap.

**Kept `deliberate-divergence`, verified correct:** `neows_bones` G2 (the one
`WithSkippingDisallowed` site — its rationale was rewritten, because it used to
justify itself by citing `calling_bell` G3, which is now a gap); `claws` and
`glass_eye` (purposes `transform_optional` / `card_reward`, both skippable).

**`orrery` G2 text corrected** — it claimed skippability as its discriminator
against `calling_bell` and misread Calling Bell as non-declinable. Marked
`live: false` (dormant; G1's stub subsumes the observable).

### A2 — `arcane_scroll` `AfterObtained` `gap → faithful` ✅ (record rollup → faithful)

Settled: `CardPileCmd.Add(card, PileType.Deck)` → `CardPile.AddInternal(card,
index = -1)` → `_cards.Add(card)` (`src/Core/Entities/Cards/CardPile.cs:83-97`,
doc at `:80`, the `else` arm at `:96`); sim `run.add_card` → `self.deck.append(card)`
(`sts2_rl/run.py:349`). Same end. The "LIVE as a documentation gap" framing is
deleted — an under-cited record is not something a player or replay sees. Added a
new guard **N5** carrying the placement citation the entry was missing.

### A3 — `beautiful_bracelet` `gap → faithful` ✅ (record rollup → waiver)

Confirmed the misread: `sts2_rl/enchantments.py:158-164` is
`SpiralEnchantment.can_enchant`, not Swift's. `SwiftEnchantment`
(`enchantments.py:341-358`) declares no `can_enchant`
(`'can_enchant' in SwiftEnchantment.__dict__` is `False`) and inherits the base at
`enchantments.py:51-62`. **Executed: Swift can enchant 168 of the 203 ported
cards; the quoted predicate yields exactly `['defend','strike']`.** Both blocking
sources read and settled: `Swift.cs` declares no `CanEnchant` and no
`CanEnchantCardType`; `BeautifulBracelet.cs:31` reaches the 4-arg overload
(`CardSelectCmd.cs:532-535`) which forwards `additionalFilter: null`, so
`CardSelectCmd.cs:549` is `Where(c => enchantment.CanEnchant(c) && true)`. The
entry now carries a clause-by-clause map of `EnchantmentModel.CanEnchant`
(`:275-279`, `:280-283`, `:284-288`, `:289-292`, `IsStackable` default at `:173`)
against the sim's base predicate.

### A4 — the potion cluster (accepted in full)

I verified the majority side myself before applying the ruling: **45 relic gap
entries across 25 records turn on potion mechanics, 27 tagged LIVE**, against only
four records that waived on the exclusion. The belt is conformance-asserted
(`runner.py:623-631` slot-by-slot, `runner.py:715-717` reads `max_potions`).

- `potion_belt` `AfterObtained` + N1 → **gap, LIVE, grade B**
  (`b12-potionbelt`: `max_potions 3 -> 3` where the game grows to 5). Record
  rollup waiver → gap. N2 was re-verdicted `faithful` and retitled — it describes
  no divergence of its own, only the fix recipe plus an executed negative (the
  missing slots cannot reach a combat number: Belt Buckle's Dexterity turns on the
  belt being EMPTY, not full).
- `alchemical_coffer` `AfterObtained` → **gap, LIVE, grade B**. Executed on a
  fresh run: `max=7` with slots
  `[0 fairy_in_a_bottle, 1 colorless_potion, 2 liquid_memories, 3 strength_potion,
  4 None, 5 None, 6 None]`, where `AlchemicalCoffer.cs:22-27` procures into
  `originalSlotCount + i` = 3,4,5,6. Record rollup waiver → gap.
- `lost_coffer` G2 → **gap, LIVE, grade A**. `PotionReward.Populate`
  (`PotionReward.cs:54-61`) draws from `Player.PlayerRng.Rewards`, two draws
  (`PotionFactory.cs:67-81`). Executed: `run.player_rng.rewards` moves **0 → 9**
  across `add_relic('lost_coffer')` and all nine belong to the card half —
  the potion contributes zero where the game contributes two.
- `phial_holster` N1 → **faithful** (`b12-phial`: `max_potions 3 -> 4`). Noted in
  the entry that this waiver was actively shielding `potion_belt`'s live gap,
  which cited it as precedent for the opposite mechanism.

### A5 — `pear` `undo_after_obtained` `dd → gap` ✅ (record rollup → gap)

Executed at 75/80 for all five implementers; every one ends `(80,80)` instead of
`(75,80)`:

```
lees_waffle   (75,80) -> (87,87)  -> (80,80)
looming_fruit (75,80) -> (106,111)-> (80,80)
mango         (75,80) -> (89,94)  -> (80,80)
pear          (75,80) -> (85,90)  -> (80,80)
strawberry    (75,80) -> (82,87)  -> (80,80)
```

Graded **C** and scoped honestly: the helper's only caller is the conformance
runner (`runner.py:455-461`), so it is a defect in the tool DETECTOR 3 rests on,
not a fidelity gap against the C#.

### A6 — `fake_strike_dummy` `dd → gap` ✅ (the entry is **N1**, not G1)

The review's guard key was off by one — G1 was already a gap. N1 is the entry
that argued equivalence while citing `damage_pipeline` G3. Flipped to `gap`,
DORMANT, with the executed dormancy evidence retained.

### A7 — `war_hammer` `faithful → gap (DORMANT, grade C)` ✅ (the entry is **N4**)

`Hook.AfterCombatVictory` (`Hook.cs:340-351`) really is two complete passes.
`WarHammer.cs:19` implements the plain pass, exactly where `sword_of_stone` G1
sits (a `gap` marked "DORMANT AT THIS SITE"), while `meat_on_the_bone` G1 is the
same mechanism LIVE. Dormancy trigger named: porting any
`AfterCombatVictoryEarly` listener that reads or rewrites the DECK.

### A8 — `NoHookUpgrades`: all three eggs now agree, as **`faithful`**

Re-ran the grep myself: `grep -rn NoHookUpgrades src/` returns exactly four lines
— the enum member (`CardCreationFlags.cs:29`) and the three egg relics reading it.
**Three readers, zero producers.** `grep -rn 'CardCreationFlags.NoUpgrades\b' src/`
returns *nothing*; `NoModifications` returns only its own declaration
(`CardCreationFlags.cs:68`).

So `frozen_egg` G2's stated dormancy trigger — "porting any C# effect that creates
cards `WithFlags(NoHookUpgrades)` — the shape exists in the source's
card-generation callers" — **is contradicted by the source**, and the entry now
retracts it explicitly. Per A9 the three sites are `faithful`, not `waiver`, and
the genuinely live sibling `NoModifyHooks` (producer at `LastingCandy.cs:127`,
gate at `CardFactory.cs:104`) is named as `relic/lasting_candy`'s business.
`frozen_egg`'s `TryModifyCardRewardOptionsLate` rollup text was rewritten; the hook
stays `gap` on G4 alone and the record rollup is unchanged (G1 IsAllowed is a LIVE
gap).

### A9 — dead-in-the-source vocabulary: **accepted for dead members, REJECTED for `winged_boots`**

**Accepted.** Nine entries moved `waiver → faithful` (and `frozen_egg` G2
`gap → faithful`), each with its grep re-run:

| entry | dead member | evidence |
|---|---|---|
| `unsettling_lamp` N1 | `PowerModel.IsVisibleInternal` | 3 hits, all in `PowerModel.cs` (`:148` doc, `:156` read, `:167` declaration); **zero overrides** |
| `calling_bell` G4, `storybook` N2, `tanxs_whistle` N2 | `Hook.ShouldAddToDeck` | 4 hits: dispatch `CardPileCmd.cs:384`, wrapper `Hook.cs:2084-2088`, base `AbstractModel.cs:2144`; **zero overrides** |
| `touch_of_orobas` N2 | `RelicModel.AfterRemoved` | zero overrides across `src/Core/Models/Relics/` |
| `fake_snecko_eye` N1 | `TestMode`-gated setter | only writer is `AssertOn`-guarded; both call sites dead in shipping |
| `toxic_egg` N1, `molten_egg` G3, `frozen_egg` G2 | `CardCreationFlags.NoHookUpgrades` | 3 readers, 0 producers (A8) |

`harness.py validate` accepts these: `maps_to` is required for `faithful` **hooks**
only (`harness.py:927-928`), and every one of these is a **guard**. No tooling
limitation to report.

**REJECTED — `winged_boots` hook `IsAllowed` stays `waiver`.** Pushing back with
evidence. `WingedBoots.cs:47-50` is `runState.Players.Count == 1`, which is a
**multiplayer** gate, and the shared contract's binding rule 1 names multiplayer
as the canonical waiver: *"`waiver` means genuinely OUT OF SCOPE and nothing else
— multiplayer, presentation/animation/SFX, ascension values, other characters."*
The distinction that makes `IsVisible` `faithful` is that no override exists
**anywhere in the shipping game**, so the member cannot vary in any run; a player
count genuinely *can* be > 1 in the shipping game — the sim simply does not model
that mode, which is the definition of out of scope. Flipping it would also create
a fresh rule-3 conflict with every `player != base.Owner` waiver in the tier
(`black_star` N1, `lava_rock` N8's sibling framing, `wongos_mystery_ticket` N10,
`sozu` N1, `white_beast_statue` N2, …). The VOCAB paragraph written into the nine
flipped entries states this boundary explicitly so the next pass does not re-open
it.

### A10 — `tuning_fork` delegation ✅ (the entry is **N6**)

The text said "*and the same reason it is a `faithful` rather than a `waiver`*"
about `unsettling_lamp` N1, which was a `waiver`. After A9 the delegation is true
as written; the entry now says so and records that the assertion used to be
backwards.

---

## PART B — rationale / citation corrections

- **B1 `red_skull` `AfterRoomEntered`** ✅ corrected, no verdict change.
  `SetUpCombat` (`CombatManager.cs:350-378`) adds creatures but rolls **no** move;
  `RollMove` is `CombatManager.cs:865` inside `AfterCreatureAdded` (`:860-867`)
  inside `StartCombatInternal` (`:387-396`) launched from `AfterCombatRoomLoaded`
  (`:380-385`), which `CombatRoom.cs:230` calls — **after** the
  `Hook.AfterRoomEntered` at `CombatRoom.cs:228`. Also recorded the review's
  cross-check: `Intent` is a plain dataclass and `RollMove` takes no power input,
  so enemy Strength cannot move an intent.
- **B2 `hefty_tablet` G3** ✅ — and this one **changed the verdict**, `dd →
  faithful`. The premise ("`run.select_cards` … has no skip channel at all") is
  false: `hefty_tablet.py:40` passes `purpose="obtain"`, which IS in
  `SKIPPABLE_PURPOSES`, so the driver issues a real decision with a skip action
  and `run.py:384-390` honours an empty return. Matches `lead_paperweight` N4,
  which had already reached that conclusion at the other `canSkip: true` screen.
- **B3 `ectoplasm` G2** ✅ corrected, `faithful` survives.
  `sts2_rl/relics/bowler_hat.py` is a 12-line behaviourless stub with no method
  body. Executed census: `grep -rn 'def modify_gold_gained' sts2_rl/` returns two
  lines — the base default (`relics/base.py:212`) and `ectoplasm.py:26`. One
  implementer, so the commutativity argument was vacuous; the verdict now rests on
  "a one-listener chain has no order".
- **B4 `winged_boots` N3** ✅ premise corrected, DORMANT conclusion kept.
  `run.add_relic` (`run.py:546-553`) appends unconditionally and
  `pull_relic_from_front` (`run.py:559-595`) has no held-relic filter, so a
  duplicate IS constructible — I used `paper_phrog` G1's hedge wording. The new
  route to dormancy is relic-specific and executed: Winged Boots is ANCIENT
  (`winged_boots.py:13`) so it is not in the grab bag and Toy Box cannot wax-copy
  it, and its only grant path is the Neow option list (`events/neow.py:41`), taken
  at most once.
- **B5 `strike_dummy` G1** ✅ census widened. `cmds.py:55-58` gates the additive
  **and** multiplicative families behind one `if`, and
  `SurroundedPower.ModifyDamageMultiplicative` (`SurroundedPower.cs:46-72`, ported
  at `powers.py:2523-2566`) is ungated — `audit/tools/power_slot_probes.py
  ungated-modifiers` lists it, along with 8 other ungated modifiers. Dormancy
  holds by a **narrower** argument than the old one, which I derived and stated:
  Surrounded's owner is the PLAYER, so the multiplier applies to damage the player
  *receives* from a Kaiser Crab arm, and every ported Kaiser Crab move routes
  through `_execute_attack` (`monsters/hive/kaiser_crab.py:77, 80, 83, 95, 142,
  145, 153`) with default powered `MONSTER_MOVE` props.
- **B6 `centennial_puzzle`** ✅ — `cmds.py:116` is a line of the explanatory
  *comment*. The guard is `if not target.is_dead:` at **`cmds.py:121`** and the
  dispatch at `:122`. Three entries (N1, N3, N4) re-pointed; the rest of the tier
  was already right.
- **B7 `fake_happy_flower`** ✅ → `sts2_rl/relics/base.py:20-24`.
- **B8 `vajra`** ✅ → both files spelled out:
  `sts2_rl/monsters/fuzzy_wurm_crawler.py:36-40` **and**
  `sts2_rl/monsters/overgrowth/fuzzy_wurm_crawler.py:37-41`. The review said the
  overgrowth copy; by line number `36-40` actually matches the top-level file, and
  the overgrowth copy's `current_intent` body sits one line lower (the extra
  package level in `from ...powers import`). Both are named in the record's own
  census sentence, so both are now cited with their correct ranges.
- **B9 six MISPATHED citations** ✅ all rewritten to full repo-relative paths
  (`fur_coat` ×2, `razor_tooth`, `oddly_smooth_stone`, `byrdpip` ×3,
  `paels_legion` ×2). `backfill_sources.py --kind relic` now reports **MISPATHED
  0**.
- **Bonus, not in the review: `lost_wisp`.** `backfill` reported *three*
  unresolvable paths, not two. The third was this record's own
  `lost_wisp.py:NN` citations, shadowed by `sts2_rl/events/lost_wisp.py`; all are
  now `sts2_rl/relics/lost_wisp.py:NN`. Unresolvable is now **0**.
  (A wrinkle worth knowing: my first corrective notes *quoted* the bad bare paths
  and so re-created the unresolvable citations. The quotes are now written so the
  basename and the line range are separated.)

---

## PART C — report only

### C1 — `UnmovablePower` × `Entrench`: **CONFIRMED, independently re-run**

The finding is correct in every particular. Evidence I reproduced myself:

- `Hook.ModifyBlock` (`src/Core/Hooks/Hook.cs:1310-1341`) has **no props gate** —
  it runs every listener's `ModifyBlockAdditive`, then every listener's
  `ModifyBlockMultiplicative`, and lets each self-gate.
- `UnmovablePower.ModifyBlockMultiplicative`
  (`src/Core/Models/Powers/UnmovablePower.cs:21-41`) gates at `:27-30` on
  `!props.IsCardOrMonsterMove()` — and `IsCardOrMonsterMove` is
  `props.HasFlag(ValueProp.Move)` **alone**
  (`src/Core/ValueProps/ValuePropExtensions.cs:23-26`). Unpowered is deliberately
  permitted, exactly like `Vambrace.cs:59-63` and `PaelsLegion.cs:132-134`.
- `Entrench.cs:23` is
  `CreatureCmd.GainBlock(Owner.Creature, Owner.Creature.Block,
  ValueProp.Unpowered | ValueProp.Move, cardPlay)` — the game's only
  `Unpowered | Move` block gain, and it carries a `cardPlay`, so C# doubles it.
- The sim hoists the filter to the call site:
  `BlockCmd.apply` (`sts2_rl/cmds.py:143-147`) reaches the block-modifier hooks
  only `if is_powered_attack(props)` (Move **and not** Unpowered,
  `sts2_rl/valueprops.py:47-49`).
- `audit/tools/power_slot_probes.py ungated-modifiers` already prints
  `UNGATED Powers\UnmovablePower.cs:21 ModifyBlockMultiplicative`
  (9 ungated / 37 gated).

**Executed divergence** (fresh `CombatState`, `unmovable` applied via
`PowerCmd.apply`, then the ported `entrench` card played):

```
Entrench  unmovable=0: block 10 -> 20   (C#: 20)
Entrench  unmovable=1: block 10 -> 20   (C#: 30)   <-- DIVERGENCE
Defend    unmovable=0: block  0 ->  5   (C#:  5)   control
Defend    unmovable=1: block  0 -> 10   (C#: 10)   control
```

**Reachability — LIVE, and it needs no relic** (verified): `'unmovable' in
IRONCLAD_POOL` is `True` (`sts2_rl/cards/pool.py:33`) and the card applies
`UnmovablePower` (`sts2_rl/cards/unmovable.py:33-36`); `entrench` is granted by the
ported Trash Heap event (`sts2_rl/events/trash_heap.py:17`, card at
`sts2_rl/cards/trash_heap_cards.py:150-176`). The seam's current liveness rests on
Vambrace / Pael's Legion, both relics; this path is pure Ironclad card content.

**The exact edits the owners should make** (I did not touch either file):

1. **`audit/records/power/unmovable.json`**, guard
   `"UnmovablePower.cs:27-30 !props.IsCardOrMonsterMove() -> 1m"` —
   currently `faithful`, and its rationale asserts the opposite of the truth:
   *"unpowered block (power/plating, power/toric_toughness, Rage, block potions)
   is not doubled on either side"*.
   **Correct verdict: `gap`, `"live": true`, grade B (state divergence).**
   Issue text should say: C#'s `IsCardOrMonsterMove()` is `Move` alone
   (`ValuePropExtensions.cs:23-26`), so an `Unpowered | Move` block gain **does**
   pass UnmovablePower's own gate and **is** doubled; the sim never reaches the
   listener because `BlockCmd.apply` (`sts2_rl/cmds.py:145`) gates on
   `is_powered_attack`. The listed examples are only *half* right — block potions
   and Plating use `NON_CARD_UNPOWERED` (no `Move`) and really are undoubled on
   both sides; `Entrench` is `Unpowered | Move` and is not. Cite the executed
   20-vs-30 above and the Defend control. The record's rollup is already `gap`
   (`ModifyBlockMultiplicative`), so **no rollup change** — but the hook entry's
   issue text should absorb the new site.
2. **`audit/records/seam/creature_card_cmds.json`**, guard **G1 (LIVE)** — its
   census of looser-gating listeners names `Vambrace.cs:59-63` and
   `PaelsLegion.cs:132-134` and **omits `UnmovablePower.cs:21-41`**. Add it, and
   add the liveness upgrade: the Entrench × Unmovable pair needs **no relic at
   all**, so the mechanism is live in a pure Ironclad-pool run rather than only
   for a player holding Vambrace. Verdict unchanged (`gap`, LIVE).
3. **`sts2_rl/powers.py:1086-1088`** (gap-fix stream) — `UnmovablePower`'s
   docstring states the false premise verbatim: *"unpowered block like
   Plating/Rage is unaffected — the sim only consults block multipliers for
   powered card/move block"*. It is the classic PROMPT.md bug class 12/24 shape:
   the comment is what talked the audit out of the gap. The fix is the one
   `creature_card_cmds` G1 already prescribes — give `modify_block_*` a `props`
   parameter and let each listener self-gate, rather than flipping the call-site
   `if` (which `brilliant_scarf` G1 needs pointing the other way).

### C2 — the A9 vocabulary question outside relic (cross-tier recommendation)

The relic tier is now internally consistent on "a C# member that is dead in the
source is `faithful`, not `waiver`". Tier-wide the split is roughly **53 `waiver`
vs 4 `faithful`**, concentrated in ~49 `power/*` sites plus `seam/power_cmd`, and
**8 records roll up to `waiver` solely on an `IsVisible` entry** — i.e. those eight
rollups are wrong under the settled vocabulary and would become `faithful`.

Recommendation to the power and seam owners: adopt the same ruling, with the
boundary the relic tier wrote into its entries — **dead member ⇒ `faithful`;
multiplayer gate ⇒ `waiver`.** The distinguishing test is executable: *can the
member vary in any run of the shipping game?* `IsVisibleInternal` cannot (zero
overrides anywhere); `Players.Count` can. `harness.py validate` accepts the flip
for **guards** with no `maps_to`; a `faithful` **hook** still needs one
(`harness.py:927-928`), so a hook-level flip needs a `maps_to` such as
`"no sim counterpart; the C# member is dead in the source"`.

### C3 — additional gaps found while re-deriving

**AUTO-KEEP-REVERSE — two new LIVE gaps, both recorded in relic records
(`toolbox` N4, `choices_paradox` G6), both previously `faithful`.**

The A1 work made the discriminator explicit — the sim can model a decline exactly
when the purpose is in `SKIPPABLE_PURPOSES`; the C# screen is declinable exactly
when `MinSelect` is 0 (`CardSelectorPrefs.cs:63-67`: the 2-arg ctor is
`this(prompt, n, n)`) or `canSkip: true` (default **false**,
`CardSelectCmd.cs:216`). Sweeping all 23 relic `select_cards` call sites against
their C# prefs turned up two sites pointing the **other** way — the sim offers a
decline the game forbids:

- **`relic/toolbox` N4 (LIVE, grade B).** `Toolbox.cs:28` calls
  `FromChooseACardScreen(context, cards, player)` with `canSkip` defaulting to
  false, so the game forces one of three Colorless cards.
  `sts2_rl/relics/toolbox.py:28` uses purpose `"obtain"`, which IS skippable, and
  the combat inherits the run's driver selector
  (`create_combat(card_selector=self.card_selector)`, `run.py:1154`), so
  `legal_actions()` (`driver.py:154-158`) publishes a SKIP index. A policy that
  takes it starts turn 1 with one card fewer in hand. The old `faithful` reasoned
  about the *no-selector* fallback (`combat.py:576-581`), which is the test
  default, not the driver.
- **`relic/choices_paradox` G6 (LIVE, grade B).** `ChoicesParadox.cs:46` is
  `FromSimpleGrid(..., new CardSelectorPrefs(prompt, 1))` — the 2-arg ctor, so
  `MinSelect == MaxSelect == 1`, forced. Same `"obtain"` purpose, same skip.

**Fix (driver, not relic):** `"obtain"` is overloaded across one genuinely
skippable site (`hefty_tablet`, `HeftyTablet.cs:32 canSkip: true`) and two forced
ones, so the purposes have to be split. The remaining 20 relic selection sites are
clean — `remove` / `enchant` / `upgrade` / `transform` are all non-skippable in the
sim *and* all built with the 2-arg `CardSelectorPrefs` ctor in C#, and `claws` /
`glass_eye` / `lead_paperweight` / `lost_coffer` correctly use skippable purposes
for min-0 screens.

**One more thing the auto-keep mechanism touches that no relic record owns**
(report only, out of my scope): the sim's *own* reward screen force-grants relics
by the same house rule — `sts2_rl/rewards.py:474-479` (elite branch) and
`rewards.py:515-519` (`pending_reward_extras` RELIC branch, Punch-Off) both call
`run.add_relic` directly, where C# offers a skippable `RelicReward`. That is the
same mechanism at two sites with no owning record; whoever owns the rewards path
should carry the A1 verdict there too. The comment at `rewards.py:495-498` is the
one that states the house rule, and it is the premise every flipped entry rested on.

---

## Findings I rejected or amended

| finding | disposition |
|---|---|
| **A9 `winged_boots` `IsAllowed` `waiver → faithful`** | **REJECTED.** `Players.Count == 1` is a multiplayer gate, which binding rule 1 names as the canonical waiver, and unlike a dead member a player count can genuinely differ in the shipping game. Flipping it would contradict every `player != base.Owner` waiver in the tier. Left `waiver`; the boundary is now written into the VOCAB paragraph of the nine entries A9 did flip. |
| **A8 "either match the two siblings [`waiver`] or re-point at `NoModifyHooks`"** | **AMENDED.** Took the third option A8 itself flagged: A9's ruling makes all three `faithful`. The `NoModifyHooks` pointer is recorded in the entries as `relic/lasting_candy`'s business rather than re-pointed here. |
| **A6 "guard `G1`"** | **AMENDED** — the entry described is `fake_strike_dummy` **N1**; G1 was already a gap. |
| **A7 "guard `G`"** | **AMENDED** — the entry is `war_hammer` **N4**. |
| **A10 "guard `G`"** | **AMENDED** — the entry is `tuning_fork` **N6**. |
| **B2 "verdict likely survives"** | **AMENDED** — the verdict does **not** survive. With the premise corrected there is no divergence at all, so `hefty_tablet` G3 is `faithful`, matching `lead_paperweight` N4. |
| **B5 "dormancy still holds (Kaiser Crab arms never deal Unpowered damage)"** | **AMENDED** — the direction is the other way round. `SurroundedPower`'s owner is the *player*, so it modifies damage the player *receives*; dormancy holds because no ported unpowered damage source has a Kaiser Crab arm as its **dealer**. Same conclusion, correct mechanism. |
| **B8 "it means `sts2_rl/monsters/overgrowth/fuzzy_wurm_crawler.py:36-40`"** | **AMENDED** — by line number `36-40` matches the **top-level** copy; the overgrowth copy is `37-41`. Both are cited. |
| **A4's "44 gaps, 21 LIVE"** | **CONFIRMED with different numbers** — my regex counts 45 entries / 27 LIVE across 25 records. The conclusion (the majority side, by a wide margin) is unaffected. |

## Not settled

- **`live` is now populated only where this pass wrote a gap** (12 relic records).
  The other 192 gap records still carry liveness in prose only. Backfilling the
  boolean across the tier is a mechanical follow-up nobody has done.
- **No content-tier gap has a pin.** Every gap this pass created or confirmed —
  including the two new AUTO-KEEP-REVERSE sites and C1 — is unpinned, so fixing
  any of them will not flip a `strict=True` xfail red-to-green. `audit/README.md`
  already flags this as the cheapest thing to stop rotting; it remains true.
- **The rewards-path auto-keep sites** (`rewards.py:474-478`, `:513-517`) have no
  owning record in any tier. They are reported here and nowhere else.
- **`extra_sources` growth.** `backfill_sources.py --kind relic` added 145 entries
  across 30 records to pin the files my new citations lean on. That is rule 7
  working, but it also means those 30 records now go stale on edits to
  `cmds.py`/`run.py`/`driver.py` that they previously ignored. Expected, not a
  problem — noting it so the next `audit_status` stale count is not a surprise.
