"""Named encounter SLOTS, and the re-sort that gives the enemy list its order.

`CreatureCmd.Add` appends to `_enemies` (CombatState.cs:534-547) and then calls
`CombatManager.AddCreature`, which runs `_state.SortEnemiesBySlotName()` whenever
`creature.SlotName != null` (CombatManager.cs:841-851) — and that sorts `_enemies`
by `Encounter.Slots.IndexOf(SlotName)` (CombatState.cs:495-501). So a spawn's
position is decided by its NAMED SLOT, not by insertion order.

The two summoners pick opposite ends of the row:
  * `EncounterModel.GetNextSlot` = `Slots.FirstOrDefault(unoccupied)`
    (EncounterModel.cs:245-248) — the Fabricator's bots (Fabricator.cs:115).
  * `Slots.LastOrDefault(unoccupied)` — the Ovicopter's eggs (Ovicopter.cs:87).

The sim had no slots at all: it appended (Fabricator) or inserted in front of
every live egg (Ovicopter), so a slot freed in the MIDDLE was never refilled in
place.

Queue entries: monster/fabricator/g5, monster/ovicopter/g2.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.monsters.glory import FABRICATOR_NORMAL
from sts2_rl.monsters.glory.fabricator import Fabricator
from sts2_rl.monsters.hive import OVICOPTER_NORMAL, THE_OBSCURA_NORMAL
from sts2_rl.monsters.hive.ovicopter import Ovicopter, ToughEgg
from sts2_rl.monsters.overgrowth import FOGMOG_NORMAL
from sts2_rl.monsters.underdocks import TWO_TAILED_RATS_NORMAL


def _combat(encounter, seed: int) -> CombatState:
    return CombatState(rng=random.Random(seed),
                       starting_deck=[make_card("strike") for _ in range(5)],
                       encounter=encounter)


# ══════════════════════════════════════════════════════════════════════════
# the machinery
# ══════════════════════════════════════════════════════════════════════════

def test_the_two_encounters_declare_their_slot_rows():
    """FabricatorNormal.cs:19 and OvicopterNormal.cs:16, verbatim."""
    assert list(FABRICATOR_NORMAL.slots) == [
        "bot1", "bot2", "fabricator", "bot3", "bot4"]
    assert list(OVICOPTER_NORMAL.slots) == [
        "egg1", "egg2", "egg3", "egg4", "egg5", "ovicopter"]


def test_the_seeded_monster_carries_its_slot_name():
    """`GenerateMonsters` returns (monster, slot) pairs — FabricatorNormal.cs:46-49
    seats the Fabricator in "fabricator" and OvicopterNormal.cs:36-39 seats the
    Ovicopter in "ovicopter"."""
    cs = _combat(FABRICATOR_NORMAL, 3)
    assert cs.enemies[0].slot_name == "fabricator"
    cs2 = _combat(OVICOPTER_NORMAL, 4)
    assert cs2.enemies[0].slot_name == "ovicopter"


def test_get_next_slot_is_the_first_unoccupied():
    """EncounterModel.cs:245-248, including the `string.Empty` default when the
    row is full — NOT null."""
    cs = _combat(FABRICATOR_NORMAL, 3)
    assert FABRICATOR_NORMAL.get_next_slot(cs) == "bot1"
    cs.enemies[0].slot_name = "bot1"
    assert FABRICATOR_NORMAL.get_next_slot(cs) == "bot2"
    for i, name in enumerate(FABRICATOR_NORMAL.slots):
        if i:
            e = type(cs.enemies[0])(cs.hooks, random.Random(0))
            e.slot_name = name
            cs.enemies.append(e)
    assert FABRICATOR_NORMAL.get_next_slot(cs) == ""


def test_last_unoccupied_slot_is_the_ovicopters_pick():
    cs = _combat(OVICOPTER_NORMAL, 4)
    assert OVICOPTER_NORMAL.last_free_slot(cs) == "egg5"


# ══════════════════════════════════════════════════════════════════════════
# monster/fabricator/g5 — bots seat BEFORE the Fabricator
# ══════════════════════════════════════════════════════════════════════════

def test_the_first_two_bots_seat_in_front_of_the_fabricator():
    """Slots = [bot1, bot2, fabricator, bot3, bot4], so after the opening
    FABRICATE the game's Enemies are [bot, bot, Fabricator] — the sim used to
    put the Fabricator first."""
    cs = _combat(FABRICATOR_NORMAL, 3)
    fab = cs.enemies[0]
    assert isinstance(fab, Fabricator)
    fab._fabricate(cs._ctx())
    assert cs.enemies[-1] is fab
    assert [e.slot_name for e in cs.enemies][:2] == ["bot1", "bot2"]


def test_later_bots_seat_behind_the_fabricator():
    """bot3 and bot4 come AFTER `fabricator` in the row."""
    cs = _combat(FABRICATOR_NORMAL, 3)
    fab = cs.enemies[0]
    for _ in range(2):
        fab._fabricate(cs._ctx())
    slots = [e.slot_name for e in cs.enemies]
    assert slots == ["bot1", "bot2", "fabricator", "bot3", "bot4"]


# ══════════════════════════════════════════════════════════════════════════
# monster/ovicopter/g2 — a freed MIDDLE slot is refilled in place
# ══════════════════════════════════════════════════════════════════════════

def test_the_opening_lay_fills_the_slots_nearest_the_ovicopter():
    """`Slots.LastOrDefault(unoccupied)` — egg5, then egg4, then egg3."""
    cs = _combat(OVICOPTER_NORMAL, 4)
    ovi = cs.enemies[0]
    assert isinstance(ovi, Ovicopter)
    ovi._lay_eggs(cs._ctx())
    assert [e.slot_name for e in cs.enemies] == [
        "egg3", "egg4", "egg5", "ovicopter"]
    assert cs.enemies[-1] is ovi


def test_a_freed_middle_slot_is_refilled_in_place():
    """The case the old index hack could not reach: kill the egg NEXT TO the
    Ovicopter (game slot egg5) and lay again — the game refills egg1, egg2 and
    egg5, so the new egg in egg5 sits at enemy index 4, not index 2."""
    cs = _combat(OVICOPTER_NORMAL, 4)
    ovi = cs.enemies[0]
    ovi._lay_eggs(cs._ctx())
    victim = next(e for e in cs.enemies if e.slot_name == "egg5")
    victim.hp = 0
    cs.enemies.remove(victim)
    ovi._lay_eggs(cs._ctx())
    assert [e.slot_name for e in cs.enemies] == [
        "egg1", "egg2", "egg3", "egg4", "egg5", "ovicopter"]
    fresh = [e for e in cs.enemies if isinstance(e, ToughEgg)]
    assert len(fresh) == 5


def test_the_lay_stops_when_the_row_is_full():
    """`if (text != null)` (Ovicopter.cs:88) — LastOrDefault returns null with no
    default argument, so a full row simply lays nothing."""
    cs = _combat(OVICOPTER_NORMAL, 4)
    ovi = cs.enemies[0]
    ovi._lay_eggs(cs._ctx())
    ovi._lay_eggs(cs._ctx())
    ovi._lay_eggs(cs._ctx())
    assert len([e for e in cs.enemies if isinstance(e, ToughEgg)]) == 5


def test_a_dead_creature_vacates_its_slot():
    """`CombatState.RemoveCreature` (CombatState.cs:287-290) drops the corpse
    out of `Enemies` before the next `Slots.FirstOrDefault(unoccupied)` scan,
    so the slot is free again. The sim keeps corpses in `combat.enemies`, so
    the scan has to skip `is_removed_from_combat` ones itself."""
    cs = _combat(FABRICATOR_NORMAL, 3)
    fab = cs.enemies[0]
    fab._fabricate(cs._ctx())
    assert FABRICATOR_NORMAL.get_next_slot(cs) == "bot3"
    bot1 = next(e for e in cs.enemies if e.slot_name == "bot1")
    bot1.hp = 0
    assert bot1.is_removed_from_combat
    assert FABRICATOR_NORMAL.get_next_slot(cs) == "bot1"


# ══════════════════════════════════════════════════════════════════════════
# encounter/_slot_order — two_tailed_rats' CALL_FOR_BACKUP
# ══════════════════════════════════════════════════════════════════════════

def test_the_three_rats_are_seated_in_the_last_three_slots():
    """TwoTailedRatsNormal.cs:12 declares five names; :36-41 seats the starting
    rats in Slots[2..4], leaving "first"/"second" for the summons."""
    assert list(TWO_TAILED_RATS_NORMAL.slots) == [
        "first", "second", "third", "fourth", "fifth"]
    cs = _combat(TWO_TAILED_RATS_NORMAL, 5)
    assert [e.slot_name for e in cs.enemies] == ["third", "fourth", "fifth"]


def test_the_backup_rat_seats_ahead_of_the_starting_three():
    """`Slots.LastOrDefault(free)` = "second" (TwoTailedRat.cs:180), and the
    re-sort puts index 1 ahead of the starting rats' 2/3/4 — so the summon is
    `enemies[0]`, not the appended `enemies[-1]` the sim used to produce."""
    cs = _combat(TWO_TAILED_RATS_NORMAL, 5)
    rat = cs.enemies[0]
    rat.turns_until_summonable = 0
    rat._call_for_backup(cs._ctx())
    assert [e.slot_name for e in cs.enemies] == [
        "second", "third", "fourth", "fifth"]
    assert cs.enemies[0].net_id == 4  # the newcomer, seated at the FRONT


def test_a_full_row_summons_nothing():
    """`if (!string.IsNullOrEmpty(nextSlot))` (TwoTailedRat.cs:181) — five
    occupied slots means the CALL_FOR_BACKUP body adds no rat at all."""
    cs = _combat(TWO_TAILED_RATS_NORMAL, 5)
    rat = cs.enemies[0]
    rat.turns_until_summonable = 0
    rat._call_for_backup(cs._ctx())
    rat._call_for_backup(cs._ctx())
    assert len(cs.enemies) == 5
    assert not rat._can_summon()  # GetNextSlot is "" — the row is full
    rat._call_for_backup(cs._ctx())
    assert len(cs.enemies) == 5


# ══════════════════════════════════════════════════════════════════════════
# encounter/fogmog/Slots + encounter/_slot_name_not_set — the illusion summons
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("encounter,summon_slot,starter_slot,summon_name", [
    (FOGMOG_NORMAL, "illusion", "fogmog", "EyeWithTeeth"),
    (THE_OBSCURA_NORMAL, "illusion", "obscura", "Parafright"),
])
def test_the_illusion_summon_seats_in_front(
    encounter, summon_slot, starter_slot, summon_name
):
    """Fogmog.cs:66 and TheObscura.cs:84 both hard-code the "illusion" slot,
    which is index 0 of their two-name rows — the summon re-sorts AHEAD of the
    summoner the instant it lands."""
    cs = _combat(encounter, 7)
    starter = cs.enemies[0]
    assert starter.slot_name == starter_slot
    move = getattr(starter, "_illusion_move", None) or starter._illusion
    move(cs._ctx())
    assert [type(e).__name__ for e in cs.enemies][0] == summon_name
    assert [e.slot_name for e in cs.enemies] == [summon_slot, starter_slot]
