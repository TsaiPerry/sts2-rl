"""Reproducible probes for seam/monster_state_machine (Task 10).

Same contract as tools/audit/dormancy_probes.py: every "executed evidence"
number the record states is produced here so a later auditor can re-derive it.

  py tools/audit/state_machine_probes.py                # every probe
  py tools/audit/state_machine_probes.py cs-addbranch   # one probe

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
                    machine? (C# returns branch 0; the sim raises RuntimeError)
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
                    spec doc cites must appear in SEAM_SOURCES.
  stun-machine      EXECUTED: what a stun does to the move machine on each
                    side (sim keeps _current_move and never touches the
                    machine; C# force-sets a synthetic STUNNED MoveState and
                    re-logs the deferred move).
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

from tools.audit.harness import DEFAULT_GAME_ROOT  # noqa: E402

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
    from tools.audit.harness import _monster_units
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


def zero_weight(walks: int = 200, steps: int = 400) -> None:
    """Can a ported RandomBranchState reach total weight 0?

    C# GetNextState (RandomBranchState.cs:117-127) does rng.NextFloat(0) -> 0,
    then `num -= 0; if (num <= 0) return States[0]` — it BURNS a draw and picks
    the FIRST branch. The sim raises RuntimeError before drawing
    (state_machine.py:182-183).

    Executed reachability: drive every ported MachineMonster's machine through
    `walks` random walks of `steps` transitions each and count RuntimeErrors."""
    import random as _random

    import sts2_rl.monsters  # noqa: F401
    from tools.audit.harness import _monster_units
    from sts2_rl.monsters.state_machine import MachineMonster

    class _Owner:
        pass

    units = dict(_monster_units())
    from sts2_rl.monsters.fake_merchant import FakeMerchantMonster
    units["fake_merchant_monster"] = FakeMerchantMonster

    fuzzed, skipped, hits, transitions = [], [], [], 0
    for unit_id, cls in sorted(units.items()):
        if not issubclass(cls, MachineMonster):
            continue
        try:
            probe = cls.__new__(cls).build_machine()
        except Exception as exc:
            skipped.append((cls.__name__, f"build_machine: {type(exc).__name__}"))
            continue
        del probe
        ok, err = 0, None
        for w in range(walks):
            rng = _random.Random(w)
            machine = cls.__new__(cls).build_machine()
            owner = _Owner()
            owner.machine = machine
            machine._performed_first_move = True
            try:
                for _ in range(steps):
                    move = machine.roll_move(owner, rng)
                    machine.on_move_performed(move)
                    ok += 1
            except RuntimeError as exc:
                if "No valid branch" in str(exc):
                    hits.append((cls.__name__, str(exc)))
                    break
                err = f"{type(exc).__name__}: {exc}"
                break
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                break
        transitions += ok
        (skipped if err else fuzzed).append(
            (cls.__name__, err or f"{ok} transitions"))
    print(f"machines fuzzed: {len(fuzzed)}  transitions: {transitions}")
    print(f"'No valid branch' (total weight 0) hits: {len(hits)}")
    for h in hits:
        print(f"  {h[0]}: {h[1]}")
    print(f"machines skipped (need a live monster instance): {len(skipped)}")
    for s in skipped:
        print(f"  {s[0]}: {s[1]}")


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
    print(f"\n  monsters whose sim port MISREADS the C# branch arguments: "
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



# ── rule-7 sweep: every cited file must be a hashed source ───────────────
_SWEEP_EXCLUDE = ("test/", "tools/audit/")


def sources_sweep() -> None:
    """Extract every .cs / .py token from the record AND the spec doc, resolve
    it against the real trees, and report any that SEAM_SOURCES does not hash.

    This is governing rule 7 mechanised — it has been a review finding on
    three consecutive seam tasks, so it is executable rather than a promise."""
    import json

    from tools.audit.harness import SEAM_SOURCES

    game_paths, sim_paths = SEAM_SOURCES["monster_state_machine"]
    hashed = {p.rsplit("/", 1)[-1] for p in game_paths + sim_paths}
    hashed_full = set(game_paths) | set(sim_paths)

    texts = []
    for rel in ("audits/seam/monster_state_machine.json",
                "docs/audit/seams/monster_state_machine.md"):
        f = _REPO / rel
        if f.exists():
            texts.append((rel, f.read_text(encoding="utf-8")))
    if not texts:
        print("  nothing to sweep yet")
        return

    cited: dict[str, set[str]] = {}
    for rel, text in texts:
        for tok in re.findall(r"[\w./\-]+\.(?:cs|py)", text):
            tok = tok.replace("\\", "/").lstrip("./")
            cited.setdefault(tok, set()).add(rel)

    missing, resolved = [], 0
    for tok in sorted(cited):
        base = tok.rsplit("/", 1)[-1]
        if any(tok.startswith(x) or f"/{x}" in tok for x in _SWEEP_EXCLUDE):
            continue
        if tok in hashed_full or base in hashed:
            resolved += 1
            continue
        # does it exist at all? (a bare basename may be a real unhashed file)
        hits = ([p.relative_to(DEFAULT_GAME_ROOT).as_posix()
                 for p in (DEFAULT_GAME_ROOT / "src").rglob(base)]
                + [p.relative_to(_REPO).as_posix()
                   for p in (_REPO / "sts2_rl").rglob(base)])
        missing.append((tok, sorted(cited[tok]), hits[:3]))
    print(f"  {len(cited)} distinct .cs/.py tokens cited; {resolved} hashed; "
          f"{len(missing)} NOT hashed (excluding {_SWEEP_EXCLUDE})")
    for tok, where, hits in missing:
        tag = "REAL FILE, UNHASHED" if hits else "no such file (prose token?)"
        print(f"    {tok:<44} {tag}  cited in {', '.join(w.split('/')[-1] for w in where)}")
        for h in hits:
            print(f"        -> {h}")


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
