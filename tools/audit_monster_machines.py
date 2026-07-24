r"""Static audit: which sim monsters hand-roll moves whose game source uses
RandomBranchState/ConditionalBranchState, and what the source's exact branch
args are. Output is a review table, not an auto-fix -- the human (or the
fixing session) reads each flagged monster's source and ports/corrects it.

Background -- the bug class this hunts (attested in TwigSlimeM, Flyconid):
a hand-rolled monster's author read a C# `AddBranch(...)` int argument as a
*weight* when it is actually a cooldown / maxRepeats value. That corrupts
both the move choice AND the MonsterAi draw count (RandomBranchState always
draws exactly one `NextFloat(total)` per transition, even when a repeat rule
or cooldown has zeroed every branch but one).

`RandomBranchState.AddBranch` overload table (from
`Slay the Spire 2/src/Core/MonsterMoves/MonsterMoveStateMachine/RandomBranchState.cs`,
read 2026-07-23) -- args always start with `state`, then:

  1. (repeatType)                                    weight=1f,  cooldown=0
  2. (maxRepeats:int)                                 weight=1f,  cooldown=0, CanRepeatXTimes
  3. (repeatType, weight:float)                       cooldown=0
  4. (repeatType, weight:Func<float>)                 cooldown=0
  5. (maxRepeats:int, weight:float)                   cooldown=0, CanRepeatXTimes
  6. (maxRepeats:int, weight:Func<float>)              cooldown=0, CanRepeatXTimes
  7. (cooldown:int, repeatType)                        weight=1f
  8. (cooldown:int, repeatType, weight:float)
  9. (cooldown:int, repeatType, weight:Func<float>)
  10. (cooldown:int, maxRepeats:int, weight:Func<float>) CanRepeatXTimes

Decoding a raw call: if a `MoveRepeatType.*` literal appears, that slot is
the repeat type and an int immediately before it (if any) is `cooldown`.
If there is NO MoveRepeatType literal and there are two leading ints before
the weight, they are `(cooldown, maxRepeats)` (overload 10, implicit
CanRepeatXTimes). If there is exactly one leading int before the weight (no
MoveRepeatType literal at all), it is `maxRepeats` alone, cooldown=0
(overloads 2/5/6) -- there is NO overload of the shape (cooldown:int,
weight) with the repeat type omitted, so a lone int followed only by a
weight is never a bare cooldown. `weight` itself is a plain float literal
or a `() => expr` lambda (evaluated at roll time, e.g. HP-scaled weights);
either way it does not change the meaning of the earlier int args.

`RandomBranchState.GetNextState` (RandomBranchState.cs:115-128) always sums
ALL branch weights (post repeat-rule/cooldown zeroing) and draws exactly one
`rng.NextFloat(max)` -- even when only one branch survives with nonzero
weight. A hand-rolled port that special-cases "only one branch is legal, so
skip the roll" desyncs the MonsterAi draw stream from that point on.

Usage: py tools/audit_monster_machines.py [act]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
SRC = _REPO.parent / "Slay the Spire 2" / "src"
MON = SRC / "Core" / "Models" / "Monsters"
MOVES = SRC / "Core" / "MonsterMoves"

_BRANCH = re.compile(r"AddBranch\s*\(([^;]*?)\)\s*;", re.S)
_STATE_MACHINE_TYPE = re.compile(
    r"\bnew\s+(\w*(?:MoveStateMachine|Moves))\s*\("
)
_GEN_MOVE_MACHINE = re.compile(r"MonsterMoveStateMachine\s+GenerateMoveStateMachine\s*\([^)]*\)\s*\{")


def _move_machine_body(text: str) -> str | None:
    """Brace-matched body of `GenerateMoveStateMachine()`, if present.

    Move-graph AddBranch calls (RandomBranchState/ConditionalBranchState)
    live here. Monster .cs files ALSO define `GenerateAnimator()`, whose
    unrelated `AnimState.AddBranch("Hit", ...)` calls share the same method
    name and would otherwise false-positive a flag (e.g. BygoneEffigy,
    CeremonialBeast both call `animState.AddBranch(...)` for visuals only --
    their actual move graphs are plain MoveState chains with no branching).
    Scoping to this method's body is what keeps the audit's flagged table
    honest.
    """
    m = _GEN_MOVE_MACHINE.search(text)
    if m is None:
        return None
    depth = 1
    i = m.end()
    start = i
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start : i - 1]


def _candidate_names(cls_name: str) -> list[str]:
    """Class-name variants to try against MON/*.cs, most-specific first.

    The sim sometimes suffixes/prefixes its class name relative to the C#
    monster class (e.g. sim `Crusher`/`Rocket` for KaiserCrab pieces, sim
    `TwigSlimeM` for the C# `TwigSlimeM` itself -- exact match first, then
    trailing-letter variants for monsters with size suffixes like S/M/L).
    """
    cands = [cls_name]
    if cls_name and cls_name[-1] in "SML" and len(cls_name) > 1:
        cands.append(cls_name[:-1])
    return cands


def source_for(cls_name: str) -> Path | None:
    for cand in _candidate_names(cls_name):
        f = MON / f"{cand}.cs"
        if f.exists():
            return f
    return None


def branch_table(cs: Path) -> list[str]:
    """All AddBranch(...) argument strings reachable from `cs`'s move graph:
    the `GenerateMoveStateMachine()` method body (NOT the whole file -- see
    `_move_machine_body`) plus any *MoveStateMachine/*Moves type it `new`s up
    (the game often factors a monster's move graph into a separate
    MonsterMoves/*.cs file, referenced by `new FooMoveStateMachine(...)` in
    the monster class; those files are pure move logic with no animator, so
    they're searched in full).
    """
    text = cs.read_text(encoding="utf-8", errors="replace")
    combined = _move_machine_body(text) or ""
    for m in _STATE_MACHINE_TYPE.finditer(text):
        for extra in MOVES.rglob(f"{m.group(1)}.cs"):
            combined += "\n" + extra.read_text(encoding="utf-8", errors="replace")
    return [" ".join(b.split()) for b in _BRANCH.findall(combined)]


def main(act_filter: str | None) -> None:
    import importlib
    import inspect

    from sts2_rl.monsters.base import Monster
    from sts2_rl.monsters.state_machine import MachineMonster

    for act in ("overgrowth", "underdocks", "hive", "glory"):
        if act_filter and act != act_filter:
            continue
        mod = importlib.import_module(f"sts2_rl.monsters.{act}")
        pkg = Path(mod.__file__).parent
        for py in sorted(pkg.glob("*.py")):
            if py.stem == "__init__":
                continue
            m = importlib.import_module(f"sts2_rl.monsters.{act}.{py.stem}")
            for cname, cls in inspect.getmembers(m, inspect.isclass):
                if not (issubclass(cls, Monster) and cls is not Monster):
                    continue
                if cls.__module__ != m.__name__:
                    continue
                cs = source_for(cname)
                if cs is None:
                    print(f"[no source] {act}.{cname} -- no {cname}.cs under {MON}")
                    continue
                branches = branch_table(cs)
                hand_rolled = not issubclass(cls, MachineMonster)
                if branches and hand_rolled:
                    print(
                        f"[FLAG] {act}.{cname}  ({cs.name}) -- hand-rolled but "
                        f"source has {len(branches)} AddBranch calls:"
                    )
                    for b in branches:
                        print(f"    AddBranch({b})")
                elif branches:
                    print(
                        f"[ok, machine] {act}.{cname}  ({cs.name}) -- "
                        f"{len(branches)} AddBranch calls, already MachineMonster"
                    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
