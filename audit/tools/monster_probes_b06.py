"""Batch-6 monster-audit probes (spiny_toad … devoted_sculptor).

Every number batch 6's records state as "executed" comes from one of these
probes. Run with `py audit/tools/monster_probes_b06.py <probe>`; `all` runs
them in order.

Probes
------
hash          -- sha256 for every file batch 6 cites with a line number, so the
                 records' `extra_sources` lists are reproducible rather than
                 hand-transcribed.
chain         -- ThievingHopper: prove the ported machine is a pure
                 deterministic chain with NO RandomBranchState on either side.
                 `monster_state_machine` G6's dormancy rests on exactly this.
branch-args   -- every `add_branch` call in this batch's sim modules with the
                 C# `AddBranch` call it transliterates, so a misread
                 cooldown/maxRepeats is visible (seam step 13).
applier       -- enumerate every ported listener that can see PowerCmd.apply's
                 `applier` argument, and show that none of them can distinguish
                 `None` from the applying monster today.
wither        -- enumerate every sim site that constructs a WitherCard, the
                 dormancy argument for Aeonglass.AfterCardGeneratedForCombat.
streams       -- the RNG stream each of this batch's random draws uses.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_GAME = Path(r"C:\Users\Perry\Desktop\Slay the Spire 2")

# Files batch 6 cites with a line number, beyond each record's own two.
CITED_GAME = [
    "src/Core/Commands/CardPileCmd.cs",
    "src/Core/Commands/PowerCmd.cs",
    "src/Core/Combat/CombatState.cs",
    "src/Core/Entities/Cards/CardRarity.cs",
    "src/Core/Models/MonsterModel.cs",
    "src/Core/Models/Powers/BurrowedPower.cs",
    "src/Core/Models/Powers/DoomPower.cs",
    "src/Core/Models/Powers/IllusionPower.cs",
    "src/Core/Models/Powers/StockPower.cs",
    "src/Core/Models/Powers/WitheringPresencePower.cs",
    "src/Core/Models/Monsters/BattleFriendV1.cs",
    "src/Core/Models/Monsters/BattleFriendV2.cs",
    "src/Core/Models/Monsters/BattleFriendV3.cs",
    "src/Core/Models/Monsters/Parafright.cs",
    "src/Core/Models/Monsters/TheObscura.cs",
    "src/Core/Entities/Players/PlayerCombatState.cs",
]
CITED_SIM = [
    "sts2_rl/cmds.py",
    "sts2_rl/powers.py",
    "sts2_rl/combat.py",
    "sts2_rl/combat_rng.py",
    "sts2_rl/rooms.py",
    "sts2_rl/player.py",
    "sts2_rl/cards/base.py",
    "sts2_rl/enchantments.py",
    "sts2_rl/monsters/base.py",
    "sts2_rl/monsters/state_machine.py",
    "sts2_rl/events/__init__.py",
    "sts2_rl/monsters/hive/the_obscura.py",
    "sts2_rl/monsters/glory/battle_friend.py",
]

SIM_MODULES = {
    "spiny_toad": "sts2_rl/monsters/hive/spiny_toad.py",
    "the_insatiable": "sts2_rl/monsters/hive/the_insatiable.py",
    "the_obscura/parafright": "sts2_rl/monsters/hive/the_obscura.py",
    "thieving_hopper": "sts2_rl/monsters/hive/thieving_hopper.py",
    "tunneler": "sts2_rl/monsters/hive/tunneler.py",
    "aeonglass": "sts2_rl/monsters/glory/aeonglass.py",
    "axebot": "sts2_rl/monsters/glory/axebot.py",
    "battle_friend": "sts2_rl/monsters/glory/battle_friend.py",
    "devoted_sculptor": "sts2_rl/monsters/glory/devoted_sculptor.py",
}
CS_MODELS = {
    "spiny_toad": "SpinyToad.cs",
    "the_insatiable": "TheInsatiable.cs",
    "the_obscura/parafright": "TheObscura.cs",
    "thieving_hopper": "ThievingHopper.cs",
    "tunneler": "Tunneler.cs",
    "aeonglass": "Aeonglass.cs",
    "axebot": "Axebot.cs",
    "battle_friend": "BattleFriendV1.cs",
    "devoted_sculptor": "DevotedSculptor.cs",
}


def _sha(p: Path) -> str:
    """Same normalization as harness.file_sha256 (LF-normalized text), so the
    numbers this prints are the ones the records must carry."""
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def probe_hash() -> None:
    print("===== hash =====")
    for rel in CITED_GAME:
        p = _GAME / rel
        print(f"  game {rel}\n       {_sha(p) if p.is_file() else 'MISSING'}")
    for rel in CITED_SIM:
        p = _REPO / rel
        print(f"  sim  {rel}\n       {_sha(p) if p.is_file() else 'MISSING'}")


def probe_chain() -> None:
    print("===== chain (ThievingHopper: G6's dormancy premise) =====")
    cs = _read(_GAME / "src/Core/Models/Monsters/ThievingHopper.cs")
    sim = _read(_REPO / "sts2_rl/monsters/hive/thieving_hopper.py")
    print(f"  C#  RandomBranchState occurrences: "
          f"{len(re.findall(r'RandomBranchState', cs))}")
    print(f"  C#  ConditionalBranchState occurrences: "
          f"{len(re.findall(r'ConditionalBranchState', cs))}")
    print(f"  C#  AddBranch(state,...) call sites: "
          f"{len(re.findall(r'(?<!Animator)\.AddBranch\((?!\")', cs))}")
    print(f"  sim RandomBranchState occurrences: "
          f"{len(re.findall(r'RandomBranchState', sim))}")
    print(f"  sim add_branch call sites: {len(re.findall(r'add_branch', sim))}")
    print("  C# FollowUpState assignments:")
    for m in re.finditer(r"(\w+)\.FollowUpState = (\w+);", cs):
        print(f"    {m.group(1)} -> {m.group(2)}")
    print("  sim follow_up assignments:")
    for m in re.finditer(r"(\w+)\.follow_up = (\w+)$", sim, re.M):
        print(f"    {m.group(1)} -> {m.group(2)}")


def probe_branch_args() -> None:
    print("===== branch-args (seam step 13) =====")
    for name, rel in SIM_MODULES.items():
        cs = _read(_GAME / "src/Core/Models/Monsters" / CS_MODELS[name])
        sim = _read(_REPO / rel)
        cs_calls = re.findall(r"\.AddBranch\((?!\")[^;]*\);", cs)
        sim_calls = re.findall(r"\.add_branch\([^)]*\)", sim)
        if not cs_calls and not sim_calls:
            print(f"  {name:24s} no branch state on either side")
            continue
        print(f"  {name}")
        for c in cs_calls:
            print(f"    C#  {' '.join(c.split())}")
        for c in sim_calls:
            print(f"    sim {' '.join(c.split())}")


def probe_applier() -> None:
    print("===== applier (is PowerCmd.apply's applier arg observable?) =====")
    hits = []
    for p in sorted(_REPO.joinpath("sts2_rl").rglob("*.py")):
        txt = _read(p)
        for i, line in enumerate(txt.splitlines(), 1):
            if re.search(r"def (modify_power_amount|on_power_applied|"
                         r"on_power_amount_changed)\b", line):
                hits.append((p.relative_to(_REPO).as_posix(), i, line.strip()))
    print(f"  listener definitions (excluding hooks.py dispatchers): ")
    for rel, ln, line in hits:
        if rel.endswith("hooks.py"):
            continue
        print(f"    {rel}:{ln}  {line}")
    print("  guards those listeners apply to `applier`:")
    for pat in (r"applier is not self\.owner", r"applier is self\.owner",
                r"applier is self\.player", r"applier is not self\.player"):
        for p in sorted(_REPO.joinpath("sts2_rl").rglob("*.py")):
            txt = _read(p)
            for i, line in enumerate(txt.splitlines(), 1):
                if re.search(pat, line):
                    print(f"    {p.relative_to(_REPO).as_posix()}:{i}  "
                          f"{line.strip()}")


def probe_wither() -> None:
    print("===== wither (Aeonglass.AfterCardGeneratedForCombat dormancy) =====")
    print("  sim sites constructing a WitherCard:")
    for p in sorted(_REPO.joinpath("sts2_rl").rglob("*.py")):
        txt = _read(p)
        for i, line in enumerate(txt.splitlines(), 1):
            if "WitherCard(" in line:
                print(f"    {p.relative_to(_REPO).as_posix()}:{i}  "
                      f"{line.strip()}")
    print("  C# sites naming Wither outside the card itself:")
    for rel in ("src/Core/Models/Monsters/Aeonglass.cs",
                "src/Core/Models/Powers/WitheringPresencePower.cs",
                "src/Core/Models/CardPools/StatusCardPool.cs"):
        txt = _read(_GAME / rel)
        for i, line in enumerate(txt.splitlines(), 1):
            if "Wither" in line and "WitheringPresence" not in line:
                print(f"    {rel}:{i}  {line.strip()}")


def probe_streams() -> None:
    print("===== streams =====")
    print("  sim CombatRng accessors:")
    txt = _read(_REPO / "sts2_rl/combat_rng.py")
    for i, line in enumerate(txt.splitlines(), 1):
        if "property(lambda" in line or ":" in line and '"' in line:
            if "=" in line and ("property" in line or line.strip().endswith(",")):
                print(f"    combat_rng.py:{i}  {line.strip()}")
    print("  random draws made by batch-6 monster ports:")
    for name, rel in SIM_MODULES.items():
        txt = _read(_REPO / rel)
        for i, line in enumerate(txt.splitlines(), 1):
            if re.search(r"_rng\.|combat_rng\.|\.choice\(|\.randrange\(", line):
                print(f"    {rel}:{i}  {line.strip()}")


PROBES = {
    "hash": probe_hash,
    "chain": probe_chain,
    "branch-args": probe_branch_args,
    "applier": probe_applier,
    "wither": probe_wither,
    "streams": probe_streams,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in PROBES and argv[1] != "all":
        print(__doc__)
        print("probes: " + ", ".join(PROBES) + ", all")
        return 2
    names = list(PROBES) if argv[1] == "all" else [argv[1]]
    for n in names:
        PROBES[n]()
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
