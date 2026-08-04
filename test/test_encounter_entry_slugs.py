"""`Encounter.entry` — the key that seeds every per-encounter Rng.

`EncounterModel.GenerateMonstersWithSlots` seeds its Rng from
(run seed, floor, `ModelId.Entry`), and `ModelId.Entry` is
`StringHelper.Slugify(className)`. The sim recovers it as `id.upper()`, which
is right for 78 of the 87 encounters and WRONG for nine: the sim id drops the
C# tier/`_ENCOUNTER` suffix (`punch_off_event` vs `PunchOffEventEncounter`,
`fuzzy_wurm_crawler` vs `FuzzyWurmCrawlerWeak`). A wrong key is a wrong stream
from its first draw — at Punch-Off it changes both constructs' starting HP.

Those nine declare `entry_slug` explicitly. This file pins them, transcribed
from the C# class names in `src/Core/Models/Encounters/`; the mechanical
re-derivation against that directory is
`py audit/tools/encounter_entry_sweep.py`, which reads the game source and so
does not belong in the suite.

Queue entry: encounter/_entry_slug_mismatch.
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest

import sts2_rl
from sts2_rl.monsters.base import Encounter

# sim id -> the game's real ModelId.Entry, for every encounter whose id is not
# its own C# class name's slug. Nothing else may carry an override.
EXPECTED_OVERRIDES = {
    "battleworn_dummy_setting_1": "BATTLEWORN_DUMMY_EVENT_ENCOUNTER",
    "battleworn_dummy_setting_2": "BATTLEWORN_DUMMY_EVENT_ENCOUNTER",
    "battleworn_dummy_setting_3": "BATTLEWORN_DUMMY_EVENT_ENCOUNTER",
    "dense_vegetation_event": "DENSE_VEGETATION_EVENT_ENCOUNTER",
    "fake_merchant_event": "FAKE_MERCHANT_EVENT_ENCOUNTER",
    "fuzzy_wurm_crawler": "FUZZY_WURM_CRAWLER_WEAK",
    "mysterious_knight_event": "MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER",
    "overgrowth_crawlers_normal": "OVERGROWTH_CRAWLERS",
    "punch_off_event": "PUNCH_OFF_EVENT_ENCOUNTER",
}


def _all_encounters() -> dict[str, Encounter]:
    found: dict[str, Encounter] = {}
    for mod in pkgutil.walk_packages(sts2_rl.__path__, "sts2_rl."):
        try:
            module = importlib.import_module(mod.name)
        except Exception:  # pragma: no cover - optional deps
            continue
        for obj in vars(module).values():
            if isinstance(obj, Encounter):
                found.setdefault(obj.id, obj)
    return found


ENCOUNTERS = _all_encounters()


def test_the_sweep_sees_every_encounter():
    """A guard on the guard: if the walk stops finding encounters, the two
    tests below would pass vacuously."""
    assert len(ENCOUNTERS) >= 87


@pytest.mark.parametrize("eid,entry", sorted(EXPECTED_OVERRIDES.items()))
def test_the_nine_mismatched_ids_seed_with_the_game_slug(eid, entry):
    assert ENCOUNTERS[eid].entry == entry


def test_no_other_encounter_declares_an_override():
    """`entry_slug` is for ids that genuinely disagree with their class name.
    Every other encounter must keep deriving its entry from its id, so a typo
    in one cannot hide behind an override."""
    declared = {eid: enc.entry_slug for eid, enc in ENCOUNTERS.items()
                if enc.entry_slug is not None}
    assert declared == EXPECTED_OVERRIDES


def test_every_other_entry_is_its_id_uppercased():
    for eid, enc in ENCOUNTERS.items():
        if eid in EXPECTED_OVERRIDES:
            continue
        assert enc.entry == eid.upper()
