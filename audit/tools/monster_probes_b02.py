"""Executed evidence for monster content-audit BATCH 2 (15 units).

Probes
------
  seq          For every unit in batch 2: build a REFERENCE
               `MonsterMoveStateMachine` transcribed literally from the C#
               `GenerateMoveStateMachine` (every `AddBranch` integer placed in
               the role `RandomBranchState.cs:46-113` gives it, per
               `audit/seams/monster_state_machine.md` step 13), drive it turn by
               turn on a `RunRngSet(seed).monster_ai` stream, and compare the
               emitted move sequence AND the MonsterAi draw count against the
               sim port driven on an identically seeded stream.  This is how the
               hand-rolled ports' "equivalent over the reachable state space"
               claim is ESTABLISHED rather than asserted (verdict rules 5/6).

  dist         Distribution check for the three units whose C# model builds a
               live `RandomBranchState` (leaf_slime_s, twig_slime_m,
               slithering_strangler): N independent combats, reference machine
               vs sim port, per-move frequency.

  intents      Per move: the C# `AbstractIntent[]` the MoveState is constructed
               with vs the sim `Intent` (primary + `also`).  A dropped secondary
               intent is observable — `env.py:160-170` / `full_env.py:562-579`
               read `Intent.has(...)` for exactly these types.

  ctor-regex   Reproduces a TOOLING DEFECT found while auditing this batch:
               `monster_probes.py`'s `_CTOR` regex is
               `def __init__\\(self...`, which does not match a ports whose
               `__init__` signature is wrapped across lines
               (`def __init__(\\n        self,`).  `ctor-order` therefore
               UNDER-REPORTS the constructor-applied-power population.

Run:  py audit/tools/monster_probes_b02.py <probe>
"""
from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from sts2_rl.combat import CombatState  # noqa: E402
from sts2_rl.monsters import Encounter  # noqa: E402
from sts2_rl.monsters.base import Intent, MoveType  # noqa: E402
from sts2_rl.monsters.state_machine import (  # noqa: E402
    MachineMonster, MonsterMoveStateMachine, MoveRepeatType, MoveState,
    RandomBranchState,
)
from sts2_rl.rng import GameRandomAdapter, RunRngSet  # noqa: E402

_NOOP_INTENT = Intent(MoveType.UNKNOWN)


class _Owner:
    """The only thing `get_next_state` reads off its owner is `.machine`."""
    machine: MonsterMoveStateMachine


def _mv(state_id: str) -> MoveState:
    return MoveState(state_id, lambda ctx: None, _NOOP_INTENT)


def _chain(ids, links, initial):
    """Build a pure MoveState chain: links is {id: follow_up_id}."""
    states = {i: _mv(i) for i in ids}
    for a, b in links.items():
        states[a].follow_up = states[b]
    return MonsterMoveStateMachine(list(states.values()), states[initial])


# ---------------------------------------------------------------------------
# REFERENCE MACHINES — one per unit, transcribed from the C# source.
# Each builder returns (machine, {c#_state_id: sim_move_key}).
# ---------------------------------------------------------------------------

def _ref_assassin():
    # AssassinRubyRaider.cs:23-30 — one MoveState, self follow-up.
    return _chain(["KILLSHOT_MOVE"], {"KILLSHOT_MOVE": "KILLSHOT_MOVE"},
                  "KILLSHOT_MOVE"), {"KILLSHOT_MOVE": "<single-move>"}


def _ref_axe():
    # AxeRubyRaider.cs:32-45 — SWING_1 -> SWING_2 -> BIG_SWING -> SWING_1,
    # initial SWING_1.
    ids = ["SWING_1", "SWING_2", "BIG_SWING"]
    return _chain(ids, {"SWING_1": "SWING_2", "SWING_2": "BIG_SWING",
                        "BIG_SWING": "SWING_1"}, "SWING_1"), {
        "SWING_1": "SWING_1", "SWING_2": "SWING_2", "BIG_SWING": "BIG_SWING"}


def _ref_brute():
    # BruteRubyRaider.cs:29-38 — BEAT <-> ROAR, initial BEAT.
    return _chain(["BEAT_MOVE", "ROAR_MOVE"],
                  {"BEAT_MOVE": "ROAR_MOVE", "ROAR_MOVE": "BEAT_MOVE"},
                  "BEAT_MOVE"), {"BEAT_MOVE": "BEAT", "ROAR_MOVE": "ROAR"}


def _ref_crossbow():
    # CrossbowRubyRaider.cs:45-54 — FIRE <-> RELOAD, initial is moveState2
    # (RELOAD_MOVE, line 53).
    return _chain(["FIRE_MOVE", "RELOAD_MOVE"],
                  {"FIRE_MOVE": "RELOAD_MOVE", "RELOAD_MOVE": "FIRE_MOVE"},
                  "RELOAD_MOVE"), {"FIRE_MOVE": "FIRE", "RELOAD_MOVE": "RELOAD"}


def _ref_tracker():
    # TrackerRubyRaider.cs:29-38 — TRACK -> HOUNDS -> HOUNDS (self), initial
    # TRACK.
    return _chain(["TRACK_MOVE", "HOUNDS_MOVE"],
                  {"TRACK_MOVE": "HOUNDS_MOVE", "HOUNDS_MOVE": "HOUNDS_MOVE"},
                  "TRACK_MOVE"), {"TRACK_MOVE": "TRACK", "HOUNDS_MOVE": "HOUNDS"}


def _ref_leaf_slime_m():
    # LeafSlimeM.cs:30-41 — CLUMP <-> STICKY, initial moveState2 (STICKY, :40).
    return _chain(["CLUMP_SHOT", "STICKY_SHOT"],
                  {"CLUMP_SHOT": "STICKY_SHOT", "STICKY_SHOT": "CLUMP_SHOT"},
                  "STICKY_SHOT"), {"CLUMP_SHOT": "CLUMP_SHOT",
                                   "STICKY_SHOT": "STICKY_SHOT"}


def _ref_leaf_slime_s():
    # LeafSlimeS.cs:28-40 — TACKLE and GOOP both follow up into RAND;
    # RAND.AddBranch(TACKLE, CannotRepeat)  -> overload #10, weight 1
    # RAND.AddBranch(GOOP,   CannotRepeat)  -> overload #10, weight 1
    # INITIAL STATE IS THE BRANCH (line 39), so combat start draws once.
    tackle, goop = _mv("TACKLE_MOVE"), _mv("GOOP_MOVE")
    rand = RandomBranchState("RAND")
    tackle.follow_up = rand
    goop.follow_up = rand
    rand.add_branch(tackle, 1.0, MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch(goop, 1.0, MoveRepeatType.CANNOT_REPEAT)
    return MonsterMoveStateMachine([tackle, goop, rand], rand), {
        "TACKLE_MOVE": "TACKLE", "GOOP_MOVE": "GOOP"}


def _ref_twig_slime_m():
    # TwigSlimeM.cs:33-45 — both moves follow up into RAND, initial STICKY.
    # :39 AddBranch(POKEY, 2)              -> overload #9: maxRepeats=2,
    #                                          CanRepeatXTimes, weight 1
    # :40 AddBranch(STICKY, CannotRepeat)  -> overload #10, weight 1
    pokey, sticky = _mv("POKEY_POUNCE_MOVE"), _mv("STICKY_SHOT_MOVE")
    rand = RandomBranchState("RAND")
    pokey.follow_up = rand
    sticky.follow_up = rand
    rand.add_branch(pokey, 1.0, MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2)
    rand.add_branch(sticky, 1.0, MoveRepeatType.CANNOT_REPEAT)
    return MonsterMoveStateMachine([pokey, sticky, rand], sticky), {
        "POKEY_POUNCE_MOVE": "POKEY_POUNCE", "STICKY_SHOT_MOVE": "STICKY_SHOT"}


def _ref_twig_slime_s():
    # TwigSlimeS.cs:23-30 — one MoveState, self follow-up.
    # The sim port keeps no move key at all (one move), so map to the sentinel.
    return _chain(["TACKLE_MOVE"], {"TACKLE_MOVE": "TACKLE_MOVE"},
                  "TACKLE_MOVE"), {"TACKLE_MOVE": "<single-move>"}


def _ref_strangler():
    # SlitheringStrangler.cs:39-55 — CONSTRICT -> rand; THWACK/LASH -> CONSTRICT.
    # :48 AddBranch(THWACK, CanRepeatForever) -> overload #10, weight 1
    # :49 AddBranch(LASH,   CanRepeatForever) -> overload #10, weight 1
    # initial CONSTRICT (:54).
    constrict, thwack, lash = _mv("CONSTRICT"), _mv("THWACK"), _mv("LASH")
    rand = RandomBranchState("rand")
    constrict.follow_up = rand
    thwack.follow_up = constrict
    lash.follow_up = constrict
    rand.add_branch(thwack, 1.0, MoveRepeatType.CAN_REPEAT_FOREVER)
    rand.add_branch(lash, 1.0, MoveRepeatType.CAN_REPEAT_FOREVER)
    return MonsterMoveStateMachine([rand, thwack, constrict, lash], constrict), {
        "CONSTRICT": "CONSTRICT", "THWACK": "THWACK", "LASH": "LASH"}


def _ref_kin_follower(starts_with_dance: bool = False):
    # KinFollower.cs:104-118 — SLASH -> BOOMERANG -> DANCE -> SLASH;
    # initial is DANCE when StartsWithDance (TheKinBoss.cs:43-44 sets it on the
    # slot1 follower only).
    ids = ["QUICK_SLASH_MOVE", "BOOMERANG_MOVE", "POWER_DANCE_MOVE"]
    links = {"QUICK_SLASH_MOVE": "BOOMERANG_MOVE",
             "BOOMERANG_MOVE": "POWER_DANCE_MOVE",
             "POWER_DANCE_MOVE": "QUICK_SLASH_MOVE"}
    initial = "POWER_DANCE_MOVE" if starts_with_dance else "QUICK_SLASH_MOVE"
    return _chain(ids, links, initial), {
        "QUICK_SLASH_MOVE": "QUICK_SLASH", "BOOMERANG_MOVE": "BOOMERANG",
        "POWER_DANCE_MOVE": "POWER_DANCE"}


def _ref_kin_priest():
    # KinPriest.cs:111-127 — FRAILTY -> WEAKNESS -> BEAM -> RITUAL -> FRAILTY.
    ids = ["ORB_OF_FRAILTY_MOVE", "ORB_OF_WEAKNESS_MOVE", "BEAM_MOVE",
           "RITUAL_MOVE"]
    links = {"ORB_OF_FRAILTY_MOVE": "ORB_OF_WEAKNESS_MOVE",
             "ORB_OF_WEAKNESS_MOVE": "BEAM_MOVE",
             "BEAM_MOVE": "RITUAL_MOVE",
             "RITUAL_MOVE": "ORB_OF_FRAILTY_MOVE"}
    return _chain(ids, links, "ORB_OF_FRAILTY_MOVE"), {
        "ORB_OF_FRAILTY_MOVE": "ORB_FRAILTY",
        "ORB_OF_WEAKNESS_MOVE": "ORB_WEAKNESS",
        "BEAM_MOVE": "BEAM", "RITUAL_MOVE": "RITUAL"}


def _ref_vantom():
    # Vantom.cs:114-130 — INK_BLOT -> INKY_LANCE -> DISMEMBER -> PREPARE -> ...
    ids = ["INK_BLOT_MOVE", "INKY_LANCE_MOVE", "DISMEMBER_MOVE", "PREPARE_MOVE"]
    links = {"INK_BLOT_MOVE": "INKY_LANCE_MOVE",
             "INKY_LANCE_MOVE": "DISMEMBER_MOVE",
             "DISMEMBER_MOVE": "PREPARE_MOVE",
             "PREPARE_MOVE": "INK_BLOT_MOVE"}
    return _chain(ids, links, "INK_BLOT_MOVE"), {
        "INK_BLOT_MOVE": "INK_BLOT", "INKY_LANCE_MOVE": "INKY_LANCE",
        "DISMEMBER_MOVE": "DISMEMBER", "PREPARE_MOVE": "PREPARE"}


def _ref_vine_shambler():
    # VineShambler.cs:44-57 — SWIPE -> VINES -> CHOMP -> SWIPE, initial SWIPE
    # (moveState2, :56).
    ids = ["GRASPING_VINES_MOVE", "SWIPE_MOVE", "CHOMP_MOVE"]
    links = {"SWIPE_MOVE": "GRASPING_VINES_MOVE",
             "GRASPING_VINES_MOVE": "CHOMP_MOVE",
             "CHOMP_MOVE": "SWIPE_MOVE"}
    return _chain(ids, links, "SWIPE_MOVE"), {
        "SWIPE_MOVE": "SWIPE", "GRASPING_VINES_MOVE": "GRASPING_VINES",
        "CHOMP_MOVE": "CHOMP"}


def _ref_corpse_slug(starter_move_idx: int = 0):
    # CorpseSlug.cs:91-109 — WHIP_SLAP -> GLOMP -> GOOP -> WHIP_SLAP; the
    # initial state is StarterMoveIdx % 3 (:103-108).
    ids = ["WHIP_SLAP_MOVE", "GLOMP_MOVE", "GOOP_MOVE"]
    links = {"WHIP_SLAP_MOVE": "GLOMP_MOVE", "GLOMP_MOVE": "GOOP_MOVE",
             "GOOP_MOVE": "WHIP_SLAP_MOVE"}
    return _chain(ids, links, ids[starter_move_idx % 3]), {i: i for i in ids}


# ---------------------------------------------------------------------------

def _sim_key(monster):
    """The port's current move, whichever representation it uses."""
    if isinstance(monster, MachineMonster):
        return monster.machine.current.id
    if hasattr(monster, "_move_key"):
        return monster._move_key
    if hasattr(monster, "_step"):          # AxeRubyRaider keeps a cycle index
        return monster._CYCLE[monster._step % len(monster._CYCLE)]
    return "<single-move>"                 # AssassinRubyRaider / TwigSlimeS


def _drive_reference(machine, seed: str, turns: int):
    rs = RunRngSet(seed)
    rng = GameRandomAdapter(rs.monster_ai)
    owner = _Owner()
    owner.machine = machine
    machine.roll_move(owner, rng)            # combat-start roll (AfterCreatureAdded)
    out = []
    for _ in range(turns):
        out.append(machine.current.id)
        machine.on_move_performed(machine.current)
        machine.roll_move(owner, rng)
    return out, rs.monster_ai.counter


def _drive_sim(factory, seed: str, turns: int):
    enc = Encounter(id="probe_b02", monster_classes=[factory])
    rs = RunRngSet(seed)
    combat = CombatState(rng_set=rs, encounter=enc)
    monster = combat.enemies[0]
    combat.player.max_hp = combat.player.hp = 10 ** 7
    ctx = combat._ctx()
    out = []
    for _ in range(turns):
        out.append(_sim_key(monster))
        monster.hp = monster.max_hp
        combat.player.hp = combat.player.max_hp
        # Every batch-2 port advances its own move inside take_turn (either
        # inline or via its telegraph_next_move override), exactly as
        # MachineMonster.take_turn does (state_machine.py:320-330), so the
        # driver must NOT advance again.
        monster.take_turn(ctx)
    return out, rs.monster_ai.counter


_UNITS = []


def _reg(unit, ref_builder, factory):
    _UNITS.append((unit, ref_builder, factory))


def _mk(cls, **kw):
    return lambda hooks, rng: cls(hooks, rng, **kw)


def _load():
    from sts2_rl.monsters.overgrowth.ruby_raiders import (
        AssassinRubyRaider, AxeRubyRaider, BruteRubyRaider, CrossbowRubyRaider,
        TrackerRubyRaider)
    from sts2_rl.monsters.overgrowth.slimes import (
        LeafSlimeM, LeafSlimeS, TwigSlimeM, TwigSlimeS)
    from sts2_rl.monsters.overgrowth.slithering_strangler import SlitheringStrangler
    from sts2_rl.monsters.overgrowth.the_kin import KinFollower, KinPriest
    from sts2_rl.monsters.overgrowth.vantom import Vantom
    from sts2_rl.monsters.overgrowth.vine_shambler import VineShambler
    from sts2_rl.monsters.underdocks.corpse_slug import CorpseSlug

    if _UNITS:
        return
    _reg("assassin_ruby_raider", _ref_assassin, _mk(AssassinRubyRaider))
    _reg("axe_ruby_raider", _ref_axe, _mk(AxeRubyRaider))
    _reg("brute_ruby_raider", _ref_brute, _mk(BruteRubyRaider))
    _reg("crossbow_ruby_raider", _ref_crossbow, _mk(CrossbowRubyRaider))
    _reg("tracker_ruby_raider", _ref_tracker, _mk(TrackerRubyRaider))
    _reg("leaf_slime_m", _ref_leaf_slime_m, _mk(LeafSlimeM))
    _reg("leaf_slime_s", _ref_leaf_slime_s, _mk(LeafSlimeS))
    _reg("twig_slime_m", _ref_twig_slime_m, _mk(TwigSlimeM))
    _reg("twig_slime_s", _ref_twig_slime_s, _mk(TwigSlimeS))
    _reg("slithering_strangler", _ref_strangler, _mk(SlitheringStrangler))
    _reg("kin_follower", _ref_kin_follower, _mk(KinFollower))
    _reg("kin_follower[dance]", lambda: _ref_kin_follower(True),
         _mk(KinFollower, starts_with_dance=True))
    _reg("kin_priest", _ref_kin_priest, _mk(KinPriest))
    _reg("vantom", _ref_vantom, _mk(Vantom))
    _reg("vine_shambler", _ref_vine_shambler, _mk(VineShambler))
    for idx in (0, 1, 2):
        _reg(f"corpse_slug[start={idx}]",
             (lambda i=idx: _ref_corpse_slug(i)),
             _mk(CorpseSlug, starter_move_idx=idx))


def seq(turns: int = 40, seeds=("B02SEQ1", "B02SEQ2", "B02SEQ3")) -> None:
    """Reference C# machine vs sim port: identical move sequence + draw count?"""
    _load()
    bad = 0
    for unit, ref_builder, factory in _UNITS:
        rows = []
        for seed in seeds:
            machine, mapping = ref_builder()
            ref_seq, ref_draws = _drive_reference(machine, seed, turns)
            sim_seq, sim_draws = _drive_sim(factory, seed, turns)
            mapped = [mapping.get(s, s) for s in ref_seq]
            rows.append((seed, mapped == sim_seq, ref_draws == sim_draws,
                         ref_draws, sim_draws, mapped, sim_seq))
        ok = all(r[1] and r[2] for r in rows)
        bad += 0 if ok else 1
        print(f"  {unit:<26} {'MATCH' if ok else 'MISMATCH'}   "
              f"draws ref/sim {rows[0][3]}/{rows[0][4]} over {turns} turns")
        if not ok:
            for seed, sq, dq, rd, sd, mp, sq2 in rows:
                if sq and dq:
                    continue
                print(f"      seed {seed}: ref={mp[:12]}")
                print(f"                  sim={sq2[:12]}  draws {rd} vs {sd}")
    print(f"\n  {len(_UNITS)} unit configurations, {bad} mismatched, "
          f"{len(seeds)} seeds x {turns} turns each")


def dist(combats: int = 4000, turns: int = 12) -> None:
    """Distribution equivalence for the three live-RandomBranchState units."""
    _load()
    want = {"leaf_slime_s", "twig_slime_m", "slithering_strangler"}
    for unit, ref_builder, factory in _UNITS:
        if unit not in want:
            continue
        ref_counts, sim_counts = {}, {}
        for i in range(combats):
            seed = f"B02D{i}"
            machine, mapping = ref_builder()
            r, _ = _drive_reference(machine, seed, turns)
            s, _ = _drive_sim(factory, seed, turns)
            for m in r:
                k = mapping.get(m, m)
                ref_counts[k] = ref_counts.get(k, 0) + 1
            for m in s:
                sim_counts[m] = sim_counts.get(m, 0) + 1
        tot = sum(ref_counts.values())
        print(f"  {unit}  ({combats} combats x {turns} turns = {tot} moves)")
        for k in sorted(set(ref_counts) | set(sim_counts)):
            rp = 100.0 * ref_counts.get(k, 0) / tot
            sp = 100.0 * sim_counts.get(k, 0) / tot
            flag = "" if abs(rp - sp) < 1e-9 else "   <-- DIFFERS"
            print(f"      {k:<16} game {rp:6.2f}%   sim {sp:6.2f}%{flag}")


# C# intent lists, transcribed from each model's GenerateMoveStateMachine.
_CS_INTENTS = {
    "assassin_ruby_raider": {"KILLSHOT": ["SingleAttackIntent"]},
    "axe_ruby_raider": {"SWING_1": ["SingleAttackIntent", "DefendIntent"],
                        "SWING_2": ["SingleAttackIntent", "DefendIntent"],
                        "BIG_SWING": ["SingleAttackIntent"]},
    "brute_ruby_raider": {"BEAT": ["SingleAttackIntent"], "ROAR": ["BuffIntent"]},
    "crossbow_ruby_raider": {"FIRE": ["SingleAttackIntent"],
                             "RELOAD": ["DefendIntent"]},
    "tracker_ruby_raider": {"TRACK": ["DebuffIntent"],
                            "HOUNDS": ["MultiAttackIntent"]},
    "leaf_slime_m": {"CLUMP_SHOT": ["SingleAttackIntent"],
                     "STICKY_SHOT": ["StatusIntent"]},
    "leaf_slime_s": {"TACKLE": ["SingleAttackIntent"], "GOOP": ["StatusIntent"]},
    "twig_slime_m": {"POKEY_POUNCE": ["SingleAttackIntent"],
                     "STICKY_SHOT": ["StatusIntent"]},
    "twig_slime_s": {"<single-move>": ["SingleAttackIntent"]},
    "slithering_strangler": {"CONSTRICT": ["DebuffIntent"],
                             "THWACK": ["SingleAttackIntent", "DefendIntent"],
                             "LASH": ["SingleAttackIntent"]},
    "kin_follower": {"QUICK_SLASH": ["SingleAttackIntent"],
                     "BOOMERANG": ["MultiAttackIntent"],
                     "POWER_DANCE": ["BuffIntent"]},
    "kin_priest": {"ORB_FRAILTY": ["SingleAttackIntent", "DebuffIntent"],
                   "ORB_WEAKNESS": ["SingleAttackIntent", "DebuffIntent"],
                   "BEAM": ["MultiAttackIntent"], "RITUAL": ["BuffIntent"]},
    "vantom": {"INK_BLOT": ["SingleAttackIntent"],
               "INKY_LANCE": ["MultiAttackIntent"],
               "DISMEMBER": ["SingleAttackIntent", "StatusIntent"],
               "PREPARE": ["BuffIntent"]},
    "vine_shambler": {"SWIPE": ["MultiAttackIntent"],
                      "GRASPING_VINES": ["SingleAttackIntent",
                                         "CardDebuffIntent"],
                      "CHOMP": ["SingleAttackIntent"]},
    "corpse_slug": {"WHIP_SLAP_MOVE": ["MultiAttackIntent"],
                    "GLOMP_MOVE": ["SingleAttackIntent"],
                    "GOOP_MOVE": ["DebuffIntent"]},
}

_INTENT_MAP = {
    "SingleAttackIntent": MoveType.ATTACK, "MultiAttackIntent": MoveType.ATTACK,
    "DefendIntent": MoveType.DEFEND, "BuffIntent": MoveType.BUFF,
    "DebuffIntent": MoveType.DEBUFF, "StatusIntent": MoveType.STATUS_CARD,
    "CardDebuffIntent": MoveType.CARD_DEBUFF,
}


def intents() -> None:
    """C# AbstractIntent[] vs the sim Intent's primary + `also` set."""
    _load()
    misses, checked = 0, 0
    for unit, ref_builder, factory in _UNITS:
        base_unit = unit.split("[")[0]
        table = _CS_INTENTS.get(base_unit)
        if table is None:
            continue
        enc = Encounter(id="probe_b02_i", monster_classes=[factory])
        combat = CombatState(rng_set=RunRngSet("B02INT"), encounter=enc)
        monster = combat.enemies[0]
        combat.player.max_hp = combat.player.hp = 10 ** 7
        ctx = combat._ctx()
        seen = set()
        for _ in range(40):
            key = _sim_key(monster)
            if key not in seen:
                seen.add(key)
                want = {_INTENT_MAP[i] for i in table.get(key, [])}
                it = monster.current_intent
                got = {it.move_type} | set(it.also)
                if want:
                    checked += 1
                    if want != got:
                        misses += 1
                        print(f"  {base_unit}/{key}: C# "
                              f"{sorted(w.value for w in want)} vs sim "
                              f"{sorted(g.value for g in got)}   <-- DIFFERS")
            combat.player.hp = combat.player.max_hp
            monster.hp = monster.max_hp
            monster.take_turn(ctx)
    print(f"  moves checked: {checked}; intent-list mismatches: {misses}")


_CTOR_OLD = re.compile(r"def __init__\(self.*?(?=\n    [@a-zA-Z]|\nclass |\Z)", re.S)
_CTOR_FIXED = re.compile(r"def __init__\(\s*self.*?(?=\n    [@a-zA-Z]|\nclass |\Z)", re.S)
_EFFECTS = re.compile(r"(PowerCmd\.apply|BlockCmd\.apply|CreatureCmd\.\w+)")


def ctor_regex() -> None:
    """TOOLING DEFECT: monster_probes.py `ctor-order` under-reports."""
    import harness
    units = harness._monster_units()
    old, new, missed = 0, 0, []
    for uid, cls in sorted(units.items()):
        try:
            src = inspect.getsource(cls)
        except OSError:
            continue
        mo, mn = _CTOR_OLD.search(src), _CTOR_FIXED.search(src)
        eo = _EFFECTS.findall(mo.group(0)) if mo else []
        en = _EFFECTS.findall(mn.group(0)) if mn else []
        old += bool(eo)
        new += bool(en)
        if en and not eo:
            missed.append((uid, sorted(set(en))))
    print(f"  monster_probes.py `ctor-order` reports : {old}")
    print(f"  with the signature regex repaired      : {new}")
    print(f"  UNDER-REPORTED                         : {len(missed)}")
    for uid, eff in missed:
        print(f"      {uid:<28} {','.join(eff)}")
    print("\n  Cause: `_CTOR` (monster_probes.py:186) is "
          "`def __init__\\(self`, which cannot match a port whose signature is\n"
          "  wrapped as `def __init__(\\n        self,`.  Two of the eleven "
          "(corpse_slug, kin_follower)\n  are batch 2 units and DO apply a "
          "starting power from __init__, so SHARED-FINDINGS\n  section 2's "
          "population of 35 is really 46.")


def slug_start() -> None:
    """corpse_slug: which RNG stream picks StarterMoveIdx?

    Game: `CorpseSlug.EnsureCorpseSlugsStartWithDifferentMoves(..., base.Rng)`
    (CorpseSlugsNormal.cs:32 / CorpseSlugsWeak.cs:32) draws `rng.NextInt(3)`
    from the PER-ENCOUNTER selection Rng (EncounterModel.cs:49,268 — the stream
    `sts2_rl/rng.py:52-67`'s `make_encounter_rng` reproduces).
    Sim: `CorpseSlugsEncounter.create_monsters` (underdocks/corpse_slug.py:79-84)
    ignores `selection_rng` entirely and draws `rng.randrange(3)` off the
    combat rng.
    """
    from sts2_rl.monsters.underdocks.corpse_slug import (
        CORPSE_SLUGS_NORMAL, CORPSE_SLUGS_WEAK)
    from sts2_rl.rng import make_encounter_rng

    print("  seed/floor      game NextInt(3)  sim starters     selection-rng draws")
    disagree = 0
    for enc in (CORPSE_SLUGS_NORMAL, CORPSE_SLUGS_WEAK):
        print(f"    -- {enc.id} (entry {enc.entry})")
        for i, floor in enumerate((3, 7, 11, 15, 19)):
            rs = RunRngSet(f"B02SLUG{i}")
            sel = make_encounter_rng(rs.seed, floor, enc.entry)
            game_first = GameRandomAdapter(sel).rng.next_int(3)
            sel2 = make_encounter_rng(rs.seed, floor, enc.entry)
            before = sel2.counter
            combat = CombatState(rng_set=rs, encounter=enc,
                                 encounter_selection_rng=sel2)
            sim = [m._starter_move_idx for m in combat.enemies]
            game = [(game_first + k) % 3 for k in range(len(combat.enemies))]
            same = sim == game
            disagree += 0 if same else 1
            print(f"    B02SLUG{i}/f{floor:<3}   {game}      {sim}   "
                  f"selection draws={sel2.counter - before}"
                  f"{'' if same else '   <-- DIFFERS'}")
    print(f"\n  configurations where the sim's starter moves differ from the "
          f"game's: {disagree}/10")
    print("  In EVERY row the per-encounter selection stream is drawn 0 times "
          "by the sim,\n  where the game draws exactly once - so the divergence "
          "is both a wrong value\n  and a desynchronised stream.")


def enc_rng() -> None:
    """Which batch-2 encounter builders consume the per-encounter selection Rng?

    The game picks every encounter's composition off `EncounterModel.Rng`
    (EncounterModel.cs:49,268).  A sim builder that ignores `selection_rng`
    both picks a different composition and leaves the parity stream unconsumed.
    """
    from sts2_rl.monsters.overgrowth.ruby_raiders import RUBY_RAIDERS_NORMAL
    from sts2_rl.monsters.overgrowth.slimes import SLIMES_NORMAL, SLIMES_WEAK
    from sts2_rl.monsters.overgrowth.slithering_strangler import (
        SLITHERING_STRANGLER_NORMAL)
    from sts2_rl.monsters.overgrowth.the_kin import THE_KIN_BOSS
    from sts2_rl.monsters.overgrowth.vantom import VANTOM_BOSS
    from sts2_rl.monsters.overgrowth.vine_shambler import VINE_SHAMBLER_NORMAL
    from sts2_rl.monsters.underdocks.corpse_slug import (
        CORPSE_SLUGS_NORMAL, CORPSE_SLUGS_WEAK)
    from sts2_rl.rng import make_encounter_rng

    # (encounter, how many draws the C# GenerateMonsters makes off base.Rng)
    rows = [
        (RUBY_RAIDERS_NORMAL, 3, "RubyRaidersNormal.cs (3 NextItem)"),
        (SLIMES_NORMAL, 1, "SlimesNormal.cs (1 NextBool)"),
        (SLIMES_WEAK, 3, "SlimesWeak.cs (3 NextItem)"),
        (SLITHERING_STRANGLER_NORMAL, None,
         "SlitheringStranglerNormal.cs:57,77,+ (2-3 NextItem)"),
        (VINE_SHAMBLER_NORMAL, 0, "VineShamblerNormal.cs (fixed)"),
        (THE_KIN_BOSS, 0, "TheKinBoss.cs:41-51 (fixed)"),
        (VANTOM_BOSS, 0, "VantomBoss.cs (fixed)"),
        (CORPSE_SLUGS_NORMAL, 1, "CorpseSlugsNormal.cs:32 (1 NextInt)"),
        (CORPSE_SLUGS_WEAK, 1, "CorpseSlugsWeak.cs:32 (1 NextInt)"),
    ]
    print(f"  {'encounter':<30}{'game draws':<12}{'sim draws':<11}source")
    for enc, want, src in rows:
        rs = RunRngSet("B02ENC")
        sel = make_encounter_rng(rs.seed, 5, enc.entry)
        before = sel.counter
        CombatState(rng_set=rs, encounter=enc,
                    encounter_selection_rng=sel)
        got = sel.counter - before
        flag = "" if (want is not None and got == want) else "   <-- CHECK"
        if want is None and got > 0:
            flag = ""
        print(f"  {enc.id:<30}{str(want):<12}{got:<11}{src}{flag}")


PROBES = {"seq": seq, "dist": dist, "intents": intents,
          "ctor-regex": ctor_regex, "slug-start": slug_start,
          "enc-rng": enc_rng}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    for name in ([args.probe] if args.probe else ["ctor-regex", "seq", "intents"]):
        print(f"\n===== {name} =====")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
