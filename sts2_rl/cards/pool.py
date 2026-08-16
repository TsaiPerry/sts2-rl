from __future__ import annotations

import random

from .base import Card, CardRarity, CardType, make_card, _CARD_CLASSES

# Ironclad card pool (IroncladCardPool.cs), in the game's exact
# GenerateAllCards() declaration order (alphabetical by C# class name).
# ORDER IS PARITY-CRITICAL: reward/transform generation does
# `Rng.NextItem(pool.Where(rarity == r))`, indexing into the rarity-filtered
# list in pool order. 87-card list minus Tank/Demonic Shield (removed by
# CardFactory.FilterForPlayerCount in single player). Basics/Ancients stay for
# completeness but are filtered out of generation; tokens/statuses/curses
# are not pool cards.
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


# Colorless card pool (ColorlessCardPool.cs), source order, minus the 11
# multiplayer-only cards CardFactory.FilterForPlayerCount removes (same
# treatment as Ironclad's Tank/Demonic Shield). Uncommon/Rare only; feeds
# the shop's two Colorless slots and Event/Ancient/Token/Quest transforms.
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


def _require_pool(pool: tuple[str, ...] | None) -> tuple[str, ...]:
    """Every generator below takes the card pool explicitly.

    These used to default to ``IRONCLAD_POOL``, which silently made any
    caller that forgot to thread the run's character through generate
    *Ironclad* cards. The game always goes through
    ``Owner.Character.CardPool``, so there is no correct default — a missing
    pool is a wiring bug, and this turns it into a loud one. Pass
    ``run.card_pool`` or ``combat.card_pool``."""
    if pool is None:
        raise TypeError(
            "pool is required: pass the character's card pool "
            "(run.card_pool / combat.card_pool), not the Ironclad default"
        )
    return pool


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
    pool: tuple[str, ...] | None = None,
) -> list[str]:
    """Ids eligible for in-combat card generation (mirrors
    ``CardFactory.FilterForCombat``, CardFactory.cs:159-162: ``cards.Where(c
    => c.CanBeGeneratedInCombat && c.Rarity != Basic && c.Rarity != Ancient
    && c.Rarity != Event).Distinct()`` — Basic, Ancient AND Event cards, plus
    CanBeGeneratedInCombat=False cards, are excluded), optionally filtered by
    card type."""
    ids = []
    for card_id in _require_pool(pool):
        cls = _CARD_CLASSES[card_id]
        if cls.rarity in (CardRarity.BASIC, CardRarity.ANCIENT, CardRarity.EVENT):
            continue
        if not cls.can_be_generated_in_combat:
            continue
        if card_type is not None and cls.card_type != card_type:
            continue
        ids.append(card_id)
    return ids


def reward_pool_card_ids(pool: tuple[str, ...] | None = None) -> list[str]:
    """Ids eligible for reward/out-of-combat card generation — the game's
    ``CardPool.GetUnlockedCards()`` (``CardCreationOptions.GetPossibleCards``):
    the full unlocked pool in declaration order.

    Unlike ``pool_card_ids`` (``FilterForCombat``), this does NOT drop
    ``CanBeGeneratedInCombat=False`` cards, nor Basic/Ancient — the combat-only
    filter never applies to rewards. ``CardFactory.CreateForReward`` instead
    filters by the rolled rarity (only ever Common/Uncommon/Rare), so Basic and
    Ancient cards are never picked (they only join the ``allowedRarities`` set),
    while Feed and NotYet (Rare, ``CanBeGeneratedInCombat=false``) ARE eligible
    rewards. For non-ascension Ironclad every pool card is unlocked, so this
    returns the pool as-is."""
    return list(_require_pool(pool))


def random_pool_cards(
    rng: random.Random,
    count: int,
    card_type: CardType | None = None,
    distinct: bool = False,
    pool: tuple[str, ...] | None = None,
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


def take_random(items, count: int, rng) -> list:
    """`IEnumerableExtensions.TakeRandom` (IEnumerableExtensions.cs:17-20) --
    `collection.ToList().UnstableShuffle(rng).Take(count)`.

    Three things this is NOT, and each of them costs a divergence:

    * It is not `rng.sample`. A full Fisher-Yates over N items spends N-1
      draws whatever `count` is, where `sample` spends far fewer -- so even a
      run where the picked items agree leaves the stream in a different place.
    * It does not mutate the caller's list (`.ToList()` first).
    * It does not clamp `count`. `Take(n)` on a shorter sequence yields the
      whole sequence, which is what lets Anointed pass `10 - handCount`.

    `rng` is the NAMED stream the call site's C# names -- a `CombatRng`
    accessor, whose `.shuffle` in a parity run is the game's top-down
    Fisher-Yates. `StableShuffle` is a different verb (it SORTS first);
    `player.stable_shuffled_cards` is that one.
    """
    pool = list(items)
    rng.shuffle(pool)
    return pool[:count]


def get_for_combat_parity(
    rng,
    count: int,
    card_type: CardType | None = None,
    pool: tuple[str, ...] | None = None,
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
    pool: tuple[str, ...] | None = None,
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


# Status card pool (StatusCardPool.cs:19-34), source declaration order —
# NOT alphabetical (Wither sits between Infection and Slimed). Order is
# parity-critical: transforms index into the filtered list in pool order.
# Debris/Void not ported yet (separate content gap). FranticEscape/Soot kept
# for completeness, filtered out of generation by CanBeGeneratedInCombat.
STATUS_POOL: tuple[str, ...] = (
    "beckon", "burn", "dazed", "frantic_escape", "infection", "wither",
    "slimed", "soot", "toxic", "wound",
)


# Transform rarities: everything except Basic/Ancient/Token/Event/... —
# a normal transform lands on a Common/Uncommon/Rare card.
_TRANSFORM_RARITIES = (CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE)


def transform_options_in_combat(
    card: Card, character_pool: tuple[str, ...] | None = None
) -> list[str]:
    """The ids an in-combat transform (Entropy) may turn `card` into.

    Mirrors CardFactory.GetDefaultTransformationOptions(isInCombat=true):
    Quest cards and Event/Ancient/Token rarities transform out of the
    Colorless pool; Statuses and Curses stay within their own pool (no
    rarity filter); everything else uses its own pool (the character's or
    Colorless) filtered to Common/Uncommon/Rare. All options must be
    generatable in combat and differ from the original card.

    `character_pool` is the fighting character's CardPool (`combat.card_pool`)
    — the fallback branch for an ordinary character card.
    """
    if card.card_type == CardType.CURSE:
        pool, rarity_filter = CURSE_POOL, False
    elif card.card_type == CardType.STATUS:
        # `CardModel.Pool` resolves a STATUS card to StatusCardPool, whose
        # declared order this preserves. It used to be rebuilt as
        # `sorted(_CARD_CLASSES)` filtered to STATUS, which both alphabetized
        # the row and swept in statuses that are not pool members at all.
        pool, rarity_filter = STATUS_POOL, False
    elif card.card_type == CardType.QUEST or card.rarity in (
        CardRarity.EVENT, CardRarity.ANCIENT, CardRarity.TOKEN
    ):
        pool, rarity_filter = COLORLESS_POOL, True
    elif card.id in COLORLESS_POOL:
        pool, rarity_filter = COLORLESS_POOL, True
    else:
        pool, rarity_filter = _require_pool(character_pool), True
    options = []
    for cid in pool:
        c = _CARD_CLASSES[cid]
        if cid == card.id or not c.can_be_generated_in_combat:
            continue
        if rarity_filter and c.rarity not in _TRANSFORM_RARITIES:
            continue
        options.append(cid)
    return options
