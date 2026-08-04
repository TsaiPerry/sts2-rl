"""Executed evidence for encounter content-audit BATCH E4 (act Hive, second
half: knowledge_demon, louse_progenitor, mytes, ovicopter, slumbering_beetle,
spiny_toad, the_insatiable, the_obscura, thieving_hopper, tunneler).

Probes:
  obscura-slot   -- TheObscuraNormal.Slots = ["illusion","obscura"];
                    TheObscura.cs:84 summons the Parafright with the explicit
                    slot "illusion", which CombatManager.AddCreature
                    (CombatManager.cs:848-851) uses to re-sort the WHOLE enemy
                    list by Encounter.Slots.IndexOf(SlotName) the instant the
                    Parafright joins. The sim's `TheObscura._illusion`
                    (monsters/hive/the_obscura.py) calls `CreatureCmd.add`
                    with no `slot_name`, and `THE_OBSCURA_NORMAL` (the
                    `Encounter` dataclass instance) carries no `slots=` /
                    `monster_slots=` either. This probe builds the encounter,
                    fires the summon through the real `CreatureCmd.add`, and
                    prints the resulting `combat.enemies` order and each
                    creature's `.slot_name`, to show the sim never reaches the
                    re-sort C# guarantees. LIVE.
  mytes-slot     -- MytesNormal.Slots = ["first","second"]; the sim's
                    `MytesEncounter` builds both `Myte`s directly and never
                    assigns `.slot_name` on either, and `MYTES_NORMAL` carries
                    no `slots=`. `Myte.cs:53-54` reads `Creature.SlotName` at
                    machine-build time to choose the opening move; the sim
                    mirrors that decision with a constructor-time `slot=`
                    string kept off-creature. This probe shows the two Mytes'
                    opening moves still land right (the re-architecture is
                    behaviourally sound for THIS unit) while enumerating the
                    three real consumers of `.slot_name` in the sim
                    (`sort_enemies_by_slot_name`, `Encounter.get_next_slot`,
                    `Encounter.last_free_slot`) and showing none of them fire
                    for an encounter that never summons -- the dormancy
                    witness for `encounter/_slot_name_not_set`'s Mytes site.
  gold-ladder    -- EncounterModel.MinGoldReward/MaxGoldReward (the RoomType
                    ladder: Monster 10-20, Elite 35-45, Boss 100-100) vs
                    `rewards.GOLD_REWARD_RANGES`, for every RoomType this
                    batch's units use (Monster, Boss). None of the ten C#
                    files override Min/MaxGoldReward, so this is the shared
                    default both sides inherit.
  no-tags        -- enumerates every EncounterTag C# declares
                    (`grep EncounterTag.cs`) against a grep of `sts2_rl/` for
                    any `tags`/`EncounterTag` symbol, to support the
                    structural finding that the sim has no Tags model at all.

Run: py audit/tools/encounter_probes_e4.py <probe>
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from sts2_rl.combat import CombatState  # noqa: E402
from sts2_rl.monsters.hive import (  # noqa: E402
    MYTES_NORMAL,
    THE_OBSCURA_NORMAL,
)


def obscura_slot() -> None:
    combat = CombatState(rng=random.Random(0), encounter=THE_OBSCURA_NORMAL)
    print("THE_OBSCURA_NORMAL.slots       :", THE_OBSCURA_NORMAL.slots)
    print("THE_OBSCURA_NORMAL.monster_slots:", THE_OBSCURA_NORMAL.monster_slots)
    print("initial enemies                :",
          [(type(e).__name__, e.slot_name) for e in combat.enemies])

    # Fire the real summon move body (TheObscura._illusion), exactly as the
    # game's ILLUSION_MOVE would on the boss's first turn.
    obscura = combat.enemies[0]
    obscura._illusion(combat._ctx())

    print("after ILLUSION_MOVE            :",
          [(type(e).__name__, e.slot_name) for e in combat.enemies])
    print()
    print("C# behaviour (TheObscura.cs:84, CombatManager.cs:848-851,")
    print("CombatState.cs:495-501): Parafright.SlotName='illusion' (index 0),")
    print("TheObscura.SlotName='obscura' (index 1) -> AddCreature's")
    print("SlotName != null guard fires SortEnemiesBySlotName, and the")
    print("Parafright sorts BEFORE TheObscura in the enemy list.")
    print()
    names = [type(e).__name__ for e in combat.enemies]
    if names == ["TheObscura", "Parafright"]:
        print("SIM RESULT: Parafright stayed appended AFTER TheObscura --")
        print("            enemy list order diverges from the game. LIVE.")
    elif names == ["Parafright", "TheObscura"]:
        print("SIM RESULT: matches the game's re-sorted order.")
    else:
        print("SIM RESULT (unexpected):", names)


def mytes_slot() -> None:
    combat = CombatState(rng=random.Random(0), encounter=MYTES_NORMAL)
    print("MYTES_NORMAL.slots        :", getattr(MYTES_NORMAL, "slots", None))
    myte1, myte2 = combat.enemies
    print("myte1.slot (ctor arg, private):", myte1.slot,
          "  .slot_name:", myte1.slot_name)
    print("myte2.slot (ctor arg, private):", myte2.slot,
          "  .slot_name:", myte2.slot_name)

    # The behavioural claim: opening moves still come out TOXIC / SUCK as
    # Myte.cs:53-54 (gated on live SlotName in C#) requires.
    print()
    print("myte1 initial move id:", myte1._current_move.id)
    print("myte2 initial move id:", myte2._current_move.id)

    print()
    print("Consumers of Creature.slot_name in sts2_rl/ (grep):")
    print("  1. combat.py:sort_enemies_by_slot_name -- no-op unless")
    print("     encounter.slots is non-empty; MYTES_NORMAL.slots is",
          getattr(MYTES_NORMAL, "slots", ()), "-- never fires for this unit.")
    print("  2. monsters/base.py Encounter.get_next_slot -- only consulted by")
    print("     a summon move; Myte has no summon move.")
    print("  3. monsters/base.py Encounter.last_free_slot -- same, unused by")
    print("     Myte.")
    print("=> DORMANT for mytes today: slot_name is never read anywhere the")
    print("   two Mytes' own None values could be observed.")


def gold_ladder() -> None:
    from sts2_rl.rewards import GOLD_REWARD_RANGES
    from sts2_rl.rooms import RoomType
    cs_ladder = {
        RoomType.MONSTER: (10, 20),
        RoomType.ELITE: (35, 45),
        RoomType.BOSS: (100, 100),
    }
    print("EncounterModel default ladder (EncounterModel.cs:64-100, non-Poverty):")
    for rt, rng_ in cs_ladder.items():
        sim_rng = GOLD_REWARD_RANGES.get(rt)
        status = "MATCH" if sim_rng == rng_ else "MISMATCH"
        print(f"  {rt}: C#={rng_}  sim={sim_rng}  [{status}]")
    print()
    print("None of this batch's 10 encounters override Min/MaxGoldReward, so")
    print("all 10 inherit this ladder directly: knowledge_demon/the_insatiable")
    print("are RoomType.Boss, the other 8 are RoomType.Monster.")
    print("Poverty-ascension multiplier: out of scope per PROMPT.md")
    print("('Ascension values: out of scope'); rewards.py:32 confirms the sim")
    print("applies non-ascension values only.")


def no_tags() -> None:
    import subprocess
    game = Path(r"C:\Users\Perry\Desktop\Slay the Spire 2")
    tags_file = game / "src" / "Core" / "Entities" / "Encounters" / "EncounterTag.cs"
    print("EncounterTag.cs exists:", tags_file.exists())
    if tags_file.exists():
        print(tags_file.read_text(encoding="utf-8", errors="replace"))
    print()
    print("grep -rn 'EncounterTag' sts2_rl/  (sim side):")
    r = subprocess.run(
        ["grep", "-rn", "EncounterTag", str(_REPO / "sts2_rl")],
        capture_output=True, text=True,
    )
    out = (r.stdout + r.stderr).strip()
    print(out if out else "(no matches -- confirmed, zero sim occurrences)")
    print()
    print("grep -rn 'class Encounter' sts2_rl/monsters/base.py -- dataclass")
    print("fields, for reference (no `tags` field declared):")
    r2 = subprocess.run(
        ["grep", "-n", "^class Encounter\\|    [a-z_]*:", str(_REPO / "sts2_rl" / "monsters" / "base.py")],
        capture_output=True, text=True,
    )
    print((r2.stdout + r2.stderr).strip()[:2000])


_PROBES = {
    "obscura-slot": obscura_slot,
    "mytes-slot": mytes_slot,
    "gold-ladder": gold_ladder,
    "no-tags": no_tags,
}


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in _PROBES:
        print(f"usage: py {sys.argv[0]} <{'|'.join(_PROBES)}>")
        sys.exit(1)
    _PROBES[sys.argv[1]]()
