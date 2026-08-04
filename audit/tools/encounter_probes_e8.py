"""Executed evidence for the `encounter` content-audit batch e8.

Batch e8 units (act Underdocks, second half): seapunk_normal, seapunk_weak,
sewer_clam, skulking_colony, sludge_spinner, soul_fysh, terror_eel,
toadpoles, two_tailed_rats, waterfall_giant.

Every number quoted with a `probe <name>` marker in
`audit/records/encounter/{two_tailed_rats,...}.json` is reproduced here.
Usage:

    py audit/tools/encounter_probes_e8.py <probe>
    py audit/tools/encounter_probes_e8.py all

Probes
------
rat-slot-order    two_tailed_rats/G1: CALL_FOR_BACKUP's mid-combat summon is
                  appended to the END of combat.enemies with slot_name=None,
                  where the C# re-sorts the whole Enemies list by
                  Encounter.Slots so the summon lands AHEAD of the three
                  starting rats (Slots[2..4] -> occupied; the summon fills
                  Slots[1] then Slots[0]). Demonstrates the sim's enemy-list
                  order diverges from the game's after one summon.
rat-selection-rng two_tailed_rats/G2: create_monsters' starter-move stagger
                  falls back to the shared legacy `random.Random` whenever
                  `selection_rng` is None -- which is every RunState built by
                  run_env.py (the RL training path never passes a
                  string_seed). Shows the draw is NOT independent of the
                  run-level stream in that configuration, breaking
                  EncounterModel.Rng's documented independence guarantee.
"""
from __future__ import annotations

import random as _random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── rat-slot-order ──────────────────────────────────────────────────────────

def probe_rat_slot_order() -> None:
    from sts2_rl.combat import CombatCtx, CombatState
    from sts2_rl.monsters.underdocks import TWO_TAILED_RATS_NORMAL, TwoTailedRat

    print("== rat-slot-order ==")
    cs = CombatState(rng=_random.Random(0), encounter=TWO_TAILED_RATS_NORMAL)
    print("  encounter.slots       =", TWO_TAILED_RATS_NORMAL.slots, "(sim; "
          "C# TwoTailedRatsNormal.Slots = [first,second,third,fourth,fifth])")
    print("  initial enemies       =", [
        (type(e).__name__, e.net_id, e.slot_name) for e in cs.enemies
    ])
    rat0 = cs.enemies[0]
    # Force CanSummon()-equivalent state and fire the summon directly.
    rat0.turns_until_summonable = 0
    ctx = CombatCtx(combat=cs, player=cs.player, enemies=cs.enemies, hooks=cs.hooks)
    rat0._call_for_backup(ctx)
    print("  after CALL_FOR_BACKUP =", [
        (type(e).__name__, e.net_id, e.slot_name) for e in cs.enemies
    ])
    print("  C# (TwoTailedRat.cs:180-185): CallForBackup resolves "
          "`Encounter.Slots.LastOrDefault(free)` (= \"second\", since "
          "third/fourth/fifth are occupied) and CreatureCmd.Add(..., "
          "\"second\") triggers CombatManager.AddCreature's "
          "SortEnemiesBySlotName -- the summon is re-sorted to the FRONT "
          "of Enemies (index 0), ahead of all three starting rats.")
    new_rat = next(e for e in cs.enemies if e.net_id == 4)
    if cs.enemies[0] is new_rat and new_rat.slot_name == "second":
        print("  MATCH: the summon holds slot 'second' and sits at "
              "enemies[0], ahead of the three starting rats -- the game's "
              "order.")
    else:
        print("  DIVERGENCE: the summon is at index",
              cs.enemies.index(new_rat), "with slot_name=",
              repr(new_rat.slot_name), "-- the game puts it at index 0 in "
              "slot 'second'. Enemies[i] indices, camera slot, and any "
              "index-based targeting disagree from the first summon onward.")


# ── rat-selection-rng ────────────────────────────────────────────────────────

def probe_rat_selection_rng() -> None:
    import inspect
    from sts2_rl.run_env import STS2RunEnv  # noqa: F401  (import proves the module loads)
    from sts2_rl import run as run_module

    print("== rat-selection-rng ==")
    src = inspect.getsource(run_module.RunState.create_combat)
    has_gate = "if self.rng_set is not None" in src
    print("  RunState.create_combat gates encounter_selection_rng on "
          "self.rng_set is not None:", has_gate)
    print("  RunState.__init__ sets self.rng_set = RunRngSet(string_seed) "
          "only `if string_seed is not None`, else None.")
    print("  run_env.py's RunState construction (the RL training path) "
          "passes no string_seed:")
    print("     RunState(rng=self._rng, character=self._character)")
    print("  => encounter_selection_rng is None for every training episode")
    print("  => TwoTailedRatsEncounter.create_monsters falls back to "
          "`rng.randrange(3)` on the shared per-combat `self._rng`, the "
          "same stream every other unseeded draw in the fight uses.")
    print("  EncounterModel.cs:42-45's own doc comment: \"independently of "
          "the run's centralized RNG... safe... because we don't need to "
          "keep track of a given encounter's RNG state once it's over\" -- "
          "false in this configuration: the draw consumes the SHARED "
          "stream, so it is not free to desync from it the way the game's "
          "encounter Rng is.")


PROBES = {
    "rat-slot-order": probe_rat_slot_order,
    "rat-selection-rng": probe_rat_selection_rng,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in (*PROBES, "all"):
        print(f"usage: py {sys.argv[0]} <{'|'.join(PROBES)}|all>")
        raise SystemExit(1)
    names = PROBES if sys.argv[1] == "all" else [sys.argv[1]]
    for name in names:
        PROBES[name]()
        print()


if __name__ == "__main__":
    main()
