"""Executed evidence for encounter content-audit batch E2.

Units: overgrowth_crawlers, phrog_parasite, ruby_raiders,
shrinker_beetle_weak, slimes_normal, slimes_weak, slithering_strangler,
snapping_jaxfruit, the_kin, vantom, vine_shambler.

    py audit/tools/encounter_probes_e2.py <probe>

Probes
    legacy-shared-stream   whether the monster-composition draw is
                           independent of the shared per-combat
                           `random.Random` on the SEEDLESS (no string-seed)
                           path. It was not: `create_monsters` took its
                           `selection_rng=None` arm and drew off the same
                           object CombatRng.legacy hands out for shuffle /
                           monster_ai / card_gen. It now re-composes with the
                           shared stream advanced 0/1/2/3/7 draws and reports
                           whether the roster moves.
    parity-draw-counts     runs the parity path (a real Rng, not the shared
                           stream) for ruby_raiders / slimes_normal /
                           slimes_weak / slithering_strangler and reports the
                           roster + the number of Rng draws each consumed, to
                           cross-check the by-hand count against the C#.
    kin-phrog-slots        instantiates phrog_parasite_elite and the_kin_boss
                           and shows every enemy's `.slot_name` plus each
                           Encounter's `.slots` row, to support the
                           encounter/_slot_row_unpopulated dormancy claim.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sts2_rl.combat import CombatState
from sts2_rl.monsters.overgrowth import ENCOUNTERS as OG
from sts2_rl.rng import Rng


def legacy_shared_stream() -> None:
    """The composition draw's independence, on the SEEDLESS path.

    The question is not whether the seedless combat's other streams are one
    shared `random.Random` — they still are, by design — but whether the
    monster-composition draw rides that shared object. It did. The witness is
    therefore: advance the shared generator, and see whether the encounter
    composes differently.
    """
    import random

    from sts2_rl.run import RunState

    def signature(encounter, shared_draws):
        rng = random.Random(4)
        run = RunState(rng=rng)
        for _ in range(shared_draws):
            rng.random()
        run.total_floor = 6
        combat = run.create_combat(encounter)
        return [(type(m).__name__, getattr(m, "_starter_move_idx", None))
                for m in combat.enemies]

    for key in ("ruby_raiders", "slimes_normal", "slimes_weak", "slithering_strangler"):
        enc = OG[key]
        base = signature(enc, 0)
        moved = [signature(enc, n) for n in (1, 2, 3, 7)]
        independent = all(s == base for s in moved)
        combat = CombatState(encounter=enc)
        print(f"{key}: shared-stream identity inside the combat "
              f"(combat._rng is monster_ai is shuffle): "
              f"{combat._rng is combat.combat_rng.monster_ai is combat.combat_rng.shuffle}"
              f" | composition independent of that stream: {independent}")
        if not independent:
            print(f"    base={base}  after shared draws={moved}")
    print()
    print("Conclusion: RunState.create_combat now seeds a per-encounter Rng on "
          "BOTH paths -- make_encounter_rng(rng_set.seed or the run's derived "
          "seedless seed, total_floor, entry) -- so `create_monsters` never "
          "takes its `selection_rng=None` arm in production and the "
          "composition no longer moves when the shared stream does. The other "
          "seedless streams remain one object; that is CombatRng.legacy's own "
          "design and not this mechanism.")


def parity_draw_counts() -> None:
    for key, expect_min, expect_max in (
        ("ruby_raiders", 3, 3),
        ("slimes_normal", 1, 1),
        ("slimes_weak", 3, 3),
        ("slithering_strangler", 1, 3),
    ):
        rng = Rng(seed=12345, name=key.upper())
        draws = {"n": 0}
        orig_next_item = rng.next_item
        orig_next_bool = rng.next_bool

        def counted_item(items, _orig=orig_next_item):
            draws["n"] += 1
            return _orig(items)

        def counted_bool(_orig=orig_next_bool):
            draws["n"] += 1
            return _orig()

        rng.next_item = counted_item
        rng.next_bool = counted_bool
        combat = CombatState(encounter=OG[key], encounter_selection_rng=rng)
        roster = [type(m).__name__ for m in combat.enemies]
        print(f"{key}: roster={roster} draws={draws['n']} "
              f"(expected {expect_min}-{expect_max})")


def kin_phrog_slots() -> None:
    for key in ("phrog_parasite", "the_kin"):
        combat = CombatState(encounter=OG[key])
        print(f"{key}: encounter.slots={getattr(combat.encounter, 'slots', None)!r} "
              f"monster_slots={getattr(combat.encounter, 'monster_slots', None)!r}")
        for e in combat.enemies:
            print(f"    {type(e).__name__}: slot_name={e.slot_name!r}")

    # Now force the phrog_parasite Wriggler spawn (InfestedPower.on_death) and
    # show the spawned creatures' slot_name too.
    from sts2_rl.monsters.overgrowth.phrog_parasite import Wriggler
    combat = CombatState(encounter=OG["phrog_parasite"])
    parasite = combat.enemies[0]
    from sts2_rl.powers import InfestedPower
    from sts2_rl.cmds import PowerCmd
    PowerCmd.apply(combat.hooks, parasite, InfestedPower, 4)
    parasite.hp = 0
    combat.hooks.on_death(parasite, False)
    print("after InfestedPower.on_death:")
    for e in combat.enemies:
        print(f"    {type(e).__name__}: slot_name={e.slot_name!r}")


PROBES = {
    "legacy-shared-stream": legacy_shared_stream,
    "parity-draw-counts": parity_draw_counts,
    "kin-phrog-slots": kin_phrog_slots,
}


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PROBES:
        print(f"usage: py {sys.argv[0]} <{'|'.join(PROBES)}>")
        raise SystemExit(1)
    PROBES[sys.argv[1]]()
