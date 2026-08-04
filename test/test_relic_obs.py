"""Tests for sts2_rl/relic_obs.py — the (counter, flag) observation row for
one relic instance (OBS_SCHEMA.md §6 / entity-obs-schema.md phase-1 R1).

Written before the implementation (TDD): the first test alone (every
registered relic, no state) is enough to fail against an empty module, and
the rest pin the three rules the spec calls out as silently leaky if done
naively — publish the DISPLAYED value, gate in-combat-only counters, and
never leak EXCLUDED_RELIC_STATE.
"""
from __future__ import annotations

import pytest

from sts2_rl.relics import ALL_RELICS
from sts2_rl.relic_obs import (
    CLAMP_CEILING,
    EXCLUDED_RELIC_STATE,
    _BOTH,
    _FLAG_ONLY,
    _IN_COMBAT_ONLY_COUNTERS,
    _TABLE,
    relic_row,
)


def _make(relic_id: str):
    return ALL_RELICS[relic_id]()


# ---------------------------------------------------------------------------
# 1. relic_row works for every registered relic and never raises.
# ---------------------------------------------------------------------------

def test_all_relics_are_registered_and_countable():
    # Re-measured, not copied from prose: ALL_RELICS is 260 as of 2026-08-03
    # (259 + the Circlet, RelicFactory's FallbackRelic).
    assert len(ALL_RELICS) == 260


def test_relic_row_never_raises_for_any_registered_relic():
    for relic_id, cls in ALL_RELICS.items():
        inst = cls()
        for in_combat in (False, True):
            counter, flag = relic_row(inst, in_combat=in_combat)
            assert isinstance(counter, int)
            assert isinstance(flag, int)
            assert 0 <= counter <= CLAMP_CEILING
            assert flag in (0, 1)


def test_relics_with_no_mutable_state_are_all_zero():
    stateless = [rid for rid in ALL_RELICS if rid not in _TABLE]
    # 260 registered - 50 admitted (28 counter-only + 4 both + 18 flag-only)
    # = 209 with either no mutable state or fully-excluded state; both
    # collapse to (0, 0) since relic_row only special-cases admitted ids.
    assert len(stateless) == 260 - len(_TABLE)
    for relic_id in stateless:
        inst = ALL_RELICS[relic_id]()
        assert relic_row(inst, in_combat=False) == (0, 0)
        assert relic_row(inst, in_combat=True) == (0, 0)


def test_admitted_relic_count_matches_the_census():
    # 28 counter-only + 18 flag-only + 4 both = 50.
    assert len(_TABLE) == 50
    counter_bearing = sum(1 for spec in _TABLE.values() if spec.counter is not None)
    flag_bearing = sum(1 for spec in _TABLE.values() if spec.flag is not None)
    assert counter_bearing == 32   # 28 counter-only + 4 both
    assert flag_bearing == 22      # 18 flag-only + 4 both


def test_relics_with_genuinely_no_mutable_attributes_are_194_from_a_bare_constructor():
    # A bare `cls()` shows 65 stateful relics (195 = 260 - 65), not 70: the
    # other 5 (`lees_waffle`, `looming_fruit`, `mango`, `pear`, `strawberry`)
    # only create `_healed` LAZILY, inside `after_obtained`, so a freshly
    # constructed instance carries no extra attribute yet. The census's
    # "70 stateful / 189 stateless" figure counts those 5 as stateful because
    # they CAN hold state after a relic-obtain event; relic_row's own table
    # only needs to cover relics whose state is genuinely displayed, and
    # none of the 5 `_healed` shims are (see EXCLUDED_RELIC_STATE) — so the
    # 189/194 split is immaterial to what this module admits.
    from sts2_rl.relics.base import Relic

    base_attrs = set(vars(Relic()).keys())
    stateless = 0
    for cls in ALL_RELICS.values():
        inst = cls()
        extra = {k: v for k, v in vars(inst).items() if k not in base_attrs}
        if not extra:
            stateless += 1
    assert stateless == 260 - 65


# ---------------------------------------------------------------------------
# 2. Targeted DISPLAYED-value tests for admitted relics.
# ---------------------------------------------------------------------------

def test_fishing_rod_publishes_modulo_not_raw_count():
    r = _make("fishing_rod")
    r.combats_seen = 37   # raw combats fought this run, unrelated to the mod
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 37 % 3
    assert counter != 37


def test_book_of_five_rings_publishes_modulo():
    r = _make("book_of_five_rings")
    r.cards_added = 23
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 23 % 5


def test_iron_club_publishes_modulo():
    r = _make("iron_club")
    r.cards_played = 17
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 17 % 4


def test_lasting_candy_publishes_modulo():
    r = _make("lasting_candy")
    r.combats_seen = 9
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 9 % 2


def test_paels_wing_publishes_modulo():
    r = _make("paels_wing")
    r.rewards_sacrificed = 5
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 5 % 2


def test_nunchaku_publishes_modulo():
    r = _make("nunchaku")
    r._attacks_played = 34
    counter, _ = relic_row(r, in_combat=True)
    assert counter == 34 % 10


def test_pen_nib_already_stored_modulo_is_not_double_modulo_d():
    r = _make("pen_nib")
    r._attacks_played = 7   # pen_nib.py keeps this in [0, 10) already
    counter, _ = relic_row(r, in_combat=True)
    assert counter == 7


def test_joss_paper_already_stored_modulo_is_not_double_modulo_d():
    r = _make("joss_paper")
    r.cards_exhausted = 3   # joss_paper.py keeps this in [0, 5) already
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 3


def test_winged_boots_counts_down():
    r = _make("winged_boots")
    r.times_used = 0
    counter0, _ = relic_row(r, in_combat=False)
    r.times_used = 1
    counter1, _ = relic_row(r, in_combat=False)
    r.times_used = 3
    counter3, flag3 = relic_row(r, in_combat=False)
    assert counter0 == 3
    assert counter1 == 2
    assert counter3 == 0
    assert flag3 == 1   # is_used_up


def test_silver_crucible_counts_down_and_flags_used_up():
    r = _make("silver_crucible")
    r.times_used = 0
    counter0, flag0 = relic_row(r, in_combat=False)
    assert counter0 == 3
    assert flag0 == 0
    r.times_used = 3
    r.treasure_rooms_entered = 0
    counter_used, flag_not_yet = relic_row(r, in_combat=False)
    assert counter_used == 0
    # not used-up yet: TimesUsed >= Cards but no chestless treasure room paid
    assert flag_not_yet == 0
    r.treasure_rooms_entered = 1
    _, flag_used_up = relic_row(r, in_combat=False)
    assert flag_used_up == 1


def test_wongos_mystery_ticket_counts_down_and_flags_gave_relic():
    r = _make("wongos_mystery_ticket")
    r.combats_finished = 2
    counter, flag = relic_row(r, in_combat=False)
    assert counter == 3
    assert flag == 0
    r.combats_finished = 5
    r.gave_relic = True
    counter2, flag2 = relic_row(r, in_combat=False)
    assert counter2 == 0
    assert flag2 == 1


def test_paels_tooth_publishes_length_not_contents():
    r = _make("paels_tooth")
    r.stored_cards = ["card_a", "card_b", "card_c"]
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 3


def test_toy_box_modulo_and_used_up_flag():
    r = _make("toy_box")
    r.combats_seen = 7
    counter, flag = relic_row(r, in_combat=False)
    assert counter == 7 % 3
    assert flag == 0
    r.combats_seen = 12   # COMBATS_PER_MELT(3) * RELICS(4)
    counter2, flag2 = relic_row(r, in_combat=False)
    assert counter2 == 12 % 3
    assert flag2 == 1


def test_girya_publishes_raw_times_lifted():
    r = _make("girya")
    r.times_lifted = 2
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 2


def test_sword_of_stone_publishes_raw_elites_defeated():
    r = _make("sword_of_stone")
    r.elites_defeated = 4
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 4


def test_ember_tea_publishes_raw_combats_left_not_gated_on_combat():
    r = _make("ember_tea")
    r.combats_left = 3
    counter_out, _ = relic_row(r, in_combat=False)
    counter_in, _ = relic_row(r, in_combat=True)
    assert counter_out == counter_in == 3


# --- flag-only relics --------------------------------------------------

def test_lizard_tail_flags_used_up():
    r = _make("lizard_tail")
    assert relic_row(r, in_combat=False) == (0, 0)
    r._used = True
    assert relic_row(r, in_combat=False) == (0, 1)


def test_maw_bank_flags_item_bought():
    r = _make("maw_bank")
    assert relic_row(r, in_combat=False)[1] == 0
    r.has_item_been_bought = True
    assert relic_row(r, in_combat=False)[1] == 1


def test_belt_buckle_flags_applied():
    r = _make("belt_buckle")
    assert relic_row(r, in_combat=True)[1] == 0
    r._applied = True
    assert relic_row(r, in_combat=True)[1] == 1


def test_rainbow_ring_flags_activated():
    r = _make("rainbow_ring")
    assert relic_row(r, in_combat=True)[1] == 0
    r._activated = True
    assert relic_row(r, in_combat=True)[1] == 1


def test_lava_rock_flags_has_triggered():
    r = _make("lava_rock")
    assert relic_row(r, in_combat=False)[1] == 0
    r.has_triggered = True
    assert relic_row(r, in_combat=False)[1] == 1


def test_venerable_tea_set_flags_pending():
    r = _make("venerable_tea_set")
    assert relic_row(r, in_combat=True)[1] == 0
    r._pending = True
    assert relic_row(r, in_combat=True)[1] == 1


def test_bone_tea_and_tea_of_discourtesy_flag_is_used_up():
    for relic_id in ("bone_tea", "tea_of_discourtesy"):
        r = _make(relic_id)
        assert relic_row(r, in_combat=False)[1] == 0
        r.combats_left = 0
        assert relic_row(r, in_combat=False)[1] == 1


# ---------------------------------------------------------------------------
# 3. The non-leak test: EXCLUDED_RELIC_STATE must never reach the row.
# ---------------------------------------------------------------------------

_SENTINEL_INT = 1234567
_SENTINEL_STR = "__SENTINEL_SHOULD_NEVER_LEAK__"
_SENTINEL_LIST = ["__SENTINEL_A__", "__SENTINEL_B__", "__SENTINEL_C__"]


def _sentinel_for(current_value):
    if isinstance(current_value, bool):
        return not current_value
    if isinstance(current_value, int):
        return _SENTINEL_INT
    if isinstance(current_value, (list, set, tuple)):
        return type(current_value)(_SENTINEL_LIST)
    return _SENTINEL_STR


@pytest.mark.parametrize(
    "relic_id", sorted(EXCLUDED_RELIC_STATE.keys()),
)
def test_excluded_relic_state_never_leaks(relic_id):
    for attr in EXCLUDED_RELIC_STATE[relic_id]:
        baseline = _make(relic_id)
        row_before = (
            relic_row(baseline, in_combat=False),
            relic_row(baseline, in_combat=True),
        )

        poisoned = _make(relic_id)
        current = getattr(poisoned, attr)
        setattr(poisoned, attr, _sentinel_for(current))
        row_after = (
            relic_row(poisoned, in_combat=False),
            relic_row(poisoned, in_combat=True),
        )

        assert row_after == row_before, (
            f"{relic_id}.{attr} changed relic_row's output — "
            f"excluded state leaked into the observation"
        )


def test_fur_coat_marked_coords_never_leaks():
    # The two citations the brief calls out by name.
    r = _make("fur_coat")
    r.marked_coords = {(1, 2), (3, 4), (5, 6)}
    assert relic_row(r, in_combat=False) == (0, 0)
    assert relic_row(r, in_combat=True) == (0, 0)


def test_dusty_tome_ancient_card_never_leaks():
    r = _make("dusty_tome")
    r.ancient_card = "some_card_the_player_has_not_seen"
    assert relic_row(r, in_combat=False) == (0, 0)
    assert relic_row(r, in_combat=True) == (0, 0)


def test_paels_tooth_card_identities_never_leak_only_count_does():
    r_a = _make("paels_tooth")
    r_a.stored_cards = ["strike", "strike", "defend"]
    r_b = _make("paels_tooth")
    r_b.stored_cards = ["apotheosis", "offering", "corruption"]
    # Same length, wildly different (and distinctive) contents -> identical
    # row: only the count is observable.
    assert relic_row(r_a, in_combat=False) == relic_row(r_b, in_combat=False)


def test_healed_shim_relics_never_leak():
    for relic_id in ("lees_waffle", "looming_fruit", "mango", "pear", "strawberry"):
        r = _make(relic_id)
        r._healed = 999
        assert relic_row(r, in_combat=False) == (0, 0)
        assert relic_row(r, in_combat=True) == (0, 0)


def test_every_excluded_attribute_actually_exists_on_its_relic():
    """Guards the fixture itself: a typo'd attribute name would make the
    non-leak test above pass vacuously (setattr creates a NEW attribute
    that nothing reads, rather than overriding one relic_row might read)."""
    for relic_id, attrs in EXCLUDED_RELIC_STATE.items():
        inst = _make(relic_id)
        for attr in attrs:
            assert hasattr(inst, attr), (
                f"EXCLUDED_RELIC_STATE names {relic_id}.{attr}, "
                f"but the relic has no such attribute by default"
            )


# ---------------------------------------------------------------------------
# 4. Clamp: pocketwatch / diamond_diadem / pumpkin_candle are unbounded in
#    the source and must be clamped, not allowed to blow up the input.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relic_id, attr", [
    ("pocketwatch", "_played_this_turn"),
    ("diamond_diadem", "cards_played_this_turn"),
    ("pumpkin_candle", "kindle_count"),
])
def test_uncapped_counters_are_clamped(relic_id, attr):
    r = _make(relic_id)
    setattr(r, attr, 10_000)
    counter, _ = relic_row(r, in_combat=True)
    assert counter == CLAMP_CEILING


def test_clamp_ceiling_is_nine():
    # The three mod-10 relics (nunchaku, pen_nib, tuning_fork) are the
    # largest STATICALLY bounded admissible counters, at 9.
    assert CLAMP_CEILING == 9


def test_clamp_never_goes_negative():
    r = _make("wongos_mystery_ticket")
    r.combats_finished = 999   # far past the countdown's 5
    counter, _ = relic_row(r, in_combat=False)
    assert counter == 0


# ---------------------------------------------------------------------------
# 5. In-combat-only relics read 0 with in_combat=False, non-zero with True.
# ---------------------------------------------------------------------------

def test_in_combat_only_set_has_ten_members():
    # Two more than the plan-stage census's 8: brilliant_scarf and
    # paels_legion also gate on CombatManager.Instance.IsInProgress.
    assert _IN_COMBAT_ONLY_COUNTERS == frozenset({
        "kunai", "kusarigama", "letter_opener", "ornamental_fan", "shuriken",
        "velvet_choker", "diamond_diadem", "pocketwatch", "brilliant_scarf",
        "paels_legion",
    })


_IN_COMBAT_ONLY_PROBES = {
    "kunai": ("_attacks_this_turn", 2),
    "kusarigama": ("_attacks_this_turn", 2),
    "letter_opener": ("_skills_this_turn", 2),
    "ornamental_fan": ("_attacks_this_turn", 2),
    "shuriken": ("_attacks_this_turn", 2),
    "velvet_choker": ("cards_played_this_turn", 3),
    "diamond_diadem": ("cards_played_this_turn", 1),
    "pocketwatch": ("_played_this_turn", 2),
    "brilliant_scarf": ("cards_played_this_turn", 2),
    "paels_legion": ("cooldown", 1),
}


@pytest.mark.parametrize("relic_id", sorted(_IN_COMBAT_ONLY_PROBES.keys()))
def test_in_combat_only_counter_reads_zero_out_of_combat(relic_id):
    attr, value = _IN_COMBAT_ONLY_PROBES[relic_id]
    r = _make(relic_id)
    setattr(r, attr, value)
    counter_out, _ = relic_row(r, in_combat=False)
    counter_in, _ = relic_row(r, in_combat=True)
    assert counter_out == 0
    assert counter_in != 0
    assert counter_in == value


def test_in_combat_only_set_matches_spec_membership():
    for relic_id in _IN_COMBAT_ONLY_COUNTERS:
        assert _TABLE[relic_id].counter_in_combat_only is True
    for relic_id, spec in _TABLE.items():
        if spec.counter is not None and relic_id not in _IN_COMBAT_ONLY_COUNTERS:
            assert spec.counter_in_combat_only is False


# ---------------------------------------------------------------------------
# Sanity: id/name coverage between the three tables is disjoint and their
# union is exactly _TABLE.
# ---------------------------------------------------------------------------

def test_table_partitions_are_disjoint_and_complete():
    from sts2_rl.relic_obs import _COUNTER_ONLY, _FLAG_ONLY as flag_only, _BOTH as both

    counter_only_ids = set(_COUNTER_ONLY.keys())
    flag_only_ids = set(flag_only.keys())
    both_ids = set(both.keys())
    assert not (counter_only_ids & flag_only_ids)
    assert not (counter_only_ids & both_ids)
    assert not (flag_only_ids & both_ids)
    assert counter_only_ids | flag_only_ids | both_ids == set(_TABLE.keys())


def test_unknown_relic_like_object_returns_zero_zero():
    class Fake:
        id = "not_a_real_relic_id"

    assert relic_row(Fake(), in_combat=False) == (0, 0)
    assert relic_row(Fake(), in_combat=True) == (0, 0)
