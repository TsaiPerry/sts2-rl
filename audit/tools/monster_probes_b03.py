"""Executed evidence for monster content-audit batch 3 (the Underdocks batch:
cultists, fossil_stalker, the gremlin_merc family, haunted_ship,
lagavulin_matriarch, living_fog/gas_bomb, phantasmal_gardener, punch_construct,
seapunk, sewer_clam).

Every number a batch-3 record cites from a script comes from here, per the
shared audit contract's "if a number you record comes from a script, commit the
script" rule. Read-only: no probe mutates repo state.

Probes
------
  slot-order      LivingFog's GasBomb spawn: the sim appends the bomb to
                  CombatState.enemies while the game slots it into "bomb1" and
                  CombatManager.AddCreature re-sorts Enemies by slot index
                  (CombatManager.cs:846-851, CombatState.cs:495-501,
                  LivingFogNormal.cs:18). Prints the sim's enemy order and the
                  order the game's sort would produce, plus the observed
                  within-turn action order on both.
  bomb-followup   GasBomb's C# MoveState has NO FollowUpState (GasBomb.cs:62)
                  while the sim self-loops EXPLODE (living_fog.py:40). Executes
                  whether a GasBomb can ever survive its own EXPLODE to reach a
                  roll: enumerates every should_die listener in the sim.
  punchoff-hp     PunchConstruct.StartingHpReduction (PunchConstruct.cs:75-78)
                  reduces CURRENT hp only; the sim's Punch-Off encounter reduces
                  MAX hp (events/punch_off.py:27-28). Prints both sides.
  cultist-base    The `_Cultist` sim intermediate base: whether it is
                  instantiable, whether its machine holds any RandomBranchState
                  (i.e. whether monster_state_machine G7's zero-weight fuzz had
                  anything to fuzz for it), and what the two concrete
                  subclasses build.
  branch-args     The one RandomBranchState in this batch (FossilStalker's
                  "RAND"): prints the sim's stored branch tuples next to the C#
                  AddBranch call shapes, confirming the maxRepeats-not-weight
                  reading the seam calls this batch's counter-evidence.
  lagavulin-wake  LagavulinMatriarch.wake_up: the machine state, the current
                  move and the state log after a damage wake and after a
                  natural wake, next to what Creature.StunInternal would leave.
  graphs          Node-by-node dump of every batch-3 sim machine (state ->
                  follow-up / branches), for the graph comparison in each
                  record.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from sts2_rl.combat import CombatState  # noqa: E402
from sts2_rl.monsters.base import Encounter  # noqa: E402
from sts2_rl.monsters.state_machine import (  # noqa: E402
    ConditionalBranchState,
    MoveState,
    RandomBranchState,
)

# LivingFogNormal.cs:18 — the encounter's declared slot ORDER. GetNextSlot
# (EncounterModel.cs:245-248) hands out the first slot no live enemy occupies,
# and CombatManager.AddCreature (CombatManager.cs:846-851) then calls
# CombatState.SortEnemiesBySlotName (CombatState.cs:495-501), which sorts
# Enemies by Slots.IndexOf(SlotName).
_LIVING_FOG_SLOTS = ["bomb1", "bomb2", "bomb3", "bomb4", "bomb5", "livingFog"]


def _combat(encounter, seed=0):
    return CombatState(rng=random.Random(seed), encounter=encounter)


def slot_order() -> None:
    from sts2_rl.monsters.underdocks.living_fog import (
        LIVING_FOG_NORMAL,
        GasBomb,
        LivingFog,
    )

    cs = _combat(LIVING_FOG_NORMAL, seed=1)
    print("sim enemies at combat start:", [type(e).__name__ for e in cs.enemies])

    fog = cs.enemies[0]
    # Drive the fog straight to BLOAT: ADVANCED_GAS -> BLOAT.
    fog.take_turn(cs._ctx())          # ADVANCED_GAS
    print("after turn 1, telegraph:", fog._current_move.id)
    fog.take_turn(cs._ctx())          # BLOAT: spawns the bomb
    print("after turn 2, telegraph:", fog._current_move.id)

    order = [type(e).__name__ for e in cs.enemies]
    print("SIM   enemies after BLOAT :", order)

    # What the game's slot sort produces. The fog holds "livingFog"; the bomb
    # takes GetNextSlot == the first free slot == "bomb1".
    game_slots = {LivingFog: "livingFog", GasBomb: "bomb1"}
    game = sorted(
        cs.enemies, key=lambda e: _LIVING_FOG_SLOTS.index(game_slots[type(e)])
    )
    print("GAME  enemies after BLOAT :", [type(e).__name__ for e in game],
          "  (slot sort over", _LIVING_FOG_SLOTS, ")")
    print("sim  next enemy turn acts in order:",
          [type(e).__name__ for e in cs.enemies if not e.is_gone])
    print("game next enemy turn acts in order:",
          [type(e).__name__ for e in game])
    print("sim  index of the Gas Bomb:", order.index("GasBomb"))
    print("game index of the Gas Bomb:",
          [type(e).__name__ for e in game].index("GasBomb"))


def bomb_followup() -> None:
    import inspect

    from sts2_rl import powers as powers_mod
    from sts2_rl.monsters.underdocks.living_fog import LIVING_FOG_NORMAL, GasBomb

    cs = _combat(LIVING_FOG_NORMAL, seed=1)
    bomb = GasBomb(cs.hooks, random.Random(0))
    machine = bomb.machine
    st = machine.states["EXPLODE_MOVE"]
    print("sim GasBomb EXPLODE_MOVE.follow_up:",
          None if st.follow_up is None else st.follow_up.id)
    print("C#  GasBomb EXPLODE_MOVE FollowUpState: <none set> (GasBomb.cs:62)")

    # Can a GasBomb ever survive its own kill and reach a roll? Enumerate every
    # should_die implementer in the sim engine.
    impl = []
    for name, obj in vars(powers_mod).items():
        if isinstance(obj, type) and "should_die" in vars(obj):
            impl.append(f"powers.{name}")
    for pkg in ("relics", "potions"):
        try:
            mod = __import__(f"sts2_rl.{pkg}", fromlist=["*"])
        except Exception as exc:                                # pragma: no cover
            print(f"  ({pkg}: {exc})")
            continue
        for name, obj in vars(mod).items():
            if isinstance(obj, type) and "should_die" in vars(obj):
                impl.append(f"{pkg}.{name}")
    print("sim should_die implementers:", sorted(impl))
    for tok in sorted(impl):
        pkg, _, cls = tok.partition(".")
        mod = sys.modules.get(f"sts2_rl.{pkg}") or __import__(
            f"sts2_rl.{pkg}", fromlist=["*"])
        src = inspect.getsource(getattr(mod, cls).should_die)
        print(f"  {tok}.should_die ->", " ".join(src.split())[:160])


def punchoff_hp() -> None:
    from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
    from sts2_rl.monsters.underdocks.punch_construct import PunchConstruct

    cs = _combat(PUNCH_OFF_EVENT_ENCOUNTER, seed=4)
    for i, m in enumerate(cs.enemies):
        print(f"sim  punch-off construct {i}: hp={m.hp} max_hp={m.max_hp} "
              f"initial_move={m._current_move.id}")
    print("C#   PunchConstruct.MinInitialHp == MaxInitialHp ==",
          PunchConstruct.min_hp, "(PunchConstruct.cs:33-35, non-ascension)")
    print("C#   AfterAddedToRoom: SetCurrentHpInternal(Max(1, CurrentHp - "
          "StartingHpReduction)) -> MaxHp stays 55 (PunchConstruct.cs:75-78)")

    # Is the Punch-Off event reachable (rule 6, both sides)?
    from sts2_rl.events import UNDERDOCKS_EVENTS
    from sts2_rl.events.base import _EVENT_CLASSES
    print("punch_off in the sim's Underdocks event pool:",
          "punch_off" in UNDERDOCKS_EVENTS,
          "| registered class:", _EVENT_CLASSES.get("punch_off"))


def cultist_base() -> None:
    from sts2_rl.monsters.underdocks.cultists import (
        CULTISTS_NORMAL,
        CalcifiedCultist,
        DampCultist,
        _Cultist,
    )

    cs = _combat(CULTISTS_NORMAL, seed=2)
    try:
        _Cultist(cs.hooks, random.Random(0))
        print("_Cultist(hooks) constructed OK  <-- unexpected")
    except Exception as exc:
        print(f"_Cultist(hooks) raises {type(exc).__name__}: {exc}")
    print("_Cultist class attrs with values:",
          {k: v for k, v in vars(_Cultist).items()
           if not k.startswith("__") and not callable(v)})
    for cls in (CalcifiedCultist, DampCultist):
        m = cls(cs.hooks, random.Random(0))
        mach = m.machine
        kinds = {type(s).__name__ for s in mach.states.values()}
        print(f"{cls.__name__}: states={sorted(mach.states)} kinds={sorted(kinds)} "
              f"RandomBranchState count="
              f"{sum(1 for s in mach.states.values() if isinstance(s, RandomBranchState))}"
              f" initial={mach.current.id} state_log={[s.id for s in mach.state_log]}")


def branch_args() -> None:
    from sts2_rl.monsters.underdocks.fossil_stalker import (
        FOSSIL_STALKER_NORMAL,
    )

    cs = _combat(FOSSIL_STALKER_NORMAL, seed=3)
    mon = cs.enemies[0]
    for state in mon.machine.states.values():
        if isinstance(state, RandomBranchState):
            print(f"sim {state.id} branches (add order):")
            for b in state._branches:
                print("   ", {k: (v if not callable(v) else "<lambda>")
                              for k, v in b.items()})
    print("C#  FossilStalker.cs:58-60  AddBranch(LATCH,2) AddBranch(TACKLE,2) "
          "AddBranch(LASH,2)  -> overload #9 (int maxRepeats), weight 1f, "
          "CanRepeatXTimes  [RandomBranchState.cs:105]")


def lagavulin_wake() -> None:
    from sts2_rl.monsters.underdocks.lagavulin_matriarch import (
        LAGAVULIN_MATRIARCH_BOSS,
    )

    for mode in ("damage", "natural"):
        cs = _combat(LAGAVULIN_MATRIARCH_BOSS, seed=5)
        m = cs.enemies[0]
        print(f"--- {mode} wake ---")
        print("  before: current=", m.machine.current.id,
              "move=", m._current_move.id,
              "log=", [s.id for s in m.machine.state_log],
              "asleep=", "asleep" in m.powers, "plating=", "plating" in m.powers)
        m.wake_up(stunned=(mode == "damage"))
        print("  after : current=", m.machine.current.id,
              "move=", m._current_move.id,
              "log=", [s.id for s in m.machine.state_log],
              "stunned=", m.stunned, "is_awake=", m.is_awake)
    print("C#  damage wake: CreatureCmd.Stun(owner, WakeUpMove, 'SLASH_MOVE') "
          "(AsleepPower.cs:33) -> synthetic MoveState('STUNNED', ...) with "
          "FollowUpStateId='SLASH_MOVE'; the post-stun roll APPENDS SLASH_MOVE "
          "to StateLog (Creature.cs:537-542, monster_state_machine step 40).")
    print("C#  natural wake: WakeUpMove called directly (AsleepPower.cs:54); "
          "the machine is untouched and SLEEP_BRANCH resolves to SLASH_MOVE on "
          "the next roll (LagavulinMatriarch.cs:173-174).")
    print("Lagavulin's only branch is a ConditionalBranchState reading "
          "HasPower<AsleepPower>, never StateLog -> the missing log entry moves "
          "no weight (monster_state_machine G4, settled, not re-verdicted).")


_BATCH = [
    ("calcified_cultist", "underdocks.cultists", "CalcifiedCultist"),
    ("damp_cultist", "underdocks.cultists", "DampCultist"),
    ("fossil_stalker", "underdocks.fossil_stalker", "FossilStalker"),
    ("gremlin_merc", "underdocks.gremlin_merc", "GremlinMerc"),
    ("sneaky_gremlin", "underdocks.gremlin_merc", "SneakyGremlin"),
    ("fat_gremlin", "underdocks.gremlin_merc", "FatGremlin"),
    ("haunted_ship", "underdocks.haunted_ship", "HauntedShip"),
    ("lagavulin_matriarch", "underdocks.lagavulin_matriarch",
     "LagavulinMatriarch"),
    ("living_fog", "underdocks.living_fog", "LivingFog"),
    ("gas_bomb", "underdocks.living_fog", "GasBomb"),
    ("phantasmal_gardener", "underdocks.phantasmal_gardener",
     "PhantasmalGardener"),
    ("punch_construct", "underdocks.punch_construct", "PunchConstruct"),
    ("seapunk", "underdocks.seapunk", "Seapunk"),
    ("sewer_clam", "underdocks.sewer_clam", "SewerClam"),
]


def graphs() -> None:
    from sts2_rl.monsters.underdocks.cultists import CULTISTS_NORMAL

    for unit, mod_name, cls_name in _BATCH:
        mod = __import__(f"sts2_rl.monsters.{mod_name}", fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        cs = _combat(CULTISTS_NORMAL, seed=7)
        mon = cls(cs.hooks, random.Random(0))
        mach = mon.machine
        print(f"== {unit} ({cls_name}) initial={mach.current.id} "
              f"log={[s.id for s in mach.state_log]} "
              f"telegraph={mon._current_move.id}")
        for sid, st in mach.states.items():
            if isinstance(st, MoveState):
                fu = None if st.follow_up is None else st.follow_up.id
                print(f"   MoveState {sid:24s} -> {fu}   intent="
                      f"{st.intent.move_type.value}"
                      f"{'/' + '+'.join(a.value for a in st.intent.also) if st.intent.also else ''}"
                      f" dmg={st.intent.damage}x{st.intent.hits}")
            elif isinstance(st, RandomBranchState):
                print(f"   RandomBranch {sid}: {st._branches}")
            elif isinstance(st, ConditionalBranchState):
                print(f"   CondBranch {sid}: {[b[0] for b in st._branches]}")


PROBES = {
    "slot-order": slot_order,
    "bomb-followup": bomb_followup,
    "punchoff-hp": punchoff_hp,
    "cultist-base": cultist_base,
    "branch-args": branch_args,
    "lagavulin-wake": lagavulin_wake,
    "graphs": graphs,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", choices=sorted(PROBES) + ["all"])
    ns = ap.parse_args(argv)
    names = sorted(PROBES) if ns.probe == "all" else [ns.probe]
    for n in names:
        print(f"===== {n} =====")
        PROBES[n]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
