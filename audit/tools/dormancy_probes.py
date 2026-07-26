"""Reproducible dormancy probes for the seam audits.

Every "executed evidence" number a seam record states about *which sim or game
classes implement a hook* is produced here, so a later auditor can re-derive it
instead of trusting a throwaway script. Each probe prints its own counts.

  py audit/tools/dormancy_probes.py                 # every probe
  py audit/tools/dormancy_probes.py card-hooks      # one probe

Probes (seam/hook_dispatch unless noted):
  card-hooks        G1, N5   which HookSystem hooks sim Card classes implement
  monster-hooks     G5       which HookSystem hooks sim Monster classes implement
  affliction-hooks  G6       ... and sim Affliction classes
  cs-monster-hooks  G5       C# MonsterModel subclasses overriding any hook
  cs-affliction-hooks G6     C# AfflictionModel subclasses overriding any hook
  cs-badge-hooks    N4       C# BadgeModel subclasses overriding any hook
  cs-potion-run-hooks step 15 C# PotionModel subclasses overriding a RUN hook
  cs-running-value  step 31  C# additive/multiplicative overrides that READ the
                             running value the dispatcher threads through them
  sim-running-value step 31  the same question on the sim side
  hook-buckets      step 21  Hook.cs dispatcher census + guard/run/bypass split
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import pkgutil
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit.tools.harness import DEFAULT_GAME_ROOT  # noqa: E402

HOOK_CS = "src/Core/Hooks/Hook.cs"
ABSTRACT_MODEL_CS = "src/Core/Models/AbstractModel.cs"


# ── helpers ──────────────────────────────────────────────────────────────
def hook_names() -> set[str]:
    """Every dispatcher HookSystem defines (the names a listener may implement)."""
    from sts2_rl.hooks import HookSystem
    return {n for n, v in vars(HookSystem).items()
            if callable(v) and not n.startswith("_")
            and n not in ("register", "unregister")}


def _import_all(package: str) -> None:
    pkg = importlib.import_module(package)
    for mod in pkgutil.walk_packages(pkg.__path__, package + "."):
        try:
            importlib.import_module(mod.name)
        except Exception as exc:                      # pragma: no cover
            print(f"  ! import {mod.name}: {exc}")


def _subclasses(root: type) -> list[type]:
    out, stack = [], [root]
    while stack:
        c = stack.pop()
        for s in c.__subclasses__():
            if s not in out:
                out.append(s)
                stack.append(s)
    return out


def _implemented(cls: type, names: set[str]) -> dict[str, str]:
    """MRO-aware: which hook names this class (or a base below the root)
    actually defines, and in which class."""
    found = {}
    for name in names:
        for base in cls.__mro__:
            if name in vars(base):
                found[name] = base.__name__
                break
    return found


def _cs_bodies(path: Path, pattern: re.Pattern) -> list[tuple[int, str, str]]:
    """(line, capture, brace-matched body) for each regex hit in a C# file."""
    txt = path.read_text(encoding="utf-8-sig", errors="replace")
    out = []
    for m in pattern.finditer(txt):
        i = txt.find("{", m.end())
        body = ""
        if i >= 0:
            depth, j = 0, i
            while j < len(txt):
                if txt[j] == "{":
                    depth += 1
                elif txt[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            body = txt[i:j + 1]
        out.append((txt[:m.start()].count("\n") + 1, m.group(0), body))
    return out


def _abstract_model_hook_names(root: Path) -> set[str]:
    """Every virtual hook AbstractModel declares — the set a model may override."""
    txt = (root / ABSTRACT_MODEL_CS).read_text(encoding="utf-8-sig",
                                               errors="replace")
    return set(re.findall(r"public virtual [\w<>\?\[\],\.\s]+?\s(\w+)\s*\(", txt))


# ── probes ───────────────────────────────────────────────────────────────
def card_hooks() -> None:
    """G1 / N5: MRO-aware scan of the whole _CARD_CLASSES registry."""
    _import_all("sts2_rl.cards")
    from sts2_rl.cards.base import _CARD_CLASSES, Card
    names = hook_names()
    hits: dict[str, list[str]] = {}
    for cid, cls in _CARD_CLASSES.items():
        for hook, owner in _implemented(cls, names).items():
            if owner == "Card":          # the base class itself, not a card hook
                continue
            hits.setdefault(hook, []).append(f"{cid} ({owner})")
    print(f"card classes in _CARD_CLASSES: {len(_CARD_CLASSES)}")
    print(f"HookSystem hook names: {len(names)}")
    print(f"hooks implemented by at least one card class: {len(hits)}")
    for hook in sorted(hits):
        impls = sorted(set(hits[hook]))
        print(f"  {hook}: {len(impls)} -> {impls}")
    assert Card is not None


def monster_hooks() -> None:
    """G5: does any sim Monster subclass define a HookSystem hook name?"""
    _import_all("sts2_rl.monsters")
    from sts2_rl.monsters.base import Monster
    names = hook_names()
    subs = _subclasses(Monster)
    hits: dict[str, list[str]] = {}
    for cls in subs:
        for hook, owner in _implemented(cls, names).items():
            if owner in ("Monster",):
                continue
            hits.setdefault(hook, []).append(f"{cls.__name__} ({owner})")
    print(f"sim Monster subclasses: {len(subs)}")
    print(f"subclasses defining any HookSystem hook name: "
          f"{len({x for v in hits.values() for x in v})}")
    for hook in sorted(hits):
        print(f"  {hook}: {sorted(set(hits[hook]))}")
    # Monster.__init__ stores _hooks but never registers:
    src = inspect.getsource(Monster)
    print(f"'hooks.register' inside sim Monster base: "
          f"{'hooks.register' in src}")


def affliction_hooks() -> None:
    """G6: does any sim Affliction subclass define a HookSystem hook name?"""
    import sts2_rl.afflictions as aff
    names = hook_names()
    subs = _subclasses(aff.Affliction)
    hits = {}
    for cls in subs:
        for hook, owner in _implemented(cls, names).items():
            if owner == "Affliction":
                continue
            hits.setdefault(hook, []).append(f"{cls.__name__} ({owner})")
    print(f"sim Affliction subclasses: {len(subs)}")
    print(f"hooks implemented: {hits}")


def _cs_model_hook_overrides(subdir: str) -> tuple[int, int, dict]:
    root = DEFAULT_GAME_ROOT
    names = _abstract_model_hook_names(root)
    pat = re.compile(r"public override\s+[\w<>\?\[\],\.\s]+?\s(\w+)\s*\(")
    files = sorted((root / subdir).rglob("*.cs"))
    hits: dict[str, list[str]] = {}
    for f in files:
        txt = f.read_text(encoding="utf-8-sig", errors="replace")
        for m in pat.finditer(txt):
            if m.group(1) in names:
                hits.setdefault(f.relative_to(root).as_posix(), []).append(
                    m.group(1))
    return len(files), len(hits), hits


def cs_monster_hooks() -> None:
    """G5: how many C# monster models override at least one AbstractModel hook?"""
    n, k, hits = _cs_model_hook_overrides("src/Core/Models/Monsters")
    print(f"C# files under src/Core/Models/Monsters: {n}")
    print(f"...overriding at least one AbstractModel hook: {k}")
    for f in sorted(hits):
        print(f"  {f}: {sorted(set(hits[f]))}")


def cs_affliction_hooks() -> None:
    """G6: which C# afflictions override an AbstractModel hook?"""
    n, k, hits = _cs_model_hook_overrides("src/Core/Models/Afflictions")
    print(f"C# files under src/Core/Models/Afflictions: {n}")
    print(f"...overriding at least one AbstractModel hook: {k}")
    for f in sorted(hits):
        print(f"  {f}: {sorted(set(hits[f]))}")


def cs_badge_hooks() -> None:
    """N4: no badge overrides a Should*/Modify*/TryModify* hook."""
    n, k, hits = _cs_model_hook_overrides("src/Core/Models/Badges")
    gating = {f: [h for h in v if h.startswith(("Should", "Modify",
                                                "TryModify"))]
              for f, v in hits.items()}
    gating = {f: v for f, v in gating.items() if v}
    print(f"C# files under src/Core/Models/Badges: {n}")
    print(f"...overriding any AbstractModel hook: {k}")
    print(f"...overriding a Should*/Modify*/TryModify* hook: {len(gating)}")
    for f in sorted(hits):
        print(f"  {f}: {sorted(set(hits[f]))}")


def cs_potion_run_hooks() -> None:
    """step 15: RunState.IterateHookListeners walks Potions too. Does any
    PotionModel override a RUN-level hook (one dispatched off
    runState.IterateHookListeners)?"""
    root = DEFAULT_GAME_ROOT
    hook_src = (root / HOOK_CS).read_text(encoding="utf-8-sig", errors="replace")
    # A genuinely RUN-scoped dispatcher iterates with NO combat state at all
    # (`runState.IterateHookListeners(null)`); the ones that pass a combatState
    # through (ShouldDie, AfterPreventingDeath, ModifyDamage...) delegate to the
    # combat list whenever a combat is running, so they are combat hooks that
    # merely enter through the run iterator.
    run_only = set(re.findall(
        r"runState\.IterateHookListeners\(null\)\)\s*\{[^}]*?\bitem\d?\.(\w+)\(",
        hook_src, re.S))
    thru_combat = set(re.findall(
        r"runState\.IterateHookListeners\(combatState\)\)\s*\{[^}]*?\bitem\d?\.(\w+)\(",
        hook_src, re.S))
    n, k, hits = _cs_model_hook_overrides("src/Core/Models/Potions")
    print(f"hooks dispatched off runState.IterateHookListeners(null)      "
          f"(run-scoped): {len(run_only)}")
    print(f"hooks dispatched off runState.IterateHookListeners(combatState) "
          f"(combat): {len(thru_combat)}")
    print(f"C# files under src/Core/Models/Potions: {n}")
    print(f"...overriding any AbstractModel hook: {k}")
    for f in sorted(hits):
        overridden = sorted(set(hits[f]))
        print(f"  {f}: {overridden}")
        for h in overridden:
            kind = ("RUN-SCOPED" if h in run_only else
                    "combat (via run iterator)" if h in thru_combat else
                    "combat-only")
            print(f"      {h}: {kind}")
    total_run = sum(1 for v in hits.values() for h in set(v) if h in run_only)
    print(f"potion overrides that are RUN-SCOPED hooks: {total_run}")


_ADD_MUL = ("ModifyDamageAdditive", "ModifyDamageMultiplicative",
            "ModifyBlockAdditive", "ModifyBlockMultiplicative")


def cs_running_value() -> None:
    """step 31 / damage_pipeline N3: do any C# additive/multiplicative
    overrides READ the running value the dispatcher hands them?"""
    root = DEFAULT_GAME_ROOT
    pat = re.compile(r"override\s+decimal\s+(" + "|".join(_ADD_MUL) +
                     r")\s*\(([^)]*)\)", re.S)
    total, readers = 0, []
    for p in (root / "src").rglob("*.cs"):
        for line, cap, body in _cs_bodies(p, pat):
            m = pat.search(cap)
            parts = [x.strip() for x in m.group(2).split(",")]
            pname = parts[1].split()[-1] if len(parts) > 1 else None
            total += 1
            if pname and re.search(r"\b" + re.escape(pname) + r"\b", body):
                readers.append((p.relative_to(root).as_posix(), line,
                                m.group(1), pname))
    print(f"C# overrides of {_ADD_MUL}: {total}")
    print(f"...that read the running value: {len(readers)}")
    for r in readers:
        print("  ", r)
    # the enchantment pre-step (Hook.cs:1314-1319, 1490-1499) has the same shape
    epat = re.compile(r"override\s+decimal\s+(Enchant(?:Damage|Block)"
                      r"(?:Additive|Multiplicative))\s*\(([^)]*)\)", re.S)
    etotal, ereaders = 0, []
    for p in (root / "src").rglob("*.cs"):
        for line, cap, body in _cs_bodies(p, epat):
            m = epat.search(cap)
            parts = [x.strip() for x in m.group(2).split(",")]
            pname = parts[0].split()[-1] if parts else None
            etotal += 1
            if pname and re.search(r"\b" + re.escape(pname) + r"\b", body):
                ereaders.append((p.relative_to(root).as_posix(), line))
    print(f"C# Enchant*Additive/Multiplicative overrides: {etotal}, "
          f"reading the running value: {len(ereaders)}")


def sim_running_value() -> None:
    """step 31 / damage_pipeline N3: the same question on the sim side."""
    import ast
    hooks = {"modify_damage_additive", "modify_damage_multiplicative",
             "modify_block_additive", "modify_block_multiplicative"}
    impls, readers = [], []
    for p in sorted((_REPO / "sts2_rl").rglob("*.py")):
        rel = p.relative_to(_REPO).as_posix()
        if rel == "sts2_rl/hooks.py":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name not in hooks:
                continue
            args = [a.arg for a in node.args.args]
            val = args[2] if len(args) > 2 else None
            impls.append((rel, node.lineno, node.name))
            if val and any(isinstance(n, ast.Name) and n.id == val
                           and isinstance(n.ctx, ast.Load)
                           for n in ast.walk(node)):
                readers.append((rel, node.lineno, node.name))
    print(f"sim implementations of the four hooks: {len(impls)}")
    print(f"...that read the dispatcher-supplied value: {len(readers)}")
    for r in readers:
        print("  ", r)


def hook_buckets() -> None:
    """step 21 / the boundary section: the Hook.cs dispatcher census."""
    root = DEFAULT_GAME_ROOT
    src = (root / HOOK_CS).read_text(encoding="utf-8-sig", errors="replace")
    lines = src.splitlines()
    # The lenient regex matches all 147. The stricter one used in the original
    # audit ("return type is a run of word/generic characters") matches only
    # 146 -- the miss is the one dispatcher whose return type is a TUPLE.
    name_re = re.compile(r"^\tpublic static\s+(?:async\s+)?.*?\s(\w+)\s*\(")
    strict_re = re.compile(
        r"^\tpublic static\s+(?:async\s+)?[\w<>\?\[\],\.\s]+?\s(\w+)\s*\(")
    decls, unparsed, strict_miss = [], [], []
    for i, l in enumerate(lines):
        if not l.startswith("\tpublic static"):
            continue
        m = name_re.match(l)
        if m:
            decls.append((i + 1, m.group(1)))
        else:
            unparsed.append((i + 1, l.strip()))
        if not strict_re.match(l):
            strict_miss.append((i + 1, l.strip()))
    print(f"'^\\tpublic static' declarations: {len(decls) + len(unparsed)}")
    print(f"lenient name-capturing regex matches: {len(decls)}")
    print(f"strict  name-capturing regex matches: "
          f"{len(decls) + len(unparsed) - len(strict_miss)}"
          f"  (misses {len(strict_miss)})")
    for ln, l in strict_miss:
        print(f"  STRICT-REGEX MISS line {ln}: {l[:170]}")
    for ln, l in unparsed:
        print(f"  NOT MATCHED line {ln}: {l[:150]}")
    priv = [(i + 1, l.strip()) for i, l in enumerate(lines)
            if l.startswith("\tprivate static")]
    print(f"private static helpers: {len(priv)}")
    for ln, l in priv:
        print(f"  line {ln}: {l.split('(')[0]}")

    def body_of(start):
        off = sum(len(x) + 1 for x in lines[:start - 1])
        i = src.find("{", off)
        depth, j = 0, i
        while j < len(src):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    return src[i:j + 1]
            j += 1
        return src[i:]

    buckets: dict[str, list] = {"guarded": [], "runside": [], "bypass": [],
                                "unclassified": []}
    for ln, name in decls + [(ln, "<UNPARSED>") for ln, _ in unparsed]:
        b = body_of(ln)
        guarded = "IterateCombatHookListeners(" in b
        runside = bool(re.search(r"\brunState\.IterateHookListeners\(", b))
        bypass = any(m.group(1) != "runState" for m in
                     re.finditer(r"(\w+)\.IterateHookListeners\(", b))
        keys = [k for k, v in (("guarded", guarded), ("runside", runside),
                               ("bypass", bypass)) if v]
        buckets[keys[0] if len(keys) == 1 else "unclassified"].append(
            (name, ln, keys))
    for k, v in buckets.items():
        print(f"{k}: {len(v)}")
        if k in ("bypass", "unclassified"):
            for x in v:
                print(f"   {x[0]} ({x[1]}) {x[2]}")


PROBES = {
    "card-hooks": card_hooks,
    "monster-hooks": monster_hooks,
    "affliction-hooks": affliction_hooks,
    "cs-monster-hooks": cs_monster_hooks,
    "cs-affliction-hooks": cs_affliction_hooks,
    "cs-badge-hooks": cs_badge_hooks,
    "cs-potion-run-hooks": cs_potion_run_hooks,
    "cs-running-value": cs_running_value,
    "sim-running-value": sim_running_value,
    "hook-buckets": hook_buckets,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    for name in ([args.probe] if args.probe else sorted(PROBES)):
        print(f"\n===== {name} =====")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
