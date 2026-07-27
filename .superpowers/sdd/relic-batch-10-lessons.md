# Relic audit batch 10 — lessons and findings

**Date:** 2026-07-26 · **Branch:** `audit-relic-b10` (worktree `sts2-rl-relic-b10`)
**Probes:** `py tools/audit/relic_probes_b10.py [name]` — 14 probes, all re-runnable
**Validation:** `harness.py validate` 136 records / 0 invalid / 0 stale ·
`citation_check.py audits/relic` MISSING 0, OUT-OF-RANGE 0 ·
`audit_status.py --kind relic` total 258 / audited 136 / gaps 106 ·
`py -m pytest test/ -q` **2476 passed, 31 xfailed** (baseline, unchanged)

---

## The 15 units

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `mummified_hand` | **gap** | 2 | 7 |
| `music_box` | **gap** | 5 | 6 |
| `mystic_lighter` | **gap** | 2 | 3 |
| `neows_bones` | **gap** | 2 | 9 |
| `neows_talisman` | **gap** | 3 | 4 |
| `neows_torment` | waiver | 3 | 3 |
| `new_leaf` | **gap** | 3 | 6 |
| `nunchaku` | **gap** | 4 | 6 |
| `nutritious_oyster` | **gap** | 3 | 3 |
| `nutritious_soup` | waiver | 2 | 6 |
| `oddly_smooth_stone` | deliberate-divergence | 2 | 4 |
| `old_coin` | **gap** | 5 | 5 |
| `orichalcum` | **gap** | 4 | 6 |
| `ornamental_fan` | **gap** | 6 | 5 |
| `orrery` | **gap** | 3 | 4 |

12 of 15 roll up to `gap`. Two are clean (`neows_torment`, `nutritious_soup` —
waiver only for presentation), one is a divergence.

---

## LIVE gaps, each with its executed evidence

1. **`neows_bones` G1 — the wrong two relics, on 24 of 60 seeds.** `NeowsBones`
   shuffles `Neow.AllPossibleOptions` on the Rewards stream and takes 2, so the
   pool's ORDER is load-bearing. `Neow.cs:49-64` lists the six trailing options
   individually (LavaRock, NeowsTalisman, NutritiousOyster, Pomander,
   SmallCapsule, StoneHumidifier); `events/neow.py:64-72` appends the three
   coin-flip PAIRS instead. *Executed (`neows-bones`):* identical Fisher-Yates
   (`Rng.cs:308-320` vs `rng.py:270-273`), so only the order differs — over 60
   string seeds the two orders give different pairs on **24**, e.g. B10SEED11
   `['small_capsule','lava_rock']` vs `['neows_talisman','lava_rock']`. **Not
   pre-diagnosed by any sweep.** Every run visits Neow and both granted relics
   run their own pickup effects, so max HP / gold / deck / relic list all move.

2. **`mystic_lighter` G1 — +9 damage on every Enchanted Attack, missing.** Stub
   justified by "the sim has no enchantments"; `enchantments.py` is ported with
   17 enchantments and three ported relics grant one. *Executed
   (`mystic-lighter`):* an enchanted Strike deals **6 with and 6 without** the
   relic; C# deals 15. One-method fix — see the sweep defect below.

3. **`old_coin` G1 — 300 gold, missing.** Stub premise "no gold system in the
   sim" is false. *Executed (`old-coin`):* `add_relic('old_coin')` leaves gold
   at 99; the exact sibling `golden_pearl` takes 99 → 249 on the same path.

4. **`old_coin` G2 — `IsAllowed` (`TotalFloor < 41`) unmodelled.** Sweep B's
   17-relic cluster, confirmed. *Executed:* at `total_floor=60` the grab bag
   still contains **and yields** `old_coin`.

5. **`orrery` G1 — five 3-card choices, missing.** Stub premise "out-of-combat
   card reward" is false. *Executed (`orrery`):* deck 1 → 1; sibling
   `lost_coffer` 1 → 2 + a potion; `create_reward_cards(REGULAR, 3)` returns
   three real cards.

6. **`music_box` G1 — the Ethereal copy is a rebuild, not a clone.** Sweep E /
   class 17, same mechanism as `burning_sticks` G3. *Executed (`music-box`):* a
   Strike carrying Tezcatara's Ember (`energy_cost=0, eternal=True`) copies as
   `enchantment=None, energy_cost=1, eternal=False`; a `Ringing(1)` affliction
   is likewise dropped. Reachable **inside the same batch** — `nutritious_soup`
   enchants exactly the Basic Strikes that Music Box copies.

7. **`neows_talisman` G1 — unguarded `Card.upgrade()` pushes a Basic past its
   max.** Sweep D's third unaudited site. *Executed (`neows-talisman`):* an
   already-upgraded last Basic Strike/Defend reaches `upgrade_level 2`
   (`is_upgradable` then False); C# skips. **The reachability took work** — the
   relic is floor-0-only, so the upgrade must happen in the SAME pickup:
   `neows_bones` grants two Neow-pool relics in sequence and `pomander`
   ("upgrade a chosen card") is in that pool; seed `B10BONES0136` orders
   pomander first, and running that pair produces `('strike', 2)`.

8. **`nunchaku` G1 — a replayed Attack counts once, not twice, and the counter
   is PER-RUN.** `hook_dispatch` G4 at a worse site than the seam record's own
   example (`pen_nib`, per-combat). *Executed (`nunchaku`):* a Throwing-Axe-
   doubled Strike leaves `_attacks_played=1` where C# leaves 2, so the +1 energy
   lands on a different attack **for the rest of the run**.

9. **`ornamental_fan` G1 — same mechanism, per-turn.** *Executed
   (`ornamental-fan`):* Throwing Axe + two Strikes gives `_attacks_this_turn=2`,
   `block=0`; C# counts 3 and grants 4 Block.

10. **`mummified_hand` G3 — same mechanism.** *Executed (`mummified-hand`):* a
    Throwing-Axe-doubled Power frees **1** card where C# frees 2.

11. **`mummified_hand` G1 — the candidate filter is blind to GLOBAL cost
    modifiers.** C# filters on `CostsEnergyOrStars(includeGlobalModifiers:true)`
    = `GetWithModifiers(CostModifiers.All) > 0`; `mummified_hand.py:25` reads
    `c.energy_cost`, the card's LOCAL cost, and never consults the sim's
    `modify_card_energy_cost` chain. *Executed:* with **Corruption** up (ported
    Ironclad Rare Power card) the sim still sees `energy_cost>0` on four Defends
    the hook prices at 0 and freed a Defend; C# admits only the Bash.

12. **`orichalcum` G1 — the two-phase VeryEarly snapshot is collapsed.**
    `turn_structure` G12's named witness. *Re-executed (`orichalcum`):*
    `[cloak_clasp, orichalcum]` → 5 Block, `[orichalcum, cloak_clasp]` → 11; C#
    always 11. Pin verified present: `test_hook_order.py:791`.

13. **`new_leaf` N1 — the named `Rng.Niche` stream is dropped.** LIVE for RNG
    parity, dormant for RL (same split as `astrolabe` N1). *Executed
    (`new-leaf`):* the transform happens with the Niche draw counter at 0 → 0.
    The stream really is CONSUMED in C# (`CardTransformation.cs:71`), unlike
    `claws`'s explicit-Replacement case that class 16 warns about.

14. **`mummified_hand` G2 — tiers 3 and 4 do not exist.** LIVE for RNG parity.
    *Executed:* with `[dazed, dazed]` left in hand the sim takes **0**
    `CombatCardSelection` draws and frees nothing; C# takes 1 (`NextItem` on an
    empty sequence takes no draw, `Rng.cs:255-265`). Gameplay-neutral, but
    `card_selection` is a run-level parity stream.

## Dormant gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `new_leaf` G1 | `FromDeckForTransformation` also excludes Quest cards; `run.transformable_cards()` filters only Eternal | any grant path for New Leaf **after floor 0** — the three ported Quest cards (`byrdonis_egg`, `lantern_key`, `spoils_map`) only enter the deck via later events, and New Leaf comes only from Neow / Neow's Bones |
| `nunchaku` N4 | `Hook.AfterModifyingEnergyGain` companion + C#'s `finalAmount > 0` guard | a ported `modify_energy_gain` listener that returns a NEGATIVE amount (today the only one, `NoEnergyGainPower`, clamps to 0) or one that needs the companion |
| `old_coin` N1 | `Hook.AfterModifyingGoldGained` companion | a second `modify_gold_gained` listener (today: only `ectoplasm`) that needs "react only when I changed it" |
| `nutritious_oyster` G1 | no `undo_after_obtained`, so the conformance runner cannot un-grant +11 Max HP | a conformance seed whose Neow node auto-grants the Oyster and whose save picked something else. Unlike `fake_mango`'s Fake Merchant the node is visited every run, so this is closer to live than that record's — I did not run a seed, so I did not label it live |
| `orrery` G2 | `RewardsCmd.OfferCustom` here is SKIPPABLE, so auto-keep would add up to 5 unwanted cards | subsumed by G1 today (nothing is added); it is the trap waiting for G1's fix |

---

## Things I found wrong in the shared tooling (evidence attached; nothing edited)

### 1. Sweep C UNDER-REPORTS: `mystic_lighter`'s dropped hook IS a HookSystem hook

`content-relic-sweeps.md` Sweep C ends with: *"A handful of dropped hooks have no
`Relic` base method **and are not `HookSystem` hooks** — `ModifyMerchantPrice`,
`ShouldRefillMerchantEntry`, `ModifyCardRewardCreationOptions`, `ShowCounter`,
`AfterGoldGained`, `ModifyExtraRestSiteHealText`, `ModifyDamageAdditive` on
`mystic_lighter`. Those need a new base hook, so they are larger than a one-relic
fix and are excluded from the 33 above."*

`ModifyDamageAdditive` **is** a HookSystem hook. `HookSystem.modify_damage_additive`
is defined at `hooks.py:52-64`, summed from `DamageCmd.deal` at `cmds.py:56-58`
over every combat listener, and relics ARE combat listeners (`Relic.attach` →
`combat.hooks.register(self)`, `relics/base.py:152-154`). The dispatcher
duck-types (`if hasattr(l, "modify_damage_additive")`), so **no member on `Relic`
is required** and six enchantments plus four powers already implement it. Mystic
Lighter is a **one-method fix**, not a pipeline change.

Root cause, executed: `sweep-stub-premises` maps a C# hook to a sim hook with

```python
sim = _RUN_HOOK_MAP.get(h) or (h if h in combat_hooks else None)   # relic_probes.py:1073
```

`h` is a **PascalCase** C# name; `combat_hooks` holds **snake_case** HookSystem
method names. The second branch can therefore never match — verified by executing
the comparison — so every dropped COMBAT hook outside the run-level
`_RUN_HOOK_MAP` (which contains only run-level hooks) is `continue`d and appears
in **neither** output bucket. I re-ran the snake_case mapping for all seven hooks
the sweep excludes on this basis: exactly **one** is a real HookSystem hook
(`modify_damage_additive`), the other six genuinely are not. So the sweep's 33 is
really 34, and the fix is `re.sub(r'(?<!^)(?=[A-Z])','_',h).lower()` before the
membership test.

**This is the stream's second under-report** (batch 8's Sweep B first-line bug was
the first) and the direction that costs the most: an over-report wastes a
reader's time and gets caught, an under-report silently shrinks the work list and
files a one-relic fix as a pipeline project.

### 2. Sweep A's "C# resets" column is still a bare hook name in the TURN-START bucket

Batch 6 found that the column was an *override census*, not a *reset census*, and
got it brace-matched to print the actual assignments — but **only in the "not
reset before a reader" bucket**. The `RESET AT TURN START` bucket still prints
`C# resets: ['AfterCombatEnd']`. For `ornamental_fan` that reads as a real reset
the sim drops; `OrnamentalFan.cs:123-127` assigns exactly one field at combat
end and it is `IsActivating = false`, a one-second glow flag whose only readers
are `DisplayAmount` and `UpdateDisplay`. Same defect, same fix, other bucket.

### 3. Cross-record disagreement under binding rule 3 — a missing `undo_after_obtained`

Two verdicts exist for the same mechanism and I could not find a principled line
between them:

- `fake_mango` N2 → **gap** (dormant), for a max-HP relic with no undo.
- `golden_pearl` N3 and `jewelry_box` N3 → **faithful**, "no C# counterpart", even
  though golden_pearl's own rationale predicts *"a spurious floor_gold diff of
  exactly 150"* and calls it "cheap to close … the same family as batch 1's
  big_mushroom finding".
- `fake_lees_waffle` N4 → **faithful**, but on a real distinction (it changes only
  current HP, which the runner re-pins anyway).

`relics/base.py:143-151` draws the line at "relics whose pickup mutates run state
outside `run.relics`", which covers max HP, gold AND deck edits alike — so
fake_mango's max-HP framing is not the line either. I matched **fake_mango** for
`nutritious_oyster` (closest analogue: a max-HP relic on the same runner path) and
am reporting the conflict rather than editing records I do not own. The stream
owner should pick one direction; my read is that all four are the same sim-only
defect and `gap` (with a "no C# counterpart" note) is the honest label, because
the *observable* is a false DETECTOR-3/floor-gold divergence either way.

---

## New bug-class candidates (each with the unit that exhibited it)

### A. A docstring that misdescribes the PORT'S OWN behaviour — pointing at a FALSE gap

`nunchaku.py:14-15`: *"Every time you play 10 Attacks, gain 1 energy. (The game's
counter persists across the run; **the sim's is per-combat, like Happy Flower**.)"*

The sim's counter is **not** per-combat. `_attacks_played` is set in `__init__`
and never reset, relic instances live on `RunState.relics` and are re-attached to
each `CombatState`, so it runs for the whole run — *executed:* one instance
through two 6-Strike combats reports 6, then 12. And C#'s `AttacksPlayed` is a
`[SavedProperty]` (`Nunchaku.cs:59-72`) that nothing resets, i.e. also per-run.
**The port is faithful and the docstring says it is divergent.**

Classes 12 and 19 both cover false claims that talk you *out of* a real gap
(class 12: a false claim about the sim's capabilities; class 19: a false claim
about the source's constant). This is the third direction: a false claim about
what the port itself does, which talks you *into* a gap that does not exist.
Sweep A's rewrite note ("the fixed column prevents false gaps as well") is the
mechanical half of the same problem; this is the prose half. Suggested wording:
*"A port's docstring may misdescribe the PORT. Verify a claimed divergence by
execution before recording it, not just a claimed equivalence."*

### B. Pool-wide shape: `run.transformable_cards()` drops `FromDeckForTransformation`'s Quest clause

Not a per-unit quirk. `CardSelectCmd.cs:487` filters
`c.Type != CardType.Quest && c.IsTransformable`; `run.py:364-366` returns every
non-Eternal deck card. Its docstring ("in the deck this equals IsRemovable") is
true of `IsTransformable` (`CardModel.cs:739-750`) but silently ignores the
caller's extra clause. **Six ported call sites** share the helper: `new_leaf`
(dormant, floor-0-only), `leafy_poultice`, and `events/endless_conveyor.py:97`,
`morphic_grove.py:44`, `symbiote.py:52`, `trial.py:99` — all five of the events
ARE reachable after a Quest card can be in the deck (`byrdonis_nest`,
`the_legends_were_true`, `the_lantern_key` add them). So the mechanism is live
*somewhere*, just not at this batch's site. Worth a `sweep-transformable` before
the event stream reaches those five, and worth the event stream re-using rather
than rediscovering.

### C. Confirming shape (no new class needed): the per-Replay `AfterCardPlayed` gap hits every counting relic

Three of this batch's fifteen (`nunchaku`, `ornamental_fan`, `mummified_hand`)
are LIVE instances of `hook_dispatch` G4, and a fourth (`music_box`) is provably
immune because its own once-per-turn latch absorbs the second iteration. G4's
issue text already says "every one of the sim's 48 `on_card_played` listeners"
widens it, so this is confirmation, not discovery — but it is worth recording
that the *severity* varies by counter lifetime: `nunchaku`'s counter is per-RUN,
so its offset never washes out, which makes it the worst instance found so far
(worse than G4's own `pen_nib` example).

---

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file from the skeleton on the first
try; `tools/audit/name_overrides.json` needs no additions. Obtainability proved
for all 15 (`relic_probes_b10.py pool`): 6 via the transcribed grab bag
(`mummified_hand` Rare, `mystic_lighter` Shop, `nunchaku` Uncommon,
`oddly_smooth_stone` Common, `old_coin` Rare, `orichalcum` Uncommon,
`ornamental_fan` Uncommon, `orrery` Shop — 8), 5 via the ported Neow event
(`neows_bones`, `neows_talisman`, `neows_torment`, `new_leaf`,
`nutritious_oyster`), `music_box` via the ported Vakuu event and
`nutritious_soup` via the ported Tezcatara event.

---

## Unverified / deliberately out

- **`nutritious_oyster` G1 is not labelled LIVE.** I executed the defect (undo
  leaves 71/91 instead of 60/80) but did not run a conformance seed to observe
  the Neow swap, so it stays dormant with the trigger named. Running one seed
  would settle it.
- **`neows_bones` N2 carries a cross-unit dependency I did not settle:** Sweep B
  records that `scroll_boxes` leaves `is_allowed_at_neow` True where C# gates on
  `CanGenerateBundles(player)`. If Scroll Boxes should be excluded, Neow's Bones'
  pool loses an entry and G1's divergence changes shape. That is `scroll_boxes`'
  own record to settle.
- **`music_box` N4's hand-overflow equivalence** rests on `cmds.py`'s own
  docstring, not on a line of `CardPileCmd.cs` I read; flagged in the record.
- **Sweep C's remaining six excluded hooks** (`ModifyMerchantPrice`,
  `ShouldRefillMerchantEntry`, `ModifyCardRewardCreationOptions`, `ShowCounter`,
  `AfterGoldGained`, `ModifyExtraRestSiteHealText`) I verified are genuinely not
  HookSystem hooks, but I did not check whether they have run-level `Relic`
  counterparts under different names.
- **No engine code, no shared sweep/PROMPT/seam file, and no other batch's record
  was touched.** The suite is at its 2476/31 baseline, which is the mechanical
  proof of that.

**Commit:** `6458e73a` on `audit-relic-b10` (not pushed).
