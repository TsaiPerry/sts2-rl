# v14 run log — mechanics exposure (script: train_curriculum_v14.ps1)

Continue from `runs/sts2_run_torch_v13_s15_schema12.pt` — v13's hand-launched
best checkpoint (rest share 0.263, asc-0 win 3.33% gate-passing, asc-0 floor
32.36 all-time high, asc-10 floor 19.41 just under the 20.1 gate), migrated
schema 11→12 by `tools/migrate_handrow_v14.py` (lossless, logits-invariant,
eval-smoked 5/5) to carry the new `glow_gold` + `block_preview_move` obs
fields. v14 adds `--deck-inject` starter-deck packages (30 packages at prob
0.5, `runs/inject_v14.json`) targeting v13's low-take-rate cards, on top of
the §2b card-face fidelity verification sweep (below — zero port gaps found,
Ironclad/colorless has no computed-block card). No masks, ever.

## Launch

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -m pytest -q     # green first (test_train_io/test_live_onnx known-excluded)
.\train_curriculum_v14.ps1                # s16 8M, s16-run-asc10-inject; auto-evals (150 eps asc 10 + asc 0)
# crash recovery: .\train_curriculum_v14.ps1 -Resume
```

Script is smoke-tested (exit 0); native PowerShell only.

## Knobs / why

| Why | Knob |
|---|---|
| carry v13's best checkpoint forward through the schema-12 migration rather than retraining from scratch | seed = `runs/sts2_run_torch_v13_s15_schema12.pt`, produced by `tools/migrate_handrow_v14.py` |
| expose the deck-injection curriculum lever without forcing every episode through it | `--deck-inject runs/inject_v14.json` at prob 0.5 — 30 packages built from v13's asc-10 `take_rate < 0.20` cards (see provenance below); `pacts_end` is NOT in the set — its CSV row shows offered=19, one short of the >=20 gate |
| elite reward carried at v13's hand-launch reference value, not re-tuned this stage | `--reward-elite 2` |
| heads live from the v13 checkpoint, only the new obs fields + injected-deck start distribution need re-pricing | `--critic-warmup 8` |

## Gates

| Stage | Gate |
|---|---|
| s16 (150 eps, asc 10) | rest-upgrade share ≥ 0.15 SURVIVES (v13 s15: 0.263); floor ≥ 20.1 (v13: 19.41 — the still-open gate); truncations < 40/150; energy report vs 0.141 |
| s16 (150 eps, asc 0) | win ≥ 3.3% sustained (v13: 3.33%); floor report vs 32.36 (all-time high — a drop below ~30 means injection is taxing capability) |
| draft diversity (asc 10 cards.csv) | REPORT-ONLY this generation: count of cards (offered ≥ 20) with take_rate < 0.05 — v13: 24/59. Expect play-skill-before-pickrate (spec §3): unchanged count is NOT failure; a falling count is signal |
| elite diving | report: elites_fought − elites gap + losing-eps hp_ratio vs overall (v13: 0.25/ep, not HP-concentrated) |
| contingency | <5% count unmoved after s16 → ε-forced drafting flag (spec ladder); rest share < 0.15 → treat as v12-style transient ONLY if the train curve is still climbing, else revisit |

## NEXT (Perry)

- Launch training: `.\train_curriculum_v14.ps1` (see Launch block above;
  `-Resume` for crash recovery).
- SpireBot handoff, contract schema 8→12: the schema-12 deployment to the
  D: mods dir and the ONNX export gate both passed (max|Δ| 8.011e-05,
  offline parity clean). SpireBot's `dotnet build` is currently BLOCKED by
  pre-existing CS1061 `Rng.Counter` errors — a game-DLL version skew
  unrelated to the v14 edit; Perry needs to fix the build env before the
  mod can compile again.
- The live obs-parity diff (`compare_obs` against a fresh game dump, once
  SpireBot builds) rides the next showcase session — not blocking s16
  launch, but needed before the schema-12 mod is trusted live.

## Log

- 2026-08-15: v14 run log assembled (Task 9). Migration, inject-package
  generation, and the §2b fidelity sweep are all complete and verified;
  s16 has not launched yet. Awaiting Perry's launch per the NEXT section
  above.
- 2026-08-16: **s16 RAN AND ANALYZED (iters 976→1585, eval ckpt iter 1586,
  150 eps each asc). ALL HARD GATES PASS — including the asc-10 floor gate
  for the first time ever.**

  | Gate | v13 s15 | v14 s16 | Verdict |
  |---|---|---|---|
  | asc-10 rest-upgrade share ≥ 0.15 | 0.263 | **0.404** | PASS — all-time high |
  | asc-10 floor ≥ 20.1 | 19.41 | **20.86** (median 16.0→19.5) | **PASS — first time** |
  | asc-10 truncations < 40/150 | 7 | 13 | PASS |
  | asc-0 win ≥ 3.3% | 3.33% | 3.33% (5/150) | PASS — sustained |
  | asc-0 floor (report, alarm <~30) | 32.36 | 32.02 | held — injection is NOT taxing capability |

  Report-only lines: asc-10 energy_unspent/turn **regressed 0.141→0.199**
  (asc-0 0.169→0.233; train-curve energy also drifted up late — plausibly
  X-cost/expensive injected cards, watch next gen). Draft diversity
  <0.05-count 24/59 → 23/58 — nominally unchanged, as spec §3 predicted.
  The real injection signal is per-card: **15/27 comparable injected cards
  moved up >+0.02** (inferno 0.182→0.444, juggling 0→0.086, iron_wave
  0.150→0.212, bloodletting 0→0.056, havoc 0→0.044, true_grit 0→0.040,
  colossus/body_slam/blood_wall/evil_eye/feel_no_pain off hard-zero), and
  overall take rate dropped 0.875→0.809 (more selective drafting).
  **9 cards remain hard-0.000**: burning_pact, drum_of_battle,
  expect_a_fight, forgotten_ritual, howl_from_beyond, pyre, rupture,
  second_wind, vicious — dominated by the conditional/synergy set; the
  burning_pact pairings did not revive their partners (second_wind,
  feel_no_pain moved only via injection exposure, not drafting). Per the
  contingency ladder these are the ε-forced-drafting candidates for v15.
  Elite diving: fought−offered gap 0.21/ep (v13 0.25), losing-eps
  hp_ratio == overall (0.775) — still not HP-concentrated. Potions still
  the dead term: use-rate 0.027 (23/865), though mean hp@use improved
  0.969→0.840. Train curve ep_ret 17.99→18.76 over the stage, still
  gently climbing at cutoff — the checkpoint is not saturated.
  Best ckpt: `runs/sts2_run_torch_v14_s16.pt` (iter 1586).

## §2b sweep table

Verification sweep for Task 2 (`calc_block` hook / `card_base_block`
helper): diffed each of the sim's 7 `calc_damage` cards against the game's
`CalculatedDamageVar.WithMultiplier` lambda, confirmed SecondWind/TrueGrit
print static `BlockVar`, and confirmed no Ironclad/colorless-reachable card
uses a computed block var.

| Card | Sim file | Game citation | Verdict |
|---|---|---|---|
| Ashen Strike | `sts2_rl/cards/ashen_strike.py:36-37` (`self._base + self._extra * len(ctx.player.exhaust_pile)`) | `AshenStrike.cs:20-22` — `CalculationBaseVar(6m)`, `ExtraDamageVar(3m)`, `WithMultiplier(... PileType.Exhaust.GetPile(card.Owner).Cards.Count)` | CONFIRMED-MATCHES |
| Body Slam | `sts2_rl/cards/body_slam.py:33-34` (`return ctx.player.block`) | `BodySlam.cs:18-20` — `CalculationBaseVar(0m)`, `ExtraDamageVar(1m)`, `WithMultiplier(... card.Owner.Creature.Block)` | CONFIRMED-MATCHES |
| Bully | `sts2_rl/cards/bully.py:35-37` (`self._base + self._extra * vuln`) | `Bully.cs:19-21` — `CalculationBaseVar(4m)`, `ExtraDamageVar(2m)`, `WithMultiplier(... target?.GetPowerAmount<VulnerablePower>() ?? 0)` | CONFIRMED-MATCHES |
| Gold Axe | `sts2_rl/cards/colorless_attacks.py:170-172` (count of `CardPlayedEntry` in history) | `GoldAxe.cs:19-21` — `CalculationBaseVar(0m)`, `ExtraDamageVar(1m)`, `WithMultiplier(... CombatManager.Instance.History.CardPlaysFinished.Count())` | CONFIRMED-MATCHES |
| Mind Blast | `sts2_rl/cards/colorless_attacks.py:292-293` (`len(ctx.player.draw_pile)`) | `MindBlast.cs:17-19` — `CalculationBaseVar(0m)`, `ExtraDamageVar(1m)`, `WithMultiplier(... PileType.Draw.GetPile(card.Owner).Cards.Count)` | CONFIRMED-MATCHES |
| Perfected Strike | `sts2_rl/cards/perfected_strike.py:37-39` (count of `"strike"`-tagged cards in `all_cards`) | `PerfectedStrike.cs:23-25` — `CalculationBaseVar(6m)`, `ExtraDamageVar(2m)`, `WithMultiplier(... AllCards.Count(c => c.Tags.Contains(CardTag.Strike)))` | CONFIRMED-MATCHES |
| Rend | `sts2_rl/cards/colorless_attacks.py:373-390` (`_debuff_count`: excludes `TemporaryStrengthPower`, else `power_type == DEBUFF or (allow_negative and amount < 0)`) | `Rend.cs:19-21,43-50` — `CalculationBaseVar(15m)`, `ExtraDamageVar(5m)`, `WithMultiplier(... target?.Powers.Count(ShouldCountPower) ?? 0)`; `ShouldCountPower` = `TypeForCurrentAmount == Debuff && !(power is ITemporaryPower)` | CONFIRMED-MATCHES — sim's sign-aware inclusion test is behaviorally equivalent to `PowerModel.GetTypeForAmount` (`powers.py:97-120`'s already-audited `type_for_amount`) given the sim invariant that non-`allow_negative` powers are removed before their amount can go negative; the only ITemporaryPower/DEBUFF instances reachable in the ported content (`ManglePower`, `DarkShacklesPower`, `ShacklingPotionPower`) are all `TemporaryStrengthPower` subclasses, so the `isinstance` exclusion is exhaustive. No fix needed. |
| Second Wind | n/a (no `calc_block`) | `SecondWind.cs:17` — `new BlockVar(5m, ValueProp.Move)` (static; the per-hand loop lives in `OnPlay`, not the var) | CONFIRMED-MATCHES (static `base_block`, no computed block) |
| True Grit | n/a (no `calc_block`) | `TrueGrit.cs:18` — `new BlockVar(7m, ValueProp.Move)` (static) | CONFIRMED-MATCHES (static `base_block`, no computed block) |

**No-other-reachable-user check:** `Select-String -Path "…\Core\Models\Cards\*.cs" -Pattern "CalculatedDamageVar|WithMultiplier" -List` lists 41 files; the only computed-*block* var class in the game is `CalculatedBlockVar` (distinct from `CalculatedDamageVar`), used by exactly 6 cards: `SovereignBlade.cs` (Regent parry — `Owner.Character is Regent` at line 125), `Mirage.cs` (poison-sum), `Mimic.cs`, `Sacrifice.cs` (Necrobinder's Osty minion), `Stack.cs`, and `DemonicShield.cs` (Ironclad but multiplayer-only, filtered by `CardFactory.FilterForPlayerCount` — see `sts2_rl/cards/pool.py:35-37`'s comment). None of their ids (`sovereign_blade`, `mirage`, `mimic`, `sacrifice`, `stack`, `demonic_shield`) appear in `IRONCLAD_POOL` or `COLORLESS_POOL` (`sts2_rl/cards/pool.py:15-51`), and none are implemented as sim cards at all. Confirms the brief's research note: zero Ironclad/colorless-reachable `calc_block` overrides today.

## inject_v14.json provenance

Generator (Task 6, base list — threshold `take_rate < 0.20`, `offered >= 20`,
class name → id via `_CARD_CLASSES` reverse map):

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -c "
import csv, json
from sts2_rl.cards.base import _CARD_CLASSES
cls2id = {cls.__name__: cid for cid, cls in _CARD_CLASSES.items()}
with open('runs/eval_v13_s15_asc10.cards.csv') as f:
    rows = [r for r in csv.DictReader(f)
            if int(r['offered']) >= 20 and float(r['take_rate']) < 0.20]
ids = sorted(cls2id[r['card']] for r in rows)
print(json.dumps(ids, indent=0))
print(len(ids), 'cards')"
```

Output: 30 ids, all resolved via the reverse map (zero misses) —
`armaments, blood_wall, bloodletting, body_slam, burning_pact, cinder,
colossus, cruelty, drum_of_battle, evil_eye, expect_a_fight, feel_no_pain,
forgotten_ritual, havoc, hellraiser, howl_from_beyond, inferno, iron_wave,
juggling, pillage, pyre, rupture, second_wind, stone_armor, sword_boomerang,
tear_asunder, thunderclap, true_grit, vicious, whirlwind`.

`pacts_end` (named in the spec §3 example table) did not appear in this
generation's base list, so its row from the Task 6 brief's package table
was not applicable — no `pacts_end` package was written.

Two additional conditional cards showed up beyond the brief's fixed table
and needed the same "dead alone" treatment as Rupture/Pact's End: `feel_no_pain`
(Power, `AfterCardExhausted` → block; zero baseline value with no exhaust
source in the run, per `sts2_rl/cards/feel_no_pain_card.py`'s docstring) and
`forgotten_ritual` (Skill with its own Exhaust keyword; gains energy only
`if a card was exhausted this turn` and its own exhaust registers too late
to satisfy itself, per `sts2_rl/cards/forgotten_ritual.py`'s docstring — a
solo play is strictly a wasted card). Both were paired with `burning_pact`
(`sts2_rl/cards/burning_pact.py`: unconditional "exhaust a chosen card;
draw 2" — the same "exhaust card" role the spec's own Second Wind example
uses) rather than inventing a new enabler.

Every other card in the base list has baseline value independent of any
partner card (guaranteed damage/block/draw/energy on its own, or a trigger
condition already met by the fixed starter deck — e.g. `hellraiser`
against starter Strikes, `vicious`/`cruelty`/`colossus` against Vulnerable
from starter Bash) and was left as a 1-card package.

Final `runs/inject_v14.json` package list (30 packages, 8 multi-card):

```json
{
  "packages": [
    ["armaments"],
    ["blood_wall"],
    ["bloodletting", "rupture"],
    ["body_slam", "iron_wave"],
    ["burning_pact", "true_grit"],
    ["cinder"],
    ["colossus"],
    ["cruelty"],
    ["drum_of_battle"],
    ["evil_eye"],
    ["expect_a_fight"],
    ["feel_no_pain", "burning_pact"],
    ["forgotten_ritual", "burning_pact"],
    ["havoc"],
    ["hellraiser"],
    ["howl_from_beyond"],
    ["inferno"],
    ["iron_wave"],
    ["juggling"],
    ["pillage"],
    ["pyre"],
    ["rupture", "bloodletting"],
    ["second_wind", "burning_pact"],
    ["stone_armor"],
    ["sword_boomerang"],
    ["tear_asunder"],
    ["thunderclap"],
    ["true_grit", "burning_pact"],
    ["vicious"],
    ["whirlwind"]
  ]
}
```

Verified via the real env path (`STS2RunEnv(deck_inject=..., deck_inject_prob=1.0)`,
`env.reset(seed=1)`): seed 1 → 11-card deck (10 starters + `cruelty`);
seed 12 checked separately → 12-card deck (10 starters + `second_wind` +
`burning_pact`), confirming multi-card package injection works end to end.
