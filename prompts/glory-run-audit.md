# Prompt: Audit and finalize Glory (Act 3) run integration

Copy everything below into a fresh session.

---

In `c:\Users\Perry\Desktop\sts2-rl` (pure-Python Slay the Spire 2 simulator + RL
envs). The decompiled game source at `c:\Users\Perry\Desktop\Slay the Spire 2`
is the fidelity source of truth: where the sim disagrees with the source, fix
the sim and update legacy tests — never preserve old sim semantics.

## Situation

Glory (Act 3) was recently wired into run sequencing: `_glory_rooms` exists in
`sts2_rl/rooms.py`, `act_has_rooms("glory")` is True, and a default
`RunState.start_run()` rolls a 3-act list ending in `glory` (verified:
`['underdocks', 'hive', 'glory']` under seed 3). But this wiring has never been
audited against the game source, and the docs still predate it. Your job is to
verify the integration end to end, fix what's wrong, and reconcile the docs.

## Tasks

1. **Audit `_glory_rooms` against the source.** Compare the weak/normal/elite/
   boss pools and `EncounterTag` values in `sts2_rl/rooms.py::_glory_rooms`
   against the Glory act model and encounter definitions in the game source
   (`src/Core/Models/Acts/` and `src/Core/Models/Encounters/*.cs` under the
   decompiled repo — find the Glory `ActModel` for `NumRooms`, weak-room count,
   elite count, boss pool, and any Glory-specific map/room parameters). Also
   check act-level knobs the sim may parameterize per act: room-count, "?"-odds
   behavior, boss selection. Fix discrepancies.

2. **Audit run-layer act-3 behavior.** In `sts2_rl/run.py`: `advance_act` into
   the final act must set `is_final_act=True` (it keys off
   `len(self.act_list) - 1`); the final boss must yield victory with **no
   rewards** (`RewardsSet.cs`: final-act boss → victory, no reward screen);
   confirm no heal and no boss relic on act transition (per `RunManager.
   EnterNextAct`). Check the `AscensionLevel.DOUBLE_BOSS` gating on the final
   act matches the source.

3. **Verify the RL envs cover a 3-act run.**
   - `sts2_rl/run_env.py`: the act-index one-hot must have room for act 3;
     floor normalization must not saturate over a 3-act run; Glory's events
     must all be present in `EVENT_IDS` (vocab-registered) and Glory monsters
     in `MONSTER_IDS`.
   - Run several seeded masked-random full episodes over `STS2RunEnv` and
     assert some reach act 3; assert an episode that beats the Glory boss sets
     `info["is_success"]` and terminal victory reward.
   - Check reward shaping still makes sense with 3 acts (per-floor/per-act
     bonuses in the env; the Act 2 boss must no longer look terminal).

4. **Reconcile stale docs.** `CLAUDE.md`'s "Known gaps" section still says
   Glory "is not yet wired into the run's map/room sequencing (rooms.py has no
   `_glory_rooms` ...)" and elsewhere "The Glory (Act-3) combat encounter
   roster proper is not started" — both false now. Update the section to the
   audited reality, including any approximations you found and kept (existing
   documented ones: Hex sets `is_ethereal` directly; the Queen re-telegraphs
   Burn Bright as Enrage at move resolution). Check `OBS_PLAN.md`, `ENEMIES.md`
   and `MODULES.md` for the same staleness.

5. **Tests.** Add/extend tests: `_glory_rooms` pool contents pinned against
   the source-audited lists; a seeded full-run test that reaches Glory and
   terminates; final-boss-no-rewards; `is_final_act` flag walk across
   `advance_act`. Full suite green: `py -m pytest test/ -q` (~1770 tests,
   ~4 min).

## Constraints

- Do not change obs/action layout unless the audit reveals a real coverage gap
  (e.g. act one-hot too small). If layout must change, bump
  `RUN_OBS_SCHEMA_VERSION` in `run_env.py` and note that old checkpoints will
  be refused by `train_torch.py`.
- `sts2_rl/vocab.json` is frozen/append-only: never reorder or delete entries;
  new ids append automatically via `sts2_rl/vocab.py`. Commit the file if it
  changes.
- One shared `random.Random` per combat/run is the sim's convention; don't add
  RNG draws to setup paths without checking seeded tests.
- `sts2_rl/curriculum_env.py` subclasses `STS2RunEnv` and shares its layout —
  it needs zero changes but its tests must stay green.
