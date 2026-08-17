# v15 — Extension, Mid-Run Exposure, Rest-Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v15: fix the live SpireBot Smith-execution loop that corrupted the rest-behavior readout, add an HP-conditioned rest metric and mid-run dead-card injection to sts2-rl, and run s17 (+8M plain extension) → s18 (+8M mid-run inject) with `hp_lost/floor` promoted to a first-class gate line.

**Architecture:** Three independent strands. (A) SpireBot: the live bot's grid-select confirm path bypasses the game's own close flow, so a rest Smith mints upgrades without consuming the rest — research the exact breaking link, fix, Perry live-verifies. (B) sts2-rl metrics + env: new `rest_*_hihp` counters (rest behavior conditioned on hp ≥ 0.65 at the visit) threaded through the existing `_count_behavior → info → evaluation.py → episodes.csv` pipeline; a new `--deck-inject-midrun-prob` env lever that appends a dead-list package on floor advance (environment stochasticity, NOT action forcing — forced actions are off-policy poison for PPO). (C) Curriculum: `train_curriculum_v15.ps1` with s17 (same knobs as v14 s16, pure capability harvest — the v14 curve was still climbing at cutoff) then s18 (mid-run inject on the 9 hard-zero synergy cards). The linear-curve experiment (`--hp-potential-low-share 0.35`) is documented as a decision-gated s19 contingency, NOT implemented as an automatic stage.

**Tech Stack:** Python 3.12 (.venv), raw-PyTorch PPO (`train_torch.py`), pytest; C# net9.0 Godot mod (SpireBot), Harmony patches; native PowerShell launch scripts.

## Global Constraints

- **Stage only, never commit/push** in sts2-rl AND SpireBot — Perry commits (project rule, overrides auto-committing skills).
- **Never re-mask**: no rest masks, no potion masks, no draft masks — exposure levers are env-side stochasticity only.
- **One knob per stage**: s17 changes nothing vs v14 s16; s18 adds exactly the mid-run inject; the curve experiment is s19-contingent, never bundled.
- Training/eval launches are **native PowerShell only** (Git-Bash→powershell.exe hangs worker spawns).
- Subagents run on **sonnet** (project rule).
- sts2-rl suite must stay green: `.venv\Scripts\python.exe -m pytest -q` (test_train_io/test_live_onnx have known xfail/skip baselines).
- `EPISODE_CSV_FIELDS` column order is a public contract — new columns append at the END only.
- The default env must draw **zero rng** from any new lever when it is off (branch_prob precedent, `curriculum_env.py:238-244`).
- SpireBot vendored files (`SpireBotCode/Replay/**`) may be edited only with a numbered delta entry in `SpireBotCode/Replay/VENDORED-FROM.md`.

**Baseline numbers (v14 s16, 150-ep evals, for every gate below):** asc-10: rest-upgrade share 0.404, floor 20.86, win 0%, trunc 13, energy/turn 0.199, hp_lost/floor 7.94; asc-0: win 3.33%, floor 32.02, energy/turn 0.233, hp_lost/floor 7.30. Dead-9 cards (take_rate exactly 0.000, offered ≥ 20, asc-10): burning_pact, drum_of_battle, expect_a_fight, forgotten_ritual, howl_from_beyond, pyre, rupture, second_wind, vicious.

---

### Task 1: SpireBot — rest-Smith execution loop root-cause + fix

**Files:**
- Read (research): `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Multiplayer\Game\RestSiteSynchronizer.cs` (`ChooseLocalOption`, `GetLocalOptions` — does a used rest empty the options?), `src\Core\Nodes\Rooms\NRestSiteRoom.cs` (`AfterSelectingOption` — what marks the site consumed), `src\Core\Nodes\Screens\CardSelection\NDeckUpgradeSelectScreen.cs:146-257` (single-select confirm flow: `OnCardClicked` → preview → `CheckIfSelectionComplete` → `SetResult` + `NOverlayStack.Instance.Remove(this)`)
- Modify: `c:\Users\Perry\Desktop\SpireBot\SpireBotCode\Replay\Commands\SelectGridCardCommand.cs:33-56`
- Modify (likely, per research): `c:\Users\Perry\Desktop\SpireBot\SpireBotCode\Replay\Commands\ChooseRestSiteOptionCommand.cs:31-56`
- Modify: `c:\Users\Perry\Desktop\SpireBot\SpireBotCode\Replay\VENDORED-FROM.md` (delta 17)

**Interfaces:**
- Consumes: `CardGridScreenCapture.ActiveScreen`, `.GetSelectableCards`, `.ClickCard`, `.ConfirmSelection` (`SpireBotCode/Replay/Commands/CardGridScreenCapture.cs:73-114`); `Affordance.IsLive` (`SpireBotCode/Affordance.cs:33-38`).
- Produces: no new API — behavioral fix only. Later tasks do not depend on this task.

**Evidence to reproduce against** (run SXFY52G6VQ): dump rows 78–94 (`C:\Users\Perry\Desktop\SpireBot\runs\SXFY52G6VQ\decisions.jsonl`) show Rest:Smith→SelectCards alternating 8× at constant hp 0.84; `%APPDATA%\SlayTheSpire2\SpireBot\logs\SXFY52G6VQ\floor_23\run.save` shows exactly 2 minted upgrades (TWIN_STRIKE, DRAMATIC_ENTRANCE, both `current_upgrade_level=1`); attempts 3–8 upgraded nothing; the loop ended only when a 3%-probability Heal was sampled. A single Smith at act1 f10 (candidate 13 → grid 13) completed normally.

- [ ] **Step 1: Research — identify the breaking link.** Read the three game files above and answer in writing (a short findings note in the task report): (1) after a successful `ChooseLocalOption`, does `GetLocalOptions()` still return options (if yes, the dispatcher's rest enumeration at `ReplayDispatcher.cs:221-227` re-offers a spent rest and MUST be gated); (2) what `NRestSiteRoom.AfterSelectingOption` does and whether our deferred call at `ChooseRestSiteOptionCommand.cs:76` can silently fail when a ghost overlay is on top; (3) why attempts 3–8 opened select screens but applied no upgrade.

- [ ] **Step 2: Implement Fix A — drive the game's own close path in `SelectGridCardCommand.Execute`.** Replace lines 53-55 with:

```csharp
        CardGridScreenCapture.ConfirmSelection(screen, selected);
        // SpireBot delta 17: the game's own single-select confirm
        // (NDeckUpgradeSelectScreen.CheckIfSelectionComplete:248-257) pairs
        // SetResult with NOverlayStack.Instance.Remove(this). Resolving the
        // completion source without removing the screen leaves a ghost
        // overlay: the rest site re-offers its options underneath and the
        // bot smiths again (observed: 2 free upgrades minted at SXFY52G6VQ
        // act0 f12, rest never consumed). Mirror the full close.
        Godot.Callable.From(() =>
        {
            if (GodotObject.IsInstanceValid(screen) && screen.IsInsideTree())
                MegaCrit.Sts2.Core.Nodes.NOverlayStack.Instance.Remove(screen);
        }).CallDeferred();
        CardGridScreenCapture.ActiveScreen = null;
        return ExecuteResult.Ok();
```

(Adjust the `NOverlayStack` namespace to the actual one found in `NDeckUpgradeSelectScreen.cs`'s usings if it differs.)

- [ ] **Step 3: Implement Fix B if Step 1's answer (1) is yes** — gate the spent rest. In `ChooseRestSiteOptionCommand.Execute`, before the dispatch (after line 51), add a refusal using whatever spent-state the research found on `NRestSiteRoom`/`RestSiteSynchronizer` (e.g. an already-chosen flag), with a `PlayerActionBuffer.LogDispatcher` line naming the refusal. If the game exposes no such state, gate on the room's option buttons via `Affordance.IsLive` instead. Both fixes may coexist — defense in depth is the established pattern (chest fix, delta 16).

- [ ] **Step 4: Log delta 17 in `VENDORED-FROM.md`** — same format as delta 16: what changed, why, the SXFY52G6VQ evidence, and that recorded-replay playback masked it.

- [ ] **Step 5: Build + stage.**

Run: `cd c:\Users\Perry\Desktop\SpireBot; dotnet build`
Expected: `0 Error(s)` (1 pre-existing CS8602 warning); the DLL auto-deploys to `D:\...\mods\SpireBot\`.
Then: `git add SpireBotCode\Replay\Commands\SelectGridCardCommand.cs SpireBotCode\Replay\Commands\ChooseRestSiteOptionCommand.cs SpireBotCode\Replay\VENDORED-FROM.md` (NO commit).

- [ ] **Step 6: Live verification protocol (Perry, game launch required).** Start a new Ironclad asc-0 run, let the bot drive to a rest site with hp < 100%. Acceptance: exactly ONE Smith decision followed by ONE SelectCards decision, the deck gains exactly ONE upgrade (check the overlay/next combat), the rest room proceeds to the map, and the decision dump shows no Rest:Smith repetition. Also re-verify a chest room end-to-end (delta 16 landed but has not been live-verified either).

---

### Task 2: sts2-rl — HP-conditioned rest metrics (`rest_visits_hihp`, `rest_upgrades_hihp`)

**Files:**
- Modify: `sts2_rl/run_env.py` (module constant near `_hp_potential` ~line 617; counter init ~line 876-883; `_count_behavior` REST branch lines 1180-1192; `_info` episode-end block ~line 1707-1709)
- Modify: `sts2_rl/evaluation.py` (RunEvalReport fields ~line 236; harvest ~line 627; `EPISODE_CSV_FIELDS` line 693-705; `write_run_csv` row ~line 778)
- Test: `test/test_behavior_metrics.py` (extend the existing rest tests around lines 250-330)

**Interfaces:**
- Consumes: existing per-visit dedup state `_rest_visit_key`/`_rest_healed_here`/`_rest_upgraded_here` (`run_env.py:879-883`), `request.run.hp`/`.max_hp` in `_count_behavior`.
- Produces: `info["ep_rest_visits_hihp"]`, `info["ep_rest_upgrades_hihp"]` (ints, episode-end only); `RunEvalReport.rest_visits_hihp`, `.rest_upgrades_hihp` (tuple[int, ...]); CSV columns `rest_visits_hihp`, `rest_upgrades_hihp` appended LAST in `EPISODE_CSV_FIELDS`. NOT added to `vec_env.EP_METRIC_KEYS` (eval-only, same as the per-card tallies).

**Definition:** a rest visit is "hi-HP" iff `hp/max_hp >= 0.65` at the FIRST rest answer of that visit (the moment `_rest_visit_key` changes). `rest_upgrades_hihp` counts first-Smith answers within hi-HP visits. 0.65 is `HIHP_REST_THRESHOLD`, a module constant. Rationale in the constant's comment: v14 dump evidence shows the policy's heal/smith crossover sits near 0.6-0.74; the gate metric must condition on the regime Perry's complaint names.

- [ ] **Step 1: Write the failing test.** Extend `test/test_behavior_metrics.py`: locate the existing rest-branch test (~line 300-330, the one asserting `env._ep_rest_visits == 1` after driving `_count_behavior` with REST answers) and add a sibling test using the same fixtures/helpers, with the run's hp forced high then low:

```python
def test_rest_hihp_split(rest_env_and_request):  # reuse the file's existing fixture/helper names
    env, req = rest_env_and_request
    # hi-HP visit: hp/max_hp >= 0.65 at first answer
    req.run.hp, req.run.max_hp = 70, 100
    env._count_behavior(req, REST_SMITH)
    assert (env._ep_rest_visits_hihp, env._ep_rest_upgrades_hihp) == (1, 1)
    # second answer at the same site: no double count
    env._count_behavior(req, REST_SMITH)
    assert env._ep_rest_upgrades_hihp == 1
    # new site, low HP: visit not counted as hihp even if it smiths
    req.run.total_floor += 1
    req.run.hp = 30
    env._count_behavior(req, REST_SMITH)
    assert (env._ep_rest_visits_hihp, env._ep_rest_upgrades_hihp) == (1, 1)
```

Adapt fixture construction to the file's existing pattern (the tests there already build an env and a synthetic rest request — mirror the neighboring test exactly; do NOT invent a new harness). Also extend the file's `_info` end-of-episode test (~line 316-320 pattern) to assert both new keys appear at episode end and not mid-episode.

- [ ] **Step 2: Run to verify failure.**

Run: `.venv\Scripts\python.exe -m pytest test/test_behavior_metrics.py -q -k hihp`
Expected: FAIL with `AttributeError: ... _ep_rest_visits_hihp`

- [ ] **Step 3: Implement.** In `run_env.py`:

Module constant (next to `_hp_potential`, ~line 617):

```python
#: A rest visit counts as "high HP" when hp/max_hp is at or above this at
#: the visit's first answer. 0.65 sits above the v14 policy's observed
#: heal/smith crossover (heals dominate <= 0.60, smith dominates >= 0.74),
#: so the eval column isolates exactly the regime the rest-economy gates ask
#: about ("does it upgrade when healthy?").
HIHP_REST_THRESHOLD = 0.65
```

Counter init (after line 883 `self._rest_upgraded_here = False`):

```python
        self._ep_rest_visits_hihp = 0
        self._ep_rest_upgrades_hihp = 0
        self._rest_visit_hihp = False
```

`_count_behavior` REST branch — replace lines 1180-1192 with:

```python
        elif request.kind == DecisionKind.REST and answer < POTION_ACTION_BASE:
            key = (request.run.act_index, request.run.total_floor)
            if key != self._rest_visit_key:
                self._rest_visit_key = key
                self._ep_rest_visits += 1
                self._rest_healed_here = False
                self._rest_upgraded_here = False
                # Classified once, at the visit's first answer -- later
                # answers at the same site (heal after smith etc.) keep the
                # entry ratio, so the split is per-visit not per-answer.
                ratio = min(request.run.hp, request.run.max_hp) / max(1, request.run.max_hp)
                self._rest_visit_hihp = ratio >= HIHP_REST_THRESHOLD
                if self._rest_visit_hihp:
                    self._ep_rest_visits_hihp += 1
            if answer == REST_HEAL and not self._rest_healed_here:
                self._rest_healed_here = True
                self._ep_rest_heals += 1
            elif answer == REST_SMITH and not self._rest_upgraded_here:
                self._rest_upgraded_here = True
                self._ep_rest_upgrades += 1
                if self._rest_visit_hihp:
                    self._ep_rest_upgrades_hihp += 1
```

`_info` (after line 1709 `info["ep_rest_upgrades"] = ...`):

```python
            info["ep_rest_visits_hihp"] = self._ep_rest_visits_hihp
            info["ep_rest_upgrades_hihp"] = self._ep_rest_upgrades_hihp
```

- [ ] **Step 4: Run the new tests.**

Run: `.venv\Scripts\python.exe -m pytest test/test_behavior_metrics.py -q`
Expected: PASS (all, including pre-existing).

- [ ] **Step 5: Thread through evaluation.py.** Add to `RunEvalReport` (after line 236 `rest_upgrades`):

```python
    # v15: the same rest split conditioned on entering the site at
    # hp/max_hp >= run_env.HIHP_REST_THRESHOLD (0.65) -- the rest-economy
    # gate metric ("does it upgrade when healthy?").
    rest_visits_hihp: tuple[int, ...] = ()
    rest_upgrades_hihp: tuple[int, ...] = ()
```

In the harvest loop (next to line 627 `rest_visits.append(...)`), add parallel lists `rest_visits_hihp` / `rest_upgrades_hihp` reading `info.get("ep_rest_visits_hihp", 0)` / `info.get("ep_rest_upgrades_hihp", 0)`, and pass them into the report construction (line ~666 block). Append `"rest_visits_hihp", "rest_upgrades_hihp"` at the END of `EPISODE_CSV_FIELDS` (after `"hp_ratio_mean"`), and at the END of the `writer.writerow([...])` list in `write_run_csv`:

```python
                    report.rest_visits_hihp[i] if report.rest_visits_hihp else 0,
                    report.rest_upgrades_hihp[i] if report.rest_upgrades_hihp else 0,
```

- [ ] **Step 6: Full suite.**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: green at the current baseline (no new failures; test_train_io/test_live_onnx baselines unchanged).

- [ ] **Step 7: Stage.** `git add sts2_rl/run_env.py sts2_rl/evaluation.py test/test_behavior_metrics.py` (NO commit).

---

### Task 3: sts2-rl — mid-run deck injection (`--deck-inject-midrun-prob`)

**Files:**
- Modify: `sts2_rl/run_env.py` (EnvSpec/ctor kwargs ~line 660; ctor body ~line 747-757; `step()` floor-advance site ~line 1026-1039)
- Modify: `train_torch.py` (CLI flag threading — copy the exact pattern `--deck-inject-prob` used in v14; find it with `grep -n "deck_inject" train_torch.py` and mirror every site)
- Modify: `sts2_rl/vec_env.py` / `sts2_rl/curriculum_env.py` ONLY IF `deck_inject_prob` appears there (mirror it; check with `grep -rn "deck_inject" sts2_rl/`)
- Test: `test/test_v15_midrun_inject.py` (new; model on `test/test_v14_deck_inject.py`)

**Interfaces:**
- Consumes: `self._deck_inject_packages` (parsed package list, `run_env.py:748-757`), `_inject_deck`'s append idiom (`run_env.py:963-971`), the floor-advance delta already computed in `step()` (`run.total_floor - floor_before`, line 1026-1030).
- Produces: env kwarg `deck_inject_midrun: str | None = None`, `deck_inject_midrun_prob: float = 0.0`; CLI `--deck-inject-midrun PATH`, `--deck-inject-midrun-prob P`. Semantics: each step where `run.total_floor` advanced (by any amount), with probability P (one rng draw per advanced step), append ONE package from the midrun JSON to `run.deck` — plain append, no hooks, same as `_inject_deck`.

**Why env-side, not action-forcing:** forced draft actions are off-policy — PPO's loss assumes logged actions came from the current policy. Mid-run env injection gives the same play-exposure with zero off-policy contamination, and reuses v14's validated machinery.

**Accounting guard (load-bearing):** the deck-growth ledger (`run_env.py:1055-1067`) pays `reward_upgrade` on upgrade-sum increases and `reward_remove` on shrink; a plain append of unupgraded cards changes neither sum direction that pays, and `_deck_len_base` re-syncs at the next out-of-combat check — so injection must append UNUPGRADED cards only, and the test must assert the injecting step's reward gained no upgrade/remove term.

- [ ] **Step 1: Write the failing test** (`test/test_v15_midrun_inject.py`, modeled on `test_v14_deck_inject.py`'s env-construction pattern — copy its imports/env builder):

```python
import json

from sts2_rl.run_env import STS2RunEnv   # match test_v14_deck_inject.py's exact import path


def _mk_midrun_json(tmp_path):
    p = tmp_path / "midrun.json"
    p.write_text(json.dumps({"packages": [["vicious"]]}))
    return str(p)


def test_midrun_inject_appends_on_floor_advance(tmp_path):
    env = STS2RunEnv(deck_inject_midrun=_mk_midrun_json(tmp_path),
                     deck_inject_midrun_prob=1.0)
    env.reset(seed=3)
    base = len(env._run.deck)
    # drive until the first floor advance (mask-legal first actions)
    import numpy as np
    for _ in range(400):
        floor_before = env._run.total_floor
        legal = np.flatnonzero(env.action_masks())
        obs, r, term, trunc, info = env.step(int(legal[0]))
        if env._run.total_floor > floor_before:
            break
        if term or trunc:
            assert False, "episode ended before any floor advance"
    assert len(env._run.deck) > base
    assert any(type(c).__name__ == "ViciousCard" for c in env._run.deck)


def test_midrun_inject_off_draws_no_rng(tmp_path):
    # zero-draw contract: default env must be bit-identical with the flag off
    import numpy as np
    def rollout(**kw):
        env = STS2RunEnv(**kw)
        env.reset(seed=7)
        out = []
        for _ in range(60):
            legal = np.flatnonzero(env.action_masks())
            obs, r, *_ , info = env.step(int(legal[0]))
            out.append((round(float(r), 6), info["floor"]))
        return out
    assert rollout() == rollout(deck_inject_midrun=_mk_midrun_json(tmp_path),
                                deck_inject_midrun_prob=0.0)
```

(Adapt the env class name / `action_masks` accessor to whatever `test_v14_deck_inject.py` actually uses — mirror that file, it is the ground truth for this harness.)

- [ ] **Step 2: Run to verify failure.**

Run: `.venv\Scripts\python.exe -m pytest test/test_v15_midrun_inject.py -q`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'deck_inject_midrun'`

- [ ] **Step 3: Implement in `run_env.py`.** Ctor kwargs (next to line 660-661):

```python
        deck_inject_midrun: str | None = None,
        deck_inject_midrun_prob: float = 0.0,
```

Ctor body (next to line 747-757, same parse-and-validate shape as `deck_inject`):

```python
        self._deck_inject_midrun_prob = deck_inject_midrun_prob
        self._deck_inject_midrun_packages: list[list[str]] | None = None
        if deck_inject_midrun is not None:
            with open(deck_inject_midrun) as fh:
                pkgs = json.load(fh)["packages"]
            self._deck_inject_midrun_packages = pkgs
```

(Copy whatever id-validation the v14 block at 749-757 performs verbatim — same errors, same shape.)

In `step()`, immediately after the floor-reward block (after line 1030, before `reward += self._act_reward ...`):

```python
        # v15 mid-run exposure: on a floor advance, with probability P,
        # append one dead-list package to the live deck. Same zero-draw
        # short-circuit contract as the reset-time inject (run_env.py:863):
        # packages None or prob 0.0 must draw no rng. Plain append of
        # UNUPGRADED cards only -- the deck ledger below (1055-1067) pays
        # nothing for growth, and the next out-of-combat check re-syncs
        # _deck_len_base, so no reward term fires from the injection itself.
        if (run.total_floor > floor_before
                and self._deck_inject_midrun_packages is not None
                and self._deck_inject_midrun_prob > 0.0
                and self._rng.random() < self._deck_inject_midrun_prob):
            from .cards import make_card
            for cid in self._rng.choice(self._deck_inject_midrun_packages):
                run.deck.append(make_card(cid))
```

- [ ] **Step 4: Run the new tests.**

Run: `.venv\Scripts\python.exe -m pytest test/test_v15_midrun_inject.py test/test_v14_deck_inject.py -q`
Expected: PASS (both files — the v14 tests guard the reset-time lever against regression).

- [ ] **Step 5: Thread the CLI.** `grep -n "deck_inject" train_torch.py sts2_rl/vec_env.py sts2_rl/curriculum_env.py` and mirror every `deck_inject`/`deck_inject_prob` site with `deck_inject_midrun`/`deck_inject_midrun_prob` (argparse flag, EnvSpec field, build_env pass-through — identical shape, defaults `None`/`0.0`).

- [ ] **Step 6: Full suite + stage.**

Run: `.venv\Scripts\python.exe -m pytest -q` — expected green at baseline.
Then: `git add sts2_rl/run_env.py train_torch.py test/test_v15_midrun_inject.py` plus any vec_env/curriculum_env touched (NO commit).

---

### Task 4: sts2-rl — `runs/inject_v15_dead.json` (the dead-9 package list)

**Files:**
- Create: `runs/inject_v15_dead.json` (gitignored build artifact, like `inject_v14.json`)

**Interfaces:**
- Produces: the file consumed by Task 5's `--deck-inject-midrun runs/inject_v15_dead.json`.

**Content — write exactly this** (the 9 hard-zero cards from the v14 asc-10 eval; enabler pairings carried over from `inject_v14.json`'s documented logic — `forgotten_ritual` and `second_wind` are dead without an exhaust enabler, `rupture` without a self-damage source; every other card has standalone baseline value):

```json
{
  "packages": [
    ["burning_pact"],
    ["drum_of_battle"],
    ["expect_a_fight"],
    ["forgotten_ritual", "burning_pact"],
    ["howl_from_beyond"],
    ["pyre"],
    ["rupture", "bloodletting"],
    ["second_wind", "burning_pact"],
    ["vicious"]
  ]
}
```

- [ ] **Step 1: Write the file** with the exact content above.
- [ ] **Step 2: Verify every id resolves** — run:

```powershell
.venv\Scripts\python.exe -c "
import json
from sts2_rl.cards.base import _CARD_CLASSES
ids = {i for p in json.load(open('runs/inject_v15_dead.json'))['packages'] for i in p}
missing = [i for i in ids if i not in _CARD_CLASSES]
print('missing:', missing); assert not missing"
```

Expected: `missing: []`
- [ ] **Step 3: Smoke the env path** — run:

```powershell
.venv\Scripts\python.exe -c "
from sts2_rl.run_env import STS2RunEnv
env = STS2RunEnv(deck_inject_midrun='runs/inject_v15_dead.json', deck_inject_midrun_prob=1.0)
env.reset(seed=1); print('ok, deck', len(env._run.deck))"
```

Expected: `ok, deck 10` (injection is mid-run only; reset deck unchanged).

---

### Task 5: `train_curriculum_v15.ps1` — s17 extension → gate → s18 mid-run inject

**Files:**
- Create: `train_curriculum_v15.ps1` (start from a copy of `train_curriculum_v14.ps1` — it carries the launch/eval/resume plumbing; apply the diffs below)

**Interfaces:**
- Consumes: `runs/sts2_run_torch_v14_s16.pt` (seed checkpoint), Task 3's CLI flags, Task 4's JSON.
- Produces: `runs/sts2_run_torch_v15_s17.pt`, `runs/sts2_run_torch_v15_s18.pt`; evals `runs/eval_v15_s17_asc{10,0}.*`, `runs/eval_v15_s18_asc{10,0}.*`.

**Stage table:**

| Stage | Steps | Seed | Delta vs v14 s16 | Purpose |
|---|---|---|---|---|
| s17 | 8M | `runs/sts2_run_torch_v14_s16.pt`, `--resume` (same-kind, NOT -WarmStart — a warm start would re-drop the run heads) | NONE (same `$runRewards`, same `--deck-inject runs/inject_v14.json` 0.5, same λ/aux/ent/lr) | harvest the unsaturated curve; clean A/B baseline |
| s18 | 8M | `runs/sts2_run_torch_v15_s17.pt`, `--resume`, `--critic-warmup 8` (env-distribution change re-prices V) | + `--deck-inject-midrun runs/inject_v15_dead.json --deck-inject-midrun-prob 0.05` | dead-9 play exposure (~1.5 injected packages per 30-floor run) |

- [ ] **Step 1: Copy `train_curriculum_v14.ps1` → `train_curriculum_v15.ps1`** and apply: rename every `v14_s16`/`s16` artifact name to `v15_s17`/`s17` for stage 1 and add a second stage block `v15_s18`/`s18` (same Invoke-Eval calls, 150 eps asc 10 + asc 0, same `-Resume` crash-recovery machinery). The seed line for s17:

```powershell
$seedCkpt = "runs\sts2_run_torch_v14_s16.pt"
```

s18's extra args, appended to the s17 arg array:

```powershell
$midrunInject = @("--deck-inject-midrun", "runs/inject_v15_dead.json",
                  "--deck-inject-midrun-prob", "0.05",
                  "--critic-warmup", "8")
```

- [ ] **Step 2: Add the between-stage gate** (same shape as v10's `Test-RestUpgradeGate`, reading the s17 asc-10 episodes CSV): abort with exit 3 (resumable) unless BOTH hold — total rest-upgrade share ≥ 0.15 AND mean floor ≥ 19.0. (Floor 19.0, not 20.1: the gate protects against collapse mid-script; the full ≥ 20.1 verdict belongs to the human-read run log, not an unattended abort.)
- [ ] **Step 3: Smoke test.** Run the script's `-Smoke` mode (v14 precedent): expect exit 0, log lines showing `resuming from runs\sts2_run_torch_v14_s16.pt` for s17 and the midrun flags present in s18's arg echo.
- [ ] **Step 4: Stage.** `git add train_curriculum_v15.ps1` (NO commit).

---

### Task 6: `v15-run-log.md` — gates, baselines, s19 contingency

**Files:**
- Create: `docs/superpowers/plans/v15-run-log.md`

**Content — the gate table (write it with these exact numbers):**

| Stage | Gate |
|---|---|
| s17 (150 eps, asc 10) | SURVIVAL: rest-upgrade share ≥ 0.15 (v14: 0.404); floor ≥ 20.1 SUSTAINED (v14: 20.86 — first-ever pass must not be a peak); truncations < 40/150 (v14: 13). asc 0: win ≥ 3.3% (v14: 3.33%), floor report vs 32.02 |
| s17 first-class report | **hp_lost/floor vs 7.94 (asc10) / 7.30 (asc0)** — this number IS the danger-zone position; the rest-economy question is closed or opened by it, not by rest shares alone. energy_unspent/turn vs 0.199/0.233 — a further rise makes energy the v16 headline. NEW: `rest_upgrades_hihp / rest_visits_hihp` (hi-HP upgrade share, threshold 0.65) — baseline-setting this generation, no gate |
| s18 (150 eps, asc 10) | same survival gates as s17; dead-9 movement: count of the 9 with take_rate > 0 (v14: 0/9) — ANY movement is signal; report per-card like the v14 analysis |
| s18 contingency | dead-9 fully unmoved after 8M → raise `--deck-inject-midrun-prob` to 0.15 (+4M, same stage pattern); do NOT reach for action-forcing |
| s19 (DECISION-GATED, not scheduled) | linear HP curve: `--hp-potential-low-share 0.35` (+8M from s18's ckpt, `--critic-warmup 8`, everything else unchanged). Launch ONLY if, after the SpireBot Smith fix is live-verified and s17/s18 are read, the SIM evals still show hi-HP heal preference (rest_upgrades_hihp share materially below the unconditional share) OR chip-damage sloppiness persists with hp_lost/floor flat. Gates if launched: floor and win survival as above; elite gap/ep ≤ 0.3 and hp_lost/floor not rising >10% (defend-spam/passivity check). Rationale: the 0.35 knee hard-codes a danger threshold the agent's own value function contradicts (behavioral crossover ~0.6, set by its bleed rate); linear shaping prices HP uniformly and lets the critic supply the danger structure — and taxes high-HP chip damage ~2×, pressuring the sloppiness directly |

Also record: rest-behavior numbers from ANY live SpireBot session are untrusted until Task 1's fix is live-verified (the Smith loop manufactured heal-heavy observations); sim evals are the only rest-economy evidence source this generation.

- [ ] **Step 1: Write the run log** with a Launch section (`.\train_curriculum_v15.ps1`, `-Resume` recovery, native PowerShell only), a Knobs/why table (one row per stage-delta above), the gate table, and a NEXT section (Perry: commit + launch; post-run: fill gates, then the v16 decision between potion-timing and energy-discipline per which report line moved).
- [ ] **Step 2: Stage.** `git add docs/superpowers/plans/v15-run-log.md` (NO commit).

---

### Task 7: Post-run handoff (documented in the run log, executed by Perry later)

No implementation now — write these as the run log's closing checklist:

- [ ] After s18 passes gates: re-export the winning checkpoint for SpireBot — `.venv\Scripts\python.exe -m sts2_rl.live.export_onnx runs\sts2_run_torch_v15_s18.pt --out runs\v15_s18_model.onnx` (parity gate must pass < 1e-4), back up `D:\...\mods\SpireBot\model\model.onnx` (`.bak_v14_s16` suffix), copy the new export over it, hash-verify. Contract is unchanged (schema 12) — no contract redeploy.
- [ ] The live obs-parity diff (`compare_obs` vs a fresh PassiveDump of a recorded replay) is STILL the open trust item for schema 12 — it rides the same showcase session as Task 1 Step 6.

---

## Self-Review

- **Spec coverage:** SpireBot Smith fix (Task 1 — the discussion's precondition for trusting any live rest observation); hi-HP rest metric (Task 2 — "measured gate rather than eyeball impression"); mid-run dead-card injection env-side (Tasks 3+4 — the ε-drafting rung reshaped to avoid off-policy data); s17 extension + s18 stage + between-stage gate (Task 5); hp_lost/floor promoted to first-class + linear-curve s19 as decision-gated contingency with its passivity gates (Task 6); model redeploy + obs-parity reminder (Task 7). The "resting refunds nothing" knob is deliberately ABSENT — the knee-cap already zeroes hi-HP heals; recorded in the run log rationale.
- **Placeholder scan:** Task 1 Steps 1/3 are research-conditional by necessity (live-only bug; two concrete coded hypotheses provided). Task 2 Step 1 and Task 3 Step 1 direct the implementer to mirror named existing harnesses rather than inventing fixtures — deliberate, with exact file/line anchors.
- **Type consistency:** `deck_inject_midrun`/`deck_inject_midrun_prob` naming is uniform across env kwargs, CLI flags, and the ps1; `rest_visits_hihp`/`rest_upgrades_hihp` uniform across env counters, info keys (`ep_` prefix), report fields, and CSV columns.
