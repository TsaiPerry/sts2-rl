# ENEMIES.md — implementing the remaining enemies

How to port the rest of the STS2 enemy roster into the sim. Read CLAUDE.md
first; its golden rule applies doubly here — **every number and move pattern
comes from the decompiled source** at `c:\Users\Perry\Desktop\Slay the Spire 2`.

## Current status

| Act | Source | Sim package | Status |
|---|---|---|---|
| Act 1 — Overgrowth | `src/Core/Models/Acts/Overgrowth.cs` | `sts2_rl/monsters/overgrowth/` | ✅ complete (22 encounters) |
| Act 2 — Underdocks | `src/Core/Models/Acts/Underdocks.cs` | `sts2_rl/monsters/underdocks/` | ✅ complete (20 encounters) |
| Act 2 — Hive (parallel Act 2; the game picks one) | `src/Core/Models/Acts/Hive.cs` | `sts2_rl/monsters/hive/` | ✅ complete (20 encounters) |
| Act 3 — **Glory** | `src/Core/Models/Acts/Glory.cs` | — | ❌ not started (18 encounters) |
| Event encounters (no act pool) | `src/Core/Models/Encounters/*EventEncounter.cs` | partial | optional |

## Where to look in the source

1. **Act encounter list**: `src/Core/Models/Acts/<Act>.cs` →
   `GenerateAllEncounters()`. This is the authoritative list of what the act
   contains (weak/normal/elite/boss all mixed together; `RoomType` on the
   encounter tells you which).
2. **Encounter composition**: `src/Core/Models/Encounters/<Name>.cs` →
   `GenerateMonsters()` — the actual monster lineup for a fight. Ignore
   `AllPossibleMonsters` (it's the superset used for UI/compendium, which is
   why naive grepping double-counts). Watch for:
   - **Multiplayer scaling** (checks on player count): port the
     **single-player** lineup only.
   - **Random compositions** (e.g. `BowlbugsNormal` rolls 2 workers from
     Egg/Silk/Nectar with per-type caps): the sim's `Encounter` dataclass
     holds a static `monster_classes` list — subclass it or give it a factory
     override for these fights, seeded from the combat RNG.
3. **Monster stats & AI**: `src/Core/Models/Monsters/<Name>.cs`.
4. **Move-machine primitives**: `src/Core/MonsterMoves/` (intents, state
   types) — already ported to `sts2_rl/monsters/state_machine.py`.
5. **Powers a monster applies/owns**: `src/Core/Models/Powers/<Name>.cs`.
   Check `sts2_rl/powers.py` first — ~50 are already ported.

Ignore `.uid` files and everything under `Models/Monsters/Mocks/` and
`Models/Encounters/Mocks/`.

## Remaining roster

Exact per-fight counts below come from each encounter's `GenerateMonsters()` —
re-verify when implementing.

### Hive (Act 2 variant) — ✅ done, `sts2_rl/monsters/hive/`

All 20 encounters ported (tests in `test/test_hive.py`). Notes for the next
act's port — the actual lineups differed from earlier guesses; always trust
`GenerateMonsters()`:

- ChompersNormal is Chomper ×2 (second has `ScreamFirst`), MytesNormal is
  Myte ×2, Exoskeletons are ×3 weak / ×4 normal, and the act pool has
  TunnelerWeak only (no TunnelerNormal).
- OvicopterNormal and TheObscuraNormal start with just the main monster;
  ToughEgg / Parafright are summoned mid-fight.
- New powers live in powers.py (Imbalanced, HardToKill, Tender, Hatch,
  Slumber, EscapeArtist, Flutter, Swipe, Burrowed, Reattach, PersonalHive,
  VitalSpark + Tainted, BackAttackLeft/Right, CrabRage, Surrounded, Sandpit,
  Disintegration, MindRot, Sloth, WasteAway); new status cards are Toxic,
  FranticEscape, and the Knowledge Demon choosable curses
  (`cards/knowledge_curses.py`, chosen via `select_cards` with purpose
  `"curse_of_knowledge"`).

### Glory (Act 3) — target package `sts2_rl/monsters/glory/`

| Encounter (source file) | Monsters needed |
|---|---|
| DevotedSculptorWeak | DevotedSculptor |
| ScrollsOfBitingWeak / ScrollsOfBitingNormal | ScrollOfBiting ×4 / ×5 |
| TurretOperatorWeak | TurretOperator + LivingShield |
| AxebotsNormal | Axebot ×2 |
| ConstructMenagerieNormal | CubexConstruct + PunchConstruct — **both already implemented**; encounter-only work |
| FabricatorNormal | Fabricator — summons Guardbot / Noisebot / Stabbot / Zapbot (4 extra monster classes, referenced only from `Fabricator.cs`) |
| FrogKnightNormal | FrogKnight |
| GlobeHeadNormal | GlobeHead |
| OwlMagistrateNormal | OwlMagistrate |
| SlimedBerserkerNormal | SlimedBerserker |
| TheLostAndForgottenNormal | TheLost + TheForgotten |
| KnightsElite | FlailKnight + MagiKnight + SpectralKnight |
| MechaKnightElite | MechaKnight |
| SoulNexusElite | SoulNexus |
| AeonglassBoss | Aeonglass |
| QueenBoss | Queen + TorchHeadAmalgam (also referenced from `Queen.cs` — likely summoned/revived; read both) |
| TestSubjectBoss | TestSubject |

### Event encounters (optional, lower priority)

Not in any act pool; fought via map events. `DenseVegetationEventEncounter`
(Wriggler ×2) and `PunchOffEventEncounter` (PunchConstruct ×3) already have
their monsters implemented. Remaining monsters: Architect
(`TheArchitectEventEncounter`), FakeMerchantMonster, MysteriousKnight,
and whatever `BattlewornDummyEventEncounter` spawns (read the file — it
builds its lineup differently).

### Skip entirely

- **Test scaffolding**: everything in `Mocks/`, `DeprecatedMonster`,
  `BigDummy`, `OneHpMonster`, `TenHpMonster`, `SingleAttackMoveMonster`,
  `MultiAttackMoveMonster`.
- **Ally/pet units** (the sim has no relics/pets/characters that spawn them):
  `Osty` (Necrobinder resource), `Byrdpip` (relic pet), `PaelsLegion`
  (Pael ancient-event relic), `BattleFriendV1/V2/V3`.

## Implementation recipe (per encounter)

1. **Read the encounter file** → lineup, `RoomType` (weak/normal/elite/boss).
2. **Read each monster's `.cs`**. Extract:
   - `MinInitialHp` / `MaxInitialHp` → `min_hp` / `max_hp`. When wrapped in
     `AscensionHelper.GetValueIfAscension(level, ascValue, baseValue)`, use
     the **last argument** (non-ascension). Same for damage/stack values.
   - `AfterAddedToRoom()` → powers applied at spawn; do this in the monster's
     `__init__` via `PowerCmd.apply` (see TerrorEel applying ShriekPower).
   - `GenerateMoveStateMachine()` → the AI.
3. **Pick the AI style** (see CLAUDE.md "Monster AI"):
   - Source machine is a plain `FollowUpState` loop → either style works;
     hand-rolled `_move_key` is fine.
   - Source uses `RandomBranchState` / `ConditionalBranchState` / repeat
     rules / cooldowns → **use `MachineMonster` +
     `MonsterMoveStateMachine`** (`monsters/state_machine.py`). Byrdonis,
     Fogmog, Mawler, TerrorEel are the reference ports.
4. **Map intents** to the sim's `Intent`:
   `MultiAttackIntent(d, n)` → `Intent(MoveType.ATTACK, damage=d, hits=n)`;
   `StatusIntent(n)` → `MoveType.STATUS_CARD`; buff/debuff/defend/summon/
   sleep/escape intents map 1:1 onto the 15-type `MoveType` vocabulary.
   Multi-effect moves: primary type + `also=(...)`.
5. **Effects go through commands** (`cmds.py`) — attacks via
   `self._execute_attack(ctx, dmg, hits)` (brackets before/after_attack for
   Vigor), powers via `PowerCmd.apply`, status cards via
   `CardPileCmd.add_to_discard`/`add_to_draw`, summons via `CreatureCmd.add`.
6. **Port missing powers** to `powers.py` from `src/Core/Models/Powers/` —
   many "new" monster mechanics are just a power the monster owns. Summoned
   secondary units that shouldn't gate the win condition get the `minion`
   power (see Kin Followers / Eye With Teeth).
7. **Wire the encounter**: module-level
   `FOO_NORMAL = Encounter(id="foo_normal", monster_classes=[...])`, add it
   to the act package's `ENCOUNTERS` dict (grouped Weak/Normal/Elite/Boss —
   copy `underdocks/__init__.py`'s shape), export monsters + encounters from
   the package `__init__`, and re-export from `monsters/__init__.py`.
8. **Test** (new `test/test_hive.py` / `test_glory.py`, mirroring
   `test_underdocks.py`): hp range over several seeds, the move
   cycle/branching (drive `cs.end_turn()` and assert intents/damage), each
   new power's behavior, and any spawn-time powers. Run the full suite:
   `py -m pytest test/ -q` — all tests must pass.
9. **Update CLAUDE.md**: package-layout blurb (new act package) and the
   known-gaps bullet about remaining monsters.

## Gotchas that bit previous ports

- **HP/damage numbers**: always the last `GetValueIfAscension` argument.
  Cross-check a couple against the wiki if unsure, but the source wins.
- **RNG discipline**: one shared `random.Random` per combat. Monster move
  rolls happen when the machine advances (the game rolls at intent-display
  time from a separate `MonsterAi` stream — accepted deviation, see
  CLAUDE.md). Don't add RNG draws to combat setup without checking seeded
  tests.
- **Stun/escape**: stunned monsters skip `take_turn` but still tick
  turn-start/end effects and must show `Intent(MoveType.STUN)`; escapes go
  through `CreatureCmd.escape` (counts as gone, not dead).
- **Forced state changes** (a power interrupting the move cycle, like
  TerrorEel's Shriek): use `machine.force_current_state(...)` and
  `must_perform_once_before_transitioning=True` so an end-of-turn roll can't
  skip the forced move.
- **Gold theft** (Thieving Hopper, like Gremlin Merc before it): the sim has
  no gold — implement the move as a no-op or intent-only, document it in the
  docstring, and note it in CLAUDE.md's gaps if it's load-bearing.
- **Segmented/linked monsters** (Decimillipede): check the source for
  death-linking or position-dependent behavior between segments before
  assuming they're independent creatures.
- **Summoners** (Fabricator, Queen, Entomancer?): summoned units register as
  hook listeners via `CreatureCmd.add` (fires `on_creature_added`); decide
  minion status from the source, since it drives the win condition.
