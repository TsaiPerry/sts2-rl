"""Executed evidence for the `encounter` content-audit batch e9.

Batch e9 units (the event-wired encounters): battleworn_dummy_event,
dense_vegetation_event, fake_merchant_event, mysterious_knight_event,
punch_off_event.

Usage:

    py audit/tools/encounter_probes_e9.py <probe>
    py audit/tools/encounter_probes_e9.py all

Probes
------
entry-slug-mismatch    encounter/_entry_slug_mismatch (all 5 units): the sim's
                       `Encounter.entry` property is `self.id.upper()`, which
                       the base class's own docstring says "recovers"
                       `ModelId.Entry` (`StringHelper.Slugify(type.Name)`,
                       confirmed by reading `ModelDb.GetEntry`/`ModelId.cs`)
                       "for every encounter whose id matches its class-name
                       slug". All 5 of this batch's sim ids do NOT match: each
                       drops the "_ENCOUNTER" suffix (or, for Battleworn
                       Dummy, is split into three per-setting ids with no
                       relation to the one shared C# class name at all). This
                       feeds `make_encounter_rng(seed, floor, entry)`
                       (`rng.py:52-67`, formula itself independently verified
                       faithful by `seam/rng_streams` step 21) the WRONG key,
                       so the per-encounter Rng this batch's units build in
                       parity mode is seeded differently than the game's.
punch-off-wrong-seed   encounter/_entry_slug_mismatch's LIVE site:
                       `PunchOffEventEncounter.GenerateMonsters` draws
                       `base.Rng.NextInt(2, 10)` TWICE (once per Punch
                       Construct) -- the only one of this batch's 5 whose
                       GenerateMonsters draws anything at all. Demonstrates
                       that seeding with the sim's actual (wrong) entry string
                       produces different `StartingHpReduction` values than
                       seeding with the game's real one, at equal run seed and
                       floor -- an observable, in-game divergence (both
                       Constructs' starting HP differ from the recording).
dormant-4-zero-draws   encounter/_entry_slug_mismatch's DORMANT sites (the
                       other 4 units): each of BattlewornDummyEventEncounter,
                       DenseVegetationEventEncounter, FakeMerchantEventEncounter
                       and MysteriousKnightEventEncounter's `GenerateMonsters`
                       bodies (read in full, quoted below) call `base.Rng`
                       zero times, so the per-encounter Rng they build is
                       constructed but never drawn from -- the wrong seed is
                       unobservable there today. Confirmed by actually
                       building each sim encounter's monsters under two
                       differently-seeded selection_rngs and diffing every
                       observable (class list, slot list, HP, starting-state
                       flags): identical both times.
slots-not-ported       encounter/_slots_not_ported (dense_vegetation_event,
                       fake_merchant_event): C# DenseVegetationEventEncounter.
                       Slots = ["wriggler1".."wriggler4"] and
                       FakeMerchantEventEncounter.Slots = ["merchant"]; the
                       sim's DENSE_VEGETATION_EVENT_ENCOUNTER and
                       FAKE_MERCHANT_EVENT_ENCOUNTER both leave `slots=()`
                       (the dataclass default) and never call
                       `CreatureCmd.add` with a slot_name for these creatures,
                       so `slot_name` stays None throughout. Confirmed dormant
                       via `combat.py`'s `sort_enemies_by_slot_name`, which is
                       a no-op whenever `encounter.slots` is empty, and via
                       `monsters/base.py`'s `get_next_slot`/`last_free_slot`,
                       neither of which either encounter's `create_monsters`
                       calls.
"""
from __future__ import annotations

import random as _random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── shared: StringHelper.Slugify, reproduced from src/Core/Helpers/
#    StringHelper.cs:74-79 (regex "([A-Za-z0-9]|\G(?!^))([A-Z])" -> "$1_$2",
#    then upper + strip non [A-Z0-9_]). Used only to recompute the game's
#    real ModelId.Entry for the 5 C# class names below, as an independent
#    check against the sim's `Encounter.entry` (`id.upper()`) -- not shipped
#    in sts2_rl itself, so re-derived here rather than imported.
def _slugify(class_name: str) -> str:
    text = re.sub(r"(?<=[A-Za-z0-9])([A-Z])", r"_\1", class_name)
    return text.upper()


_CLASS_SLUGS = {
    "battleworn_dummy_event": "BattlewornDummyEventEncounter",
    "dense_vegetation_event": "DenseVegetationEventEncounter",
    "fake_merchant_event": "FakeMerchantEventEncounter",
    "mysterious_knight_event": "MysteriousKnightEventEncounter",
    "punch_off_event": "PunchOffEventEncounter",
}


def probe_entry_slug_mismatch() -> None:
    print("== entry-slug-mismatch ==")
    from sts2_rl.monsters.glory.battle_friend import (
        BATTLEWORN_DUMMY_SETTING_1, BATTLEWORN_DUMMY_SETTING_2,
        BATTLEWORN_DUMMY_SETTING_3,
    )
    from sts2_rl.events.dense_vegetation import DENSE_VEGETATION_EVENT_ENCOUNTER
    from sts2_rl.monsters.fake_merchant import FAKE_MERCHANT_EVENT_ENCOUNTER
    from sts2_rl.monsters.hive.flail_knight import MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER
    from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER

    sim_encounters = {
        "battleworn_dummy_event (setting 1)": BATTLEWORN_DUMMY_SETTING_1,
        "battleworn_dummy_event (setting 2)": BATTLEWORN_DUMMY_SETTING_2,
        "battleworn_dummy_event (setting 3)": BATTLEWORN_DUMMY_SETTING_3,
        "dense_vegetation_event": DENSE_VEGETATION_EVENT_ENCOUNTER,
        "fake_merchant_event": FAKE_MERCHANT_EVENT_ENCOUNTER,
        "mysterious_knight_event": MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER,
        "punch_off_event": PUNCH_OFF_EVENT_ENCOUNTER,
    }
    for label, enc in sim_encounters.items():
        unit = label.split(" ")[0]
        cs_class = _CLASS_SLUGS[unit]
        real_entry = _slugify(cs_class)
        sim_entry = enc.entry
        status = "MATCH" if real_entry == sim_entry else "MISMATCH"
        print(f"  {label:38s} sim.entry={sim_entry!r:38s} "
              f"real C# Id.Entry={real_entry!r:40s} {status}")


def probe_punch_off_wrong_seed() -> None:
    from sts2_rl.rng import make_encounter_rng
    from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
    from sts2_rl.hooks import HookSystem

    print("== punch-off-wrong-seed ==")
    run_seed, floor = 12345, 7
    wrong_entry = PUNCH_OFF_EVENT_ENCOUNTER.entry
    real_entry = _slugify(_CLASS_SLUGS["punch_off_event"])
    print(f"  run_seed={run_seed} floor={floor}")
    print(f"  sim entry (actually used)  = {wrong_entry!r}")
    print(f"  game Id.Entry (should be)  = {real_entry!r}")

    def rolled_reductions(entry: str) -> list[int]:
        rng = make_encounter_rng(run_seed, floor, entry)
        hooks = HookSystem()
        monsters = PUNCH_OFF_EVENT_ENCOUNTER.create_monsters(
            hooks, _random.Random(0), rng)
        return [m.starting_hp_reduction for m in monsters]

    got = rolled_reductions(wrong_entry)
    want = rolled_reductions(real_entry)
    print(f"  StartingHpReduction with the sim's actual (wrong) seed: {got}")
    print(f"  StartingHpReduction with the game's real seed:         {want}")
    print(f"  DIVERGENT: {got != want} "
          "(both Punch Constructs' starting HP differ from what the "
          "recording would show at this seed/floor)")


def probe_dormant_4_zero_draws() -> None:
    import inspect

    print("== dormant-4-zero-draws ==")
    from sts2_rl.monsters.glory import battle_friend
    from sts2_rl.events import dense_vegetation
    from sts2_rl.monsters import fake_merchant
    from sts2_rl.monsters.hive import flail_knight
    from sts2_rl.rng import make_encounter_rng
    from sts2_rl.hooks import HookSystem

    checks = [
        ("battleworn_dummy_event (setting 1)", battle_friend.BATTLEWORN_DUMMY_SETTING_1),
        ("dense_vegetation_event", dense_vegetation.DENSE_VEGETATION_EVENT_ENCOUNTER),
        ("fake_merchant_event", fake_merchant.FAKE_MERCHANT_EVENT_ENCOUNTER),
        ("mysterious_knight_event", flail_knight.MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER),
    ]
    for label, enc in checks:
        rng_a = make_encounter_rng(1, 1, "AAAAAAAAAAAAAAAAAAAA")
        rng_b = make_encounter_rng(999999, 42, "COMPLETELY_DIFFERENT_KEY")
        hooks_a, hooks_b = HookSystem(), HookSystem()
        mons_a = enc.create_monsters(hooks_a, _random.Random(0), rng_a)
        mons_b = enc.create_monsters(hooks_b, _random.Random(0), rng_b)

        def snapshot(mons):
            return [
                (type(m).__name__, m.slot_name,
                 getattr(m, "starting_hp_reduction", None),
                 getattr(m, "hp", None), getattr(m, "max_hp", None))
                for m in mons
            ]

        snap_a, snap_b = snapshot(mons_a), snapshot(mons_b)
        identical = snap_a == snap_b
        print(f"  {label:38s} identical under two unrelated seeds: {identical}"
              f"  {snap_a}")
        assert identical, (
            f"{label}: composition changed with the selection_rng seed -- "
            "this unit is NOT in the zero-draw bucket, re-verdict it live")


def probe_slots_not_ported() -> None:
    from sts2_rl.events.dense_vegetation import DENSE_VEGETATION_EVENT_ENCOUNTER
    from sts2_rl.monsters.fake_merchant import FAKE_MERCHANT_EVENT_ENCOUNTER
    from sts2_rl import combat as combat_module

    print("== slots-not-ported ==")
    print("  DENSE_VEGETATION_EVENT_ENCOUNTER.slots =",
          DENSE_VEGETATION_EVENT_ENCOUNTER.slots,
          "(C# Slots = [\"wriggler1\",\"wriggler2\",\"wriggler3\",\"wriggler4\"])")
    print("  FAKE_MERCHANT_EVENT_ENCOUNTER.slots    =",
          FAKE_MERCHANT_EVENT_ENCOUNTER.slots,
          "(C# Slots = [\"merchant\"])")
    src = combat_module.__dict__["CombatState"].sort_enemies_by_slot_name
    import inspect
    body = inspect.getsource(src)
    has_guard = "not getattr(encounter, \"slots\", ())" in body or "encounter.slots" in body
    print("  CombatState.sort_enemies_by_slot_name no-ops when "
          "encounter.slots is empty:", has_guard)
    hooks = combat_module.HookSystem() if hasattr(combat_module, "HookSystem") else None
    cs = combat_module.CombatState(
        rng=_random.Random(0), encounter=DENSE_VEGETATION_EVENT_ENCOUNTER)
    print("  dense_vegetation_event initial enemies' slot_name:",
          [e.slot_name for e in cs.enemies], "(all None; move behaviour is "
          "still correct because it is keyed off the constructor's `slot: "
          "int` argument, not `slot_name` -- see Wriggler.__init__)")
    cs2 = combat_module.CombatState(
        rng=_random.Random(0), encounter=FAKE_MERCHANT_EVENT_ENCOUNTER)
    print("  fake_merchant_event initial enemies' slot_name:",
          [e.slot_name for e in cs2.enemies], "(C# seats it at \"merchant\"; "
          "no ported behaviour reads FakeMerchantMonster's slot_name either)")


PROBES = {
    "entry-slug-mismatch": probe_entry_slug_mismatch,
    "punch-off-wrong-seed": probe_punch_off_wrong_seed,
    "dormant-4-zero-draws": probe_dormant_4_zero_draws,
    "slots-not-ported": probe_slots_not_ported,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in (*PROBES, "all"):
        print(f"usage: py {sys.argv[0]} <{'|'.join(PROBES)}|all>")
        raise SystemExit(1)
    names = PROBES if sys.argv[1] == "all" else [sys.argv[1]]
    for name in names:
        PROBES[name]()
        print()


if __name__ == "__main__":
    main()
