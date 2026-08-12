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


def test_reusing_a_slot_evicts_the_corpse_still_holding_it():
    """The sibling of the test above, WITHOUT its `cs.enemies.remove(victim)`.

    That line stands in for `CombatState.RemoveCreature`, which the sim does
    not do — corpses stay in `combat.enemies` so enemy indices are stable. But
    the free-slot scan skips them (`_occupied` filters `is_removed_from_combat`,
    the test below this one), so a corpse's slot IS handed to the next egg, and
    nothing used to evict the corpse: the list grew by one per recycled egg,
    forever.

    That is not cosmetic. Both the observation (`_enemies_rows`) and the action
    mask (`combat_action_mask`'s `i < MAX_ENEMIES`) address enemies by raw list
    index over `MAX_ENEMIES`=6 rows, so the overflow pushed LIVING enemies out
    of both — including, measured on this encounter, the Ovicopter itself.
    """
    cs = _combat(OVICOPTER_NORMAL, 4)
    ovi = cs.enemies[0]
    ovi._lay_eggs(cs._ctx())
    victim = next(e for e in cs.enemies if e.slot_name == "egg5")
    victim.hp = 0
    assert victim.is_removed_from_combat, "fixture sanity: the egg is a corpse"
    assert victim in cs.enemies, "the sim keeps corpses in the list"

    ovi._lay_eggs(cs._ctx())

    assert victim not in cs.enemies, (
        "the corpse kept its list entry while a live egg took its slot")
    assert [e.slot_name for e in cs.enemies] == [
        "egg1", "egg2", "egg3", "egg4", "egg5", "ovicopter"]
    assert len(cs.enemies) == len(OVICOPTER_NORMAL.slots)


def test_a_recycling_encounter_never_outgrows_the_targetable_window():
    """The property the fix exists for: however many eggs are laid, killed and
    relaid, the enemy list stays within the slot row — so no living creature
    can slide past `MAX_ENEMIES` into the untargetable, unobservable tail."""
    from sts2_rl.full_env import MAX_ENEMIES

    cs = _combat(OVICOPTER_NORMAL, 4)
    ovi = cs.enemies[0]
    for _round in range(20):
        ovi._lay_eggs(cs._ctx())
        for egg in [e for e in cs.enemies if isinstance(e, ToughEgg)][:2]:
            egg.hp = 0
        assert len(cs.enemies) <= MAX_ENEMIES, (
            f"enemy list grew to {len(cs.enemies)} > MAX_ENEMIES={MAX_ENEMIES}")
        living = [i for i, e in enumerate(cs.enemies) if not e.is_gone]
        assert all(i < MAX_ENEMIES for i in living), (
            f"living enemies stranded past the cap at {living}")
    assert ovi in cs.enemies and not ovi.is_gone


def test_no_ported_encounter_can_outgrow_the_targetable_window():
    """The general form of the two Ovicopter tests above, swept over EVERY
    ported encounter rather than the one that happened to be caught.

    A recycling summoner is the only way `combat.enemies` can exceed the
    encounter's own creature count, and both readers of that list index it
    positionally against `MAX_ENEMIES`. This drives each encounter with a
    masked-random policy and asserts the list never outgrows the window --
    which is what keeps the `combat.enemies` overflow warning unreachable.

    Living Fog is the second encounter this caught (its `_bloat` hand-rolled an
    insertion index instead of using the slot row, so exploded bombs piled up
    and stranded live enemies at indices 5-6 on seed 11).
    """
    import random as _random

    from sts2_rl.full_env import MAX_ENEMIES, STS2FullCombatEnv
    from sts2_rl.monsters.glory import ENCOUNTERS as GLORY
    from sts2_rl.monsters.hive import ENCOUNTERS as HIVE
    from sts2_rl.monsters.overgrowth import ENCOUNTERS as OVER
    from sts2_rl.monsters.underdocks import ENCOUNTERS as UNDER

    encounters = {}
    for act, table in (("overgrowth", OVER), ("underdocks", UNDER),
                       ("hive", HIVE), ("glory", GLORY)):
        for key, enc in table.items():
            encounters[f"{act}/{key}"] = enc
    assert len(encounters) > 50, "sanity: the sweep must actually cover the tables"

    # 15 seeds, not 3: the Living Fog overflow this test was written for first
    # appears at seed 11 (mutation-checked — at 3 seeds the sweep passes with
    # the `_bloat` slot port reverted, which would have made it decorative).
    for name, enc in sorted(encounters.items()):
        for seed in range(15):
            env = STS2FullCombatEnv(encounters=[enc])
            env.reset(seed=seed)
            state = env._state
            rng = _random.Random(seed)
            for _ in range(300):
                if state is None or not state.enemies:
                    break
                assert len(state.enemies) <= MAX_ENEMIES, (
                    f"{name} seed {seed}: enemy list grew to "
                    f"{len(state.enemies)} > MAX_ENEMIES={MAX_ENEMIES}, so the "
                    f"observation truncates and the mask cannot reach the tail")
                legal = [i for i, m in enumerate(env.action_masks()) if m]
                if not legal:
                    break
                *_, term, trunc, _ = env.step(rng.choice(legal))
                if term or trunc:
                    break


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
