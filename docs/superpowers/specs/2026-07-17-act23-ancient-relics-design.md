# Act 2 & 3 Ancients + their relics — design

*2026-07-17*

## Goal

Port the six Act-2/3 Ancient shrine events and the ~57 relics they grant, wired
into run sequencing so the relics are obtainable in a full run. Full fidelity to
the decompiled game (`c:\Users\Perry\Desktop\Slay the Spire 2`), **excluding only
cross-character card effects** (single-character sim). Behavioral content gets
tests. Matches how Act 1's Ancient (Neow) + its relics were done.

Background: each act begins at an "Ancient" node (`MapPointType.ANCIENT`) that
hands out relics. Act 1 = Neow (already implemented). Act 2 = Orobas / Pael /
Tezcatara. Act 3 = Nonupeipe / Tanx / Vakuu (source: `src/Core/Models/Acts/
Hive.cs`, `Glory.cs`; events in `src/Core/Models/Events/`).

## Section 1 — Ancient events + run wiring

- Six event modules in `sts2_rl/events/`: `orobas.py`, `pael.py`,
  `tezcatara.py`, `nonupeipe.py`, `tanx.py`, `vakuu.py`.
- A shared `AncientEvent(Event)` base (in `events/base.py` or a new
  `events/ancient.py`) capturing the "present 3 relic options, choosing one
  grants the relic and finishes" shape (factored from `neow.py`).
- Each subclass ports the source `GenerateInitialOptions`: fixed option pools
  plus deck-conditional bonus options, evaluated against `run.deck`:
  - Pael: Claw offered if ≥3 Goopy-enchantable cards; Tooth if ≥5 removable;
    Legion if no event pet; pool2/pool3 weighting per source.
  - Tezcatara: Nutritious Soup if deck has a Basic Strike.
  - Nonupeipe: Beautiful Bracelet if ≥4 Swift-enchantable cards; shuffle-take-3.
  - Tanx: Tri-Boomerang if ≥3 Instinct-enchantable; shuffle-take-3.
  - Orobas: pool1 + (PrismaticGem 1/3 else SeaGlass) then take one each from
    pools; pool3 = TouchOfOrobas / ArchaicTooth (gated on setup success).
  - Vakuu: one from each of three pools (shuffle-take-1 each).
- Events register via `@register_event`; auto-append to events vocab
  (68→74, cap 96).
- **Wiring:** `ACT_ANCIENTS = {"hive": [...], "glory": [...]}` + uniform pick.
  `RunDriver.play()` fires the chosen ancient right after `run.advance_act()`
  (act 1 keeps its run-start Neow). New `include_ancients` flag parallels
  `include_neow`, default on. Single wiring point → covers headless driver and
  the greenlet-based run env.

## Section 2 — New subsystems & content

### Enchantments (port into `enchantments.py`, existing pattern)
- `Imbued` — enchanted Skill auto-plays on turn 1 (starts at bottom of draw).
- `Goopy` — Defend card gains Exhaust; `+block` additive grows by 1 each time
  the card is played (Amount++ on play).
- `TezcatarasEmber` — card cost→0, gains Eternal; `+dmg` additive on powered
  attacks.
- `Swift` — on play, draw `amount` cards once per combat.
- `Instinct` — ×2 damage on powered attacks (enchanted Attack only).
- `Clone` — inert marker; referenced by the Clone rest-site option.

### Engine seams
- **Auto-play:** `CombatState.auto_play(card, target)` reusing the normal play
  path; consumers = Imbued, WhisperingEarring, ThrowingAxe double-play, MusicBox.
- **Pet/summon (minimal):** a non-enemy `Creature` that grants block on a
  cooldown, for `PaelsLegion`. Smallest viable model; not a general summon system.
- **Rest-site options:** a `RestSiteOption` surface through `RunDriver._run_rest`
  (`modify_rest_site_options` relic hook already sketched in base.py). Options:
  Cook (MeatCleaver), Kindle (PumpkinCandle), Clone (PaelsGrowth).
- **Card-reward reroll:** `can_reroll` flag on card rewards (Driftwood).
- **Pickup reward screens:** `RewardsCmd`-style offer from `after_obtained`
  (GlassEye 5-tier card offer, ToyBox wax relic).
- **Map room-marking:** FurCoat via `modify_generated_map_late`.
- **Extra turn:** `should_take_extra_turn(player)` combat hook (PaelsEye).
- **Shop auto-buy:** LordsParasol via a merchant-room hook.

### New content
- Cards: `maul`, `relax`, `whistle`, `apotheosis`, `apparition`, `wish`,
  `brightest_flame`, `luminesce`, `soot` (break/dazed/enthralled/folly exist).
- Power: `DiamondDiademPower`.
- Relic: `black_blood` (TouchOfOrobas refinement of Burning Blood).

## Section 3 — Per-ancient relic map (57; **cross-character excluded**)

**Orobas (10):** electric_shrymp (Imbued), glass_eye (pickup reward),
sand_castle (upgrade deck), alchemical_coffer (potion slots), driftwood
(reroll), radiant_pearl (Luminesce T1), **sea_glass → stub (cross-character)**,
**prismatic_gem → +energy only; card-pool half stubbed (cross-character)**,
touch_of_orobas (BlackBlood), archaic_tooth (Bash→Break).

**Pael (10):** flesh (+energy T3+), horn (2 Relax), tears (energy-carry flash),
wing (sacrifice card reward → pull relic), eye (extra turn once/combat), blood
(+draw), claw (Goopy), tooth (remove 5, return 1 upgraded per combat), legion
(pet), growth (Clone enchant + rest option).

**Tezcatara (8):** yummy_cookie (upgrade), biiig_hug (Soot on shuffle),
storybook (BrightestFlame), toasty_mittens (exhaust top of draw), pumpkin_candle
(+energy next 5 combats + Kindle rest), toy_box (wax relic pickup), seal_of_gold
(turn-1 energy + gold), nutritious_soup (TezcatarasEmber on Basic Strikes).

**Nonupeipe (9):** blessed_antler (+energy, 3 Dazed T1), brilliant_scarf (every
Nth card that turn is free), delicate_frond (fill potion slots at combat start),
diamond_diadem (DiamondDiademPower on N-card turns), fur_coat (map-mark
elites/monsters for bonus), glitter (Glam on card rewards — exists), jewelry_box
(Apotheosis), signet_ring (verify source body), beautiful_bracelet (Swift).

**Tanx (10):** claws (transform → Maul), crossbow (free random Attack at turn
start), iron_club (Nth card effect), meat_cleaver (Cook rest option), sai (block
at turn start), spiked_gauntlets (+energy, Powers cost +1), tanxs_whistle
(Whistle card), throwing_axe (first card each combat played twice), war_hammer
(upgrade deck after elite), tri_boomerang (Instinct).

**Vakuu (10):** blood_soaked_rose (+energy, add Enthralled), whispering_earring
(auto-play ≤13 cards T1), fiddle (draw modifier / skip normal draw), preserved_fog
(add Folly), sere_talon (add curses + Wish), distinguished_cape (−9 maxHP, 3
Apparition), choices_paradox (T1 card select into hand), music_box (ethereal
attack clone), lords_parasol (shop auto-buy free), jeweled_mask (free Power T1).

Numeric values (energy amounts, N thresholds, block/draw counts) are taken from
each source model at implementation time (non-ascension values).

## Section 4 — Testing, phasing, vocab

- **Tests** (`test/`, `test_powers.py` / `test_new_features.py` style): each
  behavioral relic, each new enchantment/power/pet, and each ancient's
  option-generation (Neow-style). Build a seeded `CombatState`, drive
  `end_turn`/`DamageCmd`, assert. `py -m pytest test/ -q` green at end of every
  phase.
- **Phasing:** Phase 0 = shared subsystems (AncientEvent base + wiring,
  6 enchantments, auto-play seam, the small new-content cards/power/relic that
  multiple ancients need). Then one phase per ancient: Orobas → Pael → Tezcatara
  → Nonupeipe → Tanx → Vakuu. Each phase ends with the full suite green.
- **Vocab:** relics auto-append (~171→228, cap 336); events 68→74. `vocab.json`
  will change — it is part of the trained-model contract and is committed by the
  user, not auto-committed here.

## Non-goals / exclusions
- Cross-character card generation: `sea_glass` (other-character card offer) and
  the card-pool half of `prismatic_gem` are documented stubs; prismatic_gem's
  `+energy` is implemented.
- No visual/audio/dialogue fidelity (events carry option keys only, like Neow).
- Ascension-scaled values (sim uses non-ascension).

## Convention notes
- Per repo CLAUDE.md rule 4, nothing is committed automatically; changes are
  left staged for the user to review and commit.
- Relics/events/enchantments follow the existing decorator + auto-import
  registries; each is a whole-combat hook listener where it has combat behavior.
