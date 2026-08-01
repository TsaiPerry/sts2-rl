# R4 review — `relic-1` unlabelled batch (14 entries, 13 records)

Reviewer pass, 2026-07-31. Everything below was re-derived from the C# and
from the current worktree; the report's prose was used only to know what to
check. Commands run are named inline.

**Status: NEEDS-FIXES.** All 14 *verdicts* survive review — I overturned none
— but three of the fourteen tests do not pin what the report says they pin,
and one dormancy enumeration (`unsettling_lamp` G4) is materially incomplete
in exactly the way the protocol singles out. The verdicts are right; part of
the evidence is not.

---

## 0. Delta and protocol compliance

- `git status --short`: the only lane artifacts are **untracked** —
  `test/test_r13_relic1.py` and `.superpowers/sdd/round13/R4-report.md`.
- `git diff -- sts2_rl/relics` → **empty**. Zero production edits, as claimed.
- `audit/records/**` and `audit/GAP-QUEUE.md`: **untouched**. The one staged
  `audit/` path (`M  audit/tools/unlabelled_batches.py`) is the controller's
  brief generator, staged alongside the staged `.superpowers/sdd/round13/*`
  briefs; it is not attributable to this lane, whose own two files are
  untracked (i.e. no `git add` happened here).
- Footprint respected: nothing outside `test/` was written. `sts2_rl/powers.py`
  (` M`), the reward/driver files and the other `R*-brief.md` files belong to
  concurrent lanes and were ignored per instructions.
- Test counts reproduced exactly: `py -m pytest test/test_r13_relic1.py -q`
  → **14 passed**; the report's 11-file command → **516 passed**.

---

## 1. Per-entry verdicts

### 1. `relic/archaic_tooth/AfterObtained` — **CONFIRM** (DORMANT-ENUMERATED)

Both divergences re-derived from source, not from the record.

- G1 is real: `ArchaicTooth.cs:151-155` grants **exactly one** level —
  `if (starterCard.IsUpgraded) CardCmd.Upgrade(cardModel);` — against
  `archaic_tooth.py:30-32`'s `for _ in range(original.upgrade_level)`.
- G1 dormant, executed: a census over all **203** registered card classes gives
  `max_upgrade_level ∈ {0, 1}` (168 at 1, 35 at 0). The attribute is defined on
  every class, so the test's `getattr(..., 1)` default is not masking anything —
  I checked for a `MISSING` bucket explicitly and it is empty. The test is sound.
- G2 dormant, executed: all **19** registered `Enchantment` subclasses agree on
  `bash` vs `break` (13 True/True, 6 False/False). The test iterates
  `_ENCHANTMENT_CLASSES` rather than inspecting Swift alone, which is the right
  shape. (The report's queue annotation says "9 predicates"; the class count is
  19. Cosmetic.)

**Reviewer correction the report missed.** The record — and the report
repeating it — says the sim "adds a `can_enchant(transformed)` condition C#
lacks". C# does not lack it: `CardCmd.Enchant` (`CardCmd.cs:532-538`) opens
`if (!enchantment.CanEnchant(card)) throw new InvalidOperationException(...)`.
The real divergence is **silent skip vs. hard throw**, not "condition vs. no
condition". Dormancy is unaffected (nothing discriminates the two cards), but
the guard text should be corrected when next touched.

### 2. `relic/booming_conch/AfterSideTurnStart` — **CONFIRM**

- G2 real: `BoomingConch.cs:53` grants via `await PlayerCmd.GainEnergy(...)`;
  `booming_conch.py:34` is a bare `player.energy += self.ENERGY`. The chained
  path exists and is bypassed (`cmds.py:1592` `amount = hooks.modify_energy_gain(...)`).
- Hook slot (G1) genuinely closed: `hooks.py:1205-1217`'s `after_side_turn_start`
  is the **player side's** leg (the enemy side is `after_enemy_side_start`), so
  the relic cannot fire on an enemy turn. Checked because the relic's own
  `_in_elite_first_turn` has no side test of its own.
- Dormancy re-derived: `modify_energy_gain` has exactly **one** implementer in
  the whole package (`grep -rn "def modify_energy_gain" sts2_rl/` →
  `powers.py:834`, `NoEnergyGainPower`), applied from exactly one place
  (`cards/expect_a_fight.py:58`, a card play), and expiring at the owner's own
  `after_player_turn_end`. A card cannot have been played before turn 1's
  side-turn-start, so the chain is empty in Conch's only window.

### 3. `relic/fake_strike_dummy/ModifyDamageAdditive` — **CONFIRM**

`FakeStrikeDummy.cs:33` is `if (dealer != Owner.Creature && cardSource.Owner != Owner) return 0m;`
— an AND, so either disjunct alone lets the bonus through; `fake_strike_dummy.py:34`
narrows to `dealer is self.player`. Real.

Dormancy re-censused independently, not inherited:
- All 8 strike-tagged cards enumerated from `_CARD_CLASSES` and each one's
  `DamageCmd.deal` read individually (`ashen_strike:42`, `perfected_strike:44`,
  `pommel_strike:37`, `setup_strike:41-44`, `strike:29`, `twin_strike:40`,
  `ultimate_strike` in `event_cards.py`, `seeker_strike` in
  `colorless_attacks.py:456-458`) — every one passes `dealer=ctx.player`.
- The 9 `card=`-without-`dealer=player` sites are all player self-damage and
  none carries the `strike` tag.

### 4. `relic/fur_coat/AfterCreatureAddedToCombat` — **CONFIRM the finding; NEEDS-FIX the pin**

The citation-error finding is **correct and I verified it end to end**, which
makes it the most load-bearing thing in the report:

- `grep AfterCreatureAddedToCombat` over the whole decompiled tree returns 9
  lines: the `Hook` declaration/dispatcher (`Hook.cs:355,362,366`), the
  `AbstractModel` virtual (`AbstractModel.cs:539`), four overrides
  (`FurCoat.cs:130`, `PhilosophersStone.cs:41`, `SandpitPower.cs:126`,
  `Murderous.cs:23`) — and **exactly one call site**: `CreatureCmd.cs:81`,
  the last statement of `CreatureCmd.Add`.
- `CombatManager.AfterCreatureAdded` (`src/Core/Combat/CombatManager.cs:860-867`,
  read in full) calls `creature.AfterAddedToRoom()` and `Monster.RollMove` and
  nothing else. `Creature.AfterAddedToRoom` (`Creature.cs:414-420`) forwards to
  `Monster.AfterAddedToRoom` — a per-monster virtual (Zapbot, WaterfallGiant),
  not a hook.
- So the `StartCombatInternal` loop at `CombatManager.cs:394-398` does **not**
  dispatch this hook. The record's divergence (a) never existed; the sim
  (`cmds.py:790`, inside `CreatureCmd.add`) matches C# by architecture.

Divergence (b) re-confirmed: `fur_coat.py:98,102` write `hp = 1` raw where C#
goes through `CreatureCmd.SetCurrentHp` (`FurCoat.cs:126,139`); `on_hp_changed`'s
only listener in the package is `relics/red_skull.py:51`, which reads the
player's HP only. Dormant. Verdict `gap` via G3 stands.

**Defect D1 — the pinning test is vacuous in its load-bearing half.**
`test_on_creature_added_hook_never_fires_for_starting_enemies` registers the spy
*after* `_combat(...)` has already built the `CombatState`:

```python
cs = _combat(["fur_coat"], seed=4)
cs.hooks.register(_Spy())
assert calls == []          # cannot fail: the spy did not exist during construction
```

The report claims "a spy listener sees zero calls during `CombatState`
construction". It sees zero calls because it was not there. The second half
(`CreatureCmd.add` → `calls == [joiner]`) is fine. Fix: wrap
`HookSystem.on_creature_added` with a counter *before* constructing the combat
(monkeypatch), or register the spy through the `relics=` list so it is attached
during construction.

### 5. `relic/gremlin_horn/AfterDeath` — **CONFIRM** (with a citation correction of my own)

The report's stale-citation correction is right in substance: there are two
`on_damage_dealt` implementers, and both are unreachable from the
player-kills-enemy direction. I read both bodies:

- `ImbalancedPower` — `def on_damage_dealt` at `powers.py:2516`, body at
  `:2536`: `if dealer is self.owner and was_fully_blocked:`.
- `PaperCutsPower` — `def on_damage_dealt` at `powers.py:3631`, body gates on
  `dealer is self.owner and target.side == "player" and amount > 0 and is_powered_attack(props)`.

`self.owner` is the enemy holding the power in both cases, so neither fires when
the player deals the killing blow. Conclusion stands.

**Correction to the report:** its line citations (`powers.py:2486-2500`,
`:3580-3608`) point at `SteamEruptionPower` and `BattlewornDummyTimeLimitPower`,
not at the two powers named. `powers.py` is being edited by a concurrent lane
(` M` in `git status`), so line numbers taken mid-wave drift. Cite by symbol.

### 6. `relic/kusarigama/AfterCardPlayed` — **CONFIRM the verdict; NEEDS-FIX the reasoning and the pin**

Verdict is right and I re-derived the dormancy myself:

- `Kusarigama.cs:115` draws with `Rng.CombatTargets.NextItem(CombatState.HittableEnemies)`;
  `kusarigama.py:46-51` draws over `self.living_enemies()` =
  `[e for e in enemies if not e.is_gone]` (`relics/base.py:440-447`), while
  `hittable_enemies` = `[e for e in enemies if is_hittable(...)]` and
  `is_hittable` = `not target.is_gone and hooks.should_allow_hitting(target)`
  (`cmds.py:123`). Real divergence in principle.
- The two lists provably coincide today: `should_allow_hitting` has exactly
  three implementers (`powers.py:1996` Illusion, `:2920` Decimillipede
  Reattach, `:4144` Adaptable) and each returns `False` iff
  `target is self.owner and self.is_reviving`. `is_reviving` is armed only from
  `on_death` (so `hp <= 0`), and **every** ported clearing path clears the flag
  *before* restoring HP — `test_subject._respawn` calls `adaptable.do_revive()`
  then `_revive(form_hp)`; `ReattachPower.do_reattach` sets `is_reviving = False`
  then `owner.hp = amount`; `IllusionPower.revive` sets `is_reviving = False`
  then heals. So `is_reviving ⇒ is_dead ⇒ is_gone`, and `living_enemies()`
  already excludes everything `hittable_enemies` would.

**Two problems with how the report got there.**

1. Its primary stated reason — "dormant *specifically because* `DamageCmd.deal`
   applies its own `should_allow_hitting` backstop (`cmds.py:75`) before any
   hook fires" — is a **red herring, and would be wrong if the lists ever did
   diverge**. Kusarigama's divergence is in the *draw*, not the hit: a different
   candidate-list length changes which enemy the `CombatTargets` stream selects
   and burns the same RNG index against a different list. A downstream refusal
   of the hit does not repair a mis-targeted, mis-indexed draw. The load-bearing
   argument is list-coincidence, which the report also states — but the record
   should not carry the backstop clause as the reason.

2. **Defect D2 — the test that supposedly re-executes the census does not
   execute it.** `test_should_allow_hitting_false_always_coincides_with_is_dead`
   never calls `should_allow_hitting`, never calls `hittable_enemies()`, never
   compares the two lists, imports `AdaptablePower` without using it, exercises
   1 of the 3 implementers, and its two assertions (`enemy.is_dead is True`,
   twice) are trivially true because the test itself set `enemy.hp = 0`. It
   would pass unchanged if all three implementers were deleted. This test is the
   only "execution" behind **two** entries (kusarigama and stone_calendar). Fix:
   assert `set(cs.hittable_enemies) == set(living)` while a creature is
   `is_reviving`, and loop over all three power classes.

### 7 & 8. `relic/lizard_tail/ShouldDieLate` + `/AfterPreventingDeath` — **CONFIRM** (STALE-ALREADY-FIXED)

Verified on both sides against the current tree, not the record:

- `LizardTail.cs:40-51` is a pure predicate (`creature != Owner.Creature → true`,
  `WasUsed → true`, else `false`); `:53-59` is `Flash(); WasUsed = true;` then
  `CreatureCmd.Heal(creature, Math.Max(1, MaxHp * 50/100))`.
- `relics/lizard_tail.py:32-52` is likewise pure — `if creature is not self.player:
  return True; return bool(self._used)` — with **no** mutation, and `:54-71`
  is the sole writer of `_used` plus the heal. `_heal_pending` is gone from the
  file entirely.
- The record's own guards confirm the staleness: G1, G2, G4 and N1 all read
  `faithful`/"Closed 2026-07-27", and **G3 reads `faithful` / "Closed 2026-07-29
  (round 8)"**. The manifest's hook-level `issue` text ("the port still sets
  `self._used = True` and `self._heal_pending = True` INSIDE `should_die_late`
  … cards/breakthrough.py's bare `should_die`") is stale on *both* clauses —
  G3's own close note already records that round 7 deleted the breakthrough
  witness. Nothing is left open under either hook. Closing both is correct.

Minor: the two new tests near-duplicate existing pins —
`test_lizard_tail_should_die_late_is_pure` (`test_tier1_last_five.py:108`) and
`test_lizard_tail_spends_its_charge_when_it_actually_prevents` (`:123`). The new
`..._charge_spent_and_healed_only_in_after_preventing_death` does add value
(exact `max_hp * 50 // 100` where the old one only asserted `hp > 0`); the
purity test adds nothing. Not a defect, but the report should have said "already
pinned, plus one tightened assertion" rather than presenting both as new
execution.

### 9. `relic/miniature_cannon/ModifyDamageAdditive` — **CONFIRM the verdict; the report's reason is loose**

`MiniatureCannon.cs:31-34` is the same AND-of-negatives as the two dummies;
`miniature_cannon.py:36` narrows to `dealer is self.player`. Real.

The report's dormancy sentence — "every ported `card=`-but-no-`dealer=player`
site is still a non-Strike, **non-upgrade-relevant** self-damage card" — does
not hold as written: Miniature Cannon does not care about the strike tag, only
about `card.upgrade_level > 0`, and **four of those nine sites are upgradable
cards** (`blood_wall`, `bloodletting`, `hemokinesis`, `offering` — all
`max_upgrade_level = 1`). Executed the real reason instead:

- Those four pass `props=DamageProps.CARD_HP_LOSS`, and `is_powered_attack(CARD_HP_LOSS)`
  is `False` — the relic's own first guard (and `cmds.py`'s stage gate) rejects
  them.
- The other five (`burn`, `decay`, `infection`, `toxic`, `wither`) pass no props
  at all, but each has `is_unpowered = True` (so `DamageCmd.deal` infers
  `CARD_UNPOWERED`) **and** `max_upgrade_level = 0`, failing the guard twice over.

Dormant — for a reason the record should state as the props gate, not as
"non-upgrade-relevant".

### 10. `relic/pen_nib/AfterCardPlayed` — **CONFIRM** (STALE-ALREADY-FIXED; the C# re-reading is correct)

I re-derived the whole chain rather than trusting the report:

- `Hook.AfterCardPlayed` (`Hook.cs:278-294`) enumerates
  `combatState.IterateHookListeners()` — **not** `IterateCombatHookListeners` —
  and `Hook.cs:275-276` says why in the source's own words: *"Dispatched
  directly, not through the IterateCombatHookListeners guard: it completes
  resolution of the card that caused the kill."* So `hook_dispatch` G8's gate,
  which G3 leaned on, does not apply to this hook at all.
- Its single call site is `CardModel.cs:1959`, inside the `for (int i = 0; i <
  playCount; i++)` loop, gated on `CombatManager.Instance.IsInProgress` (`:1957`).
- `IsInProgress` is written `false` at exactly three places
  (`CombatManager.cs:915`, `:962` `ProcessPendingLoss`, `:977`
  `EndCombatInternal`), all reachable only from `CheckWinCondition`/teardown —
  and the ambient `CheckWinCondition` runs at `ActionExecutor.cs:161-171`,
  **after** `readyAction.Execute()` has completed. A card play is one action, so
  `IsInProgress` is still `true` on the lethal iteration.

G3's premise ("C# skips `Hook.AfterCardPlayed` when the play ended the combat")
is therefore backwards, and the record itself flagged that it had not executed
that leg. The sim's `if not self.is_over:` gate (`combat.py:986`, with
`is_over = phase == Phase.COMBAT_OVER` at `:1526`, flipped only in `_end_combat`
which the card paths reach at `:863`/`:880` after `_resolve_card_play` returns)
matches. `combat.py` is clean in `git status`, so the fix is genuinely committed,
not asserted. The test is a real end-to-end pin (primes `_attacks_played = 9`,
kills the enemy on the doubled Strike, asserts `_card_to_double is None`).

### 11. `relic/silver_crucible/ShouldGenerateTreasure` — **CONFIRM**, and the leg the report left inherited is now closed

C# side verified directly: `OneOffSynchronizer.DoTreasureRoomRewards`
(`src/Core/Multiplayer/Game/OneOffSynchronizer.cs:128-143`) opens
`if (!Hook.ShouldGenerateTreasure(...)) return 0;` and only then reaches
`await TryHandleSpoilsMap(player)` (`:141`, defined `:149-167`). So the Spoils
payout really is *inside* the gate. Sim side: `run.py:1320-1338` — the chest
relic and gold sit inside `if all(r.should_generate_treasure(self) ...)`, but
`resolution.gold += self._complete_map_point_quests(point)` at `:1338` is
outside it. Divergence real.

**The leg the report explicitly declined to re-derive, re-derived:**
`silver_crucible.py:55-56` returns `treasure_rooms_entered > 1`, over a
**run-scoped** counter incremented in `after_room_entered` (which `run.py:1291`
runs *before* the TREASURE branch) — so only the run's **first** treasure room
is suppressed. And every act map places an entire unavoidable TREASURE row:
`actmap.py:485-491` (`StandardActMap.AssignPointTypes`) sets **every** point in
row `row_count - 7` to `MapPointType.TREASURE` with `can_be_modified = False`,
and `replace_treasure_with_elites` defaults `False` with no live trigger
(`actmap.py:335`, `:1039`, `:1106`; the module docstring calls it out as having
"no live ascension trigger in the source"). The golden-path fixture carries two
TREASURE nodes too. So the run's first treasure room is always in act index 0,
while `spoils_map.py:35` pins `SPOILS_ACT_INDEX = 1`. The two can never meet.
**Dormant, fully derived.**

### 12. `relic/stone_calendar/BeforeSideTurnEnd` — **CONFIRM the verdict; inherits defect D2**

`StoneCalendar.cs:96` damages `CombatState.HittableEnemies`; `stone_calendar.py:27`
iterates `self.living_enemies()`. Same mechanism as entry 6, dormant for the
same (correct) list-coincidence reason I re-derived there. Same test defect.

### 13. `relic/strike_dummy/ModifyDamageAdditive` — **CONFIRM**

`StrikeDummy.cs:33` read in full; identical shape and identical census to entry 3.

### 14. `relic/unsettling_lamp/BeforePowerAmountChanged` — **NEEDS-FIX** (verdict survives; G4's enumeration does not)

**G2 close — CONFIRM.** Read `UnsettlingLamp.cs:62-168` in full. Neither the
latch (`:71-104`) nor the multiplicative (`:106-129`) contains an `amount <= 0`
bail; both gate on `power.GetTypeForAmount(amount) != PowerType.Debuff`
(`:97`, `:124`). `unsettling_lamp.py:65-80` matches — no bail, and
`power_cls.type_for_amount(amount)`. `Power.type_for_amount` (`powers.py:72-94`)
is a faithful port of `PowerModel.GetTypeForAmount` (`PowerModel.cs:460-471`),
which I diffed clause by clause. It is genuinely wired:
`cmds.py:868-873` runs the additive then multiplicative given-passes under
PowerCmd.Apply's own `applier is not None and _combat_contains_creature(...)`
gate, and `hooks.py:724-744` is the product-fold dispatcher. `seam/power_cmd.json`
G2 does read `faithful` / "Closed 2026-07-31 (tier-2 campaign): (Task 17.)" —
the report's claimed already-committed work exists. Malaise/Resonance remain
unported. Close G2.

**G3 — CONFIRM still open, still dormant.** `UnsettlingLamp.cs:106-129` has no
applier and no target-side guard; only the latch does (`:85` `applier != Owner.Creature`,
`:89` `target.Side == Owner.Creature.Side`). `unsettling_lamp.py:67` re-applies
`applier is not self.player or target is self.player` on every call. Real.

**G4 — NEEDS-FIX. The re-census is incomplete, and it is incomplete in the
exact shape the protocol warns about.** The report states the census as four
`auto_play_card` sites (cascade, colorless_skills ×2, plus a "new fourth"
`howl_from_beyond.py:51`). `grep -rn "auto_play_card(" sts2_rl/` returns **ten**:

```
cards/cascade.py:58            cmds.py:1552 (CardPileCmd.auto_play_from_draw_pile)
cards/colorless_skills.py:134  enchantments.py:401 (Imbued)
cards/colorless_skills.py:187  potions.py:1050
cards/howl_from_beyond.py:51   powers.py:999  (HellraiserPower)
                               powers.py:1355 (StampedePower)
                               relics/whispering_earring.py:86
```

Two of the six omitted sites are not bookkeeping — they widen the class G4's
argument has to cover:

- **`cards/havoc.py:53`** calls `CardPileCmd.auto_play_from_draw_pile`
  (`cmds.py:1498-1552`) from inside its own `on_play`. That is a **fifth
  card-level nested auto-play** the "3 sites"/"4 sites" figure has never
  included — and other records cite that figure.
- **`HellraiserPower`** (`powers.py:987-999`, applied by the ported
  `cards/hellraiser.py:36`) auto-plays on `on_card_drawn_early`. That turns
  **every card that draws mid-resolution** into a nested-auto-play site, which
  is a strictly larger set than "cards that auto-play another card". G4's
  reachability argument was never stated against that set.

I then re-derived the verdict myself so the finding is not just procedural. An
AST census over `sts2_rl/cards/` for classes that both draw
(`DrawCmd.draw` / `auto_play_from_draw_pile` / `draw_cards`) **and** apply a
power to a non-player target yields exactly one class, `MadScienceCard`, whose
draw (`_play_skill`, `wisdom` rider) and enemy debuffs (`_play_attack`,
`sapping`/`choking` riders) are on mutually exclusive `tinker_type` branches
(`mad_science.py:101-132`). Havoc, cascade, colorless_skills and
howl_from_beyond apply no debuff of their own. So **no ported card can latch the
Lamp, nest an auto-play, and debuff again — G4 stays DORMANT.** The verdict is
right; the enumeration backing it must be replaced with the 10-site one plus the
Hellraiser class-widening, and the "3 sites" figure other records cite should be
corrected wherever it appears.

**Also: the manifest is wrong about this rollup's membership.** Its issue text
says the divergences are "verdicted at its own guard (G2, G3, G4, **G5**)".
`audit/records/relic/unsettling_lamp.json` has no G5 — its entries are G1
(faithful), N1, G2, N2, G3, G4, N3, N4, N5, and the only `gap`s are G2/G3/G4.
The report followed the record (correctly) but did not flag the manifest error.

Test note: `test_unsettling_lamp_g3_same_card_self_debuff_not_doubled_dormant`
asserts `factor == 1`, i.e. it pins the **known-divergent** sim behaviour. That
is a legitimate divergence characterisation for a dormancy verdict (the docstring
says so), but it will go red the day G3 is fixed, reading like a regression. Same
shape as `test_booming_conch_..._bypasses_...` and the three `with_none == base`
assertions. Recommend a single shared marker comment (`# DIVERGENCE PIN — delete
when <record>/<guard> closes`) so the next lane does not mistake them for
fidelity pins. Not a defect; the dummy tests already carry that comment inline.

---

## 2. Spec-compliance verdict

**Substantially compliant, with two protocol misses.**

Required and delivered: all 14 entries settled by execution with a verdict from
the allowed set; C# citations throughout; per-entry verdicts, record-close
proposals that state *which reasoning they replace*, queue annotations in the
terse house style, test commands with counts, and a findings section — every
clause of the report contract. No production edits, no `audit/**` edits, no
index mutation, footprint honoured, `py` launcher used, the known
`test_conformance_floor_state.py` failures neither touched nor counted, full
suite not run.

Misses:

1. **The dormancy-enumeration rule was not met for `unsettling_lamp` G4.** The
   protocol's wording is explicit — "an enumeration naming every consumer you
   checked… ask *what else reads this?*, not *does the recorded consumer still
   hold?* — a round-12 dormancy verdict was overturned by a third consumer
   nobody had listed." The report checked whether the recorded 3-site census had
   grown by one, found `howl_from_beyond`, and stopped; it had grown by seven.
   The verdict survives only because I re-derived it.
2. **Entry 11 shipped with a knowingly inherited leg.** The report flags this
   honestly, which is the right behaviour under the protocol — but the leg was
   ~10 minutes of `actmap.py` reading, and "flagged rather than silently
   inherited" is a floor, not a target. Closed above.

Nothing beyond scope was done: zero production lines changed, and no record or
queue file was edited.

---

## 3. Code-quality verdict on `test/test_r13_relic1.py`

**Good structure, three defective tests.** The file is well organised: one
`_combat` helper, banner comments that carry the C# reasoning for each cluster,
docstrings that state the guard's dormancy premise rather than restating the
code. 14/14 pass in 0.53s, no fixtures, no ordering coupling.

Defects, in severity order:

- **D1** (entry 4) `test_on_creature_added_hook_never_fires_for_starting_enemies`:
  the `assert calls == []` half is vacuous — the spy is registered after
  construction, so it cannot observe construction. Contradicts the report's
  explicit claim that the spy "sees zero calls during `CombatState` construction".
- **D2** (entries 6 and 12) `test_should_allow_hitting_false_always_coincides_with_is_dead`:
  never calls `should_allow_hitting` or `hittable_enemies`; both assertions
  (`enemy.is_dead is True`) restate a value the test itself assigned; covers 1 of
  3 implementers; `AdaptablePower` imported and unused. It is the sole execution
  behind two entries' dormancy and would pass with the mechanism deleted.
- **D3** (entry 3) `test_strike_tagged_cards_all_deal_damage_with_the_player_as_dealer`:
  the name and docstring promise a dealer census; the body asserts only
  `len(strike_tagged) == 8`, then redundantly `assert strike_tagged`. It pins a
  brittle content count, not the claim. (I verified the underlying claim by hand
  — all 8 do pass `dealer=ctx.player` — so the census is *true*, just untested.)
- Minor: unused imports `EnergyCmd` and `RunState` (line 19, 22); `pytest` used
  only in the `__main__` guard; partial duplication of `test_tier1_last_five.py`'s
  lizard-tail pins.

The other 11 tests do pin what the report says they pin. The pen_nib, lizard-tail
heal, archaic-tooth census, enchantment census and lamp G2 tests are all genuine,
non-circular, C#-derived assertions.

---

## 4. Reviewer findings that outrank the task's

**F1 (new gap, not in any record I can find): the sim's card-play loop is
missing C#'s `Owner.Creature.IsDead` early return before `Hook.AfterCardPlayed`.**
Found while re-deriving entry 10. `CardModel.cs:1904-1965` checks
`if (Owner.Creature.IsDead) return;` at **:1932** (after `OnPlay`), **:1940**
(after the enchantment's `OnPlay`) and **:1950** (after the affliction's) — all
*before* the `IsInProgress`-gated `Hook.AfterCardPlayed` at :1957-1959 — and
again at :1960 after it. `combat.py:940-996` has no such check: it runs
`card.on_play`, `after_attack`, `card.enchantment.on_play`, then
`if not self.is_over: self.hooks.on_card_played(...)` at :986, and only *then*
`if self.player.is_dead: break` at :995. (The `self.player.is_dead` test at
:958 breaks the ALL_ENEMIES routing loop, not the play loop.) So a card play
that kills its own player — Offering / Bloodletting / Hemokinesis / Blood Wall
at low HP, or a self-damage curse — dispatches `AfterCardPlayed` to every
listener in the sim where C# returns before dispatching. `combat.py` is outside
R4's footprint, so this is a queue item, not a fix. Likely unobservable in a
single-player run that is over anyway, but it is a real ordering divergence
sitting inside the very hook two of this batch's entries own, and it should be
filed under `seam/hook_dispatch` or `seam/card_play` and reasoned about rather
than left undiscovered.

**F2: `CardCmd.Enchant` throws on `!CanEnchant`** (`CardCmd.cs:535-538`), so
`relic/archaic_tooth` G2's "a condition C# lacks" is a mischaracterisation — see
entry 1. Text-only correction.

**F3: the `auto_play_card` census that several records cite is wrong by a factor
of ~2.5** — 10 sites, not 3 or 4, and `HellraiserPower` makes the reachable set
"any card that draws" rather than "any card that auto-plays". See entry 14. Any
record whose reachability argument rests on that figure needs re-checking, not
just `unsettling_lamp` G4.

**F4: `powers.py` line citations taken this wave are unreliable** — a concurrent
lane has it modified, and the report's two `on_damage_dealt` citations are
already 30-50 lines stale. Records written mid-wave against `powers.py` should
cite symbols, not lines.

---

## 5. Required fixes before this lane is approved

1. Repair D1, D2, D3 so the three entries they back (`fur_coat`, `kusarigama`,
   `stone_calendar`, `fake_strike_dummy`) actually have execution behind them.
   D2 is the important one: it is the only evidence for two dormancy verdicts.
2. Replace `unsettling_lamp` G4's enumeration with the 10-site `auto_play_card`
   census plus the Hellraiser class-widening, and carry the corrected verdict
   reasoning (which survives — see entry 14) into the record close proposal.
3. Restate `kusarigama`/`stone_calendar` G2's dormancy on list-coincidence alone;
   drop the `DamageCmd` backstop clause, which does not defend a draw-site
   divergence.
4. Restate `miniature_cannon`'s dormancy on the `is_powered_attack` props gate
   rather than "non-upgrade-relevant".
5. Fix the `powers.py` line citations (entry 5) and the `archaic_tooth` G2
   characterisation (F2); note the manifest's phantom `unsettling_lamp` G5.
6. File F1 as a new queue entry.

None of these changes a verdict. Every one of the 14 verdicts is **CONFIRMED**.

---

## Re-review (2026-08-01)

Scope: the fix pass only. The 14 entry verdicts are not re-opened — they were
CONFIRMED in the pass above and nothing in the fix pass touches them.

**Verdict: APPROVED.** All three test defects are genuinely repaired, the
`unsettling_lamp` G4 enumeration now matches my own census in both places it
appears, and every smaller item was applied. Two cosmetic wording issues remain
(noted below); neither asserts anything false and neither blocks.

### Item 1 — the three repaired tests: **PASS**

`py -m pytest test/test_r13_relic1.py -q` → **14 passed**. I did not take the
report's RED notes on trust: I copied the file to the scratchpad and ran **seven**
independent assertion mutations against the live package (`PYTHONPATH` pointed at
the worktree; the worktree itself was never modified).

| Mutation | Target | Result |
|---|---|---|
| MUT1 | D1 `assert calls == []` → `!= []` | **FAILED** (assertion is live) |
| MUT7 | D1 + `assert cs.enemies` prepended | passed — a starting roster really is present to observe |
| MUT2 | D2 Illusion `should_allow_hitting(reviver) is False` → `is True` | **FAILED** |
| MUT5 | D2 Adaptable `should_allow_hitting(boss) is False` → `is True` | **FAILED** |
| MUT6 | D2 Adaptable set-equality, `boss` added back | **FAILED** |
| MUT3 | D2 Reattach set-equality, `victim` added back | **FAILED** |
| MUT4 | D3 `all(d is cs.player ...)` → `is not` | **FAILED** |

- **D1 (`fur_coat`) — genuinely fixed.** `HookSystem.on_creature_added` is now
  monkeypatched at class level *before* `_combat(...)` runs (test lines 154-168),
  restored in a `finally`. MUT1 shows the assertion is live; the same spy
  demonstrably records the later `CreatureCmd.add` joiner, so it is not blind;
  MUT7 confirms there is a non-empty starting roster for it to have observed.
  The report's RED note holds.
- **D2 (`kusarigama`, `stone_calendar`) — genuinely fixed, and this was the
  important one.** The test now drives all three implementers to `is_reviving`
  through a real lethal `DamageCmd.deal` (`IllusionPower` on a plain monster,
  `AdaptablePower` via `TEST_SUBJECT_BOSS`, `ReattachPower` via
  `DECIMILLIPEDE_ELITE` with live siblings so `_all_others_down()` does not
  short-circuit), then calls `cs.hooks.should_allow_hitting` directly and asserts
  `{e for e in cs.enemies if not e.is_gone} == set(cs.hittable_enemies)` per leg.
  Four separate mutations (MUT2/MUT5/MUT6/MUT3) each kill it, so **all three legs
  are independently live** — where the old version would have passed with the
  whole mechanism deleted. It now pins exactly the list-coincidence claim the two
  entries rest on.
- **D3 (strike-tagged dealer census) — genuinely fixed.** Beyond MUT4 I ran an
  instrumented probe over the real path: every one of the 8 cards returns
  `play_card(0) is True`, each records at least one real `DamageCmd.deal`
  (`twin_strike` correctly records 2), every recorded `card=` is the card itself,
  and every recorded `dealer=` is `cs.player`. The test now executes the census
  its name promises instead of asserting a content count.

  Hygiene nit (non-blocking): the teardown restores `cmds_mod.DamageCmd.deal =
  original_deal`, a plain function, where the attribute was a `staticmethod` —
  verified `type(DamageCmd.__dict__['deal'])` goes `staticmethod → function`
  across the test. Every call site in the package is class-level
  (`DamageCmd.deal(...)`), which is unaffected — I confirmed a post-restore
  class-level call still works, and the 516-test run is clean — but
  `staticmethod(original_deal)` or `pytest`'s `monkeypatch.setattr` would be
  correct. Optional companion hardening: fold MUT7's `assert cs.enemies` into D1
  so the "zero calls" claim cannot silently go vacuous if the fixture encounter
  ever changes.

### Item 2 — the rewritten `unsettling_lamp` G4 enumeration: **PASS, both places**

Checked against my own AST census, not against the report's prose.

- The 10-site `auto_play_card` table is **exactly right**: the four previously
  known (`cascade:58`, `colorless_skills:134`, `:187`, `howl_from_beyond:51`)
  plus `cmds.py:1552`, `enchantments.py:401`, `potions.py:1050`, `powers.py:999`,
  `powers.py:1355`, `relics/whispering_earring.py:86`.
- The two that matter are both correctly identified and correctly explained:
  `cards/havoc.py:53` reaching `auto_play_card` through
  `CardPileCmd.auto_play_from_draw_pile` (a fifth card-level nested auto-play),
  and `HellraiserPower` (applied by `cards/hellraiser.py:36`) firing from
  `on_card_drawn_early`, which widens the reachable class from "cards that call
  `auto_play_card`" to "any card that draws mid-resolution."
- The `MadScienceCard` argument is reproduced correctly and independently
  re-derived: `tinker_type` is fixed per instance by `configure()`, and
  `_play_attack` (the enemy debuff) and `_play_skill` (the `wisdom` draw) are
  `if/elif` siblings that cannot both fire.
- **Carried into both the per-entry text (entry 14) and the record-close proposal
  (item 4)**, which was the specific thing I asked for since the controller
  applies close-proposal text near-verbatim. The queue annotation was updated too.
- The phantom manifest `G5` is flagged in entry 14, correctly attributed to the
  manifest generator rather than to the record.

This closes the one protocol miss in my §2. The enumeration now meets the "ask
what else reads this" standard.

### Item 3 — the smaller items: **PASS** (two cosmetic residues)

- **`archaic_tooth` throw-vs-skip (F2)** — applied, with the right citation.
  `CardCmd.cs:535-537` is `if (!enchantment.CanEnchant(card)) throw new
  InvalidOperationException(...)`; the guard text now reads "silent skip vs. hard
  throw." Applied correctly.
- **Stale `powers.py` citations (F4)** — applied. Entry 5 drops the line numbers,
  cites `ImbalancedPower`/`PaperCutsPower` by symbol, and adds a standing note not
  to re-add lines while `powers.py` is under concurrent edit. Entry 6 and the
  `should_allow_hitting` citations adopt the same symbol-only convention.
- **`kusarigama`/`stone_calendar` red herring** — removed. Both entries now name
  the divergence as a target-set/draw-site one and rest dormancy on
  list-coincidence alone; the `DamageCmd` backstop clause is gone.
- **`miniature_cannon` props gate** — applied, with the facts right: the four
  upgradable self-damage cards fail on `DamageProps.CARD_HP_LOSS`, the five curses
  fail twice over on `is_unpowered` + `max_upgrade_level == 0`.
- **Phantom manifest G5** — flagged.
- **F1 filed** — finding #5 now carries the full analysis (`CardModel.cs:1932,
  1940,1950,1960` vs `combat.py:986/995`) *and* a ready-to-paste queue annotation
  for `seam/hook_dispatch` / a new `seam/card_play` mechanism, correctly noting
  that C#'s gate is on the CARD OWNER's death — a different creature than the one
  `pen_nib`/`kusarigama`'s killing-blow analysis covers — and that the fix lives
  outside every current lane's footprint. That is the right disposition.

Cosmetic residues, neither blocking:

1. Entry 12 inherits entry 6's "the divergence is in the *draw*" phrasing, but
   `StoneCalendar.cs:96` damages the whole `HittableEnemies` **set** with no RNG
   draw at all — for stone_calendar it is a target-set divergence, not a draw.
   The conclusion is unaffected (list-coincidence is the stronger argument for
   both), but the two guards are not identical in shape.
2. The `kusarigama` and `miniature_cannon` **queue annotations** were not
   refreshed with the corrected reasoning the per-entry sections now carry.
   Harmless: neither annotation ever contained the retracted claims (the
   backstop clause and "non-upgrade-relevant" both lived only in the per-entry
   prose), so nothing false is being handed to the controller.

### Footprint re-check

The worktree has moved a lot since my first pass — other lanes have landed edits
to `combat.py`, `hooks.py`, `powers.py`, `cmds.py`, `run.py`, `rewards.py`,
`player.py`, `driver.py`, `afflictions.py`, `enchantments.py`, `cards/base.py`,
`monsters/**` and three test files. **None of that is R4's.** `git diff --
sts2_rl/relics` is no longer empty, but the sole changed file is
`sts2_rl/relics/base.py`, which R4's brief explicitly assigns to another lane
("NOT yours — `sts2_rl/relics/base.py` is owned by another lane this wave"); **no
individual `sts2_rl/relics/<name>.py` is modified.** `audit/records/**` and
`audit/GAP-QUEUE.md` remain untouched, and R4's own two artifacts
(`test/test_r13_relic1.py`, `R4-report.md`) are still untracked — no `git add`.
The broader 11-file command still reports **516 passed**, unchanged through all
of that churn.
