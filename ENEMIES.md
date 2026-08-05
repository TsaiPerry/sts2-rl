# ENEMIES.md — porting enemies into the sim

How to port an STS2 enemy into the sim. Read CLAUDE.md first; its golden rule
applies doubly here — **every number and move pattern comes from the decompiled
source** at `c:\Users\Perry\Desktop\Slay the Spire 2`.

## Current status

| Act | Source | Sim package | Status |
|---|---|---|---|
| Act 1 — Overgrowth | `src/Core/Models/Acts/Overgrowth.cs` | `sts2_rl/monsters/overgrowth/` | ✅ complete (22 encounters) |
| Act 2 — Underdocks | `src/Core/Models/Acts/Underdocks.cs` | `sts2_rl/monsters/underdocks/` | ✅ complete (20 encounters) |
| Act 2 — Hive (parallel Act 2; the game picks one) | `src/Core/Models/Acts/Hive.cs` | `sts2_rl/monsters/hive/` | ✅ complete (20 encounters) |
| Act 3 — Glory | `src/Core/Models/Acts/Glory.cs` | `sts2_rl/monsters/glory/` | ✅ complete (18 encounters) |
| Event encounters (no act pool) | `src/Core/Models/Encounters/*EventEncounter.cs` | mostly ported | see below |

**All four act rosters are complete** — 111 monster classes, 138 powers. What
remains is event-encounter and cross-character content:

- **Not ported:** `TheArchitectEventEncounter`'s Architect.
- **Ported since this file was written:** FakeMerchantMonster
  (`monsters/fake_merchant.py`), MysteriousKnight
  (`monsters/hive/flail_knight.py`), the BattleFriend dummies
  (`monsters/glory/battle_friend.py`).

### Skip entirely

- **Test scaffolding**: everything in `Mocks/`, `DeprecatedMonster`,
  `BigDummy`, `OneHpMonster`, `TenHpMonster`, `SingleAttackMoveMonster`,
  `MultiAttackMoveMonster`.
- **Ally/pet units** the sim's Ironclad-only scope never spawns: `Osty`
  (Necrobinder resource), `Byrdpip` (relic pet).

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
   Check `sts2_rl/powers.py` first — 138 are already ported.

Ignore `.uid` files and everything under `Models/Monsters/Mocks/` and
`Models/Encounters/Mocks/`.

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
8. **Test** (mirroring `test/test_hive.py` / `test_glory.py` /
   `test_underdocks.py`): hp range over several seeds, the move
   cycle/branching (drive `cs.end_turn()` and assert intents/damage), each
   new power's behavior, and any spawn-time powers. Run the full suite:
   `py -m pytest test/ -q` — all tests must pass.
9. **Update CLAUDE.md**: package-layout blurb (new act package) and the
   known-gaps bullet about remaining monsters.

## Gotchas that bit previous ports

- **Trust `GenerateMonsters()`, never a guess about the lineup.** The Hive and
  Glory ports both found the real compositions differed from what the
  encounter names implied — ScrollsOfBiting is ×3/×4 not ×4/×5, AxebotsNormal
  is a *single* Axebot that respawns via Stock, OvicopterNormal starts with
  just the Ovicopter and summons the eggs mid-fight.
- **HP/damage numbers**: always the last `GetValueIfAscension` argument.
  Cross-check a couple against the wiki if unsure, but the source wins.
- **`AddBranch`'s int arguments are cooldown / maxRepeats, NOT weights.**
  Five hand-rolled monsters misread them. Read the overload before porting a
  `RandomBranchState`.
- **RNG discipline**: combat randomness goes through `CombatState.combat_rng`
  (`combat_rng.py`), which has seven named accessors — `shuffle`,
  `monster_ai`, `card_gen`, `card_selection`, `targets`, `energy`,
  `potion_gen`. In legacy (RL-training) mode every accessor is the one shared
  `random.Random`; in a string-seeded parity run each is a `GameRandomAdapter`
  over the matching game stream. **Use the accessor that names your purpose,
  never `combat._rng` directly** — reaching for the shared object is the most
  common fidelity defect in this codebase, and it desyncs every later draw in
  a parity run. Monster move rolls belong on `combat_rng.monster_ai`.
- **Stun/escape**: stunned monsters skip `take_turn` but still tick
  turn-start/end effects and must show `Intent(MoveType.STUN)`; escapes go
  through `CreatureCmd.escape` (counts as gone, not dead).
- **Death is not removal**: a creature can die at 0 HP and keep taking turns
  (withered Decimillipede segments). Only removal from `Enemies` is vetoed.
- **Forced state changes** (a power interrupting the move cycle, like
  TerrorEel's Shriek): use `machine.force_current_state(...)` and
  `must_perform_once_before_transitioning=True` so an end-of-turn roll can't
  skip the forced move.
- **Segmented/linked monsters** (Decimillipede): check the source for
  death-linking or position-dependent behavior between segments before
  assuming they're independent creatures.
- **Summoners** (Fabricator, Queen, Entomancer): summoned units register as
  hook listeners via `CreatureCmd.add` (fires `on_creature_added`); decide
  minion status from the source, since it drives the win condition. Slot
  *placement* can matter — the Ovicopter's eggs occupy specific slots.
- **Approximations must be documented inline.** Glory's card-keyword-heavy
  powers are approximated where the sim lacks the plumbing: Hex sets each
  Hexed card's `is_ethereal` flag directly, and the Queen re-telegraphs an
  in-progress Burn Bright as Enrage at move resolution rather than the instant
  the Torch Head Amalgam dies.
