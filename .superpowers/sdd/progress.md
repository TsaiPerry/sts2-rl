# Tier-2 dormant-gap campaign — progress ledger

Plan: docs/superpowers/plans/2026-07-30-tier2-dormant-gaps.md
Worktree: c:\Users\Perry\Desktop\sts2-rl-tier2 (branch tier2-gaps)
Protocol: NO COMMITS anywhere — controller runs `git add -A` after each
approved task; a task's diff = unstaged working-tree diff at review time.
Closer: <scratchpad>/closer.py (round-trip proven 848/0 on 2026-07-30).
Suite floor: 2 failed (933T floor_49 fixture) / 3347 passed / 6 xfailed.

PARALLEL MODE (Perry, 2026-07-30, during T7): implementers now run in
concurrent waves with disjoint code footprints; they no longer edit
audit/records/** or GAP-QUEUE.md (they propose close notes; controller
applies via closer.py at fold time), and the controller runs the full
suite + gates per wave instead of per task. Per-task diffs are
generated with `git diff -- <task files>`.

Task list is the plan's table (T0–T28). One line per completed task below.

## Completed

T0: complete (queue coverage reconcile — 5 unlisted power_cmd sites + 2 phantom-key mechanism anchors filed in §3G; coverage 478/0 + 626/0, cite-check 0, validate 848/0; review clean)

T1: complete (power_cmd/G5 PowerInstanceType — dispatch mirrors FindExistingInstanceForStacking; 11/13 entries closed, the_bomb+swipe left open w/ reasons; FranticEscape companion fix; suite 3359/2/6; review clean after 1 fix loop)

T2: complete (damage_pipeline/G4+step17.5 killing-blow pre-death-prevention snapshot + G6+step17.4 dealer-before-victim swap; all 4 entries faithful; suite 3363/2/6; review clean, no fix loop)

T3: complete (creature_card_cmds/N10+step104/105 auto-select shortcut + card_selection stream + rarity/id pre-sort; 3/3 faithful; NeowsFury min_select=0 + has_shortcut gate for FromChooseACardScreen purposes after review; Choices Paradox=FromSimpleGrid correction; suite 3380/2/6; 1 fix loop)

T4: complete (creature_card_cmds/step55 — STALE: transform already on combat_rng.card_selection + mid-play search premise false; closed w/ enumeration + 3 pinning tests; suite 3383/2/6; review confirmed staleness independently; record typo fixed by controller)

T5: complete (creature_card_cmds/G10+step93+step102b — step93/102b stale-closed; real fix: detached-list shuffle so modify_shuffle_order sees pre-shuffle pile membership per CardPileCmd.cs, 40-seedx2x2 pin; suite 3385/2/6; review clean)

T6: complete (guard batch — A dmg/G5 target-dead guard fixed (dealer-half stale); B cc/N4 duplicate-instance asserts on 3 add helpers; C cc/N5+step31 stale-closed on verified max(0,..) equivalence; D cc/N2 should_afflict+CanAfflict+AfterApplied w/ Ringing test correction; suite 3396/2/6; review clean)

T7: complete (creature_card_cmds/N3 — dead-owner/IsEnding drop ALREADY modelled (_refuses_combat_add); result object confirmed-unbuilt (external readers = VFX only); step70 re-classified out of the rollup; +1 pin test; review Needs-fixes -> controller narrowed the VFX overclaim in record+queue per reviewer wording; suite +1)

T12: complete (residue verify — G11/G16/G10 confirmed closed as recorded; step14 STALE, flipped faithful w/ 4 pins; step63 AfterFlush stays open+dormant; docstring false-claim fixed by controller; 11 new tests; review approved)
T23: complete (card/_unplayable_cost — 29 cards -> -1 + energy_cost short-circuit; readers/spend/obs audit verified by reviewer; selectors.py to_draw_top finding filed in Named-work; 15 new tests; review approved; controller applied 29 record closes + queue annotation)

T22: complete (monster_state_machine G8+G7+G2 — rebind guard, overload-1 sentinel, C#-exact fall-through loop (also kills the Flyconid all-zero hazard), unreachable_states machinery + Inklet premise correction; 14 new tests; review approved; controller applied 4 closes + 3 queue annotations)

T8: complete (cc/G8 residue: Add/Draw/reshuffle sites wired [step81/89/96 closed], step61 closed, step70+G8 narrowed, step69 routed to T20; aeonglass moved onto real on_card_generated_for_combat + Entropy-Wither bug fixed; HookSystem per-hook listener-presence cache -> hot loop 50-63% FASTER than pre-task baseline; census 46->47/41->42; 41 new tests; review approved; controller applied 5 closes + 2 narrows + 4 queue edits + probe-defect filing)

SWEEP 2 (wave-1 boundary, 2026-07-30): suite 2 failed (933T env floor) / 3469 passed / 6 xfailed; validate 848/0; rehash re-pinned 548; audit_status 0 stale; counts 559 entries / 461 mechanisms / 5 live; cite-check 0; coverage 0/0; power_census 0. All folded. Wave 2 dispatched: T9, T10, T24, T28 (T13 moved to wave 3 to avoid monsters/base.py + powers.py overlap with T28).

T9: complete (cc/G12+step34 gold hooks — STALE: fix + record closes predate campaign, only queue prose had drifted; verified line-by-line vs PlayerCmd.cs/DragonFruit.cs by implementer AND reviewer; +8 pin tests; queue annotated by controller; review approved)

T28: complete (monster families — Intent.none()+MoveType.NONE, status_count at 3 sites, retained-corpse scans on is_removed_from_combat, knowledge-demon applier fixed (source half narrowed to power_cmd ownership), Dampen caster set; 15 new tests; review approved; controller applied 9 closes + 2 narrows + 5 queue annotations + Vantom 4th-site filing)

T24: complete (card/_printed_vars 23/23 — base vars wired incl. 3 live computed overrides + feel_no_pain wrong-value fix; behavior byte-identical; obs values move for 20 cards (checkpoint note in record+queue); 48 new tests; review approved; controller applied 23 closes + queue annotation)

T10: complete (cc/G11+step49 PREMISE REVERSED — FlushPlayerHand fires no AfterCardDiscarded, sim flush dispatch removed; G9+step84 should_draw hoisted + after_preventing_draw added, flip-divergence pinned 5/1 vs 1/2; legacy test_end_turn_hook_sequence updated w/ citations; 11 new tests; review approved after 1 fix loop; controller applied 4 closes + 2 queue annotations + combat.py turn-end-discard filing)

SWEEP 3 (wave-2 boundary, 2026-07-31): suite 2 failed (933T env floor) / 3551 passed / 6 xfailed; validate 848/0; rehash re-pinned 518; audit_status 0 stale; counts 522 entries / 454 mechanisms / 5 live; cite-check 0; coverage 0/0; power_census 0. Pytest collection warning from T28's TestSubject import fixed by controller (SubjectMonster alias). All folded. Wave 3 dispatched: T13, T25, T27.

T25: complete (power/_stack_type_single 16/16 — 15 on_stack no-ops deleted; all 16 C# StackType+InstanceType pairs re-verified by reviewer; dampen's StackType is None not Single (queue list wrong), hex genuinely reads Amount (real divergence closed, still dormant), illusion correct as-is; 39 new tests; review approved; controller applied 16 closes + queue annotation)

T27: complete (card/_is_dead_early_return — blood_wall/brand/hemokinesis returns DELETED (downstream commands self-gate exactly as C# does; guard provably redundant); bloodletting/offering kept, dependency CORRECTED from _death_prevention_branch to EnergyCmd.gain's missing IsEnding bail (= relic/lantern/g1); breakthrough filed as uncounted 6th site; 11 new tests; review approved; controller applied 3 closes + 2 narrows + queue annotation)

T13: complete (turn_structure/step8 AmountOnTurnStart snapshot + both readers incl. HelloWorld's snapshot-as-COUNT; step32/step67 SpawnedThisTurn — DORMANCY OVERTURNED, spawn-during-AfterSideTurnStart is reachable and CRASHES without the guard; 11 new tests; review Needs-fixes on record TEXT only -> controller wrote the corrected step-31 attribution itself; 3 closes + 2 queue annotations)

SWEEP 4 (wave-3 boundary, 2026-07-31): suite 2 failed (933T env floor) / 3612 passed / 6 xfailed; counts 500 entries / 451 mechanisms / 5 live. All folded. T11 dispatched solo against this base.

NOTE (2026-07-31, T11 review): `hook_dispatch/step37`'s RECORD PREMISE IS FALSE. C#'s
`flag = flag || item.ShouldX(...)` DOES short-circuit (verified by language spec, a compiled
reproduction, and Hook.cs:1451-1452 where the devs hoisted a call onto its own line to avoid
exactly that skip), so the sim's `any(...)` was already faithful. T11's 'fix' inverted it and
is being reverted; the entry closes as faithful-on-false-premise, not as a gap fixed.

T11: complete (6 dispatchers/orderings + 1 false-premise removal — A before_block_gained, B before_card_auto_played, C after_modifying_hand_draw (w/ C#-shape dedup after review), D before_flush, E energy-hook reorder, G turn-end-discard dispatch REMOVED; **F REVERTED: hook_dispatch/step37's premise was FALSE — C# short-circuits, the sim was already faithful**; 12 new tests; suite 3624/2/6; review approved after 1 fix loop; controller applied 6 closes + 6 queue annotations + Named-work update)

T26: complete (step8c — record was STALE+self-contradictory, hook/wiring/gate-exclusion already shipped, only SurprisePower's override missing (added, provably dormant); _after_damage_given_substitution — hp_lost>0 dropped from on_damage_dealt + was_fully_blocked mirroring CreatureCmd.cs, both powers moved onto the dealer-side hook, Imbalanced's two non-C# guards deleted (inert: BowlbugRock never self-hits); 15 new tests; suite 3639/2/6; review approved; controller applied 4 closes + imbalanced guard-prose revision + 2 queue annotations. Implementer's git-stash slip into the index was verified harmless by the controller (no unmerged entries, no conflict markers, staged blobs compile, unstaged delta = exactly this task's files).

T17: complete (power_cmd/G1 — already fixed, only sibling step13 prose was stale; power_cmd/G2+step10 — **the sim's docstring had the C# BACKWARDS**: UnsettlingLamp.cs has no amount<=0 bail, the sim's own bail was the divergence; deleted + sign-aware condition; duration ticks proven structurally unreachable from the Lamp; 933T Mecha Knight green; 14 new tests; suite 3653/2/6; review approved; controller applied 2 closes + 2 queue annotations + 3 citation fixes (Resonance steals Strength not Dexterity; SharedFate.cs:39 is a third trigger card)

NOTE (2026-07-31, T19 review): do NOT close `creature_card_cmds` step 25 (`SetMaxHp`,
currently `deliberate-divergence` with an empty issue field) as fully faithful — the
MaxHp<=0 unconditional-kill short-circuit was missing and is being fixed; re-judge after.
Also flagged for a later round: step 19's closure claims `is_over` == C#'s `IsEnding`,
but the sim's `is_over` (phase == COMBAT_OVER) and `is_ending` are genuinely distinct.

T19: complete (creature/card HP+block verbs, all 5 mechanisms REAL fixes, none stale). heal fires on the RAW amount incl. at full HP; lose_max_hp now computes unfloored -> full damage pipeline -> floors last, so a 10/10 losing 30 max HP DIES; new BlockCmd.lose_block (BurrowedPower migrated, Hand Drill now sees AfterBlockBroken); new CreatureCmd.set_current_hp; new set_max_and_current_hp (Decimillipede x2 + ToughEgg migrated). Reviewer caught a real omission -- set_max_hp's MaxHp<=0 kill must SHORT-CIRCUIT ShouldDie (CreatureCmd.cs:844-846 is `force || MaxHp<=0 || ShouldDie`); the fix agent landed the code but was cut off before the pin, so the CONTROLLER wrote TestMaxHpZeroKillBypassesShouldDie (a vetoing listener is never consulted and never spends its charge; an ordinary lethal hit still consults it). Record defect found: step23's cited ToricToughnessPower.block site is a FALSE POSITIVE (the power's own stored value, not a creature's). Suite 3680/2/6. Controller applied 9+5=14 closes (incl. step25, whose whole `deliberate-divergence` rationale was "there is no standalone set_max_hp verb" -- there now is) + 5 queue annotations. Queue 488->475 entries, 441->435 mechanisms.

SWEEP 5 (2026-07-31, post-T19): validate 848/0 invalid; cite-check 343 citations / 125 files / 0 problems; suite 2 failed (933T env) / 3680 passed / 6 xfailed.

T30: complete (card-GENERATION pool family, wave 5 lane B). Mechanism A -- cards/pool.py's FilterForCombat port was missing its Event-rarity clause; the record's 'three rarities' claim was verified CORRECT against CardFactory.cs:159-162 and the real bug source was pool.py's OWN docstring claiming two. Dormancy-preserving (both pools re-enumerated unchanged). Mechanism B -- 6 cards had TWO mismatched flags each (is_playable=False and can_be_generated_by_modifiers=False both wrong, can_be_generated_in_combat=False missing). **A DORMANCY VERDICT WAS OVERTURNED**: the recorded dormancy checked only pool_card_ids and curse_pool_ids, but transform_options_in_combat's STATUS branch (ported Entropy) is a third consumer that genuinely leaked all four bad cards pre-fix, incl. frantic_escape which The Insatiable really puts in piles -- reproduced by execution by BOTH the implementer and the reviewer (who monkeypatched the old flags rather than mutating source). Reviewer approved both verdicts. 36 new tests. Controller applied 20 closes + 1 bonus (relic/crossbow/g3, same root, found by the controller) + 2 queue annotations.

T31: complete (rewards dispatch + relic stubs, wave 5 lane C). Mostly a VERIFICATION task: 2 of 3 mechanism-A entries and 1 of 4 B entries were already fixed by pre-existing STAGED work (confirmed real via `git show HEAD:sts2_rl/run.py`, not asserted). royal_stamp premise-corrected from 'stub' to fully implemented + already pinned. bing_bong / massive_scroll / punch_dagger deliberately LEFT OPEN as genuine-but-dormant rather than closed. **SPUN OFF A NEW LIVE GAP, found by unit work and confirmed by the reviewer**: events/brain_leech.py + events/trial.py hand CombatRewards to driver.py._run_event's pending_rewards channel with no apply_reward_modifiers dispatch, so Driftwood's reroll is unavailable there though both events and Driftwood are ported -- dispatched as T32. Reviewer approved both verdicts. Controller applied 4 closes + 2 queue annotations.

NOTE (2026-07-31): T31's implementer used a 'temporarily revert the fix, see RED, restore' technique while another agent was live in the same worktree. Controller verified the tree (footprint exactly as declared, no conflict markers, reverts restored). All later dispatches now forbid it explicitly -- get RED by writing the test BEFORE the fix.

SWEEP 6 (2026-07-31, post-T30/T31): validate 848/0 invalid; cite-check 348 citations / 127 files / 0 problems. Queue 475->451 entries, 435->423 mechanisms.

T20: complete (exhaust/escape/RemoveFromCombat/EnergyCmd, wave 5 lane A). Four items, all real. A: exhaust now scans EVERY pile incl. exhaust. B: escape strips powers silently via Power._expire (no on_removed), mirroring RemoveAllPowersInternalExcept's deliberate contrast with death; on_creature_escaped KEPT after the reviewer traced the whole C# chain and found zero Hook.AfterX; a compensating SwipePower.hand_off_stolen_origins was needed because run.py's finish_combat reconciliation is sim-only architecture (C# steals from the deck immediately, SwipePower.cs:75). C: step69 wired = the 4th of G8's four dispatch sites. D: EnergyCmd.gain got its is_ending bail (PlayerCmd.cs:29-43), unblocking bloodletting+offering. **REVIEWER CAUGHT A REAL NEW DIVERGENCE THE FIX INTRODUCED**: item A's first pass raised ValueError on a re-exhaust, reasoning from CardPile.AddInternal's throw -- but CardPileCmd.Add removes (:494-496) BEFORE it adds (:510), so with oldPile==targetPile==Exhaust the contains-guard tests an emptied slot and never fires; re-exhausting is a legal no-throw reposition. THE CONTROLLER'S OWN BRIEF had suggested the raising behavior -- the C# overruled it. Controller fixed it directly (scan includes exhaust_pile, assert dropped) and rewrote the pin to assert the reposition-to-bottom. Controller applied 7 closes + 2 NARROWINGS (G8 keeps one unwired site, the manual play, pending N9/T21; relic/lantern g1 keeps its AfterModifyingEnergyGain clause) + 4 queue annotations.

SWEEP 7 (2026-07-31, post-T20): validate 848/0 invalid; cite-check 358 citations / 128 files / 0 problems. Queue 451->444 entries, 423->419 mechanisms. NOTE: full suite not yet re-run post-T20-fix -- T32 was mid-flight in driver.py/events. Run it before the round banner.

T32: complete (mid-event reward-modifier dispatch -- a LIVE gap this round FOUND rather than inherited, spun off by T31 and confirmed by its reviewer). Enumerated all 11 sim reward-offer sites: 2 missing the dispatch and FIXED (brain_leech._rip, trial._nondescript_guilty -- Driftwood's reroll now reaches both), 8 immune, 1 MORE live gap found and deliberately left open (events/base.py::Event.offer_card_reward via the_future_of_potions -- a take-or-skip protocol with no reroll surface, so it needs new capability, not a call). Fix is PER-SITE, not central: _offer_rewards's 3 other callers already dispatch at construction time, so a central call would double-dispatch and duplicate gold/relics (reviewer verified). That leaves the sim structurally unlike C#'s single choke point -- recorded as the real follow-up. Reviewer approved both verdicts but caught a FACTUAL ERROR baked into a permanent test comment: 'Driftwood is the only room-ungated hook of 8' is FALSE -- Midas.TryModifyRewardsLate (Midas.cs:12-29) takes a room param and never reads it. Controller verified against the C# and corrected the comment (Midas is irrelevant there for a different reason: those screens carry no GoldReward), plus two Minor prose fixes (Trial.cs:185 is ONE OfferCustom with a 2-item list, not two calls; BrainLeech batches RewardCount groups where C# loops -- dormant at RewardCount=1). Controller added 2 new FAITHFUL record entries (found+fixed) and 1 new LIVE GAP entry (event/the_future_of_potions/g15) + 1 queue annotation.

NEW OPEN WORK found this round, not yet owned:
- event/the_future_of_potions/g15 -- Event.offer_card_reward has no reroll surface (LIVE).
- run.reward_offer_selector is NEVER wired by driver.py (set only in test files) so take-or-skip screens AUTO-ACCEPT in real play. Pre-existing, LARGER than the reroll flag, needs its own task.
- Consolidating the sim's several construction-time reward dispatches onto one choke point (C# has exactly one: RewardsSet.GenerateWithoutOffering).

SWEEP 8 (2026-07-31, post-T32): validate 848/0 invalid; cite-check 362 citations / 129 files / 0 problems. Queue 444->445 entries (UP one: a new live gap recorded), 419->420 mechanisms. Full suite last seen 2 failed (933T env) / 3738 passed / 6 xfailed, which included the controller's exhaust correction.

T18: complete after a FIX PASS (power_cmd/G3 + G4 -> damage_pipeline/G2 -- the campaign's headline task). C#'s three ordered phases are now three real dispatches: given-additive then given-multiplicative (Hook.cs:1888-1912's sum-THEN-product, which a naive fold gets wrong) under a real applier/ContainsCreature gate, then the received chain unconditionally; both AfterModifyingPowerAmount* companion events exist with a modifiers out-list carrying only listeners that actually changed the value; Artifact and RuinedHelmet are REAL LISTENERS instead of hand-inlined. RESULT: **zero live entries across all six seam records** -- the engine tier has no live gap. damage_pipeline/G2 dropped live->dormant but stays an OPEN gap (7 of its 9 variants still uncovered). **THE REVIEWER CAUGHT A REAL DEFECT IN THE HEADLINE MECHANISM**: pass 1 fired both companions BEFORE the power was registered/stacked, where C# runs ApplyInternal (PowerCmd.cs:135) and SetAmount (:237) FIRST (:148-152, :238-242). The CONTROLLER found a third facet nobody had flagged: C#'s Apply wraps its ENTIRE tail incl. both companions inside `if (target.CanReceivePowers)` (:133-158), so a target failing that re-test must get NEITHER companion -- the sim fired them before its re-test. The controller also CLEARED one thing the reviewer had passed over: the sim's empty-list skip is equivalent to C#'s unconditional call, because both companion hooks iterate listeners and filter on modifiers.Contains(modifier) (Hook.cs:796-824). Fix pass handled all three plus the load-bearing trap: ApplyInternal's `if (!(amount == 0m))` is INTERNAL to it, so an Artifact-zeroed debuff attaches nothing but STILL fires both companions -- which is how Artifact spends its charge on a debuff it blocks. NOTE: full-suite green proved nothing here; both defects were invisible to current content and only visible against the C#. PERF: end_turn got 14.76% FASTER -- profiling found combat_is_over ran a live `import` STATEMENT per call (pre-existing, circular-import workaround), now cached in _PHASE_CLS. PowerCmd.apply itself is 28-42% slower (three _each() calls where there was one); reviewer notes 147 files call it, so watch it. Controller applied 6 closes + damage_pipeline/G2 live->dormant + 4 re-scopes/citation fixes (step21/step31 machinery-now-exists; N4/step4 cited step6 as dormant when it is now closed) + 3 queue annotations.

SWEEP 9 (2026-07-31, post-T18): validate 848/0 invalid; cite-check 367 citations / 129 files / 0 problems. Queue 445->439 entries, 420->416 mechanisms. LIVE: 6->5 mechanisms, ALL content-tier (power/skittish/AfterAttack; event/crystal_sphere x2 and event/war_historian_repy/g2, all deferred whole-event port stubs; event/the_future_of_potions/g15, NEW this round). SEAM LIVE ENTRIES: 0.

## Minor findings carried to final review

- T0: the two new §3G coverage-anchor rows are wordier than the table's terse norm (GAP-QUEUE.md ~2092, ~2099)
- T1: orphan-instance surfaces (PowerCmd.remove, _strip_powers_after_death) documented-unreachable, left for future work; full_env.py sees newest-instance amount for stacked Instanced powers (was a wrong sum)
- T3: card.id vs ModelId.Entry tie-break fidelity not exhaustively cross-checked (reviewer ⚠); shortcut path draw-pile ordering pinned by test
- T5: held-card branch keeps mid-play card physically in discard (N9 territory, disclosed); bottled-potential test doesn't race draw-vs-discard Perfect Fit copies
- T6: N4 closure text omits shuffle-re-add/transform pile-mutation sites from the old enumeration (different failure shape, unguarded); afflict's combatState==null non-mirror lives only in closure prose, no gap id
- T7: caller-enumeration phrasing slightly overstates per-file inspection (reviewer-verified no counter-example); step73 + HasBeenRemovedFromState + detached-card deferred with reasons
- T12: step71's N2 waiver may under-scope Player.AfterCombatEnd teardown (pre-existing, future round)
- T23: CardEnergyCost.cs true short-circuit lines are 101-104 (records carry 100-103 drift); selectors.py clamp is a 1-line follow-up
- T22: state_machine_probes.py zero_weight probe greps the OLD message text (stale, out of footprint); T22 reviewer transiently mutated state_machine.py mid-review (restored, verified byte-identical, disclosed)
- T8: step69 (thieving_hopper RemoveFromCombat dispatch) assigned to T20; manual-play site waits on N9 (T21); monster_probes_b06 grep blind spot filed in outstanding defects
- T9: hook_dispatch/N5 queue entry (~line 1348) carries a stale G12 cross-reference — T16's implementer to fix with N5
- T28: mechanism-D TDD covers Disintegration/MindRot only (shared code path with Sloth/WasteAway); Vantom status_count=3 one-liner pending an owner
- T24: Normality's live magic_number override does a linear history scan on the obs hot path (pre-existing cost pattern, flag if Normality-heavy decks train slow); report cited base.py:65-69 for text actually at :143-146
- T10: fiddle.py inline comment misidentifies which C# bail is missing (player!=owner, not the Side check) — hygiene, inert in single-player sim
- T25: hex's dormancy is content-dependent (a 2nd Hex applier makes it live); census no-op heuristic mirrors the audit tool's own fragile 'ends with pass' proxy
- T27: two more same-idiom sites (conflagration.py, tear_asunder.py) are the correct multi-hit loop-break idiom, not this mechanism; hemokinesis's 2026-07-26 record misquotes which AttackCommand line it cited
- T13: step31's own 'faithful' rationale is overbroad (true only for spawns after ExecuteEnemyTurn's ToList) — noted in its sibling closes, verdict stands; amount_on_turn_start uses getattr not a Power.__init__ field (normalize when powers.py is free)
- T11: after_modifying_hand_draw's dispatcher doesn't re-check _live (unreachable at its sole call site; matches after_preventing_draw's shape); before_flush note cites CombatManager where the NetId gate is in Hook.cs:534-538
- T17: cmds.py's PowerCmd.modify_amount docstring now misdescribes its own blocker (fix when next touched); G4 + damage_pipeline/G2's variants remain blocked on dispatch architecture (modify_power_amount has no modifiers out-list; Artifact hard-coded outside the listener system = power_cmd/G3)

# Round 13 (2026-08-01) — dormant-gap campaign continued

Plan: docs/superpowers/prompts/2026-08-01-tier2-round13.md
Worktree: c:\Users\Perry\Desktop\sts2-rl-tier2, branch tier2-round13 off main c9bc3374.
Protocol: identical to round 12 — NO git commit/push/add/stash/checkout/reset/restore
by any implementer; controller stages (`git add -A`) after each approved task;
implementers NEVER touch audit/** (they propose closes in reports, controller
applies via closer.py); no "revert-to-see-RED" — write the test before the fix;
reviewers get diffs scoped to the task's declared paths; every review dispatch
says "do not defer to the brief; the C# decides" and names the claim to re-derive.
Closer: <scratchpad>/closer.py (recovered from round 12, round-trip re-proven
848/0 on 2026-08-01; stamp for this round: "Closed 2026-08-01 (tier-2 round 13):").
Baseline at branch point: counts 372 entries / 349 mechanisms / 7 live, 0 seam
live; suite 2 failed (933T floor_49 env fixture — NEVER "fix") / 3766 passed / 6 xfailed.
Unlabelled: 56 entries = 4 triage manifests (.superpowers/sdd/unlabelled-r13/,
power-1 12 + power-2 11 + relic-1 14 + relic-2 14) + 5 carved out to dedicated
lanes (skittish/suck/painful_stabs -> R9, smoggy -> R5, kifuda -> R12).

Task table (waves have disjoint FILE footprints; engine lane paired w/ content lanes):
- R1 (W1, engine lane: hooks.py + combat.py + player.py): hook_dispatch registry
  family G1+G7+G5+G6 then N5 — "lands together or not at all"; perf-gate end_turn
  before/after (round 12 required the _has_listener_for presence cache).
- R2 (W1: events/base.py + events/the_future_of_potions.py): g15 reroll surface.
- R3 (W1: powers.py + power content): unlabelled power-1 manifest.
- R4 (W1: relics/*): unlabelled relic-1 manifest.
- R5 (W2, engine lane: combat.py + player.py + cmds.py + cards): Play-pile family
  N9+step82, step99, step51, step56, G8's last site (CardPileCmd.cs:683) +
  power/smoggy pile-limbo entry.
- R6 (W2: driver.py + run.py): wire run.reward_offer_selector (largest known live
  divergence — take-or-skip screens auto-accept in real play).
- R7 (W2: powers.py + power content): unlabelled power-2 manifest.
- R8 (W2: relics/*): unlabelled relic-2 manifest.
- R9 (W3: cmds.py + powers.py): AttackCommand-level AfterAttack hook +
  skittish/suck/painful_stabs.
- R10 (W3: driver.py + rewards.py + events): consolidate reward-modifier dispatch
  onto one choke point (RewardsSet.cs:136); NAIVE CENTRAL CALL DOUBLE-FIRES —
  _offer_rewards callers already dispatch at construction.
- R11 (W3: cards/breakthrough.py, monsters/vantom.py, selectors.py,
  audit/tools/state_machine_probes.py): ledger backlog minis + step19
  is_over-vs-IsEnding re-derivation (record fix is controller's).
- R12 (W3 or W4: run.py select_cards + relics/kifuda.py): _auto_keep/kifuda
  partial-confirm (CardSelectorPrefs 0..3, Cancelable=false).
Wave 4: spillover + fix loops. Footprint conflicts resolved by scout reports
before each dispatch; R10/R12 may not share run.py/driver.py in one wave.

## ROUND 13 CLOSE (2026-08-01)

**ROUND 12'S HEADLINE IS BROKEN, BY THIS ROUND'S OWN WORK.** Round 12 closed with
"0 live entries across all six seam records — the engine tier has no live gap."
There are now **4 live seam entries** -- all found by this round, all confirmed by execution, none previously recorded. The engine tier was never clean; it was UNMEASURED.

Final: **360 entries / 339 mechanisms / 17 LIVE entries / 16 live mechanisms**
(from 372 / 349 / 7 / 7). Entries -12 and mechanisms -10, while **LIVE +10 and seam live 0 -> 3** (a 4th live gap is real but MISFILED onto a seam record -- see STILL OPEN). Suite **3942 passed / 6 xfailed / 0 real failures** -- RE-VERIFIED at close in a QUIET TREE (zero unstaged/untracked, no agents live), which is the confirmation my first claim lacked (from 3766), plus the 2
known 933T floor_49 fixture failures which are an ENVIRONMENT GAP and were never
touched. closer.py round-trip 848/0. citation_check MISSING 49 — PROVEN PRE-EXISTING
by running the same tool in a throwaway worktree of the branch point.

10 of 12 planned lanes ran (R1 R2 R3 R4 R5 R6 R8 R10 R11 R12), each through
implement -> review -> fix -> re-review -> fold. **R9 (AfterAttack payload) and R7
(power-2 batch) were NEVER STARTED** — blocked all round on powers.py/cmds.py, held
by the Play-pile lane. Their briefs are written and current.

WHAT THE ROUND IS ACTUALLY WORTH, in the campaign's own terms:
1. **Four fixes introduced new divergences and the full suite passed over every one**
   — the round-12 lesson, four more times, all four found by reading the C#.
2. **Three tests were DEFENDING bugs**, one of them the sole reason the suite stayed
   green over a real fix, one asserting a divergence was intended.
3. **Dormancy failed on ENUMERATIONS, not verdicts**: a 4-site census that was 10; a
   "backstop" that was DEAD CODE; a guard closed on a census that never listed the
   production driver; and a reviewer that withdrew its own rating after admitting it
   had generalised from two probes instead of enumerating nine listeners —
   **"commands re-gate; counters do not."**
4. **Four wrong closures were REOPENED** and one mechanism re-scoped 4 -> 18 sites.
5. **Cross-record staleness is systemic**, not incidental — two lanes rediscovered
   one root independently.
6. **A tool trap bit the CONTROLLER twice** (closer.py's label-vs-positional lookup);
   closer.py now ships find_labelled() and the rule is: never fold a guard without it.

FOR THE USER, on RL training: the Play pile changes the observation ONLY at a
decision point suspended inside OnPlay — the resolving card counts in `play` rather
than `discard`, moving exactly two slots by one card — and **never changes a
trajectory**. Run env 30/30 observation-neutral across the fix pass. The two seeds
that DO change trajectory and reward are 100% the events lane's fidelity fix, proven
with an isolation tree containing none of the Play-pile work. Terminal observations
of 3 of 5 combats differ (a `terminated=True` obs PPO/GAE never bootstraps from).
**No obs schema change — existing checkpoints still load.**

RETRACTED -- MY `OPEN REGRESSION` CLAIM WAS FALSE, AND THE MEASUREMENT WAS MINE.
I reported 3 order-dependent hefty_tablet failures as a round-13 cross-lane regression.
The whole-branch review REFUTED it: two independent full-suite runs in real collection
order both give **3942 passed / 6 xfailed / 2 failed** (only the known fixture gap). The
cause was the review's OWN test-quality mutation sweep, which applied 53 source mutations
in this shared worktree during my run window -- one of them to relics/hefty_tablet.py. The
"order dependence" was illusory: varying test selection varies RUN DURATION, so a
4.5-minute full-suite run reliably overlaps a mutation window while 10-second targeted runs
fall between them. All three of my suspects are cleared. Lesson for me, not for the code:
**I diagnosed a concurrency artifact as a product defect because I trusted a single
full-suite run taken while other agents were live in the tree.** Do not treat any suite
result from a shared worktree as evidence without confirming no agent is mutating it.
THE NEAR-MISS IS THE REAL FINDING: my `git add -A` briefly STAGED a deliberately-broken
relic, and this round's rule is stage-never-commit -- so the index is exactly what a human
would have committed. Verified clean at close (hefty_tablet.py staged == HEAD, zero
mutation markers, zero unstaged production changes). Also surfaced, genuinely latent:
`frozen_ids` (vocab.py:117-119) WRITES vocab.json to disk on import when a new id
appears.

R5: **FOLDED** (this was missing -- the reviewer caught that the largest lane had no
FOLDED line while its record text still asserted "the sim still has no Play pile" and "the
Sly keyword is UNPORTED" against a tree where player.play_pile and is_sly_this_turn both
exist).

FIXED AT CLOSE, from the whole-branch review:
- **3 schema-invalid records** (audit_status exited 2 where HEAD exits 0): my three
  reopenings put their reasoning in `rationale` and left `issue` empty, which a `gap`
  verdict does not allow. Moved into `issue`; **audit_status now exits 0**.
- **GAP-QUEUE coverage had REGRESSED from 0/0 at HEAD to 12 mechanisms / 13 entries
  missing** -- and the missing set was almost exactly this round's own work: all the new
  live seam entries, all three reopenings, and the new turn_structure gap. The queue's own
  header calls it "generated, not transcribed", so an unnamed entry is INVISIBLE to the
  next round. Added a "Round 13's own new entries -- the coverage list" section naming all
  13. **Coverage back to 0/0.** CRLF re-normalised after the edit (the documented trap --
  my first write broke it).

STILL OPEN at close, from the whole-branch review (NOT fixed):
- `creature_card_cmds/F-R13d` (the NoUpgradeRoll class-wide gap) is a real live gap but
  MISFILED onto a seam record that cites none of its C#. **The flagship "seam live" number
  should therefore be 3, not 4.** Needs rehoming onto a content record.
- The remaining items in FINAL-REVIEW.md's fix list (none touch production code).

WHAT THE WHOLE-BRANCH REVIEW CONFIRMED: both original live seam gaps reproduced by
execution (and it found a BETTER witness for one than the record's own -- Joss Paper's
counter ticking in the ending window, where the record's ForgottenSoul witness had been
silently invalidated by a sibling lane); the RL claim holds EXACTLY (obs schema
byte-identical, the "two slots" claim is literally two floats); engine-seam tests are
strong under mutation (52/54 and 22/31 killed).
NOT COMMITTED. Everything is staged only, per the standing rule.

## Round 13 completed

R10: complete (reward-modifier dispatch consolidated onto C#'s REAL shape — one choke
point reached from TWO entry points: CombatRewards.generated mirrors
RewardsSet._isGenerated, offer-time backstop in driver._offer_rewards +
RunState.offer_rewards; BRIEF'S CENTRAL CITATION OVERRULED: RewardsCmd.OfferForRoomEnd
is dead code (zero call sites), real path = TreasureRoom.DoExtraRewardsIfNeeded ->
GenerateForRoomEnd; TREASURE-ROOM DISPATCH HOLE found+FIXED (dormant — all 8 ported
implementers enumerated; behavior-identity proven by execution incl. identical
shared-RNG state); 15 new tests RED-first; review approved after a text-only fix pass
(the docstring's justification premise was false — the OfferCustom majority dispatches
ONLY at offer time, a STRONGER argument for the landed shape; reviewer owned one of the
three final nits itself, controller applied all three); controller applied 2 event-record
amendments + wongos N7 amendment + new seam/hook_dispatch guard G-R10 + 2 queue
annotations. Also: test_rng_tripwire's line-number watch item is STALE (allowlist is
function-name-keyed now).

R3: complete (power-1 triage, 12 entries: 5 FIXED [dark_embrace x2, rebound x2,
retain_hand] + 4 stale + 2 dormant-enumerated + the_bomb/InstanceType confirmed-LIVE
blocked on cmds.py+full_env.py [dedicated task candidate: 11 InstanceType units];
corruption + nostalgia-g8's Corruption half BLOCKED-ON-FOOTPRINT with exact fix shape
documented for the hooks.py/combat.py owner. REVIEWER OVERTURNED the report's
Corruption-beats-Nostalgia-divergence framing — C# is order-independent too
(CorruptionPower.cs has no pileType guard; Nostalgia+Rebound bail on non-Discard), close
text corrected BEFORE it misdirected the later engine lane. REVIEW CAUGHT A REAL
INTRODUCED DEFECT: the first Rebound fix spent a stack on Exhaust-seed cards where C#
abstains (live via Trash Heap Rebound + any of 36 exhausting cards, invisible to every
test) — fix pass added the exhaust gate, re-review re-derived it arm-for-arm vs
CardModel.cs:2070-2083. F1: pre-existing guard "Rebound redirects its own card" was
mis-verdicted faithful (C# decides the pile BEFORE OnPlay applies the power);
encoding test split/corrected. F2: power/_death_prevention_branch queue summary may be
wholly stale (all 3 named units dropped their ShouldDie overrides) — re-check could
close the mechanism. F3: power_cmd/G5 summary overstates the_bomb closure. 11+2 tests;
re-review sweep 817/0.)

R4: complete (relic-1 triage, 14 entries, ZERO production edits needed: 3 stale-closed
[lizard_tail x2 — G3 closed round 8, current code a pure predicate; pen_nib — G3's
premise was BACKWARDS, Hook.AfterCardPlayed deliberately bypasses
IterateCombatHookListeners and IsInProgress stays true on the lethal iteration] + 2
narrowed with citation-error findings [fur_coat: the recorded divergence NEVER EXISTED —
the record conflated CombatManager.AfterCreatureAdded with the hook, sole real dispatch
site CreatureCmd.cs:81; unsettling_lamp: G2 closed by concurrent round-13 work, G3+G4
stay open] + 9 re-confirmed dormant with fresh execution. Review NEEDS-FIXES on
EVIDENCE quality: 3 defective tests repaired (one never called the function it pinned
and asserted a value the test itself assigned), unsettling_lamp G4 enumeration rewritten
4->10 sites incl. havoc's nested auto-play + HellraiserPower (verdict survives via
MadScienceCard mutually-exclusive branches). Re-review verified the repairs BY MUTATION
(7 assertion inversions, all killed). NEW FINDING OUTRANKING THE TASK: combat.py's play
loop is missing C#'s Owner.Creature.IsDead early return (CardModel.cs:1932/1940/1950) —
a self-killing play dispatches after_card_played where C# returns first; routed into
R5's brief (owns that region in wave 2). 14 tests.)

R1: **COMPLETE, APPROVED, FOLDED** (2026-08-01). Final verdicts: G1 FIXED, G2-slot FIXED,
G5 FIXED, G6 FIXED (machinery; dormant on content), **G7 NARROWED** with three residues
named. **THE RE-REVIEW OVERTURNED THE REVIEWER'S OWN REMEDY.** On the dying-monster
defect the reviewer had proposed reordering the `retained_after_death` assignment; the
lane showed by execution that this is INERT (the flag defaults False, so
`is_gone and not retained_after_death` is already True at the HP write, before
`_resolve_death` is even entered), and the reviewer confirmed it by exporting the
pre-fix-pass tree, applying ONLY its own remedy, and observing the dying monster still
received nothing. The lane's replacement diagnosis — prediction-vs-EVENT — is strictly
wider: the same window also swallows Hook.ShouldDie (CreatureCmd.cs:505) and
ShouldCreatureBeRemovedFromCombatAfterDeath (:508), which the reviewer's remedy would
not have touched. New `Monster.combat_removal_committed` has exactly three write sites
mapping 1:1 onto the only three in-fight statements reaching CombatState.RemoveCreature
(:529 under the :523/:527 gates, :601 via CreatureEscaped, MonsterModel.cs:450's
deferred completion); `CombatState._perform_move` is a complete funnel (combat.py's only
take_turn site). Eight executed cases all C#-correct. G1 upgraded NARROWED->FIXED on a
citation the review lacked: a draw takes `drawPile.Cards.FirstOrDefault()`
(CardPileCmd.cs:843), so `_derive` walks the draw pile REVERSED while storage orientation
is untouched; isolated cost -0.4% (nil).
**CONTROLLER TRAP AVOIDED:** the originally-approved §7 `Power` diff would have shipped
the same dying-owner bug into powers.py (`not owner.is_removed_from_combat` drops a power
from its OWN owner's AfterDeath, since C# nulls the back-pointer at :523-531 and strips
powers at :533-537, both AFTER the :519 dispatch). The reviewer re-ran the separating
question on scratch copies (old: [], new: [True]; C# says [True]) and REJECTED its own
earlier approval, owning the error precisely: it had checked the diff against the C# ARM
but not against the TIMING of the sim value it reads. **Controller landed the corrected
FP-6 diff**, the unchanged potions.py diff, and the new one-line run.py deck-removal
flag; 284 targeted tests green.
Controller applied: step3/step9/step44/step4/step6/step45 CLOSED, step11 numbers
corrected, guard G6 CLOSED, step12 NARROWED, step16 LEFT-OPEN and re-scoped under N5.
**hook_dispatch seam: 14 entries/8 mechanisms -> 7/4, still 0 live.** Queue 361->354
entries, 338->334 mechanisms. NOTE for future folds: hook_dispatch has NO G1/G5/G7 GUARD
entries — those are mechanism names whose sites are steps; only G4, G6 and the new
G-R10 are guards.
NEW GAP QUEUED BY R1, deliberately deferred (and the reviewer corrected HOW to file it):
`can_receive_powers` and `_combat_contains_creature` still read the eager prediction and
diverge for the whole death sequence. **Do NOT file it as "blocked on footprint"** —
both consumers live in cmds.py, which IS in the footprint; the honest reason is live
blast radius on PowerCmd.apply's gate. File it with the derived dormancy statement: all
four death-hook power-appliers target a live teammate, a fresh summon, or the player —
none a mid-death creature.

R12: **COMPLETE, APPROVED, FOLDED** (2026-08-01). Controller applied: relic/kifuda g2
CLOSED; **THREE REOPENINGS** — relic/gnarled_hammer's N2 and both potions' G1, each
faithful -> gap + LIVE. Queue 354->356 entries, 334->335 mechanisms, LIVE 9->11 entries /
10 mechanisms. **UP, and that is the honest direction.**
CONTROLLER ERROR, SECOND OCCURRENCE OF TRAP 3 IN ONE ROUND: I passed `g2` for
gnarled_hammer and hit the record's N1 (queue g2) instead of its N2 (queue g3) — the
positional-vs-label collision closer.py documents. Caught by inspecting the fold's own
output against the entry text, restored with `git checkout HEAD -- <that one record>`
(it had no other round-13 edits, verified against HEAD), and redone with
**find_labelled("g3", "N2")**, which asserts the label and would have refused the first
attempt. **Rule for future folds: never call find() for a guard entry — use
find_labelled().** The potions' G1 entries were correct on the first attempt (verified
faithful at HEAD, and their `what` text is the right mechanism).
The reviewer also conceded its OWN error to the lane: the shared-`from_discard` sibling
is Liquid Memories (potions.py:1098, LiquidMemories.cs:25 -- a one-arg exact-count
prefs), NOT Headbutt, whose sim screen is named for its DESTINATION (`to_draw_top`) not
its source pile. The reviewer re-executed it: with 2 candidates and count=1 Liquid
Memories DOES reach card_selector, so a blanket SKIPPABLE_PURPOSES add would make an
exact-one-pick screen declinable -- the structural conflict stands, under the right unit.

R12 (detail): implemented + reviewed + fix pass + re-review.
Code verified CORRECT (mutation probe: 8 of 13 new tests fail with the mechanism disabled;
the 5 survivors are the intended controls). Fix: a new `enchant_optional` purpose in
driver.SKIPPABLE_PURPOSES, chosen over threading min_select because the latter would break
dozens of hand-rolled 3-arg card_selector callables. **THE REVIEWER RULED THE CHOSEN SHAPE
LESS FAITHFUL AND ORDERED THE DESIGN DEFECT FILED AS ITS OWN MECHANISM:** C# carries TWO
INTEGERS on CardSelectorPrefs (:25-27) that every consumer derives from, while
SKIPPABLE_PURPOSES is a lossy STRING-KEYED re-encoding of ONE BOOLEAN derived from them,
living in a different file from the call site that knows the numbers — it can only express
`min in {0, count}`, it now stands at FIVE purpose forks for one C# field, and its two
halves CAN SILENTLY DISAGREE, **which they already do at three live sites**.
TWO OVERTURNS, both confirmed: (1) `relic/gnarled_hammer` shares Kifuda's C# prefs
character-for-character (GnarledHammer.cs:30-34), still force-fills 3 through a real
RunDriver, and its record guard N2 is MIS-RECORDED `faithful` on DOUBLY stale reasoning —
so `relic/_auto_keep` NARROWS, it does not close. (2) Ashwater / Gambler's Brew have the
identical live bug through the production RunDriver (reproduced end-to-end: Ashwater
exhausts the ENTIRE hand with the policy never asked).
**BUT THE REVIEWER CAUGHT THE LANE REPEATING, OVER ONE RECORD, EXACTLY THE ARCHIVED-PROSE
ERROR IT HAD CORRECTLY CAUGHT THE BRIEF MAKING**: it quoted "no production path is
selectorless" as CURRENT when that line lives inside the guard's own
`The gap it replaced read:` block. Those guards are faithful/CLOSED, not dormant, so the
right action is REOPENING a guard closed on an incomplete consumer enumeration that never
listed RunDriver — reframed accordingly in the fix pass.
Reviewer's own outranking find: a THIRD live site, `cards/neows_fury.py:67`
(NeowsFury.cs:39, MinSelect 0) passing min_select=0 under purpose `"from_discard"`, which
is not skippable AND is SHARED with an exact-count screen — making the current idiom need
a sixth fork. **The fix pass then CORRECTED THE REVIEWER: the shared-purpose sibling is
Liquid Memories (potions.py:1098), not Headbutt as the review claimed** — verified by
execution. Filed as a correction to the EXISTING card/neows_fury.json OnPlay entry (stale
since before SKIPPABLE_PURPOSES existed) rather than as a new entry. neows_fury.py was
NOT edited: another lane holds it this wave.

R2: **COMPLETE, APPROVED, FOLDED** (2026-08-01). `event/the_future_of_potions/g15`
CLOSED — the reroll surface is built (offer_card_reward deleted, the screen now goes
through the pending_rewards channel to driver._offer_card_group and C#'s single
{cards..., Skip, REROLL} surface). Verified BOTH directions by execution: pre-fix the
screen raised only EVENT + SELECT_CARDS and never REWARD_CARD, so the reroll was
STRUCTURALLY IMPOSSIBLE; post-fix it rerolls, redraws from the same filtered pool,
returns +1, and is one-shot; modifiers dispatch EXACTLY ONCE under R10's choke point.
**THE FIRST PASS INTRODUCED A REGRESSION AND THE FIX PASS FOUND A SECOND LIVE DIVERGENCE
NOBODY HAD LOOKED FOR.** Regression: setting IsCardReward alone made Dingy Rug widen the
offer with two Colorless cards (an RNG-ORDER as well as card-identity divergence) — fixed
by a real flags passthrough (create_reward_cards extra_flags + CardRewardGroup.flags),
and **dingy_rug.py was deliberately NOT patched**: the reviewer ruled it a guard-for-guard
transcription that was never wrong, the defect being that the PRODUCING side could not
express a flag the CONSUMING side already read — patching the relic would have hidden
that and left Prismatic Gem / Character Cards / Big Game Hunter to reintroduce it.
Second divergence, found by re-deriving the whole flag set from the FACTORY rather than
the one visible .WithFlags call: ForNonCombatWithUniformOdds itself ORs NoUpgradeRoll
(CardCreationOptions.cs:159-162) and CardFactory.cs:98-102 guards the entire
RollForUpgrade call INCLUDING its rng.NextFloat() (:290) — so the screen burned 3 EXTRA
Rewards draws and offered +2 cards where C# offers +1. Conformance-visible. **Invisible
at act 0, which is why the first review missed it.**
Controller applied: g15 CLOSED, the pool guard's reasoning replaced (it was "accidentally
true" — true of the C#, false of the sim), one NEW guard for the flag set, and the
reviewer's RR-7 citation corrections applied IN THE SOURCE FILES before folding
(CardFactory.cs:97-101 -> :98-102, :102/:102-105 -> :104, CardCreationOptions.cs:160-162
-> :159-162; one was a regression from a previously-correct :104).
**Queue 355->354 entries, 335->334 mechanisms, LIVE 10->9.**
THREE FINDINGS FILED-READY, none in footprint: FIND-A brain_leech/trial reroll from the
CHARACTER pool (executed: a Colorless screen becomes an Ironclad screen on reroll);
FIND-B brain_leech's modify_hooks=False stand-in (executed: Silver Crucible/Silken Tress
never fire, times_used=0) — the exact mirror of the bug fixed here, under-firing instead
of over-firing; FIND-D NoUpgradeRoll still unmodelled at ~11 other non-combat creation
sites, **with an explicit warning that a BLIND SWEEP WOULD BE WRONG** because
CardCreationFlags.cs:20-24 names Orrery (:22) and LastingCandy.cs:127 as raw-constructor
exceptions where the roll DOES apply.

R5: **IMPLEMENTED (after two session-limit deaths), review running.** The round's largest
change. `player.play_pile` is a real fifth pile (LAST in AllPiles per
PlayerCombatState.cs:70-80); `_resolve_card_play` now follows OnPlayWrapper's statement
order with the Play-GATED exit switch (CardModel.cs:1976-1991); G8's manual-play dispatch
wired (CardPileCmd.cs:683); new `CardCmd.discard_and_draw` + AutoPlayType (step51);
`pile_index_sort_key` (step56); AutoPlayFromDrawPile parks picks in Play and gained two
callers it should always have had (Cascade, Distilled Chaos). **Both HARD BLOCKERS fixed
by porting the C# LITERALLY, and doing so proved the brief wrong: Corruption is a
ModifyCardPlayResultPileTypeAndPosition implementer with NO pile test at all, and Rebound
has ONE guard, not three — INDEPENDENTLY CONFIRMING R3's reviewer's overturn of the
Corruption/Nostalgia order-dependence framing.** All eight de-hacks removed. The
ADDENDUM's IsDead early returns landed at FOUR slots with pins — **and the brief's slot
list was wrong**: the pre-loop gate is :1896 and it missed :1960. 42 new pins (33 failed
/ 9 passed BEFORE the fix -> 42 passed); 336 passed across its files + the six re-staged
legacy tests; 622 across the card/power/pile blast radius; 95 passed / 6 xfailed on
conformance replay-parity. Full suite with this work in: **3910 passed / 6 xfailed / 0
failed** (up from 3866).
THREE CONCERNS, all carried into review:
1. **G8 does NOT close fully** — the record's "four C# dispatch sites" enumeration is ONE
   SHORT: `CardCmd.Exhaust` IS `CardPileCmd.Add(card, PileType.Exhaust)` (CardCmd.cs:242),
   so EVERY exhaust dispatches AfterCardChangedPiles in C# and NONE does in the sim (~30
   call sites). That is step81's residue, not step82's. Two-line diff written but
   DELIBERATELY NOT LANDED (outside brief scope, wide blast radius, live tree) — correct
   conservatism.
2. **`power/smoggy`'s issue text is WRONG ABOUT THE SIM, not merely stale** — the
   resolving Skill WAS already in all_cards (the old code parked it in the discard), and
   the entry is filed under `AfterCardEnteredCombat` while describing `AfterCardPlayed`.
   `power/ringing`'s cross-referenced entry must be RE-DERIVED, not closed by analogy.
3. **RL OBSERVATION IS NO LONGER BYTE-IDENTICAL AT MID-PLAY DECISION POINTS** (matters to
   the user's training): measured HEAD-vs-live, combat env 5/5 identical; run env 23/30
   identical, 5 of the 7 diffs being exactly the intended discard->play membership and 2 a
   downstream shared-RNG cascade because Headbutt's / Neow's Fury's candidate list
   correctly no longer contains the resolving card. Conformance parity green; NO obs
   schema change, so existing checkpoints still load. Reviewer asked to re-derive this
   independently.
One line owed outside footprint: `relics/pen_nib.py` should read
`card not in player.play_pile`.

R2 REVIEW VERDICT (2026-08-01): **NEEDS-FIXES — THE FIX INTRODUCED A NEW DIVERGENCE.**
This is the round-12 lesson's FOURTH occurrence this round.
The reroll work itself is CONFIRMED CORRECT by execution: the reviewer reproduced HEAD
out of tree (loading `git show HEAD:` versions into a THROWAWAY PROCESS — the shared
worktree was never reverted) and showed the reroll was STRUCTURALLY IMPOSSIBLE pre-fix
(HEAD raised only EVENT + SELECT_CARDS, never REWARD_CARD), while post-fix the screen
raises REWARD_CARD, offers the reroll at n+1, redraws from the same filtered pool, hands
back a card at upgrade_level 1, and is one-shot. Regeneration matches
CardReward.cs:156-164/:322-332 (Reroll clears _cards and re-enters Populate's draw
branch, re-firing AfterGenerated), and since RerollOptions == Options for the 3-arg ctor
(:114-115) the pool-carrying subclass is the right shape. Dispatch is EXACTLY ONCE
end-to-end (state-mutating spy: 1 plain + 1 late, R10's backstop no-opping on
`generated`). No second accept gate; not built on select_cards; offer_card_reward
correctly deleted (no callers left).
**BUT THE SIDE-EFFECT FIX WENT HALF-WAY.** Setting `is_card_reward=True` was right —
C# always sets it (CardReward.cs:114-115), NoModifyHooks is absent
(TheFutureOfPotions.cs:127, CardFactory.cs:104-107), and pre-fix the sim really did skip
both relics (executed: silken_tress.is_used stayed False; Silver Crucible left cards at
+1 instead of +2). **However `NO_CARD_POOL_MODIFICATIONS` is set at NO call site in the
sim, so Dingy Rug's operative gate is that SAME `IS_CARD_REWARD` flag** (dingy_rug.py:33)
— post-fix a run holding Dingy Rug is offered two COLOURLESS cards where pre-fix it
matched the no-relic offer exactly. C# forbids it (TheFutureOfPotions.cs:127 +
DingyRug.cs:19-22). A newly-created CARD-IDENTITY and RNG-ORDER divergence, needing a
flags passthrough in create_reward_cards/CardRewardGroup — i.e. it was
BLOCKED-ON-FOOTPRINT and should have been reported, not half-shipped. **R2's proposed
record text asserting the pool guard "is unaffected" MUST NOT BE APPLIED**: that guard
(the_future_of_potions.json:186-187, currently `faithful`) is flipped INTO A GAP, and
the reviewer rules this needs TWO record entries, not zero.
Three further findings outrank the task: brain_leech/trial reroll from the CHARACTER
pool instead of Colorless (executed); brain_leech uses `modify_hooks=False` as a stand-in
for a different flag; and a second stale reference in _accept_offer's docstring. R8
cross-check: the two findings are CONSISTENT (two sides of the same IsCardReward flag)
and R8's hefty_tablet LIVE verdict is UNAFFECTED. Fix pass dispatched with rewards.py
newly granted. NOTE: the safety classifier was unavailable for this review — its claims
are being re-derived by the fix pass rather than taken on trust.

R5: interrupted a SECOND time by an API session limit, mid `_add_to_play_pile` refactor,
before writing any report. Tree verified COHERENT and the **FULL SUITE GREEN AT 3910
passed / 6 xfailed / 0 failed** with the partial Play-pile work in it (up from 3866):
player.play_pile exists (player.py:129), all_cards includes it LAST (:184),
_add_to_play_pile at combat.py:963 with call sites :837/:1004, exit legs at :1203/:1224
reading play_pile. Resumed with instructions to write the report FIRST.

R8: **COMPLETE, APPROVED, FOLDED** (2026-08-01). All 14 verdicts survived review; what
failed was the EVIDENCE layer, and repairing it found a live gap.
**A VERDICT FLIPPED DORMANT -> LIVE: `relic/hefty_tablet` G2** — discovered by rewriting
a VACUOUS test (it measured a RunState with NO relics, so it asserted nothing, and Relic
declares both methods on the base so hasattr would have been True for any relic anyway).
The real state is the one when the screen OPENS: run.add_relic appends THEN calls
after_obtained, so anything obtained earlier is co-held; Neow's Bones grants two
Neow-pool relics and large_capsule pulls two grab-bag relics in its own after_obtained.
ToxicEgg.cs:21-32 bails only on NoHookUpgrades while HeftyTablet.cs:29 sets
NoUpgradeRoll — A DIFFERENT FLAG. **The reviewer strengthened it independently:
CardCreationFlags.cs also defines NoUpgrades = 6, a combined "no upgrades at all" flag
that HeftyTablet POINTEDLY DOES NOT USE**, so hook upgrades are deliberately in scope.
Observable, executed: with Toxic Egg held the sim offers `brand` (Rare Skill) plain where
the game upgrades it. Census corrected 4 -> 7 -> **TEN** (MRO-aware, and the reviewer's
scan found zero non-relic implementers, so ten is the whole population).
**PRIORITISED HONESTLY: LIVE but RARE** — 60,000 seeds gave 220 both-drawn / 105 correct
order / 3 with an implementer co-held / 0 with a matching-type Rare offered, i.e. ~1 in
20,000 picks. Fix BLOCKED-ON-FOOTPRINT; reviewer's refinement: reuse the existing
three-pass chain rewards.create_reward_cards rather than hand-rolling.
**THE DORMANCY REASON FOR FOUR ENTRIES WAS DEAD CODE.** The claimed `DamageCmd.deal`
should_allow_hitting backstop is unreachable — dominated by `if target.is_dead: return 0`
above it; should_allow_hitting is False only from Illusion/Reattach/Adaptable, all gated
on is_reviving, which is cleared before HP is restored, so False implies is_dead.
Executed both ways: 0 damage with the hook live AND with it neutered; deleting the
is_dead guard instead lets 3 land. Dormancy survives on SET-COINCIDENCE ALONE — one leg,
not two. Note the asymmetry that is now the point: the POWER side's can_receive_powers
backstop IS load-bearing (PowerCmd.apply has no is_dead guard — Creature.cs:308-322
deliberately omits it).
NEW GAP FILED (seam/turn_structure guard G-R8): **`Relic._check_win()` has the win/loss
tie-break BACKWARDS — the FIFTH site of a class G13's close note says it eliminated at
four.** Ten relics route through it; a dead player with all enemies dead resolves as a
WON combat in the sim and a LOST RUN in the game. DORMANT on three executed closures,
the strongest being that a dead player's DeactivateHooks drops all ten relics out of the
listener walk, so no dispatch can reach it while a pending loss stands — the reviewer
watched all ten vanish from all five trigger hooks while a direct _check_win() on that
same state still misfired to player_won=True.
Controller applied: 2 closes (ruined_helmet x2 — cross-record staleness, power_cmd's own
G3/G4 closed five days after this record's audit and it was never revisited), 4 reasoning
replacements, 1 liveness promotion, 1 new gap entry. **Queue 356->355 entries, 336->335
mechanisms, LIVE 9->10.** Seam live entries: still 0 across all six.
ALSO ROOT-CAUSED HERE: the suite's AttributeError was a sibling lane's LOSSY MONKEYPATCH
RESTORE — test_r13_relic1.py put the UNWRAPPED function back where a staticmethod
descriptor belonged, corrupting DamageCmd for every test that ran after it. Controller
landed the one-line fix (save/restore the raw class-dict entry).

R11: **COMPLETE, APPROVED, FOLDED** (2026-08-01). Fix pass corrected every census the
first pass got wrong, and the reviewer re-derived each independently:
**StatusIntent = 18 C# sites (not 4), 1:1 with 18 sim constructions, 5 ported / 13
OPEN.** `_cost` = 3 consumers (upgrade inert — 0 of 29 unplayables upgradable;
to_draw_top live; choose_a_card* real but unreachable). Clamp deliberately kept SHARED,
not narrowed, and the reviewer RULED THE SENTINEL ARGUMENT SOUND: `-1` is a sentinel
(CardEnergyCost.cs:100-103 short-circuits before any modifier), not a price, and
selectors.py already grants CostsX its own sentinel rank, so normalising in the same
helper is the consistent locus. `_RAISE_PAIRS`: **6 of 12 rows stale** (not 2), a 7th
mis-bucketed AND misreading its own C# citation, all 12 sim citations stale; printed
summary corrected to "8 SYM / 1 gap / 2 closed asymmetries". Probe now separates the
RandomBranch and ConditionalBranch raises — **the old grep matched 13 ConditionalBranch
machines, a LIVE false positive** — and both pass-2 setup holes are fixed (forced hits
13->15; TwoTailedRat and Fabricator now credited instead of filed unfuzzed; 0/0
unforced). Noisebot's status_count=2 landed (it lives in monsters/glory/fabricator.py,
not the non-existent noisebot.py the brief named — reviewer ruled the edit in scope) and
**its wrong-premise pin was INVERTED**: it had asserted the missing count was intended.
is_over sweep = 56 hits; the first pass's proposed grep returned 0 on its OWN site
(`getattr(combat, "is_over", False)`).
CONTROLLER APPLIED: creature_card_cmds **steps[20] and guards[3] REOPENED faithful ->
gap** (a closure's equivalence claim proven false by execution), guards[24] NARROWED;
monster/vantom DISMEMBER guard refreshed with the true 18-site denominator;
card/breakthrough guard appended (with its own caveat that the deletion's correctness is
hostage to DamageCmd.deal's bail in another file, and that its pins would NOT catch a
regression there); monsters/base.py's false "Every StatusIntent site now sets it"
docstring corrected; a new **"Round 13 — corrections that REOPEN or WIDEN recorded
work"** section added at the top of GAP-QUEUE.md covering all four. **Queue 354->356
entries, 334->336 mechanisms — UP, on purpose.**
REVIEWER'S RE-SCOPING CALL, adopted: `monster/_intent_count_lost` should be REOPENED,
not closed. The 13 remaining sites are dormant for exactly the reason the 5 fixed ones
were (the encoder reads only the STATUS_CARD flag bit, full_env.py:571), so dormancy is
no reason to leave them, and **a 5-of-18 partial port is the worst resting state**:
five monsters telegraph a count, thirteen do not, and nothing in the tree explains the
split. The census ledger test fires the moment it changes; batch the remaining 13 as one
follow-up task rather than rediscovering them site by site.

R11 REVIEW VERDICT (2026-08-01): **NEEDS-FIXES** — all four CODE changes verified
CORRECT (the riskiest, the Breakthrough guard DELETION, was proven sound by
reconstructing the pre-edit body as a SUBCLASS and diffing 48 configurations —
multi-enemy, already-dead enemy, lethal/non-lethal, several seeds — on full state PLUS
ordered hook traces: zero differences; Breakthrough.cs:24-31 has no tail after the
attack). **ITEM 5 CONFIRMED AND STRENGTHENED with an execution witness the lane did not
have: `combat.is_over` is not a narrower or looser `IsEnding`, it is the COMPLEMENTARY
window, wrong in BOTH directions.** With all enemies dead but combat not torn down,
`CreatureCmd.heal(enemy, 7)` returns 7 in the sim where C#'s `IsEnding && !IsPlayer`
(CreatureCmd.cs:693, CombatManager.cs:180-202) REFUSES; with `phase == COMBAT_OVER` the
sim returns 0 where C# PERMITS. F3 is genuinely adjacent: Hook.cs:55 gates on
`IsOverOrEnding` while the heal gates on bare `IsEnding`, so one "swap in
is_over_or_ending" edit would OVER-GUARD the heal site. The dedicated sweep is confirmed
worth a task (49 `is_over`/`COMBAT_OVER` reads) but "sweep BEFORE fixing either" is
OVERTURNED — and the lane's proposed grep would MISS ITS OWN SITE, which is written
`getattr(combat, "is_over", False)`.
SIX reasoning/proposal defects in the fix pass, two of which are new findings:
**(1) `monster/_intent_count_lost` has 18 C# StatusIntent sites, not 4** — the queue line
"All 4 known sites now carry their count" is FALSE, and `test_monster_tier_families.py`
ACTIVELY PINS Noisebot's missing count as intended while `Noisebot.cs:45` is
`StatusIntent(2)` (a pin asserting a divergence is intended).
**(2) `_cost` has THREE consumers, not two** — the clamp measurably changes
`choose_a_card`/`choose_a_card_optional` for three non-junk QUEST unplayables: the exact
"third consumer nobody listed" failure the protocol names, found on a lane that had just
been told about it. (3) the item-3 test PASSES UNDER A DELIBERATELY WRONG FIX, so it
pins nothing. (4) the old probe grep was NOT dead — `"No valid branch"` still matches
`ConditionalBranchState`'s raise, a live FALSE-POSITIVE source; plus a
hit-misclassification hole in the probe's pass-2 setup path hides exactly the machine
the probe was extended to cover. (5) two more `_RAISE_PAIRS` rows stale beyond the two
flagged, and all 12 rows' sim line citations. (6) the false `is_over`==`IsEnding` claim
ALSO lives in guards/3 and guards/24 of the same record, unnamed by the correction
proposal. Fix pass dispatched.

R6 REVIEW VERDICT (2026-08-01): **NEEDS-FIXES, but the engine change stands as-is** —
every required fix is prose + 4 test lines. **PREMISE CORRECTION: CONFIRMED BY
EXECUTION.** The reviewer reinstated HEAD's `_accept_offer` IN MEMORY (never on disk,
per the live-tree no-revert rule) and drove both consumers through a real RunDriver:
pre-fix, `the_future_of_potions` raised ['event','select_cards'] and a decline-everything
policy left the deck at 10 vs 11 for take — so the CARD screen's decline genuinely
worked before R6 — while all 8 offer_potion sites across the 6 events raised only
['event'] and granted the potion regardless. Post-fix they ask exactly 1/1/1/3/1/2
times, matching the C# reward-set shapes (PotionCourier.cs:41-43 = one OfferCustom with
three PotionRewards; WhisperingHollow.cs:53-56 = two; none use WithSkippingDisallowed).
**F1 (steers another task, so it was corrected BEFORE that task ran):** R6's parting
advice — put the reroll surface on `select_cards` — is WRONG.
`CardRewardAlternative.Generate` (CardRewardAlternative.cs:53-74) puts **Skip AND REROLL
as options on the card-selection screen itself**, so C# has ONE screen offering
{cards..., Skip, REROLL} and the sim's existing REWARD_CARD decision already has that
shape; a second accept gate would invent a decision the game lacks. R2's brief has been
amended with this correction. **F2:** `run.reward_offer_selector` is STILL WIRED NOWHERE
in production after R6 (the fix routed potion offers through a different, already-wired
seam) and the proposed notes never said so — a future grep would re-open it.
**Evidence finding worth more than the fix: the conformance suite only walks ACT 0,
where `_accept_offer` is never reached at all — so its greenness proved NOTHING about
this change.** The reviewer re-drove all 15 recordings to act 2 (which do reach
the_future_of_potions / drowning_beacon / the_legends_were_true) to show pre/post walks
identical. Fix pass dispatched (prose + F4's four redundant .begin() calls).

R6: implemented, review running. **PREMISE CORRECTION that shrinks a recorded live
gap**: the brief (from round 12's record) claimed the unwired run.reward_offer_selector
makes ALL take-or-skip event reward screens auto-accept in real play. R6 reports
Event.offer_card_reward NEVER auto-accepted — its decline path already ran through
RunState.select_cards's pre-existing skippable-purpose machinery — so only
Event.offer_potion's event callers were genuinely broken, and wiring a second decision
for card offers would DOUBLE-ASK for one C# screen. Fix is events/base.py ONLY (delta
verified by construction: driver.py/run.py deltas vs HEAD belong to R10). 86/86 on the
footprint regression set, conformance baseline held. Under independent review because a
claim that shrinks a live gap is exactly what this campaign verifies hardest.

R8: implemented, review running (relic-2 triage, 14 entries; 19 tests; ONE production
edit, vambrace.py DOCSTRING ONLY). **Systemic finding — dormancy citations go stale
ACROSS records, not just within one**: the seam/power_cmd Task 17/18 rewrite (closed
2026-07-31) left multiple downstream relic records unrevisited, so relic/ruined_helmet's
two entries and a relic/spiked_gauntlets guard flip to closed — the SAME pattern R4 hit
independently on unsettling_lamp, i.e. two lanes rediscovered one systemic defect.
Also: bag_of_marbles/G2 cites a power_cmd/G6 gap that closed THREE ROUNDS BEFORE that
record's own audit date, and festive_popper/G3 cites a turn_structure/G13 gap that is
now closed but never covered the window the divergence actually lives in — **the report
says NO replacement gap exists**, so if the reviewer confirms it that is a NEW UNRECORDED
GAP for the controller to file.

R11: implemented, review running (4 code items + 1 report-only). FIXED: breakthrough's
redundant is_dead guard DELETED (6th _is_dead_early_return site); vantom DISMEMBER
status_count=3 (4th _intent_count_lost site); selectors.py to_draw_top cost clamped so
an unplayable card's canonical -1 TIES a 0-cost card; state_machine_probes' stale grep
repaired ("No valid branch" -> "No valid state found") — and the probe now correctly
reports 0 hits because T22 fixed the underlying reachability too, so a wrong-string
probe and a correctly-empty probe had been indistinguishable from outside.
**ITEM 5 SETTLES THE F3 OWNERSHIP QUESTION: step19's closure claim is FALSE, and it is
ADJACENT TO — NOT IDENTICAL WITH — R1's F3.** `combat.is_over` mirrors `!IsInProgress`
(true only POST-teardown) while C#'s heal guard uses `IsEnding` alone (true only DURING
the ending window, false again after teardown), verified against CombatManager.cs:180-220;
F3 is a different file (hooks.py vs cmds.py), a different mechanism (generic dispatch
gate vs hand-written command guard) and needs a DIFFERENT replacement (`is_over_or_ending`
vs `combat.is_ending`). **One fix does not close both — they need separate owners**, and
R11 recommends a dedicated is_over-vs-is_ending site sweep before fixing either.
DISCLOSED PROCESS DEVIATION: items 1+2 wrote the fix before the test (RED derivable from
quoted pre-edit source, not from a real red run) — reviewer is checking those two pins
specifically. Flagged not fixed: state_machine_probes' raise_sites() census has two stale
rows that may make guard N7's site count wrong.

R1 REVIEW VERDICT (2026-08-01): **NEEDS-FIXES**, fix pass dispatched. Perf
re-measured independently (interleaved `git archive HEAD` export vs live tree, 3 rounds
x 5 samples): plain deck +0.1% (noise), enchanted worst case **+7.3%** on global minima
(per-round medians +3.2/+7.3/+14.3%) — R1 claimed +5.0%; budget ~15%, PASS either way.
All four structural claims verified by code AND instrumentation, reproducing R1's
counters to the digit (_each 13,275 calls; _ordered() 3,075 HEAD -> 2,100 live).
Live-tree suite 3,833 passed / 6 xfailed / 0 failed; probe 176,549 calls / 0 hits.
**THE FINDING THAT OUTRANKS THE TASK (round-12 lesson, third occurrence): G5's new
Monster.hook_contains() SILENTLY REMOVES A DYING MONSTER FROM ITS OWN AfterDeath
DISPATCH.** C# computes shouldRemoveFromCombat at CreatureCmd.cs:508, dispatches
Hook.AfterDeath at :519 while Creature.CombatState is still non-null (so the MonsterModel
Contains arm at CombatState.cs:585 passes), and removes only at :525-529; the sim
assigns retained_after_death ONE LINE BEFORE hooks.on_death (cmds.py:159-162), so the
new predicate sees an already-removed monster. Proven by execution ("dying monster's own
on_death delivered: []"). 8 of the 10 C# monster AfterDeath overrides are self-death-only
**including KinPriest (KinPriest.cs:104-107) — the record's OWN named concrete trigger
for G5** — so the first content port G5 exists to unblock would land on a hook the new
machinery cannot deliver. Dormant today, not a regression, and EVERY TEST IN THE SUITE
PASSES WITH IT IN PLACE; it exists only because R1 built the predicate.
Two residues force honest re-verdicts: **G1 -> NARROWED** (the draw-pile leg walks the
sim's reversed orientation — CardPile.cs:160-167 enumerates top-first, player.py:581
stores top-last, verified by execution) and **G7 -> NARROWED** (has_been_removed_from_state
is declared but NEVER SET in production, so that leg is machinery-only). F4 confirmed
genuine, both halves proven (without the ActivateHooks mirrors Chosen Cheese's
AfterCombatEnd effect is silently lost: max_hp 80->80 instead of 80->81) — BUT a new
comment in player.py claims single-player never reaches ActivateHooks, contradicting the
fix the same lane shipped, and is the single thing most likely to get that fix deleted
later. All four items in the fix pass.

R1: implemented, review pending (hook_dispatch registry family — the round's hardest
engine task; KILLED MID-RUN by an API session limit and RESUMED from its transcript,
its working tree intact and green). Verdicts claimed: G1 FIXED (combat listener order
now DERIVED PER DISPATCH from pile membership, per CombatState.cs:410-493, so a card
that changes pile changes dispatch position), the G2 SLOT-ORDER half FIXED (potions
walked in slot order per :436-443), G5 FIXED (Monster is a real listener in C#'s slot;
BOTH glory shims — aeonglass + queen — DELETED and their handlers moved onto the
monsters), G6 FIXED (affliction machinery built; stays dormant — 0 of 7 sim affliction
classes define a hook), G7 **NARROWED not closed**: the per-item state re-check
(HasBeenRemovedFromState / IsActiveForHooks / IsMelted) is implemented for cards,
relics, afflictions, enchantments and monsters, but Power.hook_contains and
Potion.hook_contains remain BLOCKED-ON-FOOTPRINT (exact diffs in report §7 for the
controller to land). PERF (the binding contract, budget ~15%): plain 30-card deck ~0%,
enchanted worst case forcing the per-card walk **+5.0%**; all four structural
requirements met (presence gate above the derivation, _phased incremental — which also
cut _ordered() calls 3075->2100, presence cache keyed on set membership only so a pile
move cannot thrash it, per-item re-check = one attribute read, no isinstance dispatch).
22 new pins, 18 RED against a `git archive HEAD` export. Stale-listener probe: 178,595
calls / **0 hits** (HEAD 175,517 / 0) — the record's "IntangiblePower x10 over 191,270
calls / 2476 passed" was stale in BOTH the hit and the counts, and was already stale
before this change.
NEW FINDINGS (R1): **F3 — a new gap**: HookSystem.combat_is_over tests only
`phase == COMBAT_OVER` where C# gates on `IsOverOrEnding` (Hook.cs:53-63), affecting
all 73 combat-gated dispatchers in the window between the killing blow and teardown;
the faithful predicate `CombatState.is_over_or_ending` ALREADY EXISTS. Left open
deliberately (R11 is checking whether it is the same defect as
creature_card_cmds/step19's is_over==IsEnding closure claim — if so ONE fix closes
both). **F4 — a near-miss worth more than the fix**: implementing IsActiveForHooks
without Creature.HealInternal's ActivateHooks would have SILENTLY KILLED every
AfterCombatEnd relic effect on a fight won at 0 HP, and NOTHING IN THE SUITE WOULD HAVE
CAUGHT IT — the round-12 lesson reproduced exactly; now pinned. **F2** — the brief's
run.py:1095-1098 citation drifted to :1113-1116, and the `[*relics, *deck]` order bug
(reversed vs RunState.cs:548-570) is **LIVE, not dormant**: LanternKeyCard and map-hook
relics contend on the same hook today and the relic wins.

SWEEP 1 (wave-1 fold, 2026-08-01): closes+amendments APPLIED BY THE CONTROLLER for
R3 (7 closes + 4 in-place reasoning replacements) and R4 (4 closes + 3 amendments),
plus R10's 3 record amendments + new seam/hook_dispatch guard G-R10 + 2 GAP-QUEUE
annotations. Gates: closer round-trip 848/0; suite (minus the 933T env fixture file)
**3826 passed / 6 xfailed, 0 failed** — up from the 3766 baseline, and R1's PARTIAL
work is in that green number; citation_check 10919 citations / MISSING 49, PROVEN
PRE-EXISTING by running the same tool in a throwaway worktree of the branch point
(c9bc3374: 10889 citations, the SAME MISSING 49) — the fold added 30 citations and
broke none. Counts 372->361 entries, 349->338 mechanisms, unlabelled 56->42,
**LIVE 7->9 (UP, and honestly so)**: R3 confirmed power/the_bomb/InstanceType and
power/corruption as genuinely LIVE where they had been unlabelled inheriting dormancy.
Everything staged (66 files).

TOOLING DEFECT FOUND BY UNIT WORK (2026-08-01, the sixth round running — and this
time it bit the CONTROLLER, mid-fold): **closer.py's find() honours two disagreeing
conventions and CASE ALONE silently selects between them.** `find(rec, "G2")` matches
the guard whose `what` text starts "G2 ..."; `find(rec, "g2")` falls through to a
POSITIONAL lookup = guards[1]. gap_queue.py's local_ids are POSITIONAL, so for
relic/unsettling_lamp (guards labelled G1, N1, G2, N2, G3, G4) the queue's `g3` IS the
record's own "G2" and the queue's `g6` IS its "G4". R4's report quoted the RECORD'S
labels; I passed them through unchanged and closed/rewrote the unrelated N1 and N2
guards. Caught by inspecting the fold's own output (an amendment reported landing on a
`deliberate-divergence` entry where the report said `gap`), undone via `git checkout
HEAD -- <that one record>`, re-applied against g3/g6 with the label asserted.
closer.py now documents this as TRAP 3 and ships `find_by_label()` +
`find_labelled(local_id, label)`; **use find_labelled for every guard entry from here
on** — it proves the id landed where the report meant instead of quietly rewriting a
neighbour. Nothing else in the fold used a guard-label id (every other entry was a
hooks key or a queue-native gN), verified entry by entry.

Minor findings carried (wave 1): R3 — ReboundPower docstring retains one
self-contradicting paragraph; entry #12's "no affliction persists across combats"
phrasing overbroad (verdict stands on the on_death-clears argument); IsDupe is
unmodelled engine-wide (RF6 — relevant to R5's MoveToResultPileWithoutPlaying port).
R4 — entry 12 inherits entry 6's "divergence is in the draw" phrasing though
StoneCalendar.cs:96 hits all HittableEnemies with no RNG draw; kusarigama/
miniature_cannon queue annotations not refreshed (never carried the retracted claims);
test_r13_relic1 D3 restores DamageCmd.deal as a plain function not a staticmethod
(works for class-level call sites; monkeypatch.setattr is the correct idiom next touch).
