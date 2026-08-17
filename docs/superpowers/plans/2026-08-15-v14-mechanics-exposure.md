# v14 Mechanics Exposure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/superpowers/specs/2026-08-15-v14-mechanics-exposure-design.md`: glow-gold + Move-prop block-preview obs fields (combat schema 7→8, run schema 11→12) with a lossless checkpoint migration for v13_s15, a `calc_block` hook + preview-fidelity verification sweep, the `--deck-inject` run-env flag, the SpireBot obs-writer port, and the s16 training script.

**Architecture:** Two new floats append to the 29-float combat hand-card row (`card_features`), flowing automatically into the entset encoder (its row width derives from `N_CARD_FEATURES`) and into SpireBot via the exported contract JSON. A new migration tool splices two zero input-columns into the saved hand-row projection weights so the migrated v13_s15 policy is output-identical. Deck injection copies the existing `deck_random_prob`/`_randomize_deck` reset-time pattern.

**Tech Stack:** Python 3 / PyTorch (sts2-rl, `.venv`), C# net9.0 Godot (SpireBot), PowerShell curriculum scripts.

## Global Constraints

- **Stage only, NEVER commit or push** — in sts2-rl and SpireBot, `git add` is the last step of every task; Perry commits. (Overrides this plan template's commit steps.)
- Test suite: `cd c:\Users\Perry\Desktop\sts2-rl; .venv\Scripts\python.exe -m pytest -q` — known-excluded/pre-existing failures: `test_train_io.py`, `test_live_onnx.py` (4 xfail baseline). Suite must be otherwise green at the end of every task.
- Default env bit-identical: every new knob/field defaults to today's behavior; the default-constructed env must draw ZERO extra RNG.
- Obs-parity rule: hand.f fields 0–28 and their semantics are untouched; new information goes ONLY in new fields f[29]/f[30]. Field 21 keeps `ValueProp.NONE` (89U 224-mismatch guard, `full_env.py:699-707`).
- Every game-behavior port cites the game `.cs` file+line (source tree: `c:\Users\Perry\Desktop\Slay the Spire 2\src`).
- Both schema constants move in the SAME task: `full_env.OBS_SCHEMA_VERSION` 7→8 AND `run_env.RUN_OBS_SCHEMA_VERSION` 11→12 (`test_run_obs_v4.py:222-249` guards this).
- Training/eval launches are Perry's, native PowerShell only (Git-Bash boundary hangs worker spawns). `-Smoke` verification is allowed.

**Task order:** 1 → 2 → 3 → 4 are sequential (hooks → obs → migration). 5 → 6 are independent of 1–4. 7 needs 3. 8 needs 4+5+6. 9 (run log) last.

---

### Task 1: `should_glow_gold` hook + Ironclad-reachable ports

**Files:**
- Modify: `sts2_rl/cards/base.py` (Card class, near the `base_damage` property at ~line 381)
- Modify: `sts2_rl/enchantments.py` (base Enchantment class)
- Modify: `sts2_rl/cards/pacts_end.py` (+ every Ironclad-reachable override found in Step 1)
- Test: `test/test_glow_gold.py` (new)

**Interfaces:**
- Produces: `Card.should_glow_gold(ctx: CombatCtx) -> bool` (public, consumed by Task 3's obs field), `Card._should_glow_gold_internal(ctx) -> bool` (per-card override point), `Enchantment.should_glow_gold(ctx, card) -> bool` (fallback, default False).

- [ ] **Step 1: Determine the port list.** The game has 17 `ShouldGlowGoldInternal` overrides (all in `src\Core\Models\Cards\`): BubbleBubble, Clash, DeathsDoor, Dismantle, Eidolon, EvilEye, Fetch, Flatten, ForgottenRitual, Ftl, GoForTheEyes, GrandFinale, HeavenlyDrill, Impatience, PactsEnd, Restlessness, Spite. Intersect with the Ironclad-reachable pools:

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -c "
from sts2_rl.cards.pool import IRONCLAD_POOL, COLORLESS_POOL, CURSE_POOL, STATUS_POOL
reachable = set(IRONCLAD_POOL) | set(COLORLESS_POOL) | set(CURSE_POOL) | set(STATUS_POOL)
cands = ['bubble_bubble','clash','deaths_door','dismantle','eidolon','evil_eye','fetch','flatten','forgotten_ritual','ftl','go_for_the_eyes','grand_finale','heavenly_drill','impatience','pacts_end','restlessness','spite']
print([c for c in cands if c in reachable])"
```

Record the resulting list (expect at least `pacts_end`, `forgotten_ritual`, `evil_eye`; possibly `clash`/`spite` — trust the command, not this guess). Also check the enchantment side (the game's `CardModel.ShouldGlowGold` falls back to `Enchantment?.ShouldGlowGold`, CardModel.cs:830-840):

```powershell
Select-String -Path "c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Models\Enchantments\*.cs" -Pattern "ShouldGlowGold" -List | ForEach-Object Filename
```

Any hit that is one of the 17 ported enchantments (see `sts2_rl/enchantments.py`) joins the port list.

- [ ] **Step 2: Write the failing tests** in `test/test_glow_gold.py`. One base-behavior test, one Pact's End test (the template for each additional port), one enchantment-fallback test:

```python
"""v14 glow-gold hook: mirrors CardModel.ShouldGlowGold (CardModel.cs:830-858)."""
from sts2_rl.cards import make_card
from test.helpers import start_simple_combat  # use the existing combat fixture
                                              # helper this suite uses (grep
                                              # test_previews.py for the real
                                              # name and copy its setup)

def test_default_card_never_glows():
    combat = start_simple_combat(deck=["strike"])
    card = make_card("strike")
    assert card.should_glow_gold(combat._ctx()) is False

def test_pacts_end_glows_at_three_exhausted():
    # PactsEnd.cs:21-23: glow == exhaust pile count >= Cards var (3)
    combat = start_simple_combat(deck=["pacts_end"])
    card = make_card("pacts_end")
    ctx = combat._ctx()
    combat.player.exhaust_pile[:] = [make_card("strike"), make_card("strike")]
    assert card.should_glow_gold(ctx) is False
    combat.player.exhaust_pile.append(make_card("strike"))
    assert card.should_glow_gold(ctx) is True
```

(Adapt the fixture call to the suite's actual combat-construction helper — `test_previews.py` shows the working pattern; do NOT invent a new fixture.)

- [ ] **Step 3: Run the tests, verify they fail** — `pytest test/test_glow_gold.py -v` → FAIL with `AttributeError: ... 'should_glow_gold'`.

- [ ] **Step 4: Implement the base hook** in `sts2_rl/cards/base.py`, next to the `base_damage`/`base_block` properties:

```python
def should_glow_gold(self, ctx) -> bool:
    """The card face's gold-glow signal — the game's 'condition armed'
    indicator (CardModel.ShouldGlowGold, CardModel.cs:830-840): the
    per-card internal check OR the enchantment's own glow."""
    if self._should_glow_gold_internal(ctx):
        return True
    ench = self.enchantment
    return ench.should_glow_gold(ctx, self) if ench is not None else False

def _should_glow_gold_internal(self, ctx) -> bool:
    """Per-card override point (CardModel.cs:858 default: False)."""
    return False
```

And in `sts2_rl/enchantments.py` on the base Enchantment class:

```python
def should_glow_gold(self, ctx, card) -> bool:
    """EnchantmentModel.ShouldGlowGold default (consulted as CardModel's
    fallback, CardModel.cs:834-837)."""
    return False
```

- [ ] **Step 5: Port each override from Step 1's list, 1:1 with citation.** Pact's End (`sts2_rl/cards/pacts_end.py`):

```python
def _should_glow_gold_internal(self, ctx) -> bool:
    # PactsEnd.cs:21-23: CanDealDamage = exhaust pile count >= Cards (3)
    return len(ctx.player.exhaust_pile) >= self._cards
```

For every other card on the list: read its `.cs` `ShouldGlowGoldInternal` expression, port the exact condition against sim state, cite file:line in the comment, and add a `test_<id>_glows_when_<condition>` test to `test/test_glow_gold.py` in the Step 2 shape (set up the condition false → assert False, make it true → assert True). Same for any enchantment override.

- [ ] **Step 6: Run the new tests, verify pass** — `pytest test/test_glow_gold.py -v` → all PASS.

- [ ] **Step 7: Full suite** — `.venv\Scripts\python.exe -m pytest -q` → green (baseline exclusions only).

- [ ] **Step 8: Stage** — `git add sts2_rl/cards/base.py sts2_rl/enchantments.py sts2_rl/cards/pacts_end.py <other ported files> test/test_glow_gold.py` (NO commit).

---

### Task 2: `calc_block` hook, `card_base_block` helper, preview-fidelity verification sweep

**Files:**
- Modify: `sts2_rl/previews.py` (new helper above `preview_card_block` at ~line 199; reroute `preview_card_block`)
- Modify: `sts2_rl/full_env.py:697-698` (base-block obs field routes through the helper)
- Test: `test/test_previews.py` (extend)
- Create: sweep verdict table in `docs/superpowers/plans/v14-run-log.md` (Task 9 creates the file; this task drafts the table in a scratch note it hands forward, or creates the run-log file early with just the table — creating it early is fine)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `previews.card_base_block(combat: CombatState, card: Card) -> int | None` (consumed by Task 3's field and by `preview_card_block`); the per-card hook convention `calc_block(ctx, target=None) -> int` (zero overrides today — see research note).

**Research note (established at plan time, verify in Step 5):** the game's computed-card-face pattern (`CalculatedDamageVar.WithMultiplier`) is used by exactly 7 Ironclad/colorless-reachable cards — AshenStrike, BodySlam, Bully, GoldAxe, MindBlast, PerfectedStrike, Rend — and ALL 7 already have `calc_damage` in the sim. No Ironclad/colorless-reachable card uses a computed block var (SecondWind.cs and TrueGrit.cs print static `BlockVar(N)`; their loops live in `OnPlay`). So this task adds the `calc_block` plumbing for symmetry (zero overrides), and the "sweep" is a recorded verification, not new ports.

- [ ] **Step 1: Write the failing test** in `test/test_previews.py`:

```python
def test_card_base_block_prefers_calc_block():
    # calc_block is the block analog of calc_damage (card_base_damage,
    # previews.py:168-180): preferred over the static declaration.
    from sts2_rl.previews import card_base_block
    combat = <same combat fixture the module already uses>
    card = make_card("iron_wave")           # any card with static base_block
    assert card_base_block(combat, card) == card.base_block
    card.calc_block = lambda ctx, target=None: 42   # stub hook
    assert card_base_block(combat, card) == 42

def test_preview_card_block_routes_through_base_helper():
    from sts2_rl.previews import preview_card_block
    combat = <fixture>
    card = make_card("iron_wave")
    card.calc_block = lambda ctx, target=None: 42
    # 42 then flows through the MOVE pipeline (dex 0 here -> unchanged)
    assert preview_card_block(combat, card) == 42
```

- [ ] **Step 2: Run, verify fail** — `pytest test/test_previews.py -k calc_block -v` → FAIL (`ImportError: card_base_block`).

- [ ] **Step 3: Implement** in `sts2_rl/previews.py`, mirroring `card_base_damage` (lines 168-180) exactly:

```python
def card_base_block(combat: CombatState, card: Card) -> int | None:
    """The card's printed block before modifiers.

    Prefers the card's calc_block(ctx, target) when it computes block from
    combat state (no Ironclad-reachable card does today — the hook exists
    for symmetry with calc_damage and for future characters); otherwise
    the declared base_block. None for cards that grant no block."""
    calc = getattr(card, "calc_block", None)
    if calc is not None:
        return calc(combat._ctx(), None)
    return card.base_block
```

Reroute `preview_card_block`: replace `base = card.base_block` (previews.py:218) with `base = card_base_block(combat, card)`. Reroute the obs base-block field: in `full_env.py:697-698`, replace `if card.base_block is not None: f[20] = _clip01(card.base_block / ABS_SCALE)` with:

```python
    base_blk = card_base_block(s, card)
    if base_blk is not None:
        f[20] = _clip01(base_blk / ABS_SCALE)
```

(`preview_card_block` at line 218 also needs `combat` — it already takes it as its first parameter, no signature change.)

- [ ] **Step 4: Run, verify pass** — `pytest test/test_previews.py -v` → PASS, including all pre-existing tests (rerouting must not change any current value: with no `calc_block` anywhere, `card_base_block` ≡ `card.base_block`).

- [ ] **Step 5: Execute the verification sweep and record it.** For each of the 7 `calc_damage` cards, diff the sim implementation against its `.cs` `WithMultiplier` lambda; for SecondWind/TrueGrit confirm static `BlockVar`; confirm no other `CalculatedDamageVar`/block-multiplier user is in `IRONCLAD_POOL`/`COLORLESS_POOL`:

```powershell
Select-String -Path "c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Models\Cards\*.cs" -Pattern "CalculatedDamageVar|WithMultiplier" -List | ForEach-Object Filename
```

Write the verdict table (card → sim file → game citation → verdict CONFIRMED-MATCHES / GAP-FIXED) into `docs/superpowers/plans/v14-run-log.md` under a `## §2b sweep table` heading (create the file with just this section; Task 9 fills the rest). Any GAP found: fix the sim card's `calc_damage` 1:1 and add a value test in `test/test_previews.py` before recording CONFIRMED.

- [ ] **Step 6: Full suite** — green.

- [ ] **Step 7: Stage** — `git add sts2_rl/previews.py sts2_rl/full_env.py test/test_previews.py docs/superpowers/plans/v14-run-log.md`.

---

### Task 3: Obs fields f[29]/f[30], `N_CARD_FEATURES` 29→31, schema bumps 7→8 and 11→12

**Files:**
- Modify: `sts2_rl/full_env.py` (`N_CARD_FEATURES` line 264, `OBS_SCHEMA_VERSION` line 147, `card_features` tail lines 713-724)
- Modify: `sts2_rl/run_env.py:191` (`RUN_OBS_SCHEMA_VERSION` 11→12)
- Modify: `OBS_SCHEMA.md` §5.2 (hand.f row: 10×29 → 10×31, document both fields)
- Modify (pin updates): `test/test_full_env.py:67` (`_SCHEMA_FOR_WIDTHS`), `test/test_run_obs_v4.py:222,249`, `test/test_run_env.py:66`, `test/test_obs_game_observable.py:54,222`, `test/test_live_contract.py:19-20`, `test/test_obs_pins.py` (numeric-index enumeration)
- Test: `test/test_obs_pins.py` (new field-value tests)

**Interfaces:**
- Consumes: `Card.should_glow_gold(ctx)` (Task 1), `previews.card_base_block` reroute (Task 2), `preview_card_block(s, card, props=ValueProp.MOVE)` (exists).
- Produces: hand.f layout `f[29]` = glow_gold flag, `f[30]` = Move-prop block preview `/ABS_SCALE`; `N_CARD_FEATURES == 31`; `OBS_SCHEMA_VERSION == 8`; `RUN_OBS_SCHEMA_VERSION == 12`. Everything downstream (write_rows n_float, entset row width via `entset_segment_plan`'s `n_float = f_width // cap`, contract export) tracks these constants automatically.

- [ ] **Step 1: Write the failing field-value tests** in `test/test_obs_pins.py`, following that file's existing `test_card_number_pins` pattern (reshape hand.f by `N_CARD_FEATURES`, index a known card's row):

```python
def test_glow_gold_field_pacts_end():
    # f[29]: 0 until 3 exhausted, then 1 (PactsEnd.cs:21-23 via Task 1 hook)
    <build combat with pacts_end in hand — same setup style as
     test_card_number_pins>
    row = obs_f_hand_row_for("pacts_end")
    assert row[29] == 0.0
    <exhaust 3 cards, rebuild obs>
    assert row[29] == 1.0

def test_block_preview_move_field_dexterity():
    # f[30]: Defend previews base+dex under the MOVE pipeline; field 20/21
    # stay at their old (dex-blind) values — the parity guard.
    <build combat with defend in hand, give player 2 dexterity>
    row = obs_f_hand_row_for("defend")
    assert row[20] == pytest.approx(5 / 100.0)   # base, unchanged
    assert row[21] == pytest.approx(5 / 100.0)   # ValueProp.NONE, unchanged
    assert row[30] == pytest.approx(7 / 100.0)   # 5 + 2 dex, MOVE pipeline
```

- [ ] **Step 2: Run, verify fail** — `pytest test/test_obs_pins.py -k "glow_gold or block_preview" -v` → FAIL (IndexError / wrong width).

- [ ] **Step 3: Implement.** In `full_env.py`: `N_CARD_FEATURES = 31` (line 264), `OBS_SCHEMA_VERSION = 8` (line 147). In `run_env.py:191`: `RUN_OBS_SCHEMA_VERSION = 12`. Append to `card_features` after the `f[28]` write (line 723):

```python
    # ── v14 fields (schema 8; OBS_SCHEMA.md §5.2) ─────────────────────
    # f[29]: the game's gold-glow "condition armed" signal
    # (CardModel.ShouldGlowGold) — the ONLY obs carrier for on_play-only
    # conditions like Pact's End; the parity-pinned damage/block fields
    # deliberately keep the card-face printed numbers.
    f[29] = 1.0 if card.should_glow_gold(s._ctx()) else 0.0
    # f[30]: the true block this card grants right now — the full MOVE
    # pipeline (Dexterity, Frail, enchantments, Fasten), unlike f[21]'s
    # ValueProp.NONE parity field.
    mv_block = preview_card_block(s, card, props=ValueProp.MOVE)
    f[30] = _clip01(mv_block / ABS_SCALE) if mv_block is not None else 0.0
    return f
```

(`card_features` receives the combat state as `s` — match the function's actual parameter name when editing; `ValueProp` import already exists in full_env.py for the field-21 call.)

- [ ] **Step 4: Update every pin, using printed-actual values.** Run `pytest test/test_full_env.py test/test_run_obs_v4.py test/test_run_env.py test/test_obs_game_observable.py test/test_live_contract.py -v` and read the failures. Expected new values: combat `(f_dim, i_dim)` = `(1697, 606)` for schema 8 (old 1677 + MAX_HAND·2 = 20), run pin `(12, 4735, 1469)` (old 4715 + 20 — the run layout embeds the combat hand block once). **If the printed actuals differ from these predictions, trust the printed actuals** (the run layout may embed hand more than once) — the pins exist to be exact, not aspirational. Update `_SCHEMA_FOR_WIDTHS` to `{(1697, 606): 8}` (or actual), the `RUN_OBS_SCHEMA_VERSION == 12` asserts, and `test_obs_pins.py`'s numeric-index enumeration (`test_numeric_indices_cover_the_preview_segments_and_exclude_categorical_ones`): f[30] joins the numeric/preview set; f[29] is a flag (match how f[25]-f[27] flags are classified there).

- [ ] **Step 5: Update `OBS_SCHEMA.md` §5.2** hand.f row: width 10×31; append field docs: `29 glow_gold (CardModel.ShouldGlowGold, 0/1)`, `30 block_preview_move (preview_card_block ValueProp.MOVE, /ABS_SCALE; 0 when the card grants no block)`.

- [ ] **Step 6: Full suite** — `.venv\Scripts\python.exe -m pytest -q` → green. This includes `test_combat_obs_v4.py` and `test_entset_rows.py`, which must pass WITHOUT edits (their derivations track `N_CARD_FEATURES`); if either needs a literal updated, update it, but investigate first — a failure there beyond a width literal means a real regression.

- [ ] **Step 7: Stage** — `git add sts2_rl/full_env.py sts2_rl/run_env.py OBS_SCHEMA.md test/test_full_env.py test/test_run_obs_v4.py test/test_run_env.py test/test_obs_game_observable.py test/test_live_contract.py test/test_obs_pins.py`.

---

### Task 4: Lossless checkpoint migration (v13_s15 → schema 12)

**Files:**
- Create: `tools/migrate_handrow_v14.py`
- Test: `test/test_migrate_handrow_v14.py` (new)

**Interfaces:**
- Consumes: schema-12 code from Task 3 (`load_agent`/model construction now builds 31-wide hand rows).
- Produces: `runs/sts2_run_torch_v13_s15_schema12.pt` — the s16 seed (Task 8). CLI: `.venv\Scripts\python.exe tools\migrate_handrow_v14.py <in.pt> <out.pt>`.

**Context the implementer needs:** the historical v3→v4 migration in `sts2_rl/checkpoints.py:340-429` is STUBBED (every path raises SystemExit) — do not call it; this tool is a fresh, narrower implementation. The entset arch builds each row block's projection as `Linear(row_in, block_dim)` where `row_in = sum(embed dims for the block's vocabs) + n_float` (`models.py:552-556`, plan derivation at `models.py:443-502`). The hand block's `n_float` goes 29→31, so the saved projection weight `[block_dim, row_in_old]` needs 2 zero columns inserted at the positions of the two new floats. Adam state is positional (`optim.state` keyed by param index in `named_parameters()` order); NO parameters are added or reordered by this change, so indices are stable — only shapes change.

- [ ] **Step 1: Confirm the concat order** of embeds vs floats in the entset row projection: read `_EntsetEncoder.forward` in `sts2_rl/models.py` and note whether a row is `cat([embeds..., floats])` or `cat([floats, embeds...])`. If floats are the TAIL (expected), the two new columns append at the END of the weight's input dim; if floats lead, they insert at positions `[n_float_old, n_float_old+2)` offset by nothing. Record which in the tool's docstring. **Do not guess — read the forward.** Note: with per-row floats appended per row and cap>1 rows flattened, confirm whether the projection consumes ONE row (row_in per row) — it does (`write_rows` rows are projected row-wise) — so the splice is per-row-width, applied once to the single shared `Linear`.

- [ ] **Step 2: Write the failing tests** in `test/test_migrate_handrow_v14.py`:

```python
"""Migration = output-identical: spliced zero columns make the new model
ignore f[29]/f[30], so logits match the pre-bump policy exactly."""
import torch
from tools.migrate_handrow_v14 import splice_zero_columns, migrate

def test_splice_zero_columns_positions_and_values():
    w = torch.arange(12.0).reshape(3, 4)          # [out=3, in=4]
    out = splice_zero_columns(w, insert_at=4, width=2)
    assert out.shape == (3, 6)
    assert torch.equal(out[:, :4], w)
    assert torch.equal(out[:, 4:], torch.zeros(3, 2))

def test_migrated_model_ignores_new_fields(tmp_path):
    # Build a fresh schema-12 entset agent, save it, hand-shrink its hand
    # projection back to the 29-wide shape (the "old checkpoint"), migrate,
    # reload, and assert logits are invariant to f[29]/f[30] noise.
    <construct a small run-scale entset agent via the same helper
     test_entset_rows.py uses; save checkpoint to tmp_path/'old.pt' after
     slicing the hand-block projection weight (and its absence from optim
     is fine for the test) down by the 2 tail columns and stamping
     obs_schema = 11>
    migrate(tmp_path / 'old.pt', tmp_path / 'new.pt')
    ck = torch.load(tmp_path / 'new.pt', map_location='cpu', weights_only=False)
    assert ck['obs_schema'] == 12
    <load agent from new.pt; build one run obs; copy it and randomize the
     f[29]/f[30] slots of every hand row in the copy; assert
     torch.equal(logits(obs), logits(obs_randomized))>
```

(The angle-bracketed setup must use the repo's existing agent-construction and obs-building helpers — `test_entset_rows.py` and `test_train_io.py` show model construction; `checkpoints.py` shows the checkpoint dict shape saved by `train_torch.py`: keys `model`, `optim`, `iteration`, `global_step`, `obs_dim`, `n_actions`, `hidden`, `arch`, `head_version`, `shared_encoder`, `obs_schema`, `env_kind`, `ascension`, `n_envs`, `n_steps`, `start_snapshots`.)

- [ ] **Step 3: Run, verify fail** — `pytest test/test_migrate_handrow_v14.py -v` → FAIL (no module).

- [ ] **Step 4: Implement `tools/migrate_handrow_v14.py`:**

```python
"""One-shot lossless migration: run-scale entset checkpoint, obs schema
11 -> 12 (hand.f 29 -> 31 floats/row, v14 glow_gold + block_preview_move).

The two new floats are at the TAIL of each hand row's float block
(<confirmed against _EntsetEncoder.forward in Step 1 — state the actual
order found>), so the hand-row projection Linear gains 2 zero input
columns at <the position found>. Zero columns = the new inputs contribute
nothing: the migrated policy's outputs are bit-identical to the source
checkpoint's. Adam moments are spliced identically (positional state,
param order unchanged by this migration).
"""
import argparse, sys
import torch

def splice_zero_columns(mat: torch.Tensor, insert_at: int, width: int) -> torch.Tensor:
    return torch.cat(
        [mat[:, :insert_at], mat.new_zeros(mat.shape[0], width), mat[:, insert_at:]],
        dim=1)

def migrate(src, dst) -> None:
    ck = torch.load(src, map_location="cpu", weights_only=False)
    if ck.get("obs_schema") != 11:
        sys.exit(f"expected obs_schema 11, got {ck.get('obs_schema')}")
    if ck.get("arch") != "entset" or ck.get("env_kind") != "run":
        sys.exit("this tool migrates run-scale entset checkpoints only")
    model = ck["model"]
    # <Step 5 discovers the exact hand-projection key names; hardcode the
    #  discovered names here as a tuple, e.g.:>
    hand_keys = (<discovered weight key(s) for the hand row projection —
                  actor-side, and critic-side if shared_encoder is False>)
    param_names = <the model's named_parameters() order — reconstruct by
                   building a schema-12 agent from ck's hyperparams via the
                   same constructor train_torch uses, then
                   [n for n, _ in agent.named_parameters()]>
    for key in hand_keys:
        w = model[key]
        model[key] = splice_zero_columns(w, insert_at=<from Step 1>, width=2)
        pstate = ck.get("optim", {}).get("state", {}).get(param_names.index(key))
        if pstate is not None:
            for moment in ("exp_avg", "exp_avg_sq"):
                if moment in pstate:
                    pstate[moment] = splice_zero_columns(
                        pstate[moment], insert_at=<from Step 1>, width=2)
    ck["obs_schema"] = 12
    torch.save(ck, dst)
    print(f"migrated {src} -> {dst} (obs_schema 12, keys: {list(hand_keys)})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    a = ap.parse_args()
    migrate(a.src, a.dst)
```

- [ ] **Step 5: Discover the real key names/positions.** List `[k for k in ck['model'] if 'hand' in k]` on `runs/sts2_run_torch_v13_s15.pt` and identify the hand row-projection weight(s) (bias needs no splice — output dim unchanged). The checkpoint has `shared_encoder: True` — verify whether that means one encoder serves actor+critic (then ONE weight to splice) by checking for a second `critic`-prefixed hand block key. Replace the placeholders in the tool; also fill the insert position from Step 1.

- [ ] **Step 6: Run tests, verify pass** — `pytest test/test_migrate_handrow_v14.py -v` → PASS.

- [ ] **Step 7: Migrate the real checkpoint and verify:**

```powershell
.venv\Scripts\python.exe tools\migrate_handrow_v14.py runs\sts2_run_torch_v13_s15.pt runs\sts2_run_torch_v13_s15_schema12.pt
.venv\Scripts\python.exe eval.py runs\sts2_run_torch_v13_s15_schema12.pt --env run --episodes 5 --ascension 10 --csv runs\eval_v14_migration_smoke
```

Expected: eval runs to completion (5 episodes, no shape errors). Floors will differ from v13's eval only by episode-seed variance, not systematically.

- [ ] **Step 8: Full suite green, then stage** — `git add tools/migrate_handrow_v14.py test/test_migrate_handrow_v14.py`. (`runs/*.pt` is not tracked.)

---

### Task 5: `--deck-inject` / `--deck-inject-prob` env flag

**Files:**
- Modify: `sts2_rl/run_env.py` (`__init__` kwargs at ~line 627-660; reset hook after the `deck_random_prob` block at line 838; new `_inject_deck` next to `_randomize_deck` at ~line 919)
- Modify: `sts2_rl/vec_env.py` (EnvSpec fields at ~line 54-102; `build_env` passthrough at ~line 127)
- Modify: `train_torch.py` (argparse near `--deck-random-prob`; the run-only guard at lines 386-400; `env_spec()` at ~line 519)
- Test: `test/test_v14_deck_inject.py` (new)

**Interfaces:**
- Consumes: `make_card` (`sts2_rl/cards/base.py:53`), the `self._rng` episode RNG (`run_env.py:764,831`).
- Produces: `STS2RunEnv(deck_inject: str | None = None, deck_inject_prob: float = 0.0)`; JSON format `{"packages": [["rupture", "bloodletting"], ["thunderclap"], ...]}` (lowercase card ids); EnvSpec fields `deck_inject: str | None = None`, `deck_inject_prob: float = 0.0`; CLI `--deck-inject <path>` + `--deck-inject-prob <float>`.

- [ ] **Step 1: Write the failing tests** in `test/test_v14_deck_inject.py` (mirror `test/test_v10_lowshare.py`'s three-test structure, plus behavior):

```python
import json, random
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.vec_env import EnvSpec, build_env

def _pkg_file(tmp_path, packages):
    p = tmp_path / "inject.json"
    p.write_text(json.dumps({"packages": packages}))
    return str(p)

def test_default_bit_identical():
    env = build_env(EnvSpec(kind="run"))
    assert env._deck_inject_packages is None
    assert env._deck_inject_prob == 0.0

def test_envspec_threads_to_env(tmp_path):
    f = _pkg_file(tmp_path, [["thunderclap"]])
    env = build_env(EnvSpec(kind="run", deck_inject=f, deck_inject_prob=0.5))
    assert env._deck_inject_packages == [["thunderclap"]]
    assert env._deck_inject_prob == 0.5

def test_prob_one_injects_whole_package(tmp_path):
    f = _pkg_file(tmp_path, [["rupture", "bloodletting"]])
    env = STS2RunEnv(deck_inject=f, deck_inject_prob=1.0)
    env.reset(seed=7)
    ids = [c.id for c in env._run.deck]
    assert ids.count("rupture") == 1 and ids.count("bloodletting") == 1
    assert len(ids) == 10 + 2          # starter deck + the package

def test_prob_zero_never_injects(tmp_path):
    f = _pkg_file(tmp_path, [["rupture"]])
    env = STS2RunEnv(deck_inject=f, deck_inject_prob=0.0)
    env.reset(seed=7)
    assert all(c.id != "rupture" for c in env._run.deck)

def test_cli_threads_to_envspec(tmp_path):
    import train_torch
    f = _pkg_file(tmp_path, [["thunderclap"]])
    ns = <argparse.Namespace built the way test_v10_lowshare.py's third
         test builds one, with deck_inject=f, deck_inject_prob=0.5>
    spec = train_torch.env_spec(ns)
    assert spec.deck_inject == f and spec.deck_inject_prob == 0.5
```

(Starter deck size: assert against `len(build_starting_deck(...))` rather than the literal 10 if the Ironclad starter isn't exactly 10 — check `sts2_rl/run.py:118` while writing the test.)

- [ ] **Step 2: Run, verify fail** — `pytest test/test_v14_deck_inject.py -v` → FAIL (unexpected kwarg).

- [ ] **Step 3: Implement the env side** in `run_env.py`. `__init__` (after `deck_random_cards`):

```python
        deck_inject: str | None = None,
        deck_inject_prob: float = 0.0,
```

Body: load once at construction (fail fast on a bad path/id, not mid-training):

```python
        self._deck_inject_prob = deck_inject_prob
        self._deck_inject_packages: list[list[str]] | None = None
        if deck_inject is not None:
            import json
            with open(deck_inject) as fh:
                pkgs = json.load(fh)["packages"]
            from .cards import make_card
            for pkg in pkgs:
                for cid in pkg:
                    make_card(cid)      # KeyError now, not at episode 40k
            self._deck_inject_packages = pkgs
```

Reset hook — immediately AFTER the `deck_random_prob` block (`run_env.py:838-839`), same zero-draw short-circuit contract (the comment at 834-837 applies to this block too):

```python
        if (self._deck_inject_packages is not None
                and self._deck_inject_prob > 0.0
                and self._rng.random() < self._deck_inject_prob):
            self._inject_deck(self._run)
```

New method next to `_randomize_deck` (line ~919):

```python
    def _inject_deck(self, run: RunState) -> None:
        """v14: append one inject package (1-3 card ids) to the starting
        deck — plain append, no hooks, same as _randomize_deck. Packages,
        not single cards: a lone synergy card (Pact's End with no exhaust
        engine) would teach the card is dead (spec §3)."""
        from .cards import make_card
        pkg = self._rng.choice(self._deck_inject_packages)
        for cid in pkg:
            run.deck.append(make_card(cid))
```

- [ ] **Step 4: Implement the threading.** `vec_env.py` EnvSpec: `deck_inject: str | None = None` and `deck_inject_prob: float = 0.0`; `build_env`'s kwargs dict: `deck_inject=spec.deck_inject, deck_inject_prob=spec.deck_inject_prob,`. `train_torch.py`: argparse next to `--deck-random-prob`:

```python
ap.add_argument("--deck-inject", type=str, default=None,
                help="v14: JSON of card-id packages appended to the "
                     "starting deck with --deck-inject-prob (spec "
                     "2026-08-15-v14-mechanics-exposure-design.md)")
ap.add_argument("--deck-inject-prob", type=float, default=0.0)
```

Add `args.deck_inject or args.deck_inject_prob` to the run-only guard condition (train_torch.py:386-400) and both flag names to its message string. `env_spec()`: `deck_inject=getattr(args, "deck_inject", None), deck_inject_prob=getattr(args, "deck_inject_prob", 0.0),`.

- [ ] **Step 5: Run, verify pass** — `pytest test/test_v14_deck_inject.py -v` → PASS.

- [ ] **Step 6: Full suite green** (eval.py needs no change — `make_run_env` passes only `acts`/`ascension`, so evals are clean by construction).

- [ ] **Step 7: Stage** — `git add sts2_rl/run_env.py sts2_rl/vec_env.py train_torch.py test/test_v14_deck_inject.py`.

---

### Task 6: Generate `runs/inject_v14.json`

**Files:**
- Create: `runs/inject_v14.json` (gitignored under runs/ — also copy the generator command into `docs/superpowers/plans/v14-run-log.md` so it is reproducible, per the v11 corpus precedent)

**Interfaces:**
- Consumes: `runs/eval_v13_s15_asc10.cards.csv` (columns `policy,card,offered,taken,take_rate`; `card` is the CLASS name, e.g. `RuptureCard`), the card registry (`_CARD_CLASSES` in `sts2_rl/cards/base.py` maps lowercase id → class).
- Produces: the file Task 8's script passes to `--deck-inject`.

- [ ] **Step 1: Generate the base list** (threshold from the approved spec: `take_rate < 0.20`, `offered >= 20`; class name → id via the registry reverse map):

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

Expect ~30 ids (24 were under 5%; <20% adds more). If any class name misses in `cls2id`, resolve it by hand against `sts2_rl/cards/` before continuing — do not silently drop it.

- [ ] **Step 2: Build the package table.** Start from the printed ids: every id becomes a 1-card package EXCEPT the conditional/synergy cards, which get the spec §3 support packages. Apply this table (extend it with the same logic for any other conditional card that showed up in Step 1 — the §2b sweep table from Task 2 and each card's docstring say what it needs):

| Card | Package |
|---|---|
| `pacts_end` | `["pacts_end", "true_grit", "second_wind"]` |
| `rupture` | `["rupture", "bloodletting"]` |
| `body_slam` | `["body_slam", "iron_wave"]` |
| `second_wind` | `["second_wind", "burning_pact"]` |
| `true_grit` | `["true_grit", "burning_pact"]` |
| `burning_pact` | `["burning_pact", "true_grit"]` |
| `bloodletting` | `["bloodletting", "rupture"]` |
| `whirlwind` | `["whirlwind"]` (energy is generic) |
| `havoc` | `["havoc"]` |

Every package id must exist in the registry (Task 5's constructor check enforces this at env build). Write `runs/inject_v14.json` as `{"packages": [[...], ...]}`.

- [ ] **Step 3: Verify the file loads** through the real env path:

```powershell
.venv\Scripts\python.exe -c "
from sts2_rl.run_env import STS2RunEnv
env = STS2RunEnv(deck_inject='runs/inject_v14.json', deck_inject_prob=1.0)
env.reset(seed=1)
print(len(env._run.deck), [c.id for c in env._run.deck])"
```

Expected: prints a starter deck plus one package's cards, no exception.

- [ ] **Step 4: Record the generator command + final package list** in `docs/superpowers/plans/v14-run-log.md` under `## inject_v14.json provenance`, then `git add docs/superpowers/plans/v14-run-log.md` (the JSON itself is gitignored).

---

### Task 7: SpireBot obs-writer port + contract + ONNX export gate

**Files:**
- Modify: `c:\Users\Perry\Desktop\SpireBot\SpireBotCode\Obs\CombatObsWriter.cs` (`NCardFeatures` line 60; `WriteCardFeatures` lines 455-603)
- Regenerate: `contract.json` via `sts2_rl.live.export_contract` (wherever the repo's live docs say the deployed copy lives — check `sts2_rl/live/contract.py`'s docstring)

**Interfaces:**
- Consumes: Task 3's schema (combat 8 / run 12) via the exported contract; the game's public `CardModel.ShouldGlowGold` (CardModel.cs:830) and `Hook.ModifyBlock` (the field-21 call at CombatObsWriter.cs:541-556 is the template).
- Produces: a C# writer emitting 31-float hand rows matching `card_features` exactly.

- [ ] **Step 1: Determine the C# Move prop.** Sim f[30] runs `preview_card_block(props=ValueProp.MOVE)`. Open `sts2_rl/valueprops.py` and find which game enum member `MOVE` mirrors (the file documents the mapping); confirm against the game's `Hook.ModifyBlock` callers (e.g. `BlockCmd`) which prop a real powered move-block application passes. Record it — that exact prop replaces `default` in the new call.

- [ ] **Step 2: Bump `NCardFeatures` 29→31** (CombatObsWriter.cs:60) and append the two writes at the end of `WriteCardFeatures` (after `S(28, ...)`):

```csharp
// v14 (schema 8): the card face's gold-glow condition signal — sim f[29].
S(29, card.ShouldGlowGold ? 1f : 0f);
// v14 (schema 8): true block under the powered/move pipeline (Dexterity,
// Frail, Fasten) — sim f[30] (preview_card_block ValueProp.MOVE). The
// field-21 call above keeps default(ValueProp) — parity-pinned.
decimal mvBlock = Hook.ModifyBlock(combatState, player.Creature, bb, <Move prop from Step 1>, card, null, out _);
S(30, bb > 0m ? Clip01((float)mvBlock / AbsScale) : 0f);
```

Match the surrounding code's actual local names (`bb`, `combatState`, `player`) — copy the field-21 block at lines 541-556 and change only the prop and index. Sim parity detail: sim f[30] is 0.0 when `card_base_block` is None (no block card); the C# guard `bb > 0m` must mirror however the existing field-20/21 code distinguishes "no block var" — reuse its exact condition, not a new one.

- [ ] **Step 3: Regenerate the contract** so `combat.hand.f` width and both schema stamps flow to C#:

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -m sts2_rl.live.export_contract <args per the module's docstring>
```

Verify the emitted JSON has `combat_obs_schema: 8`, `run_obs_schema: 12`, and the `combat.hand.f` width grew by `MAX_HAND * 2`. Deploy it wherever SpireBot loads it from (per `Contract.cs` / the Task-18 setup notes in `docs/`).

- [ ] **Step 4: Build SpireBot** — `cd C:/Users/Perry/Desktop/SpireBot; dotnet build` → `Build succeeded`, 0 errors, only the 1 pre-existing `CS8602` warning. (`local.props` must point at the D:-drive game install — it is machine-local and already set up; if the build fails on missing sts2.dll, that's the local.props path, not this change.)

- [ ] **Step 5: Export + parity-gate the migrated checkpoint:**

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -m sts2_rl.live.export_onnx runs\sts2_run_torch_v13_s15_schema12.pt --out runs\v14_s16_seed.onnx
```

Expected: export succeeds and the script's built-in torch-vs-onnxruntime gate passes (32 samples, max|Δ| < 1e-4). This proves the schema-12 export path end-to-end; the full live obs-parity diff (`compare_obs.py` against a fresh game dump) happens at Perry's next live-showcase session, not in this task — note that handoff in the run log.

- [ ] **Step 6: Stage (SpireBot repo)** — `cd C:/Users/Perry/Desktop/SpireBot; git add SpireBotCode/Obs/CombatObsWriter.cs` plus the deployed contract file if it is repo-tracked.

---

### Task 8: `train_curriculum_v14.ps1`

**Files:**
- Create: `train_curriculum_v14.ps1` (copy `train_curriculum_v12.ps1` and edit — the helpers `Invoke-Phase`/`Get-CkptStep`/`Invoke-Stage`/`Invoke-Eval` stay byte-identical)

**Interfaces:**
- Consumes: `runs/sts2_run_torch_v13_s15_schema12.pt` (Task 4), `runs/inject_v14.json` (Task 6), `--deck-inject`/`--deck-inject-prob` (Task 5).
- Produces: stage s16 checkpoint `runs/sts2_run_torch_v14_s16.pt` + auto-evals `runs/eval_v14_s16_asc{10,0}.*`.

- [ ] **Step 1: Copy and edit.** From the v12 script change ONLY: header comment (v14 story, spec pointer); `$Tag = "v14"`; `$SeedCkpt = "runs/sts2_run_torch_v13_s15_schema12.pt"`; `$S14Steps` → `$S16Steps = 8000000` (rename the param and the `$ckpt` key 14→16, stage name `s16-run-asc10-inject`); `--reward-elite` **"2"** in `$runRewards` (v13's value — Perry's hand-launch lowered it from 3 and v13 is the reference policy; every other reward verbatim from the v12 script incl. `--reward-elite-attempt 1`); append to the stage args:

```powershell
"--deck-inject", "runs/inject_v14.json", "--deck-inject-prob", "0.5"
```

Keep: `--critic-warmup 8`, `-EntCoef 0.01` flat, lr 3e-4, `$longHorizon` (λ0.98 + aux 0.25), `--resume` handoff semantics (NO `-WarmStart` — the run heads carry the recovered rest-share behavior), eval invocations at 150 eps asc-10 + asc-0 with CLEAN env (Invoke-Eval passes no inject flags — true by construction, verify nothing was added).

- [ ] **Step 2: Guard the seed.** The copied script already exits if `$SeedCkpt` is missing; additionally, since an unmigrated seed would crash 8M steps in confusingly, add after the seed existence check:

```powershell
$schema = & $py -c "import sys, torch; print(torch.load(sys.argv[1], map_location='cpu', weights_only=False).get('obs_schema'))" (Join-Path $root $SeedCkpt)
if (($schema | Select-Object -Last 1).Trim() -ne "12") {
    Write-Host "SeedCkpt is not schema 12 - run tools\migrate_handrow_v14.py first." -ForegroundColor Red
    exit 1
}
```

- [ ] **Step 3: Smoke test** — `.\train_curriculum_v14.ps1 -Smoke` (65536 steps, scratch tag). Expected: exit 0, the log shows `seeding from runs/sts2_run_torch_v13_s15_schema12.pt`, a `critic warmup` line, and nonzero `aux=` in the training rows. Delete `runs/*v14smoke*` afterwards.

- [ ] **Step 4: Full suite still green, then stage** — `git add train_curriculum_v14.ps1`.

---

### Task 9: `v14-run-log.md` gates + launch handoff

**Files:**
- Modify: `docs/superpowers/plans/v14-run-log.md` (created by Tasks 2/6 with the sweep + provenance sections; add the header, knob table, and gate table)

- [ ] **Step 1: Write the run log** in the house shape (see `v12-run-log.md`): launch block (`pytest -q` green first, then `.\train_curriculum_v14.ps1`, `-Resume` for crash recovery, native PowerShell), knob/why table (schema-12 seed via migration tool; inject 0.5 × `inject_v14.json`; elite 2 = v13's reference value; critic-warmup 8 for the new start distribution), and this gate table:

| Stage | Gate |
|---|---|
| s16 (150 eps, asc 10) | rest-upgrade share ≥ 0.15 SURVIVES (v13 s15: 0.263); floor ≥ 20.1 (v13: 19.41 — the still-open gate); truncations < 40/150; energy report vs 0.141 |
| s16 (150 eps, asc 0) | win ≥ 3.3% sustained (v13: 3.33%); floor report vs 32.36 (all-time high — a drop below ~30 means injection is taxing capability) |
| draft diversity (asc 10 cards.csv) | REPORT-ONLY this generation: count of cards (offered ≥ 20) with take_rate < 0.05 — v13: 24/59. Expect play-skill-before-pickrate (spec §3): unchanged count is NOT failure; a falling count is signal |
| elite diving | report: elites_fought − elites gap + losing-eps hp_ratio vs overall (v13: 0.25/ep, not HP-concentrated) |
| contingency | <5% count unmoved after s16 → ε-forced drafting flag (spec ladder); rest share < 0.15 → treat as v12-style transient ONLY if the train curve is still climbing, else revisit |

- [ ] **Step 2: Stage** — `git add docs/superpowers/plans/v14-run-log.md`. **NEXT (Perry):** launch `.\train_curriculum_v14.ps1`; the live obs-parity diff (compare_obs vs a fresh game dump with the new SpireBot build) rides the next showcase session.

---

## Self-review notes (already applied)

- Spec §2b's "port gaps" resolved to a verification sweep: research established all 7 game-side computed-damage cards already carry `calc_damage`, and no Ironclad-reachable card computes block on its face — recorded in Task 2 rather than phantom porting tasks.
- Commit steps replaced with stage-only steps throughout (standing sts2 rule).
- The two schema constants and the ~8 pin-test files move inside one task (Task 3) — the `test_run_obs_v4.py` lockstep warning.
- Task 4's migration must NOT reuse `checkpoints.migrate_checkpoint` (stubbed dead code); placeholders in its code are discovery steps (key names, concat order) with explicit instructions, not TBDs.
