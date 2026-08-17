# v14: Card-mechanics exposure — truthful previews + deck injection — design

**Date:** 2026-08-15
**Status:** approved by Perry 2026-08-15 (all four open questions resolved:
inject threshold 0.20, prob 0.5, s16 = 8M, glow sweep Ironclad-reachable
only)
**Context:** v13 s15 is the best model yet (asc-0 win 3.33% gate met, asc-0
floor 32.36 all-time high, rest share 0.263 recovered) but the asc-10 eval's
`cards.csv` shows draft collapse: 24 of 59 cards (offered ≥20×) taken <5%,
12 at exactly 0 (Blood Wall, True Grit, Havoc, Bloodletting, Body Slam,
Rupture, Whirlwind, Second Wind, …) — every one a synergy/conditional card
whose value only exists in decks the policy never builds. Two causes
addressed here: (a) the obs misrepresents conditional cards, (b) the policy
gets zero in-combat reps with cards it never drafts.

## Problem detail (verified against source)

- **Conditional cards lie in the obs.** `preview_card_damage` uses
  `calc_damage` when a card has one (Body Slam, Perfected Strike — truthful)
  else printed base damage. Pact's End's condition lives only in `on_play`
  (`cards/pacts_end.py:39`): the obs shows 17-to-all even when the play
  would do NOTHING. The game itself signals the condition to the player via
  the gold glow — `PactsEnd.cs:21 ShouldGlowGoldInternal => CanDealDamage`
  — and our obs drops that signal entirely.
- **Block previews drop Dexterity/Frail/Fasten by design.** `hand.f`'s
  effective-block field passes `ValueProp.NONE` (`full_env.py:708`) for
  byte-parity with the game's DecisionDumper (CombatObsWriter.cs:470);
  Move-gated modifiers are no-ops there. That field is parity-pinned
  (89U 224-mismatch regression guard) and MUST NOT change — but the model
  currently has to recompose block = base + dex + Fasten from three
  separate obs pieces. There is no per-card `calc_block`.
- **Zero-pickrate cards get zero play experience** — the draft
  chicken-and-egg: never drafted → never played → value estimate never
  updates → never drafted.

## Components

### 1. Glow-gold bit on hand rows (conditional-card signal)

- New hand-row float `glow_gold`: 1.0 iff the card's condition-met signal
  is on, mirroring the game's `ShouldGlowGoldInternal` per card.
- Implementation: `Card.should_glow_gold` property, default `False`
  (base-class parity: `ShouldGlowGoldInternal`'s default). Sweep the game
  source for `ShouldGlowGoldInternal` overrides among Ironclad-reachable
  cards and port each 1:1 (Pact's End: `len(exhaust_pile) >= self._cards`).
  Sweep command + card list recorded in v14-run-log.md.
- Deliberately NOT a `calc_damage` returning 0: the game's dumper prints
  17 for a dead Pact's End, so zeroing the base-damage field would violate
  obs parity. The glow bit adds a real game-visible signal instead of
  editing a parity-pinned one.

### 2. Truthful block preview (new field + `calc_block` hook, schema bump)

- New hand-row float `block_preview_move` =
  `preview_card_block(s, card, props=ValueProp.MOVE)` — the full pipeline:
  Dexterity, Frail, enchantments, Fasten. The function already exists and
  is probe/test-covered; this only writes it into the obs.
- New per-card hook `calc_block(ctx) -> int | None`, the exact analog of
  `calc_damage`: a new `card_base_block(combat, card)` helper prefers it
  over the static `base_block` declaration (mirroring
  `previews.card_base_damage`), and `preview_card_block` +
  `full_env.py`'s base-block field route through the helper. Cards whose
  block the game computes from combat state (e.g. Second Wind's
  per-non-attack-card block) currently preview None/static — after this
  they preview what the game's own card face shows.
- Existing field 21 (`ValueProp.NONE`) stays byte-identical — SpireBot
  live-obs parity depends on it.
- Both new floats (§1+§2) widen `hand` rows → **obs_schema 11→12** with a
  lossless checkpoint migration (v3→v4 precedent): new encoder input
  columns zero-initialized, so the migrated v13_s15 policy's outputs are
  bit-identical pre-training. Adam state is positional — migration must
  patch optimizer param shapes the same way the v3→v4 migration did.

### 2b. Preview-fidelity sweep: every card through `calc_damage`/`calc_block`

Perry's extension (2026-08-15): audit every Ironclad-reachable card
against the game's own on-click card-face pipeline (the DynamicVars
Damage/Block values the game computes and prints when a human selects the
card), and port a `calc_damage`/`calc_block` wherever the game's number
is COMPUTED from combat state but ours is static.

- **The scoping rule that keeps this parity-safe:** a calc hook is added
  exactly when — and computes exactly what — the game's own dynamic var
  computes on the card face, cited to the card's `.cs` per the standing
  fidelity method. Body Slam / Perfected Strike are the existing
  precedent: their `calc_damage` is why their obs fields are truthful AND
  parity-clean. We never invent a "truer" number than the game shows:
  Pact's End's face prints 17 even when the play would do nothing (the
  gold glow carries the condition, §1), so it keeps 17 — conditional
  no-op cards are the glow bit's job, not a zeroed preview.
- Sweep mechanics: enumerate Ironclad-reachable cards (same list as the
  §1 glow sweep — one pass covers both), read each card's `.cs`
  DynamicVars/`GetDamage`/`GetBlock`-style computations, diff against our
  card's declaration, port gaps 1:1. Sweep table (card → verdict →
  citation) recorded in v14-run-log.md, audit-stream style.
- Downstream effect: the damage matrix, `hand.f` base-damage/base-block
  fields, and the new `block_preview_move` field all improve for the
  swept cards automatically — they already route through
  `card_base_damage` / (§2's new) `card_base_block`.

### 3. `--deck-inject` (run-env flag, Perry's proposal refined)

- `STS2RunEnv(deck_inject: str | None = None, deck_inject_prob: float =
  0.0)` — **defaults = bit-identical env.**
- At run start, with probability `deck_inject_prob`, add ONE entry from the
  inject list to the starting deck. An entry is a **package**: a list of
  1–3 card ids added together, because a lone synergy card teaches the
  wrong lesson (a Pact's End with no exhaust cards is dead all run; a lone
  Rupture never triggers). Standalone cards are 1-card packages.
- The list is a static JSON file (`--deck-inject runs/inject_v14.json`),
  generated OFFLINE from the latest eval `cards.csv` (take_rate < 0.20,
  offered ≥ 20) — NOT computed live in the trainer: live pickrate tracking
  is nonstationary (threshold pop-in/out) and the trainer has no per-card
  draft stats. Generator = one-off inline command recorded in
  v14-run-log.md (YAGNI, v11 corpus precedent). Conditional cards get
  hand-written packages (~15-line table in the same file), e.g.:
  Rupture+Bloodletting; Pact's End+2 exhaust cards; Body Slam+Iron Wave;
  Second Wind+exhaust card; Whirlwind alone (energy is generic).
- Sampling: uniform over packages, seeded from the env's episode RNG
  (determinism per seed preserved).
- **Evals stay clean** (no inject flags) so gates remain comparable across
  generations.
- Threading: EnvSpec → build_env → `train_torch.py --deck-inject /
  --deck-inject-prob` (run-only guard), tests in the v10-lowshare style
  (threading + bit-identical default + injected-deck contents + prob=0 /
  prob=1 behavior).

### 4. SpireBot obs-construction port (live parity for schema 12)

The live bot builds its own observation in C# (SpireBot
`CombatObsWriter.cs`) and feeds the exported ONNX model — every obs
change in §1/§2/§2b must land there too or a schema-12 export is
unusable live:

- `glow_gold`: read the game's own `ShouldGlowGold`/`ShouldGlowGoldInternal`
  off the live card — no logic port needed on the C# side, the game
  computes it.
- `block_preview_move`: mirror the sim's `ValueProp.MOVE` pipeline via
  the game's `Hook.ModifyBlock` with a Move-flagged prop (the existing
  field's `default(ValueProp)` call stays untouched beside it).
- §2b calc values: the game's card face already computes these
  (DynamicVars) — SpireBot reads the computed values rather than
  re-porting any per-card logic.
- Field ORDER and normalization must match `full_env.py`'s hand-row
  layout exactly; verified the established way — `live/compare_obs.py`
  parity diff against a live dump, plus the export-parity gate from the
  Task 18 pipeline before any live showcase.
- Note for planning: SpireBot builds against the game DLLs on D:
  (committed csproj paths are stale — see runreplays-build memory).

### 5. Training stage (sketch — sized at plan time)

- s16 = `--resume` of the MIGRATED v13_s15 (+8M, asc 10, same rewards as
  v13 incl. `--reward-elite 2`), `--deck-inject runs/inject_v14.json
  --deck-inject-prob 0.5`, `--critic-warmup 8` (schema migration + new
  start distribution both re-price returns). NO warm-start, ever — the
  run heads carry the recovered rest-share behavior.
- Gates (v14-run-log.md): rest share ≥ 0.15 SURVIVES (v13: 0.263); asc-10
  floor ≥ 20.1 (v13: 19.41, the still-open gate); asc-0 win ≥ 3.3%
  sustained; **cards.csv <5%-take-rate count falling (v13: 24/59)** —
  report-only first generation, per §3's expectation that play skill moves
  before pickrates do.

## Expected outcome / contingency ladder

Injection gives the encoder+critic experience; the draft head gets no
direct gradient from it. First generation likely fixes play competence
while take rates barely move — that is progress (accurate values are the
prerequisite). If after s16 the <5% count hasn't moved: add ε-forced
drafting (train-only random draft override, ~5%) as its own small flag —
the draft-head half of the same coin. Held for later, not in v14:
mechanic-tag card features, per-head entropy.

## Constraints (standing)

- Stage only, never commit; Perry launches real training (native
  PowerShell, CUDA venv); `-Smoke` for script verification.
- Default env bit-identical: every knob defaults to today's behavior.
- Obs-parity fields are load-bearing for SpireBot — new information goes
  in NEW fields, never edits to dumped ones.
- Tests on `.venv`; known-excluded: `test_train_io.py`,
  `test_live_onnx.py`. No masks, ever.

## Rejected alternatives

- **`calc_damage` returning 0 for dead conditionals:** violates obs parity
  (the game prints 17); the glow bit carries the same information from a
  signal the game actually shows.
- **Editing hand.f field 21 to `ValueProp.MOVE`:** reintroduces the 224-
  mismatch regression; pinned by the 89U parity fix.
- **Live <20% pickrate tracking in the trainer:** nonstationary target,
  new bookkeeping; a static list regenerated between stages is equivalent
  and reproducible.
- **Combat-scale mechanic drills:** the run→combat→run round trip
  fresh-inits every run-only head (v11 mechanism) — would erase the
  recovered rest-share (0.263) and cost a ~28M-step rebuild.
- **Draft novelty reward bonus:** most hackable option (pays for drafting
  bad cards); reserved behind ε-forced drafting in the ladder.

## Decisions (Perry, 2026-08-15)

1. Inject threshold: **take_rate < 0.20** (offered ≥ 20, from the latest
   eval cards.csv).
2. `deck_inject_prob`: **0.5** for s16 (flag default stays 0.0 =
   bit-identical).
3. s16 budget: **8M steps**.
4. Glow-gold sweep: **Ironclad-reachable cards only**.
5. (Later same day) §2b added at Perry's request: full
   `calc_damage`/`calc_block` preview-fidelity sweep, same
   Ironclad-reachable scope, game-card-face-mirroring rule.
6. (Later same day) §4 added at Perry's request: SpireBot
   `CombatObsWriter.cs` ports the schema-12 fields so live play stays
   obs-parity with the sim.
