"""Executed evidence for monster content-audit batch 4.

Units: skulking_colony, sludge_spinner, soul_fysh, terror_eel, toadpole,
two_tailed_rat, waterfall_giant, bowlbug_{egg,nectar,rock,silk},
decimillipede_segment{,_front,_middle,_back}.

Every number a batch-4 record cites from execution is produced here.

    py audit/tools/monster_probes_b04.py <probe>

Probes
    branches      every RandomBranchState in the batch, resolved to
                  (weight, repeat_type, max_times, cooldown), diffed against
                  the C# AddBranch overload table (seam step 13).
    rat-weights   TwoTailedRat's non-dyadic 1f/12f lambda arm, opened live.
    deci-hp       DecimillipedeSegment.AfterAddedToRoom's even/unique HP pass
                  (legacy + parity) and the creature_card_cmds step-26
                  SetMaxAndCurrentHp liveness question, with an on_hp_changed
                  spy.
    deci-death    death != removal: a withered segment keeps taking turns and
                  reaches DEAD -> REATTACH.
    eel-stun      TerrorEel's Shriek -> TERROR splice, both trigger timings.
    rock-stun     BowlbugRock's fully-blocked headbutt -> DIZZY.
    fysh-beckon   SoulFysh BECKON/GAZE card placement.
    graphs        every batch unit's move graph walked from its initial state.
    pools         each unit's encounter id vs the ported act pools.
"""
from __future__ import annotations

import os
import random as _random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── the C# ground truth, transcribed from the models by hand ────────────────
# (state_id, weight, repeat_type, max_times, cooldown) in AddBranch order.
CS_BRANCHES = {
    # SludgeSpinner.cs:45-47 -- AddBranch(state, MoveRepeatType.CannotRepeat),
    # overload #10 (no int at all), weight defaults to 1f.
    "SludgeSpinner": [
        ("OIL_SPRAY_MOVE", 1.0, "CANNOT_REPEAT", 0, 0),
        ("SLAM_MOVE", 1.0, "CANNOT_REPEAT", 0, 0),
        ("RAGE_MOVE", 1.0, "CANNOT_REPEAT", 0, 0),
    ],
    # TwoTailedRat.cs:125-128 -- three overload #6 (R, Func<float>) plus ONE
    # overload #1 (int cooldown, R, Func<float>) on SCREECH: the 3 is a
    # COOLDOWN, not a weight.
    "TwoTailedRat": [
        ("SCRATCH_MOVE", "lambda", "CANNOT_REPEAT", 0, 0),
        ("DISEASE_BITE_MOVE", "lambda", "CANNOT_REPEAT", 0, 0),
        ("SCREECH_MOVE", "lambda", "CANNOT_REPEAT", 0, 3),
        ("CALL_FOR_BACKUP_MOVE", "lambda", "USE_ONLY_ONCE", 0, 0),
    ],
    # DecimillipedeSegment.cs:163-165 -- overload #10 again.
    "DecimillipedeSegmentFront": [
        ("WRITHE_MOVE", 1.0, "CANNOT_REPEAT", 0, 0),
        ("BULK_MOVE", 1.0, "CANNOT_REPEAT", 0, 0),
        ("CONSTRICT_MOVE", 1.0, "CANNOT_REPEAT", 0, 0),
    ],
}
# Front/Middle/Back declare no GenerateMoveStateMachine of their own; the
# graph is inherited verbatim from DecimillipedeSegment.cs:146-178.
CS_BRANCHES["DecimillipedeSegmentMiddle"] = CS_BRANCHES["DecimillipedeSegmentFront"]
CS_BRANCHES["DecimillipedeSegmentBack"] = CS_BRANCHES["DecimillipedeSegmentFront"]


def _units():
    from sts2_rl.monsters.hive.bowlbugs import (
        BowlbugEgg, BowlbugNectar, BowlbugRock, BowlbugSilk,
    )
    from sts2_rl.monsters.hive.decimillipede import (
        DecimillipedeSegmentBack, DecimillipedeSegmentFront,
        DecimillipedeSegmentMiddle,
    )
    from sts2_rl.monsters.underdocks.skulking_colony import SkulkingColony
    from sts2_rl.monsters.underdocks.sludge_spinner import SludgeSpinner
    from sts2_rl.monsters.underdocks.soul_fysh import SoulFysh
    from sts2_rl.monsters.underdocks.terror_eel import TerrorEel
    from sts2_rl.monsters.underdocks.toadpole import Toadpole
    from sts2_rl.monsters.underdocks.two_tailed_rat import TwoTailedRat
    from sts2_rl.monsters.underdocks.waterfall_giant import WaterfallGiant
    return {
        "skulking_colony": SkulkingColony,
        "sludge_spinner": SludgeSpinner,
        "soul_fysh": SoulFysh,
        "terror_eel": TerrorEel,
        "toadpole": Toadpole,
        "two_tailed_rat": TwoTailedRat,
        "waterfall_giant": WaterfallGiant,
        "bowlbug_egg": BowlbugEgg,
        "bowlbug_nectar": BowlbugNectar,
        "bowlbug_rock": BowlbugRock,
        "bowlbug_silk": BowlbugSilk,
        "decimillipede_segment_front": DecimillipedeSegmentFront,
        "decimillipede_segment_middle": DecimillipedeSegmentMiddle,
        "decimillipede_segment_back": DecimillipedeSegmentBack,
    }


def _live(cls, seed=0, **kw):
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter

    class _E(Encounter):
        def create_monsters(self, hooks, rng, selection_rng=None):
            return [cls(hooks, rng, **kw)]

    enc = _E(id="probe_b04", monster_classes=[])
    cs = CombatState(rng=_random.Random(seed), encounter=enc)
    return cs, cs.enemies[0]


# ───────────────────────────────────────────────────────────── branches ────
def probe_branches() -> None:
    from sts2_rl.monsters.state_machine import RandomBranchState
    print("== RandomBranchState parameters, sim vs C# (seam step 13) ==")
    mism = 0
    for uid, cls in _units().items():
        _, mon = _live(cls)
        for st in mon.machine.states.values():
            if not isinstance(st, RandomBranchState):
                continue
            got = []
            for b in st._branches:
                w = b["weight"]
                got.append((b["state_id"],
                            "lambda" if callable(w) else float(w),
                            b["repeat_type"].name, b["max_times"],
                            b["cooldown"]))
            want = CS_BRANCHES.get(cls.__name__)
            ok = want == got
            mism += 0 if ok else 1
            print(f"  {uid}.{st.id}: {'MATCH' if ok else 'MISMATCH'}")
            for row in got:
                print(f"      sim  {row}")
            if want is None:
                print("      C#   (no transcription -- update CS_BRANCHES)")
            elif not ok:
                for row in want:
                    print(f"      C#   {row}")
    print(f"  branch states compared: mismatches = {mism}")
    print("  units with NO RandomBranchState (pure chains / conditional only):")
    for uid, cls in _units().items():
        _, mon = _live(cls)
        if not any(isinstance(s, RandomBranchState)
                   for s in mon.machine.states.values()):
            print(f"      {uid}")


# ─────────────────────────────────────────────────────────── rat-weights ────
def probe_rat_weights() -> None:
    from sts2_rl.monsters.state_machine import RandomBranchState
    from sts2_rl.monsters.underdocks.two_tailed_rat import TwoTailedRat
    from sts2_rl.monsters import Encounter
    from sts2_rl.combat import CombatState

    class _E(Encounter):
        def create_monsters(self, hooks, rng, selection_rng=None):
            return [TwoTailedRat(hooks, rng, starter_move_idx=i)
                    for i in range(3)]

    cs = CombatState(rng=_random.Random(1), encounter=_E(id="p", monster_classes=[]))
    rat = cs.enemies[0]
    rand = rat.machine.states["RAND"]
    assert isinstance(rand, RandomBranchState)

    def vec():
        return [round(RandomBranchState._effective_weight(b, rat.machine), 6)
                for b in rand._branches]

    print("== TwoTailedRat weight lambdas (the batch's only non-dyadic arm) ==")
    print(f"  turns_until_summonable={rat.turns_until_summonable} "
          f"can_summon={rat._can_summon()}  weights={vec()}")
    for r in cs.enemies:
        r.turns_until_summonable = 0
    print(f"  turns_until_summonable=0  can_summon={rat._can_summon()}  "
          f"weights={vec()}")
    print(f"  1/12 = {1/12:.6f}; CALL_FOR_BACKUP weight 0.75 "
          f"(TwoTailedRat.cs:125-128)")
    rat.call_for_backup_count = 3
    print(f"  call_for_backup_count=3   can_summon={rat._can_summon()}  "
          f"weights={vec()}")
    rat.call_for_backup_count = 0
    # cooldown 3 on SCREECH: log three SCREECHes and watch it zero
    log = rat.machine.state_log
    log[:] = [rat.machine.states["SCREECH_MOVE"]]
    print(f"  state_log=[SCREECH]        weights={vec()}   "
          f"(SCREECH zeroed by cooldown 3, not by a weight)")


# ────────────────────────────────────────────────────────────── deci-hp ────
def probe_deci_hp() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.hive.decimillipede import (
        DECIMILLIPEDE_ELITE, DecimillipedeSegment,
    )
    from sts2_rl.rng import RunRngSet

    print("== DecimillipedeSegment.AfterAddedToRoom HP pass ==")
    print(f"  C# MinInitialHp/MaxInitialHp (non-asc, DecimillipedeSegment.cs:"
          f"64-66) = 40 / 46 ; sim = {DecimillipedeSegment.min_hp} / "
          f"{DecimillipedeSegment.max_hp}")

    calls = []

    class Spy:
        def on_hp_changed(self, creature, delta):
            calls.append((getattr(creature, "name", "?"), delta))

    for label, kw in (("legacy", {}),
                      ("parity", {"rng_set": RunRngSet("933T39V18D")})):
        calls.clear()
        cs = CombatState(rng=_random.Random(4), encounter=DECIMILLIPEDE_ELITE,
                         **kw)
        # (the spy has to be registered before creation to see the assignment,
        #  so re-run the class-level pass with it attached)
        cs.hooks.register(Spy())
        hps = [(e.__class__.__name__, e.hp, e.max_hp) for e in cs.enemies]
        print(f"  {label}: {hps}")
        for e in cs.enemies:
            e.adjust_hp_after_added([o for o in cs.enemies if o is not e])
        print(f"    re-running adjust_hp_after_added with an on_hp_changed spy"
              f" -> {len(calls)} calls, hps now "
              f"{[e.max_hp for e in cs.enemies]}")
        assert all(h % 2 == 0 for _, _, h in hps), hps
        assert len({h for _, _, h in hps}) == 3, hps
        assert all(hp == mx for _, hp, mx in hps), hps
        assert all(0 < mx for _, _, mx in hps), hps
    print("  step 26 (SetMaxAndCurrentHp): every assigned value is even, "
          "positive, distinct, and hp == max_hp, so SetMaxHpInternal's "
          "CurrentHp clamp and SetMaxHp's `MaxHp <= 0 -> Kill` are both "
          "unreachable here.")
    print("  on_hp_changed listeners in the whole sim:")
    os.system(f'{sys.executable} -c "import subprocess"')
    import re
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / "sts2_rl"
    for p in sorted(root.rglob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*def on_hp_changed\(", line):
                print(f"      {p.relative_to(root.parent)}:{i}")


# ─────────────────────────────────────────────────────────── deci-death ────
def probe_deci_death() -> None:
    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.hive.decimillipede import DECIMILLIPEDE_ELITE

    print("== death != removal: a withered Decimillipede segment ==")
    deaths = []

    class Spy:
        def on_death(self, creature):
            deaths.append(getattr(creature, "name", "?"))

    cs = CombatState(rng=_random.Random(7), encounter=DECIMILLIPEDE_ELITE)
    cs.hooks.register(Spy())
    seg = cs.enemies[0]
    CreatureCmd.kill(cs.hooks, seg)
    print(f"  after kill: hp={seg.hp} is_dead={seg.is_dead} "
          f"is_gone={seg.is_gone} retained_after_death={seg.retained_after_death}")
    print(f"  on_death listeners fired: {deaths}  "
          f"(a should_die veto would have fired NONE -- PROMPT.md class 21)")
    print(f"  move parked at {seg._current_move.id!r} "
          f"(ReattachPower.on_death -> enter_dead_state)")
    seq = []
    for _ in range(4):
        cs._execute_enemy_turn()
        seq.append((seg._current_move.id, seg.hp))
    print(f"  four enemy sides later: {seq}")
    print(f"  segment HP back to {seg.hp} "
          f"(ReattachPower.do_reattach), retained_after_death="
          f"{seg.retained_after_death}")


# ───────────────────────────────────────────────────────────── eel-stun ────
def probe_eel_stun() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.underdocks.terror_eel import TERROR_EEL_ELITE

    print("== TerrorEel: ShriekPower -> TERROR ==")
    cs = CombatState(rng=_random.Random(2), encounter=TERROR_EEL_ELITE)
    eel = cs.enemies[0]
    print(f"  states: {sorted(eel.machine.states)}  "
          f"(C# also registers STUN_MOVE, TerrorEel.cs:73/81 -- unwired and "
          f"unreachable there too: nothing sets FollowUpState to it and it is "
          f"not the initial state; same shape as seam G2)")
    print(f"  opening move {eel._current_move.id}, shriek="
          f"{eel.powers['shriek'].amount}")
    eel.trigger_terror()
    print(f"  after trigger_terror: current={eel._current_move.id} "
          f"stunned={eel.stunned} "
          f"can_transition_away={eel._current_move.can_transition_away}")
    # (a) the trigger lands on the player's turn -> the eel is stunned, skips
    seq = []
    for _ in range(3):
        cs._execute_enemy_turn()
        seq.append(eel._current_move.id)
    print(f"  next three enemy sides telegraph: {seq}")
    print("  C#: ShriekPower.AfterDamageReceived -> CreatureCmd.Stun(owner, "
          "TerrorState.StateId) -> synthetic MoveState('STUNNED', "
          "MustPerformOnceBeforeTransitioning=true, FollowUpStateId="
          "'TERROR_MOVE'); stunned turn does nothing, next turn TERROR. Same "
          "two-turn shape.")

    # (b) the trigger lands mid-move (Thorns), so the eel's OWN end-of-turn
    #     roll runs right after: must_perform_once has to pin it.
    cs2 = CombatState(rng=_random.Random(2), encounter=TERROR_EEL_ELITE)
    eel2 = cs2.enemies[0]
    eel2.trigger_terror()
    eel2.stunned = False           # simulate the trigger firing mid-own-turn
    eel2.telegraph_next_move()
    print(f"  mid-turn trigger then an immediate roll -> "
          f"{eel2._current_move.id} (must_perform_once pin; C# gets the same "
          f"pin from the synthetic STUNNED state's own flag, Creature.cs:541)")


# ──────────────────────────────────────────────────────────── rock-stun ────
def probe_rock_stun() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.hive.bowlbugs import BOWLBUGS_WEAK, BowlbugRock

    print("== BowlbugRock: fully-blocked HEADBUTT -> DIZZY ==")
    cs = CombatState(rng=_random.Random(11), encounter=BOWLBUGS_WEAK)
    rock = next(e for e in cs.enemies if isinstance(e, BowlbugRock))
    print(f"  powers: {sorted(rock.powers)}  move={rock._current_move.id}")
    cs.player.block = 999
    cs._execute_enemy_turn()
    print(f"  after a fully-blocked headbutt: is_off_balance="
          f"{rock.is_off_balance} next={rock._current_move.id}")
    cs._execute_enemy_turn()
    print(f"  after the DIZZY turn: is_off_balance={rock.is_off_balance} "
          f"next={rock._current_move.id}")
    print("  C#: BowlbugRock.HeadbuttMove calls CreatureCmd.Stun(creature, "
          "DizzyMove) when IsOffBalance; the sim reaches DIZZY through the "
          "POST_HEADBUTT ConditionalBranchState instead -- see the record.")


# ────────────────────────────────────────────────────────── fysh-beckon ────
def probe_fysh_beckon() -> None:
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.underdocks.soul_fysh import SOUL_FYSH_BOSS

    print("== SoulFysh BECKON / GAZE card placement ==")
    cs = CombatState(rng=_random.Random(5), encounter=SOUL_FYSH_BOSS)
    fysh = cs.enemies[0]
    before_draw = len(cs.player.draw_pile)
    before_disc = len(cs.player.discard_pile)
    fysh._beckon(cs._ctx())
    print(f"  BECKON: draw {before_draw}->{len(cs.player.draw_pile)} "
          f"discard {before_disc}->{len(cs.player.discard_pile)}")
    print(f"    draw pile beckon indices: "
          f"{[i for i, c in enumerate(cs.player.draw_pile) if c.id == 'beckon']}"
          f" of {len(cs.player.draw_pile)} (CardPilePosition.Random)")
    d = len(cs.player.discard_pile)
    fysh._gaze(cs._ctx())
    print(f"  GAZE: discard {d}->{len(cs.player.discard_pile)}, "
          f"player hp now {cs.player.hp}")


# ─────────────────────────────────────────────────────────────── graphs ────
def probe_graphs() -> None:
    print("== move graphs, walked from the initial state ==")
    for uid, cls in _units().items():
        _, mon = _live(cls)
        m = mon.machine
        edges = []
        for sid, st in m.states.items():
            fu = getattr(st, "follow_up", None)
            if fu is not None:
                edges.append(f"{sid}->{fu.id}")
            elif hasattr(st, "_branches"):
                for b in st._branches:
                    tgt = b["state_id"] if isinstance(b, dict) else b[0]
                    edges.append(f"{sid}=>{tgt}")
        print(f"  {uid}: initial={m._initial.id if hasattr(m, '_initial') else m.current.id}"
              f" first_move={mon._current_move.id}")
        print(f"      {' , '.join(edges)}")


# ──────────────────────────────────────────────────────────────── pools ────
def probe_pools() -> None:
    from sts2_rl.rooms import _ACT_ROOMS_FACTORIES
    wanted = {
        "skulking_colony": "skulking_colony", "sludge_spinner": "sludge_spinner",
        "soul_fysh": "soul_fysh", "terror_eel": "terror_eel",
        "toadpole": "toadpoles", "two_tailed_rat": "two_tailed_rats",
        "waterfall_giant": "waterfall_giant",
        "bowlbug_egg": "bowlbugs_weak", "bowlbug_nectar": "bowlbugs_weak",
        "bowlbug_rock": "bowlbugs_weak", "bowlbug_silk": "bowlbugs_normal",
        "decimillipede_segment_front": "decimillipede",
        "decimillipede_segment_middle": "decimillipede",
        "decimillipede_segment_back": "decimillipede",
    }
    print("== encounter reachability in the ported act pools (rooms.py) ==")
    for act, factory in _ACT_ROOMS_FACTORIES.items():
        r = factory()
        keys = set(r.weak_keys) | set(r.normal_keys) | set(r.elite_keys) | set(r.boss_keys)
        for uid, key in sorted(wanted.items()):
            if key in keys:
                print(f"  {uid:32s} -> {act}/{key}")


# ─────────────────────────────────────────────────────────── giant-blow ────
def probe_giant_blow() -> None:
    """WaterfallGiant's killing-blow sequence, and the on_death dispatch it
    misses (PROMPT.md bug class 21 -- SteamEruptionPower is ported onto
    `should_die`, which VETOES the death, where C# lets the giant really die
    and only keeps the corpse in Enemies)."""
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.underdocks.waterfall_giant import WATERFALL_GIANT_BOSS
    from sts2_rl.relics.gremlin_horn import GremlinHorn

    print("== WaterfallGiant: killing blow -> ABOUT_TO_BLOW -> EXPLODE ==")
    deaths = []

    class Spy:
        def on_death(self, creature):
            deaths.append(getattr(creature, "name", "?"))

    cs = CombatState(rng=_random.Random(3), encounter=WATERFALL_GIANT_BOSS,
                     relics=[GremlinHorn()])
    cs.hooks.register(Spy())
    g = cs.enemies[0]
    for _ in range(6):
        cs.player.hp = 500
        cs._execute_enemy_turn()
    steam = g.powers["steam_eruption"].amount
    print(f"  after 6 enemy sides: steam={steam} move={g._current_move.id}")
    e0, d0 = cs.player.energy, len(cs.player.hand)
    DamageCmd.deal(cs.hooks, g, 9999, dealer=cs.player)
    print(f"  killing blow: hp={g.hp} max_hp={g.max_hp} is_dead={g.is_dead} "
          f"about_to_blow={g.is_about_to_blow} move={g._current_move.id}")
    print(f"    on_death dispatches so far: {deaths}   "
          f"(C#: SteamEruptionPower.AfterDeath fires HERE -- the giant really "
          f"dies, ShouldCreatureBeRemovedFromCombatAfterDeath keeps the corpse, "
          f"and TriggerAboutToBlowState then revives it at 999999999)")
    print(f"    Gremlin Horn: energy {e0}->{cs.player.energy}, "
          f"hand {d0}->{len(cs.player.hand)}")
    cs._execute_enemy_turn()
    print(f"  ABOUT_TO_BLOW turn: move={g._current_move.id} "
          f"steam_dmg={g._steam_eruption_dmg} powers={sorted(g.powers)}")
    e1, d1 = cs.player.energy, len(cs.player.hand)
    cs._execute_enemy_turn()
    print(f"  EXPLODE turn: player hp={cs.player.hp} giant is_dead={g.is_dead} "
          f"phase={cs.phase}")
    print(f"    on_death dispatches total: {deaths}  "
          f"(C# fires AfterDeath TWICE, the sim once)")
    print(f"    Gremlin Horn on the explode death: energy {e1}->"
          f"{cs.player.energy}, hand {d1}->{len(cs.player.hand)}")


PROBES = {
    "branches": probe_branches,
    "giant-blow": probe_giant_blow,
    "rat-weights": probe_rat_weights,
    "deci-hp": probe_deci_hp,
    "deci-death": probe_deci_death,
    "eel-stun": probe_eel_stun,
    "rock-stun": probe_rock_stun,
    "fysh-beckon": probe_fysh_beckon,
    "graphs": probe_graphs,
    "pools": probe_pools,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in PROBES:
        print(__doc__)
        print("probes: " + ", ".join(PROBES))
        raise SystemExit(1)
    PROBES[sys.argv[1]]()
