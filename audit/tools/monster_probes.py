"""Pool-wide sweeps for the monster content-audit stream.

`audit/tools/PROMPT.md`'s "Sweep the shape before you audit the units" section
asks each kind to write its own version of the relic sweeps. These are the
monster ones. Every number a monster record cites from a sweep is reproducible
with `py audit/tools/monster_probes.py <probe>`.

BINDING CAVEAT, from PROMPT.md v6 item 1: **a sweep may escalate a candidate,
it may never clear one.** Every bucket below is named for what it OBSERVED, not
for a safety claim; where a bucket cannot decide, it prints INCONCLUSIVE and
the unit's own batch has to settle it by reading both files.

Probes
------
  hp            Min/MaxInitialHp (non-ascension branch) vs the sim class's
                min_hp/max_hp, for all 109 roster units.
  kind          Which sim ports are MachineMonster and which are hand-rolled,
                cross-referenced with whether the C# model builds a machine at
                all and how many states/branches it has.
  ctor-order    The AfterAddedToRoom-in-__init__ shape: the game applies a
                monster's starting powers from Hook AfterCreatureAdded (before
                Hook.BeforeCombatStart, CombatManager.cs:860-867) with every
                run-level listener already live; the sim applies them inside
                Monster.__init__, which runs at CombatState.__init__'s
                create_monsters call (combat.py:134) - BEFORE relics attach
                (:157-159), before belt potions register (:164-166), before the
                parity Niche HP roll (:152-153), and before hooks.on_combat_start
                (:208). Reports each site plus what is and is not registered.
  roll-order    Per MachineMonster with a constructor-applied power: does the
                sim's first roll (state_machine.py:301, inside super().__init__)
                run BEFORE that power is applied, and can the first roll read
                state at all (i.e. is the initial state a branch)? A branch
                initial state means the roll is not the sticky no-op of
                monster_state_machine step 30 and the missing power is readable.
  intents       C# intent classes used per model vs the sim MoveType(s) the
                port telegraphs. Enumeration only - the mapping itself is
                unaudited by any seam (monster_state_machine boundary hole 2).
"""
from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_GAME = Path(r"C:\Users\Perry\Desktop\Slay the Spire 2")
_CS = _GAME / "src" / "Core" / "Models" / "Monsters"

if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _units() -> dict[str, type]:
    import harness
    return harness._monster_units()


def _cs_path_for(unit_id: str, cls: type) -> Path | None:
    """The roster's own resolution, reused so a sweep cannot disagree with it."""
    import harness
    name = cls.__name__.lstrip("_")
    p = _CS / f"{name}.cs"
    if p.is_file():
        return p
    # harness carries the name_overrides table; fall back to it.
    try:
        row = harness.name_overrides()  # type: ignore[attr-defined]
    except Exception:
        row = {}
    alt = (row.get("monster") or {}).get(unit_id)
    if alt:
        p2 = _GAME / alt
        if p2.is_file():
            return p2
    return None


_ASC = re.compile(
    r"AscensionHelper\.GetValueIfAscension\(\s*AscensionLevel\.\w+\s*,\s*"
    r"(-?\d+)\s*,\s*(-?\d+)\s*\)")


def _non_ascension(expr: str) -> str:
    """GetValueIfAscension(level, ascensionValue, fallbackValue) - PROMPT.md v5:
    the NON-ascension value is the LAST argument."""
    return _ASC.sub(lambda m: m.group(2), expr)


def _cs_int_prop(text: str, name: str) -> str | None:
    m = re.search(rf"\boverride\s+int\s+{name}\s*=>\s*(.+?);", text)
    if not m:
        return None
    return _non_ascension(m.group(1)).strip()


def _eval_hp(expr: str, text: str, depth: int = 0) -> int | None:
    """Resolve a Min/MaxInitialHp expression to an int, following one level of
    `=> MinInitialHp` style self-reference and simple arithmetic."""
    if depth > 3:
        return None
    expr = expr.strip()
    if re.fullmatch(r"-?\d+", expr):
        return int(expr)
    for other in ("MinInitialHp", "MaxInitialHp"):
        if other in expr:
            sub = _cs_int_prop(text, other)
            if sub is None:
                return None
            val = _eval_hp(sub, text, depth + 1)
            if val is None:
                return None
            expr = expr.replace(other, str(val))
    if re.fullmatch(r"[\d\s+\-*/()]+", expr):
        try:
            return int(eval(expr))  # noqa: S307 - digits and operators only
        except Exception:
            return None
    return None


def hp() -> None:
    """Min/MaxInitialHp (non-ascension) vs the sim's declared range."""
    units = _units()
    rows, unresolved = [], []
    for unit_id, cls in sorted(units.items()):
        p = _cs_path_for(unit_id, cls)
        if p is None:
            unresolved.append((unit_id, "no C# file resolved"))
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        mn_e, mx_e = _cs_int_prop(text, "MinInitialHp"), _cs_int_prop(text, "MaxInitialHp")
        if mn_e is None and mx_e is None:
            unresolved.append((unit_id, "no Min/MaxInitialHp override (inherited)"))
            continue
        mn = _eval_hp(mn_e, text) if mn_e else None
        mx = _eval_hp(mx_e, text) if mx_e else None
        smn, smx = getattr(cls, "min_hp", None), getattr(cls, "max_hp", None)
        if mn is None or mx is None:
            unresolved.append((unit_id, f"unparsed: min={mn_e!r} max={mx_e!r}"))
            continue
        rows.append((unit_id, mn, mx, smn, smx, (mn, mx) == (smn, smx)))
    bad = [r for r in rows if not r[5]]
    print(f"  {len(rows)} units compared, {len(bad)} MISMATCH, "
          f"{len(unresolved)} INCONCLUSIVE (not compared)")
    for unit_id, mn, mx, smn, smx, _ in bad:
        print(f"    MISMATCH {unit_id:<30} C#[{mn},{mx}]  sim[{smn},{smx}]")
    for unit_id, why in unresolved:
        print(f"    INCONCLUSIVE {unit_id:<26} {why}")
    print("  (a match here is NOT a clear for the unit: it compares two "
          "numbers and nothing else)")


def kind() -> None:
    """MachineMonster vs hand-rolled, against the C# machine's shape."""
    from sts2_rl.monsters.state_machine import MachineMonster
    units = _units()
    machine, hand, nomachine = [], [], []
    for unit_id, cls in sorted(units.items()):
        p = _cs_path_for(unit_id, cls)
        text = p.read_text(encoding="utf-8-sig", errors="replace") if p else ""
        n_move = len(re.findall(r"new MoveState\(", text))
        n_rand = len(re.findall(r"new RandomBranchState\(", text))
        n_cond = len(re.findall(r"new ConditionalBranchState\(", text))
        has_gen = "GenerateMoveStateMachine" in text
        row = (unit_id, n_move, n_rand, n_cond, has_gen)
        if issubclass(cls, MachineMonster):
            machine.append(row)
        elif not has_gen:
            nomachine.append(row)
        else:
            hand.append(row)
    print(f"  MachineMonster ports: {len(machine)}")
    print(f"  hand-rolled ports whose C# model DOES build a machine: {len(hand)}")
    for unit_id, mv, rb, cb, _ in hand:
        flag = "  <- has a C# branch state" if (rb or cb) else ""
        print(f"    {unit_id:<30} C# MoveStates={mv} Random={rb} Conditional={cb}{flag}")
    print(f"  ports whose C# model builds NO machine: {len(nomachine)}")
    for unit_id, *_ in nomachine:
        print(f"    {unit_id}")


# DEFECT FIXED 2026-07-27, found by batch 2 while auditing its own units and
# never by reviewing this file (PROMPT.md v6 item 1, third instance). The
# original pattern was `def __init__\(self`, which cannot match a WRAPPED
# signature — `def __init__(\n        self, ...)`. `ctor-order` therefore
# under-reported by 11 (35 sites where the true count is 46), and
# SHARED-FINDINGS §2 shipped the wrong population. A sweep that under-reports
# silently CLEARS units, which is the direction nothing downstream re-checks.
# `_ctor_body` now also reports how many classes it could not find an
# `__init__` for at all, so a future regex failure is visible rather than mute.
_CTOR = re.compile(r"def __init__\(\s*self.*?(?=\n    [@a-zA-Z]|\nclass |\Z)", re.S)


def ctor_order() -> None:
    """Starting powers applied in __init__ vs the game's AfterAddedToRoom."""
    from sts2_rl.monsters.state_machine import MachineMonster
    units = _units()
    sites, no_ctor, unreadable = [], [], []
    for unit_id, cls in sorted(units.items()):
        try:
            src = inspect.getsource(cls)
        except OSError:
            unreadable.append(unit_id)
            continue
        m = _CTOR.search(src)
        if not m:
            no_ctor.append(unit_id)
            continue
        body = m.group(0)
        effects = re.findall(r"(PowerCmd\.apply|BlockCmd\.apply|CreatureCmd\.\w+)", body)
        if not effects:
            continue
        p = _cs_path_for(unit_id, cls)
        text = p.read_text(encoding="utf-8-sig", errors="replace") if p else ""
        sites.append((unit_id, sorted(set(effects)),
                      "AfterAddedToRoom" in text,
                      issubclass(cls, MachineMonster)))
    print(f"  sim monsters applying an effect from __init__: {len(sites)}")
    no_hook = [s for s in sites if not s[2]]
    for unit_id, eff, has_hook, is_machine in sites:
        tag = "" if has_hook else "   <- C# model has NO AfterAddedToRoom override"
        print(f"    {unit_id:<30} {'machine' if is_machine else 'hand   '} "
              f"{','.join(eff)}{tag}")
    print(f"  of those, {len(no_hook)} have no C# AfterAddedToRoom override "
          f"(the port chose the constructor for something the game does elsewhere)")
    print(f"  COVERAGE (so a regex failure is visible, not mute): "
          f"{len(units)} roster units, {len(no_ctor)} with no __init__ matched, "
          f"{len(unreadable)} whose source could not be read")
    if no_ctor:
        print(f"    no __init__ matched: {', '.join(no_ctor)}")
    print("""
  WHAT IS LIVE AT THAT MOMENT (read from sts2_rl/combat.py, CombatState.__init__):
    registered BEFORE create_monsters (combat.py:134):
      CombatHistory (:112), the player's cards and their enchantments (:124-133)
    NOT registered until AFTER create_monsters returns:
      relics            (:157-159 relic.attach)
      belt potions      (:164-166)
      the parity Niche HP roll that overwrites hp/max_hp (:152-153)
      hooks.on_combat_start (:208)
    and `combat.enemies` does not exist until the assignment at :134 completes,
    so a constructor-time effect cannot see its own side.
  GAME SIDE: CombatManager.AfterCreatureAdded (CombatManager.cs:860-867) awaits
    creature.AfterAddedToRoom() from StartCombatInternal (CombatManager.cs:394-398),
    which runs AFTER SetUpCombat has added every creature and BEFORE
    Hook.BeforeCombatStart (CombatManager.cs:403). Relics/potions are run-level
    AbstractModel listeners and are live for all of it.""")


def roll_order() -> None:
    """For MachineMonsters: does the first roll precede the starting powers,
    and is the initial state a branch (i.e. can that roll read them)?"""
    from sts2_rl.monsters.state_machine import (MachineMonster, MoveState,
                                                MonsterMoveStateMachine)
    units = _units()
    rows = []
    for unit_id, cls in sorted(units.items()):
        if not issubclass(cls, MachineMonster):
            continue
        try:
            src = inspect.getsource(cls)
        except OSError:
            continue
        m = _CTOR.search(src)
        ctor_effect = bool(m and re.search(
            r"(PowerCmd\.apply|BlockCmd\.apply)", m.group(0)))
        if not ctor_effect:
            continue
        # Build the machine detached to read its initial state's type.
        try:
            inst = cls.__new__(cls)
            machine: MonsterMoveStateMachine = cls.build_machine(inst)
            initial = machine.current
            sticky = isinstance(initial, MoveState)
        except Exception as exc:                       # pragma: no cover
            rows.append((unit_id, "INCONCLUSIVE", f"build failed: {exc!r}"))
            continue
        rows.append((unit_id, "sticky-no-op" if sticky else "WALKS",
                     f"initial={initial.id} ({type(initial).__name__})"))
    print("  MachineMonsters that apply a power in __init__ (so the first roll,\n"
          "  state_machine.py:301 inside super().__init__, runs BEFORE it):")
    for unit_id, verdict, detail in rows:
        print(f"    {unit_id:<30} {verdict:<14} {detail}")
    print("""
  READING: 'sticky-no-op' means monster_state_machine step 30's early return
  fires (the initial state is a MoveState and _performed_first_move is False),
  so the first roll evaluates no branch and reads no power - the ordering is
  unobservable for that unit. 'WALKS' means the initial state is a branch, so
  the constructor's first roll DOES evaluate branch weights/conditions while
  the monster's own starting powers are not applied yet; that unit's batch must
  check whether any of its weights or conditions reads self.powers.""")


_INTENT = re.compile(r"new (\w*Intent)\(")


def intents() -> None:
    """C# intent classes per model vs the sim MoveTypes the port names."""
    units = _units()
    for unit_id, cls in sorted(units.items()):
        p = _cs_path_for(unit_id, cls)
        if p is None:
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        cs = sorted(set(_INTENT.findall(text)))
        try:
            src = inspect.getsource(inspect.getmodule(cls))
        except OSError:
            src = ""
        sim = sorted(set(re.findall(r"MoveType\.(\w+)", src)))
        print(f"    {unit_id:<30} C#: {','.join(cs) or '-'}")
        print(f"    {'':<30} sim module: {','.join(sim) or '-'}")


PROBES = {
    "hp": hp,
    "kind": kind,
    "ctor-order": ctor_order,
    "roll-order": roll_order,
    "intents": intents,
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
