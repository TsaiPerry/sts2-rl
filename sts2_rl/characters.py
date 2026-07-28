"""The character table — every per-character value the run layer reads.

Mirrors ``CharacterModel`` (``src/Core/Models/CharacterModel.cs``) and its five
concrete subclasses (``src/Core/Models/Characters/*.cs``). The sim used to hard-
code Ironclad's numbers as ``RunState`` class constants and reach the Ironclad
card pool through module-level defaults; this module replaces both with data, so
a second character is a table row plus its content rather than an edit to the
run layer.

Everything here is transcribed verbatim from the source. The five characters and
their declaration ORDER are ``ModelDb.AllCharacters`` (ModelDb.cs:123-130) —
that order is parity-critical, because Orobas picks the Sea Glass character with
a ``NextItem`` over it (``events/orobas.py``).

Only Ironclad's content is ported so far. The other four rows carry their real,
source-verified stats but empty pools, and :func:`get_character` marks them
unplayable — ``RunState(character="defect")`` raises a message naming what is
missing rather than silently dealing an empty deck. Porting a character means
filling that row's ``starting_deck`` / ``card_pool`` / ``relic_pool`` /
``potion_pool`` in, not touching ``run.py``.

**Content ownership.** A relic or potion class that belongs to one character
sets ``character = "<id>"`` on the class (the default ``None`` means the shared
pool, available to everyone). That attribute is what keeps a character's content
out of every other character's grab bags — see ``RunState``'s bag builders.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Character:
    """One playable character (``CharacterModel``).

    Field-by-field source map:

    ==========================  ==========================================
    field                       source
    ==========================  ==========================================
    ``id``                      lowercase class name; the sim's handle
    ``save_id``                 ``SerializablePlayer.CharacterId``
    ``starting_hp``             ``CharacterModel.StartingHp`` (abstract)
    ``starting_gold``           ``CharacterModel.StartingGold`` (abstract)
    ``max_energy``              ``CharacterModel.cs:84`` (virtual, 3)
    ``base_orb_slot_count``     ``CharacterModel.cs:88`` (virtual, 0)
    ``starting_deck``           ``CharacterModel.StartingDeck``, in order
    ``starting_relics``         ``CharacterModel.StartingRelics``, in order
    ``starting_potions``        ``CharacterModel.cs:102`` (virtual, empty)
    ``card_pool``               ``CharacterModel.CardPool``
    ``relic_pool``              ``CharacterModel.RelicPool``
    ``potion_pool``             ``CharacterModel.PotionPool``
    ==========================  ==========================================

    ``starting_deck`` lists card ids WITH repeats, in the source's exact array
    order — the deck is dealt in that order and the combat-start shuffle is
    order-dependent, so it is not a multiset.
    """

    id: str
    save_id: str
    starting_hp: int
    starting_gold: int
    # CharacterModel.StartingDeck / StartingRelics — ids, source order.
    starting_deck: tuple[str, ...] = ()
    starting_relics: tuple[str, ...] = ()
    # CharacterModel.cs:102 StartingPotions — empty for all five characters;
    # carried so a future character with one needs no run.py change.
    starting_potions: tuple[str, ...] = ()
    # The character's own pools. `card_pool` is card ids in CardPool
    # declaration order (parity-critical — reward/transform generation indexes
    # a rarity-filtered slice of it). `relic_pool` is (RELIC.ID, rarity) pairs
    # as relic_pools.py stores them; `potion_pool` is (potion_id, rarity) pairs
    # as potion_pools.py stores them. Empty until the character is ported.
    card_pool: tuple[str, ...] = ()
    relic_pool: tuple[tuple[str, str], ...] = ()
    potion_pool: tuple[tuple[str, str], ...] = ()
    # CharacterModel.cs:84 — every one of the five inherits the base 3.
    max_energy: int = 3
    # CharacterModel.cs:88 — 0 for everyone except Defect (Defect.cs:64).
    base_orb_slot_count: int = 0

    @property
    def is_ported(self) -> bool:
        """True once this character has enough content to play a run.

        A character with no starting deck and no card pool is a table row
        waiting for its content waves, not a playable character."""
        return bool(self.starting_deck) and bool(self.card_pool)


def _ironclad() -> Character:
    """Ironclad.cs — the one fully ported character."""
    from .cards.pool import IRONCLAD_POOL
    from .potion_pools import IRONCLAD_POTION_POOL
    from .relic_pools import IRONCLAD_RELIC_POOL

    return Character(
        id="ironclad",
        save_id="CHARACTER.IRONCLAD",
        starting_hp=80,                       # Ironclad.cs:33
        starting_gold=99,                     # Ironclad.cs:35
        # Ironclad.cs:43-55 — 5 Strike, 4 Defend, Bash.
        starting_deck=(
            "strike", "strike", "strike", "strike", "strike",
            "defend", "defend", "defend", "defend",
            "bash",
        ),
        starting_relics=("burning_blood",),   # Ironclad.cs:57
        card_pool=IRONCLAD_POOL,              # Ironclad.cs:37
        relic_pool=IRONCLAD_RELIC_POOL,       # Ironclad.cs:41
        potion_pool=IRONCLAD_POTION_POOL,     # Ironclad.cs:39
    )


def _unported(
    char_id: str,
    save_id: str,
    starting_hp: int,
    starting_relics: tuple[str, ...],
    base_orb_slot_count: int = 0,
) -> Character:
    """A source-verified stat row for a character whose content isn't ported.

    The starting deck and the three pools stay empty on purpose: naming cards
    that no ``@register_card`` has created would turn a clear "not ported yet"
    error into a ``KeyError`` deep inside deck construction. Fill them in (and
    delete this helper's use for that character) as part of porting it."""
    return Character(
        id=char_id,
        save_id=save_id,
        starting_hp=starting_hp,
        starting_gold=99,          # all five share StartingGold => 99
        starting_relics=starting_relics,
        base_orb_slot_count=base_orb_slot_count,
    )


def _build_registry() -> dict[str, Character]:
    """ModelDb.AllCharacters (ModelDb.cs:123-130), in declaration order."""
    chars = (
        _ironclad(),
        # Silent.cs:34 StartingHp 70; :60 RingOfTheSnake. Deck (Silent.cs:44-58)
        # is 12 cards: 5 Strike, 5 Defend, Neutralize, Survivor.
        _unported("silent", "CHARACTER.SILENT", 70, ("ring_of_the_snake",)),
        # Regent.cs:32 StartingHp 75; :58 DivineRight. Deck (Regent.cs:44-56):
        # 4 Strike, 4 Defend, FallingStar, Venerate.
        _unported("regent", "CHARACTER.REGENT", 75, ("divine_right",)),
        # Necrobinder.cs:33 StartingHp 66; :63 BoundPhylactery. Deck
        # (Necrobinder.cs:49-61): 4 Strike, 4 Defend, Bodyguard, Unleash.
        _unported(
            "necrobinder", "CHARACTER.NECROBINDER", 66, ("bound_phylactery",)
        ),
        # Defect.cs:28 StartingHp 75; :54 CrackedCore; :64 BaseOrbSlotCount 3.
        # Deck (Defect.cs:40-52): 4 Strike, 4 Defend, Zap, Dualcast.
        _unported(
            "defect", "CHARACTER.DEFECT", 75, ("cracked_core",),
            base_orb_slot_count=3,
        ),
    )
    return {c.id: c for c in chars}


CHARACTERS: dict[str, Character] = _build_registry()

# ModelDb.AllCharacters order, as ids. Orobas draws a NextItem over this list
# minus the player's own character (Orobas.cs GenerateInitialOptions), so the
# ORDER is parity-critical — append-only, and only in the game's order.
ALL_CHARACTER_IDS: tuple[str, ...] = tuple(CHARACTERS)

DEFAULT_CHARACTER = "ironclad"


def register_character(character: Character) -> Character:
    """Add a character to the registry (used by tests and future ports).

    Appends to ``ALL_CHARACTER_IDS``. Note that appending a character the game
    does not have would desync Orobas' ``NextItem``, so this is for the five
    real characters and for tests that unregister afterwards."""
    global ALL_CHARACTER_IDS
    if character.id in CHARACTERS:
        raise ValueError(f"character {character.id!r} is already registered")
    CHARACTERS[character.id] = character
    ALL_CHARACTER_IDS = tuple(CHARACTERS)
    return character


def unregister_character(char_id: str) -> None:
    """Remove a registered character (test cleanup for register_character)."""
    global ALL_CHARACTER_IDS
    CHARACTERS.pop(char_id, None)
    ALL_CHARACTER_IDS = tuple(CHARACTERS)


def get_character(character: "str | Character") -> Character:
    """Resolve a character id (or pass a ``Character`` through).

    Raises ``NotImplementedError`` for a registered-but-unported character, so
    starting such a run fails with a message naming the missing content instead
    of dealing an empty deck."""
    if isinstance(character, Character):
        resolved = character
    else:
        try:
            resolved = CHARACTERS[character]
        except KeyError:
            known = ", ".join(sorted(CHARACTERS))
            raise KeyError(
                f"unknown character {character!r} (known: {known})"
            ) from None
    if not resolved.is_ported:
        raise NotImplementedError(
            f"character {resolved.id!r} has no content ported yet: its "
            f"starting deck and card/relic/potion pools are empty. Fill in "
            f"CHARACTERS[{resolved.id!r}] in sts2_rl/characters.py as part of "
            f"porting it."
        )
    return resolved
