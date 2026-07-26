"""Census probes for the power content-audit stream (Tier 1).

Follows `tools/audit/dormancy_probes.py`'s pattern: every number the power
audit records comes out of a committed, re-runnable probe rather than an
agent's reading. Nothing here judges faithfulness -- it extracts declarations
from both trees so the per-unit records can cite reproducible figures.

Usage:
  py tools/audit/power_census.py typing        # sign-aware-typing census
  py tools/audit/power_census.py neg-appliers  # C# sites applying a power < 0
  py tools/audit/power_census.py stack         # StackType vs sim on_stack
  py tools/audit/power_census.py instance      # InstanceType overrides
  py tools/audit/power_census.py visible       # IsVisibleInternal overrides
  py tools/audit/power_census.py multipliers   # sim multiplicative factors
  py tools/audit/power_census.py unregistered  # sim Power classes not in ALL_POWERS
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

sys.path.insert(0, str(_HERE.parent))
from harness import (  # noqa: E402
    DEFAULT_GAME_ROOT,
    _load_name_overrides,
    list_overrides,
    roster,
)

GAME = DEFAULT_GAME_ROOT
POWER_DIR = GAME / "src/Core/Models/Powers"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def _expr(text: str, member: str) -> str | None:
    """The right-hand side of `public [override] <T> <member> => <expr>;`."""
    m = re.search(
        rf"public\s+(?:override\s+|virtual\s+)?[\w<>?\[\].]+\s+{member}\s*=>\s*([^;]+);",
        text,
    )
    return m.group(1).strip() if m else None


def _decl(text: str, member: str) -> str | None:
    """`protected override bool <member> => <expr>;` (IsVisibleInternal)."""
    m = re.search(
        rf"(?:protected|public)\s+override\s+bool\s+{member}\s*=>\s*([^;]+);", text
    )
    return m.group(1).strip() if m else None


def _game_paths() -> dict[str, Path]:
    ov = _load_name_overrides()
    out = {}
    for row in roster("power", GAME):
        uid = row["unit"].split("/", 1)[1]
        out[uid] = GAME / row["game_path"]
    assert ov is not None
    return out


def _sim_classes() -> dict[str, type]:
    from sts2_rl.powers import ALL_POWERS
    return dict(ALL_POWERS)


def _short(expr: str | None, default: str) -> str:
    if expr is None:
        return default
    return expr.split(".")[-1]


def cmd_typing() -> None:
    """Every unit's (Type, StackType, AllowNegative) vs the sim's static attrs.

    `GetTypeForAmount` (PowerModel.cs:460-471) returns Debuff for a
    Counter+AllowNegative power at a negative amount, and Buff for a
    !AllowNegative Debuff at a negative amount.  A unit is SIGN-SENSITIVE when
    either arm can fire.  The sim models neither arm (no get_type_for_amount
    anywhere), so a sign-sensitive unit's power_type is wrong for one sign.
    """
    sims = _sim_classes()
    rows = []
    for uid, gp in sorted(_game_paths().items()):
        t = _read(gp)
        typ = _short(_expr(t, "Type"), "?")
        stack = _short(_expr(t, "StackType"), "?")
        allow = _expr(t, "AllowNegative") or "false"
        allow_b = allow.strip() == "true"
        sim = sims[uid]
        sim_allow = bool(getattr(sim, "allow_negative", False))
        arm1 = stack == "Counter" and allow_b          # Buff-typed -> Debuff at < 0
        arm2 = (not allow_b) and typ == "Debuff"       # Debuff-typed -> Buff at < 0
        rows.append((uid, typ, stack, allow_b, sim.power_type.name, sim_allow,
                     arm1, arm2))
    print(f"{'unit':34} {'cs Type':8} {'StackType':9} {'AllowNeg':8} "
          f"{'sim':6} {'simNeg':6} arms")
    for uid, typ, stack, allow_b, simt, simneg, a1, a2 in rows:
        arms = ",".join(x for x, on in (("counter-neg", a1), ("debuff-neg", a2)) if on)
        flag = "  <-- MISMATCH" if allow_b != simneg else ""
        print(f"{uid:34} {typ:8} {stack:9} {str(allow_b):8} {simt:6} "
              f"{str(simneg):6} {arms}{flag}")
    print()
    print(f"units: {len(rows)}")
    print(f"  Counter+AllowNegative (arm 1, Buff->Debuff at <0): "
          f"{sum(1 for r in rows if r[6])}")
    print(f"  !AllowNegative & Debuff (arm 2, Debuff->Buff at <0): "
          f"{sum(1 for r in rows if r[7])}")
    print(f"  allow_negative disagrees with C#: "
          f"{sum(1 for r in rows if r[3] != r[5])}")


_NEG_APPLY = re.compile(
    r"Apply(?:ToAll)?<(\w+Power)>\s*\([^;]*?"
    r"(-\s*\d+|-\s*\w+|\bSign\b|IsPositive)", re.S)


def cmd_neg_appliers() -> None:
    """C# call sites that apply a power with a syntactically negative amount.

    Bug class 3 needs, per power: does anything apply it negative?  A hit here
    is a candidate, not a proof -- `Sign`/`IsPositive` sites are the
    TemporaryStrength/Dexterity family and are negative only for the
    IsPositive=false subclasses.
    """
    hits: dict[str, set[str]] = {}
    for p in sorted(GAME.glob("src/Core/**/*.cs")):
        t = _read(p)
        for power, amt in _NEG_APPLY.findall(t):
            rel = str(p.relative_to(GAME)).replace("\\", "/")
            hits.setdefault(power, set()).add(f"{rel} [{' '.join(amt.split())}]")
    for power in sorted(hits):
        print(power)
        for site in sorted(hits[power]):
            print(f"    {site}")
    print(f"\npowers applied with a negative/sign amount: {len(hits)}")


def cmd_stack() -> None:
    """Sim `on_stack` no-op overrides vs C#'s unconditional additive stacking.

    `PowerCmd.ModifyAmount` (PowerCmd.cs:236) is `power.Amount + modifiedOffset`
    with NO StackType branch, and `StackType`'s only non-presentation consumers
    are `GetTypeForAmount` (PowerModel.cs:462) and `InvokePowerModified`'s
    VFX split (Creature.cs:628); `PowerStackType.Single` means "Amount is
    hidden in the UI", not "re-application is a no-op".  So the sim's default
    `Power.on_stack` (`self.amount += amount`) is the shape that matches C#,
    and every `on_stack` override that drops the offset is a divergence
    candidate -- listed here with the C# StackType it cites.
    """
    import inspect
    sims = _sim_classes()
    noops = []
    for uid, gp in sorted(_game_paths().items()):
        stack = _short(_expr(_read(gp), "StackType"), "inherited")
        cls = sims[uid]
        if "on_stack" not in vars(cls):
            continue
        body = inspect.getsource(cls.on_stack).strip().splitlines()[-1].strip()
        if body.startswith("pass"):
            noops.append((uid, stack, body))
            print(f"{uid:34} cs StackType={stack:9} sim on_stack -> {body}")
    print(f"\nsim on_stack no-op overrides: {len(noops)}")
    print("C# adds unconditionally at PowerCmd.cs:236, so each of these drops "
          "a re-application's offset.")


def cmd_instance() -> None:
    """PowerInstanceType overrides among the ported units."""
    n = 0
    for uid, gp in sorted(_game_paths().items()):
        it = _expr(_read(gp), "InstanceType")
        if it:
            n += 1
            print(f"{uid:34} {it}")
    print(f"\nported units overriding InstanceType: {n}")


def cmd_visible() -> None:
    """IsVisibleInternal overrides across ALL power .cs files, ported or not."""
    n = 0
    for p in sorted(POWER_DIR.glob("*.cs")):
        v = _decl(_read(p), "IsVisibleInternal")
        if v:
            n += 1
            print(f"{p.name:40} => {v}")
    print(f"\nIsVisibleInternal overrides in {POWER_DIR.name}: {n} "
          f"(of {len(list(POWER_DIR.glob('*.cs')))} files)")


def cmd_multipliers() -> None:
    """Every literal factor a sim power returns from a multiplicative hook.

    hook_dispatch G9's blast radius depends on these being dyadic (exactly
    representable in binary): a non-dyadic factor makes the sim's float product
    differ from C#'s sequential decimal fold.
    """
    from fractions import Fraction

    def dyadic(val) -> bool:
        """Is the DECIMAL literal exactly a binary fraction?

        Not `float.as_integer_ratio()` -- that is a power of two for every
        finite float and would call 0.7 dyadic.  Parse the literal as written.
        """
        fr = Fraction(str(val))
        d = fr.denominator
        return d & (d - 1) == 0

    src = (_REPO / "sts2_rl/powers.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    hooks = {"modify_damage_multiplicative", "modify_block_multiplicative",
             "modify_vulnerable_multiplier"}
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for fn in node.body:
            if not isinstance(fn, ast.FunctionDef) or fn.name not in hooks:
                continue
            computed = any(
                isinstance(s, ast.BinOp) and isinstance(s.op, (ast.Add, ast.Mult,
                                                              ast.Div, ast.Sub))
                for s in ast.walk(fn))
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Constant) and isinstance(
                        sub.value, (int, float)) and not isinstance(sub.value, bool):
                    rows.append((node.name, fn.name, sub.value, sub.lineno,
                                 computed))
    seen: dict = {}
    for cls, fn, val, line, computed in rows:
        seen.setdefault((cls, fn, val), (line, computed))
    nd = []
    for (cls, fn, val), (line, computed) in seen.items():
        ok = dyadic(val)
        if not ok:
            nd.append((cls, fn, val, line))
        print(f"{cls:30} {fn:34} {val!r:8} line {line:5} "
              f"{'dyadic' if ok else 'NON-DYADIC'}"
              f"{'  (factor is computed, not the literal)' if computed else ''}")
    print(f"\nliteral operands: {len(seen)}, non-dyadic: {len(nd)}")
    for c, f, v, line in sorted(nd):
        print(f"    NON-DYADIC {c}.{f} -> {v!r} (powers.py:{line})")


def cmd_unregistered() -> None:
    """Sim Power subclasses carrying an `id` but absent from ALL_POWERS.

    Such a power is invisible to the harness roster (`skeleton power/<id>`
    raises StopIteration) AND absent from full_env's POWER_IDS observation
    vocabulary, which is built from ALL_POWERS.
    """
    import inspect
    from sts2_rl import powers as P
    from sts2_rl.powers import ALL_POWERS, Power
    defined = {
        c.id: c for _, c in inspect.getmembers(P, inspect.isclass)
        if issubclass(c, Power) and c is not Power and getattr(c, "id", None)
    }
    missing = sorted(i for i in defined if i not in ALL_POWERS)
    for i in missing:
        print(f"{i:24} {defined[i].__name__}")
    print(f"\nALL_POWERS: {len(ALL_POWERS)}  classes with id: {len(defined)}  "
          f"unregistered: {len(missing)}")


def cmd_overrides() -> None:
    """Per-unit `public override` list -- the harness's required hook set."""
    for uid, gp in sorted(_game_paths().items()):
        names = list_overrides(_read(gp))
        print(f"{uid:34} {len(names):3}  {' '.join(names)}")


# C# side-scoped turn hooks -> the sim slot that actually matches, resolved
# by following the dispatcher to its CombatManager call site:
#   AbstractModel.AfterSideTurnEnd   <- Hook.AfterTurnEnd        (Hook.cs:1267)
#                                       CombatManager.cs:1256 (enemy) / 1307 (player)
#   AbstractModel.BeforeSideTurnEnd  <- Hook.BeforeTurnEnd       (CombatManager.cs:1179/1251)
#   AbstractModel.AfterSideTurnStart <- Hook.AfterSideTurnStart  (CombatManager.cs:522)
#   AbstractModel.BeforeSideTurnStart<- Hook.BeforeSideTurnStart (CombatManager.cs:458)
# Sim slots (combat.py): on_player_turn_start 5xx pre-draw,
# on_player_turn_started post-draw, on_player_turn_end 654 (BeforeTurnEnd),
# after_player_turn_end 665 (AfterTurnEnd), on_enemy_turn_start 301 and
# on_enemy_turn_end 341 are PER CREATURE, on_enemy_side_end 345 is once.
SIDE_HOOKS = {
    "AfterSideTurnEnd": ("after_player_turn_end", "on_enemy_side_end"),
    "AfterSideTurnEndLate": ("after_player_turn_end", "on_enemy_side_end"),
    "BeforeSideTurnEnd": ("on_player_turn_end", "on_enemy_side_end"),
    "BeforeSideTurnEndVeryEarly": ("on_player_turn_end", "on_enemy_side_end"),
    "AfterSideTurnStart": ("on_player_turn_started", "on_enemy_side_start*"),
    "BeforeSideTurnStart": ("on_player_turn_start", "on_enemy_side_start*"),
}
PER_CREATURE_SLOTS = {"on_enemy_turn_start", "on_enemy_turn_end"}
SIM_TURN_SLOTS = {
    "on_player_turn_start", "on_player_turn_started", "on_player_turn_end",
    "after_player_turn_end", "on_enemy_turn_start", "on_enemy_turn_end",
    "on_enemy_side_end", "on_combat_start", "on_energy_reset",
}


def cmd_slots() -> None:
    """Every unit whose C# hook is SIDE-scoped but whose sim slot is not.

    The sim has exactly one enemy-side-scoped slot, `on_enemy_side_end`
    (combat.py:345, fired once after every enemy has acted).  A power that
    implements a C# side hook with `on_enemy_turn_start`/`on_enemy_turn_end`
    (combat.py:301/341, per creature) therefore fires at a different point in
    the round as soon as the owner shares the enemy side with anything else.
    There is NO enemy-side-START slot at all, so `AfterSideTurnStart` /
    `BeforeSideTurnStart` on an enemy-owned power has no exact counterpart.
    """
    sims = _sim_classes()
    n_side = n_bad = 0
    for uid, gp in sorted(_game_paths().items()):
        overrides = set(list_overrides(_read(gp)))
        side = sorted(overrides & set(SIDE_HOOKS))
        if not side:
            continue
        n_side += 1
        cls = sims[uid]
        impl = sorted(
            name for name in SIM_TURN_SLOTS
            if any(name in vars(b) for b in cls.__mro__[:-1]))
        per_creature = sorted(set(impl) & PER_CREATURE_SLOTS)
        marks = []
        if per_creature:
            marks.append("PER-CREATURE:" + ",".join(per_creature))
        if any(SIDE_HOOKS[h][1].endswith("*") for h in side):
            marks.append("NO-SIM-SIDE-START-SLOT")
        if marks:
            n_bad += 1
        print(f"{uid:30} cs={','.join(side):45} sim={','.join(impl):60} "
              f"{' '.join(marks)}")
    print(f"\nunits overriding a C# side turn hook: {n_side}; "
          f"of those with a per-creature or missing sim slot: {n_bad}")


COMMANDS = {
    "slots": cmd_slots,
    "typing": cmd_typing,
    "neg-appliers": cmd_neg_appliers,
    "stack": cmd_stack,
    "instance": cmd_instance,
    "visible": cmd_visible,
    "multipliers": cmd_multipliers,
    "unregistered": cmd_unregistered,
    "overrides": cmd_overrides,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        print("commands: " + ", ".join(sorted(COMMANDS)))
        return 2
    COMMANDS[argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
