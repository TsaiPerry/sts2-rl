from __future__ import annotations

import random

from .base import Card, CardRarity, CardType, make_card, _CARD_CLASSES

# The implemented portion of the Ironclad card pool (IroncladCardPool.cs).
# Basics (Strike/Defend/Bash) and Ancients (Break/Corruption) are listed for
# completeness but filtered out of in-combat generation, mirroring
# CardFactory.FilterForCombat. Tokens/statuses/curses are not pool cards.
IRONCLAD_POOL: tuple[str, ...] = (
    # Basics
    "strike", "defend", "bash",
    # Attacks
    "anger", "ashen_strike", "bludgeon", "body_slam", "break", "breakthrough",
    "bully", "cinder", "conflagration", "dismantle", "feed", "fiend_fire",
    "fight_me", "headbutt", "hemokinesis", "howl_from_beyond", "iron_wave",
    "mangle", "molten_fist", "pacts_end", "perfected_strike", "pillage",
    "pommel_strike", "rampage", "setup_strike", "spite", "stomp",
    "sword_boomerang", "tear_asunder", "thrash", "thunderclap", "twin_strike",
    "unrelenting", "uppercut", "whirlwind",
    # Skills
    "armaments", "battle_trance", "blood_wall", "bloodletting", "brand",
    "burning_pact", "cascade", "colossus", "dominate", "drum_of_battle",
    "evil_eye", "expect_a_fight", "flame_barrier", "forgotten_ritual",
    "havoc", "impervious", "infernal_blade", "not_yet", "offering",
    "one_two_punch", "primal_force", "rage", "second_wind", "shrug_it_off",
    "stoke", "taunt", "tremble", "true_grit",
    # Powers
    "aggression", "barricade", "corruption", "crimson_mantle", "cruelty",
    "dark_embrace", "demon_form", "feel_no_pain", "hellraiser", "inferno",
    "inflame", "juggernaut", "juggling", "pyre", "rupture", "stampede",
    "stone_armor", "unmovable", "vicious",
)


def pool_card_ids(
    card_type: CardType | None = None,
    pool: tuple[str, ...] = IRONCLAD_POOL,
) -> list[str]:
    """Ids eligible for in-combat card generation (mirrors FilterForCombat:
    Basic and Ancient cards are excluded), optionally filtered by card type."""
    ids = []
    for card_id in pool:
        cls = _CARD_CLASSES[card_id]
        if cls.rarity in (CardRarity.BASIC, CardRarity.ANCIENT):
            continue
        if card_type is not None and cls.card_type != card_type:
            continue
        ids.append(card_id)
    return ids


def random_pool_cards(
    rng: random.Random,
    count: int,
    card_type: CardType | None = None,
    distinct: bool = False,
) -> list[Card]:
    """Generate random cards from the character pool for in-combat effects.

    Mirrors CardFactory.GetForCombat (uniform, with replacement) and
    GetDistinctForCombat (distinct=True) — used by e.g. Infernal Blade
    (1 distinct Attack) and Stoke (N cards, repeats allowed).
    """
    options = pool_card_ids(card_type)
    if not options:
        return []
    if distinct:
        chosen = rng.sample(options, min(count, len(options)))
    else:
        chosen = [rng.choice(options) for _ in range(count)]
    return [make_card(card_id) for card_id in chosen]
