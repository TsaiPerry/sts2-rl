"""Executed witnesses for batch E7's `encounter` kind audit (Underdocks, first
half: corpse_slugs_normal/weak, cultists, fossil_stalker, gremlin_merc,
haunted_ship, lagavulin_matriarch, living_fog, phantasmal_gardeners,
punch_construct).

Each function is a standalone executed witness cited by
`audit/records/encounter/<unit>.json`. Run: py audit/tools/encounter_probes_e7.py [probe]
(no arg = every probe).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def gremlin_merc_gold_proportion() -> None:
    """`GremlinMercNormal.CalculateGoldProportion` (GremlinMercNormal.cs:58-69):
    if the Fat Gremlin escaped AND any gold was stolen this combat, the
    override returns 0.0 -- ZERO monster gold, not the room's normal 10-20
    range. `EncounterModel.CalculateGoldProportion`'s own base formula
    (`1 - EscapedCreatures.Count / SpawnedEnemies.Count`, EncounterModel.cs:
    373-376) is not ported anywhere in sts2_rl either (`grep -rn
    CalculateGoldProportion|gold_proportion sts2_rl/` finds only the unused
    `gold_proportion` kwarg default on `generate_combat_rewards`/
    `RunState.generate_combat_rewards`, always 1.0), and the one production
    call site, `driver.py:_run_combat`'s `run.generate_combat_rewards(room_type,
    encounter=encounter)`, never supplies one.

    This reproduces test_underdocks.py::TestGremlinMercThievery's own
    `test_fled_fat_gremlin_keeps_gold_lost` scenario (Fat Gremlin escapes after
    the Merc stole 20 gold) one step further, into the reward screen that test
    never reaches."""
    from sts2_rl import DamageCmd
    from sts2_rl.monsters.underdocks import GREMLIN_MERC_NORMAL
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.gold = 100
    cs = run.create_combat(GREMLIN_MERC_NORMAL)
    cs.end_turn()  # GIMME -> Steal() takes 20
    DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)  # kill Merc
    fat = cs.enemies[2]
    cs.end_turn()  # Sneaky+Fat SPAWNED_MOVE (wake-up, no-op)
    cs.end_turn()  # Sneaky TACKLEs, Fat FLEEs
    assert fat.escaped, "setup failed: Fat Gremlin did not escape"
    assert cs.gold_stolen == 20, f"setup failed: gold_stolen={cs.gold_stolen}"
    run.finish_combat(cs, room_type=RoomType.MONSTER)
    # The production call, as `driver._run_combat` / `conformance.runner` make
    # it: `CombatRoom.OnCombatEnded` computes the proportion off the finished
    # combat and the reward set scales the Monster range by it.
    proportion = GREMLIN_MERC_NORMAL.calculate_gold_proportion(cs)
    rewards = run.generate_combat_rewards(
        RoomType.MONSTER, encounter=GREMLIN_MERC_NORMAL,
        gold_proportion=proportion)
    print(f"Fat Gremlin escaped: {fat.escaped}; gold stolen this combat: 20")
    print(f"CalculateGoldProportion -> {proportion}")
    print(f"Sim reward-screen gold: {rewards.gold} (Monster range is 10-20)")
    print("Game (GremlinMercNormal.CalculateGoldProportion): FatGremlin "
          "escaped AND GoldWasStolen -> proportion 0.0 -> reward-screen "
          "gold MUST be 0")
    if rewards.gold > 0:
        print("MISMATCH -- LIVE: sim over-awards gold in a scenario the game "
              "pays zero for.")
    else:
        print("MATCH: the reward screen pays 0, as the override requires.")


def gremlin_merc_slot_dormancy() -> None:
    """`GremlinMercNormal.GenerateMonsters` returns `(GremlinMerc, "merc")`
    and `SurprisePower.AfterDeath` adds the two spawns with `"sneaky"`/`"fat"`
    (SurprisePower.cs:23-24) -- three non-null SlotNames. The sim's
    `GREMLIN_MERC_NORMAL = Encounter(monster_classes=[GremlinMerc])` sets no
    `monster_slots`, and `SurprisePower.on_death` (powers.py) calls
    `CreatureCmd.add` with no `slot_name=` for either spawn, so all three
    `Creature.slot_name`s stay `None` on the sim side.

    Dormancy claim: `GremlinMercNormal` does not override `Slots` (inherits
    EncounterModel's empty default), so `CombatState.SortEnemiesBySlotName`'s
    comparator (`Encounter.Slots.IndexOf(SlotName)`) returns -1 for EVERY
    creature in this encounter regardless of its SlotName string -- the sort
    is a no-op on the game side too. This prints the sim's final enemy order
    (which the missing slot_name cannot have perturbed, since
    `sort_enemies_by_slot_name` is a no-op whenever `encounter.slots` is
    empty -- combat.py's own `sort_enemies_by_slot_name`) to confirm nothing
    downstream reads slot_name for this encounter."""
    from sts2_rl import DamageCmd
    from sts2_rl.monsters.underdocks import GREMLIN_MERC_NORMAL
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    cs = run.create_combat(GREMLIN_MERC_NORMAL)
    DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)  # kill Merc
    names = [type(e).__name__ for e in cs.enemies]
    slots = [e.slot_name for e in cs.enemies]
    print(f"encounter.slots (the named row): {GREMLIN_MERC_NORMAL.slots!r}")
    print(f"enemies after Surprise fires: {names}")
    print(f"their slot_name values: {slots}")
    assert all(s is None for s in slots), "slot_name unexpectedly set"
    assert names == ["GremlinMerc", "SneakyGremlin", "FatGremlin"], names
    print("encounter.slots is empty -> sort_enemies_by_slot_name is a no-op "
          "regardless of slot_name -> DORMANT: the dropped 'merc'/'sneaky'/"
          "'fat' slot labels have no reachable observer in this build.")


def corpse_slug_draw_count() -> None:
    """`CorpseSlug.EnsureCorpseSlugsStartWithDifferentMoves` (CorpseSlug.cs:
    135-144) draws exactly ONE `rng.NextInt(3)` off the per-encounter Rng,
    regardless of slug count (3 for Normal, 2 for Weak), and staggers each
    slug's StarterMoveIdx by +1 from that single draw. Confirms the sim's
    `CorpseSlugsEncounter.create_monsters` draws exactly once on
    `selection_rng` for both encounters, by counting calls with a wrapping
    stub."""
    from sts2_rl.monsters.underdocks.corpse_slug import (
        CORPSE_SLUGS_NORMAL, CORPSE_SLUGS_WEAK,
    )
    from sts2_rl.hooks import HookSystem

    class _CountingRng:
        def __init__(self, real):
            self._real = real
            self.calls = 0

        def next_int(self, n):
            self.calls += 1
            return self._real.next_int(n)

    from sts2_rl.rng import make_encounter_rng
    for enc, expected_count in ((CORPSE_SLUGS_NORMAL, 3), (CORPSE_SLUGS_WEAK, 2)):
        real = make_encounter_rng(2221240958, 6, enc.entry)
        wrapped = _CountingRng(real)
        hooks = HookSystem()
        monsters = enc.create_monsters(hooks, random.Random(0), wrapped)
        print(f"{enc.id}: {len(monsters)} monsters (expected {expected_count}), "
              f"{wrapped.calls} draw(s) on the per-encounter Rng (game draws "
              f"exactly 1 regardless of count)")
        assert len(monsters) == expected_count
        assert wrapped.calls == 1, f"expected 1 draw, got {wrapped.calls}"


PROBES = {
    "gremlin-gold": gremlin_merc_gold_proportion,
    "gremlin-slot": gremlin_merc_slot_dormancy,
    "corpse-slug-draws": corpse_slug_draw_count,
}


def main() -> None:
    names = sys.argv[1:] or list(PROBES)
    for name in names:
        fn = PROBES.get(name)
        if fn is None:
            print(f"unknown probe {name!r}; choices: {sorted(PROBES)}")
            continue
        print(f"=== {name} ===")
        fn()
        print()


if __name__ == "__main__":
    main()
