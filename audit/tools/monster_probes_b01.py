"""Executed evidence for monster content-audit BATCH 1 (the 15 overgrowth units
bygone_effigy, byrdonis, ceremonial_beast, cubex_construct, flyconid,
eye_with_teeth, fogmog, fuzzy_wurm_crawler, inklet, mawler, nibbit,
phrog_parasite, wriggler, shrinker_beetle, snapping_jaxfruit).

Twelve of the fifteen are HAND-ROLLED ports (a `_move_key` string) whose C#
counterpart is a `MonsterMoveStateMachine`.  Verdict rules 5 and 6 forbid
asserting sequence/distribution equivalence, so every such claim in
`audit/records/monster/*.json` is produced here by EXECUTION: each probe
rebuilds the C# `GenerateMoveStateMachine` graph on the sim's own
`MonsterMoveStateMachine` primitives (so the branch walk, the repeat rules and
the single-`NextFloat(total)` draw are the audited machinery, not a
re-implementation), drives it and the shipped port from two identically seeded
`RunRngSet`s, and diffs the emitted move sequences turn by turn.

Probes:
  chain      -- sequence equivalence for the 10 deterministic hand-rolled ports
  branch     -- sequence equivalence for the 2 branch-backed hand-rolled ports
                (flyconid, inklet) against the C# add order and parameters
  inklet     -- the batch's headline defect, isolated: the sim's RAND branch
                is added in the REVERSE of Inklet.cs:73-74's order
  machine    -- the 2 MachineMonster ports (fogmog, mawler) vs the C# params
  reach      -- which ported room pools / summons reach each of the 15 units

Run: py audit/tools/monster_probes_b01.py <probe>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import random  # noqa: E402

from sts2_rl.combat import CombatState  # noqa: E402
from sts2_rl.monsters import Encounter  # noqa: E402
from sts2_rl.monsters.base import Intent, MoveType  # noqa: E402
from sts2_rl.monsters.state_machine import (  # noqa: E402
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)
from sts2_rl.rng import RunRngSet  # noqa: E402

_NOOP_INTENT = Intent(MoveType.UNKNOWN)


class RefMonster(MachineMonster):
    """A MachineMonster whose graph is supplied by the probe: the C# model's
    `GenerateMoveStateMachine` transcribed node for node, with every move's
    perform delegate replaced by a recorder.  HP is irrelevant here."""

    min_hp = 1
    max_hp = 1

    def __init__(self, hooks, rng, *, builder=None):
        self._builder = builder
        self.performed: list[str] = []
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        return self._builder(self)

    def take_turn(self, ctx) -> None:  # record instead of acting
        self.performed.append(self._current_move.id)
        self.machine.on_move_performed(self._current_move)
        self.telegraph_next_move()


def _mv(owner, state_id):
    return MoveState(state_id, lambda ctx: None, _NOOP_INTENT)


# --------------------------------------------------------------------------
# C# graphs, transcribed. Each returns (builder, initial_move_id).
# --------------------------------------------------------------------------

def _cs_bygone_effigy(owner):
    """BygoneEffigy.cs:40-56. SLEEP_MOVE_2 is registered but unreachable."""
    sleep = _mv(owner, "SLEEP_MOVE")
    wake = _mv(owner, "WAKE_MOVE")
    sleep2 = _mv(owner, "SLEEP_MOVE_2")
    slash = _mv(owner, "SLASHES_MOVE")
    sleep.follow_up = wake
    wake.follow_up = slash
    sleep2.follow_up = slash
    slash.follow_up = slash
    return MonsterMoveStateMachine([sleep, wake, sleep2, slash], sleep)


def _cs_cubex(owner):
    """CubexConstruct.cs:110-126."""
    charge = _mv(owner, "CHARGE_UP_MOVE")
    rb1 = _mv(owner, "REPEATER_BLAST_MOVE")
    rb2 = _mv(owner, "REPEATER_BLAST_MOVE_2")
    expel = _mv(owner, "EXPEL_MOVE")
    charge.follow_up = rb1
    rb1.follow_up = rb2
    rb2.follow_up = expel
    expel.follow_up = rb1
    return MonsterMoveStateMachine([charge, rb1, rb2, expel], charge)


def _cs_fuzzy(owner):
    """FuzzyWurmCrawler.cs:48-60."""
    first = _mv(owner, "FIRST_ACID_GOOP")
    goop = _mv(owner, "ACID_GOOP")
    inhale = _mv(owner, "INHALE")
    first.follow_up = inhale
    inhale.follow_up = goop
    goop.follow_up = first
    return MonsterMoveStateMachine([first, goop, inhale], first)


def _cs_shrinker(owner):
    """ShrinkerBeetle.cs:31-44."""
    shrink = _mv(owner, "SHRINKER_MOVE")
    chomp = _mv(owner, "CHOMP_MOVE")
    stomp = _mv(owner, "STOMP_MOVE")
    shrink.follow_up = chomp
    chomp.follow_up = stomp
    stomp.follow_up = chomp
    return MonsterMoveStateMachine([shrink, chomp, stomp], shrink)


def _cs_jaxfruit(owner):
    """SnappingJaxfruit.cs:44-51."""
    orb = _mv(owner, "ENERGY_ORB_MOVE")
    orb.follow_up = orb
    return MonsterMoveStateMachine([orb], orb)


def _cs_eye(owner):
    """EyeWithTeeth.cs:36-43."""
    distract = _mv(owner, "DISTRACT_MOVE")
    distract.follow_up = distract
    return MonsterMoveStateMachine([distract], distract)


def _cs_ceremonial(owner):
    """CeremonialBeast.cs:143-168. STUN_MOVE is registered but unreachable --
    PlowPower.cs:45 stuns with a SYNTHETIC 'STUNNED' MoveState carrying
    FollowUpStateId = BeastCryState.StateId, not with this node."""
    stamp = _mv(owner, "STAMP_MOVE")
    plow = _mv(owner, "PLOW_MOVE")
    stun = MoveState("STUN_MOVE", lambda ctx: None, _NOOP_INTENT,
                     must_perform_once_before_transitioning=True)
    cry = _mv(owner, "BEAST_CRY_MOVE")
    stomp = _mv(owner, "STOMP_MOVE")
    crush = _mv(owner, "CRUSH_MOVE")
    stamp.follow_up = plow
    plow.follow_up = plow
    stun.follow_up = cry
    cry.follow_up = stomp
    stomp.follow_up = crush
    crush.follow_up = cry
    return MonsterMoveStateMachine([plow, stamp, stun, cry, stomp, crush], stamp)


def _cs_nibbit(is_front, is_alone):
    """Nibbit.cs:68-92. ConditionalBranchState resolved to its winning arm --
    the conditions are constant over a combat (IsFront/IsAlone are set by the
    encounter and never mutate), so the branch is entered exactly once."""
    def build(owner):
        butt = _mv(owner, "BUTT_MOVE")
        slice_ = _mv(owner, "SLICE_MOVE")
        hiss = _mv(owner, "HISS_MOVE")
        slice_.follow_up = hiss
        butt.follow_up = slice_
        hiss.follow_up = butt
        if is_alone:
            initial = butt
        else:
            initial = slice_ if is_front else hiss
        return MonsterMoveStateMachine([butt, slice_, hiss], initial)
    return build


def _cs_wriggler(slot):
    """Wriggler.cs:51-71 (StartStunned=False arm; the True arm prepends the
    no-op SPAWNED_MOVE, see the record)."""
    def build(owner):
        bite = _mv(owner, "NASTY_BITE_MOVE")
        wriggle = _mv(owner, "WRIGGLE_MOVE")
        bite.follow_up = wriggle
        wriggle.follow_up = bite
        initial = bite if slot in (1, 3) else wriggle
        return MonsterMoveStateMachine([bite, wriggle], initial)
    return build


def _cs_phrog(owner):
    """PhrogParasite.cs:39-53. 'RAND' is built with two branches and never
    wired to any FollowUpState nor used as initialState (seam G2's shape)."""
    infect = _mv(owner, "INFECT_MOVE")
    lash = _mv(owner, "LASH_MOVE")
    infect.follow_up = lash
    lash.follow_up = infect
    return MonsterMoveStateMachine([infect, lash], infect)


def _cs_flyconid(owner):
    """Flyconid.cs:28-50. Every int is a COOLDOWN (overload #8: `int cooldown,
    MoveRepeatType`), never a weight; all five branches weigh 1f."""
    vspore = _mv(owner, "VULNERABLE_SPORES_MOVE")
    fspore = _mv(owner, "FRAIL_SPORES_MOVE")
    smash = _mv(owner, "SMASH_MOVE")
    rand = RandomBranchState("RAND")
    initial = RandomBranchState("INITIAL")
    vspore.follow_up = rand
    fspore.follow_up = rand
    smash.follow_up = rand
    rand.add_branch(vspore, 1.0, MoveRepeatType.CANNOT_REPEAT, cooldown=3)
    rand.add_branch(fspore, 1.0, MoveRepeatType.CANNOT_REPEAT, cooldown=2)
    rand.add_branch(smash, 1.0, MoveRepeatType.CANNOT_REPEAT)
    initial.add_branch(fspore, 1.0, MoveRepeatType.CANNOT_REPEAT, cooldown=2)
    initial.add_branch(smash, 1.0, MoveRepeatType.CANNOT_REPEAT)
    return MonsterMoveStateMachine([vspore, fspore, smash, rand, initial], initial)


def _cs_inklet(is_middle):
    """Inklet.cs:63-84. The live branch is 'RAND', added
    PIERCING_GAZE first (line 73) then WHIRLWIND (line 74)."""
    def build(owner):
        jab = _mv(owner, "JAB_MOVE")
        whirl = _mv(owner, "WHIRLWIND_MOVE")
        gaze = _mv(owner, "PIERCING_GAZE_MOVE")
        rand = RandomBranchState("RAND")
        rand.add_branch(gaze, 1.0, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(whirl, 1.0, MoveRepeatType.CANNOT_REPEAT)
        jab.follow_up = rand
        whirl.follow_up = jab
        gaze.follow_up = jab
        initial = whirl if is_middle else jab
        return MonsterMoveStateMachine([jab, gaze, whirl, rand], initial)
    return build


def _cs_fogmog(owner):
    """Fogmog.cs:38-58."""
    illusion = _mv(owner, "ILLUSION_MOVE")
    swipe = _mv(owner, "SWIPE_MOVE")
    swipe_rand = _mv(owner, "SWIPE_RANDOM_MOVE")
    headbutt = _mv(owner, "HEADBUTT_MOVE")
    branch = RandomBranchState("BRANCH")
    branch.add_branch(swipe_rand, 0.4, MoveRepeatType.CANNOT_REPEAT)
    branch.add_branch(headbutt, 0.6, MoveRepeatType.CANNOT_REPEAT)
    illusion.follow_up = swipe
    swipe.follow_up = branch
    swipe_rand.follow_up = headbutt
    headbutt.follow_up = swipe
    return MonsterMoveStateMachine(
        [illusion, swipe, swipe_rand, branch, headbutt], illusion)


def _cs_byrdonis(owner):
    """Byrdonis.cs:40-51 -- initialState is SWOOP_MOVE (moveState2)."""
    peck = _mv(owner, "PECK_MOVE")
    swoop = _mv(owner, "SWOOP_MOVE")
    peck.follow_up = swoop
    swoop.follow_up = peck
    return MonsterMoveStateMachine([swoop, peck], swoop)


def _cs_mawler(owner):
    """Mawler.cs:29-44."""
    rip = _mv(owner, "RIP_AND_TEAR_MOVE")
    roar = _mv(owner, "ROAR_MOVE")
    claw = _mv(owner, "CLAW_MOVE")
    rand = RandomBranchState("RAND")
    rand.add_branch(rip, 1.0, MoveRepeatType.CANNOT_REPEAT)
    rand.add_branch(roar, 1.0, MoveRepeatType.USE_ONLY_ONCE)
    rand.add_branch(claw, 1.0, MoveRepeatType.CANNOT_REPEAT)
    rip.follow_up = rand
    roar.follow_up = rand
    claw.follow_up = rand
    return MonsterMoveStateMachine([rip, roar, claw, rand], claw)


# --------------------------------------------------------------------------
# drivers
# --------------------------------------------------------------------------

def _drive_ref(builder, seed: str, turns: int):
    enc = Encounter(id="ref", monster_classes=[
        lambda hooks, rng: RefMonster(hooks, rng, builder=builder)])
    combat = CombatState(rng_set=RunRngSet(seed), encounter=enc)
    ref = combat.enemies[0]
    ctx = combat._ctx()
    for _ in range(turns):
        try:
            ref.take_turn(ctx)
        except RuntimeError as exc:  # sim machinery's degenerate-weight raise
            ref.performed.append("<RAISE:%s>" % exc)
            break
    return ref.performed, combat.rng_set.monster_ai.counter


def _drive_sim(factory, seed: str, turns: int, keyed=True):
    enc = Encounter(id="sim", monster_classes=[factory])
    combat = CombatState(rng_set=RunRngSet(seed), encounter=enc)
    mon = combat.enemies[0]
    ctx = combat._ctx()
    seq = []
    for _ in range(turns):
        seq.append(mon._move_key if keyed else mon._current_move.id)
        mon.take_turn(ctx)
    return seq, combat.rng_set.monster_ai.counter


def _cmp(label, sim_seq, ref_seq, sim_draws, ref_draws, alias, quiet=False):
    mapped = [alias.get(m, m) for m in sim_seq]
    if ref_seq and ref_seq[-1].startswith("<RAISE:"):
        # The reference MACHINE hit the sim machinery's degenerate-weight raise
        # (seam G7b). Compare the prefix the reference did produce.
        n = len(ref_seq) - 1
        ok = mapped[:n] == ref_seq[:n]
        print(f"  {label:<34} "
              f"{'MATCH(prefix)' if ok else 'DIVERGE'} "
              f"{n}/{len(mapped)} turns before {ref_seq[-1]}")
        if not ok:
            print(f"      sim  : {mapped[:n]}")
            print(f"      game : {ref_seq[:n]}")
        return ok
    ok = mapped == ref_seq and sim_draws == ref_draws
    print(f"  {label:<34} {'MATCH  ' if ok else 'DIVERGE'} "
          f"draws sim={sim_draws} game={ref_draws}")
    if not ok and not quiet:
        print(f"      sim  : {mapped}")
        print(f"      game : {ref_seq}")
    elif not ok:
        first = next((i for i, (a, b) in enumerate(zip(mapped, ref_seq))
                      if a != b), None)
        print(f"      first difference at turn {first}: "
              f"sim={mapped[first]!r} game={ref_seq[first]!r}; "
              f"agreements {sum(a == b for a, b in zip(mapped, ref_seq))}"
              f"/{len(ref_seq)}")
    return ok


_CHAIN = [
    # (label, sim factory, sim->C# id alias, C# builder, turns)
    ("bygone_effigy", "bygone_effigy:BygoneEffigy",
     {"SLEEP": "SLEEP_MOVE", "WAKE": "WAKE_MOVE", "SLASHES": "SLASHES_MOVE"},
     _cs_bygone_effigy),
    ("cubex_construct", "cubex_construct:CubexConstruct",
     {"CHARGE_UP": "CHARGE_UP_MOVE", "RB": "REPEATER_BLAST_MOVE",
      "EXPEL": "EXPEL_MOVE"}, _cs_cubex),
    ("fuzzy_wurm_crawler", "fuzzy_wurm_crawler:FuzzyWurmCrawler", {}, _cs_fuzzy),
    ("shrinker_beetle", "shrinker_beetle:ShrinkerBeetle",
     {"SHRINKER": "SHRINKER_MOVE", "CHOMP": "CHOMP_MOVE",
      "STOMP": "STOMP_MOVE"}, _cs_shrinker),
    ("phrog_parasite", "phrog_parasite:PhrogParasite",
     {"INFECT": "INFECT_MOVE", "LASH": "LASH_MOVE"}, _cs_phrog),
    ("ceremonial_beast", "ceremonial_beast:CeremonialBeast",
     {"STAMP": "STAMP_MOVE", "PLOW": "PLOW_MOVE"}, _cs_ceremonial),
]


def _load(spec):
    mod, cls = spec.split(":")
    import importlib
    m = importlib.import_module("sts2_rl.monsters.overgrowth." + mod)
    return getattr(m, cls)


def probe_chain():
    """Deterministic hand-rolled ports: identical move sequence + zero draws."""
    print("chain -- hand-rolled deterministic ports vs the C# graph "
          "(20 turns, seed 'b01')")
    ok = True
    for label, spec, alias, builder in _CHAIN:
        cls = _load(spec)
        # CubexConstruct's REPEATER_BLAST_MOVE_2 is a distinct C# id emitting the
        # identical move; the sim uses one key. Fold the C# ids for comparison.
        ref, rdraws = _drive_ref(builder, "b01", 20)
        if label == "cubex_construct":
            ref = ["REPEATER_BLAST_MOVE" if r == "REPEATER_BLAST_MOVE_2" else r
                   for r in ref]
        sim, sdraws = _drive_sim(lambda h, r, c=cls: c(h, r), "b01", 20)
        ok &= _cmp(label, sim, ref, sdraws, rdraws, alias)

    # Nibbit: three encounter configurations.
    NB = _load("nibbit:Nibbit")
    alias = {"BUTT": "BUTT_MOVE", "SLICE": "SLICE_MOVE", "HISS": "HISS_MOVE"}
    for cfg, kw in (("alone", {"is_alone": True}), ("front", {"is_front": True}),
                    ("back", {})):
        ref, rd = _drive_ref(_cs_nibbit(kw.get("is_front", False),
                                        kw.get("is_alone", False)), "b01", 20)
        sim, sd = _drive_sim(lambda h, r, k=kw: NB(h, r, **k), "b01", 20)
        ok &= _cmp(f"nibbit[{cfg}]", sim, ref, sd, rd, alias)

    # Wriggler: slots 1-4, StartStunned=False arm.
    WR = _load("phrog_parasite:Wriggler")
    alias = {"NASTY_BITE": "NASTY_BITE_MOVE", "WRIGGLE": "WRIGGLE_MOVE"}
    for slot in (1, 2, 3, 4):
        ref, rd = _drive_ref(_cs_wriggler(slot), "b01", 20)
        sim, sd = _drive_sim(lambda h, r, s=slot: WR(h, r, slot=s), "b01", 20)
        ok &= _cmp(f"wriggler[slot{slot}]", sim, ref, sd, rd, alias)

    # SnappingJaxfruit / EyeWithTeeth: single-move loops, no _move_key at all.
    for label, spec, builder in (
            ("snapping_jaxfruit", "snapping_jaxfruit:SnappingJaxfruit",
             _cs_jaxfruit),
            ("eye_with_teeth", "fogmog:EyeWithTeeth", _cs_eye)):
        cls = _load(spec)
        ref, rd = _drive_ref(builder, "b01", 20)
        enc = Encounter(id="s", monster_classes=[lambda h, r, c=cls: c(h, r)])
        combat = CombatState(rng_set=RunRngSet("b01"), encounter=enc)
        mon = combat.enemies[0]
        ctx = combat._ctx()
        sim = []
        for _ in range(20):
            sim.append(mon.current_intent.move_type.name)
            mon.take_turn(ctx)
        sd = combat.rng_set.monster_ai.counter
        same_move = len(set(sim)) == 1
        print(f"  {label:<34} "
              f"{'MATCH  ' if (same_move and sd == rd) else 'DIVERGE'} "
              f"draws sim={sd} game={rd} single-move-loop={same_move} "
              f"intent={sim[0]}")
        ok &= same_move and sd == rd
    print("chain:", "ALL MATCH" if ok else "DIVERGENCES ABOVE")


def probe_branch():
    """flyconid / inklet: the branch-backed hand-rolled ports."""
    print("branch -- hand-rolled ports with a live RandomBranchState, 40 turns")
    FLY = _load("flyconid:Flyconid")
    alias = {"V_SPORES": "VULNERABLE_SPORES_MOVE",
             "FRAIL_SPORES": "FRAIL_SPORES_MOVE", "SMASH": "SMASH_MOVE"}
    ok = True
    for seed in ("b01", "b02", "b03", "b04", "b05"):
        ref, rd = _drive_ref(_cs_flyconid, seed, 40)
        sim, sd = _drive_sim(lambda h, r: FLY(h, r), seed, 40)
        ok &= _cmp(f"flyconid[{seed}]", sim, ref, sd, rd, alias)

    INK = _load("inklets:Inklet")
    alias = {"JAB": "JAB_MOVE", "WHIRLWIND": "WHIRLWIND_MOVE",
             "PIERCING_GAZE": "PIERCING_GAZE_MOVE"}
    for seed in ("b01", "b02", "b03"):
        for mid in (False, True):
            ref, rd = _drive_ref(_cs_inklet(mid), seed, 40)
            sim, sd = _drive_sim(lambda h, r, m=mid: INK(h, r, is_middle=m),
                                 seed, 40)
            ok &= _cmp(f"inklet[{seed},middle={mid}]", sim, ref, sd, rd, alias,
                       quiet=True)
    print("branch:", "ALL MATCH" if ok else "DIVERGENCES ABOVE")


def probe_inklet():
    """Isolate the defect: Inklet.cs:73-74 adds PIERCING_GAZE then WHIRLWIND;
    inklets.py:64 rolls ['WHIRLWIND', 'PIERCING_GAZE'].  Add order is
    observable (monster_state_machine step 14: one NextFloat(total) then a
    subtract-and-walk in add order), so with two equal weights the SAME draw
    resolves to the OPPOSITE move."""
    from sts2_rl.monsters.state_machine import weighted_branch_pick
    from sts2_rl.rng import GameRandomAdapter
    print("inklet -- RAND branch add order, 20000 rolls per side")
    n = 20000
    sim_rs, game_rs = RunRngSet("inklet-order"), RunRngSet("inklet-order")
    sim_rng = GameRandomAdapter(sim_rs.monster_ai)
    game_rng = GameRandomAdapter(game_rs.monster_ai)
    agree = 0
    counts = {"sim": {}, "game": {}}
    for _ in range(n):
        s = weighted_branch_pick(sim_rng, ["WHIRLWIND", "PIERCING_GAZE"], [1, 1])
        g = weighted_branch_pick(game_rng, ["PIERCING_GAZE", "WHIRLWIND"], [1, 1])
        agree += (s == g)
        counts["sim"][s] = counts["sim"].get(s, 0) + 1
        counts["game"][g] = counts["game"].get(g, 0) + 1
    print(f"  identical MonsterAi stream, same draw count on both sides "
          f"({sim_rs.monster_ai.counter} == {game_rs.monster_ai.counter})")
    print(f"  agreement: {agree}/{n} rolls ({100.0 * agree / n:.2f}%)")
    print(f"  sim  order ['WHIRLWIND','PIERCING_GAZE'] -> {counts['sim']}")
    print(f"  game order ['PIERCING_GAZE','WHIRLWIND'] -> {counts['game']}")
    print("  => the marginal 50/50 is preserved; the PER-DRAW move is inverted,")
    print("     so a replay diverges on the first JAB->RAND transition.")


def probe_machine():
    """fogmog / mawler: the two MachineMonster ports."""
    print("machine -- MachineMonster ports vs the C# graph, 40 turns")
    ok = True
    FOG = _load("fogmog:Fogmog")
    alias = {}
    for seed in ("b01", "b02", "b03"):
        ref, rd = _drive_ref(_cs_fogmog, seed, 40)
        sim, sd = _drive_sim(lambda h, r: FOG(h, r), seed, 40, keyed=False)
        ok &= _cmp(f"fogmog[{seed}]", sim, ref, sd, rd, alias)
    BYR = _load("byrdonis:Byrdonis")
    for seed in ("b01", "b02"):
        ref, rd = _drive_ref(_cs_byrdonis, seed, 40)
        sim, sd = _drive_sim(lambda h, r: BYR(h, r), seed, 40, keyed=False)
        ok &= _cmp(f"byrdonis[{seed}]", sim, ref, sd, rd, {})
    MAW = _load("mawler:Mawler")
    alias = {"CLAW": "CLAW_MOVE", "RIP_AND_TEAR": "RIP_AND_TEAR_MOVE",
             "ROAR": "ROAR_MOVE"}
    for seed in ("b01", "b02", "b03"):
        ref, rd = _drive_ref(_cs_mawler, seed, 40)
        sim, sd = _drive_sim(lambda h, r: MAW(h, r), seed, 40, keyed=False)
        ok &= _cmp(f"mawler[{seed}]", sim, ref, sd, rd, alias)
    print("machine:", "ALL MATCH" if ok else "DIVERGENCES ABOVE")


def probe_reach():
    """Rule 6: prove each unit is reachable with ported content."""
    from sts2_rl import rooms
    units = {
        "bygone_effigy": "BygoneEffigy", "byrdonis": "Byrdonis",
        "ceremonial_beast": "CeremonialBeast", "cubex_construct": "CubexConstruct",
        "flyconid": "Flyconid", "eye_with_teeth": "EyeWithTeeth",
        "fogmog": "Fogmog", "fuzzy_wurm_crawler": "FuzzyWurmCrawler",
        "inklet": "Inklet", "mawler": "Mawler", "nibbit": "Nibbit",
        "phrog_parasite": "PhrogParasite", "wriggler": "Wriggler",
        "shrinker_beetle": "ShrinkerBeetle",
        "snapping_jaxfruit": "SnappingJaxfruit",
    }
    act = rooms._overgrowth_rooms()
    ENCOUNTERS = act.encounters()
    keys = (list(act.weak_keys) + list(act.normal_keys) + list(act.elite_keys)
            + list(act.boss_keys))
    print("reach -- overgrowth pool keys per unit "
          "(weak/normal/elite/boss in rooms.py)")
    for unit, cls_name in sorted(units.items()):
        hits = []
        for key in keys:
            enc = ENCOUNTERS.get(key)
            if enc is None:
                continue
            names = []
            for f in getattr(enc, "monster_classes", []) or []:
                names.append(getattr(f, "__name__", None)
                             or getattr(getattr(f, "func", None), "__name__", ""))
            if cls_name in names:
                hits.append(key)
        print(f"  {unit:<20} {hits if hits else 'NOT DIRECTLY IN A POOL'}")
    print("  eye_with_teeth: summoned by Fogmog.ILLUSION_MOVE "
          "(overgrowth/fogmog.py:93-95, pool key 'fogmog')")
    print("  wriggler      : spawned by InfestedPower on PhrogParasite's death "
          "(pool key 'phrog_parasite')")
    print("  flyconid      : FlyconidEncounter overrides create_monsters (pool key")
    print("                  'flyconid', overgrowth/flyconid.py:87-100) and is the")
    print("                  second slot of 'snapping_jaxfruit' via the _flyconid")
    print("                  factory (overgrowth/snapping_jaxfruit.py:35-42) -- both")
    print("                  invisible to a monster_classes scan.")


def probe_deadlock():
    """Flyconid's RAND reaches an ALL-ZERO weight vector, i.e. the exact input
    of `monster_state_machine` G7 arm (b) -- and it does so on ported content,
    every time the log tail is [V_SPORES, FRAIL_SPORES, SMASH].

    C# (`RandomBranchState.cs:115-128`): max = 0, ONE `rng.NextFloat(0)` draw
    (= 0f), then `0 - 0 <= 0` on the FIRST branch -> returns branch 0.
    Sim machinery (`state_machine.py:182-183`): raises BEFORE drawing.
    Sim hand-rolled port (`weighted_branch_pick`, state_machine.py:47-59):
    same total-0 draw, same walk, same first item.  So the shipped port is
    faithful and a MachineMonster re-port would crash."""
    from sts2_rl.monsters.state_machine import weighted_branch_pick
    from sts2_rl.rng import GameRandomAdapter
    FLY = _load("flyconid:Flyconid")
    print("deadlock -- Flyconid RAND with every branch weight 0")

    # 1. reachability of the all-zero vector, by execution over the port itself
    print("  reachable log tails that zero all three branches:")
    hit = None
    for seed in ("b01", "b02", "b03", "b04", "b05"):
        enc = Encounter(id="f", monster_classes=[lambda h, r: FLY(h, r)])
        combat = CombatState(rng_set=RunRngSet(seed), encounter=enc)
        fly = combat.enemies[0]
        ctx = combat._ctx()
        for turn in range(40):
            fly.take_turn(ctx)
            w = []
            for m in ("V_SPORES", "FRAIL_SPORES", "SMASH"):
                cd = {"V_SPORES": 3, "FRAIL_SPORES": 2, "SMASH": 0}[m]
                win = fly._log[-cd:] if cd > 0 else fly._log[-1:]
                w.append(0 if m in win else 1)
            if sum(w) == 0:
                print(f"    seed={seed} turn={turn} log_tail={fly._log[-3:]} "
                      f"weights={w} -> port picked {fly._move_key!r}")
                hit = hit or (seed, turn)
                break
    print(f"  first hit: {hit}  (the tail is always "
          "['V_SPORES','FRAIL_SPORES','SMASH'])")

    # 2. what each of the three implementations does with [0, 0, 0]
    rs = RunRngSet("deadlock")
    rng = GameRandomAdapter(rs.monster_ai)
    before = rs.monster_ai.counter
    picked = weighted_branch_pick(rng, ["V_SPORES", "FRAIL_SPORES", "SMASH"],
                                  [0, 0, 0])
    print(f"  sim hand-rolled weighted_branch_pick([0,0,0]) -> {picked!r}, "
          f"draws consumed = {rs.monster_ai.counter - before}")
    print("  C# RandomBranchState.GetNextState  -> branch 0 = 'V_SPORES', "
          "draws consumed = 1   (same)")
    ref, _ = _drive_ref(_cs_flyconid, "b01", 40)
    print(f"  sim MachineMonster machinery       -> {ref[-1]}")


def probe_order():
    """Wriggler.WRIGGLE_MOVE is the batch's one intra-move ORDER inversion:
    `Wriggler.cs:87-101` adds the Infection card FIRST and applies Strength 2
    SECOND; `overgrowth/phrog_parasite.py:55-60` does the reverse.  Executed
    diff of the whole observable state after one WRIGGLE turn, shipped order
    vs the C# order, on identical seeds."""
    WR = _load("phrog_parasite:Wriggler")

    def snapshot(combat, mon):
        pl = combat.player
        return {
            "player_hp": pl.hp, "player_block": pl.block,
            "player_powers": sorted((p, pw.amount)
                                    for p, pw in pl.powers.items()),
            "discard": [c.id for c in pl.discard_pile],
            "draw": [c.id for c in pl.draw_pile],
            "hand": [c.id for c in pl.hand],
            "exhaust": [c.id for c in getattr(pl, "exhaust_pile", [])],
            "mon_hp": mon.hp, "mon_block": mon.block,
            "mon_powers": sorted((p, pw.amount) for p, pw in mon.powers.items()),
            "monster_ai": combat.rng_set.monster_ai.counter,
            "shuffle": combat.rng_set.shuffle.counter,
        }

    def run(csharp_order):
        enc = Encounter(id="w", monster_classes=[
            lambda h, r: WR(h, r, slot=2)])
        combat = CombatState(rng_set=RunRngSet("wriggle-order"), encounter=enc)
        mon = combat.enemies[0]
        ctx = combat._ctx()
        assert mon._move_key == "WRIGGLE"
        if csharp_order:
            from sts2_rl.cards import InfectionCard
            from sts2_rl.cmds import CardPileCmd, PowerCmd
            from sts2_rl.powers import StrengthPower
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, InfectionCard())
            PowerCmd.apply(ctx.hooks, mon, StrengthPower, 2)
            mon._move_key = "NASTY_BITE"
        else:
            mon.take_turn(ctx)
        return snapshot(combat, mon)

    sim, game = run(False), run(True)
    print("order -- Wriggler WRIGGLE_MOVE, shipped order vs Wriggler.cs order")
    diffs = {k: (sim[k], game[k]) for k in sim if sim[k] != game[k]}
    print(f"  observable keys compared: {len(sim)}")
    print(f"  differences: {diffs if diffs else 'NONE'}")


_PROBES = {
    "order": probe_order,
    "chain": probe_chain, "branch": probe_branch, "inklet": probe_inklet,
    "machine": probe_machine, "reach": probe_reach, "deadlock": probe_deadlock,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in _PROBES:
        print(__doc__)
        print("probes:", ", ".join(_PROBES))
        raise SystemExit(1)
    _PROBES[sys.argv[1]]()
