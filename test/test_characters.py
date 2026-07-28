"""The character table (sts2_rl/characters.py) and the character scoping it
imposes on the run layer.

Two things are under test here:

  1. **Ironclad is unchanged.** The table replaced hardcoded literals and
     module-level `IRONCLAD_POOL` defaults; every Ironclad-facing number, pool
     and RNG draw must be exactly what it was. The seeded assertions below are
     the fast tripwire; the conformance suite is the slow one.
  2. **The machinery is generic.** A synthetic second character is registered
     with its own card/relic/potion pools, and the same run layer deals its
     deck, rolls its relics and offers its potions — with no cross-contamination
     in either direction. That is what makes porting Defect (and Silent, Regent,
     Necrobinder) a table row plus content rather than a run.py rewrite.

Character stats are transcribed from src/Core/Models/Characters/*.cs; see the
per-assertion citations.
"""
import random

import pytest

from sts2_rl.characters import (
    ALL_CHARACTER_IDS,
    CHARACTERS,
    Character,
    get_character,
    register_character,
    unregister_character,
)
from sts2_rl.potions import Potion, _POTION_CLASSES, register_potion
from sts2_rl.relics import ALL_RELICS, RelicRarity
from sts2_rl.relics.base import Relic, register_relic
from sts2_rl.run import RunState


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


# ── The table itself ─────────────────────────────────────────────────────


class TestCharacterTable:
    def test_roster_is_model_db_all_characters_in_order(self):
        """ModelDb.cs:123-130 — the order is parity-critical (Orobas NextItem)."""
        assert ALL_CHARACTER_IDS == (
            "ironclad", "silent", "regent", "necrobinder", "defect",
        )

    @pytest.mark.parametrize(
        "char_id,save_id,hp,orb_slots,starting_relic",
        [
            # Ironclad.cs:33,35,57 (BaseOrbSlotCount inherits CharacterModel.cs:88)
            ("ironclad", "CHARACTER.IRONCLAD", 80, 0, "burning_blood"),
            ("silent", "CHARACTER.SILENT", 70, 0, "ring_of_the_snake"),     # Silent.cs:34,60
            ("regent", "CHARACTER.REGENT", 75, 0, "divine_right"),          # Regent.cs:32,58
            ("necrobinder", "CHARACTER.NECROBINDER", 66, 0, "bound_phylactery"),  # Necrobinder.cs:33,63
            ("defect", "CHARACTER.DEFECT", 75, 3, "cracked_core"),          # Defect.cs:28,54,64
        ],
    )
    def test_source_stats(self, char_id, save_id, hp, orb_slots, starting_relic):
        c = CHARACTERS[char_id]
        assert c.save_id == save_id
        assert c.starting_hp == hp
        assert c.starting_gold == 99          # all five: StartingGold => 99
        assert c.max_energy == 3              # CharacterModel.cs:84, none override
        assert c.base_orb_slot_count == orb_slots
        assert c.starting_relics == (starting_relic,)
        assert c.starting_potions == ()       # CharacterModel.cs:102, none override

    def test_ironclad_starting_deck_is_source_order(self):
        """Ironclad.cs:43-55 — 5 Strike, 4 Defend, Bash, in that order."""
        assert CHARACTERS["ironclad"].starting_deck == (
            "strike", "strike", "strike", "strike", "strike",
            "defend", "defend", "defend", "defend",
            "bash",
        )

    def test_only_ironclad_is_ported(self):
        assert CHARACTERS["ironclad"].is_ported
        for char_id in ("silent", "regent", "necrobinder", "defect"):
            assert not CHARACTERS[char_id].is_ported

    def test_unported_character_raises_a_useful_error(self):
        with pytest.raises(NotImplementedError, match="no content ported yet"):
            RunState(character="defect")

    def test_unknown_character_raises(self):
        with pytest.raises(KeyError, match="unknown character"):
            get_character("the_watcher")


# ── Ironclad is unchanged ────────────────────────────────────────────────


class TestIroncladUnchanged:
    def test_defaults(self):
        run = fresh_run()
        assert run.character.id == "ironclad"
        assert run.max_hp == 80 and run.hp == 80 and run.gold == 99
        assert run.max_potions == 3
        assert [c.id for c in run.deck] == [
            "strike", "strike", "strike", "strike", "strike",
            "defend", "defend", "defend", "defend",
            "bash",
        ]

    def test_start_run_grants_burning_blood(self):
        run = fresh_run()
        run.start_run(acts=["overgrowth"])
        assert run.relics[0].id == "burning_blood"

    def test_card_pool_is_the_ironclad_pool(self):
        from sts2_rl.cards import IRONCLAD_POOL

        assert fresh_run().card_pool == IRONCLAD_POOL

    def test_potion_pool_is_character_then_shared(self):
        from sts2_rl.potion_pools import POTION_POOL

        assert fresh_run().potion_pool == POTION_POOL

    def test_relic_grab_bag_order_is_seed_stable(self):
        """The bag feeds a shuffle, so its *order* — not just its membership —
        is what every Ironclad relic pull depends on."""
        a = fresh_run(seed=7).relic_grab_bag
        b = fresh_run(seed=7).relic_grab_bag
        assert a == b
        # Every bag-rarity relic in the catalogue is Ironclad-reachable today,
        # so scoping must not have dropped any of them.
        expected = {
            rid for rid, cls in ALL_RELICS.items()
            if cls.rarity in (
                RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE
            )
        }
        assert set(a) == expected


# ── Genericity: a synthetic second character ─────────────────────────────


@pytest.fixture
def second_character():
    """Register a throwaway character with content of its own.

    Uses real Ironclad cards for the deck/pool (Wave 0 adds no cards), but its
    OWN relic and potion, so the ownership filters are exercised in both
    directions: the guest's content must never reach an Ironclad run, and the
    guest must still see every shared relic and potion."""

    @register_relic
    class _GuestRelic(Relic):
        id = "_guest_relic"
        name = "Guest Relic"
        rarity = RelicRarity.COMMON
        character = "guest"

    # `relics/__init__` snapshots `_RELIC_CLASSES` into ALL_RELICS at import
    # time, which is what a real character-relic FILE would land in (its module
    # is auto-imported before the snapshot). Inject it so this fixture
    # reproduces that leak surface rather than a weaker one.
    ALL_RELICS["_guest_relic"] = _GuestRelic

    @register_potion
    class _GuestPotion(Potion):
        id = "_guest_potion"
        name = "Guest Potion"
        rarity = "common"
        character = "guest"

        def use(self, ctx, target=None):
            pass

    from sts2_rl.cards import IRONCLAD_POOL
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL

    char = register_character(Character(
        id="guest",
        save_id="CHARACTER.GUEST",
        starting_hp=61,
        starting_gold=7,
        starting_deck=("defend", "strike", "strike"),
        starting_relics=("_guest_relic",),
        card_pool=IRONCLAD_POOL,
        relic_pool=IRONCLAD_RELIC_POOL,
        potion_pool=(("_guest_potion", "common"),),
        base_orb_slot_count=2,
    ))
    try:
        yield char
    finally:
        unregister_character("guest")
        ALL_RELICS.pop("_guest_relic", None)
        _POTION_CLASSES.pop("_guest_potion", None)


class TestSecondCharacter:
    def test_run_uses_the_guest_stats_and_deck(self, second_character):
        run = fresh_run(character="guest")
        assert run.character.id == "guest"
        assert run.max_hp == 61 and run.hp == 61 and run.gold == 7
        # The deck is dealt in the table's order, repeats and all.
        assert [c.id for c in run.deck] == ["defend", "strike", "strike"]

    def test_start_run_grants_the_guest_starting_relic(self, second_character):
        run = fresh_run(character="guest")
        run.start_run(acts=["overgrowth"])
        assert [r.id for r in run.relics] == ["_guest_relic"]
        assert not any(r.id == "burning_blood" for r in run.relics)

    def test_guest_relic_never_reaches_an_ironclad_run(self, second_character):
        ironclad = fresh_run()
        assert "_guest_relic" in ALL_RELICS       # registered, so reachable...
        assert "_guest_relic" not in ironclad.relic_grab_bag   # ...but not offered
        assert "_guest_relic" in fresh_run(character="guest").relic_grab_bag

    def test_guest_potion_never_reaches_an_ironclad_run(self, second_character):
        ironclad_ids = {c.id for c in fresh_run()._reward_potion_classes()}
        guest_ids = {c.id for c in fresh_run(character="guest")._reward_potion_classes()}
        assert "_guest_potion" not in ironclad_ids
        assert "_guest_potion" in guest_ids
        # Shared potions stay visible to both.
        assert "fire_potion" in ironclad_ids and "fire_potion" in guest_ids

    def test_registering_a_character_does_not_disturb_ironclad(
        self, second_character
    ):
        """The guest's relic and potion exist in the global registries while
        this test runs — an Ironclad run must be byte-identical anyway."""
        run = fresh_run(seed=3)
        assert run.max_hp == 80 and run.gold == 99
        assert "_guest_relic" not in run.relic_grab_bag
        assert run.potion_pool[0][0] == "blood_potion"   # IroncladPotionPool first

    def test_guest_potion_pool_is_its_own_then_shared(self, second_character):
        from sts2_rl.potion_pools import SHARED_POTION_POOL

        pool = fresh_run(character="guest").potion_pool
        assert pool == (("_guest_potion", "common"),) + SHARED_POTION_POOL


# ── The pool defaults are gone ───────────────────────────────────────────


class TestNoSilentIroncladDefault:
    """Every generator takes its pool explicitly; a missing one is a TypeError,
    not a silent Ironclad fallback."""

    def test_card_generators_require_a_pool(self):
        from sts2_rl.cards.pool import (
            get_distinct_for_combat_parity,
            get_for_combat_parity,
            pool_card_ids,
            random_pool_cards,
            reward_pool_card_ids,
        )

        rng = random.Random(0)
        for call in (
            lambda: pool_card_ids(),
            lambda: reward_pool_card_ids(),
            lambda: random_pool_cards(rng, 1),
            lambda: get_for_combat_parity(rng, 1),
            lambda: get_distinct_for_combat_parity(rng, 1),
        ):
            with pytest.raises(TypeError, match="pool is required"):
                call()

    def test_transform_options_require_a_pool(self):
        from sts2_rl.cards import make_card
        from sts2_rl.cards.pool import transform_options_in_combat

        with pytest.raises(TypeError, match="pool is required"):
            transform_options_in_combat(make_card("strike"))

    def test_potion_generators_require_a_pool(self):
        from sts2_rl.potion_pools import (
            generate_random_potion,
            generate_random_potion_in_combat,
            generate_random_potions,
            legacy_random_potion_out_of_combat,
        )

        rng = random.Random(0)
        with pytest.raises(TypeError, match="pool is required"):
            legacy_random_potion_out_of_combat(rng)
        for call in (
            lambda: generate_random_potion(None),
            lambda: generate_random_potion_in_combat(None),
            lambda: generate_random_potions(None, 1),
        ):
            with pytest.raises(TypeError, match="pool is required"):
                call()

    def test_every_registry_scan_is_character_scoped(self):
        """`relics/` auto-imports into ALL_RELICS and `@register_potion` fills
        _POTION_CLASSES, so ANY iteration over those registries can offer a
        character's content in another character's run. Every such scan must
        sit next to an `owns_relic` / `owns_potion` guard."""
        import pathlib
        import re

        scan = re.compile(
            r"(ALL_RELICS|ALL_POTIONS|_POTION_CLASSES|_RELIC_CLASSES)"
            r"\.(items|values)\(\)"
        )
        # relics/__init__ builds the catalogue itself; potion_pools indexes the
        # explicit (id, rarity) rosters, which are already character-scoped.
        allowed = {"relics/__init__.py", "potion_pools.py"}
        root = pathlib.Path(__file__).resolve().parent.parent / "sts2_rl"
        unguarded = []
        for path in root.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            if scan.search(text) and "owns_relic" not in text and (
                "owns_potion" not in text
            ):
                unguarded.append(rel)
        assert unguarded == []

    def test_no_module_reaches_for_the_ironclad_pool_by_name(self):
        """`IRONCLAD_POOL` may only be named where it is defined, re-exported,
        or bound to the Ironclad row — never inside run/combat logic, which is
        exactly how the old silent default leaked."""
        import pathlib

        allowed = {"cards/pool.py", "cards/__init__.py", "characters.py"}
        root = pathlib.Path(__file__).resolve().parent.parent / "sts2_rl"
        offenders = []
        for path in root.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel in allowed:
                continue
            if "IRONCLAD_POOL" in path.read_text(encoding="utf-8"):
                offenders.append(rel)
        assert offenders == []
