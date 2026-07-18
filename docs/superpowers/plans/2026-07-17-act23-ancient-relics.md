# Act 2 & 3 Ancient Relics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, this session). Steps use checkbox (`- [ ]`) syntax. This is a *navigational* plan: exact files + source refs + behavior + test targets per task, with full code only for shared seams (the executor has full repo context; reproducing 57 relic listings would violate DRY).

**Goal:** Port the six Act-2/3 Ancient shrine events and the ~57 relics they grant, wired into run sequencing, full-fidelity except cross-character card effects, with tests for behavioral content.

**Architecture:** Ancient events subclass a shared `AncientEvent(Event)` (factored from `neow.py`) presenting 3 relic options; the driver fires the act's chosen ancient after `advance_act()`. Relics are hook-listener classes in `relics/` (existing pattern). New shared subsystems: 6 enchantments, an auto-play seam, a minimal pet, rest-site options, and a handful of new cards/power/relic.

**Tech Stack:** Python 3, pytest, the sts2_rl engine (`CombatState`, `HookSystem`, `cmds.py`, decorator registries).

## Progress (2026-07-17) — ✅ COMPLETE

All phases landed and green (1904 tests):

- ✅ **Phase 0** — `events/ancient.py` base, `neow.py` refactor, `driver.py` `ACT_ANCIENTS`/`include_ancients` wiring, `CombatState.auto_play`, all 6 enchantments.
- ✅ **Orobas / Pael / Tezcatara / Nonupeipe / Tanx / Vakuu** — all 6 events + 57 relics + 11 cards + 2 powers, tests in `test/test_ancients.py` (83) + `test/test_ancient_subsystems.py`.
- Engine seams added along the way: extra-turn hook (`should_take_extra_turn`/`on_extra_turn`), rest-site options (`RestSiteOption` + `modify_rest_site_options` + driver REST indices 3+), reward reroll (`CombatRewards.can_reroll`) and sacrifice (`sacrifice_relic`) actions, `after_shop_entered` + `purchase(ignore_cost)`, `CombatState.gold_spent`, `player_gold` constructor arg, wax relics (`Relic.is_wax`), `adds_pet`/`has_event_pet`.
- Legacy pins updated: `test_relics` count 168→226; `test_full_env` power-vocab check is set-based (frozen vocab appends aren't alphabetical).
- Cross-character stubs as specced: `sea_glass` (full), `prismatic_gem` card-pool half.

## Global Constraints

- Source of truth: `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\Models\...`. Use **non-ascension** numeric values (`AscensionHelper.GetValueIfAscension` → take the base branch).
- Effects go through `cmds.py`, never by mutating hp/block directly.
- Every relic/event/enchantment registers via its decorator; auto-import handles the rest. `make_relic`/`make_event`/`make_enchantment` build by id.
- `py -m pytest test/ -q` green at the end of every phase.
- Do NOT `git commit` — leave changes staged for the user (repo CLAUDE.md rule 4). "Commit" steps below mean *stage + stop at a green checkpoint*, not run git commit.
- Cross-character exclusions: `sea_glass` (full stub), `prismatic_gem` card-pool half stub (energy implemented).
- `vocab.json` will gain relic/event ids automatically; leave it for the user to commit.

---

## Phase 0 — Shared subsystems

### Task 0.1: `AncientEvent` base

**Files:** Create `sts2_rl/events/ancient.py`; Test `test/test_ancients.py`.

**Interfaces — Produces:**
- `class AncientEvent(Event)` with helper `self._relic_option(relic_id) -> EventOption` (grants relic + `_finish("DONE")`), and subclasses implement `initial_options()`.

```python
# sts2_rl/events/ancient.py
from __future__ import annotations
from typing import TYPE_CHECKING
from ..relics import make_relic
from .base import Event, EventOption
if TYPE_CHECKING:
    from ..run import RunState

class AncientEvent(Event):
    """Base for act-start Ancient shrines (mirrors AncientEventModel): present
    a set of relic options; choosing one obtains the relic and finishes."""
    def _relic_option(self, relic_id: str) -> EventOption:
        def on_chosen() -> None:
            self.run.add_relic(make_relic(relic_id))
            self._finish("DONE")
        return EventOption(relic_id, on_chosen)
```

Refactor `neow.py` `_relic_option` to inherit from `AncientEvent` (behavior identical). Test: existing neow tests still pass; a trivial `AncientEvent` subclass offering `["vajra"]` grants it on choose.

- [ ] Write test, run (fail), implement, run (pass), checkpoint.

### Task 0.2: Driver wiring + `ACT_ANCIENTS`

**Files:** Modify `sts2_rl/driver.py` (`__init__` add `include_ancients=True`; `play()` after `advance_act()`), add `ACT_ANCIENTS` map (in `driver.py` or `run.py`).

**Behavior:** after `run.advance_act()` returns, look up `run.act_config.name` in `ACT_ANCIENTS`; if present and `include_ancients`, `self._run_event(make_event(self.rng-uniform-pick, run))`. `ACT_ANCIENTS = {"hive": ["orobas","pael","tezcatara"], "glory": ["nonupeipe","tanx","vakuu"]}`. Use `run.rng.choice`.

**Test:** a scripted run with a stubbed 1-ancient map reaching act 2 fires exactly one hive ancient; `include_ancients=False` fires none. (Use existing driver test harness / `play_random_run` seam.)

- [ ] Write test, run (fail), implement, run (pass), checkpoint.

### Task 0.3: Auto-play seam

**Files:** Modify `sts2_rl/combat.py` (add `auto_play(card, target=None)`), Test `test/test_new_features.py`.

**Source:** `CardCmd.AutoPlay` — plays a card without spending energy/normal-play bookkeeping differences; reuse `_resolve_card_play` path but flag `is_auto` so relics that skip auto-plays (PaelsEye) can check. Add `CombatCtx.is_auto_play` or a param threaded to `before_card_played`.

**Test:** auto_play a Strike kills-damage a dummy without consuming energy; `on_card_played` fires.

- [ ] TDD cycle + checkpoint.

### Task 0.4: Six enchantments

**Files:** Modify `sts2_rl/enchantments.py`; Test `test/test_new_features.py` (or `test_enchantments.py`).

Port each per `enchantments.py` pattern. Source: `src/Core/Models/Enchantments/{Imbued,Goopy,Clone,TezcatarasEmber,Swift,Instinct}.cs`.
- `Imbued`: `can_enchant` Skill only; on turn-1 pre-play, `combat.auto_play(self.card)`. Uses Task 0.3.
- `Goopy`: `can_enchant` Defend only; `attach` adds exhaust; `modify_block_additive` returns `amount-1`; `on_card_played` (own card) `amount += 1`.
- `TezcatarasEmber`: `attach` sets cost 0 + eternal; `modify_damage_additive` on powered attack returns configured amount.
- `Swift`: `on_card_played` (own card, once/combat) draw `amount`.
- `Instinct`: `can_enchant` Attack only; `modify_damage_multiplicative` powered → 2.
- `Clone`: inert (no hooks).

**Tests:** one behavior test each (block growth for Goopy, ×2 for Instinct, draw for Swift, cost-0+dmg for Ember, auto-play for Imbued).

- [ ] TDD per enchantment + checkpoint.

### Task 0.5: New cards / power / relic prerequisites

**Files:** Create `sts2_rl/cards/{maul,relax,whistle,apotheosis,apparition,wish,brightest_flame,luminesce,soot}.py`; `sts2_rl/powers.py` add `DiamondDiademPower`; `sts2_rl/relics/black_blood.py`. Tests in `test/`.

Port each from `src/Core/Models/Cards/<Name>.cs`, `Powers/DiamondDiademPower.cs`, `Relics/BlackBlood.cs` using existing card/power/relic patterns. `black_blood` = Burning Blood but heals more (check source). Only implement what the granting relics need.

- [ ] TDD per item (behavioral ones) + checkpoint.

---

## Phase 1 — Orobas (10 relics + event)

**Files:** Create `sts2_rl/events/orobas.py` + `sts2_rl/relics/{electric_shrymp,glass_eye,sand_castle,alchemical_coffer,driftwood,radiant_pearl,sea_glass,prismatic_gem,touch_of_orobas,archaic_tooth}.py`. Test `test/test_ancient_relics.py` + `test/test_ancients.py`.

Per-relic (source `src/Core/Models/Relics/<Name>.cs`, behavior from spec §3):
- [ ] `sand_castle` — `after_obtained`: upgrade all upgradable deck cards. **Test.**
- [ ] `radiant_pearl` — `on_player_turn_start` turn 1: add `luminesce` to hand. **Test.**
- [ ] `archaic_tooth` — `after_obtained`: transform Bash→Break in deck (Ironclad). **Test.**
- [ ] `touch_of_orobas` — `after_obtained`: replace `burning_blood` starter with `black_blood`. **Test.**
- [ ] `electric_shrymp` — `after_obtained`: enchant 1 chosen deck card with Imbued (via `run.select_cards`). **Test.**
- [ ] `glass_eye` — `after_obtained`: offer 5-tier (C,C,U,U,R) card rewards (pickup reward screen seam). **Test.**
- [ ] `driftwood` — mark card rewards `can_reroll` (reward-hook + reroll seam). **Test.**
- [ ] `alchemical_coffer` — `after_obtained`: +2 potion slots, fill (potion procurement). **Test.**
- [ ] `prismatic_gem` — `modify_max_energy` +1; card-pool half = documented stub. **Test energy.**
- [ ] `sea_glass` — documented cross-character stub (no hooks). No behavior test.
- [ ] `orobas.py` event — `GenerateInitialOptions` per `Events/Orobas.cs` (pool1 + prismatic/seaglass 1/3 + pool2 + pool3 gated). **Option-generation test.**
- [ ] Full suite green; checkpoint.

---

## Phase 2 — Pael (10 relics + event)

**Files:** `sts2_rl/events/pael.py` + `relics/paels_{flesh,horn,tears,wing,eye,blood,claw,tooth,legion,growth}.py`. Pet layer in `creatures.py`/`combat.py` for legion. Tests.

- [ ] `paels_flesh` — `modify_max_energy` +N when `turn >= 3`. **Test.**
- [ ] `paels_blood` — `modify_hand_draw` +N. **Test.**
- [ ] `paels_horn` — `after_obtained`: add 2 `relax`. **Test.**
- [ ] `paels_claw` — `after_obtained`: enchant all Goopy-eligible deck cards. **Test.**
- [ ] `paels_growth` — `after_obtained`: enchant 1 chosen card Clone; add Clone rest option. **Test (enchant path).**
- [ ] `paels_tooth` — `after_obtained`: remove 5 chosen cards, store; `after_combat_end`: return 1 upgraded. **Test.**
- [ ] `paels_tears` — energy-carry flash; port faithfully (verify full source body for any real effect). **Test if effect exists.**
- [ ] `paels_eye` — `should_take_extra_turn` once/combat if no cards played (extra-turn seam). **Test.**
- [ ] `paels_wing` — sacrifice card-reward alternative → pull relic from front (reward-alt seam). **Test.**
- [ ] `paels_legion` — minimal pet granting block on cooldown. **Test.**
- [ ] `pael.py` event per `Events/Pael.cs` (deck-conditional Claw/Tooth/Legion). **Option test.**
- [ ] Full suite green; checkpoint.

---

## Phase 3 — Tezcatara (8 relics + event)

**Files:** `events/tezcatara.py` + `relics/{yummy_cookie,biiig_hug,storybook,toasty_mittens,pumpkin_candle,toy_box,seal_of_gold,nutritious_soup}.py`. Rest-option framework (`_run_rest` + `modify_rest_site_options`) lands here. Tests.

- [ ] `yummy_cookie` — `after_obtained`: upgrade (source: which cards). **Test.**
- [ ] `storybook` — add `brightest_flame`. **Test.**
- [ ] `toasty_mittens` — `on_player_turn_start`: exhaust top of draw (skip innate turn 1). **Test.**
- [ ] `seal_of_gold` — turn-1 `on_player_turn_start`: gain 1 energy + 5 gold. **Test.**
- [ ] `nutritious_soup` — `after_obtained`: TezcatarasEmber on Basic Strikes. **Test.**
- [ ] `biiig_hug` — `after_obtained` remove cards; `on_shuffle`: add `soot` to draw. **Test.**
- [ ] `pumpkin_candle` — `modify_max_energy` +1 while KindleCount>0; `after_combat_end` decrement; Kindle rest option. **Test.**
- [ ] `toy_box` — wax-relic pickup reward + per-combat counter. **Test.**
- [ ] `tezcatara.py` event per `Events/Tezcatara.cs` (Soup if Basic Strike). **Option test.**
- [ ] Full suite green; checkpoint.

---

## Phase 4 — Nonupeipe (9 relics + event)

**Files:** `events/nonupeipe.py` + `relics/{blessed_antler,brilliant_scarf,delicate_frond,diamond_diadem,fur_coat,glitter,jewelry_box,signet_ring,beautiful_bracelet}.py`. Map-mark seam for fur_coat. Tests.

- [ ] `brilliant_scarf` — every Nth card that turn is free (`modify_card_energy_cost` + per-turn count). **Test.**
- [ ] `blessed_antler` — `modify_max_energy` +1; turn-1 shuffle 3 `dazed` into draw. **Test.**
- [ ] `diamond_diadem` — count cards/turn; `on_player_turn_end` if ≥threshold apply `DiamondDiademPower`. **Test.**
- [ ] `delicate_frond` — `on_combat_start`: fill potion slots (procurement). **Test.**
- [ ] `glitter` — `modify_card_reward_options`: Glam-enchant eligible reward cards (Glam exists). **Test.**
- [ ] `jewelry_box` — add `apotheosis`. **Test.**
- [ ] `beautiful_bracelet` — `after_obtained`: enchant 3 Swift-eligible cards. **Test.**
- [ ] `signet_ring` — verify source body, implement (or stub if empty). **Test if effect.**
- [ ] `fur_coat` — `modify_generated_map_late`: mark elite/monster rooms for bonus. **Test.**
- [ ] `nonupeipe.py` event per `Events/Nonupeipe.cs` (Bracelet if ≥4 Swift-eligible; shuffle-take-3). **Option test.**
- [ ] Full suite green; checkpoint.

---

## Phase 5 — Tanx (10 relics + event)

**Files:** `events/tanx.py` + `relics/{claws,crossbow,iron_club,meat_cleaver,sai,spiked_gauntlets,tanxs_whistle,throwing_axe,war_hammer,tri_boomerang}.py`. Tests.

- [ ] `spiked_gauntlets` — `modify_max_energy` +1; Power cards `modify_card_energy_cost` +1. **Test.**
- [ ] `sai` — `on_player_turn_start`: gain block (source amount). **Test.**
- [ ] `war_hammer` — `after_combat_end` elite: upgrade all upgradable deck cards. **Test.**
- [ ] `throwing_axe` — first card each combat played twice (`modify_card_play_count` once, uses auto-play/replay). **Test.**
- [ ] `crossbow` — `on_player_turn_start`: add 1 free random Attack from character pool. **Test.**
- [ ] `iron_club` — every Nth card played → effect (verify source body — likely draw). **Test.**
- [ ] `claws` — `after_obtained`: transform chosen cards → `maul`. **Test.**
- [ ] `tanxs_whistle` — add `whistle`. **Test.**
- [ ] `tri_boomerang` — `after_obtained`: enchant 3 Instinct-eligible cards. **Test.**
- [ ] `meat_cleaver` — Cook rest-site option (uses Phase-3 framework). **Test.**
- [ ] `tanx.py` event per `Events/Tanx.cs` (Tri-Boomerang if ≥3 Instinct-eligible). **Option test.**
- [ ] Full suite green; checkpoint.

---

## Phase 6 — Vakuu (10 relics + event)

**Files:** `events/vakuu.py` + `relics/{blood_soaked_rose,whispering_earring,fiddle,preserved_fog,sere_talon,distinguished_cape,choices_paradox,music_box,lords_parasol,jeweled_mask}.py`. Shop auto-buy seam. Tests.

- [ ] `blood_soaked_rose` — `modify_max_energy` +N; `after_obtained` add `enthralled`. **Test.**
- [ ] `jeweled_mask` — turn ≤1 `on_player_turn_start`: a Power in draw becomes free + to hand. **Test.**
- [ ] `music_box` — first Attack/turn → add ethereal clone to hand. **Test.**
- [ ] `choices_paradox` — turn 1: generate cards (retain), select 1 into hand. **Test.**
- [ ] `fiddle` — `modify_hand_draw` +N and suppress normal turn-start draw (`should_draw`). **Test.**
- [ ] `distinguished_cape` — `after_obtained`: −9 max HP, add 3 `apparition`. **Test.**
- [ ] `preserved_fog` — `after_obtained`: remove cards, add `folly`. **Test.**
- [ ] `sere_talon` — `after_obtained`: add random curses + `wish`. **Test.**
- [ ] `whispering_earring` — `modify_max_energy` +N; turn-1 auto-play ≤13 playable cards (auto-play seam). **Test.**
- [ ] `lords_parasol` — merchant-room hook: buy everything free. **Test.**
- [ ] `vakuu.py` event per `Events/Vakuu.cs` (one from each of 3 pools). **Option test.**
- [ ] Full suite green; checkpoint.

---

## Final

- [ ] `py -m pytest test/ -q` fully green.
- [ ] Confirm `vocab.json` grew (relics + 6 events) and no capacity error at import.
- [ ] Update `CLAUDE.md` "Known gaps" + `MODULES.md` relic/event enumerations to note act-2/3 ancients now implemented.
- [ ] Summarize staged changes for the user to review + commit.

## Self-review notes
- Spec §1 events → each phase's event task. §2 subsystems → Phase 0 (enchant/auto-play/cards) + per-phase seams (pet=P2, rest=P3, map=P4, shop=P6, reward pickup/reroll/extra-turn=P1/P2). §3 relics → per-phase tasks. §4 tests/phasing/vocab → per-task tests + Final.
- Cross-character stubs (sea_glass, prismatic_gem half) explicitly marked no-test.
- Numeric values deliberately deferred to implementation (read each source model); flagged inline as "(source amount)".
