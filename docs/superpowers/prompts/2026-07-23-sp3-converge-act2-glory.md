# Prompt: SP3 — converge Act 2 (Glory) for both Ironclad seeds

Paste into a fresh session. Work in `c:\Users\Perry\Desktop\sts2-rl`. This
continues the SP3 per-seed convergence grind
(`[[sp3-933t-seed-converged-act0]]`, `[[sp3-89u-act1-reconcile-and-relics]]`).
Method is `[[docs/superpowers/prompts/2026-07-22-sp3-seed-convergence-grind.md]]`
— that file is canonical; this one supplies the starting state and the leads.

## Read this first: it is NOT a content port

The predecessor session's note said "NEXT = port act-2 Glory combats." **That
framing is wrong and will waste your time.** All 19 Glory encounters are already
ported in `sts2_rl/monsters/glory/` (Devoted Sculptor, Turret Operator, Globe
Head, Mecha Knight, Test Subject, Queen, Soul Nexus, Aeonglass, …), as are the
act-2 events (`tanx.py`, `tinker_time.py`), the Claws relic
(`sts2_rl/relics/claws.py`), Horn Cleat, and the Tremble / Luminesce / Evil Eye
cards. Act 2 force-wins because **the deck is already wrong when act 2 opens**,
not because the enemies are missing.

This is a normal convergence grind. Fix the earliest divergence, re-triage.

## Starting state (measured 2026-07-23, both triages re-run at the top of this session)

`py tools/converge_triage.py <seed> floor_49 2`

### 933T39V18D — `forced_combats=7`, `unresolved_play_card_ids=[]`

Earliest per-command mismatch is **room 442**, the opening hand of the **first
act-2 combat** (Turret Operator + Living Shield):

```
expected ['Luminesce', 'Conflagration+', 'Molten Fist', 'Impervious+', 'Hemokinesis+', 'Uppercut+']
got      ['Luminesce', 'Dark Embrace',   'Fasten+',     'Catastrophe+', 'Impervious+',  'Feel No Pain']
```

61 per-command mismatches total; 5 counter diffs (Shuffle 909/716,
CombatCardGeneration 113/96, CombatCardSelection 8/6, CombatTargets 26/10,
CombatPotionGeneration 14/4); DETECTOR 3 `act 1 player_hp` 56/61 (+5),
`act 2 player_hp` 67/80 (+13). Max-HP is green at all three checkpoints.

### 89U21BV1TZ — `forced_combats=10`, `unresolved_play_card_ids=[]`

**Its earliest divergence is in act 1, not act 2** — don't assume the two seeds
share a cause. `ProceedToNextAct` sits at log lines 217 / 464 / 719, so:

```
[play_card] room 448: expected 'play Bully (db id 23)',
            got ['Breakthrough','Pommel Strike','Taunt+','Uppercut','True Grit']
            (recorded card absent from live hand)
```

Line 448 is turn 4 of an act-1 fight; the same Bully instance (net id 1764463)
is played at lines 432, 448 and 451. `Bully.cs` is an ordinary 0-cost Uncommon
attack (damage scales on the target's Vulnerable) — **no return-to-hand
mechanic**, so this is a draw-order divergence upstream of line 448, not a Bully
bug. Also: 4 counter diffs (note CombatCardGeneration **over**-draws here:
1517/1568) and `act 2 player_max_hp` expected 111 got 107 (**low by 4**) — a
real max-HP gap, and max-HP deltas outrank current-HP in the priority order.

## Lead 1 (confirmed root cause for 933T) — multi-index `SelectGridCard`

`933T39V18D/floor_49` line 439 is `SelectGridCard 0 1 2 3 8` — **five indices in
one command**. It answers the Claws relic taken from the act-2 Ancient
(`ChooseEventOption 0 # TANX.pages.INITIAL.options.CLAWS`, line 438).

`Claws.cs` `AfterObtained`: `CardSelectorPrefs(prompt, 0, CardsVar(6))` with
`Cancelable = false, RequireManualConfirmation = true`, then
`CardSelectCmd.FromDeckForTransformation` → each chosen card becomes a **Maul**
carrying over upgrade and enchantment (`CreateMaulFromOriginal`).

`sts2_rl/conformance/runner.py:268` `_answer_select_grid` reads **only
`cmd.args[0]`** and returns one index. For a 5-index command it serves pick #1
and then finds no further `SelectGridCard` before the room boundary, so picks
2–5 fall back to `legal[0]`. The sim transforms the wrong 5 cards → the act-2
deck is wrong from the first fight onward. Every later act-2 hand mismatch is
downstream of this.

This is the same shape as the batch-17 `SelectHandCards` fix — see
`sts2_rl/conformance/combat_driver.py:83-100` for the established pattern
(one command, full-grid indices, consumed once). Note the in-combat path in
`combat_driver.py` already distinguishes the two; the out-of-combat path in
`runner.py` does not.

Corroboration that the fix is right: `Maul` / `Maul+` appear in 933T's recorded
act-2 hands from line 477 onward, and `Conflagration+` / `Molten Fist` (both in
the expected room-442 hand) were added at lines 395 and 45 respectively.

Watch for a second-order issue while you're here: `Claws.after_obtained` feeds
`run.removable_cards()` as candidates, but `CardSelectCmd.FromDeckForTransformation`
is passed **no filter** — check whether the game's grid is the full deck (index
mapping must match exactly or the indices land on different cards).

## Lead 2 (confirmed bug) — Mad Science "chaos" rider is on the shared rng

`[DETECTOR 1]` for 933T reports 1 wrong-stream site, 4 draws:
`sts2_rl/cards/mad_science.py:142` (`_play_skill`) calls
`random_pool_cards(ctx.combat._rng, 1, distinct=True)` — the unseeded shared
rng. 933T picks the card at line 461-463 (`TINKER_TIME` → `POWER` →
`EXPERTISE`), so the *chaos* rider isn't even the one this run took; audit all
three riders. Ground truth is `Core/Models/Events/TinkerTime.cs` and
`Core/Models/Cards/MadScience.cs`. A generated card almost certainly belongs on
`Rng.CombatCardGeneration` — and remember `[[random-card-pick-is-a-shuffle]]`:
check whether the source does `StableShuffle(...).First()` rather than one
`choice`, because that changes the *count*, not just the stream.

## Lead 3 — the counter gaps, after the deck is right

Re-triage before chasing these; most should shrink on their own once 933T's
act-2 deck is correct. What is left over is real:

- **CombatTargets −16** — auto-play targeting (`CardCmd.cs:77`,
  `Rng.CombatTargets.NextItem(HittableEnemies)`). 933T plays `Catastrophe+`
  repeatedly in act 2; each auto-played attack should draw one target.
- **CombatPotionGeneration −10** — 933T plays `Alchemize+` several times.
  Check whether the upgraded card procures **two** potions
  (`PotionFactory.CreateRandomPotionInCombat` is 2 draws per potion).
- **Shuffle −193** and **CombatCardGeneration −17** — likely mostly downstream.
- 89U's CombatCardGeneration **over**-draw (+51) is the odd one out; it is a
  distinct bug from 933T's under-draw and deserves its own look.

## Act-2 content 933T actually exercises (for orientation)

Ancient `TANX` → Claws; `TINKER_TIME` → Mad Science (Power / Expertise); a shop
(`BuyCard Tremble+`, `BuyRelic Horn Cleat`); combats vs Turret Operator + Living
Shield, Devoted Sculptor, Globe Head; `Mecha Knight` elite; `Test Subject #C71`
boss (two phases, 100 then 200 HP).

## Rules

- Ground truth is the decompiled game at
  `c:\Users\Perry\Desktop\Slay the Spire 2\src` (`[[original-means-game-source]]`).
  When a fix changes sim behaviour to match the game, **update legacy tests to
  the game-correct value — never weaken a real regression guard.**
- TDD: failing test with a source citation first, then the fix.
- **Never `git commit` / `git push`** in sts2-rl (`[[sts2-no-auto-commit]]`,
  CLAUDE.md rule 4). `git add <paths>` and stop; Perry commits in batches.
  **You inherit ~96 already-staged, uncommitted files** — stage on top, don't
  reset. RunReplays is a separate repo (fixtures staged, convention unconfirmed).
- `from __future__ import annotations` + lazy in-method imports.
- Out-of-combat draws ride the unseeded shared rng, so triage numbers wobble —
  run it 2–3× before trusting a delta (`[[conformance-replay-determinism]]`).

## Gates

- Seed gate: `py -m pytest test/test_conformance_player_state.py -k full_run_player_state_parity -q`
- Full suite (~5 min): `py -m pytest test/ -q` — baseline **2305 passed,
  6 xfailed**. Must stay green and unregressed.

## Definition of done

`933T39V18D` and `89U21BV1TZ` both reach the act-2 boss with **zero**
`player_hp` / `player_max_hp` divergence at every act boundary,
`forced_combats=0`, and unregressed stream counters — at which point both
`_XFAIL_CONVERGENCE` entries come out of
`test/test_conformance_player_state.py` and the cases go PASS.

If a genuinely un-ported piece of content turns up, port it if tractable, else
`xfail` that specific seed with an accurate reason and record the debt. Stage
everything, report the staged diff to Perry, and write a memory per new
fidelity gap found.
