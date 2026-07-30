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
from sts2_rl.monsters.hive import OVICOPTER_NORMAL
from sts2_rl.monsters.hive.ovicopter import Ovicopter, ToughEgg


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
