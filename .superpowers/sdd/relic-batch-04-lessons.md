# Relic content audit — batch 4 lessons and findings

**Date:** 2026-07-26 · **Branch:** `audit-relic-b04` (based on `audit-relic` @ `4542c32f`)
**Units:** `crossbow` … `ectoplasm` (15)
**Probes:** `py tools/audit/relic_probes_b04.py` (13 probes, committed, re-runnable)

`py tools/audit/harness.py validate` → **66 records, 0 invalid**.
`py tools/audit/citation_check.py audits/relic` → 511 citations, **MISSING 0,
OUT-OF-RANGE 0, AMBIGUOUS 0** (one bad citation of mine — `cmds.py:604-611` on a
554-line file — was caught by the gate and corrected to `cmds.py:110-113`; the
gate earns its keep).
`py tools/audit_status.py --kind relic` → `total 258 · audited 61 · invalid 0 ·
stale 0 · gaps 43 · unaudited 197`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged. No engine code
was touched; `git status` shows only the 15 records, the probe module and this file.

---

## Units and rollup verdicts

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `crossbow` | **gap** | 2 | 6 |
| `cursed_pearl` | waiver | 2 | 4 |
| `darkstone_periapt` | **gap** | 2 | 6 |
| `daughter_of_the_wind` | **gap** | 2 | 5 |
| `delicate_frond` | **gap** | 2 | 5 |
| `demon_tongue` | **gap** | 3 | 5 |
| `diamond_diadem` | **gap** | 6 | 5 |
| `dingy_rug` | **gap** | 2 | 3 |
| `distinguished_cape` | **gap** | 3 | 4 |
| `dollys_mirror` | **gap** | 3 | 3 |
| `dragon_fruit` | **gap** | 3 | 4 |
| `dream_catcher` | **gap** | 3 | 5 |
| `driftwood` | **gap** | 2 | 4 |
| `dusty_tome` | **gap** | 2 | 7 |
| `ectoplasm` | waiver | 4 | 4 |

**13 of 15 roll up to `gap`** (87%, against the pilot's 69%). Two units —
`cursed_pearl` and `ectoplasm` — are clean ports whose worst entry is a
presentation waiver. Both were checked by execution anyway, and `ectoplasm`'s
"you can never gain gold" promise needed a repo-wide scan to earn its `faithful`
(binding rule 5): only `run.py:333`, inside `gain_gold` and after the hook chain,
writes `RunState.gold` on a gain path.

## LIVE gaps, with the executed evidence

Fifteen LIVE gap entries. Each line is one record entry; the probe name is the
reproducer.

1. **`diamond_diadem` G1 — the relic is dead on turn 1 of every combat after the
   first.** The sim's only reset is in `on_player_turn_end`, and
   `CombatState.end_turn` returns at `combat.py:641-642` when the fight is
   already over — i.e. every time the player wins on their own turn. *`diadem`:*
   combat 1 ends with `cards_played_this_turn=3` and stays there; in combat 2,
   on a turn with **zero** cards played, the carried instance grants `[]` and a
   fresh one `[('diamond_diadem', 1)]`. C# resets in `AfterCombatEnd`
   (`DiamondDiadem.cs:80`).
2. **`diamond_diadem` G2 — the card counter under-counts replays, so the relic
   fires when the game withholds it.** `hook_dispatch` G4 at a new site, with the
   observable inverted by the `<= 2` threshold.
3. **`darkstone_periapt` G1 — an out-of-combat transform into a Curse pays no
   Max HP.** *`darkstone`:* `add_card(curse)` gives 80 → 86 (correct);
   `transform_card(curse)` → `clumsy` leaves Max HP at 86 where C# gives 92.
   `RunState.transform_card` writes `self.deck` directly (`run.py:466`/`:469`)
   and dispatches no deck hook; C# fires both at `CardCmd.cs:429`/`:447`.
   Fifteen ported call sites reach it.
4. **`distinguished_cape` G1 — the relic's −9 Max HP is implemented in the wrong
   file, on a false premise.** *`cape`:*
   `add_relic('distinguished_cape')` → `(80, 80, 13)` where C# gives
   `(71, 71, 13)`. The port's docstring blames
   `EventOption.ThatDecreasesMaxHp(9)`; that helper
   (`EventOption.cs:193-197`) only sets the red-flash predicate and applies
   nothing. `events/vakuu.py:59` pays the 9 instead, so the Vakuu total is right
   **by accident** and the defect is invisible to anyone who only plays the
   event. Exactly `big_mushroom` G1 with the sign reversed, including the
   conformance-runner consequence and the missing `undo_after_obtained`.
5. **`crossbow` G1 — Crossbow × Whispering Earring is decided by relic order.**
   *`earring-order`:* `[crossbow, whispering_earring]` leaves the enemy at
   **36 HP**, `[whispering_earring, crossbow]` at **45 HP** — 9 damage from relic
   order alone. C# always gives 36 because the AutoPrePlay phase is entered
   strictly after `Hook.AfterSideTurnStart`. See the cross-record section.
6. **`delicate_frond` G1 — potion rarity weighting is missing entirely.**
   *`frond`:* the port picks uniformly over 48 reward-pool potions
   (16 Common / 16 Uncommon / 16 Rare), so P(Rare) = **0.333** where
   `PotionFactory.cs:67-81` rolls **0.10**. The sim already has the faithful
   helper (`potion_pools.generate_random_potion`) and does not use it.
7. **`delicate_frond` G2 — Sozu does not stop the Frond.** *`frond`:*
   `['delicate_frond']` and `['delicate_frond', 'sozu']` both yield the same full
   belt; C# leaves it empty (`PotionCmd.cs:31-39` refuses, `DelicateFrond.cs:20`
   breaks). `player.add_potion`'s own docstring admits the omission.
8. **`delicate_frond` G3 — the Frond is a no-input trigger for `belt_buckle`'s
   recorded `AfterPotionProcured` gap.** *`frond`:*
   `[belt_buckle, delicate_frond]` ends combat start at `[('dexterity', 2)]`
   with a full belt; C# nets 0.
9. **`daughter_of_the_wind` G1 — a replayed Attack grants 1 Block instead of 2.**
   *`dotw`:* with `throwing_axe` added the Block is still 1.
   `hook_dispatch` G4's observable at this relic.
10. **`dingy_rug` — card rewards never contain Colorless cards.** *`stubs`:*
    identical options with and without the relic, zero Colorless either way,
    while `COLORLESS_POOL` is fully ported (53 cards) and `create_reward_cards`
    already takes a `pool` override.
11. **`dollys_mirror` — the duplicate card never appears.** *`stubs`:* deck stays
    at 10 where C# gives 11; `after_obtained` is dispatched for every relic at
    `run.py:552`.
12. **`dragon_fruit` G1 — +1 Max HP per gold gain never happens.** *`stubs`:*
    `gain_gold(25)` moves gold 99 → 124 and Max HP stays 80 with and without the
    relic.
13. **`dragon_fruit` G2 — `IsAllowed` / `IsBeforeAct3TreasureChest` unmodelled**
    (sweep B's 16-relic cluster; `hasattr(Relic, 'is_allowed')` is False,
    `run.total_floor` already exists). Matches
    `amethyst_aubergine`'s verdict.
14. **`dream_catcher` G1 — a MIMICKED rest heal offers no cards.** *`dream-driftwood`:*
    the real screen offers 3 cards; `events/dense_vegetation.py:65-68`'s `_rest`
    heals 50 → 74 and builds no reward screen at all. C# has one implementation
    (`HealRestSiteOption.ExecuteRestSiteHeal`) that both paths share, and
    `DreamCatcher` ignores `isMimicked`. Also silences `stone_humidifier` and
    `tiny_mailbox` on the mimic path — one fix in the event, not one per relic.
15. **`driftwood` G1 — the reroll only reaches the combat screen.**
    *`dream-driftwood`:* `[dream_catcher, driftwood]` gives a rest screen with
    `can_reroll=False`, while `driftwood` alone on a MONSTER screen gives
    `can_reroll=True`. C# dispatches `TryModifyRewardsLate` from
    `Hook.ModifyRewards`, whose only caller is
    `RewardsSet.GenerateWithoutOffering` (`RewardsSet.cs:136`) — every reward
    screen, including `RewardsCmd.OfferCustom`.

Plus `dusty_tome` G2, LIVE **only on the `add_relic` path** (the conformance
runner's relic resync): the port re-rolls `ancient_card` lazily inside
`after_obtained` where C# fixes it at offer time on `PlayerRng.Rewards`. Dormant
for the card identity because the candidate set has exactly one member.

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `crossbow` G2 | named RNG stream (`CombatCardGeneration`) and draw shape (`sample` vs `UnstableShuffle`+Take) not used, though the parity helper exists | already LIVE for RNG parity (fires every player turn); dormant only for RL play |
| `crossbow` G3 | `FilterForCombat` also drops `CardRarity.Event`; `pool_card_ids` does not | porting any Event-rarity Attack into the Ironclad pool — executed: **zero** exist today |
| `darkstone_periapt` G2 | C# fires the hook for a card entering `PileType.Deck` mid-combat | porting any effect that adds a card to the RUN deck from inside a fight |
| `daughter_of_the_wind` G2 | no `IsOverOrEnding` gate — a lethal Strike still grants Block | `hook_dispatch` G8's own trigger: a listener on a guarded dispatcher that mutates run-level state |
| `demon_tongue` G2 | heals `hp_lost` (overkill-inclusive) vs `DamageResult.UnblockedDamage` | a player-side death preventer that leaves the player at 0–1 HP; the ported preventers protect enemies or heal past the difference |
| `dream_catcher` G3 | C# adds a distinct `CardReward`; the sim extends one pick-one group | porting `tiny_mailbox`'s rest reward (currently a sweep-C stub) — C# would offer two screens, the sim one merged choice |
| `driftwood` G2 | the **Late** phase is flattened into one `modify_combat_rewards` pass | porting Prayer Wheel or White Star (both sweep-C stubs) — a plain-phase listener that ADDS a `CardReward` |
| `dusty_tome` G1 | unguarded `Card.upgrade()` (sweep D's open site) | an Ancient-rarity Ironclad pool card with `max_upgrade_level 0` — executed: the candidate set is exactly `['corruption']`, `max_upgrade_level 1` |
| `dusty_tome` N2 | the port ADDS `has_upon_pickup_effect = True`, which `DustyTome.cs` never declares | any use of the flag that is not also rarity-gated (`is_tradable` already excludes Ancient, so it is masked) |

## Cross-record disagreement (binding rule 3)

**One, and it matters.** `audits/seam/turn_structure.json` guard **G8** (the
missing `AutoPrePlay`/`AutoPostPlay` phases) is LIVE on the AutoPostPlay side and
calls the **AutoPrePlay side DORMANT**, on this stated basis:

> "The AutoPrePlay side is dormant: Whispering Earring
> (`relics/whispering_earring.py:27-43`) and Imbued (`enchantments.py:261-267`)
> both fire from `on_player_turn_started` and neither reads another turn-start
> listener's output."

`relics/crossbow.py` refutes the argument. Crossbow does not *read* the Earring's
output — it **writes the hand the Earring then consumes**, which is the same
dependency with the arrow reversed. Executed (`earring-order`): 36 HP vs 45 HP on
the enemy after turn 1, decided purely by relic order, where C# is fixed.

I did **not** edit the seam record (ownership contract). `crossbow`'s guard G1
carries G8's verdict per rule 3 and states the contradiction in its issue text.
**Action for the seam owner:** G8's AutoPrePlay dormancy rationale should be
replaced with a LIVE label naming `relics/crossbow.py` as the witness, and
`test_end_of_turn_auto_plays_run_before_turn_end_hooks` gains a start-of-turn
sibling.

Everything else reproduced a prior verdict without conflict: `hook_dispatch` G4
(gap, LIVE) at `daughter_of_the_wind` and `diamond_diadem`; `hook_dispatch` G8
(gap, dormant) at its own named witness; `turn_structure` G12 (gap) noted as
*not* changing `diamond_diadem`'s or `crossbow`'s answer; `calling_bell` G4's
`ShouldAddToDeck` waiver reused at `cursed_pearl`; `amethyst_aubergine`'s
`IsAllowed` gap reused at `dragon_fruit`; `belt_buckle`'s `AfterPotionProcured`
gap reused at `delicate_frond`; `brilliant_scarf`'s `BeforeSideTurnStart`
deliberate-divergence reused at `demon_tongue`; `brilliant_scarf` N1's
`IsInProgress` argument reused at `diamond_diadem`; `beating_remnant`'s
killing-blow confirm reused at `demon_tongue`.

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file on the first try, all 15 are
registered, and all 15 are obtainable with ported content (`b04-pool`):
`demon_tongue` (Rare), `dingy_rug`, `dollys_mirror`, `dragon_fruit` (Shop) from
the transcribed grab bag; the other eleven from ported events/shrines (Tanx,
Neow, Trash Heap ×2, Doll Room, Nonupeipe ×2, Vakuu, Orobas, Darv ×2).
`tools/audit/name_overrides.json` needs no additions.

---

## New bug classes and pool-wide shapes

### Class 19 — a turn-boundary reset is NOT a safe substitute for a combat-boundary reset, because `end_turn` does not run on the winning turn

**Exhibited by `diamond_diadem` (LIVE).** `CombatState.end_turn` opens with
`if self.phase != Phase.PLAYER_TURN: return` (`combat.py:641-642`), so
`hooks.on_player_turn_end` (`combat.py:654`) never fires when the player kills the
last enemy during their own turn — the **normal** way a fight ends. Any relic
whose only reset lives in `on_player_turn_end` therefore carries the winning
turn's value into the next combat.

This is a **refinement of PROMPT.md class 13, and it invalidates part of sweep
A**. Sweep A sorted 21 relics into a "reset only at a **turn** boundary
(`art_of_war` shape)" bucket, treated that bucket as probably-safe (it required a
reader trace but ran no execution on it), and only executed the 16 whose C# has a
combat-boundary reset. `diamond_diadem` is in the turn-boundary bucket **and** its
C# has an `AfterCombatEnd` reset — the sweep's executed arm should have caught it
and its bucket logic filed it away instead. Two consequences:

- **The other 20 turn-boundary relics need re-triage**, and the discriminator is
  cheap and mechanical: a reset in `on_player_turn_start` (or
  `on_player_turn_started`) is safe, because `CombatState.__init__` runs the first
  player turn before any reader — that is exactly why `demon_tongue` G3 and
  `art_of_war` are clean, and `demon_tongue`'s probe demonstrates it. A reset in
  `on_player_turn_end` is **not** safe. `brilliant_scarf`'s `AfterCombatEnd`
  divergence, verdicted safe in batch 2 on the "the turn reset runs before any
  reader" argument, holds for the same reason — its reset is at turn *start*
  (`brilliant_scarf.py:37-38`) — but the argument as written ("the turn reset")
  is too loose and would license the wrong conclusion for a turn-*end* relic.
- **Sweep A's next revision should split the bucket** on which turn hook does the
  resetting, and should execute the turn-end half by ending combat 1 with a
  card play rather than with `end_turn()`.

### Class 20 — `RunState.transform_card` dispatches no deck hooks at all, where C# fires both

**Exhibited by `darkstone_periapt` (LIVE).** The out-of-combat transform is a
deck ADD in C#: `CardCmd.cs:429` fires `Hook.ModifyCardBeingAddedToDeck` and
`CardCmd.cs:447` fires `Hook.AfterCardChangedPiles` for the replacement. The sim's
`run.transform_card` writes `self.deck` directly (`run.py:466`/`:469`).

**Pool-wide, not one relic.** Every ported listener on either deck hook is
silently skipped on all 15 transform call sites: `darkstone_periapt`
(`after_card_added_to_deck`), `book_of_five_rings` and `lucky_fysh` (same hook),
and the three egg relics plus anything else on
`modify_card_being_added_to_deck`. The next batches to hold those relics should
confirm rather than rediscover, and the card stream should check the same for
`Card`-side deck hooks. A one-line sweep would be: for each relic implementing
either hook, run `transform_card` and diff the run state.

### Class 21 — check whether a fluent event-option helper actually *does* anything before believing a port that relies on it

**Exhibited by `distinguished_cape` (LIVE).** `EventOption.ThatDecreasesMaxHp(9)`
reads like it costs 9 Max HP. It is `ThatWillKillPlayerIf(p => p.MaxHp <= 9)`
(`EventOption.cs:193-197`) — a red-flash predicate with no consumer that loses
HP. The port moved a relic effect into the event on the strength of the method
NAME. The same trap is loaded elsewhere: `EventOption.ThatDoesDamage(x)` is
`ThatWillKillPlayerIf(p => p.CurrentHp <= x)` and applies no damage either, and
`DrowningBeacon.cs:32` / `UnrestSite.cs:36` are the other two
`ThatDecreasesMaxHp` callers — both apply their loss in their own option bodies,
so the **event** stream should verify that neither sim port double-pays or
under-pays. This is class 12 ("a port that does nothing justifies itself with a
claim — check the claim") extended to the opposite direction: a port that does
something **in the wrong file**, justified by a claim about a *helper*.

### A pool-wide shape worth one cheap sweep before the next batches

Three of this batch's 15 units (`delicate_frond`, `crossbow`, and `dusty_tome`
partially) diverge because the port hand-rolls a generator the sim **already has
a faithful parity helper for** and does not call it:

| Port | Hand-rolled | Faithful helper it ignores |
|---|---|---|
| `crossbow.py:26-28` | `random_pool_cards(self.combat._rng, …)` | `cards/pool.py` `get_distinct_for_combat_parity` |
| `delicate_frond.py:20-25` | uniform `choice` over `in_reward_pool` classes | `potion_pools.generate_random_potion` |
| `dusty_tome.py:48` | `run.rng.choice(options)` fallback | `run.player_rng.rewards.next_item` (used on the parity branch) |

That is a mechanical scan — grep every `sts2_rl/relics/*.py` for
`random_pool_cards`, `self.combat._rng`, `run.rng.choice` and
`_POTION_CLASSES`, then check whether a `*_parity` / `potion_pools` /
`player_rng` equivalent exists — and it would pre-populate the remaining 197
units the way sweeps A–E did. It is a **superset** of class 16's RNG-stream half:
the divergence is not only the stream but the *distribution* (`delicate_frond`
turns a 10% Rare roll into 33%), which no stream fix would repair.

I did not write it: `tools/audit/relic_probes.py` is read-only to this batch and
a batch-local sweep would duplicate work five other concurrent batches might
also do. Recommended as sweep **F** for the relic stream owner after the merge.

## Left unverified / out of scope

- **`crossbow` G2's draw-shape claim is demonstrated, not measured against a real
  parity run.** The probe shows `sample` and `shuffle`+`take` disagree on the
  same seed; it does not run a conformance seed that takes Crossbow. No seed
  fixture in the repo takes it.
- **`delicate_frond`'s three gaps are filed as gaps despite the contract's blanket
  potion deferral**, on `belt_buckle`'s precedent (the divergent observable is
  what the player carries and what the runner's belt resync compares, not the
  potion system). If Perry wants the deferral read strictly, G1 becomes a waiver;
  G2 and G3 should not, since their observables are Sozu's veto and the player's
  Dexterity.
- **`demon_tongue` G2 was reasoned, not executed.** The overkill-vs-`UnblockedDamage`
  difference needs a player-side death preventer to observe, and the ported
  preventers either protect enemies or (Lizard Tail) heal past the difference; I
  did not build a synthetic preventer to force it, so the label rests on reading
  `DamageResult.cs` and `cmds.py` plus the executed absence of a suitable
  preventer.
- **`dingy_rug` G2's four C# guards are recorded as a group**, not individually
  verdicted, because with no base hook there is nothing for any of them to gate.
- **Multiplayer owner checks** (`player != base.Owner`, `PlayerChoiceContext`,
  `LocalContext.IsMe`) are treated per the contract as mapping notes rather than
  divergences throughout.
- **Nothing was fixed.** All 43 relic gaps, including this batch's, are records
  only; the suite is unchanged.

**Commit:** see the `audit-relic-b04` HEAD (recorded in the commit message
naming all 15 units and the 15 LIVE gaps).
