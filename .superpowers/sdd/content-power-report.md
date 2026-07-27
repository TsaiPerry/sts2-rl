# Stream report — content audits: powers

Branch `audit-power`, worktree `c:\Users\Perry\Desktop\sts2-rl-power`, based on
`audit-pipeline` at `3d63f3b0`. Written 2026-07-26, updated as batches land.

**Status: COMPLETE — 134 of 134 units audited and committed.** The stream ran in
three passes: this session's first 45 units (sections 2-10 below), then two
concurrent continuation sessions in sibling worktrees that took the remaining 89
as disjoint halves. Both halves finished and merged back into `audit-power`
without conflict.

| | |
|---|---|
| units audited | **134 / 134** |
| unit rollups | 112 gap, 12 waiver, 7 faithful, 3 deliberate-divergence |
| entries (hooks + guards) | 1145 — 705 faithful, 248 gap, 149 waiver, 43 dd |
| gap rate | 84% of units carry at least one gap; 22% of entries are gaps |
| suite | 2476 passed / 31 xfailed, unchanged at every batch boundary |
| commits, first 45 | `e6170905`, `e9a046ad`, `62b0d42f` (+ `e90f112f`, `370ce70c`) |
| commits, half A (41) | `dfca8463`, `5ff2baf8`, `625e94bb` |
| commits, half B (48) | `c27003a4`, `8696d479`, `4f795978` |

**Where the detail lives.** Sections 2-10 of this file are the first 45 units
plus the census results, which are final for all 134. The two halves' per-unit
detail is in `content-power-report-a.md` (41 player-side units) and
`content-power-report-b.md` (48 enemy units), both committed alongside this file
and both worth reading in full — this file's sections 3, 4, 6, 8 and 10 have
been updated to carry their conclusions, but not their evidence.

Batches, in the order they were done and why: **1** the core buff/debuff set
(the sign-awareness question lives here), **2** the Ironclad card powers,
**3** the player-side `AfterSideTurnEnd` group that batch 1-2's census had
identified as the highest-yield remaining cluster. Batch 3 was chosen *by* the
report rather than in advance, which is the workflow to keep — and the A/B split
that followed was likewise chosen by the census, not by alphabet.

## 0. What the whole stream turned up, in one place

Three findings overturn or widen a **committed seam record**, and are the most
consequential output of the stream:

1. **`turn_structure` G8's AutoPrePlay half is LIVE, not dormant** (half A).
   G8's dormancy argument enumerates Whispering Earring and Imbued and misses
   `MayhemPower`, C#'s third ported `AfterAutoPrePlayPhaseEntered` implementer —
   and Mayhem *reads other turn-start listeners' output*. The game runs it at
   `CombatManager.cs:568`, strictly after `AfterSideTurnStart` (`:522`); the sim
   shares one `on_player_turn_started` slot, so the order is registration order.
   Three executed witnesses, incl. Prep Time × Mayhem (auto-played Strike deals
   9 vs 6).
2. **`power_cmd` G6 is LIVE** (half B), where its own text says no interaction
   is demonstrated. `AdaptablePower.ShouldAllowHitting` exists precisely so the
   reviving Test Subject receives no powers; the sim wires that predicate into
   `DamageCmd.deal` but not `PowerCmd.apply`, so Vulnerable 2 lands on the
   reviving boss (damage in the same window is correctly refused — the control).
3. **`power_cmd` G5 now has three reachable arithmetically-divergent witnesses**
   (half A: `rolling_boulder`, `automation`, `toric_toughness`) against a text
   that says "no currently-demonstrated collision"; and its documentation count
   is **3 of 11, not 2** — `SwipePower` documents the instancing too (half B).

Two systematic bug classes, each hitting many units:

4. **Wrong RNG stream.** Eight power units draw on a shared rng where C# names a
   stream — `hello_world`, `entropy`, `stampede`, `confused`, `juggernaut`,
   `calamity`, `aggression` (all `combat._rng`, half A) and `flutter`
   (`owner._rng` instead of `_move_rng`, half B). The correct accessor exists
   one line away in `combat.py` in every case. Any parity replay that touches
   one of these diverges.
5. **A before/per-hit hook ported onto an after/aggregate hook.** `thorns`,
   `curl_up`, `skittish` (first 45) and `suck` (half B, Fossil Stalker's 2-hit
   LASH deals 9 vs 6). Two consequences each: the killing-blow guard
   (`cmds.py:121`) suppresses the after-hook, and inline-granted effects become
   visible to later hits of the same card.

Both halves independently confirmed there is **no fourth non-dyadic
multiplicative factor** — see section 3, now closed for all 134 units.

## 1. The tool this stream added

`tools/audit/power_census.py` (committed in batch 1, follows
`dormancy_probes.py`'s pattern). Every number in every record and in this
report is re-derivable from it:

```
py tools/audit/power_census.py typing        # sign-aware-typing census, all 134
py tools/audit/power_census.py slots         # C# side-hook -> sim slot mapping
py tools/audit/power_census.py stack         # on_stack no-ops vs C# stacking
py tools/audit/power_census.py multipliers   # dyadic check on every factor
py tools/audit/power_census.py neg-appliers  # C# sites applying a power < 0
py tools/audit/power_census.py instance      # PowerInstanceType overrides
py tools/audit/power_census.py visible       # IsVisibleInternal overrides
py tools/audit/power_census.py unregistered  # Power classes absent from ALL_POWERS
py tools/audit/power_census.py overrides     # per-unit override list
```

Building it first was the right call and is the main process lesson: five of
the eight bug classes are *population* questions, and answering them by
census once beats answering them 134 times by reading.

## 2. Sign-aware power typing — the deliverable, complete for all 134 units

`py tools/audit/power_census.py typing`. `GetTypeForAmount`
(`PowerModel.cs:460-471`) has two arms that can disagree with a static
`power_type` attribute:

- **arm 1**, `StackType == Counter && AllowNegative && amount < 0` → `Debuff`.
  **3 ported powers qualify: `strength`, `dexterity`, `shriek`.**
- **arm 2**, `!AllowNegative && Type == Debuff && amount < 0` → `Buff`.
  **28 ported powers qualify.**

**Only two powers actually carry the defect: `strength` and `dexterity`.**

- `shriek` qualifies for arm 1 but is *inert*: its `Type` is already `Debuff`,
  so the arm returns the answer the static attribute already gives. Recorded
  as `faithful` with that reasoning in `audits/power/shriek.json`.
- All **28** arm-2 powers are inert too, and for a reason worth writing down:
  arm 2 is a *protective* rule in C#. Every duration tick goes through
  `PowerCmd.Decrement` → `ModifyAmount(-1)` → `ModifyPowerAmountReceived`, so
  without arm 2 an Artifact holder would try to intercept its own
  Vulnerable ticking down. The sim never reaches that code at all: `_tick` /
  `_tick_duration` (`powers.py:70-84`) decrement the field directly and bypass
  `PowerCmd`. Different mechanism, identical observable. Independently,
  `neg-appliers` finds **no Debuff-typed ported power is applied with a
  negative amount anywhere in the decompiled source** — the only five powers
  C# ever applies negatively are Strength, Dexterity, Focus (unported),
  Shrink and Thorns.
- `shrink` is the one power whose `AllowNegative` the sim gets **wrong**
  (C# `true`, sim absent → `False`). It is not a *typing* defect — at a
  negative amount Shrink's `StackType` flips to `Single`, so neither arm fires
  and both sides say `Debuff` — but it is a real gap through
  `ShouldRemoveDueToAmount`, and it is the sharpest one in this batch: a
  negative Shrink is C#'s **infinite-duration** encoding, and the sim deletes
  it on re-application. Executed: two `Shrink -1` applications give the sim
  `Shrink(-1)` then `None`, the game `Shrink(-2)`. Dormant only because the
  Shrinker Beetle's move machine plays `SHRINKER` exactly once.
- `thorns` is applied negatively by two ported monsters (`SpinyToad.cs:-5`,
  `Toadpole.cs:-SpikenAmount`) and is `AllowNegative == false`, so neither arm
  fires and both sides remove it at ≤ 0. Faithful.

**Consequence for the seam tier: `power_cmd`'s G1 and G2 stay dormant and
their trigger is confirmed as stated.** I looked for a second route and there
isn't one. Every sim site that applies Strength or Dexterity negatively is
either a monster targeting the player (Artifact needs a player-side source
that exists nowhere in the game) or an applier-less self-application (Lamp
needs `applier is player`). Porting `Malaise.cs:39` or `Resonance.cs:33`
remains the single named trigger.

## 3. Non-dyadic multiplicative factors — `hook_dispatch` G9's blast radius

The prompt asked for this loudly, so: **`py tools/audit/power_census.py
multipliers` finds exactly two non-dyadic literal factors, and a third
computed one.** All three are on **damage**; **every ported block multiplier
is dyadic**, so `hook_dispatch`'s block-site dormancy argument is unaffected.

| factor | site | note |
|---|---|---|
| `0.7` | `ShrinkPower` (`powers.py:1386`) | already G9's executed witness. C# computes `(100m - 30m)/100m` in decimal. |
| `0.1` | `SlowPower` (`powers.py:1261`) | the factor is `1.0 + 0.1 * cards_played`, so it is non-dyadic for most counts. **Not previously named by G9.** |
| computed | `VulnerablePower` + `CrueltyPower` (`powers.py:414-416`) | `1.5 + cruelty.amount / 100.0`. Non-dyadic for most Cruelty amounts (10 → 1.6, 30 → 1.8). **Not previously named by G9.** |

Dyadic and therefore safe: Weak `0.75`, Frail `0.75`, Colossus `0.5`, Flutter
`0.5`, Soar `0.5`, Diamond Diadem `0.5`, Surrounded `1.5`, Unmovable `2.0`,
No Block `0.0`, Gigantification `3`.

**Caveat on the census's own method, stated because it bit me:**
`float.as_integer_ratio()` has a power-of-two denominator for *every* finite
float, so the obvious dyadic test calls `0.7` dyadic. The committed probe
parses the literal with `Fraction(str(val))` instead. Anyone re-deriving this
number a different way should check that first.

**CLOSED for all 134 units.** Both continuation halves were asked to report a
fourth factor loudly and neither found one: half A's candidates (`no_block`
×0.0, `diamond_diadem` ×0.5, `unmovable` ×2.0, `gigantification` ×3) are all
dyadic, and half B enumerated 26 literal operands across the enemy powers of
which the only two non-dyadic are the two already named here. **`hook_dispatch`
G9's population is final at three, and all three are on damage** — every ported
*block* multiplier is dyadic, so G9's block-site dormancy survives the full
census.

## 4. LIVE gaps found (all executed, all on ported content)

Sections 4.1-4.15 below are the first 45 units. The two halves add **13 more
live gaps**, evidenced in their own reports: half A's `mayhem` (see section 0),
`plating`, `nostalgia`, `rolling_boulder`, `automation`, `toric_toughness`,
`retain_hand`, `free_attack`, `unmovable`, `buffer` and the seven-unit
`combat._rng` class; half B's `rampart`, `flutter`, `adaptable`,
`minion`/`reattach` and `suck`. Two of half B's are worth restating here because
they change *run outcomes* rather than intermediate state:

- **`rampart` drops `RampartPower.cs:23`'s `PlayersTakingExtraTurn` guard.**
  With ported Pael's Eye the sim grants the Turret Operator 25 block on the
  extra turn; the game grants 0.
- **`minion`/`reattach` have no sim hook for `ShouldOwnerDeathTriggerFatal`**, so
  Feed into a Minion-marked Tough Egg gives +3 max HP where the game gives 0 —
  and `adaptable` diverges the *other* way, the game paying out for Feeding the
  Test Subject where the sim does not, which contradicts `cards/feed.py`'s own
  docstring.

1. **`ritual` — the skip-first-trigger flag keys on the wrong thing.**
   `RitualPower.cs:36-43` sets the skip whenever **`Owner.IsEnemy`**; the sim
   (`powers.py:194-196`) sets it when the applier is on the opposing side.
   Every ported Ritual source is a monster buffing *itself*, so the sim's test
   is false exactly where C#'s is true. Executed with the ported Calcified
   Cultist: after one round the sim shows `Strength(2)`, the game shows none.
   Damp Cultist (Ritual 5) and Devoted Sculptor are the same shape.
2. **`thorns` — C#'s `BeforeDamageReceived` ported onto `on_damage_received`,
   and the `IsPoweredAttack` gate dropped.** Two executed consequences: a
   99-damage Strike into a 3-HP Thorns-5 enemy costs the sim's player 0 HP and
   the game 5 (the sim's after-damage hook is skipped on a killing blow, C#'s
   before-damage hook is not); and 3 unpowered non-card damage with
   `dealer = player` costs the sim's player 5 and the game 0. Reachable from
   the ported Ironclad card Juggernaut against a Toadpole or Spiny Toad.
3. **`rupture` — the `CurrentSide == Owner.Side` guard is missing.**
   `RupturePower.cs:47` makes Rupture pay out only for damage taken during the
   owner's own turn, i.e. self-inflicted. The sim pays out for every enemy
   attack that gets through, turning a self-harm payoff card into a free
   Strength engine. Its `BeforeCardPlayed`/`AfterCardPlayed`
   accumulate-then-apply-once deferral is also absent, so even the in-scope
   case grants Strength mid-card. `InfernoPower` has the identical guard in C#
   and the sim **does** implement it there (`powers.py:757-759`), so the
   concept and the accessor both exist — this is an omission, not an absence.
4. **`feel_no_pain` and `curl_up` — block gained without `props`.** Both call
   `BlockCmd.apply` with no `props`, which defaults to `ValueProp.MOVE`
   (`cmds.py:143-144`) and so runs both block-modifier families, where C#
   passes `ValueProp.Unpowered`. Feel No Pain 3 under Dexterity 3 gives the sim
   6 block and the game 3; under Frail the sim gives 2 and the game 3. **Eight
   sibling powers pass `UNPOWERED` correctly** (Crimson Mantle, Rage, Plating,
   Toric Toughness, Skittish, Crab Rage, Rampart, Blocked Off), so this is a
   two-call-site omission and a cheap fix.
5. **`curl_up` — the block is granted inline instead of after the card play.**
   C# latches the card in `AfterDamageReceived` and gains the block in
   `AfterCardPlayed`; the sim gains it immediately, so the *second and later
   hits* of a multi-hit attack are absorbed by block the game has not granted
   yet. Also drops the `IsPoweredAttack` and `cardSource == null` guards and
   never sets `LouseProgenitor.Curled`.
6. **`demon_form`, `crimson_mantle`, `inferno` — pre-draw turn-start slot.**
   The sim's `on_player_turn_start` (`player.py:169`) is pre-draw; C#'s
   `AfterSideTurnStart` / `AfterPlayerTurnStart` are post-draw
   (`CombatManager.cs:522` vs `:514`). Executed witness for Demon Form using
   two ported Ironclad cards: with Hellraiser auto-playing Strikes as they are
   drawn, the turn after Demon Form 2 lands the sim deals 24 damage
   (enemy 41 → 17) and the game 18 (41 → 23). For Crimson Mantle and Inferno
   the self-damage can cancel a hand draw the game already made, which is
   conformance-visible even when nothing dies. **The sim already has the right
   slot and does not use it: `on_player_turn_started` (`player.py:186`).**
7. **`dark_embrace` — the `causedByEthereal` deferral is missing.**
   `DarkEmbracePower.cs:37-60` banks ethereal-caused exhausts and draws for
   them at side end, *after* the flush, and the source comment says that is
   deliberate. The sim draws immediately, so those cards are flushed away. The
   draw count is also hard-coded to 1 where C# draws `Amount`.
8. **`aggression` — wrong RNG stream and wrong algorithm.**
   `AggressionPower.cs:28` is `UnstableShuffle(Rng.CombatCardSelection).Take(N)`;
   `powers.py:514` is `random.sample` on the shared unseeded combat rng. Both
   the stream and the selection algorithm differ, so any replay that plays
   Aggression diverges and every later shared-rng draw is perturbed.
9. **`corruption` — a Late-phase cost modifier flattened, and a pile decision
   replaced by an after-the-fact move.** `Nostalgia` runs first in the sim's
   `modify_card_play_result_pile` chain and can move the Skill to the draw
   pile, after which Corruption's `card in discard_pile` test fails and the
   Skill is never exhausted. Both are ported Ironclad-pool powers.
10. **`no_draw` — removed at `BeforeTurnEnd` instead of `AfterTurnEnd`**, so a
    turn-end draw the game blocks succeeds in the sim.
11. **The whole player-side `AfterSideTurnEnd` group, via one concrete route
    found in batch 3.** `StampedePower` (`powers.py:1025-1041`) auto-plays
    Attack cards from *its own* `on_player_turn_end`, and
    `_process_turn_end_cards` (`combat.py:658`) runs more card effects
    immediately after — both *before* the sim removes or resets these powers,
    and both *after* the game does (`Hook.AfterTurnEnd` at
    `CombatManager.cs:1307`). So `rage` (block per Attack), `one_two_punch` and
    `duplication` (double the play), `tender` (restores Strength), `juggling`
    (counts Attacks), `ringing` and `tangled` (clear card afflictions) are all
    reliably present for those turn-end plays in the game and present in the
    sim only if hook-registration order happens to favour them. `constrict` and
    `demise` deal *damage* in that slot, so a lethal tick cancels turn-end card
    effects the game already ran.
12. **`rebound` — the same pile-hook defect as `corruption`, with an extra
    consequence.** `NostalgiaPower` uses `modify_card_play_result_pile`
    (dispatched first, `combat.py:510`) and Rebound reaches into the piles from
    `on_card_played` instead, so Nostalgia moves the card first and Rebound
    finds nothing in the discard pile — getting its effect for free *and*
    keeping its stack, where C# consumes exactly one.
13. **`tangled` — the sim adds an `Affliction == null` test C# does not have.**
    `TangledPower.cs:23-30` afflicts every Attack unconditionally and
    *overwrites*; `powers.py:1476` skips already-afflicted Attacks. After
    Ringing (also ported) the game re-afflicts Attacks as Entangled and taxes
    them; the sim leaves them Ringing and taxes nothing.
14. **`skittish` — `AfterAttack` ported onto `on_damage_received`**, so the
    block lands per hit instead of after the attack command, absorbing later
    hits of a multi-hit card. Identical defect to `curl_up`'s, and the sim's
    `after_attack` slot (`hooks.py:361-370`) exists and is used by Vigor and
    Gigantification.
15. **`disintegration` — the only unit losing both a phase and a slot.** It is
    `AfterSideTurnEndLate`, i.e. deliberately last in the game (the second
    complete pass at `Hook.cs:1284-1291`); the sim fires it in the earliest of
    the three places it could go. Dormant only because nothing ports a
    Disintegration applier.

**A new bug class this batch surfaced — `all_cards` misses the Play pile.**
`ringing`, `smoggy` and `tangled` all sweep `player.all_cards`, which is
`hand + draw + discard + exhaust` (`player.py:100-103`), where C#'s
`PlayerCombatState.AllCards` is those four **plus Play**
(`PlayerCombatState.cs:70-80`). This is `PROMPT.md` bug class 7 (pile limbo) in
its *power* form, and it is sharpest on `smoggy`: its affliction sweep runs
from `AfterCardPlayed` while the triggering Skill is itself mid-resolution, so
in the game that Skill is in the Play pile and *is* Smogged, and in the sim it
is in neither `all_cards` nor the discard pile yet and is skipped — so an effect
that returns it to hand can replay it where the game would refuse.

## 5. The systematic finding: side-hook → sim-slot mapping

`py tools/audit/power_census.py slots`. **54 of the 134 ported powers override
a C# side-scoped turn hook. 19 of those implement it with a per-creature sim
slot, or with no matching slot at all.** Resolved by following each dispatcher
to its `CombatManager` call site:

| C# override | dispatcher | correct sim slot (player / enemy) |
|---|---|---|
| `AfterSideTurnEnd` | `Hook.AfterTurnEnd` (`Hook.cs:1267`) | `after_player_turn_end` (`combat.py:665`) / `on_enemy_side_end` (`combat.py:345`) |
| `BeforeSideTurnEnd` | `Hook.BeforeTurnEnd` | `on_player_turn_end` (`combat.py:654`) / — |
| `AfterSideTurnStart` | `Hook.AfterSideTurnStart` (`CombatManager.cs:522`) | `on_player_turn_started` (`player.py:186`) / — |
| `BeforeSideTurnStart` | `Hook.BeforeSideTurnStart` (`CombatManager.cs:458`) | `on_player_turn_start` (`player.py:169`) / — |

Two distinct sub-classes, and they are worth separating because they have
different owners:

- **Enemy-side per-creature slots** (`on_enemy_turn_start`/`_end`) are
  `turn_structure`'s **G5** and I did not re-verdict them (rule 3) — the
  records cross-reference with the identical `gap` verdict. Affected:
  `asleep`, `battleworn_dummy_time_limit`, `demon_form`, `escape_artist`,
  `hardened_shell`, `hatch`, `plating`, `poison`, `regen`, `ritual`,
  `sandpit`, `slow`, `slumber`.
- **Player-side `AfterSideTurnEnd` mapped to `on_player_turn_end`** is *not*
  covered by any seam record I could find, and it is one slot too early —
  before the turn-end card effects and the hand flush, where C# is after both.
  Affected: `constrict`, `demise`, `disintegration`, `duplication`, `juggling`,
  `no_draw`, `no_energy_gain`, `one_two_punch`, `panache`, `rage`, `rebound`,
  `ringing`, `shrink`, `skittish`, `smoggy`, `tangled`, `tender`.
  **All 17 are now audited** (batches 1-3), and the group turned out to be
  worth prioritising: batch 3 found the concrete route (section 4 item 11) that
  turns the shape into a live gap for seven of them, and the fix is the same
  one line each — move to `after_player_turn_end` (`combat.py:665`).

## 6. Cross-record disagreements spotted under rule 3

1. **`turn_structure` G5 — SETTLED by half B: dormant, but for a different
   reason than the record gives, and one of my premises here was false.**
   I originally reported (correctly) that G5's dormancy rests on "every ported
   listener on these hooks self-filters to its own owner", which establishes
   only that *ordering within one hook* is unobservable and does not cover a
   listener whose effect changes state other creatures then read. I named three
   units as escaping that argument and asked for a two-dummy Battle Friend
   witness. Half B executed the question and both halves independently
   established that **the two-dummy witness is not constructible**:
   `BattlewornDummyEventEncounter.GenerateMonsters` (`:63-72`) returns a
   `_ReadOnlySingleElementList`, and that file is the only one in the game
   mentioning `BattleFriend`. So `battleworn_dummy_time_limit` does not make G5
   live. (It is also in **half A**, not half B — the continuation prompt's split
   list misassigned it.) `asleep` removes `Plating` from *itself*, so it was
   inside G5's original argument all along. That leaves `slumber` as the only
   real test, and `SLUMBERING_BEETLE_NORMAL` does field three creatures — it
   passes **only because the beetle is last in the enemy list**, which is where
   a per-creature turn-end slot coincides exactly with a side-end slot.
   **The correct dormancy argument is therefore the encounter rosters, not
   listener self-filtering**, and the seam record should be restated in those
   terms with its Battle Friend sentence deleted. Executed via half B's
   committed `tools/audit/power_slot_probes.py` (`rosters`, `g5-witness`,
   `enemy-hook-order`). G5's *verdict* stands.

1b. **`turn_structure` G8's AutoPrePlay half is LIVE, not dormant** — half A,
   see section 0 item 1. This is the stream's largest single correction to a
   committed seam record, and unlike G5 it changes the verdict, not just the
   rationale.

1c. **`power_cmd` G6 is LIVE** — half B, section 0 item 2. G6's own text says
   the interaction is undemonstrated; `adaptable` demonstrates it.

1d. **`power_cmd` G5 understates itself twice** — half A supplies three
   reachable arithmetically-divergent witnesses against "no currently-
   demonstrated collision", and half B corrects its documentation count from
   2 of 11 to 3 of 11 (`SwipePower`).
2. **`hook_dispatch` G9's factor population was incomplete.** It names Shrink
   `0.7` and reasons about block factors; it does not name `SlowPower`'s `0.1`
   or the `Vulnerable + Cruelty` computed factor. Both widen the damage-site
   gap. The *block*-site dormancy argument survives intact — see section 3.
3. **`power_cmd`'s G1/G2 trigger is confirmed, not contradicted** (section 2).
   Recorded here because a confirmation found by looking for a counterexample
   is worth as much as a contradiction.

## 7. Lessons for `tools/audit/PROMPT.md` (relic stream to fold in)

The relic stream owns `PROMPT.md`; I did not touch it. Proposed additions, in
descending order of how much time they would have saved me:

0. **New bug class — `all_cards` is not `AllCards`: the Play pile is missing.**
   See the end of section 4. Three of the 45 audited units sweep the sim's
   `player.all_cards` where C# reads `PlayerCombatState.AllCards`, which
   additionally contains the Play pile, so a card mid-resolution is invisible to
   the sim's sweep. This is bug class 7 in a form the current wording does not
   cover — the existing entry is about a *reshuffle* excluding a card in Play,
   not about an enumeration missing it. Checklist line: *when a unit walks the
   owner's cards, check the sim helper's pile list against
   `PlayerCombatState.cs:70-80` — `all_cards` omits Play.*
1. **New bug class — "the applied `props` are the block/damage typing."** Two
   of my ten live gaps are `BlockCmd.apply(...)`/`DamageCmd.deal(...)` calls
   that omit `props=ValueProp.UNPOWERED`, silently defaulting to powered and
   picking up Dexterity/Frail/Strength/Vulnerable the game excludes. Checklist
   line: *for every damage or block a unit deals, compare the C# `ValueProp`
   argument against the sim's `props=`; an omitted `props` is not a neutral
   default.*
2. **New bug class — side hooks vs per-creature slots.** Section 5's table
   belongs in `PROMPT.md`. `AfterSideTurnEnd` in particular is dispatched by
   `Hook.AfterTurnEnd`, which is not guessable from the name, and 19 of 134
   power units get it wrong. Checklist line: *resolve every `*SideTurn*`
   override to its `CombatManager` call site before believing a sim slot.*
3. **Bug class 3 is a population question, not a per-unit one.** Add the
   finding rather than the instruction: only `strength` and `dexterity` flip;
   arm 2 is inert because the sim's ticks bypass `PowerCmd`. That saves the
   next auditor from re-deriving it on all 134.
4. **Bug class 4 (visibility guards) can be closed game-wide.** `0 of the 260
   files under src/Core/Models/Powers override IsVisibleInternal`
   (`power_census.py visible`). `IsVisible` is provably always `true` for
   every power in the whole decompiled game, so an `IsVisible` guard is always
   a `waiver`. Worth stating once in `PROMPT.md` instead of being re-litigated.
5. **`PowerStackType.Single` does not mean "re-application is a no-op."** It
   means "Amount is hidden, and is always 1" (`PowerStackType.cs:10-13`);
   `PowerCmd.ModifyAmount:236` adds unconditionally with no `StackType` branch.
   **15 ported powers override `on_stack` to `pass` citing Single and are
   therefore wrong** (`power_census.py stack`). All 15 are currently dormant
   because none reads `Amount` — but the comment is repeated 15 times and will
   be copied a 16th.
6. **A unit-level `deliberate-divergence` needs the mechanism named, not just
   the outcome.** I used it 7 times, mostly for `_expire()` standing in for
   `PowerCmd.Remove` and for `StrengthCmd.apply` standing in for
   `PowerCmd.Apply<StrengthPower>(applier: Owner)`. Both are observably
   identical today and both would break a future `AfterRemoved` / applier
   reader. Worth a checklist line so they are recorded rather than waved past.

## 8. Roster and harness problems (I own neither; reporting per the contract)

1. **4 ported powers are invisible to the roster and to the RL observation.**
   `py tools/audit/power_census.py unregistered`: `ALL_POWERS` has 134
   entries, but 138 `Power` subclasses carry an `id`. Missing:
   `flex_potion`, `heist`, `speed_potion`, `thievery`. All four are live
   content (`HeistPower`/`ThieveryPower` drive the Gremlin Merc's gold theft,
   referenced by class rather than by id), so they work in play but:
   - the roster never enumerates them, and `harness.skeleton power/thievery`
     raises `StopIteration`, so **they cannot be audited at all** through the
     harness — they are 4 units of silent under-coverage in the 134 total;
   - `full_env.POWER_IDS` is built from `ALL_POWERS` (`full_env.py:147`), so
     they are **absent from the observation vector** the policy sees.
   The second half is an engine issue for the gap-fix stream, not an audit
   finding. `name_overrides.json` cannot express it — the fix is four lines in
   `ALL_POWERS`.
2. **`harness.list_overrides` misses overrides with a tuple return type.**
   Hit three times — `CorruptionPower` (batch 2), `ReboundPower` (batch 3) and
   `NostalgiaPower` (half A) — so it is a general defect, not a one-off.
   `ModifyCardPlayResultPileTypeAndPosition` returns
   `(PileType, CardPilePosition)`, and `_OVERRIDE_RE`'s
   `[\w<>,.?\[\] ]+?` return-type class does not match the parentheses — the
   **exact** 147-vs-146 defect `hook_dispatch` documented for `Hook.cs`, now
   reproducing in the content tier. The harness therefore *under-*enumerates
   required hooks, which is a silent-skip failure mode rather than a loud one.
   I added the hook to `audits/power/corruption.json` by hand; validation
   accepts extra keys, so the record is complete. Any other content unit whose
   C# file has a tuple-returning override has the same blind spot.
2b. **`harness.list_overrides` does not follow a C# base class** — found by
   half A, same silent-under-enumeration failure mode as the tuple defect above
   and arguably worse. Six half-A units subclass `TemporaryStrengthPower`; their
   own `.cs` file declares one member while the unit needs six verdicts, and the
   harness asks for one. Half A added the missing hooks by hand. Half B checked
   all 46 of its own C# files for both defects and found neither, so the
   exposure is confined to the player-side powers — but a future content tier
   (cards, relics) should assume both are present.
3. **`audit_status.py` reports no live/dormant split.** Not a defect, but with
   248 gap entries of which ~28 are live, `gaps` as a single column understates
   how much of the ledger is a queue and overstates how much is a fire.
4. **The `PROMPT.md` improvement loop never closed.** As of half A's last batch
   `tools/audit/PROMPT.md` was still **v1** — none of section 7's seven proposed
   lessons had landed, and both halves added more (half A seven, half B four).
   The relic stream owns the file and the powers stream cannot write it, so the
   pipeline has a structural bottleneck: the stream that learns the lessons is
   not the stream that can record them. Worth fixing at the pipeline level
   before the next content tier starts, or the same traps get paid for a third
   time. All proposed additions are collected in section 7 here plus section 7
   of report-a and section 6 of report-b.

## 9. Cost data

Wall-clock is dominated by the suite, not the auditing: `py -m pytest test/ -q`
is **~4m15s** and runs once per batch, so 2 batches spent ~8.5 minutes of the
session on a gate that (correctly) never moved off 2476 passed / 31 xfailed.

- **45 units in 3 batches**, and the batches got cheaper: batch 1's cost was
  front-loaded (reading `sts2_rl/powers.py` in full — 4221 lines — the four
  binding documents, and building `power_census.py`), batch 2 cost roughly half
  of it, and batch 3 less again because the recurring findings had already been
  named and could be cross-referenced instead of re-derived. That shared cost is
  now paid for all 134, which is the main reason the residual queue should be
  cheaper per unit than what is behind it.
- **Marginal cost is ~4 units per C# dump.** The efficient loop is:
  `grep -n "" X.cs | grep -v using` for 6-8 files at a time (real line numbers
  — an `awk` filter that renumbers makes every citation wrong, which I did
  once and had to redo), then write records through one Python filler rather
  than hand-writing JSON.
- **7 of 45 units needed execution to settle** (ritual, thorns ×2, shrink,
  demon_form, and the two slot-semantics probes, all in batch 1). Execution was
  decisive every time: it confirmed 5 gaps as live, corrected one wrong claim of
  mine (Shriek's stun *is* faithful — `TerrorEel.trigger_terror` does call
  `CreatureCmd.stun`, which I had asserted it did not before reading it), and
  falsified one claim in the *sim's own docstring* (Hellraiser's
  infinite-HP-enemy justification). Batches 2-3 needed none, because the
  mechanisms they found were already-executed ones being cross-referenced or
  were settled by reading two files side by side.
- **Gap rate 89% of units, 23% of entries.** The high unit rate is mostly
  cross-references to already-recorded seam mechanisms — a unit inherits `gap`
  from one cross-referenced entry — so the unit rollup is a poor severity
  signal. **Use the entry counts, not the unit rollups:** the 90 gap entries
  split roughly 15 live / 75 dormant, and the 262 faithful entries are the real
  measure of how much of the port is right.
- **One process cost worth naming:** the batch gate is dominated by
  `py -m pytest test/ -q` at ~4 minutes, run 3 times for ~12 minutes total, and
  it correctly never moved off 2476 passed / 31 xfailed because audits add no
  code. It is still the right gate — it is what would catch an accidental edit —
  but a resumed session should expect it, not be surprised by it.

## 10. Residual queue — EMPTY for auditing; 5 items handed to other streams

**All 134 auditable units are audited.** The queue below is kept as the merge
record — it is the plan the two continuation halves executed, and each item's
outcome is noted. What actually remains is not audit work:

1. ~~**The 4 unauditable units**~~ — **RESOLVED. Perry authorised the 4-line
   `ALL_POWERS` fix and all four are now audited** (`flex_potion`, `speed_potion`,
   `thievery`, `heist`), so the power tier is **138/138** with no coverage hole.
   Details and the three consequences worth knowing are in section 11.
2. **Three seam records need amending** by the seam session: `turn_structure` G8
   (verdict change — the AutoPrePlay half is live), `power_cmd` G6 (verdict
   change — live), `power_cmd` G5 (text: three demonstrated witnesses, doc count
   3 of 11), plus `turn_structure` G5's *rationale* restated in roster terms with
   its Battle Friend sentence deleted.
3. **`PROMPT.md` has 18 unlanded lessons** across this report's section 7,
   report-a's section 7 and report-b's section 6 — see section 8 item 4 on why
   the loop never closed.
4. **Two harness defects** (section 8 items 2 and 2b), both silent
   under-enumeration.
5. **The gap-fix stream's highest-value targets**, in order: the eight-unit wrong
   RNG-stream class (section 0 item 4 — one-line fixes, and every one of them
   breaks parity replay), the four before/per-hit hook mis-ports (section 0 item
   5), and `props`-omitted-on-block (`feel_no_pain`, `curl_up`). Report-a's
   section 10 handover names the three fixes that clear most of half A's live
   ledger.

### The plan as it stood, kept for the record

Ordered by expected yield, with what was already known about each group:

1. ~~The player-side `AfterSideTurnEnd` units~~ — **done in batch 3.**
2. **The 15 `on_stack`-no-op units** (section 7 item 5): `adaptable`,
   `burrowed`, `confused`, `corruption`✓, `dampen`, `hellraiser`✓, `hex`,
   `imbalanced`, `nemesis`, `no_draw`✓, `no_energy_gain`✓, `smoggy`✓, `soar`,
   `surrounded`, `the_gambit`. Five are done; the rest need only the
   "does anything read `Amount`" question answered, which is a one-grep answer
   per unit.
3. **The 9 `PowerInstanceType` units** (`power_census.py instance`):
   `automation`, `panache`✓, `rolling_boulder`, `sandpit`, `strangle`
   (`InstancedPerApplier`), `swipe`, `the_bomb`, `toric_toughness`,
   `withering_presence`. `power_cmd`'s G5 already owns the mechanism; what is
   per-unit is whether two simultaneous instances are reachable. `strangle` is
   the interesting one — it is the only ported `InstancedPerApplier` power.
   Panache is done and was a clean instance of the pattern: it neither
   documents the approximation nor works around it, unlike `toric_toughness`
   and `the_bomb`.
4. **The remaining enemy powers** (Overgrowth / Hive / Glory, ~50 units).
   Expect more of the `props` omission (bug class new-1) and more
   per-creature-slot instances. `asleep`, `plating` and `slumber` are already
   flagged by the slots census as touching *other* creatures' state in a
   side-hook slot, which is the section-6 disagreement with `turn_structure`
   G5 — settling those three would resolve it.
5. **The Colorless/potion-source powers** (~17 units). Lower yield: several
   are pure data (`minion`, `back_attack_left/right`, `improvement`) and the
   potion-sourced ones are dormant by scope, though the *power* still has to
   be audited.
6. **The 4 unauditable units** (section 8 item 1) — blocked on a 4-line
   `ALL_POWERS` fix that this stream must not make. **Still open.**

**Outcome:** items 1-5 are all done. Item 4 (the enemy powers) was the largest
and split off as half B; items 2, 3 and 5 were absorbed into halves A and B. The
prediction that the residual units would be *cheaper per unit* than the first 45
held — see the cost sections of report-a and report-b. The prediction that item 5
was "lower yield" did **not** hold: `mayhem`, `nostalgia` and `plating` are all
in it, and `mayhem` produced the stream's biggest finding.

## 11. The last four units — `flex_potion`, `speed_potion`, `thievery`, `heist`

Audited after Perry authorised the 4-line `ALL_POWERS` fix that section 8 item 1
asked for. **The power tier is now 138/138.** All four roll up `gap`; none of
their gaps is live. Three findings are worth carrying forward.

**1. `heist` is a death-time instance of the before/after hook mis-port**
(section 0 item 5, previously only seen on damage hooks). `Hook.BeforeDeath` is
called **unconditionally** at `CreatureCmd.cs:503`, two lines *before*
`Hook.ShouldDie` at `:505` decides whether the death stands. The sim's
`on_death` fires only inside the `should_die`-true branch (`cmds.py:96-105`), so
it is `AfterDeath` (`:519`), not `BeforeDeath`. Two divergences follow: a
prevented death queues the gold reward in the game and not in the sim, and a
creature killed *after* a prevented death has `BeforeDeath` called twice, so C#
queues the reward **twice**. Dormant, and established by enumerating the ported
`should_die` listeners rather than asserting it — `IllusionPower`,
`SteamEruptionPower`, `AdaptablePower`, `FairyInABottle` and Lizard Tail, none
of which reaches the Underdocks Fat Gremlin that owns `HeistPower`. Named
trigger: any ported death-preventer on a Fat Gremlin.

**2. `heist` carries a guard the sim ADDS that is load-bearing compensation for
a seam gap.** `powers.py:1679`'s `amount <= 0` test has no C# counterpart, and a
zero-amount Heist is very reachable (kill the Merc before it attacks, so
Thievery's total is 0 and Surprise moves 0 across). It is nevertheless
`faithful`, because C#'s `PowerCmd.Apply` returns early on `amount == 0m`
(`PowerCmd.cs:104`) and so never creates the power at all — while the sim, which
has no zero-amount no-op (`power_cmd`'s step-6 finding, re-confirmed here by
reading `cmds.py:288-326`), does create `HeistPower(0)` and relies on this guard
to stay silent. **Either fix alone is correct; removing the guard without fixing
`power_cmd` step 6, or vice versa, introduces a divergence.** This is the first
instance in the stream of two known defects cancelling, and it is an argument
for recording bug-class-8 "guards the sim adds" even when they verdict faithful.

**3. Two more `PowerInstanceType` units, making eleven not nine.** `thievery`
and `heist` are both `PowerInstanceType.Instanced` and were missing from section
10 item 3's list purely because they were missing from the roster. Both dormant
(one applier, one instance each). The `power_cmd` G5 population should read
**eleven**.

Also settled: `PlayerCmd.LoseGold` (`PlayerCmd.cs:178-199`) dispatches **no
hooks** — it writes history counters and assigns `player.Gold`. That is what
makes `thievery`'s deferred `combat.gold_stolen` debit `faithful` rather than a
divergence; had `LoseGold` fired a hook, the deferral would be a gap. Worth
knowing for any other unit that moves gold.

### Two process consequences

- **The harness base-class blind spot (section 8 item 2b) reproduced on both
  potion powers**: `list_overrides` enumerated one hook (`OriginModel`, the only
  member the `.cs` file declares) where each unit needs six. That is 8 of the
  units audited in this stream hit by the same defect — it should be the first
  harness fix, ahead of the tuple-return one.
- **Any engine edit re-stales the whole tier.** Applying the `ALL_POWERS` fix in
  the audit worktree moved `powers.py`'s hash and `audit_status` immediately
  reported **134 stale**. The four new records are therefore hashed against the
  *committed* `powers.py`, and they sit as roster-invisible orphans (valid, but
  not counted: `validate` sees 143 records while `--kind power` reports 134)
  until the engine fix lands on this branch. Whoever merges the fix must re-hash
  all 138 records in the same commit. This coupling will bite the gap-fix stream
  on every change it makes, and is worth a `harness.py --rehash` subcommand.
- **`vocab.json` is written as a side effect of importing the sim, and reverting
  the code alone leaves a broken tree.** `frozen_ids` (`vocab.py:102-120`)
  *persists* newly-seen ids on every import. Applying the `ALL_POWERS` fix here,
  importing once, then reverting `powers.py` left `vocab.json` holding four ids
  the registry no longer had — and because `merge_frozen` deliberately *keeps*
  frozen ids missing from the registry as dead slots, `POWER_IDS` was 138 against
  `ALL_POWERS`'s 134 and `test_full_env.py::test_full_power_vocabulary_triples`
  failed. **Revert both files or neither.** This is the only way this stream
  managed to move the suite off baseline, and it is a trap for anyone who
  experiments with a registry edit in an audit worktree. On the engine branch the
  `vocab.json` append is correct and belongs in the same commit.

## Review fix pass (2026-07-26)

Six targeted corrections from the post-approval review, applied to
`audit/records/power/*.json` and `audit/records/seam/creature_card_cmds.json`
only. The tier was not re-audited. Every liveness claim below was executed.

**FIX 1 (critical) — `adaptable` / `illusion` / `steam_eruption` are one
mechanism, and its shared observable is LIVE.** All three implement a C#
`AfterDeath` body by returning `False` from `should_die` (`powers.py:3365-3369`,
`:1566-1570`, `:2016-2020`), so all three execute the sim's death-*prevention*
branch (`cmds.py:106-113`) where C# executes the *real-death* branch
(`CreatureCmd.cs:505-559`) — and all three C# bodies sit behind
`!wasRemovalPrevented`, i.e. are explicitly excluded from the branch the sim
runs. `steam_eruption`'s `AfterDeath` was `deliberate-divergence` on the
rationale that it "repairs the only observable it produces"; that is false three
ways (it repairs the HP display only; the repair runs from an
`on_damage_received` dispatch the game deliberately skips on a killing blow,
`CreatureCmd.cs:392`; and it does not fire at all on the non-damage kill path),
so it is now `gap`, LIVE. All three carry the same verdict and cross-reference
each other. **The shared witness:** `Hook.AfterDeath` is dispatched to *every*
listener on **both** C# branches (`:519` and `:566`) and in the sim on
**neither** — `GremlinHorn.cs:24-32` has no `wasRemovalPrevented` guard, so the
game grants +1 energy and draws a card on every Test Subject / Waterfall Giant /
Eye with Teeth / Parafright death while `relics/gremlin_horn.py:18-22` never
runs. Feed is the second witness for `adaptable` and `steam_eruption`
(`DamageResult.cs:89-99` documents `WasTargetKilled` as true even when the death
is prevented). Two smaller divergences added as guards on all three: the sim's
`hp = 1` floor vs C# leaving the creature at 0 and re-entering
`KillWithoutCheckingWinCondition` up to ten times (`CreatureCmd.cs:560-571`), and
the non-damage kill path (`cmds.py:191-205`).

**FIX 2 (important) — the two engine-wide death-time absences now carry a
verdict.** Both were prose-only in `content-power-report-b.md` section 3c and
reached neither `audit_status` nor the gap queue. Filed as steps on
`seam/creature_card_cmds`, which already owns the sibling *Escape* strip at step
8. Step **8b** (`gap`, **LIVE**): `ShouldPowerBeRemovedAfterOwnerDeath` inverted
by omission — C#'s default is `true` (`PowerModel.cs:637-640`) and
`CreatureCmd.cs:533-537` strips through `Creature.RemoveAllPowersAfterDeath`
(`Creature.cs:668-671`) then awaits each `AfterRemoved`; the sim never strips.
Executed: a Decimillipede segment given Vulnerable 3, killed, and reattached
comes back at 25 HP *still Vulnerable 3*, where nothing in the game vetoes the
strip. Step **8c** (`gap`, dormant with a named trigger):
`ShouldStopCombatFromEnding` has no sim hook at all (`CombatManager.cs:196` /
`Hook.cs:2442-2452` vs `combat.py:272-277`); all five ported overrides are paired
with a death prevention or a mid-death spawn, so the outcome coincides today.
Cross-referenced from `adaptable`, `minion`, `painful_stabs`, `reattach`,
`steam_eruption` (8b) and `adaptable`, `infested`, `steam_eruption`, `stock`,
`surprise` (8c); those per-power verdicts are unchanged.

**FIX 3 (important) — `the_bomb`'s `InstanceType` dd → `gap`.** Two live fuses
are trivially reachable (a ported non-exhausting Colorless Skill played on two
consecutive turns). Executed: the sim holds one `the_bomb` with fuses
`[[2,40],[3,40]]` and `amount = min() = 2`; C# holds two `TheBombPower`
instances with Amount 2 and 3. The damage is reproduced exactly, the **state** is
not, and `full_env.py:412` encodes one signed amount per power id, so the game's
state cannot even be represented. The identical G5 mechanism is `gap` on
`rolling_boulder`; the two now agree and cross-reference.

**FIX 4 (important) — `speed_potion`'s LIVE tag, and the self-contradicting
potion waiver.** (a) The `AfterSideTurnEnd` slot gap's verdict is inherited under
rule 3 from `setup_strike`, but that witness is a *Strength* witness; this unit's
Dexterity leg is dormant with a named trigger. Enumerated: Dexterity's only sim
consumer is `modify_block_additive`, `BlockCmd.apply` dispatches the
block-modifier families only when `is_powered_attack(props)`
(`valueprops.py:47-49`), all four ported turn-end block relics pass
`ValueProp.UNPOWERED`, an AST sweep of every `on_player_turn_end` finds only
`PlatingPower` (also unpowered, owner-filtered), and none of the ten ported
`on_turn_end_in_hand` bodies gains block. (b) The waiver claiming to waive "only
the reachability of its one applier" is logically incompatible with any LIVE tag
and is stale — every one of these potions is ported *and* pool-registered. It is
narrowed to what is genuinely out of scope (the potion *unit's* own record;
there is no `audit/records/potion/` tier), with reachability stated
affirmatively. Applied at all **seven** sites carrying the guard (`buffer`,
`clarity`, `flex_potion`, `gigantification`, `radiance`, `shackling_potion`,
`speed_potion`) so the mechanism keeps one verdict per rule 3.

**FIX 5 (important) — `illusion`'s dormancy rested on a false grep.**
`monsters/hive/the_obscura.py:38-39` (Parafright) and
`monsters/overgrowth/fogmog.py:34-35` (Eye with Teeth) both apply
`IllusionPower`. Re-derived: the `ShouldPowerBeRemovedOnDeath` **debuff half is
LIVE, not dormant** (executed — an Eye with Teeth revives at 6/6 still holding
Vulnerable 3 where the game strips it); the `FollowUpStateId` / `REVIVE_MOVE`
splice *is* dormant, but for a real reason — both ported appliers have a single
self-looping move state (`Parafright.cs:44-47`, `EyeWithTeeth.cs:39-42`) and
neither sets the property; and the "Parafright is unported" waiver rationale is
corrected, the waiver now standing on presentation alone (the guarded body is one
`SfxCmd.Play`).

**FIX 6 (minor) — three smaller corrections.** `power/diamond_diadem`'s "the
applier's own condition" guard was a `waiver` delegating to
`audits/relic/diamond_diadem`, which does not exist (relic tier 0/258) — rule 4
made it a waiver over an unaudited verdict. Re-verdicted `gap` on its own
evidence and marked explicitly blocked-on-relic-tier: `DiamondDiadem.cs:78-84`
resets `CardsPlayedThisTurn` in `AfterCombatEnd` and `relics/diamond_diadem.py`
does not, so (executed) killing the last enemy with your third card of a turn
leaves the counter at 3 and silently suppresses the power for turn 1 of the next
combat. `power/flex_potion` and `power/speed_potion`'s "HARNESS: base-class hooks
not enumerated" guards moved out of the `waiver` class into a new top-level
`notes` list — a tooling defect is not a scope exclusion. The IsVisible
boilerplate (49 sites) is canonicalised: `IsVisible` is the non-virtual property
at `src/Core/Models/PowerModel.cs:150-160` (the file is directly under `Models/`,
**not** under `Models/Powers/`), the overridable virtual `IsVisibleInternal` is
at `:167`, and 260 is the `.cs` files directly under `src/Core/Models/Powers`,
**excluding** the 16 in `Powers/Mocks/` (276 including them; a recursive grep
covering `Mocks/` also returns 0). Rider: every power record cited the probes as
`py tools/audit/<probe>.py`, a path that does not exist; corrected to
`py audit/tools/<probe>.py` in 75 records.

### Recomputed power-tier verdict counts (138 records, computed, not recalled)

| scope | faithful | waiver | deliberate-divergence | gap |
|---|---|---|---|---|
| unit rollups | 7 | 11 | 3 | **117** |
| hook entries | 374 | 55 | 5 | 181 |
| guard entries | 353 | 99 | 40 | 86 |
| all entries (1193) | 727 | 154 | 45 | 267 |

Deltas against the pre-fix state: unit rollups `waiver` 12 → 11 and `gap` 116 →
117 (only `diamond_diadem` moved tier; the other two re-verdicts were on records
already rolling up to `gap`). Entries: `gap` 258 → 267 (+6 new guards from FIX 1,
+2 dd→gap, +1 waiver→gap), `waiver` 157 → 154 (−2 harness guards moved to
`notes`, −1 to `gap`), `deliberate-divergence` 47 → 45, `faithful` unchanged at
727. `audit_status` power gaps: 112 → **113**.

### Verification

- `py audit/tools/harness.py validate` → 428 records, **0 invalid**.
- `py audit/tools/audit_status.py` → power `134 total / 134 audited / 0 invalid /
  0 stale / 113 gaps / 0 unaudited`.
- `py -m pytest test/ -q` → **2522 passed, 38 xfailed** (the brief's 2478 predates
  concurrent test additions by the other streams; no failures, no regressions).
- `git diff --name-only main...audit-pipeline | grep "^sts2_rl/"` → empty.
