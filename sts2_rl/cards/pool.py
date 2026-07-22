from __future__ import annotations

import random

from .base import Card, CardRarity, CardType, make_card, _CARD_CLASSES

# The implemented portion of the Ironclad card pool (IroncladCardPool.cs), in
# the game's exact GenerateAllCards() declaration order (alphabetical by C#
# class name). This ORDER is parity-critical: reward/transform generation does
# `Rng.NextItem(pool.Where(rarity == r))`, indexing into the rarity-filtered
# candidate list *in pool order* — a different order picks a different card for
# the same RNG draw. The game's 87-card list minus the two cards
# CardFactory.FilterForPlayerCount removes in single player (Tank, Demonic
# Shield), which are therefore never in the single-player candidate set.
# Basics (Strike/Defend/Bash) and Ancients (Break/Corruption) stay in the list
# for completeness but are filtered out of generation (CardFactory.FilterForCombat
# / the reward rarity roll). Tokens/statuses/curses are not pool cards.
IRONCLAD_POOL: tuple[str, ...] = (
    "aggression", "anger", "armaments", "ashen_strike", "barricade", "bash",
    "battle_trance", "blood_wall", "bloodletting", "bludgeon", "body_slam",
    "brand", "break", "breakthrough", "bully", "burning_pact", "cascade",
    "cinder", "colossus", "conflagration", "corruption", "crimson_mantle",
    "cruelty", "dark_embrace", "defend", "demon_form", "dismantle", "dominate",
    "drum_of_battle", "evil_eye", "expect_a_fight", "feed", "feel_no_pain",
    "fiend_fire", "fight_me", "flame_barrier", "forgotten_ritual", "havoc",
    "headbutt", "hellraiser", "hemokinesis", "howl_from_beyond", "impervious",
    "infernal_blade", "inferno", "inflame", "iron_wave", "juggernaut",
    "juggling", "mangle", "molten_fist", "not_yet", "offering", "one_two_punch",
    "pacts_end", "perfected_strike", "pillage", "pommel_strike", "primal_force",
    "pyre", "rage", "rampage", "rupture", "second_wind", "setup_strike",
    "shrug_it_off", "spite", "stampede", "stoke", "stomp", "stone_armor",
    "strike", "sword_boomerang", "taunt", "tear_asunder", "thrash",
    "thunderclap", "tremble", "true_grit", "twin_strike", "unmovable",
    "unrelenting", "uppercut", "vicious", "whirlwind",
)


# The Colorless card pool (ColorlessCardPool.cs), in the source's order,
# minus the 11 multiplayer-only cards (Beacon of Hope, Believe in You,
# Coordinate, Gang Up, Huddle Up, Intercept, Knockdown, Lift, Mimic, Rally,
# Tag Team) that CardFactory.FilterForPlayerCount removes in single player —
# the same treatment as Ironclad's Tank / Demonic Shield. Colorless cards
# are only Uncommon or Rare; the shop's two Colorless slots and transforms
# of Event/Ancient/Token/Quest cards draw from here.
COLORLESS_POOL: tuple[str, ...] = (
    "alchemize", "anointed", "automation", "beat_down", "bolas", "calamity",
    "catastrophe", "dark_shackles", "discovery", "dramatic_entrance",
    "entropy", "equilibrium", "eternal_armor", "fasten", "finesse",
    "fisticuffs", "flash_of_steel", "gold_axe", "hand_of_greed", "hidden_gem",
    "impatience", "jack_of_all_trades", "jackpot", "master_of_strategy",
    "mayhem", "mind_blast", "nostalgia", "omnislice", "panache",
    "panic_button", "prep_time", "production", "prolong", "prowess",
    "purity", "rend", "restlessness", "rolling_boulder", "salvo", "scrawl",
    "secret_technique", "secret_weapon", "seeker_strike", "shockwave",
    "splash", "stratagem", "the_bomb", "the_gambit", "thinking_ahead",
    "thrumming_hatchet", "ultimate_defend", "ultimate_strike", "volley",
)


# The curse card pool (CurseCardPool.cs) — all 18 curses, in the source's
# order. Random curse generation draws from the subset with
# CanBeGeneratedByModifiers (CursedRun, Neow's Bones, Sere Talon).
CURSE_POOL: tuple[str, ...] = (
    "ascenders_bane", "bad_luck", "clumsy", "curse_of_the_bell", "debt",
    "decay", "doubt", "enthralled", "folly", "greed", "guilty", "injury",
    "normality", "poor_sleep", "regret", "shame", "spore_mind", "writhe",
)


def curse_pool_ids(generatable_only: bool = True) -> list[str]:
    """Ids in the curse pool, by default only those a random-curse effect can
    generate (mirrors the CanBeGeneratedByModifiers filter every consumer of
    CurseCardPool applies)."""
    return [
        card_id for card_id in CURSE_POOL
        if not generatable_only
        or _CARD_CLASSES[card_id].can_be_generated_by_modifiers
    ]


def random_curses(
    rng: random.Random,
    count: int = 1,
    distinct: bool = False,
) -> list[Card]:
    """Generate random curses from the generatable curse pool.

    Mirrors the game's consumers: CursedRun picks uniformly with replacement
    (Rng.Niche.NextItem); Neow's Bones and Sere Talon pick distinct curses,
    removing each choice from the candidate list (distinct=True).
    """
    options = curse_pool_ids()
    if distinct:
        chosen = rng.sample(options, min(count, len(options)))
    else:
        chosen = [rng.choice(options) for _ in range(count)]
    return [make_card(card_id) for card_id in chosen]


def pool_card_ids(
    card_type: CardType | None = None,
    pool: tuple[str, ...] = IRONCLAD_POOL,
) -> list[str]:
    """Ids eligible for in-combat card generation (mirrors FilterForCombat:
    Basic and Ancient cards and CanBeGeneratedInCombat=False cards are
    excluded), optionally filtered by card type."""
    ids = []
    for card_id in pool:
        cls = _CARD_CLASSES[card_id]
        if cls.rarity in (CardRarity.BASIC, CardRarity.ANCIENT):
            continue
        if not cls.can_be_generated_in_combat:
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
    pool: tuple[str, ...] = IRONCLAD_POOL,
    exclude_ids: set[str] | None = None,
) -> list[Card]:
    """Generate random cards from a card pool for in-combat effects.

    Mirrors CardFactory.GetForCombat (uniform, with replacement) and
    GetDistinctForCombat (distinct=True) — used by e.g. Infernal Blade
    (1 distinct Attack) and Stoke (N cards, repeats allowed). pool defaults
    to the character (Ironclad) pool; Jack of All Trades passes
    COLORLESS_POOL with its own id excluded.
    """
    options = pool_card_ids(card_type, pool)
    if exclude_ids:
        options = [cid for cid in options if cid not in exclude_ids]
    if not options:
        return []
    if distinct:
        chosen = rng.sample(options, min(count, len(options)))
    else:
        chosen = [rng.choice(options) for _ in range(count)]
    return [make_card(card_id) for card_id in chosen]


def get_for_combat_parity(
    rng,
    count: int,
    card_type: CardType | None = None,
    pool: tuple[str, ...] = IRONCLAD_POOL,
) -> list[Card]:
    """Parity port of ``CardFactory.GetForCombat`` (Stoke, Calamity, …).

    ``count`` picks WITH replacement, each ``rng.NextItem(FilterForCombat(pool))``
    — one CombatCardGeneration draw per card, in pool order. Distinct from
    ``get_distinct_for_combat_parity`` (a single shuffle, no repeats) and from
    the legacy ``random_pool_cards`` (shared ``random.Random``)."""
    options = pool_card_ids(card_type, pool)
    if not options:
        return []
    return [make_card(rng.choice(options)) for _ in range(count)]


def get_distinct_for_combat_parity(
    rng,
    count: int,
    card_type: CardType | None = None,
    pool: tuple[str, ...] = IRONCLAD_POOL,
) -> list[Card]:
    """Parity port of ``CardFactory.GetDistinctForCombat``.

    The game does ``FilterForCombat(pool.GetUnlockedCards()[.Where(type)])
    .TakeRandom(count, rng)`` where ``TakeRandom(n) == list.ToList()
    .UnstableShuffle(rng).Take(n)``. ``FilterForCombat`` (== ``pool_card_ids``
    here) keeps generatable non-Basic/Ancient cards in pool order and is already
    ``Distinct`` (the pool has no repeats), so a plain in-place shuffle of the
    filtered id list, then the first ``count``, reproduces the game exactly.

    ``rng`` is the combat ``card_gen`` accessor — in a parity run a
    ``GameRandomAdapter`` over the ``CombatCardGeneration`` stream whose
    ``.shuffle`` is the game's top-down Fisher-Yates ``UnstableShuffle``
    (``NextInt(i+1)``). Distinct from the legacy ``random_pool_cards`` path,
    which shuffles the shared ``random.Random`` via ``sample``."""
    ids = pool_card_ids(card_type, pool)
    rng.shuffle(ids)
    return [make_card(card_id) for card_id in ids[:count]]


# Transform rarities: everything except Basic/Ancient/Token/Event/... —
# a normal transform lands on a Common/Uncommon/Rare card.
_TRANSFORM_RARITIES = (CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE)


def transform_options_in_combat(card: Card) -> list[str]:
    """The ids an in-combat transform (Entropy) may turn `card` into.

    Mirrors CardFactory.GetDefaultTransformationOptions(isInCombat=true):
    Quest cards and Event/Ancient/Token rarities transform out of the
    Colorless pool; Statuses and Curses stay within their own pool (no
    rarity filter); everything else uses its own pool (Ironclad or
    Colorless) filtered to Common/Uncommon/Rare. All options must be
    generatable in combat and differ from the original card.
    """
    if card.card_type == CardType.CURSE:
        pool, rarity_filter = CURSE_POOL, False
    elif card.card_type == CardType.STATUS:
        pool = tuple(
            cid for cid, c in sorted(_CARD_CLASSES.items())
            if c.card_type == CardType.STATUS
        )
        rarity_filter = False
    elif card.card_type == CardType.QUEST or card.rarity in (
        CardRarity.EVENT, CardRarity.ANCIENT, CardRarity.TOKEN
    ):
        pool, rarity_filter = COLORLESS_POOL, True
    elif card.id in COLORLESS_POOL:
        pool, rarity_filter = COLORLESS_POOL, True
    else:
        pool, rarity_filter = IRONCLAD_POOL, True
    options = []
    for cid in pool:
        c = _CARD_CLASSES[cid]
        if cid == card.id or not c.can_be_generated_in_combat:
            continue
        if rarity_filter and c.rarity not in _TRANSFORM_RARITIES:
            continue
        options.append(cid)
    return options
