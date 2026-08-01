"""Reproducible probes for seam/monster_state_machine (Task 10).

Same contract as audit/tools/dormancy_probes.py: every "executed evidence"
number the record states is produced here so a later auditor can re-derive it.

  py audit/tools/state_machine_probes.py                # every probe
  py audit/tools/state_machine_probes.py cs-addbranch   # one probe

Probes:
  cs-addbranch      the AddBranch overload census: every C# monster call site
                    resolved to one of the 10 overloads, with the role of each
                    int argument (cooldown vs maxRepeats) spelled out.
  sim-addbranch     the same census on the sim's MachineMonster ports, with
                    each call's effective (weight, repeat, max_times, cooldown).
  addbranch-diff    the two joined per monster: which C# branch semantics the
                    sim port reproduces and which it drops.
  branch-order      C# AddBranch *add order* per RandomBranchState (resolved
                    to MoveState string ids) vs the sim port's — the walk in
                    GetNextState is order-sensitive, so an inverted pair picks
                    the opposite move for the same draw.
  hand-rolled       sim Monster subclasses whose C# counterpart HAS a
                    RandomBranchState — the population exposed to the
                    weight-vs-cooldown misreading.
  move-rng          which sim monsters roll their move off combat_rng.monster_ai
                    and which use some other stream.
  zero-weight       is "every branch weight zeroed" reachable in a ported
                    machine? (round 12 T22: both sides now return branch 0 --
                    see zero_weight()'s docstring for the message-grep fix
                    and why the mechanism this probe hunted is now closed)
  cs-conditional    the ConditionalBranchState.AddState census (the second
                    branch dispatcher; cs-addbranch does not see it).
  mismatch          EXECUTED: for every ported RandomBranchState, the C#
                    branch tuple (weight, repeatType, maxTimes, cooldown) vs
                    the sim port's, listed per branch. The record's
                    "N monsters misread the int argument" number comes from here.
  distribution      EXECUTED: the observable of `mismatch` — roll each
                    mismatched sim machine 100000 times and, beside it, the
                    same machine with the C# branch parameters restored.
  sources-sweep     rule 7 mechanised: every .cs/.py file the record or the
                    spec doc cites must appear in SEAM_SOURCES. PATH-AWARE.
  stun-machine      EXECUTED: what a stun does to the move machine on each
                    side (sim keeps _current_move and never touches the
                    machine; C# force-sets a synthetic STUNNED MoveState and
                    re-logs the deferred move) — plus the 2x2 that separates
                    G4's missing duplicate from G1's mis-read parameters on
                    the stun-REACHABLE monster.
  stun-sites        EXECUTED: every CreatureCmd.stun call site in the sim, self
                    vs external target, and the branch class of every monster
                    that can hold a stunning power. Backs step 38 (rule 5) and
                    completes G4/G5's caller inventories.
  whistle-route     EXECUTED: the only player-reachable stun end to end —
                    tanx -> Tanx's Whistle -> the Whistle card -> which act's
                    monsters — and the branch class of every monster in that
                    act's pools. This is G4's liveness proof.
  nondyadic-weights EXECUTED: G7 clause c's named trigger. Finds every ported
                    branch with a CALLABLE weight, opens the gate that makes
                    the weight non-dyadic, and fuzzes it.
  spawn-roll        EXECUTED: the `PrepareForNextTurn(rollNewMove: false)`
                    hand-off from creature_card_cmds step 3 — C#'s spawn-roll
                    truth table vs the sim's roll-at-construction.
  raise-sites       the raise/throw census, bucketed. Backs guard N7's count
                    of what it does and does not cover.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit.tools.harness import DEFAULT_GAME_ROOT  # noqa: E402

CS_MONSTER_DIR = "src/Core/Models/Monsters"
SIM_MONSTER_DIR = "sts2_rl/monsters"

# The 10 RandomBranchState.AddBranch overloads (RandomBranchState.cs:46-113),
# keyed by the argument-type sequence AFTER the leading MonsterState.
#   role tuple = (cooldown source, maxRepeats source, repeatType, weight source)
# "-" means the overload does not supply it (defaults: cooldown 0, maxTimes 0,
# weight 1f, repeatType from the argument).
OVERLOADS: dict[tuple[str, ...], tuple[str, str]] = {
    ("int", "repeat", "func"): ("46", "int=cooldown"),
    ("int", "int", "func"): ("62", "int0=cooldown int1=maxRepeats"),
    ("int", "func"): ("75", "int=maxRepeats"),
    ("int", "repeat", "float"): ("80", "int=cooldown"),
    ("repeat", "float"): ("85", "no int"),
    ("repeat", "func"): ("90", "no int"),
    ("int", "float"): ("95", "int=maxRepeats"),
    ("int", "repeat"): ("100", "int=cooldown"),
    ("int",): ("105", "int=maxRepeats"),
    ("repeat",): ("110", "no int"),
}


def _split_args(text: str) -> list[str]:
    """Split a C#/Python argument list on top-level commas."""
    out, depth, buf = [], 0, ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


def _call_text(src: str, open_idx: int) -> str:
    """Text between the '(' at open_idx and its matching ')'."""
    depth = 0
    for i in range(open_idx, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return src[open_idx + 1:i]
    raise ValueError("unbalanced call")


def _arg_kind(tok: str) -> str:
    tok = tok.strip()
    if tok.startswith("MoveRepeatType."):
        return "repeat"
    if re.fullmatch(r"-?\d+", tok):
        return "int"
    if re.fullmatch(r"-?\d*\.?\d+f?", tok):
        return "float"
    if "=>" in tok or tok.startswith("()"):
        return "func"
    return "func"          # method group / delegate variable


def _iter_cs_addbranch():
    root = DEFAULT_GAME_ROOT / CS_MONSTER_DIR
    for path in sorted(root.glob("*.cs")):
        src = path.read_text(encoding="utf-8-sig", errors="replace")
        for m in re.finditer(r"\bAddBranch\s*\(", src):
            body = _call_text(src, m.end() - 1)
            args = _split_args(body)
            if not args or args[0].startswith('"'):
                continue                       # CreatureAnimator.AddBranch
            line = src[:m.start()].count("\n") + 1
            kinds = tuple(_arg_kind(a) for a in args[1:])
            yield path.name, line, args, kinds


# ── probes ───────────────────────────────────────────────────────────────
def cs_addbranch() -> None:
    print("RandomBranchState.AddBranch overloads (RandomBranchState.cs):")
    for kinds, (ln, role) in sorted(OVERLOADS.items(), key=lambda kv: int(kv[1][0])):
        print(f"  :{ln:<4} (state, {', '.join(kinds)})  ->  {role}")
    print("\nC# monster call sites:")
    counts: dict[str, int] = {}
    unknown = []
    files: dict[str, list] = {}
    for name, line, args, kinds in _iter_cs_addbranch():
        hit = OVERLOADS.get(kinds)
        key = f"{hit[0]} {hit[1]}" if hit else f"UNRESOLVED {kinds}"
        counts[key] = counts.get(key, 0) + 1
        if not hit:
            unknown.append((name, line, args))
        files.setdefault(name, []).append((line, kinds, args))
    total = sum(counts.values())
    for key, n in sorted(counts.items()):
        print(f"  {n:>3}  overload {key}")
    print(f"  {total} monster AddBranch call sites in {len(files)} files")
    if unknown:
        print("  UNRESOLVED:")
        for u in unknown:
            print(f"    {u}")
    print("\n  sites carrying a NON-DEFAULT cooldown or maxRepeats:")
    for name in sorted(files):
        for line, kinds, args in files[name]:
            hit = OVERLOADS.get(kinds)
            if hit and "int" in kinds:
                print(f"    {name}:{line}  {hit[1]:<28} AddBranch({', '.join(args)})")


def _sim_addbranch_calls():
    root = _REPO / SIM_MONSTER_DIR
    for path in sorted(root.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:                    # pragma: no cover
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_branch"):
                pos = [ast.unparse(a) for a in node.args]
                kw = {k.arg: ast.unparse(k.value) for k in node.keywords}
                yield path.relative_to(_REPO).as_posix(), node.lineno, pos, kw


def sim_addbranch() -> None:
    """sim add_branch signature is (state, weight, repeat_type, max_times, cooldown)
    — NOTE the positional order differs from C#'s (state, cooldown, repeatType,
    weight), so a positional port of a C# int argument lands on `weight`."""
    names = ["state", "weight", "repeat_type", "max_times", "cooldown"]
    rows = list(_sim_addbranch_calls())
    print(f"{len(rows)} sim add_branch call sites")
    nonzero = 0
    for path, line, pos, kw in rows:
        eff = {"weight": "1.0", "repeat_type": "CAN_REPEAT_FOREVER",
               "max_times": "0", "cooldown": "0"}
        for i, v in enumerate(pos[1:], start=1):
            eff[names[i]] = v
        eff.update({k: v for k, v in kw.items() if k in eff})
        if eff["max_times"] != "0" or eff["cooldown"] != "0":
            nonzero += 1
        print(f"  {path}:{line}  weight={eff['weight']} "
              f"repeat={eff['repeat_type']} max_times={eff['max_times']} "
              f"cooldown={eff['cooldown']}")
    print(f"  sites with a non-default max_times or cooldown: {nonzero}")


def _pascal(stem: str) -> str:
    return "".join(p.title() for p in stem.split("_"))


def addbranch_diff() -> None:
    """Join the two censuses by monster and report the C# branch parameters the
    sim port does not carry."""
    cs: dict[str, list] = {}
    for name, line, args, kinds in _iter_cs_addbranch():
        cs.setdefault(name[:-3], []).append((line, kinds, args))
    sim_src: dict[str, list] = {}
    for path, line, pos, kw in _sim_addbranch_calls():
        sim_src.setdefault(path, []).append((line, pos, kw))
    # C# monsters carrying a cooldown/maxRepeats, and whether any sim file
    # mentions the same class name at all.
    print("C# monsters with a non-default cooldown/maxRepeats branch:")
    for model in sorted(cs):
        interesting = [x for x in cs[model] if "int" in x[1]]
        if not interesting:
            continue
        hits = [p for p in (_REPO / SIM_MONSTER_DIR).rglob("*.py")
                if re.search(rf"\bclass {model}\b", p.read_text(encoding="utf-8"))]
        where = hits[0].relative_to(_REPO).as_posix() if hits else "UNPORTED"
        sim_calls = sim_src.get(where, [])
        print(f"\n  {model}.cs  -> sim {where}")
        for line, kinds, args in interesting:
            role = OVERLOADS.get(kinds, ("?", "?"))[1]
            print(f"     C#:{line}  {role:<28} AddBranch({', '.join(args)})")
        for line, pos, kw in sim_calls:
            print(f"     sim:{line}  add_branch({', '.join(pos + [f'{k}={v}' for k, v in kw.items()])})")
        if not sim_calls and where != "UNPORTED":
            print("     sim: NO add_branch calls (hand-rolled port)")


def branch_order() -> None:
    """Per C# RandomBranchState: the order branches were added, resolved from
    the local `moveStateN` variable to the MoveState's string id."""
    root = DEFAULT_GAME_ROOT / CS_MONSTER_DIR
    for path in sorted(root.glob("*.cs")):
        src = path.read_text(encoding="utf-8-sig", errors="replace")
        if not re.search(r"\bAddBranch\s*\(\s*[a-z]", src):
            continue
        ids = dict(re.findall(
            r"MoveState\s+(\w+)\s*=\s*new MoveState\(\"([^\"]+)\"", src))
        branch_vars = dict(re.findall(
            r"RandomBranchState\s+(\w+)\s*=[^;]*?new RandomBranchState\(\"([^\"]+)\"",
            src, re.S))
        order: dict[str, list[str]] = {}
        for m in re.finditer(r"(\w+)\.AddBranch\s*\(\s*([a-z]\w*)", src):
            owner, arg = m.group(1), m.group(2)
            if owner not in branch_vars:
                continue
            order.setdefault(branch_vars[owner], []).append(ids.get(arg, arg))
        if order:
            print(f"  {path.name}")
            for bid, seq in order.items():
                print(f"     {bid}: {' -> '.join(seq)}")


def hand_rolled() -> None:
    """Sim Monster subclasses whose C# model uses a RandomBranchState."""
    import sts2_rl.monsters  # noqa: F401
    from audit.tools.harness import _monster_units
    from sts2_rl.monsters.state_machine import MachineMonster

    cs_with_branch = {p.stem for p in
                      (DEFAULT_GAME_ROOT / CS_MONSTER_DIR).glob("*.cs")
                      if re.search(r"\bAddBranch\s*\(\s*[a-z]",
                                   p.read_text(encoding="utf-8-sig",
                                               errors="replace"))}
    units = _monster_units()
    machine, hand, no_cs = [], [], []
    for unit_id, cls in sorted(units.items()):
        name = cls.__name__
        if name not in cs_with_branch:
            no_cs.append(name)
            continue
        (machine if issubclass(cls, MachineMonster) else hand).append(name)
    print(f"{len(units)} sim Monster subclasses; "
          f"{len(cs_with_branch)} C# monster models use a RandomBranchState")
    print(f"  ported ON the state machine ({len(machine)}): {', '.join(machine)}")
    print(f"  ported HAND-ROLLED anyway ({len(hand)}): {', '.join(hand)}")
    print(f"  no C# RandomBranchState / name mismatch: {len(no_cs)}")


def move_rng() -> None:
    """Which sim monsters roll their next move off the MonsterAi stream."""
    root = _REPO / SIM_MONSTER_DIR
    ai, other = [], []
    for path in sorted(root.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(_REPO).as_posix()
        uses_ai = "combat_rng.monster_ai" in src
        # a roll that is not on monster_ai: weighted_branch_pick / .choice /
        # .random() / randint fed by self._rng inside a move-selection method
        rolls_shared = re.findall(
            r"^.*self\._rng\.(random|choice|randint|randrange|shuffle)\(.*$",
            src, re.M)
        if uses_ai:
            ai.append(rel)
        if rolls_shared:
            other.append((rel, [s.strip() for s in rolls_shared]))
    # every machine.roll_move(...) call site REPO-WIDE and the rng it passes:
    # the sim monsters package is not the only caller (powers.py splices one in).
    print("machine.roll_move(...) call sites repo-wide and the rng argument:")
    for path in sorted((_REPO / "sts2_rl").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:                       # pragma: no cover
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "roll_move" and len(node.args) >= 2):
                arg = ast.unparse(node.args[1])
                ok = "_move_rng" in arg or "monster_ai" in arg
                print(f"  {'   ' if ok else '-> '}"
                      f"{path.relative_to(_REPO).as_posix()}:{node.lineno}"
                      f"  rng={arg}{'' if ok else '   *** NOT the MonsterAi stream ***'}")
    print()
    print(f"files rolling on combat_rng.monster_ai ({len(ai)}):")
    for f in ai:
        print(f"  {f}")
    print(f"\nfiles drawing from the SHARED self._rng ({len(other)}):")
    for f, lines in other:
        print(f"  {f}")
        for ln in lines:
            print(f"      {ln}")


def _fractional_branch_weights(machine) -> list[str]:
    """Every RandomBranchState in `machine` whose CURRENT effective weights are
    not all whole numbers. Float rounding in GetNextState's sequential
    subtraction (step 15 / G7 clause c) can only bite on a non-dyadic weight,
    and the record names TwoTailedRat's 1f/12f as the concrete route — so the
    fuzz has to be able to say whether it reached such a vector at all."""
    out = []
    for state in machine.states.values():
        if type(state).__name__ != "RandomBranchState":
            continue
        try:
            ws = [state._effective_weight(b, machine) for b in state._branches]
        except Exception:
            continue
        if any(w != int(w) for w in ws):
            out.append(f"{state.id}={[round(w, 6) for w in ws]}")
    return out


# ── the two machine fall-through raises, which must NOT share a bucket ──────
# `sts2_rl/monsters/state_machine.py` raises at 11 sites (96, 120, 131, 196,
# 240, 273, 324, 381, 432, 491, 508). Exactly two of them are branch
# fall-throughs, and they belong to DIFFERENT mechanisms:
#
#   :273  RandomBranchState.get_next_state   "No valid state found in
#         RandomBranchState {id}!"  == RandomBranchState.cs:127 verbatim.
#         This is the one `zero_weight`/`nondyadic_weights` hunt.
#   :324  ConditionalBranchState.get_next_state  "No valid branch in
#         ConditionalBranchState {id}"  -- a different dispatcher (see
#         `cs_conditional`), a different asymmetry question.
#
# The probes' PRE-round-13 grep was the bare substring "No valid branch",
# which (a) does NOT match :273's current message at all -- round 12's T22
# reworded it to the C# text -- so every genuine RandomBranchState hit was
# reclassified as an "other error", and (b) DOES still match :324, so a
# ConditionalBranchState fall-through would have been counted and printed
# under a headline reading "(total weight 0)". It was a live false-positive
# source, not merely a dead grep. Both substrings below therefore name their
# state class, so neither can drift onto the other. Naming the class also
# keeps :432's lowercase `f"no valid state found: {next_id}"` -- a THIRD,
# unrelated raise one capitalisation away from the first -- out of the bucket
# by construction rather than by case-sensitivity luck. (Round 13 R11 item 4
# + fix pass.)
_RAND_FALLTHROUGH = "No valid state found in RandomBranchState"
_COND_FALLTHROUGH = "No valid branch in ConditionalBranchState"


def _classify_machine_raise(exc: BaseException) -> tuple[str, str]:
    """('rand' | 'cond' | 'other', text) for an exception out of a machine.

    Used by every classification point in `zero_weight` and
    `nondyadic_weights` -- including the ones that wrap Encounter/CombatState
    CONSTRUCTION, not just the walk. A machine that falls through on its very
    first roll does so during construction, so a construction-site `except`
    that files everything under "couldn't fuzz it" hides exactly the hit the
    probe exists to report. That hole used to swallow TwoTailedRat and
    Fabricator -- and TwoTailedRat is this probe's own named G7-clause-c
    trigger, i.e. pass 2 was blind on the case pass 2 was added for.
    """
    text = str(exc)
    if isinstance(exc, RuntimeError):
        if _RAND_FALLTHROUGH in text:
            return "rand", text
        if _COND_FALLTHROUGH in text:
            return "cond", text
    return "other", f"{type(exc).__name__}: {exc}"


def zero_weight(walks: int = 200, steps: int = 400) -> None:
    """Can a ported RandomBranchState reach total weight 0?

    C# GetNextState (RandomBranchState.cs:117-127) does rng.NextFloat(0) -> 0,
    then `num -= 0; if (num <= 0) return States[0]` — it BURNS a draw and picks
    the FIRST branch. STALE CITATION FIXED (round 13 R11 item 4): this used to
    say "the sim raises RuntimeError before drawing (state_machine.py:182-183)"
    -- both the path and the claim are wrong on the current tree. The real
    file is `sts2_rl/monsters/state_machine.py`, and round 12's T22 didn't
    just reword the raise message, it also fixed the REACHABILITY: the sim's
    `get_next_state` (state_machine.py:255-273) now draws FIRST via the same
    `_weighted_roll` primitive C# uses and only THEN loops branches, so an
    all-zero-weight vector resolves to branch 0 exactly like C# — it no
    longer raises at all. The remaining `RuntimeError` at state_machine.py:273
    ("No valid state found in RandomBranchState {id}!", matching
    RandomBranchState.cs:127 verbatim) is reachable only by a GENUINE
    sequential-subtraction float-rounding fall-through, which is SYMMETRIC
    with C#'s own throw at the same site — not the zero-weight ASYMMETRY this
    probe was built to detect. That mechanism is closed; what this probe can
    still show is whether the (now merely theoretical) fall-through is
    reachable at all, and whether the probe's own hit-detection still works
    when it is forced — see the standalone proof cited in R11-report.md item 4.

    The old `"No valid branch"` grep was NOT merely dead. It still matches
    ConditionalBranchState's raise (state_machine.py:324), a different
    dispatcher entirely, so the probe had a live FALSE-POSITIVE source as
    well as a miss: a ConditionalBranchState fall-through would have been
    counted and printed under a headline reading "(total weight 0)". The two
    are now classified separately and printed under separate headlines — see
    `_classify_machine_raise`.

    Executed reachability: drive every ported MachineMonster's machine through
    `walks` random walks of `steps` transitions each and count RuntimeErrors.

    TWO passes, because `cls.__new__(cls).build_machine()` cannot serve a
    monster whose graph reads constructor-set fields or live combat state:
      pass 1  the cheap detached build (this is the pass whose 59 machines /
              4,720,008 transitions the record has always cited);
      pass 2  a LIVE instance for everything pass 1 could not fuzz — a real
              one-monster Encounter in a real CombatState, then the same walk.
              Pass 2 exists because the first version of this probe skipped 24
              machines, among them TwoTailedRat (the named G7-clause-c trigger),
              ScrollOfBiting, LagavulinMatriarch, SlumberingBeetle, Queen,
              Fabricator, Exoskeleton and the Decimillipede segments, so the
              dormancy claim did not actually cover its own trigger.
    Pass 2's caveat, stated because it bounds the claim: the walk drives the
    MACHINE, not the combat, so a state-dependent weight lambda is evaluated
    against a turn-0 combat. The `fractional weight vectors reached` line below
    is how far that goes — it names every machine whose weights were observed
    off the whole numbers."""
    import random as _random

    import sts2_rl.monsters  # noqa: F401
    from audit.tools.harness import _monster_units
    from sts2_rl.monsters.state_machine import MachineMonster

    class _Owner:
        pass

    units = dict(_monster_units())
    from sts2_rl.monsters.fake_merchant import FakeMerchantMonster
    units["fake_merchant_monster"] = FakeMerchantMonster

    def _walk_machine(machine, owner, seed
                      ) -> tuple[int, str | None, str | None, str | None]:
        """(transitions, RandomBranch hit, ConditionalBranch hit, other error).

        The two branch fall-throughs are reported in separate slots -- see
        `_classify_machine_raise` for why sharing a bucket was wrong in both
        directions.
        """
        rng = _random.Random(seed)
        machine._performed_first_move = True
        n = 0
        try:
            for _ in range(steps):
                move = machine.roll_move(owner, rng)
                machine.on_move_performed(move)
                n += 1
        except Exception as exc:
            kind, text = _classify_machine_raise(exc)
            return (n,
                    text if kind == "rand" else None,
                    text if kind == "cond" else None,
                    text if kind == "other" else None)
        return n, None, None, None

    fuzzed, deferred, hits, transitions = [], [], [], 0
    cond_hits: list[tuple[str, str]] = []
    fractional: list[str] = []
    for unit_id, cls in sorted(units.items()):
        if not issubclass(cls, MachineMonster):
            continue
        try:
            probe = cls.__new__(cls).build_machine()
        except Exception as exc:
            deferred.append((cls.__name__, f"build_machine: {type(exc).__name__}"))
            continue
        del probe
        ok, err = 0, None
        for w in range(walks):
            machine = cls.__new__(cls).build_machine()
            owner = _Owner()
            owner.machine = machine
            n, hit, cond, err = _walk_machine(machine, owner, w)
            ok += n
            if w == 0:
                fractional += [f"{cls.__name__}.{f}"
                               for f in _fractional_branch_weights(machine)]
            if cond:
                cond_hits.append((cls.__name__, cond))
                break
            if hit:
                hits.append((cls.__name__, hit))
                break
            if err:
                break
        transitions += ok
        (deferred if err else fuzzed).append(
            (cls.__name__, err or f"{ok} transitions"))
    print(f"pass 1 (detached build) machines fuzzed: {len(fuzzed)}  "
          f"transitions: {transitions}")
    print(f"pass 1 could not fuzz: {len(deferred)}")
    for s in deferred:
        print(f"  {s[0]}: {s[1]}")

    # ── pass 2: a live instance for everything pass 1 deferred ──────────────
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter

    live_ok, live_bad, live_transitions = [], [], 0
    by_name = {c.__name__: c for c in units.values()}
    for name, _reason in deferred:
        cls = by_name.get(name)
        if cls is None:                             # pragma: no cover
            live_bad.append((name, "class not in the roster"))
            continue
        # Building the Encounter/CombatState ALSO drives the machine (the
        # monster rolls its opening move), so a fall-through can be raised
        # right here. Classify it exactly as the walk does instead of filing
        # every construction failure under "couldn't fuzz it" -- see
        # `_classify_machine_raise` (round 13 R11 fix pass; this hole hid
        # TwoTailedRat, the probe's own named G7-clause-c trigger).
        try:
            enc = Encounter(id="probe_zero_weight", monster_classes=[cls])
            base = CombatState(rng=_random.Random(0), encounter=enc)
            mon = base.enemies[0]
        except Exception as exc:
            kind, text = _classify_machine_raise(exc)
            if kind == "rand":
                hits.append((name, text))
            elif kind == "cond":
                cond_hits.append((name, text))
            else:
                live_bad.append((name, f"CombatState: {text}"))
            continue
        fractional += [f"{name}.{f}"
                       for f in _fractional_branch_weights(mon.machine)]
        ok, err, hit_here = 0, None, None
        for w in range(walks):
            # Same classification for the per-walk rebuild: unguarded, a
            # construction fall-through on any seed > 0 crashed the probe.
            try:
                enc = Encounter(id="probe_zero_weight", monster_classes=[cls])
                cs = CombatState(rng=_random.Random(w), encounter=enc)
                m = cs.enemies[0]
            except Exception as exc:
                kind, text = _classify_machine_raise(exc)
                if kind == "rand":
                    hit_here = text
                    hits.append((name, text))
                elif kind == "cond":
                    hit_here = text
                    cond_hits.append((name, text))
                else:
                    err = f"CombatState: {text}"
                break
            n, hit, cond, err = _walk_machine(m.machine, m, w)
            ok += n
            if cond:
                hit_here = cond
                cond_hits.append((name, cond))
                break
            if hit:
                hit_here = hit
                hits.append((name, hit))
                break
            if err:
                break
        live_transitions += ok
        if err and not hit_here:
            live_bad.append((name, err))
        else:
            live_ok.append((name, f"{ok} transitions"))
    print(f"\npass 2 (live instance) machines fuzzed: {len(live_ok)}  "
          f"transitions: {live_transitions}")
    for s in live_ok:
        print(f"  {s[0]}: {s[1]}")
    print(f"\nmachines STILL not fuzzed (dormancy unproven for these): "
          f"{len(live_bad)}")
    for s in live_bad:
        print(f"  {s[0]}: {s[1]}")

    print(f"\nTOTAL machines fuzzed: {len(fuzzed) + len(live_ok)}  "
          f"transitions: {transitions + live_transitions}")
    print(f"RandomBranchState fall-through "
          f"('{_RAND_FALLTHROUGH} ...') hits: {len(hits)}")
    for h in hits:
        print(f"  {h[0]}: {h[1]}")
    # A DIFFERENT mechanism, printed under its own headline so it can never be
    # read as a zero-weight hit (the old shared "No valid branch" grep could).
    print(f"ConditionalBranchState fall-through "
          f"('{_COND_FALLTHROUGH} ...') hits: {len(cond_hits)}  "
          f"[different mechanism -- not a zero-weight hit]")
    for h in cond_hits:
        print(f"  {h[0]}: {h[1]}")
    print(f"fractional (non-whole) branch weight vectors reached: "
          f"{len(fractional)}")
    for f in sorted(set(fractional)):
        print(f"  {f}")


_WEIGHT_FIELD_DENY = {
    "hp", "max_hp", "block", "net_id", "slot", "side", "min_hp",
}


def nondyadic_weights(walks: int = 200, steps: int = 400) -> None:
    """Step 15 / G7 clause c names TwoTailedRat's `1f/12f` as the ONLY ported
    non-dyadic branch weight and therefore as the concrete fall-through route.
    `zero-weight` fuzzes TwoTailedRat but cannot reach that arm: the weight is a
    LAMBDA gated on `_can_summon()` (two_tailed_rat.py:75-79, 101-113), which
    reads `turns_until_summonable`, and the fuzz drives the MACHINE only — it
    never runs a move's perform delegate, which is what decrements the counter
    (two_tailed_rat.py:115-117 etc.). So the gate is never open.

    This probe closes that hole mechanically: for every ported machine holding a
    callable branch weight, it searches the monster's own integer fields for a
    setting that opens the gate (each candidate set to 0, then restored), prints
    the resulting weight vector, and fuzzes the machine with the gate open,
    counting RandomBranchState fall-throughs (message text corrected, round 13
    R11 item 4 -- see `zero_weight`'s docstring and `_classify_machine_raise`
    for why the old "No valid branch" grep both missed the raise it was aiming
    at and still matched a DIFFERENT one).

    Scope caveat, stated because it bounds the claim: this probe's population
    is a SINGLE machine (TwoTailedRat). Its corrected classification is
    therefore exercised only as far as that one machine goes; the executed
    "the corrected grep really does fire" evidence in R11-report.md covers
    `zero_weight`, not this probe."""
    import random as _random

    import sts2_rl.monsters  # noqa: F401
    from audit.tools.harness import _monster_units
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.state_machine import MachineMonster

    units = dict(_monster_units())
    from sts2_rl.monsters.fake_merchant import FakeMerchantMonster
    units["fake_merchant_monster"] = FakeMerchantMonster

    def _live(cls, seed=0):
        enc = Encounter(id="probe_nondyadic", monster_classes=[cls])
        return CombatState(rng=_random.Random(seed), encounter=enc).enemies[0]

    callable_weight, opened, hits, transitions = [], [], [], 0
    cond_hits: list[tuple[str, str]] = []
    for _uid, cls in sorted(units.items()):
        if not issubclass(cls, MachineMonster):
            continue
        try:
            mon = _live(cls)
        except Exception:
            continue
        branches = [s for s in mon.machine.states.values()
                    if type(s).__name__ == "RandomBranchState"
                    and any(callable(b["weight"]) for b in s._branches)]
        if not branches:
            continue
        callable_weight.append(cls.__name__)
        as_built = _fractional_branch_weights(mon.machine)
        print(f"  {cls.__name__}: {len(branches)} RandomBranchState(s) with a "
              f"callable weight")
        print(f"     as constructed, fractional vectors: {as_built or 'NONE'}")
        # search the monster's own int fields for one that opens the gate
        found = None
        for field_name, val in sorted(vars(mon).items()):
            if (field_name in _WEIGHT_FIELD_DENY or not isinstance(val, int)
                    or isinstance(val, bool) or val == 0):
                continue
            try:
                setattr(mon, field_name, 0)
                frac = _fractional_branch_weights(mon.machine)
            except Exception:
                setattr(mon, field_name, val)
                continue
            if frac:
                found = (field_name, val, frac)
                print(f"     {field_name}={val} -> 0 OPENS the gate: {frac}")
                break
            setattr(mon, field_name, val)
        if found is None:
            print("     no single int field opens a fractional vector")
            continue
        opened.append(f"{cls.__name__}.{found[0]}")
        ok, err = 0, None
        for w in range(walks):
            # `_live` builds an Encounter + CombatState, which drives the
            # machine's opening roll -- a fall-through can land here, so it
            # gets the same classification as the walk (round 13 R11 fix
            # pass; unguarded, this both crashed the probe and, when it did
            # not, hid the hit). See `_classify_machine_raise`.
            try:
                m = _live(cls, w)
            except Exception as exc:
                kind, text = _classify_machine_raise(exc)
                if kind == "rand":
                    hits.append((cls.__name__, text))
                elif kind == "cond":
                    cond_hits.append((cls.__name__, text))
                else:
                    err = f"CombatState: {text}"
                break
            setattr(m, found[0], 0)
            m.machine._performed_first_move = True
            rng = _random.Random(w)
            try:
                for _ in range(steps):
                    setattr(m, found[0], 0)      # keep the gate open
                    mv = m.machine.roll_move(m, rng)
                    m.machine.on_move_performed(mv)
                    ok += 1
            except Exception as exc:
                kind, text = _classify_machine_raise(exc)
                if kind == "rand":
                    hits.append((cls.__name__, text))
                elif kind == "cond":
                    cond_hits.append((cls.__name__, text))
                else:
                    err = text
                break
        transitions += ok
        print(f"     fuzzed with the gate OPEN: {ok} transitions"
              f"{'  ERROR ' + err if err else ''}")
    print(f"\nported machines with a CALLABLE branch weight: "
          f"{len(callable_weight)}  ({', '.join(callable_weight) or 'none'})")
    print(f"of those, gate opened to a fractional weight vector: {len(opened)}"
          f"  ({', '.join(opened) or 'none'})")
    print(f"transitions fuzzed with a fractional vector live: {transitions}")
    print(f"RandomBranchState fall-throughs: {len(hits)}")
    for h in hits:
        print(f"  {h[0]}: {h[1]}")
    print(f"ConditionalBranchState fall-throughs: {len(cond_hits)}  "
          f"[different mechanism -- not a G7c hit]")
    for h in cond_hits:
        print(f"  {h[0]}: {h[1]}")


# ── ConditionalBranchState census ────────────────────────────────────────
def cs_conditional() -> None:
    """The SECOND branch dispatcher. cs-addbranch is blind to it, so the
    61-site AddBranch census is NOT the whole seam surface."""
    root = DEFAULT_GAME_ROOT / CS_MONSTER_DIR
    total, files = 0, {}
    for path in sorted(root.rglob("*.cs")):
        src = path.read_text(encoding="utf-8-sig", errors="replace")
        hits = []
        for m in re.finditer(r"\.AddState\s*\(", src):
            body = _call_text(src, m.end() - 1)
            args = _split_args(body)
            line = src[:m.start()].count("\n") + 1
            hits.append((line, len(args)))
        if hits:
            files[path.name] = hits
            total += len(hits)
    print(f"{total} ConditionalBranchState.AddState call sites in {len(files)} files")
    one_arg = sum(1 for h in files.values() for _, n in h if n == 1)
    print(f"  sites with NO condition lambda (unconditional fallback): {one_arg}")
    for name in sorted(files):
        print(f"  {name}: {', '.join(str(ln) for ln, _ in files[name])}")


# ── C#-vs-sim branch-parameter diff (the seam's central check) ───────────
# Resolved by hand from the overload table above and re-checked by `mismatch`
# against the C# text: (branch add-order) -> (weight, repeatType, maxTimes,
# cooldown) as the GAME builds it.  "R" = MoveRepeatType.
_CS_BRANCHES: dict[str, tuple[str, list[tuple[str, str, float, str, int, int]]]] = {
    # sim module                              C# file:first AddBranch line
    "sts2_rl/monsters/hive/flail_knight.py": ("FlailKnight.cs:49-51", [
        ("WAR_CHANT", "moveState",  1.0, "CANNOT_REPEAT",    0, 0),
        ("FLAIL",     "moveState2", 1.0, "CAN_REPEAT_X_TIMES", 2, 0),
        ("RAM",       "moveState3", 1.0, "CAN_REPEAT_X_TIMES", 2, 0)]),
    "sts2_rl/monsters/hive/hunter_killer.py": ("HunterKiller.cs:42-43", [
        ("BITE",     "moveState2", 1.0, "CANNOT_REPEAT",      0, 0),
        ("PUNCTURE", "moveState3", 1.0, "CAN_REPEAT_X_TIMES", 2, 0)]),
    "sts2_rl/monsters/glory/scroll_of_biting.py": ("ScrollOfBiting.cs:89-90", [
        ("CHOMP", "moveState",  1.0, "CANNOT_REPEAT",      0, 0),
        ("CHEW",  "moveState2", 1.0, "CAN_REPEAT_X_TIMES", 2, 0)]),
    "sts2_rl/monsters/glory/knights.py": ("SpectralKnight.cs:52-53", [
        ("SOUL_SLASH", "moveState2", 1.0, "CAN_REPEAT_X_TIMES", 2, 0),
        ("SOUL_FLAME", "moveState3", 1.0, "CANNOT_REPEAT",      0, 0)]),
    "sts2_rl/monsters/fake_merchant.py": ("FakeMerchantMonster.cs:55-58", [
        ("SWIPE",  "moveState",  1.0, "CANNOT_REPEAT", 0, 0),
        ("SPEW",   "moveState2", 1.0, "CANNOT_REPEAT", 0, 0),
        ("THROW",  "moveState3", 1.0, "CANNOT_REPEAT", 0, 0),
        ("ENRAGE", "moveState4", 1.0, "CANNOT_REPEAT", 0, 3),
        # second RandomBranchState, RAND_ATTACK_MOVE (FakeMerchantMonster.cs:66-68)
        ("SWIPE(atk)",  "moveState",  1.0, "CANNOT_REPEAT", 0, 0),
        ("SPEW(atk)",   "moveState2", 1.0, "CANNOT_REPEAT", 0, 0),
        ("THROW(atk)",  "moveState3", 1.0, "CANNOT_REPEAT", 0, 0)]),
    "sts2_rl/monsters/underdocks/fossil_stalker.py": ("FossilStalker.cs:58-60", [
        ("LATCH",  "moveState2", 1.0, "CAN_REPEAT_X_TIMES", 2, 0),
        ("TACKLE", "moveState",  1.0, "CAN_REPEAT_X_TIMES", 2, 0),
        ("LASH",   "moveState3", 1.0, "CAN_REPEAT_X_TIMES", 2, 0)]),
    "sts2_rl/monsters/underdocks/two_tailed_rat.py": ("TwoTailedRat.cs:124-127", [
        ("SCRATCH", "moveState",  -1, "CANNOT_REPEAT", 0, 0),
        ("BITE",    "moveState2", -1, "CANNOT_REPEAT", 0, 0),
        ("SCREECH", "moveState3", -1, "CANNOT_REPEAT", 0, 3),
        ("BACKUP",  "moveState4", -1, "USE_ONLY_ONCE", 0, 0)]),
    "sts2_rl/monsters/overgrowth/mawler.py": ("Mawler.cs:47-49", [
        ("RIP",  "moveState",  1.0, "CANNOT_REPEAT", 0, 0),
        ("ROAR", "moveState2", 1.0, "USE_ONLY_ONCE", 0, 0),
        ("CLAW", "moveState3", 1.0, "CANNOT_REPEAT", 0, 0)]),
    "sts2_rl/monsters/overgrowth/fogmog.py": ("Fogmog.cs:47-48", [
        ("SWIPE_RANDOM", "moveState3", 0.4, "CANNOT_REPEAT", 0, 0),
        ("HEADBUTT",     "moveState4", 0.6, "CANNOT_REPEAT", 0, 0)]),
    "sts2_rl/monsters/hive/exoskeleton.py": ("Exoskeleton.cs:44-45", [
        ("SKITTER",   "moveState",  1.0, "CANNOT_REPEAT", 0, 0),
        ("MANDIBLES", "moveState2", 1.0, "CANNOT_REPEAT", 0, 0)]),
    "sts2_rl/monsters/glory/fabricator.py": ("Fabricator.cs:52-53", [
        ("FABRICATE",         "moveState",  1.0, "CAN_REPEAT_FOREVER", 0, 0),
        ("FABRICATING_STRIKE", "moveState2", 1.0, "CAN_REPEAT_FOREVER", 0, 0)]),
    "sts2_rl/monsters/hive/decimillipede.py": ("DecimillipedeSegment.cs:151-153", [
        ("WRITHE",    "moveState",  1.0, "CANNOT_REPEAT", 0, 0),
        ("BULK",      "moveState2", 1.0, "CANNOT_REPEAT", 0, 0),
        ("CONSTRICT", "moveState3", 1.0, "CANNOT_REPEAT", 0, 0)]),
}


def _sim_branch_rows(path: str):
    """(line, weight, repeat, max_times, cooldown) per add_branch in add order."""
    names = ["state", "weight", "repeat_type", "max_times", "cooldown"]
    rows = []
    for p, line, pos, kw in _sim_addbranch_calls():
        if p != path:
            continue
        eff = {"weight": "1.0", "repeat_type": "CAN_REPEAT_FOREVER",
               "max_times": "0", "cooldown": "0"}
        for i, v in enumerate(pos[1:], start=1):
            eff[names[i]] = v
        eff.update({k: v for k, v in kw.items() if k in eff})
        rows.append((line, pos[0] if pos else "?", eff))
    return rows


def _norm_repeat(tok: str) -> str:
    return tok.rsplit(".", 1)[-1]


# How many C# RandomBranchStates each _CS_BRANCHES row folds together. Every
# row is one sim MODULE; FakeMerchantMonster.cs builds TWO RandomBranchStates
# (RAND_MOVE :55-58 and RAND_ATTACK_MOVE :66-68) and the row lists both their
# branch sets, so the module count and the branch-state count differ by one.
_ROW_BRANCH_STATES = {"sts2_rl/monsters/fake_merchant.py": 2}


def mismatch() -> None:
    print("C# branch parameters vs the sim port's, per branch, in add order.")
    print("A '2' or '3' appearing as the sim's WEIGHT where C# has it as")
    print("maxTimes/cooldown is the TwigSlimeM/Flyconid bug class.\n")
    bad: list[str] = []
    for path, (cite, cs_rows) in _CS_BRANCHES.items():
        sim_rows = _sim_branch_rows(path)
        hdr = f"  {path}   <-  {cite}"
        lines, monster_bad = [], False
        if len(sim_rows) != len(cs_rows):
            lines.append(f"     !! branch COUNT {len(sim_rows)} sim vs "
                         f"{len(cs_rows)} C# (a loop in the port is fine "
                         f"if the params match)")
        for i, (label, var, w, rep, mx, cd) in enumerate(cs_rows):
            if i < len(sim_rows):
                ln, state, eff = sim_rows[i]
            elif len(sim_rows) == 1:      # single add_branch inside a for-loop
                ln, state, eff = sim_rows[0]
            else:
                lines.append(f"     {label:<18} C#(w={w} {rep} max={mx} cd={cd})"
                             f"  sim: MISSING")
                monster_bad = True
                continue
            s_w = eff["weight"]
            s_rep = _norm_repeat(eff["repeat_type"])
            s_mx, s_cd = eff["max_times"], eff["cooldown"]
            # w == -1 means "a lambda; compare the repeat/max/cooldown only"
            w_ok = (w == -1) or (_num(s_w) == w)
            ok = w_ok and s_rep == rep and _num(s_mx) == mx and _num(s_cd) == cd
            flag = "   " if ok else " ->"
            lines.append(f"    {flag} {label:<18} C#(w={w if w != -1 else 'lambda'} "
                         f"{rep} max={mx} cd={cd})   "
                         f"sim:{ln}(w={s_w} {s_rep} max={s_mx} cd={s_cd})")
            monster_bad |= not ok
        print(hdr + ("     *** MISMATCH ***" if monster_bad else ""))
        print("\n".join(lines))
        if monster_bad:
            bad.append(path)
    # Explicit totals. The record's headline arithmetic comes from HERE and
    # nowhere else -- an earlier pass stated "13 resolved / 8 match" by reading
    # the branch-state count (13) as the pair count (12).
    pairs = len(_CS_BRANCHES)
    branch_states = sum(_ROW_BRANCH_STATES.get(p, 1) for p in _CS_BRANCHES)
    print(f"\n  resolved C#<->sim pairs (one per sim MODULE): {pairs}")
    print(f"  C# RandomBranchStates those pairs cover: {branch_states} "
          f"(fake_merchant.py folds 2)")
    print(f"  pairs that MATCH the C# branch arguments exactly: {pairs - len(bad)}")
    print(f"  monsters whose sim port MISREADS the C# branch arguments: "
          f"{len(bad)}")
    for b in bad:
        print(f"    {b}")


def _num(tok: str) -> float | None:
    try:
        return float(tok)
    except (TypeError, ValueError):
        return None


# ── executed observable of the mismatch ──────────────────────────────────
_DIST_CASES = {
    # sim class -> [(branch add-order index, corrected kwargs), ...]
    "FlailKnight": ("sts2_rl.monsters.hive.flail_knight", "FlailKnight", {
        1: dict(weight=1.0, repeat="CAN_REPEAT_X_TIMES", max_times=2),
        2: dict(weight=1.0, repeat="CAN_REPEAT_X_TIMES", max_times=2)}),
    "HunterKiller": ("sts2_rl.monsters.hive.hunter_killer", "HunterKiller", {
        1: dict(weight=1.0, repeat="CAN_REPEAT_X_TIMES", max_times=2)}),
    "ScrollOfBiting": ("sts2_rl.monsters.glory.scroll_of_biting",
                       "ScrollOfBiting", {
        1: dict(weight=1.0, repeat="CAN_REPEAT_X_TIMES", max_times=2)}),
    "SpectralKnight": ("sts2_rl.monsters.glory.knights", "SpectralKnight", {
        0: dict(weight=1.0, repeat="CAN_REPEAT_X_TIMES", max_times=2)}),
    "FakeMerchantMonster": ("sts2_rl.monsters.fake_merchant",
                            "FakeMerchantMonster", {
        3: dict(weight=1.0, repeat="CANNOT_REPEAT", cooldown=3)}),
}


def _walk(machine, owner, rng, steps: int) -> dict[str, int]:
    from collections import Counter
    counts: Counter = Counter()
    machine._performed_first_move = True
    for _ in range(steps):
        move = machine.roll_move(owner, rng)
        machine.on_move_performed(move)
        counts[move.id] += 1
    return dict(counts)


def distribution(steps: int = 100000) -> None:
    """Roll each mismatched machine as the sim builds it, and again with the
    C# branch parameters restored, from the same seed."""
    import importlib
    import random as _random

    from sts2_rl.monsters.state_machine import MoveRepeatType

    class _Owner:
        pass

    def _blank(cls):
        # build_machine() reads a couple of ctor-set fields on some monsters;
        # supply the defaults their __init__ would (starter index 0 etc.).
        obj = cls.__new__(cls)
        for attr, val in (("_starter_move_idx", 0), ("_middle_inklet", False),
                          ("_starter_move_index", 0)):
            setattr(obj, attr, val)
        return obj

    for label, (mod, cls_name, fixes) in _DIST_CASES.items():
        cls = getattr(importlib.import_module(mod), cls_name)
        as_is = _blank(cls).build_machine()
        fixed = _blank(cls).build_machine()
        # apply the C# parameters to the ONE RandomBranchState the fix targets
        branch = next(s for s in fixed.states.values()
                      if type(s).__name__ == "RandomBranchState"
                      and len(getattr(s, "_branches", [])) > max(fixes))
        for idx, kw in fixes.items():
            b = branch._branches[idx]
            b["weight"] = kw.get("weight", b["weight"])
            b["repeat_type"] = MoveRepeatType[kw["repeat"]]
            b["max_times"] = kw.get("max_times", 0)
            b["cooldown"] = kw.get("cooldown", 0)
        o1, o2 = _Owner(), _Owner()
        o1.machine, o2.machine = as_is, fixed
        a = _walk(as_is, o1, _random.Random(7), steps)
        b = _walk(fixed, o2, _random.Random(7), steps)
        print(f"\n  {label}  ({steps} rolls, seed 7)")
        for k in sorted(set(a) | set(b)):
            pa, pb = a.get(k, 0) / steps, b.get(k, 0) / steps
            mark = "  <== DIFFERS" if abs(pa - pb) > 0.005 else ""
            print(f"     {k:<22} sim {pa:6.1%}   game {pb:6.1%}{mark}")


# ── stun × move machine ──────────────────────────────────────────────────
def stun_machine() -> None:
    """Executed: what CreatureCmd.stun does to a MachineMonster's machine.

    C#: Creature.StunInternal (Creature.cs:524-544) builds a synthetic
    MoveState("STUNNED", ..., FollowUpStateId = StateLog.Last().Id,
    MustPerformOnceBeforeTransitioning = true) and force-sets it. The next
    RollMove transitions STUNNED -> that id with NO draw and appends the id to
    StateLog a SECOND time.
    Sim: cmds.py:208-218 sets a bool and, for hand-rolled monsters only,
    overwrites _move_key. The machine is never touched."""
    import random as _random

    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker
    from sts2_rl.monsters import Encounter

    enc = Encounter(id="probe_stun", monster_classes=[FossilStalker])
    cs = CombatState(rng=_random.Random(3), encounter=enc)
    mon = cs.enemies[0]
    machine = mon.machine
    before_move = mon._current_move.id
    before_log = [s.id for s in machine.state_log]
    CreatureCmd.stun(cs.hooks, mon, next_move_key="LASH_MOVE")
    print(f"  sim FossilStalker: stunned={mon.stunned} "
          f"has _move_key={hasattr(mon, '_move_key')}")
    print(f"    current_move  {before_move} -> {mon._current_move.id}")
    print(f"    machine.current {machine.current.id!r}  "
          f"(a 'STUNNED' state was NOT created)")
    print(f"    state_log     {before_log} -> {[s.id for s in machine.state_log]}")
    print(f"    intent shown  {mon.current_intent.move_type}")
    print("    next_move_key='LASH_MOVE' was SILENTLY DROPPED "
          f"(hasattr _move_key = {hasattr(mon, '_move_key')})")
    print("  C# equivalent: machine.current = MoveState('STUNNED'), "
          "state_log unchanged now, then +1 duplicate of the deferred move "
          "at the next RollMove (Creature.cs:534-541 + "
          "MonsterMoveStateMachine.cs:76-79).")
    print("  NOTE FossilStalker is the G5 vehicle only: it is an UNDERDOCKS "
          "monster and no ported caller can stun it (probe stun-sites: every "
          "stun but Whistle's is a self-stun, and Whistle is Glory-only -- "
          "probe whistle-route). The stun-REACHABLE case is below.")

    # ── the reachable case: a Glory monster a player can actually stun ──
    from sts2_rl.monsters.glory.scroll_of_biting import ScrollOfBiting
    from sts2_rl.monsters.state_machine import MoveRepeatType

    enc = Encounter(id="probe_stun_route", monster_classes=[ScrollOfBiting])
    cs = CombatState(rng=_random.Random(3), encounter=enc)
    scroll = cs.enemies[0]
    m = scroll.machine
    # park it where a Whistle stun bites: telegraphing CHEW, whose follow-up is
    # the RandomBranchState. Reachable prefix CHOMP -> MORE_TEETH -> CHEW.
    prefix = ["CHOMP", "MORE_TEETH", "CHEW"]
    m.state_log[:] = [m.states[i] for i in prefix]
    m.force_current_state(m.states["CHEW"])
    m._performed_first_move = True
    scroll._current_move = m.states["CHEW"]
    before_log = [s.id for s in m.state_log]
    CreatureCmd.stun(cs.hooks, scroll)
    print("\n  sim ScrollOfBiting (Glory, the Whistle-reachable case):")
    print(f"    stunned={scroll.stunned}  machine.current="
          f"{m.current.id!r}  (no 'STUNNED' state was created)")
    print(f"    state_log {before_log} -> {[s.id for s in m.state_log]}")
    print(f"    C# would reach {before_log + ['CHEW']} after the post-stun roll")

    branch = next(s for s in m.states.values()
                  if type(s).__name__ == "RandomBranchState")

    def _pick_dist(log_ids, corrected, trials=100000, seed=7):
        from collections import Counter
        saved = [dict(b) for b in branch._branches]
        if corrected:                       # restore the C# parameters (G1)
            for b in branch._branches:
                if b["state_id"] == "CHEW":
                    b["weight"] = 1.0
                    b["repeat_type"] = MoveRepeatType.CAN_REPEAT_X_TIMES
                    b["max_times"] = 2
        counts: Counter = Counter()
        rng = _random.Random(seed)
        for _ in range(trials):
            m.state_log[:] = [m.states[i] for i in log_ids]
            m.force_current_state(m.states["CHEW"])
            counts[m.roll_move(scroll, rng).id] += 1
        branch._branches[:] = saved
        return {k: v / trials for k, v in counts.items()}

    dup = prefix + ["CHEW"]
    cells = (
        ("sim as shipped        (G4 gap + G1 gap)", prefix, False),
        ("duplicate restored    (G1 gap only)    ", dup, False),
        ("C# params restored    (G4 gap only)    ", prefix, True),
        ("the GAME              (both fixed)     ", dup, True),
    )
    print("\n    the move the branch picks on the turn AFTER the deferred CHEW"
          " (100000 rolls, seed 7):")
    for label, log_ids, corrected in cells:
        d = _pick_dist(log_ids, corrected)
        print(f"      {label}  "
              + "  ".join(f"{k} {v:5.1%}" for k, v in sorted(d.items())))
    print("    -> the game's post-stun branch is FORCED to CHOMP because the "
          "duplicated CHEW fills CanRepeatXTimes(2)'s window; the sim offers "
          "CHEW. Both gaps must be fixed to close it, which is why G1 and G4 "
          "are recorded separately (rule 3).")



# ── rule-7 sweep: every cited file must be a hashed source ───────────────
_SWEEP_EXCLUDE = ("test/", "audit/tools/")


def sources_sweep() -> None:
    """Extract every .cs / .py token from the record AND the spec doc, resolve
    it against the real trees, and report any that SEAM_SOURCES does not hash.

    This is governing rule 7 mechanised — it has been a review finding on
    three consecutive seam tasks, so it is executable rather than a promise.

    RESOLUTION IS PATH-AWARE, and the difference matters. A token that carries
    a directory (`sts2_rl/monsters/hive/flail_knight.py`) must match a hashed
    path by suffix. A BARE BASENAME (`Creature.cs`, `base.py` — the normal form
    for a C# citation) is resolved against the real trees first:
      * exactly one real file with that basename -> it must be the hashed one;
      * several real files -> AMBIGUOUS. An earlier version of this probe
        resolved every token by basename alone, so a citation of
        `sts2_rl/cards/base.py` would have been satisfied by the hashed
        `sts2_rl/monsters/base.py`. Ambiguous tokens are now listed with all
        their candidates so the reader can see which file was meant.
    Residual limitation, stated rather than hidden: for an ambiguous bare
    basename the probe cannot know WHICH candidate the prose meant, so it
    accepts the token if any candidate is hashed and flags it for a human."""
    from audit.tools.harness import SEAM_SOURCES

    game_paths, sim_paths = SEAM_SOURCES["monster_state_machine"]
    hashed_full = set(game_paths) | set(sim_paths)

    texts = []
    for rel in ("audit/records/seam/monster_state_machine.json",
                "audit/seams/monster_state_machine.md"):
        f = _REPO / rel
        if f.exists():
            texts.append((rel, f.read_text(encoding="utf-8")))
    if not texts:
        print("  nothing to sweep yet")
        return

    # Rule 7's wording is "cites a file WITH LINE NUMBERS", so track whether any
    # citation of a token is line-numbered. A bare mention (a name in a
    # hole-list table, say) is not evidence and does not pull the file into the
    # unit; it is reported separately instead of counted as a miss.
    cited: dict[str, set[str]] = {}
    lineno_cited: set[str] = set()
    for rel, text in texts:
        for m in re.finditer(r"([\w./\-]+\.(?:cs|py))(:\d+)?", text):
            tok = m.group(1).replace("\\", "/").lstrip("./")
            cited.setdefault(tok, set()).add(rel)
            if m.group(2):
                lineno_cited.add(tok)

    def _real(base: str) -> list[str]:
        return ([p.relative_to(DEFAULT_GAME_ROOT).as_posix()
                 for p in (DEFAULT_GAME_ROOT / "src").rglob(base)]
                + [p.relative_to(_REPO).as_posix()
                   for p in (_REPO / "sts2_rl").rglob(base)])

    missing, ambiguous, excluded, name_only = [], [], [], []
    resolved = 0
    for tok in sorted(cited):
        base = tok.rsplit("/", 1)[-1]
        if any(tok.startswith(x) or f"/{x}" in tok for x in _SWEEP_EXCLUDE):
            excluded.append(tok)
            continue
        if "/" in tok:
            # a token carrying a directory must match a hashed PATH by suffix
            hit = any(h == tok or h.endswith("/" + tok) for h in hashed_full)
            hashed_candidates = []
        else:
            # a bare basename: resolve it against the real trees first
            hashed_candidates = [h for h in hashed_full
                                 if h.rsplit("/", 1)[-1] == base]
            hit = bool(hashed_candidates)
        if hit:
            resolved += 1
            real = _real(base)
            if hashed_candidates and len(real) > 1:
                ambiguous.append((tok, sorted(real), hashed_candidates))
        elif tok not in lineno_cited:
            name_only.append((tok, sorted(cited[tok])))
        else:
            missing.append((tok, sorted(cited[tok]), _real(base)[:3]))
    print(f"  {len(cited)} distinct .cs/.py tokens cited; {resolved} hashed; "
          f"{len(missing)} NOT hashed; {len(excluded)} excluded "
          f"{_SWEEP_EXCLUDE}; {len(name_only)} cited by NAME ONLY (no line "
          f"number, so rule 7 does not pull them into the unit)")
    for tok in excluded:
        print(f"    excluded: {tok}")
    for tok, where, real in missing:
        tag = "REAL FILE, UNHASHED" if real else "no such file (prose token?)"
        print(f"    {tok:<44} {tag}  cited in {', '.join(w.split('/')[-1] for w in where)}")
        for h in real:
            print(f"        -> {h}")
    if name_only:
        print("\n  NAME-ONLY citations (no `:line` anywhere; a bare mention is "
              "not evidence):")
        for tok, where in name_only:
            print(f"    {tok:<44} cited in "
                  f"{', '.join(w.split('/')[-1] for w in where)}")
    print(f"\n  AMBIGUOUS bare basenames (several real files share the name, so "
          f"basename resolution alone could false-positive): {len(ambiguous)}")
    for tok, real, hashed_candidates in ambiguous:
        print(f"    {tok:<24} real: {real}")
        print(f"    {'':<24} hashed: {hashed_candidates}")


# ── stun caller inventory (rule 5: no unexecuted unreachability claims) ──
def stun_sites() -> None:
    """EXECUTED inventory of every sim stun. Step 38's `faithful` rests on "no
    ported caller can stun a player" (C# StunInternal throws for a player,
    Creature.cs:524-531) and G4/G5's liveness rests on WHICH callers exist, so
    both need enumerating rather than asserting.

    Reports, per `CreatureCmd.stun(...)` call site: the target expression, and
    whether the target is the caller itself (a monster self-stun, which can
    never be the player) or an externally supplied creature."""
    import sts2_rl.monsters  # noqa: F401
    from audit.tools.harness import _monster_units
    from sts2_rl.monsters.state_machine import MachineMonster

    rows = []
    for path in sorted((_REPO / "sts2_rl").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:                          # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "stun"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "CreatureCmd"):
                continue
            args = [ast.unparse(a) for a in node.args]
            kw = {k.arg: ast.unparse(k.value) for k in node.keywords}
            target = args[1] if len(args) > 1 else "?"
            rows.append((path.relative_to(_REPO).as_posix(), node.lineno,
                         target, kw.get("next_move_key")))
    self_stun = [r for r in rows
                 if r[2] in ("self", "self.owner", "self.owner.creature")]
    external = [r for r in rows if r not in self_stun]
    print(f"CreatureCmd.stun(...) call sites in sts2_rl/: {len(rows)}")
    for path, line, target, nmk in rows:
        kind = "SELF (a monster stunning itself)" if (path, line, target, nmk) in self_stun \
            else "EXTERNAL target"
        print(f"  {path}:{line}  target={target:<12} "
              f"next_move_key={nmk or '-':<14} {kind}")
    print(f"\n  self-stuns (target can never be the player): {len(self_stun)}")
    print(f"  externally-targeted stuns: {len(external)}")
    for path, line, target, _nmk in external:
        print(f"    {path}:{line}  target={target}")
    print("  -> the only externally-targeted stun is the Whistle card, whose "
          "target comes from ctx.resolve_target (an ENEMY slot), so no ported "
          "caller can reach C#'s player guard (Creature.cs:524-531).")
    print(f"  sites passing next_move_key: "
          f"{[f'{r[0]}:{r[1]}' for r in rows if r[3]]}")

    # which of the stunnable monsters is a MachineMonster (G5's hasattr gate)
    units = _monster_units()
    hand, machine = [], []
    for path, line, target, _nmk in rows:
        mod = path.rsplit("/", 1)[-1][:-3]
        for cls in units.values():
            if cls.__module__.endswith(mod):
                (machine if issubclass(cls, MachineMonster) else hand).append(
                    f"{cls.__name__} ({path}:{line})")
                break
    print(f"\n  stun-calling monsters that are MachineMonsters: {sorted(set(machine))}")
    print(f"  stun-calling monsters that are hand-rolled: {sorted(set(hand))}")

    # The three POWER-side stun sites: which power, who applies it, and what
    # that applier's machine is (a chain cannot show the G4 repeat-bar at all).
    print("\n  the power-side stun sites, resolved to their appliers:")
    pw_src = (_REPO / "sts2_rl/powers.py").read_text(encoding="utf-8")
    pw_tree = ast.parse(pw_src)
    owner_of: dict[int, str] = {}
    for node in ast.walk(pw_tree):
        if isinstance(node, ast.ClassDef):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "stun"
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "CreatureCmd"):
                    owner_of[sub.lineno] = node.name
    for line in sorted(owner_of):
        power = owner_of[line]
        appliers = []
        for p in sorted((_REPO / "sts2_rl").rglob("*.py")):
            if p.name == "powers.py":
                continue
            if power in p.read_text(encoding="utf-8"):
                appliers.append(p.relative_to(_REPO).as_posix())
        print(f"    powers.py:{line}  {power}  applied in {appliers}")
        for ap in appliers:
            for cls in units.values():
                if not cls.__module__.endswith(ap.rsplit("/", 1)[-1][:-3]):
                    continue
                classes = _branch_classes(cls)
                print(f"        {cls.__name__}: machine branch classes = "
                      f"{classes or ['NONE (pure chain)']}")


def _branch_classes(cls) -> list[str]:
    """The branch-state classes a monster's machine actually contains, from a
    LIVE instance (a detached build cannot serve every monster)."""
    import random as _random

    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.state_machine import MachineMonster

    if not issubclass(cls, MachineMonster):
        return ["hand-rolled (no machine)"]
    try:
        enc = Encounter(id="probe_branch_classes", monster_classes=[cls])
        mon = CombatState(rng=_random.Random(0), encounter=enc).enemies[0]
    except Exception as exc:                          # pragma: no cover
        return [f"UNBUILDABLE {type(exc).__name__}"]
    return sorted({type(s).__name__ for s in mon.machine.states.values()
                   if type(s).__name__.endswith("BranchState")})


# ── the Whistle -> Glory reachability route for G4 ───────────────────────
_HISTORY_RULES = ("CANNOT_REPEAT", "CAN_REPEAT_X_TIMES", "USE_ONLY_ONCE")


def whistle_route() -> None:
    """EXECUTED end-to-end reachability for G4: which ported monsters a player
    can actually stun, and which of those have a history-sensitive branch.

    Whistle is the only externally-targeted stun in the sim (`stun-sites`) and it
    is granted by ONE relic, Tanx's Whistle, whose shrine key `tanx` belongs to
    exactly one act's ancient pool. So the population of stunnable monsters is
    that act's encounter pools — and NOT any monster of an earlier act, because
    a relic obtained in act N cannot be carried backwards."""
    import random as _random

    from sts2_rl.monsters.state_machine import MachineMonster
    from sts2_rl.rooms import act_rooms
    from sts2_rl.run import _ACTS_BY_INDEX

    acts = ["overgrowth", "underdocks", "hive", "glory"]
    print("  which act's ancient pool holds `tanx` (the Whistle relic's shrine):")
    tanx_acts = []
    for name in acts:
        keys = act_rooms(name).ancient_keys
        if "tanx" in keys:
            tanx_acts.append(name)
        print(f"    {name:<12} ancient_keys={keys}")
    print(f"    -> tanx is in {tanx_acts}")
    print(f"  act order (run._ACTS_BY_INDEX): {_ACTS_BY_INDEX}")
    for name in tanx_acts:
        idx = [i for i, a in enumerate(_ACTS_BY_INDEX) if name in a]
        print(f"    -> {name} is act index {idx}; acts at a LOWER index "
              f"({[a for i, l in enumerate(_ACTS_BY_INDEX) if i < min(idx) for a in l]}) "
              f"are already past when the relic is obtained")

    print("\n  the grant chain, read from the ported files:")
    for rel, pat in (("sts2_rl/relics/tanxs_whistle.py", r"make_card\(\"(\w+)\"\)"),
                     ("sts2_rl/cards/whistle.py", r"CreatureCmd\.stun\(([^)]*)\)")):
        src = (_REPO / rel).read_text(encoding="utf-8")
        for m in re.finditer(pat, src):
            line = src[:m.start()].count("\n") + 1
            print(f"    {rel}:{line}  {m.group(0)}")

    print("\n  every monster in the stun-reachable act's pools, with its "
          "branch classes and repeat rules:")
    hits = []
    for name in tanx_acts:
        rooms = act_rooms(name)
        registry = rooms.encounters()
        keys = (rooms.weak_keys + rooms.normal_keys + rooms.elite_keys
                + rooms.boss_keys)
        seen = {}
        for key in keys:
            enc = registry.get(key)
            if enc is None:
                continue
            try:
                from sts2_rl.combat import CombatState
                mons = CombatState(rng=_random.Random(0), encounter=enc).enemies
            except Exception as exc:                 # pragma: no cover
                print(f"    {key}: could not instantiate ({type(exc).__name__})")
                continue
            for mon in mons:
                cls = type(mon)
                if cls.__name__ in seen:
                    continue
                if not isinstance(mon, MachineMonster):
                    seen[cls.__name__] = (key, "hand-rolled (no machine)", [])
                    continue
                classes, rules = set(), []
                for st in mon.machine.states.values():
                    tn = type(st).__name__
                    if tn in ("RandomBranchState", "ConditionalBranchState"):
                        classes.add(tn)
                    if tn == "RandomBranchState":
                        for b in st._branches:
                            rules.append(
                                f"{b['state_id']}:{b['repeat_type'].name}"
                                + (f"({b['max_times']})"
                                   if b["repeat_type"].name == "CAN_REPEAT_X_TIMES"
                                   else "")
                                + (f"+cd{b['cooldown']}" if b["cooldown"] else ""))
                seen[cls.__name__] = (key, ", ".join(sorted(classes)) or "chain only",
                                      rules)
        for cls_name in sorted(seen):
            key, classes, rules = seen[cls_name]
            mark = ""
            if "RandomBranchState" in classes and any(
                    r.split(":")[1].startswith(x) for r in rules
                    for x in _HISTORY_RULES):
                mark = "   <== RandomBranchState + a history-sensitive rule"
                hits.append(f"{cls_name} ({key})")
            print(f"    {cls_name:<24} [{key}] {classes}{mark}")
            if rules:
                print(f"        {rules}")
    print(f"\n  stun-reachable RandomBranchState machines whose weights read "
          f"the state log: {len(hits)}")
    for h in hits:
        print(f"    {h}")

    print("\n  the monsters the record USED to cite as making G4 live, and what "
          "their machines actually are:")
    for mod, cls_name in (
            ("sts2_rl.monsters.hive.slumbering_beetle", "SlumberingBeetle"),
            ("sts2_rl.monsters.underdocks.lagavulin_matriarch", "LagavulinMatriarch"),
            ("sts2_rl.monsters.underdocks.terror_eel", "TerrorEel"),
            ("sts2_rl.monsters.underdocks.fossil_stalker", "FossilStalker")):
        import importlib
        cls = getattr(importlib.import_module(mod), cls_name)
        from sts2_rl.combat import CombatState
        from sts2_rl.monsters import Encounter
        enc = Encounter(id="probe_route", monster_classes=[cls])
        mon = CombatState(rng=_random.Random(0), encounter=enc).enemies[0]
        classes = sorted({type(s).__name__ for s in mon.machine.states.values()
                          if type(s).__name__.endswith("BranchState")})
        act = [a for a in acts
               if cls.__name__ in {type(m).__name__
                                   for k in (act_rooms(a).weak_keys
                                             + act_rooms(a).normal_keys
                                             + act_rooms(a).elite_keys
                                             + act_rooms(a).boss_keys)
                                   if (e := act_rooms(a).encounters().get(k))
                                   for m in _safe_monsters(e)}]
        print(f"    {cls_name:<20} branch classes={classes or ['NONE (pure chain)']}"
              f"  act(s)={act}")


def _safe_monsters(enc):
    import random as _random
    from sts2_rl.combat import CombatState
    try:
        return CombatState(rng=_random.Random(0), encounter=enc).enemies
    except Exception:                                # pragma: no cover
        return []


# ── the spawn-roll hand-off dropped by creature_card_cmds step 3 ─────────
def spawn_roll() -> None:
    """`creature_card_cmds` step 3 deferred `PrepareForNextTurn(rollNewMove:
    false)` for a monster added while `CurrentSide != Enemy`
    (CreatureCmd.cs:72-75) to this record. EXECUTED here.

    The C# side, read in order out of CreatureCmd.Add (:56-80):
      1. `await CombatManager.AfterCreatureAdded(creature)` -- CombatManager.cs
         :860-867 rolls a move IFF `creature.IsEnemy && CurrentSide == Player`.
      2. `if (CurrentSide != CombatSide.Enemy && creature.IsMonster)` ->
         `PrepareForNextTurn(players, rollNewMove: false)`. With the flag FALSE
         the whole body of PrepareForNextTurn (Creature.cs:546-554) reduces to
         `NCombatRoom...RefreshIntents()`, i.e. presentation -- so the CALL adds
         no mechanics, and the FLAG is a double-roll guard: it stops step 2
         re-rolling what step 1 already rolled.
    Net rolls per spawn, from those two guards (CombatSide has three values:
    None, Player, Enemy -- CombatSide.cs:3-8):
      Player + enemy monster    -> 1 roll   (step 1 rolls; step 2 suppressed)
      Player + NON-enemy monster-> 0 rolls  (step 1's IsEnemy fails; step 2
                                             suppressed)      -> UNSET_MOVE
      Enemy  + any monster      -> 0 rolls  (step 1's side fails; step 2 not
                                             reached)          -> UNSET_MOVE
      None   + any monster      -> 0 rolls                     -> UNSET_MOVE
    The sim has no separate intent-preparation step at all: `CreatureCmd.add`
    (cmds.py:237-266) never rolls, and `MachineMonster.__init__` rolls once at
    construction (state_machine.py:300-301)."""
    import random as _random

    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.state_machine import (
        MachineMonster, MonsterMoveStateMachine,
    )
    from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker

    print("  C# PrepareForNextTurn call sites and their rollNewMove argument:")
    for rel in ("src/Core/Combat/CombatManager.cs",
                "src/Core/Commands/CreatureCmd.cs",
                "src/Core/Entities/Creatures/Creature.cs"):
        src = (DEFAULT_GAME_ROOT / rel).read_text(encoding="utf-8-sig",
                                                  errors="replace")
        for i, ln in enumerate(src.splitlines(), 1):
            if "PrepareForNextTurn" in ln:
                flag = ("rollNewMove: false" if "rollNewMove: false" in ln
                        else "rollNewMove: (default true)"
                        if "(" in ln and "bool rollNewMove" not in ln
                        else "the DECLARATION")
                print(f"    {rel.rsplit('/', 1)[-1]}:{i}  {flag}")
    print("    -> exactly one call site passes false, and it is the one "
          "creature_card_cmds deferred here.")

    # sim: does adding a MachineMonster mid-combat roll, and how many times?
    enc = Encounter(id="probe_spawn", monster_classes=[FossilStalker])
    cs = CombatState(rng=_random.Random(5), encounter=enc)
    real_roll = MonsterMoveStateMachine.roll_move
    calls = {"n": 0}

    def _counting(self, owner, rng):
        calls["n"] += 1
        return real_roll(self, owner, rng)

    MonsterMoveStateMachine.roll_move = _counting
    try:
        spawn = FossilStalker(cs.hooks, _random.Random(6))
        after_ctor = calls["n"]
        log_after_ctor = [s.id for s in spawn.machine.state_log]
        CreatureCmd.add(cs.hooks, spawn)
        after_add = calls["n"]
        # the other arm of AfterCreatureAdded's gate (CombatManager.cs:860-867)
        cs.current_side = "enemy"
        enemy_spawn = FossilStalker(cs.hooks, _random.Random(6))
        before_enemy = calls["n"]
        CreatureCmd.add(cs.hooks, enemy_spawn)
        after_enemy = calls["n"]
    finally:
        MonsterMoveStateMachine.roll_move = real_roll
        cs.current_side = "player"
    print(f"\n  sim, a MachineMonster spawned mid-combat on the PLAYER side:")
    print(f"    roll_move calls during __init__      : {after_ctor}")
    print(f"    roll_move calls during CreatureCmd.add: {after_add - after_ctor}")
    print(f"    state_log after construction         : {log_after_ctor}")
    print(f"    state_log after add                  : "
          f"{[s.id for s in spawn.machine.state_log]}")
    print(f"    _current_move                        : {spawn._current_move.id}")
    print(f"\n  the same spawn on the ENEMY side (the gate's other arm):")
    print(f"    roll_move calls during CreatureCmd.add: "
          f"{after_enemy - before_enemy}   (C#: 0)")
    print(f"    _current_move                        : "
          f"{enemy_spawn._current_move.id}"
          f"   (MonsterModel.NextMove's initial `new MoveState()`)")
    print(f"    picked up by the next player-turn-start pass instead, at its "
          f"position in the enemy list")
    print(f"    creature.side                        : {spawn.side!r}")

    # is the non-enemy-monster arm representable in the sim at all?
    import sts2_rl.monsters  # noqa: F401
    from audit.tools.harness import _monster_units
    sides = set()
    for _uid, cls in sorted(_monster_units().items()):
        if not issubclass(cls, MachineMonster):
            continue
        try:
            e = Encounter(id="probe_side", monster_classes=[cls])
            sides.add(CombatState(rng=_random.Random(0),
                                  encounter=e).enemies[0].side)
        except Exception:
            continue
    print(f"\n  distinct `side` values over every buildable ported monster: "
          f"{sorted(sides)}")
    print("    -> C#'s `Player + NON-enemy monster -> 0 rolls` arm has no sim "
          "representative: creatures.py:21 defaults side='enemy' and no ported "
          "monster changes it.")

    # which sim spawn callers run during the enemy side (the reachable arm)
    callers = []
    for path in sorted((_REPO / "sts2_rl").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:                           # pragma: no cover
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "CreatureCmd"):
                callers.append(f"{path.relative_to(_REPO).as_posix()}:"
                               f"{node.lineno}")
    print(f"\n  sim CreatureCmd.add call sites: {len(callers)}")
    for c in callers:
        print(f"    {c}")
    print("    -> all of them fire from a monster move, a monster death or a "
          "power, i.e. during the ENEMY side, which is exactly the arm where "
          "C# leaves the spawn on UNSET_MOVE (step 11 / G9).")


# ── raise/throw asymmetry census (backs guard N7's recount) ──────────────
# Hand-resolved pairing, re-checked against the greps this probe prints.
# Buckets: SYM = both sides raise on the same input, so only the exception TYPE
# differs (guard N7's whole scope). ASYM = exactly one side raises (a gap).
# ONE-SIDED-GUARD = only one side has a deliberate guard, but the other happens
# to raise anyway for an unrelated reason. DEAD = a defensive throw on a state
# the API on that side cannot produce, with no field to mirror.
#
# REFRESHED 2026-08-01 (round 13 R11 fix pass). Every row below was re-derived
# BY EXECUTION against the current `sts2_rl/monsters/state_machine.py`, not by
# reading the old text. The table it replaces was badly stale: SIX of the
# twelve rows described sim behaviour that no longer exists (rows 6-11 below,
# all of which asserted an asymmetry that has since been closed), a seventh
# (row 2) had the wrong bucket AND a misread of what the C# guard even checks,
# and ALL TWELVE sim line citations pointed at lines that hold something else.
# The old summary line therefore read "guard N7 covers 5 sites; 6
# raise-behaviour sites are gaps (G7 x3, G8 x3)" when the true count is 8
# symmetric and ONE gap. Rounds 12-13 closed those gaps in the engine and
# nobody re-ran this census.
#
# One bucket is new. "SYM" was documented as "both sides raise on the same
# input, so only the TYPE differs" -- that is guard N7's entire scope, so a
# row where NEITHER side raises must not inflate N7's count. Two rows are now
# in that state (the engine matched C# by no longer raising at all), so they
# get their own bucket and are kept as a record of a closed asymmetry rather
# than deleted.
_RAISE_PAIRS = [
    # (bucket, what, C# site, sim site)
    ("SYM", "machine: RollMove landed on a non-move",
     "MonsterMoveStateMachine.cs:37-40",
     "state_machine.py:380-381 raises RuntimeError with the same text "
     "('{id} is not a valid move state')"),
    ("ONE-SIDED-GUARD",
     "machine: FindNextMoveState entered with a NULL current state",
     "MonsterMoveStateMachine.cs:56-59 throws InvalidOperationException "
     "('Cannot find next move state when current state is null.')",
     "no deliberate guard: `_find_next_move_state` (state_machine.py:424) "
     "reads `self.current.can_transition_away` and the constructor "
     "(state_machine.py:373) reads `initial_state.should_appear_in_logs`, so "
     "a None lands as an AttributeError from attribute access -- a different "
     "predicate's side effect, which is what this bucket means. NOTE: the "
     "row this replaces was labelled 'no initial state to fall back to', "
     "which misreads the C#; :56-59 guards the CURRENT state, and the "
     "initial-state fallback at :72 has no guard on either side"),
    ("SYM", "machine: unknown state id from GetNextState",
     "MonsterMoveStateMachine.cs:68-71",
     "state_machine.py:431-432 raises RuntimeError with C#'s text verbatim "
     "('no valid state found: {id}')"),
    ("SYM", "MoveState: no follow-up at all",
     "MoveState.cs:69",
     "state_machine.py:196 raises RuntimeError "
     "('MoveState {id} has no follow-up state')"),
    ("SYM", "conditional: no branch evaluated > 0",
     "ConditionalBranchState.cs:53",
     "state_machine.py:324 raises RuntimeError "
     "('No valid branch in ConditionalBranchState {id}')"),
    ("SYM", "branch: the subtract-and-check loop falls through (step 15, G7c)",
     "RandomBranchState.cs:127",
     "state_machine.py:273 RAISES, with RandomBranchState.cs:127's text "
     "verbatim -- executed under a forced overshoot. The row this replaces "
     "was bucketed ASYM on the claim 'state_machine.py:189 returns the LAST "
     "branch'; that has not been true since round 12's T22"),
    ("SYM-NO-RAISE", "branch: every weight is 0 (step 15, G7 clause b)",
     "RandomBranchState.cs:117-124 burns a draw and picks branch 0 -- no throw",
     "state_machine.py:265-273 does the same: `_weighted_roll` draws FIRST, "
     "roll starts at 0 and branch 0's `roll <= 0` is immediately true. "
     "Executed: an all-zero vector returns branch 0, no raise. The row this "
     "replaces was bucketed ASYM on 'state_machine.py:183 raises before "
     "drawing'"),
    ("SYM-NO-RAISE",
     "branch: CanRepeatXTimes with an explicit maxTimes == 0 (step 21, G7a)",
     "RandomBranchState.cs:144-147 builds a permanently dead branch -- no throw",
     "state_machine.py:239-240's guard fires only for `max_times is None`; an "
     "explicit `max_times=0` is legal and ported in `_effective_weight`. "
     "Executed: accepted, no raise. The row this replaces claimed "
     "'state_machine.py:168-169 raises ValueError'"),
    ("SYM", "register: duplicate state id (step 3, G8 clause a)",
     "MonsterState.cs:19 -> Dictionary.Add throws ArgumentException",
     "state_machine.py:130-134 raises ValueError ('duplicate state id ...'). "
     "Executed. The row this replaces claimed 'state_machine.py:87 silently "
     "overwrites'"),
    ("SYM", "model: the MoveStateMachine setter set twice (step 37, G8 clause b)",
     "MonsterModel.cs:222-237 throws InvalidOperationException; "
     "ResetStateMachine (MonsterModel.cs:389-392) is the sanctioned clear",
     "state_machine.py:482-495 IS a property setter and raises RuntimeError; "
     "`reset_state_machine` (state_machine.py:497-505) mirrors C#'s clear and "
     "is the only way to reassign. Both executed. The row this replaces "
     "claimed 'no setter; `self.machine = ...` silently rebinds'"),
    ("SYM",
     "AddBranch overload #1 given CanRepeatXTimes (step 22, G8 clause c)",
     "RandomBranchState.cs:48-51 throws ArgumentException "
     "('Use other constructor to specify number of repeats')",
     "state_machine.py:239-240 raises ValueError on exactly C#'s predicate -- "
     "repeat_type CAN_REPEAT_X_TIMES with no maxRepeats supplied "
     "(`max_times is None`). Executed. The row this replaces called it "
     "'no analogue of C#'s guard ... happens to raise for a DIFFERENT "
     "predicate (max_times <= 0)', which is doubly wrong: the predicate is "
     "the same one, and `max_times <= 0` is not what the code tests"),
    ("DEAD", "branch: StateWeight.GetWeight with a null lambda (step 12)",
     "RandomBranchState.cs:29 -- unreachable, no overload can leave it null",
     "no such field; the sim's weight default is in the add_branch signature "
     "(`weight: float | Callable = 1.0`, state_machine.py:220). Caveat found "
     "while re-deriving: an EXPLICIT `add_branch(state, None)` is accepted and "
     "stored verbatim, so it would TypeError at roll time rather than at "
     "build time -- unreached today (no caller passes None) but not guarded"),
]


def raise_sites() -> None:
    """Guard N7 claims the exception TYPE never matters and excludes "the places
    where one side raises and the other does not". That exclusion list has to be
    counted, not guessed — this probe counts it.

    Prints the raw greps (C# `throw` in the five machine files + MonsterModel,
    sim `raise` in state_machine.py) and then the resolved pairing, bucketed."""
    cs_files = [
        "src/Core/MonsterMoves/MonsterMoveStateMachine/MonsterMoveStateMachine.cs",
        "src/Core/MonsterMoves/MonsterMoveStateMachine/MonsterState.cs",
        "src/Core/MonsterMoves/MonsterMoveStateMachine/MoveState.cs",
        "src/Core/MonsterMoves/MonsterMoveStateMachine/RandomBranchState.cs",
        "src/Core/MonsterMoves/MonsterMoveStateMachine/ConditionalBranchState.cs",
    ]
    total_cs = 0
    for rel in cs_files:
        src = (DEFAULT_GAME_ROOT / rel).read_text(encoding="utf-8-sig",
                                                  errors="replace")
        lines = [i + 1 for i, ln in enumerate(src.splitlines())
                 if re.search(r"\bthrow new\b", ln)]
        total_cs += len(lines)
        print(f"  {rel.rsplit('/', 1)[-1]:<28} throw new at {lines}")
    sim = (_REPO / "sts2_rl/monsters/state_machine.py").read_text(encoding="utf-8")
    sim_lines = [i + 1 for i, ln in enumerate(sim.splitlines())
                 if re.search(r"^\s*raise \w", ln)]
    print(f"  {'state_machine.py':<28} raise at {sim_lines}")
    print(f"\n  C# throw sites in the machine files: {total_cs}   "
          f"sim raise sites in state_machine.py: {len(sim_lines)}")

    labels = {
        "SYM": "SYMMETRIC (both sides raise -> only the TYPE differs; "
               "this is guard N7's ENTIRE scope)",
        "SYM-NO-RAISE": "SYMMETRIC, NEITHER SIDE RAISES (the sim used to and "
                        "no longer does -> a CLOSED asymmetry, and NOT part "
                        "of N7's count, which is about raise TYPE)",
        "ASYM": "ASYMMETRIC (exactly one side raises -> a gap, NOT N7's)",
        "ONE-SIDED-GUARD": "ONE-SIDED GUARD (only C# guards it deliberately; "
                           "the sim's raise is a different predicate's "
                           "side effect -> also a gap)",
        "DEAD": "DEAD ON BOTH SIDES (a defensive throw the API cannot reach; "
                "faithful)",
    }
    seen = set()
    for bucket, label in labels.items():
        rows = [p for p in _RAISE_PAIRS if p[0] == bucket]
        seen.update(p[0] for p in rows)
        print(f"\n  {label}: {len(rows)}")
        for _b, what, cs, py in rows:
            print(f"    {what}\n        C#: {cs}\n        sim: {py}")
    unlabelled = {p[0] for p in _RAISE_PAIRS} - set(labels)
    if unlabelled:                                   # pragma: no cover
        print(f"\n  !! rows in unlabelled buckets (not counted): {unlabelled}")
    n_sym = sum(1 for p in _RAISE_PAIRS if p[0] == "SYM")
    n_closed = sum(1 for p in _RAISE_PAIRS if p[0] == "SYM-NO-RAISE")
    n_gap = sum(1 for p in _RAISE_PAIRS if p[0] in ("ASYM", "ONE-SIDED-GUARD"))
    print(f"\n  => guard N7 covers {n_sym} sites; {n_gap} raise-behaviour "
          f"site(s) remain gaps and are NOT N7's; {n_closed} former "
          f"asymmetries are now closed on both sides.")
    print("     (Refreshed by execution 2026-08-01, round 13 R11 fix pass. "
          "The previous printout said '5 sites / 6 gaps (G7 x3, G8 x3)' from "
          "a table whose sim half had gone stale in six rows -- see the "
          "comment above _RAISE_PAIRS.)")


PROBES = {
    "sources-sweep": sources_sweep,
    "cs-addbranch": cs_addbranch,
    "cs-conditional": cs_conditional,
    "mismatch": mismatch,
    "distribution": distribution,
    "stun-machine": stun_machine,
    "sim-addbranch": sim_addbranch,
    "addbranch-diff": addbranch_diff,
    "branch-order": branch_order,
    "hand-rolled": hand_rolled,
    "move-rng": move_rng,
    "zero-weight": zero_weight,
    "nondyadic-weights": nondyadic_weights,
    "stun-sites": stun_sites,
    "whistle-route": whistle_route,
    "raise-sites": raise_sites,
    "spawn-roll": spawn_roll,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    for name in ([args.probe] if args.probe else sorted(PROBES)):
        print(f"\n===== {name} =====")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
