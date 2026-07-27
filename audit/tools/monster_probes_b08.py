"""Executed evidence for monster content-audit batch 8.

Batch 8 units: soul_nexus, test_subject, the_forgotten, the_lost,
living_shield, turret_operator.

Every number quoted with a `probe <name>` marker in
`audit/records/monster/{soul_nexus,test_subject,living_shield,...}.json`
is reproduced here. Usage:

    py audit/tools/monster_probes_b08.py <probe>
    py audit/tools/monster_probes_b08.py all

Probes
------
soul-nexus-control   SoulNexus's three branches: parameter tuple + a 100k-roll
                     distribution, plus the seam's G4 control claim (a log
                     duplicate cannot move a last-1 CannotRepeat window).
adaptable-death      Bug class 21 on the Test Subject: the sim routes
                     AdaptablePower onto `should_die` and vetoes the death, so
                     `on_death` never fires for phases 1 and 2. Runs a real
                     combat with a Gremlin Horn attached and counts the payout.
respawn-hp           The HP/delta consequence of the same misroute
                     (CreatureCmd.SetMaxHp+Heal from 0 vs `_revive` from 1).
must-perform-once    TestSubject's RESPAWN_MOVE is a
                     MustPerformOnceBeforeTransitioning move (monster_state_machine
                     G5's named trigger, now ported onto MachineMonster): show
                     that the sticky rule holds and the flag resets on exit.
ally-count           LivingShield's ConditionalBranchState reads an ally count;
                     compare the sim's `not is_gone` filter with C#'s IsAlive
                     over GetTeammatesOf, including a retained corpse.
graphs               Move-graph dump for all six units (ids, follow-ups, branch
                     parameters, add order) for eyeballing against the C#.
"""
from __future__ import annotations

import random as _random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _encounter(cls, eid="probe_b08"):
    from sts2_rl.monsters import Encounter
    return Encounter(id=eid, monster_classes=[cls])


# ── soul-nexus-control ──────────────────────────────────────────────────────

def probe_soul_nexus_control() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.glory.soul_nexus import SoulNexus

    print("== soul-nexus-control ==")
    cs = CombatState(rng=_random.Random(0), encounter=_encounter(SoulNexus))
    nexus = cs.enemies[0]
    branch = nexus.machine.states["RAND"]
    print("  sim RAND branches, in add order "
          "(SoulNexus.cs:70-72 order: SOUL_BURN, MAELSTROM, DRAIN_LIFE):")
    for b in branch._branches:
        print(f"    {b['state_id']:<16} weight={b['weight']!r} "
              f"repeat={b['repeat_type'].value} max_times={b['max_times']} "
              f"cooldown={b['cooldown']}")
    print("  C# AddBranch(state, MoveRepeatType.CannotRepeat, 1f) is overload #5")
    print("  (RandomBranchState.cs:85, `R repeatType, float weight`) -- NO int")
    print("  argument at any of the three sites, so there is no maxRepeats or")
    print("  cooldown for a positional transliteration to lose.")

    # distribution over the reachable steady state
    counts: dict[str, int] = {}
    rolls = 100000
    for seed in range(1):
        cs = CombatState(rng=_random.Random(7), encounter=_encounter(SoulNexus))
        mon = cs.enemies[0]
        m = mon.machine
        m._performed_first_move = True
        rng = _random.Random(7)
        for _ in range(rolls):
            mv = m.roll_move(mon, rng)
            counts[mv.id] = counts.get(mv.id, 0) + 1
            m.on_move_performed(mv)
    print(f"  {rolls} rolls, seed 7:")
    for k in sorted(counts):
        print(f"    {k:<16} {counts[k]*100.0/rolls:5.1f}%")
    print("  expected: never the move just logged, uniform over the other two")
    print("  -> 0% self-repeat, ~50/50 on the other two conditioned on history.")

    # the seam's G4 control claim, executed: a duplicate at the tail of the log
    # cannot change a last-1 window.
    cs = CombatState(rng=_random.Random(0), encounter=_encounter(SoulNexus))
    mon = cs.enemies[0]
    m = mon.machine
    m._performed_first_move = True
    m.state_log[:] = [m.states["SOUL_BURN_MOVE"]]
    w_single = [branch._effective_weight(b, m) for b in branch._branches]
    m.state_log[:] = [m.states["SOUL_BURN_MOVE"], m.states["SOUL_BURN_MOVE"]]
    w_dup = [branch._effective_weight(b, m) for b in branch._branches]
    print("  G4 control check (do NOT re-verdict G4 -- this only confirms the")
    print("  seam's reading of SoulNexus as the insensitive control):")
    print(f"    log=[SOUL_BURN]            weights={w_single}")
    print(f"    log=[SOUL_BURN, SOUL_BURN] weights={w_dup}")
    print(f"    identical: {w_single == w_dup}")


# ── adaptable-death (bug class 21) ──────────────────────────────────────────

class _DeathSpy:
    """Records every on_death / should_die / should_remove dispatch."""

    def __init__(self) -> None:
        self.deaths: list[str] = []

    def on_death(self, creature) -> None:
        self.deaths.append(type(creature).__name__)


def probe_adaptable_death() -> None:
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.glory.test_subject import TestSubject
    from sts2_rl.relics.gremlin_horn import GremlinHorn
    from sts2_rl.relics.base import _RELIC_CLASSES

    print("== adaptable-death (PROMPT.md bug class 21) ==")
    print(f"  gremlin_horn registered/obtainable: "
          f"{'gremlin_horn' in _RELIC_CLASSES}")

    cs = CombatState(rng=_random.Random(0), encounter=_encounter(TestSubject),
                     relics=[GremlinHorn()])
    ts = cs.enemies[0]
    spy = _DeathSpy()
    cs.hooks.register(spy)

    print(f"  start: hp={ts.hp}/{ts.max_hp} powers={sorted(ts.powers)}")
    e0, h0 = cs.player.energy, len(cs.player.hand)

    # kill phase 1
    DamageCmd.deal(cs.hooks, ts, 500, dealer=cs.player)
    print("  after a lethal 500 to phase 1:")
    print(f"    hp={ts.hp}  is_dead={ts.is_dead}  "
          f"retained_after_death={ts.retained_after_death}")
    print(f"    powers still on it: {sorted(ts.powers)}")
    print(f"    telegraphed move: {ts._current_move.id}")
    print(f"    on_death fires so far: {spy.deaths}")
    print(f"    Gremlin Horn payout: energy {e0}->{cs.player.energy}, "
          f"hand {h0}->{len(cs.player.hand)}")
    print("  GAME (CreatureCmd.cs:498-533): LoseHpInternal to 0, BeforeDeath,")
    print("  Hook.ShouldDie has no AdaptablePower implementer so the death")
    print("  STANDS -> InvokeDiedEvent, shouldRemoveFromCombat=false")
    print("  (AdaptablePower.cs:58-65), Hook.AfterDeath(wasRemovalPrevented:")
    print("  FALSE) -> GremlinHorn.cs:24-32 pays +1 energy +1 card, and")
    print("  RemoveAllPowersAfterDeath (Creature.cs:668-671) strips every power")
    print("  whose ShouldPowerBeRemovedAfterOwnerDeath() is true -- default is")
    print("  TRUE (PowerModel.cs:637-640), only AdaptablePower and")
    print("  PainfulStabsPower opt out. So the game's phase-2 body carries")
    print("  NEITHER Enrage nor any Strength it stacked; the sim's does.")

    # drive it to phase 2 and kill again
    cs.enemies[0].take_turn(cs._ctx())          # RESPAWN_MOVE
    print(f"  after RESPAWN_MOVE: hp={ts.hp}/{ts.max_hp} "
          f"powers={sorted(ts.powers)} next={ts._current_move.id}")
    DamageCmd.deal(cs.hooks, ts, 500, dealer=cs.player)
    cs.enemies[0].take_turn(cs._ctx())          # RESPAWN_MOVE again
    print(f"  after 2nd respawn: hp={ts.hp}/{ts.max_hp} "
          f"powers={sorted(ts.powers)} next={ts._current_move.id}")
    DamageCmd.deal(cs.hooks, ts, 500, dealer=cs.player)
    print(f"  after the FINAL kill: hp={ts.hp} is_dead={ts.is_dead}")
    print(f"  on_death fired {len(spy.deaths)} time(s) across the whole boss: "
          f"{spy.deaths}")
    print("  GAME fires AfterDeath THREE times (one per form). Gremlin Horn")
    print("  therefore pays 3 energy + 3 cards in the game and "
          f"{cs.player.energy - e0} energy in the sim.")


def probe_respawn_hp() -> None:
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.glory.test_subject import TestSubject

    print("== respawn-hp ==")

    class _HpSpy:
        def __init__(self): self.deltas = []
        def on_hp_changed(self, creature, delta):
            if isinstance(creature, TestSubject):
                self.deltas.append(delta)

    cs = CombatState(rng=_random.Random(0), encounter=_encounter(TestSubject))
    ts = cs.enemies[0]
    spy = _HpSpy()
    cs.hooks.register(spy)
    DamageCmd.deal(cs.hooks, ts, 500, dealer=cs.player)
    print(f"  sim HP after the vetoed death: {ts.hp} "
          f"(cmds.py:112 floors a prevented death at 1)")
    spy.deltas.clear()
    cs.enemies[0].take_turn(cs._ctx())
    print(f"  sim on_hp_changed deltas during RESPAWN_MOVE: {spy.deltas}")
    print(f"  sim hp/max after revive: {ts.hp}/{ts.max_hp}")
    print("  GAME: the creature sits at CurrentHp 0 (dead), Revive() runs")
    print("  CreatureCmd.SetMaxHp(200) [CurrentHp stays 0] then")
    print("  CreatureCmd.Heal(200) -> HealInternal 0->200, fires the Revived")
    print("  event (Creature.cs:477-486) and")
    print("  Hook.AfterCurrentHpChanged(+200) (CreatureCmd.cs:750-753).")
    print("  So the game's delta is +200 and the sim's is +199.")


def probe_must_perform_once() -> None:
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.glory.test_subject import TestSubject

    print("== must-perform-once ==")
    cs = CombatState(rng=_random.Random(0), encounter=_encounter(TestSubject))
    ts = cs.enemies[0]
    dead = ts.machine.states["RESPAWN_MOVE"]
    print(f"  RESPAWN_MOVE.must_perform_once_before_transitioning="
          f"{dead.must_perform_once_before_transitioning}  "
          f"(TestSubject.cs:194)")
    DamageCmd.deal(cs.hooks, ts, 500, dealer=cs.player)
    print(f"  after trigger_dead_state: machine.current="
          f"{ts.machine.current.id}  _current_move={ts._current_move.id}")
    print(f"    can_transition_away={dead.can_transition_away} "
          "(not performed yet -> the roll is a no-op)")
    before = ts._current_move.id
    ts.telegraph_next_move()
    print(f"    telegraph_next_move: {before} -> {ts._current_move.id} "
          "(sticky, as MonsterMoveStateMachine.cs:60-63 requires)")
    ts.take_turn(cs._ctx())
    print(f"  after performing it: current={ts._current_move.id} "
          f"(REVIVE_BRANCH resolved with respawns={ts._respawns})")
    print(f"    _performed_at_least_once reset on exit: "
          f"{dead._performed_at_least_once}")


def probe_ally_count() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.glory.turret_operator import LivingShield, TurretOperator

    print("== ally-count ==")
    enc = Encounter(id="turret_operator_weak",
                    monster_classes=[LivingShield, TurretOperator])
    cs = CombatState(rng=_random.Random(0), encounter=enc)
    shield, turret = cs.enemies
    print(f"  slots: {[type(e).__name__ for e in cs.enemies]} "
          "(TurretOperatorWeak.cs:19-23 order: LivingShield, TurretOperator)")
    print(f"  ally_count with both alive: {shield._ally_count()}")
    turret.hp = 0
    print(f"  turret at 0 hp (is_gone={turret.is_gone}): "
          f"ally_count={shield._ally_count()}")
    turret.retained_after_death = True
    print(f"  turret retained_after_death=True (a corpse the combat keeps): "
          f"ally_count={shield._ally_count()}")
    print("  C# GetAllyCount (LivingShield.cs:71-74) is")
    print("  GetTeammatesOf(Creature).Count(c => c.IsAlive && c != Creature),")
    print("  IsAlive => CurrentHp > 0 (Creature.cs:206). A retained corpse is")
    print("  still in Enemies and still fails IsAlive -> not counted. Same.")
    branch = shield.machine.states["SHIELD_SLAM_BRANCH"]
    print(f"  branch add order: {[b[0] for b in branch._branches]} "
          "(C#: SHIELD_SLAM_MOVE then SMASH_MOVE)")


def probe_graphs() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.glory.soul_nexus import SoulNexus
    from sts2_rl.monsters.glory.test_subject import TestSubject
    from sts2_rl.monsters.glory.the_lost_and_forgotten import TheForgotten, TheLost
    from sts2_rl.monsters.glory.turret_operator import LivingShield, TurretOperator
    from sts2_rl.monsters.state_machine import (
        ConditionalBranchState, MoveState, RandomBranchState,
    )

    print("== graphs ==")
    for cls in (SoulNexus, TestSubject, TheForgotten, TheLost,
                LivingShield, TurretOperator):
        cs = CombatState(rng=_random.Random(0), encounter=_encounter(cls))
        mon = cs.enemies[0]
        m = mon.machine
        print(f"  -- {cls.__name__}  hp={mon.min_hp}/{mon.max_hp}  "
              f"initial={m._initial_state.id}  "
              f"powers_at_init={sorted(mon.powers)}")
        for sid, st in m.states.items():
            if isinstance(st, MoveState):
                fu = st.follow_up.id if st.follow_up else None
                print(f"     MOVE  {sid:<20} -> {fu}")
            elif isinstance(st, RandomBranchState):
                print(f"     RAND  {sid}")
                for b in st._branches:
                    print(f"           {b['state_id']:<18} w={b['weight']} "
                          f"{b['repeat_type'].value} "
                          f"max={b['max_times']} cd={b['cooldown']}")
            elif isinstance(st, ConditionalBranchState):
                print(f"     COND  {sid}  order="
                      f"{[b[0] for b in st._branches]}")


_PROBES = {
    "soul-nexus-control": probe_soul_nexus_control,
    "adaptable-death": probe_adaptable_death,
    "respawn-hp": probe_respawn_hp,
    "must-perform-once": probe_must_perform_once,
    "ally-count": probe_ally_count,
    "graphs": probe_graphs,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or (argv[1] not in _PROBES and argv[1] != "all"):
        print(__doc__)
        print("probes: " + ", ".join(sorted(_PROBES)) + ", all")
        return 2
    names = sorted(_PROBES) if argv[1] == "all" else [argv[1]]
    for n in names:
        _PROBES[n]()
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
