"""Tests for the affliction registry (afflictions.py) and the new
'afflictions'/'enchantments' vocab.py capacities — entity-obs-schema phase 1,
task T2.

Ownership note: this test file, sts2_rl/afflictions.py and sts2_rl/vocab.py
are the only files this task may touch. Production frozen-id wiring for
'enchantments' would naturally live in sts2_rl/enchantments.py (the way
full_env.py holds CARD_IDS and run_env.py holds RELIC_IDS), but that file is
owned by another in-flight task, so it was left unedited. The enchantment-
side tests below exercise the same vocab.frozen_ids mechanism directly,
against a scratch path, so they do not depend on wiring that does not exist
yet and do not write an 'enchantments' entry into the real vocab.json.
"""
from __future__ import annotations

import json

import pytest

from sts2_rl import afflictions, enchantments
from sts2_rl.afflictions import (
    ALL_AFFLICTIONS,
    AFFLICTION_IDS,
    AFFLICTION_INDEX,
    Affliction,
    make_affliction,
)
from sts2_rl.enchantments import ALL_ENCHANTMENTS, Enchantment
from sts2_rl.vocab import CAPACITIES, VOCAB_PATH, _load, capacity, frozen_ids


def _all_subclasses(cls: type) -> set[type]:
    """Recursively walks __subclasses__() of ``cls``, keeping only classes
    declared in ``cls``'s OWN module — independent of any registry, so a real
    affliction missing its @register_affliction decorator still shows up here
    and the coverage test below can actually catch it.

    The module filter is load-bearing, not tidiness. `__subclasses__()` is
    process-global and sees anything that has been imported, so under the full
    suite it also finds test doubles — `test_round13_listener_derivation.py`
    declares `_HookedAffliction(Affliction)`. Without the filter these tests
    pass when run alone and fail when run with the suite, which is the worst
    possible failure mode: it looks like a real regression and it depends on
    collection order. A test double is deliberately unregistered, so demanding
    it carry a decorator tests nothing.
    """
    home = cls.__module__
    seen: set[type] = set()
    stack = list(cls.__subclasses__())
    while stack:
        sub = stack.pop()
        if sub not in seen:
            # Walk THROUGH foreign subclasses (a test double could itself be
            # subclassed by a real one) but never collect them.
            stack.extend(sub.__subclasses__())
            if sub.__module__ != home:
                continue
            seen.add(sub)
    return seen


# ═════════════════════════════════════════════════════════════════════════
# (1) Every Affliction subclass is registered; make_affliction round-trips
# ═════════════════════════════════════════════════════════════════════════

def test_every_affliction_subclass_is_registered():
    discovered = _all_subclasses(Affliction)
    assert discovered, "discovery found nothing — the walk itself is broken"
    for cls in discovered:
        assert cls.id in ALL_AFFLICTIONS, (
            f"{cls.__name__} (id={cls.id!r}) has no @register_affliction "
            f"decorator")
        assert ALL_AFFLICTIONS[cls.id] is cls


def test_registry_has_no_extra_classes():
    # The reverse direction: nothing registered that __subclasses__() can't
    # also find (would indicate a stale/duplicate registration).
    discovered_ids = {cls.id for cls in _all_subclasses(Affliction)}
    assert set(ALL_AFFLICTIONS) == discovered_ids


def test_make_affliction_returns_the_right_class_for_every_id():
    for cls in _all_subclasses(Affliction):
        made = make_affliction(cls.id)
        assert type(made) is cls
        assert isinstance(made, Affliction)


def test_make_affliction_unknown_id_raises():
    with pytest.raises(KeyError):
        make_affliction("not_a_real_affliction")


# ═════════════════════════════════════════════════════════════════════════
# (2) Ids are unique
# ═════════════════════════════════════════════════════════════════════════

def test_affliction_ids_are_unique():
    ids = [cls.id for cls in _all_subclasses(Affliction)]
    assert len(ids) == len(set(ids))


def test_enchantment_ids_are_unique():
    ids = [cls.id for cls in _all_subclasses(Enchantment)]
    assert len(ids) == len(set(ids))
    # Cross-check against the registry populated by @register_enchantment.
    assert len(ALL_ENCHANTMENTS) == len(set(ALL_ENCHANTMENTS))


# ═════════════════════════════════════════════════════════════════════════
# (3) Live counts fit inside the new capacities
# ═════════════════════════════════════════════════════════════════════════

def test_affliction_live_count_fits_capacity():
    n = len(ALL_AFFLICTIONS)
    cap = capacity("afflictions")
    assert n <= cap, (
        f"{n} registered afflictions exceeds capacity {cap} — bump "
        f"CAPACITIES['afflictions'] in sts2_rl/vocab.py, bump the affected "
        f"obs schema version(s), and retrain (see vocab.py's module "
        f"docstring / frozen_ids' RuntimeError for the full procedure)")


def test_enchantment_live_count_fits_capacity():
    n = len(ALL_ENCHANTMENTS)
    cap = capacity("enchantments")
    assert n <= cap, (
        f"{n} registered enchantments exceeds capacity {cap} — bump "
        f"CAPACITIES['enchantments'] in sts2_rl/vocab.py, bump the affected "
        f"obs schema version(s), and retrain (see vocab.py's module "
        f"docstring / frozen_ids' RuntimeError for the full procedure)")


# ═════════════════════════════════════════════════════════════════════════
# (4) Frozen lists are prefix-stable
# ═════════════════════════════════════════════════════════════════════════

def test_affliction_frozen_ids_prefix_stable_across_calls():
    # AFFLICTION_IDS was already computed once at import time (against the
    # real vocab.json). Calling frozen_ids again with the same registered
    # set must reproduce it exactly and not move anything.
    again = frozen_ids("afflictions", ALL_AFFLICTIONS)
    assert again == AFFLICTION_IDS
    for i, aid in enumerate(AFFLICTION_IDS):
        assert AFFLICTION_INDEX[aid] == i


def test_affliction_frozen_ids_match_persisted_registry():
    assert _load(VOCAB_PATH).get("afflictions") == AFFLICTION_IDS


def test_enchantment_frozen_ids_prefix_stable_across_calls(tmp_path):
    path = tmp_path / "vocab.json"
    first = frozen_ids("enchantments", ALL_ENCHANTMENTS, path=path)
    second = frozen_ids("enchantments", ALL_ENCHANTMENTS, path=path)
    assert first == second
    assert set(first) == set(ALL_ENCHANTMENTS)
    # Persisted content agrees with what was returned.
    assert json.loads(path.read_text())["enchantments"] == first
    # A no-op re-registration (nothing new) does not touch mtime-affecting
    # content: re-running merge is idempotent.
    third = frozen_ids("enchantments", ALL_ENCHANTMENTS, path=path)
    assert third == first


# ═════════════════════════════════════════════════════════════════════════
# (5) Capacity covers the GAME total, not the ported total
# ═════════════════════════════════════════════════════════════════════════

def test_affliction_capacity_covers_full_game_total():
    # Counted 2026-08-01 from the decompiled game source: every *.cs file
    # directly under src/Core/Models/Afflictions/, excluding the Mocks/
    # subdirectory and *.uid sidecar files:
    #   Bound, Entangled, Galvanized, Hexed, Ringing, Smog, Tainted = 7
    # All 7 are ported (this file's registry also has exactly 7 entries).
    game_total = 7
    assert capacity("afflictions") >= game_total
    assert len(ALL_AFFLICTIONS) == game_total, (
        "ported count no longer matches the measured game total — "
        "re-verify against src/Core/Models/Afflictions/")


def test_enchantment_capacity_covers_full_game_total():
    # Counted 2026-08-01 from the decompiled game source: every *.cs file
    # directly under src/Core/Models/Enchantments/, excluding the Mocks/
    # subdirectory, *.uid sidecar files, and DeprecatedEnchantment.cs (an
    # empty `sealed class DeprecatedEnchantment : EnchantmentModel {}` with
    # no id/content — a marker, not a real enchantment):
    #   Adroit, Clone, Corrupted, Glam, Goopy, Imbued, Inky, Instinct,
    #   Momentum, Nimble, PerfectFit, RoyallyApproved, Sharp, Slither,
    #   SlumberingEssence, SoulsPower, Sown, Spiral, Steady, Swift,
    #   TezcatarasEmber, Vigorous = 22
    # Only 19 are ported today (Inky, Momentum, SlumberingEssence are not) —
    # capacity must still cover the full 22, which is the whole point of
    # sizing to the game total rather than the ported total.
    game_total = 22
    ported_total = 19
    assert capacity("enchantments") >= game_total
    assert len(ALL_ENCHANTMENTS) == ported_total, (
        "ported enchantment count drifted — re-verify against "
        "sts2_rl/enchantments.py and src/Core/Models/Enchantments/")


def test_new_capacities_registered_and_have_headroom():
    assert "afflictions" in CAPACITIES
    assert "enchantments" in CAPACITIES
    # Headroom exists (capacity strictly greater than today's live count),
    # so a newly-ported affliction/enchantment doesn't immediately trip the
    # frozen_ids() RuntimeError.
    assert capacity("afflictions") > len(ALL_AFFLICTIONS)
    assert capacity("enchantments") > len(ALL_ENCHANTMENTS)
