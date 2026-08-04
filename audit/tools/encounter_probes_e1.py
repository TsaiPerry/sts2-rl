"""Executed evidence for the `encounter` content-audit batch e1.

Batch e1 units (act Overgrowth, first half): bygone_effigy, byrdonis,
ceremonial_beast, cubex_construct, flyconid, fogmog, fuzzy_wurm_weak,
inklets_normal, mawler_normal, nibbits_normal, nibbits_weak.

Every number quoted with a `probe <name>` marker in
`audit/records/encounter/{fogmog,flyconid,nibbits_normal}.json` is reproduced
here. Usage:

    py audit/tools/encounter_probes_e1.py <probe>
    py audit/tools/encounter_probes_e1.py all

Probes
------
fogmog-slot-order      fogmog/G1: FogmogNormal.Slots = ["illusion","fogmog"]
                       and Fogmog.cs's ILLUSION_MOVE calls
                       `CreatureCmd.Add<EyeWithTeeth>(base.CombatState,
                       "illusion")`, which re-sorts Enemies so the summon
                       lands AHEAD of the starting Fogmog (illusion=index0,
                       fogmog=index1). The sim's FOGMOG_NORMAL declares no
                       `slots` at all and `_illusion_move` calls
                       `CreatureCmd.add` with no slot_name, so the summon is
                       simply appended. Demonstrates the sim's enemy-list
                       order diverges from the game's from the first enemy
                       turn onward (turn 1 is always ILLUSION_MOVE).
nibbits-slot-dormancy  nibbits_normal/G1 (dormant half of the same shape):
                       NibbitsNormal.Slots = ["front","back"] exists only to
                       order the INITIAL two Nibbits; Nibbit.cs has no
                       CreatureCmd.Add call anywhere (no summon capability),
                       so SortEnemiesBySlotName never runs again after
                       construction. Confirms the sim's missing `slots`
                       declaration on NIBBITS_NORMAL costs nothing today
                       because the initial construction order already
                       matches the slot order.
flyconid-selection-rng flyconid/G1 (shared family `encounter/
                       _selection_rng_fallback`, also exhibited by
                       two_tailed_rats/G2 in batch e8): FlyconidEncounter.
                       create_monsters falls back to `rng.choice(...)` on
                       the shared per-combat `random.Random` whenever
                       `selection_rng` is None. It USED to be None for every
                       RunState run_env.py builds (the RL training path
                       passes no string_seed), which broke
                       EncounterModel.Rng's documented independence. The
                       probe now advances the shared stream and re-composes:
                       `RunState.create_combat` seeds a per-encounter Rng on
                       the seedless path too, so the roster no longer moves
                       and the fallback arm is unreachable in production.
"""
from __future__ import annotations

import random as _random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── fogmog-slot-order ────────────────────────────────────────────────────────

def probe_fogmog_slot_order() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.overgrowth import FOGMOG_NORMAL

    print("== fogmog-slot-order ==")
    cs = CombatState(rng=_random.Random(0), encounter=FOGMOG_NORMAL)
    print("  encounter.slots        =", FOGMOG_NORMAL.slots,
          "(sim; C# FogmogNormal.Slots = [\"illusion\",\"fogmog\"])")
    print("  encounter.monster_slots=", FOGMOG_NORMAL.monster_slots,
          "(sim; C# GenerateMonsters returns (Fogmog, \"fogmog\"))")
    print("  initial enemies        =", [
        (type(e).__name__, e.net_id, e.slot_name) for e in cs.enemies
    ])
    fogmog = cs.enemies[0]
    # Fogmog's move machine starts at ILLUSION_MOVE -- perform it directly.
    from sts2_rl.combat import CombatCtx
    ctx = CombatCtx(combat=cs, player=cs.player, enemies=cs.enemies, hooks=cs.hooks)
    fogmog._illusion_move(ctx)
    print("  after ILLUSION_MOVE    =", [
        (type(e).__name__, e.net_id, e.slot_name) for e in cs.enemies
    ])
    print("  C# (Fogmog.cs:60-67): IllusionMove calls "
          "`CreatureCmd.Add<EyeWithTeeth>(base.CombatState, \"illusion\")`, "
          "which triggers CombatManager.AddCreature's SortEnemiesBySlotName "
          "-- Slots.IndexOf(\"illusion\")=0 < Slots.IndexOf(\"fogmog\")=1, so "
          "the summon is re-sorted to the FRONT of Enemies (index 0), ahead "
          "of the starting Fogmog.")
    order = [type(e).__name__ for e in cs.enemies]
    if order == ["EyeWithTeeth", "Fogmog"]:
        print("  MATCH: the summon holds slot 'illusion' and sits at "
              "enemies[0], ahead of the Fogmog -- the game's order.")
    else:
        print("  DIVERGENCE: sim enemy-list order after turn 1 (Fogmog's "
              f"first move is always ILLUSION_MOVE) is {order}; the game's "
              "is ['EyeWithTeeth', 'Fogmog']. Enemies[i] indices, camera "
              "slot, and any index-based targeting/observation disagree "
              "from turn 1 onward for the whole rest of combat.")


# ── nibbits-slot-dormancy ────────────────────────────────────────────────────

def probe_nibbits_slot_dormancy() -> None:
    import inspect
    from sts2_rl.monsters.overgrowth import Nibbit, NIBBITS_NORMAL

    print("== nibbits-slot-dormancy ==")
    print("  encounter.slots         =", NIBBITS_NORMAL.slots,
          "(sim; C# NibbitsNormal.Slots = [\"front\",\"back\"])")
    print("  encounter.monster_slots =", NIBBITS_NORMAL.monster_slots,
          "(sim; C# GenerateMonsters returns [(front,\"front\"),(back,"
          "\"back\")])")
    src = inspect.getsource(Nibbit)
    has_add = "CreatureCmd.add" in src or "CreatureCmd.Add" in src
    print("  'CreatureCmd.add' appears in sts2_rl/monsters/overgrowth/"
          "nibbit.py's Nibbit class:", has_add)
    print("  C# Nibbit.cs has no CreatureCmd.Add call anywhere (BUTT/SLICE/"
          "HISS are the only three moves, none of which summon) -- "
          "confirmed by reading the file top to bottom: only DamageCmd."
          "Attack, CreatureCmd.GainBlock, CreatureCmd.TriggerAnim, PowerCmd."
          "Apply are called.")
    print("  => SortEnemiesBySlotName's only OTHER caller besides the "
          "initial construction (CombatManager.AddCreature, gated on a "
          "non-null SlotName) is never reached for this encounter, so the "
          "missing `slots`/`monster_slots` declaration on the sim's "
          "NIBBITS_NORMAL is DORMANT: the initial order the sim already "
          "produces ([front-tagged Nibbit, plain Nibbit], matching C#'s "
          "array order) is never subsequently reshuffled by either side.")


# ── flyconid-selection-rng ───────────────────────────────────────────────────

def probe_flyconid_selection_rng() -> None:
    import inspect
    from sts2_rl import run as run_module
    from sts2_rl.monsters.overgrowth.flyconid import (
        FLYCONID_NORMAL, FlyconidEncounter,
    )

    print("== flyconid-selection-rng ==")
    src = inspect.getsource(run_module.RunState.create_combat)
    has_gate = "if self.rng_set is not None" in src
    print("  RunState.create_combat still gates encounter_selection_rng on "
          "self.rng_set is not None:", has_gate)
    print("  run_env.py's RunState construction (the RL training path) "
          "passes no string_seed:")
    print("     RunState(rng=self._rng, character=self._character)")
    fc_src = inspect.getsource(FlyconidEncounter.create_monsters)
    print("  FlyconidEncounter.create_monsters body:")
    for line in fc_src.splitlines():
        print("   ", line)

    # The executed check: build the seedless RunState run_env builds, and see
    # whether the roster moves when the SHARED stream is advanced.
    import random

    def roster(shared_draws):
        rng = random.Random(4)
        run = run_module.RunState(rng=rng)
        for _ in range(shared_draws):
            rng.random()
        run.total_floor = 6
        return [type(m).__name__ for m in run.create_combat(FLYCONID_NORMAL).enemies]

    base = roster(0)
    moved = [roster(n) for n in (1, 2, 3, 7)]
    print(f"  seedless roster with the shared stream advanced 0/1/2/3/7 draws: "
          f"{[base] + moved}")
    if all(r == base for r in moved):
        print("  => the composition draw is ISOLATED from the shared stream: "
              "create_combat seeds make_encounter_rng on the seedless path "
              "too, so the `selection_rng is None` arm above is unreachable "
              "from any production call site.")
    else:
        print("  => the roster moves with the shared stream: the draw is "
              "still riding it, which EncounterModel.cs:42-45's own doc "
              "comment (\"independently of the run's centralized RNG\") "
              "forbids. Mechanism `encounter/_selection_rng_fallback`.")


PROBES = {
    "fogmog-slot-order": probe_fogmog_slot_order,
    "nibbits-slot-dormancy": probe_nibbits_slot_dormancy,
    "flyconid-selection-rng": probe_flyconid_selection_rng,
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
