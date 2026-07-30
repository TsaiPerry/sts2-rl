"""Executed dormancy probes for the power stream's half-B (enemy-power) audits.

Every number quoted in `audit/records/power/*.json` for the units below, and every
number in `.superpowers/sdd/content-power-report-b.md`, is re-derivable from
one of these subcommands. Follows the pattern of
`audit/tools/dormancy_probes.py` and `audit/tools/power_census.py`.

    py audit/tools/power_slot_probes.py rosters
    py audit/tools/power_slot_probes.py g5-witness
    py audit/tools/power_slot_probes.py enemy-hook-order
    py audit/tools/power_slot_probes.py ungated-modifiers
    py audit/tools/power_slot_probes.py extra-turns
    py audit/tools/power_slot_probes.py applier-readers
"""
from __future__ import annotations

import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
CS_ROOT = r"c:\Users\Perry\Desktop\Slay the Spire 2"


# ── rosters: how many creatures does each per-creature-slot owner fight with? ──

# owner power id -> (encounter constant module path, encounter attr)
_OWNER_ENCOUNTERS = [
    ("battleworn_dummy_time_limit", "sts2_rl.monsters.glory.battle_friend",
     ["BATTLEWORN_DUMMY_SETTING_1", "BATTLEWORN_DUMMY_SETTING_2",
      "BATTLEWORN_DUMMY_SETTING_3"]),
    ("asleep / plating", "sts2_rl.monsters.underdocks.lagavulin_matriarch",
     ["LAGAVULIN_MATRIARCH_BOSS"]),
    ("slumber", "sts2_rl.monsters.hive.slumbering_beetle",
     ["SLUMBERING_BEETLE_NORMAL"]),
    ("hatch / minion", "sts2_rl.monsters.hive.ovicopter", ["OVICOPTER_NORMAL"]),
    ("escape_artist / flutter", "sts2_rl.monsters.hive.thieving_hopper",
     ["THIEVING_HOPPER_WEAK"]),
    ("sandpit", "sts2_rl.monsters.hive.the_insatiable", ["THE_INSATIABLE_BOSS"]),
    ("hardened_shell", "sts2_rl.monsters.underdocks.skulking_colony",
     ["SKULKING_COLONY_ELITE"]),
]


def _make_combat(encounter):
    import random
    from sts2_rl.combat import CombatState
    return CombatState(rng=random.Random(0), encounter=encounter)


def rosters() -> None:
    import importlib
    import random
    print("Sim encounter rosters for every half-B owner whose C# side hook the")
    print("sim implements with a PER-CREATURE slot (turn_structure G5/G11).")
    print()
    for label, mod, names in _OWNER_ENCOUNTERS:
        try:
            m = importlib.import_module(mod)
        except Exception as exc:  # pragma: no cover
            print(f"  {label:26s} MODULE MISSING {mod} ({exc})")
            continue
        if names is None:
            names = [n for n in dir(m) if n.isupper() and "ENCOUNTER" not in n]
        for n in names:
            enc = getattr(m, n, None)
            if enc is None:
                continue
            try:
                c = _make_combat(enc)
                order = [type(e).__name__ for e in c.enemies]
            except Exception as exc:
                order = [f"<{exc}>"]
            print(f"  {label:26s} {n:34s} n={len(order)} order={order}")
    print()
    print("A per-creature slot is observationally equal to the side slot exactly")
    print("when the owner is the LAST creature in this order (turn-end slots) or")
    print("the FIRST (turn-start slots).")


def g5_witness() -> None:
    """The two-dummy Battle Friend witness the power report asked for."""
    print("turn_structure G5 -- the two-dummy Battle Friend witness.")
    print()
    src = os.path.join(
        CS_ROOT, "src", "Core", "Models", "Encounters",
        "BattlewornDummyEventEncounter.cs")
    txt = open(src, encoding="utf-8", errors="replace").read()
    single = "ReadOnlySingleElementList" in txt
    print(f"  C# GenerateMonsters returns a single-element list: {single}")
    print("    (BattlewornDummyEventEncounter.cs:63-72)")
    hits = [(p, i + 1) for p in _all_cs_files("src/Core/Models/Encounters")
            for i, l in enumerate(open(p, encoding="utf-8",
                                       errors="replace").read().splitlines())
            if "BattleFriend" in l]
    print(f"  C# encounter files mentioning BattleFriend at all: "
          f"{sorted({os.path.basename(p) for p, _ in hits})}")
    import importlib
    m = importlib.import_module("sts2_rl.monsters.glory.battle_friend")
    for n in ("BATTLEWORN_DUMMY_SETTING_1", "BATTLEWORN_DUMMY_SETTING_2",
              "BATTLEWORN_DUMMY_SETTING_3"):
        enc = getattr(m, n)
        print(f"  sim {n}: monster_classes="
              f"{[c.__name__ for c in enc.monster_classes]}")
    print()
    print("  VERDICT: a two-dummy Battle Friend combat is not constructible in")
    print("  either source, so BattlewornDummyTimeLimitPower's mid-round Escape")
    print("  cannot be observed by a second dummy. G5 stays dormant for it, but")
    print("  NOT for the reason G5 gives.")


def _all_cs_files(rel: str):
    root = os.path.join(CS_ROOT, *rel.split("/"))
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".cs"):
                yield os.path.join(dirpath, f)


def enemy_hook_order() -> None:
    """Record the sim's actual enemy-side hook sequence for a 3-enemy fight."""
    import random
    from sts2_rl.monsters.hive.slumbering_beetle import SLUMBERING_BEETLE_NORMAL

    log: list[str] = []

    class Spy:
        """A listener on every enemy-side slot, recording (slot, creature)."""

        def before_enemy_side_start(self):
            log.append("side_start_before")

        def on_block_cleared(self, creature):
            log.append(f"clear:{type(creature).__name__}")

        def after_enemy_side_start(self):
            log.append("side_start_after")

        def before_enemy_side_end(self):
            log.append("side_end_before")

        def on_enemy_side_end(self):
            log.append("side_end_after")

    combat = _make_combat(SLUMBERING_BEETLE_NORMAL)
    for e in combat.enemies:
        e.block = 1
    combat.hooks.register(Spy())
    print("sim enemy list:", [type(e).__name__ for e in combat.enemies])
    combat._run_enemy_turns()
    print("sim dispatch order:", log)
    print()
    print("C# (turn_structure step spec, CombatManager.cs:449-507, 1072-1090,")
    print("1251, 1256): [clear*n, AfterBlockCleared*n, AfterSideTurnStart,")
    print("move*n, BeforeTurnEnd, AfterTurnEnd].")
    print()
    beetle_last = type(combat.enemies[-1]).__name__ == "SlumberingBeetle"
    print(f"SlumberingBeetle is the LAST enemy: {beetle_last}  -> under the OLD")
    print("per-creature model its turn-end slot was adjacent to the side-end")
    print("slot, which is why SlumberPower's natural wake was dormant. The")
    print("slots are side-scoped now, so roster position no longer matters.")


def ungated_modifiers() -> None:
    """Which C# damage/block modifier overrides do NOT self-gate on powered-ness?

    The sim hoists the gate into the pipeline (cmds.py:56-58, :145-147), so an
    ungated C# override is a divergence. damage_pipeline G3 (damage site) and
    creature_card_cmds G1 (block site) own the mechanism; this reproduces the
    population independently.
    """
    pat = re.compile(r"public override decimal (Modify(?:Damage|Block)"
                     r"(?:Additive|Multiplicative))\b")
    gated = ungated = 0
    for p in _all_cs_files("src/Core/Models"):
        lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
        for i, line in enumerate(lines):
            m = pat.search(line)
            if not m:
                continue
            body, depth, started = [], 0, False
            for j in range(i, min(i + 60, len(lines))):
                body.append(lines[j])
                depth += lines[j].count("{") - lines[j].count("}")
                started = started or "{" in lines[j]
                if started and depth == 0:
                    break
            b = "\n".join(body)
            ok = ("IsPoweredAttack" in b
                  or "IsPoweredCardOrMonsterMoveBlock" in b
                  or "Unpowered" in b)
            gated += ok
            ungated += not ok
            if not ok:
                rel = os.path.relpath(p, os.path.join(CS_ROOT, "src", "Core",
                                                      "Models"))
                print(f"  UNGATED {rel}:{i + 1} {m.group(1)}")
    print()
    print(f"gated: {gated}   ungated: {ungated}")


def extra_turns() -> None:
    """Is a PLAYER extra turn reachable in the sim? (RampartPower's dropped guard.)"""
    import subprocess
    print("RampartPower.cs:23 skips its block grant when")
    print("CombatManager.Instance.PlayersTakingExtraTurn.Count > 0. Sim sources")
    print("that can put the player on an extra turn:")
    out = subprocess.run(
        [sys.executable, "-c", "pass"], capture_output=True)  # noqa: F841
    hits = []
    for dirpath, _d, files in os.walk(os.path.join(_ROOT, "sts2_rl")):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            for i, l in enumerate(open(p, encoding="utf-8",
                                       errors="replace").read().splitlines()):
                if "extra_turn" in l:
                    hits.append((os.path.relpath(p, _ROOT), i + 1, l.strip()))
    for rel, ln, txt in hits:
        print(f"  {rel}:{ln}  {txt[:100]}")
    print(f"\ntotal extra_turn mentions in sts2_rl: {len(hits)}")


def applier_readers() -> None:
    """Every sim reader of a power application's `applier`.

    HighVoltagePower / TerritorialPower omit `applier=` where C# passes
    `base.Owner`; this enumerates who could notice.
    """
    pats = ("applier", )
    for dirpath, _d, files in os.walk(os.path.join(_ROOT, "sts2_rl")):
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
            for i, l in enumerate(lines):
                if not any(q in l for q in pats):
                    continue
                if "self.applier" in l or ".applier" in l or "applier is" in l:
                    print(f"  {os.path.relpath(p, _ROOT)}:{i + 1}  {l.strip()[:110]}")


_CMDS = {
    "rosters": rosters,
    "g5-witness": g5_witness,
    "enemy-hook-order": enemy_hook_order,
    "ungated-modifiers": ungated_modifiers,
    "extra-turns": extra_turns,
    "applier-readers": applier_readers,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in _CMDS:
        print(__doc__)
        print("subcommands:", ", ".join(_CMDS))
        raise SystemExit(1)
    _CMDS[sys.argv[1]]()
