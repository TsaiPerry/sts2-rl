"""GAP-QUEUE entries 65 and 66 — monster-side stream desyncs.

65 `monster/_encounter_selection_rng`: `EncounterModel.GenerateMonstersWithSlots`
   (EncounterModel.cs:259-277) seeds a per-encounter `Rng` from
   `runState.Rng.Seed + runState.TotalFloor + hash(Id.Entry)` and every
   `GenerateMonsters` override composes off THAT stream. Three sim builders
   still drew their composition off the shared combat `random.Random`:
   CorpseSlugsNormal/Weak, SlitheringStranglerNormal, ScrollsOfBiting*.

66 `monster/_off_stream_draw`: `Fabricator.cs:115` picks its spawned bot with
   `base.RunRng.MonsterAi.NextItem(items)` and `ThievingHopper.cs:222` picks the
   stolen card with `base.RunRng.CombatCardGeneration.NextItem(enumerable)`;
   both sim sites drew off the shared combat `random.Random`.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter
from sts2_rl.rng import Rng, RunRngSet, make_encounter_rng


def _peek(stream: Rng) -> Rng:
    """A detached copy of `stream` at its current position, for computing what
    the next draw off that stream WILL be without consuming it."""
    return Rng(seed=stream.seed, counter=stream.counter)


class _NoSharedChoice:
    """Proxy over the legacy shared `random.Random` that fails loudly on
    `.choice(...)` — the exact call the two entry-66 sites used to make."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def choice(self, seq):
        raise AssertionError(
            "in-combat pick taken from the legacy shared rng, not the named stream")


# ── 65. Corpse Slugs ─────────────────────────────────────────────────────────
# CorpseSlugsNormal.cs:32 / CorpseSlugsWeak.cs:32 both call
# CorpseSlug.EnsureCorpseSlugsStartWithDifferentMoves(monsters, base.Rng), which
# is one `rng.NextInt(3)` (CorpseSlug.cs:138) staggered +1 per slug.

def _corpse_encounters():
    from sts2_rl.monsters.underdocks.corpse_slug import (
        CORPSE_SLUGS_NORMAL, CORPSE_SLUGS_WEAK)
    return [(CORPSE_SLUGS_NORMAL, 3), (CORPSE_SLUGS_WEAK, 2)]


@pytest.mark.parametrize("floor", [3, 7, 11, 15, 19])
@pytest.mark.parametrize("weak", [False, True], ids=["normal", "weak"])
def test_corpse_slug_starters_come_from_the_per_encounter_rng(floor, weak):
    enc, count = _corpse_encounters()[1 if weak else 0]
    rs = RunRngSet(f"SEL65SLUG{floor}")
    first = make_encounter_rng(rs.seed, floor, enc.entry).next_int(3)

    sel = make_encounter_rng(rs.seed, floor, enc.entry)
    combat = CombatState(rng=random.Random(4242), rng_set=rs, encounter=enc,
                         encounter_selection_rng=sel)

    assert [m._starter_move_idx for m in combat.enemies] == [
        (first + k) % 3 for k in range(count)]
    # the game draws the selection stream exactly once here; the sim drew 0
    assert sel.counter == 1


def test_corpse_slug_starters_reproduce_across_identical_parity_runs():
    """The entry's replay-non-determinism observable: with no shared rng seeded
    (the state a parity replay is in), the sim returned a different stagger on
    each of four consecutive constructions."""
    from sts2_rl.monsters.underdocks.corpse_slug import CORPSE_SLUGS_NORMAL

    seen = set()
    for _ in range(4):
        rs = RunRngSet("SEL65REPLAY")
        sel = make_encounter_rng(rs.seed, 5, CORPSE_SLUGS_NORMAL.entry)
        combat = CombatState(rng_set=rs, encounter=CORPSE_SLUGS_NORMAL,
                             encounter_selection_rng=sel)
        seen.add(tuple(m._starter_move_idx for m in combat.enemies))
    assert len(seen) == 1, f"corpse slug stagger is not reproducible: {seen}"


def test_corpse_slug_legacy_arm_still_uses_the_shared_rng():
    from sts2_rl.monsters.underdocks.corpse_slug import CORPSE_SLUGS_NORMAL

    a = CombatState(rng=random.Random(99), encounter=CORPSE_SLUGS_NORMAL)
    b = CombatState(rng=random.Random(99), encounter=CORPSE_SLUGS_NORMAL)
    assert ([m._starter_move_idx for m in a.enemies]
            == [m._starter_move_idx for m in b.enemies])


# ── 65. Slithering Strangler ─────────────────────────────────────────────────
# SlitheringStranglerNormal.cs:57,77,88,90 — one NextItem over the
# SecondaryEnemyType enum (SnappingJaxfruit, MediumSlime, SmallSlimes), then
# 0 / 1 / 2 further NextItems, then the Strangler appended last.

@pytest.mark.parametrize("floor", [2, 6, 10, 14, 18, 22, 26, 30])
def test_slithering_strangler_composition_comes_from_the_per_encounter_rng(floor):
    from sts2_rl.monsters.overgrowth.slimes import (
        LeafSlimeM, LeafSlimeS, TwigSlimeM, TwigSlimeS)
    from sts2_rl.monsters.overgrowth.slithering_strangler import (
        SLITHERING_STRANGLER_NORMAL, SlitheringStrangler)
    from sts2_rl.monsters.overgrowth.snapping_jaxfruit import SnappingJaxfruit

    enc = SLITHERING_STRANGLER_NORMAL
    rs = RunRngSet(f"SEL65STR{floor}")

    peek = make_encounter_rng(rs.seed, floor, enc.entry)
    kind = peek.next_item(["SnappingJaxfruit", "MediumSlime", "SmallSlimes"])
    if kind == "SnappingJaxfruit":
        want = [SnappingJaxfruit]
    elif kind == "MediumSlime":
        want = [peek.next_item([LeafSlimeM, TwigSlimeM])]
    else:
        want = [peek.next_item([LeafSlimeS, TwigSlimeS]),
                peek.next_item([LeafSlimeS, TwigSlimeS])]
    want.append(SlitheringStrangler)

    sel = make_encounter_rng(rs.seed, floor, enc.entry)
    combat = CombatState(rng=random.Random(4242), rng_set=rs, encounter=enc,
                         encounter_selection_rng=sel)

    assert [type(m) for m in combat.enemies] == want
    assert sel.counter == peek.counter


# ── 65. Scrolls of Biting ────────────────────────────────────────────────────
# ScrollsOfBiting{Weak,Normal}.cs:22-25 — one base.Rng.NextInt(3) staggered
# +1/+2 across the first three scrolls; the normal fight's 4th is pinned to 2.

@pytest.mark.parametrize("floor", [0, 4, 8, 12, 16])
@pytest.mark.parametrize("count", [3, 4], ids=["weak", "normal"])
def test_scrolls_of_biting_starters_come_from_the_per_encounter_rng(floor, count):
    from sts2_rl.monsters.glory.scroll_of_biting import (
        SCROLLS_OF_BITING_NORMAL, SCROLLS_OF_BITING_WEAK)

    enc = SCROLLS_OF_BITING_WEAK if count == 3 else SCROLLS_OF_BITING_NORMAL
    rs = RunRngSet(f"SEL65SCR{floor}")
    first = make_encounter_rng(rs.seed, floor, enc.entry).next_int(3)

    sel = make_encounter_rng(rs.seed, floor, enc.entry)
    combat = CombatState(rng=random.Random(4242), rng_set=rs, encounter=enc,
                         encounter_selection_rng=sel)

    want = [(first + i) % 3 for i in range(3)]
    if count == 4:
        want.append(2)
    assert [m._starter_move_idx for m in combat.enemies] == want
    assert sel.counter == 1


# ── 65. Two more sites of the same mechanism, not in the entry's `sites` list
# DecimillipedeElite.cs:40 and TwoTailedRatsNormal.cs:33 are the identical
# `base.Rng.NextInt(3)` stagger the entry describes for Corpse Slug.

@pytest.mark.parametrize("floor", [1, 5, 9, 13, 17])
@pytest.mark.parametrize("which", ["decimillipede", "two_tailed_rats"])
def test_staggered_trio_starters_come_from_the_per_encounter_rng(floor, which):
    if which == "decimillipede":
        from sts2_rl.monsters.hive.decimillipede import DECIMILLIPEDE_ELITE as enc
        attr = "starter_move_idx"
    else:
        from sts2_rl.monsters.underdocks.two_tailed_rat import (
            TWO_TAILED_RATS_NORMAL as enc)
        attr = "_starter_move_idx"

    rs = RunRngSet(f"SEL65TRIO{floor}")
    first = make_encounter_rng(rs.seed, floor, enc.entry).next_int(3)

    sel = make_encounter_rng(rs.seed, floor, enc.entry)
    combat = CombatState(rng=random.Random(4242), rng_set=rs, encounter=enc,
                         encounter_selection_rng=sel)

    assert [getattr(m, attr) for m in combat.enemies] == [
        (first + k) % 3 for k in range(3)]
    assert sel.counter == 1


# ── 66. Fabricator ───────────────────────────────────────────────────────────

def test_fabricator_spawn_pick_comes_from_the_monster_ai_stream():
    from sts2_rl.monsters.glory.fabricator import (
        _AGGRO_SPAWNS, FABRICATOR_NORMAL)

    rs = RunRngSet("SEL66FAB")
    combat = CombatState(rng=random.Random(5), rng_set=rs,
                         encounter=FABRICATOR_NORMAL)
    fab = combat.enemies[0]
    expected = _peek(rs.monster_ai).next_item(list(_AGGRO_SPAWNS))

    combat._rng = _NoSharedChoice(combat._rng)
    fab._spawn_bot(combat._ctx(), _AGGRO_SPAWNS)

    assert fab._last_spawned is expected
    # MOVED 2026-07-29 (round 7, monster/fabricator/g5): this asserted
    # `enemies[-1]`, i.e. that the bot was APPENDED. Fabricator.cs:115 passes
    # `Encounter.GetNextSlot(CombatState)` to CreatureCmd.Add and the row is
    # [bot1, bot2, fabricator, bot3, bot4] (FabricatorNormal.cs:19), so the first
    # bot takes bot1 and seats in FRONT of the Fabricator — the game's Enemies
    # after the opening FABRICATE are [bot, Fabricator]. The pick itself (what
    # this test is for) is unchanged.
    assert isinstance(combat.enemies[0], expected)
    assert combat.enemies[-1] is fab


def test_fabricator_spawn_pick_is_independent_of_the_shared_rng():
    from sts2_rl.monsters.glory.fabricator import (
        _AGGRO_SPAWNS, FABRICATOR_NORMAL)

    picks = []
    for shared_seed in (1, 2, 3, 4, 5, 6, 7, 8):
        rs = RunRngSet("SEL66FAB2")
        combat = CombatState(rng=random.Random(shared_seed), rng_set=rs,
                             encounter=FABRICATOR_NORMAL)
        fab = combat.enemies[0]
        fab._spawn_bot(combat._ctx(), _AGGRO_SPAWNS)
        # Hold the reference: the spawned bot seats at bot1, so after the spawn
        # `enemies[0]` is the BOT, not the Fabricator (monster/fabricator/g5).
        picks.append(fab._last_spawned)
    assert len(set(picks)) == 1, f"shared-rng-dependent spawn pick: {picks}"


# ── 66. Thieving Hopper ──────────────────────────────────────────────────────

def test_thieving_hopper_steal_pick_comes_from_the_card_gen_stream():
    from sts2_rl.monsters.hive.thieving_hopper import ThievingHopper

    rs = RunRngSet("SEL66HOP")
    combat = CombatState(rng=random.Random(5), rng_set=rs,
                         encounter=Encounter("thieving_hopper", [ThievingHopper]))
    hopper = combat.enemies[0]
    player = combat.player

    candidates = list(player.draw_pile) + list(player.discard_pile)
    for predicate in ThievingHopper._steal_priorities():
        subset = [c for c in candidates if predicate(c)]
        if subset:
            candidates = subset
            break
    assert len(candidates) > 1  # a one-card pool would not discriminate
    expected = _peek(rs.combat_card_generation).next_item(candidates)

    before = rs.combat_card_generation.counter
    combat._rng = _NoSharedChoice(combat._rng)
    hopper._thievery(combat._ctx())

    assert rs.combat_card_generation.counter == before + 1
    assert expected not in player.draw_pile
    assert expected not in player.discard_pile
    assert hopper.powers["swipe"].stolen_card is expected
