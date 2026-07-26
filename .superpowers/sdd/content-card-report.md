# Stream 3 — card content audits

Branch `audit-card`, worktree `c:\Users\Perry\Desktop\sts2-rl-card`.
Records under `audits/card/**`; probes under `tools/audit/card_probes.py`.

**Status: IN PROGRESS.** This file is written incrementally and committed with
each batch, so a session that dies at a usage limit leaves the findings behind.
The final section tracks what is done and what is left.

---

## 1. Progress

| Batch | Units | Rollups | Commit |
|---|---|---|---|
| 1 | aggression, alchemize, anger, anointed, apotheosis, apparition, armaments, ascenders_bane, ashen_strike, automation, bad_luck, barricade, bash, battle_trance, beat_down | 8 gap, 6 faithful, 1 waiver | `10946560` |
| 2 | beckon, blood_wall, bloodletting, bludgeon, body_slam, bolas, brand, break, breakthrough, brightest_flame, bully, burn, burning_pact, byrd_swoop, byrdonis_egg | 10 gap, 5 faithful | `716f023e` |
| 3 | calamity, caltrops, cascade, catastrophe, cinder, clash, clumsy, colossus, conflagration, corruption, crimson_mantle, cruelty, curse_of_the_bell, dark_embrace, dark_shackles | 8 gap, 6 faithful, 1 dd | `2c8b3c35` |
| 4 | dazed, debt, decay, defend, demon_form, discovery, disintegration, dismantle, distraction, dominate, doubt, dramatic_entrance, drum_of_battle, dual_wield, enlightenment | 11 gap, 4 faithful | `935bc8da` |
| 5 | enthralled, entrench, entropy, equilibrium, eternal_armor, evil_eye, expect_a_fight, exterminate, fasten, feed, feeding_frenzy, feel_no_pain, fiend_fire, fight_me, finesse | 7 gap, 8 faithful | `6cd22260` |
| 6 | fisticuffs, flame_barrier, flash_of_steel, folly, forgotten_ritual, frantic_escape, giant_rock, gold_axe, greed, guilty, hand_of_greed, havoc, headbutt, hello_world, hellraiser | 8 gap, 7 faithful | `f5e3e3e8` |
| 7 | hemokinesis, hidden_gem, howl_from_beyond, impatience, impervious, infection, infernal_blade, inferno, inflame, injury, iron_wave, jack_of_all_trades, jackpot, juggernaut, juggling | 9 gap, 5 faithful, 1 dd | `437c0134` |
| 8 | lantern_key, luminesce, mad_science, mangle, master_of_strategy, maul, mayhem, metamorphosis, mind_blast, mind_rot, molten_fist, neows_fury, normality, nostalgia, not_yet | 8 gap, 7 faithful | `708a6a37` |

`py tools/audit_status.py --kind card` after batch 8: **120 / 203 audited, 0
invalid, 0 stale, 69 with gaps.** `py -m pytest test/ -q` is unchanged at
**2476 passed, 31 xfailed** after both batches — audits add no executable code;
the only non-record file added is the probe script.

---

## 2. Cost data (requested after the first two batches)

Measured over batches 1–2 (30 units).

| Metric | Batch 1 | Batch 2 | Notes |
|---|---|---|---|
| Units | 15 | 15 | |
| Gap rate (unit rollups) | 8/15 = 53% | 10/15 = 67% | rollup, not per-entry |
| Units needing EXECUTION to settle | 5 | 1 | see below |
| Test-suite run | 250 s | 253 s | the single largest fixed cost per batch |

**Wall time.** Batch 1 took materially longer than batch 2 (roughly 2×) because
it paid all the one-off costs: reading `cards/base.py` and the `CardModel`
surface in full, reading the `creature_card_cmds` and `hook_dispatch` gap
lists, establishing what `CalculatedVar` / `CardEnergyCost` / `CreateClone` /
`CardSelectCmd` actually do, and writing the probe script. Batch 2 is the
steady-state figure. Excluding the fixed 4-minute suite run, steady state is
roughly **1.5–2 minutes of wall time per unit**, dominated by reading the two
sources rather than by writing the record.

**Tokens.** The dominant per-unit cost is reading the two sources, and cards
are small: a C# card model is 25–55 lines and a sim card 30–50. Read in bulk
(8 C# files per `cat -n` call, one sim module per call), a batch of 15 units
costs roughly 25–30 k tokens of source. Cross-file investigation — the greps
into `CreatureCmd.cs`, `PowerCmd.cs`, `CardEnergyCost.cs`, `hooks.py`,
`powers.py` that a single suspicious line forces — costs about as much again,
but AMORTISES: nearly every such lookup in batch 2 was already answered by
batch 1. Record emission is the cheap part. Call it **~4–5 k tokens per unit
including the record**, trending down.

**What this means for the pool.** 173 units remain, ~12 batches. The per-unit
cost is low enough that the binding constraint is context window, not effort
per unit: the accumulated cross-file knowledge (which is what makes later
batches cheap) is also what fills the window. Mitigation in use: pool-wide
probes that answer a question once for all 203 units, shared finding texts
reused verbatim across records so rule 3 is satisfied by construction, and
committing plus updating this report every batch.

**Units that needed execution to settle** (rule 5 — no unreachability claim
without running something):

- The five downgrade-sticky cards were found only by running the probe; the
  static read of `aggression.py` looks correct.
- `card/armaments` and `card/blood_wall`: needed the `unpowered-block` probe to
  confirm they are NOT in gap G1's blast radius.
- `card/bash`, `card/break`: needed the `dead-target-guards` probe plus a
  reachability chase through `ViciousPower` and `retained_after_death`.
- `card/anointed`, `card/beat_down`: needed the `shared-rng` probe to establish
  that the correct parity accessors exist and are simply not used.
- `card/brightest_flame`: needed reading `RupturePower` on both sides to
  overturn a seam record's dormancy claim.

---

## 3. Pool-wide findings (executed)

All four numbers below come from `py tools/audit/card_probes.py`, committed so
they are re-derivable.

### 3.1 `downgrade()` does not restore upgrade-toggled keywords — 5 cards, LIVE

`Card.downgrade` (cards/base.py:150-165) rebuilds printed state by zeroing
`upgrade_level`, re-running `_init_vars`, and re-applying upgrades. A card
whose `_on_upgrade` writes a KEYWORD flag that `_init_vars` does not re-seed
keeps that flag forever. C# `CardModel.DowngradeInternal` rebuilds the whole
keyword set from canonical (`_keywords = cardModel.GetKeywordsWithSources(
KeywordSources.Local).ToHashSet()`, CardModel.cs:2143).

```
downgrade: 5 of 203 sim cards do not restore
  aggression: innate: False -> True
  apparition: is_ethereal: True -> False
  hello_world: innate: False -> True
  juggling:   innate: False -> True
  wish:       retain: False -> True
```

LIVE — `downgrade()` has three ported callers: `events/reflections.py:40`
(registered `events/__init__.py:104`), `events/welcome_to_wongos.py:90`
(registered `events/__init__.py:135`) and `powers.py:3171` (DampenPower
downgrades every upgraded card in AllCards). All three act on arbitrary deck
cards. `anointed` shows the correct pattern (`self.retain = False` in
`_init_vars`), so the fix is one line per card.

`hello_world`, `juggling` and `wish` are in later batches; recorded here so the
finding survives even if those batches do not.

### 3.2 Gap G1's blast radius (block gained with `Unpowered`) — ONE ported card

```
unpowered-block: 3 C# card(s) gain block with Unpowered
  Entrench.cs [PORTED as card/entrench]: GainBlock(Owner.Creature,
      Owner.Creature.Block, ValueProp.Unpowered | ValueProp.Move, cardPlay)
  PillarOfCreation.cs [not ported]: 3m, ValueProp.Unpowered
  Shroud.cs        [not ported]: 2m, ValueProp.Unpowered
```

So `creature_card_cmds` G1 — `BlockCmd.apply` gating the whole block-modifier
dispatch on `is_powered_attack` (cmds.py:145-147) — touches exactly
**card/entrench** among ported cards, which is already the seam's own named
witness. Two unported cards (Pillar of Creation, Shroud) would join it. Every
other block-gaining card audited so far (armaments 5, blood_wall 16) uses a
plain `BlockVar(n, ValueProp.Move)` and is correctly doubled by Vambrace on
both sides. `card/entrench` is in a later batch and will carry the finding.

### 3.3 Gap G4's blast radius (play count > 1)

The sim's play count is `hooks.modify_card_play_count(card, enemy,
1 + card.base_replay_count)` (combat.py:469-470), and the C# bracket that G4
says fires per iteration is `Hook.BeforeCardPlayed` / `AfterCardPlayed` inside
`CardModel`'s Replay loop. The sources that can push a card above one play:

```
sts2_rl/cards/colorless_skills.py:322  card.base_replay_count += self._replay   (Hidden Gem)
sts2_rl/potions.py:1072                card.base_replay_count += 1
sts2_rl/enchantments.py:167, 232       modify_card_play_count                   (Spiral, Glam)
sts2_rl/powers.py:966, 3919            modify_card_play_count
sts2_rl/relics/throwing_axe.py:30      modify_card_play_count
sts2_rl/cards/drum_of_battle.py:48     play_count = ...modify_card_play_count(self, None, 1)
```

No card in batches 1–2 raises its own play count. **card/hidden_gem** (raises
`base_replay_count` on another card) and **card/drum_of_battle** (consults the
hook itself) are the two card units in the blast radius; both are in later
batches. Every other card is affected only passively, via Throwing Axe, the
Spiral/Glam enchantments, or the two powers — i.e. the blast radius is "any
playable card", and the seam's Throwing Axe + Pen Nib witness already pins it.

### 3.4 Cards drawing on the unseeded shared RNG — 21 classes

```
shared-rng: 21 sim card class(es) touch combat._rng
  cinder.py:             cinder
  colorless_attacks.py:  jackpot, seeker_strike, volley
  colorless_skills.py:   alchemize, anointed, beat_down, discovery, hidden_gem,
                         jack_of_all_trades, splash
  event_cards.py:        metamorphosis
  havoc.py:              havoc
  infernal_blade.py:     infernal_blade
  mad_science.py:        mad_science
  stoke.py:              stoke
  sword_boomerang.py:    sword_boomerang
  thrash.py:             thrash
  trash_heap_cards.py:   distraction, rip_and_tear
  true_grit.py:          true_grit
```

`CombatRng` already exposes the named parity accessors (`shuffle`,
`card_selection`, `targets`, `card_gen`, `energy`, `potion_gen`,
`monster_ai` — combat_rng.py:17-56), and in legacy mode they all alias the same
shared `random.Random`, so switching is behaviour-preserving for RL. Under a
string-seeded parity run each of these is a stream desync. Note `alchemize` is
a FALSE POSITIVE for the finding — it uses the correct
`rng_set.combat_potion_generation` and touches `_rng` only in the
`rng_set is None` fallback (colorless_skills.py:43-52). The remaining 20 are
audited as they come up; `anointed` (should be CombatCardSelection) and
`beat_down` (should be Shuffle, and is also missing StableShuffle's stabilising
pre-sort) are recorded in batch 1.

### 3.5 Liveness guards C# does not have — 41 classes

`py tools/audit/card_probes.py dead-target-guards` lists 41 sim card classes
that test `is_gone` / `is_dead`. They fall into three kinds, and only the second
is a divergence:

1. `if ctx.player.is_dead: return` mid-card — the sim bails between two effects
   where C# keeps going. Dormant everywhere so far (a genuinely dead player has
   already lost the combat on both sides). Recorded on blood_wall, bloodletting,
   brand.
2. `if not target.is_gone:` before applying a POWER — a real divergence.
   C# `Creature.CanReceivePowers` (Creature.cs:308-321) explicitly allows powers
   on dead creatures and refuses only for a REMOVED one. Ordinary kills agree
   (Kill removes the creature inside `CreatureCmd.Damage`, CreatureCmd.cs:409,
   523-525), but a corpse whose removal was vetoed
   (`ShouldCreatureBeRemovedFromCombatAfterDeath`; `retained_after_death`,
   cmds.py:100-104) stays powerable in C#. LIVE via `ViciousPower`, which draws
   on any Vulnerable its owner applies with no liveness test
   (ViciousPower.cs:19-26). Recorded on bash and break so far.
3. `[e for e in enemies if not e.is_gone]` — mirrors C#'s `HittableEnemies`.
   Faithful. `card/breakthrough` is the one card that writes `is_dead` here
   instead, so an escaped-but-alive enemy is still struck (dormant).

---

## 4. Gaps by unit, with live/dormant determination

### LIVE

| Unit | Entry | Gap |
|---|---|---|
| `aggression` | OnUpgrade | Innate survives `downgrade()`; the game rebuilds keywords from canonical. Evidence: §3.1. |
| `apparition` | OnUpgrade | Ethereal stays REMOVED after `downgrade()`. Evidence: §3.1. |
| `anger` | OnPlay | The copy is a fresh `AngerCard()` + replayed upgrades, not `CreateClone()`. C#'s clone deep-copies the Enchantment (CardModel.cs:1204-1209), the Affliction (1210-1214), the keyword set and the `_energyCost` object. A Spiral-enchanted Anger produces a Spiral-enchanted copy in the game and a vanilla one in the sim. Spiral accepts any Attack (enchantments.py:372-375) and `events/spiraling_whirlpool.py:46` attaches it. |
| `anointed` | OnPlay | Draws its Rare cards with `combat._rng.sample` instead of `Rng.CombatCardSelection` + `TakeRandom` (= `UnstableShuffle` then `Take`, IEnumerableExtensions.cs:17-20). Wrong stream AND wrong algorithm. |
| `beat_down` | OnPlay | `combat._rng.shuffle` instead of `StableShuffle(Rng.Shuffle)`. Three stacked divergences: wrong stream, missing the stabilising `list2.Sort()` (ListExtensions.cs:22-31), different Fisher-Yates variant. |
| `bash` | OnPlay | `if not target.is_gone` skips the Vulnerable on a removal-vetoed corpse; C# applies it and Vicious draws. Evidence: §3.5 kind 2. |
| `break` | OnPlay | Same mechanism, same verdict (rule 3). |
| `bolas` | BeforeHandDraw | C# returns the card from ANY non-hand pile via `CardPileCmd.Add(this, PileType.Hand)` (Bolas.cs:43-47); the sim's helper searches only draw and discard (colorless_attacks.py:532-535), so an EXHAUSTED Bolas never returns. Ported exhausters that can reach it: brand, burning_pact (both pass a null filter), second_wind, fiend_fire. `card/thrumming_hatchet` shares the helper and inherits the gap. |
| `breakthrough` | OnPlay | The 1 HP self-loss is hand-rolled (`p.hp = max(0, p.hp - 1)` + bare `on_hp_changed`, breakthrough.py:42-50) instead of `CreatureCmd.Damage(..., Unblockable\|Unpowered\|Move, this)`, so `on_damage_received` never fires and no damage modifier, cap or Buffer is consulted. `RupturePower.AfterDamageReceived` (RupturePower.cs:44-57, cardSource-null branch) gains Strength on any unblocked damage its owner takes, and the sim port listens on `on_damage_received` (powers.py:272-289). Breakthrough + Rupture diverges. |
| `brightest_flame` | guard | Makes seam gap **G6** live — see §5. |

### DORMANT (trigger named)

| Unit | Entry | Gap and what would make it live |
|---|---|---|
| `ascenders_bane`, `bad_luck`, `burn`, `byrdonis_egg` | ctor | Canonical energy cost **-1** maps to **0**. `CardEnergyCost.GetWithModifiers` returns early on `_base < 0` (CardEnergyCost.cs:100-103), so the game's unplayable card is immune to every cost modifier; the sim runs a base of 0 through the full chain (cards/base.py:222-232). `GetAmountToSpend()` clamps to 0 on both sides, so only READS diverge. All three ported cost readers agree today (`mummified_hand.py:25` and `potions.py:168` filter `> 0`; `event_cards.py:328` skips `<= 1`) and `infested_automaton.py:35` filters `pool_card_ids()`, which holds no curses/statuses/quests. **Live** as soon as anything reads an unplayable card's cost without a `> 0` filter. Applies pool-wide to every unplayable curse/status. |
| `bad_luck`, `beckon`, `breakthrough`, `burn` | CanonicalVars | A printed DynamicVar with no `_`-attribute in `_init_vars`, so `base_hp_loss` / `base_damage` report 0 / None. The DEALT number is right, so nothing in the game diverges — but `full_env.card_features` (full_env.py:455-489) encodes those properties into the observation, so a policy sees Bad Luck and Beckon as costing no HP and Burn as dealing no damage. **Dormant for game fidelity, live for the observation encoder.** One-line fix per card. |
| `anointed` | guard | Cards are moved Draw→Hand by direct list mutation instead of `CardPileCmd.Add`, so no pile-transition hook fires. The sim has no `after_card_changed_piles` listener at all, so nothing observable is dropped until one is ported. |
| `blood_wall`, `bloodletting`, `brand` | guard | `if ctx.player.is_dead: return` mid-card, which C# does not have. Dormant: the sim floors a death-prevented creature at 1 HP (cmds.py:106-112), so `is_dead` means the combat is already lost on both sides. |
| `breakthrough` | guard | AoE loop filters `is_dead`, not `is_gone`, so an escaped-but-alive enemy is still struck. Live with any ported escaping monster in a multi-enemy fight. |
| `apotheosis` | guard | The sim's `all_cards` omits the Play pile that C#'s `AllPiles` includes; they agree today only because the sim parks non-Power cards in the discard-pile limbo. Live if a POWER card is ever ported that auto-plays another card. |

### Waivers issued (and why they are genuinely out of scope)

Only one unit rolls up to `waiver`: **`card/alchemize`**, whose entire OnPlay is
potion procurement — explicitly out of scope per the shared contract. Its
record still states, for the record, that the sim uses the correct
`combat_potion_generation` stream and reproduces the create-then-maybe-drop
ordering, so nothing is being hidden behind the waiver.

**Presentation is NOT recorded as a waiver entry.** After batch 1 it became
clear that giving every `TriggerAnim` / `HoverTip` / `VfxCmd` line its own
guard entry pushes the unit rollup to `waiver` (rule 4: a rollup carries
`max(verdict)`), which drowns the signal — three otherwise-clean cards rolled
up `waiver` on nothing but animation triggers. Policy from batch 1 onward:
presentation is named inside the owning hook's rationale, so it is still
audited and visible, but does not carry a verdict. This is a candidate lesson
for `PROMPT.md` (§6).

---

## 5. Cross-record disagreement (rule 3)

**`creature_card_cmds` guard G6 is labelled DORMANT and is actually LIVE.**

The seam's verdict (`gap`) is correct and is not disputed; only its dormancy
argument is. G6 says:

> Dormant: the two in-combat callers are Brightest Flame
> (cards/brightest_flame.py:37) and PaperCutsPower (powers.py:2959), neither of
> which reaches a fatal magnitude, and the isFromCard Move flag exists for
> cards that are not ported.

That covers two of the three consequences of not routing through the damage
pipeline (the kill, and the `Move` flag) and misses the third, which is the
live one:

- C# `CreatureCmd.LoseMaxHp` deals the overflow as real damage —
  `Damage(choiceContext, creature, CurrentHp - newMaxHp, isFromCard ?
  (Unblockable|Unpowered|Move) : (Unblockable|Unpowered), null, null)`
  (CreatureCmd.cs:826) — which fires `Hook.AfterDamageReceived`.
- The sim's `CreatureCmd.lose_max_hp` (cmds.py:179-189) only clamps HP and
  calls `on_hp_changed`.
- `RupturePower.AfterDamageReceived` (RupturePower.cs:44-57) applies Strength on
  ANY unblocked damage its owner receives; with `cardSource == null` — exactly
  what LoseMaxHp passes — it takes the immediate-apply branch at line 48.
- **Rupture is ported**: `sts2_rl/cards/rupture_card.py`, power at
  powers.py:272-289, listening on `on_damage_received`.

Repro: play Brightest Flame at full HP holding Rupture. `newMaxHp <
CurrentHp`, so the game deals 1 damage and Rupture grants Strength; the sim
grants none. Both halves are ported Ironclad content.

Recorded as a guard entry on `audits/card/brightest_flame.json`. **`audits/seam/**`
is not edited** — this is for the seam owner to fold in.

---

## 6. Lessons for `tools/audit/PROMPT.md` (for the relic stream to apply)

The card stream does not own `PROMPT.md`. These are offered, not applied.

1. **The skeleton under-enumerates by design, and the prompt does not say so.**
   `harness.py list_overrides` matches `public\s+override` only
   (harness.py:51-55). Card models put almost everything behind
   `protected override`: `OnPlay`, `OnUpgrade`, `OnTurnEndInHand`,
   `CanonicalVars`, `CanonicalTags`, `ExtraHoverTips`, `IsPlayable`,
   `ExtraRunAssetPaths`. **Five of the fifteen units in batch 1 generated an
   EMPTY `hooks` map**, and a card like Bash — whose whole audit is its OnPlay
   and OnUpgrade — validates as complete with zero entries. Suggested prompt
   text: *"The skeleton's `hooks` map lists only `public override` members. Add
   an entry by hand for the constructor and for every `protected override` —
   `OnPlay`, `OnUpgrade`, `OnTurnEndInHand`, `CanonicalVars`, `CanonicalTags` —
   before you start. An empty or short `hooks` map is a bug in the skeleton, not
   a small unit."* This affects powers and relics too.
2. **Add "printed value vs modelled value" to the bug-class checklist.** Four
   cards in two batches declare a `DynamicVar` the sim never stores, inlining
   the literal at the use site. The dealt number is right, so a behaviour-only
   read passes it; but the sim's own printed-number API (`base_damage`,
   `base_block`, `base_hp_loss`, `magic_number`, cards/base.py:191-220) then
   lies, and `full_env.card_features` encodes it into the RL observation. Worth
   a checklist line: *"Every canonical var must have a stored counterpart, not
   just a correct number at the call site."*
3. **Add "downgrade round-trip" to the checklist.** Bug class 10 covers per-turn
   and per-combat reset timing but not the upgrade/downgrade round trip.
   `CardCmd.Downgrade` → `DowngradeInternal` rebuilds vars, cost AND keywords
   from canonical (CardModel.cs:2135-2148); any port that mutates state on
   upgrade must be checked for restore, not just for the upgraded value.
4. **Say what to do with presentation.** The prompt lists animation/SFX as out
   of scope but not how to record it. Recording each as a `waiver` entry drags
   the unit rollup to `waiver` (rule 4) and makes clean units look scoped-out.
   Recommend: name presentation inside the owning hook's rationale; reserve
   `waiver` entries for units where an out-of-scope area is the SUBSTANCE of the
   behaviour (card/alchemize is the only one so far).
5. **`-1` is a sentinel, not a number.** `CardEnergyCost` short-circuits every
   modifier on `_base < 0` (CardEnergyCost.cs:100-103). Any port that maps a -1
   canonical cost to 0 silently makes the card modifiable. Worth a line under
   "numeric constants".
6. **Prefer a pool-wide probe to 200 per-unit reachability claims.** Rule 5
   demands execution behind any unreachability claim. Written per unit that is
   200 scripts; written once per QUESTION it is four functions
   (`tools/audit/card_probes.py`) that answer for all 203. Recommend the prompt
   tell agents to write the probe at the level of the question, not the unit.

## 7. Roster problems

- **`card/sweep` is unmatched.** `harness.py roster card` reports
  `UNMATCHED card/sweep -> expected src\Core\Models\Cards\Sweep.cs`, which does
  not exist. The sim's `SweepCard` (sts2_rl/cards/sweep.py) is a 1-cost BASIC
  Attack hitting every enemy for 4. `LegSweep.cs` is a different card (2-cost
  Uncommon Skill, 11 block + 2 Weak) and is NOT the counterpart. Resolution is
  pending and will be recorded here; `tools/audit/name_overrides.json` is
  relic-stream-owned, so the card stream will not edit it.

## 7b. Additional live gaps from batches 3-4

| Unit | Entry | Gap |
|---|---|---|
| `clash` | IsPlayable | The predicate is right, the HOOK is wrong. C# `IsPlayable` is read only by `CardModel.CanPlay` (CardModel.cs:1759-1762) -- the MANUAL play path. `CardCmd.AutoPlay` checks only the Unplayable KEYWORD and `Hook.ShouldPlay` (CardCmd.cs:57-71), neither of which Clash implements, so an auto-played Clash fires in the game regardless of hand contents. The sim routes the gate through `should_play_card`, which `auto_play_card` DOES consult (combat.py:536, `auto_play=True`), so the sim discards it unplayed. Four ported auto-play sources reach it: beat_down, havoc, catastrophe, cascade. Fix shape: `if auto_play: return True`. |
| `catastrophe` | guard | The sim breaks its pick loop on combat-over; Catastrophe.cs has no loop-level bail and does the StableShuffle pick BEFORE `CardCmd.AutoPlay`'s own `IsOverOrEnding` return (CardCmd.cs:53-56). When an auto-played card ends the combat, C# burns a full StableShuffle per remaining iteration and the sim burns none -- a Shuffle-stream COUNT desync under parity. Opposite polarity to `beat_down`'s target-roll guard, where the sim is the one that skips a draw. |
| `debt` | HasTurnEndInHandEffect + OnTurnEndInHand | Both simply absent. The sim's docstring justifies it with "the sim has no gold", which is FALSE -- `RunState.gold` exists and `RunState.lose_gold` is implemented with the matching floor-at-zero semantics and a `PlayerCmd.LoseGold` citation (run.py:335-337), and ported events spend gold routinely. Debt is a strictly weaker curse in the sim, compounding across a combat and changing shop affordability. A textbook rule-1 case: "not modelled" is a gap, never a waiver. |
| `enlightenment` | OnPlay | The unupgraded branch writes a RELATIVE delta (`add_cost_this_turn(1 - card.energy_cost)`) where C# registers an ABSOLUTE LocalCostModifier of 1 (CardEnergyCost.cs:197-203). They agree until the card's base cost changes within the same turn -- which `armaments` and `apotheosis` both do to cards in hand, and several Ironclad cards drop a cost on upgrade. The sim already has the absolute primitive (`Card.set_cost_this_turn`, cards/base.py:252-258). |
| `drum_of_battle` | AfterCardExhausted | The exhaust payout feeds a bare `1` into `modify_card_play_count` where C# feeds `GetEnchantedReplayCount() + 1` = `Enchantment?.EnchantPlayCount(BaseReplayCount) ?? BaseReplayCount` plus one (CardModel.cs:1129-1132, 2015-2021), and also drops the `AfterModifyingCardPlayCount` notification. Hidden Gem on Drum of Battle pays out twice in the game and once in the sim. This is gap G4's card-side blast radius. |
| `discovery`, `distraction` | OnPlay | Both generate from the unseeded shared `combat._rng` where C# names `Rng.CombatCardGeneration`, and `random_pool_cards` uses `rng.sample` (pool.py:158) rather than GetDistinctForCombat's draw sequence. Same mechanism as `anointed` / `beat_down`; 4 of the 21 shared-RNG cards are now audited and all 4 are gaps. |
| `dual_wield` | OnPlay | Its copies are `type(card)()` plus replayed upgrades, not `CreateClone` deep clones, so an enchanted Attack duplicates as vanilla. Same verdict as `anger` (rule 3), and the card where it matters most -- copying an enchanted Attack is the whole point. |

New dormant gaps from batches 3-4, in brief: `conflagration` (and, by the same
mechanism, `dramatic_entrance` and every other ALL_ENEMIES card) hands the
damage pipeline one target at a time where C# hands it the whole valid-target
list per hit, so deaths interleave differently -- live once a monster with a
sibling-affecting on-death effect is ported; `crimson_mantle` increments its
self-damage counter whenever the power is present where C# skips it when Apply
returns null; `disintegration` has TWO mismatched flags (C# overrides
`CanBeGeneratedInCombat => false`, the sim instead sets
`can_be_generated_by_modifiers = False`, which C# leaves true) and is marked
unplayable where C# gives it no Unplayable keyword; `enlightenment`'s
`reduceOnly` is lazy in C# (`LocalCostModifier.IsReduceOnly` is a per-READ
test) and eager in the sim; plus more inlined CanonicalVars (colossus,
corruption, decay, doubt, debt) and more -1 costs (clumsy, curse_of_the_bell,
dazed, decay, doubt, disintegration).

Two faithful ports are worth naming as the patterns others should follow:
**`card/cinder`** routes `Rng.CombatCardSelection` correctly under parity and
falls back to the shared rng only in legacy mode -- the shape the other 20
shared-RNG cards need; and **`card/catastrophe`**'s pick reproduces
StableShuffle's stabilising sort, the game's top-first pile orientation, the
N-1 draw count AND the unfiltered fallback. **`card/discovery`** is the correct
KEYWORD pattern: it sets `exhausts` in `_init_vars` rather than as a class
attribute, which is exactly why it survives the downgrade rebuild that catches
aggression and apparition.

## 7c. Additional live gaps from batches 5-8

Grouped by what they teach, not by unit.

**Port-shape defects - a whole engine verb reimplemented or skipped.**

| Unit | Gap |
|---|---|
| `havoc` | The worst port defect found. C# is one line (`AutoPlayFromDrawPile(..., 1, Top, forceExhaust: true)`); the sim reimplements the verb inline AND calls `card.on_play()` directly instead of `CombatState.auto_play_card`, skipping the entire play bracket (combat.py:441-513): `on_energy_spent` (Free Attack never fires), `before_card_played`, the `modify_card_play_count` replay loop (a Spiral or Hidden-Gem'd card plays once instead of twice), the `before/after_attack` bracket (Akabeko's Vigor is not consumed), and `captured_x` (a Havoc'd Whirlwind does nothing). It also rolls the random target on `combat._rng`. `cascade` reimplements the same verb correctly and `howl_from_beyond` routes through `auto_play_card` - both are the fix shape. |
| `debt` | `HasTurnEndInHandEffect` and the whole `OnTurnEndInHand` gold loss are absent. The docstring's "the sim has no gold" is false: `RunState.gold` + `RunState.lose_gold` (run.py:335-337). |
| `guilty` | `AfterCombatEnd` absent, so Guilty never removes itself from the deck after 5 combats. "The sim doesn't model the persistent deck" is false - `RunState.deck` is it. |
| `lantern_key` | `ModifyUnknownMapPointRoomTypes` not overridden even though the sim's `Card` base HAS the hook and `spoils_map` already uses the same pipeline. "The sim has no map" is false. |
| `maul` | `AfterDowngraded` absent, so `downgrade()` destroys the damage accumulated from Maul plays this combat. A *second, distinct* downgrade defect from the five sticky-keyword cards, and one the probe cannot see (it compares a fresh card, and Maul's loss only shows after a play). |

**Wrong quantity or wrong hook.**

| Unit | Gap |
|---|---|
| `fisticuffs` | Block = C#'s `TotalDamage + OverkillDamage` (blocked + hp lost + overkill, DamageResult.cs:64 + Creature.cs:445-457); the sim uses `DamageCmd.deal`'s return, which is hp_lost only. Hit a 5-HP enemy for 7: game grants 7, sim grants 5; against a blocking enemy the sim can grant 0. |
| `feed`, `hand_of_greed` | Both Fatal cards drop the power-veto half of the test. C# requires `Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())` as well as `WasTargetKilled`; `MinionPower` (unconditionally) and `ReattachPower` both veto, both are ported, and MinionPower is applied by three ported monsters (Fabricator bots, Queen, Ovicopter eggs). `hand_of_greed`'s docstring asserts no power vetoes fatal - false. |
| `clash` | `IsPlayable` routed through `should_play_card`. C# reads `IsPlayable` only in `CardModel.CanPlay` (the manual path); `CardCmd.AutoPlay` checks only the Unplayable keyword and `Hook.ShouldPlay`. `enthralled` and `normality` show what a real `ShouldPlay` port looks like. |
| `normality` | Right hook, wrong counter: C# counts plays STARTED, the sim counts finished. Play two cards then Havoc: C# blocks the auto-play, the sim allows it. |
| `drum_of_battle` | Feeds a bare `1` into `modify_card_play_count` where C# feeds `GetEnchantedReplayCount() + 1`, dropping `base_replay_count`. Hidden Gem + Drum of Battle: game pays twice, sim once. |
| `hidden_gem` | The already-replaying filter checks only for a spiral/glam enchantment; C#'s `GetEnchantedReplayCount() < 1` returns `BaseReplayCount` on the null branch, so any already-replaying card is excluded. Two Hidden Gems can stack on one card in the sim. |
| `mad_science` | `GainsBlock` is TYPE-dependent in C# (`Type == Skill`) and never set in the sim, so Nimble refuses a Skill Mad Science. Notable because the parallel `base_block` type-dependence WAS handled. |
| `feel_no_pain` | Stores the power's block-per-exhaust amount in `_block`, the attribute `base_block` reads - so the sim reports a card that grants 3 block on play. `cards/base.py:65-69` warns about this exact confusion by name. `eternal_armor` stores the same shape correctly, in `_plating`. |
| `enlightenment` | Relative delta where C# registers an absolute `LocalCostModifier`; they diverge once the card's base cost changes in the same turn, which `armaments` and `apotheosis` both do. |
| `frantic_escape` | `AddThisCombat(1)` implemented as `self._energy_cost += 1`, mutating the BASE cost, which `reset_combat_state` never clears - the bump leaks into later combats. |
| `metamorphosis` | Adds its generated Attacks at `CardPilePosition.Random` in C# (one CombatCardSelection draw each); the sim appends to the top of the draw pile and takes no draw. |
| `catastrophe` | The sim breaks its pick loop on combat-over; C# has no loop-level bail and does the StableShuffle pick BEFORE `AutoPlay`'s own `IsOverOrEnding` return, so C# burns a full StableShuffle per remaining iteration and the sim burns none. Opposite polarity to `beat_down`'s target-roll guard. |
| `bolas` | Returns to hand from any non-hand pile in C#; the sim searches only draw and discard, so an exhausted Bolas never comes back. `thrumming_hatchet` shares the helper. |
| `dual_wield` | Copies are fresh instances, not `CreateClone` deep clones (same as `anger`), and this is the card where it matters most. |
| `breakthrough` | Hand-rolls its 1 HP self-loss instead of `DamageCmd`, so `on_damage_received` never fires and Rupture does not trigger. |
| `entrench` | The entire ported blast radius of seam gap G1. |
| `discovery`, `distraction`, `jack_of_all_trades`, `jackpot`, `hidden_gem`, `metamorphosis`, `havoc`, `anointed`, `beat_down` | Nine of the 21 shared-RNG cards audited, all nine gaps. `cinder`, `infernal_blade` and `mad_science`'s Chaos rider show the correct shape - branch on `crng.is_parity`, use the named accessor. |
| `aggression`, `apparition`, `hello_world`, `juggling` | Four of the five sticky-keyword cards audited; `wish` remains. |

**Dormant additions.** `neows_fury` is the first unit whose C# selector prefs
use a RANGE (MinSelect 0), which the sim's fixed `count` cannot express - the
min/max half of seam guard N10 at a card site. `inferno` repeats
`crimson_mantle`'s `?.IncrementSelfDamage()` null-check divergence (these two
are the pool's only such sites). `mind_rot` and `frantic_escape` repeat
`disintegration`'s mismatched-flag error; `neows_fury` relies on rarity instead
of the flag - three different treatments of `CanBeGeneratedInCombat` across six
cards, against `feed` / `hand_of_greed` / `hidden_gem` / `not_yet`, which set it
correctly. `breakthrough` filters its AoE loop on `is_dead` where every other
AoE card uses `is_gone`. `dramatic_entrance`, `exterminate` and
`howl_from_beyond` inherit `conflagration`'s per-enemy fan-out finding.

**Faithful ports worth copying.** `molten_fist` is the one card in the
liveness-guard family whose `is_gone` check is faithful, because C# writes the
`IsAlive` test itself. `enthralled` is the model `ShouldPlay` port - all four
clauses, same short-circuit order, and the sim's `auto_play` flag really is
C#'s `autoPlayType != None`. `fiend_fire` gets snapshot-then-exhaust-then-hit
exactly right. `iron_wave` gets the counter-intuitive block-before-attack order
right. `maul` correctly includes the just-played card in its own buff.
`jackpot` transcribes the *canonical*-cost filter rather than the current cost.
`mad_science` accounts for all eleven of its C# vars and exposes the two
printed ones through type-dependent properties.

## 8. Remaining work

173 units, batches 3–14, alphabetically from `calamity`. Findings already
banked for units not yet audited, so they are not lost if the stream stops:
`hello_world` / `juggling` / `wish` (downgrade-sticky, §3.1), `entrench` (the
sole ported member of G1's blast radius, §3.2), `hidden_gem` and
`drum_of_battle` (G4, §3.3), the 18 remaining shared-RNG cards (§3.4), and
`thrumming_hatchet` (shares Bolas's return-to-hand helper), and `wish` (the
last of the five sticky-keyword cards).
