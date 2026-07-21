"""Game-faithful relic grab-bag rosters for SP2 UpFront parity (Task 8d).

At run init the game shuffles two relic grab bags on the ``UpFront`` stream
(``RunManager.InitializeNewRun`` -> ``RelicGrabBag.Populate``):

  * **SHARED bag** — ``SharedRelicPool.GetUnlockedRelics`` (all 6 rarities),
    bucketed into per-rarity deques, each ``UnstableShuffle``d separately
    (``RelicGrabBag.Populate(IEnumerable, Rng)``).
  * **PLAYER bag** — ``SharedRelicPool`` + the character's ``RelicPool``,
    filtered to ``{Common, Uncommon, Rare, Shop}``, bucketed into 4 per-rarity
    deques, each shuffled (``RelicGrabBag.Populate(Player, Rng)``).

The run-init UpFront draw count is ``sum(len(deque) - 1)`` over all deques
(``UnstableShuffle`` == ``Rng.shuffle``, ``len - 1`` draws each). For a
fully-unlocked Ironclad run this is a constant **230** — verified against all
five ``RunReplays`` recordings, whose act-0 event shuffle lands at UpFront
offset 232 (= 230 relic-bag + 2 shared-ancient subset draws). The count is
actually 230 for every one of the five recorded characters: the shared bag is
character-independent (112 draws) and each character pool contributes exactly
7 bag-eligible relics (118 player draws).

Rosters are transcribed verbatim (source order) from
``Slay the Spire 2/src/Core/Models/RelicPools/{SharedRelicPool,
IroncladRelicPool}.cs`` with each relic's ``Rarity`` from its
``Models/Relics/<Name>.cs``. Ids are ``RELIC.<SNAKE_UPPER(className)>`` — the
``run.save`` id form (validated: every recorded bag relic is a member here).
This is **draw-count / structure** fidelity (Task 8d, verify-draw-count-first);
the shuffled relic *identities* become a reward-pull oracle in Task 9.

Only the Ironclad pool is transcribed because the sim is Ironclad-only; the
other four character pools are added when the sim can play them.
"""
from __future__ import annotations

# The four rarities eligible for the player grab bag (RelicGrabBag._rarities);
# a relic of any other rarity (Event, Ancient, Starter) never enters it.
BAG_RARITIES: frozenset[str] = frozenset({"Common", "Uncommon", "Rare", "Shop"})

# SharedRelicPool.GenerateAllRelics — 118 relics, source order.
SHARED_RELIC_POOL: tuple[tuple[str, str], ...] = (
    ("RELIC.AKABEKO", "Uncommon"),
    ("RELIC.AMETHYST_AUBERGINE", "Common"),
    ("RELIC.ANCHOR", "Common"),
    ("RELIC.ART_OF_WAR", "Rare"),
    ("RELIC.BAG_OF_MARBLES", "Common"),
    ("RELIC.BAG_OF_PREPARATION", "Common"),
    ("RELIC.BEATING_REMNANT", "Rare"),
    ("RELIC.BELLOWS", "Rare"),
    ("RELIC.BELT_BUCKLE", "Shop"),
    ("RELIC.BLOOD_VIAL", "Common"),
    ("RELIC.BOOK_OF_FIVE_RINGS", "Common"),
    ("RELIC.BOWLER_HAT", "Uncommon"),
    ("RELIC.BREAD", "Shop"),
    ("RELIC.BRONZE_SCALES", "Common"),
    ("RELIC.BURNING_STICKS", "Shop"),
    ("RELIC.CANDELABRA", "Uncommon"),
    ("RELIC.CAPTAINS_WHEEL", "Rare"),
    ("RELIC.CAULDRON", "Shop"),
    ("RELIC.CENTENNIAL_PUZZLE", "Common"),
    ("RELIC.CHANDELIER", "Rare"),
    ("RELIC.CHEMICAL_X", "Shop"),
    ("RELIC.CLOAK_CLASP", "Rare"),
    ("RELIC.DINGY_RUG", "Shop"),
    ("RELIC.DOLLYS_MIRROR", "Shop"),
    ("RELIC.DRAGON_FRUIT", "Shop"),
    ("RELIC.ETERNAL_FEATHER", "Uncommon"),
    ("RELIC.FESTIVE_POPPER", "Common"),
    ("RELIC.FRESNEL_LENS", "Event"),
    ("RELIC.FROZEN_EGG", "Rare"),
    ("RELIC.GAMBLING_CHIP", "Rare"),
    ("RELIC.GAME_PIECE", "Rare"),
    ("RELIC.GHOST_SEED", "Shop"),
    ("RELIC.GIRYA", "Rare"),
    ("RELIC.GNARLED_HAMMER", "Shop"),
    ("RELIC.GORGET", "Common"),
    ("RELIC.GREMLIN_HORN", "Uncommon"),
    ("RELIC.HAPPY_FLOWER", "Common"),
    ("RELIC.HORN_CLEAT", "Uncommon"),
    ("RELIC.ICE_CREAM", "Rare"),
    ("RELIC.INTIMIDATING_HELMET", "Rare"),
    ("RELIC.JOSS_PAPER", "Uncommon"),
    ("RELIC.JUZU_BRACELET", "Common"),
    ("RELIC.KIFUDA", "Shop"),
    ("RELIC.KUNAI", "Rare"),
    ("RELIC.KUSARIGAMA", "Uncommon"),
    ("RELIC.LANTERN", "Common"),
    ("RELIC.LASTING_CANDY", "Uncommon"),
    ("RELIC.LAVA_LAMP", "Shop"),
    ("RELIC.LEES_WAFFLE", "Shop"),
    ("RELIC.LETTER_OPENER", "Uncommon"),
    ("RELIC.LIZARD_TAIL", "Rare"),
    ("RELIC.LOOMING_FRUIT", "Ancient"),
    ("RELIC.LUCKY_FYSH", "Uncommon"),
    ("RELIC.MANGO", "Rare"),
    ("RELIC.MEAL_TICKET", "Common"),
    ("RELIC.MEAT_ON_THE_BONE", "Rare"),
    ("RELIC.MEMBERSHIP_CARD", "Shop"),
    ("RELIC.MERCURY_HOURGLASS", "Uncommon"),
    ("RELIC.MINIATURE_CANNON", "Uncommon"),
    ("RELIC.MINIATURE_TENT", "Shop"),
    ("RELIC.MOLTEN_EGG", "Rare"),
    ("RELIC.MUMMIFIED_HAND", "Rare"),
    ("RELIC.MYSTIC_LIGHTER", "Shop"),
    ("RELIC.NUNCHAKU", "Uncommon"),
    ("RELIC.ODDLY_SMOOTH_STONE", "Common"),
    ("RELIC.OLD_COIN", "Rare"),
    ("RELIC.ORICHALCUM", "Uncommon"),
    ("RELIC.ORNAMENTAL_FAN", "Uncommon"),
    ("RELIC.ORRERY", "Shop"),
    ("RELIC.PANTOGRAPH", "Uncommon"),
    ("RELIC.PARRYING_SHIELD", "Uncommon"),
    ("RELIC.PEAR", "Uncommon"),
    ("RELIC.PEN_NIB", "Uncommon"),
    ("RELIC.PENDULUM", "Common"),
    ("RELIC.PERMAFROST", "Uncommon"),
    ("RELIC.PETRIFIED_TOAD", "Uncommon"),
    ("RELIC.PLANISPHERE", "Uncommon"),
    ("RELIC.POCKETWATCH", "Rare"),
    ("RELIC.POTION_BELT", "Common"),
    ("RELIC.PRAYER_WHEEL", "Rare"),
    ("RELIC.PUNCH_DAGGER", "Shop"),
    ("RELIC.RAINBOW_RING", "Rare"),
    ("RELIC.RAZOR_TOOTH", "Rare"),
    ("RELIC.RED_MASK", "Common"),
    ("RELIC.REGAL_PILLOW", "Common"),
    ("RELIC.REPTILE_TRINKET", "Uncommon"),
    ("RELIC.RINGING_TRIANGLE", "Shop"),
    ("RELIC.RIPPLE_BASIN", "Uncommon"),
    ("RELIC.ROYAL_STAMP", "Shop"),
    ("RELIC.SCREAMING_FLAGON", "Shop"),
    ("RELIC.SHOVEL", "Rare"),
    ("RELIC.SHURIKEN", "Rare"),
    ("RELIC.SLING_OF_COURAGE", "Shop"),
    ("RELIC.SPARKLING_ROUGE", "Uncommon"),
    ("RELIC.STONE_CALENDAR", "Rare"),
    ("RELIC.STONE_CRACKER", "Uncommon"),
    ("RELIC.STRAWBERRY", "Common"),
    ("RELIC.STRIKE_DUMMY", "Common"),
    ("RELIC.STURDY_CLAMP", "Rare"),
    ("RELIC.THE_ABACUS", "Shop"),
    ("RELIC.THE_COURIER", "Rare"),
    ("RELIC.TINY_MAILBOX", "Uncommon"),
    ("RELIC.TOOLBOX", "Shop"),
    ("RELIC.TOXIC_EGG", "Rare"),
    ("RELIC.TUNGSTEN_ROD", "Rare"),
    ("RELIC.TUNING_FORK", "Uncommon"),
    ("RELIC.UNCEASING_TOP", "Rare"),
    ("RELIC.UNSETTLING_LAMP", "Rare"),
    ("RELIC.VAJRA", "Common"),
    ("RELIC.VAMBRACE", "Uncommon"),
    ("RELIC.VENERABLE_TEA_SET", "Common"),
    ("RELIC.VERY_HOT_COCOA", "Ancient"),
    ("RELIC.VEXING_PUZZLEBOX", "Rare"),
    ("RELIC.WAR_PAINT", "Common"),
    ("RELIC.WHETSTONE", "Common"),
    ("RELIC.WHITE_BEAST_STATUE", "Rare"),
    ("RELIC.WHITE_STAR", "Rare"),
    ("RELIC.WING_CHARM", "Shop"),
)

# IroncladRelicPool.GenerateAllRelics — 8 relics, source order. Burning Blood
# is the starter relic (rarity Starter) so it is filtered out of the bag.
IRONCLAD_RELIC_POOL: tuple[tuple[str, str], ...] = (
    ("RELIC.BRIMSTONE", "Shop"),
    ("RELIC.BURNING_BLOOD", "Starter"),
    ("RELIC.CHARONS_ASHES", "Rare"),
    ("RELIC.DEMON_TONGUE", "Rare"),
    ("RELIC.PAPER_PHROG", "Uncommon"),
    ("RELIC.RED_SKULL", "Common"),
    ("RELIC.RUINED_HELMET", "Rare"),
    ("RELIC.SELF_FORMING_CLAY", "Uncommon"),
)


def _bucket(pairs: tuple[tuple[str, str], ...] | list[tuple[str, str]]) -> dict[str, list[str]]:
    """Bucket ``(id, rarity)`` pairs into an insertion-ordered
    ``{rarity: [id, ...]}`` — mirrors ``RelicGrabBag``'s
    ``Dictionary<RelicRarity, List<RelicModel>>`` filled in iteration order
    (Python dicts and .NET dictionaries both iterate first-inserted-first)."""
    deques: dict[str, list[str]] = {}
    for relic_id, rarity in pairs:
        deques.setdefault(rarity, []).append(relic_id)
    return deques


def populate_relic_grab_bags(
    rng,
    character_pool: tuple[tuple[str, str], ...] = IRONCLAD_RELIC_POOL,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Populate + shuffle the shared and player relic grab bags on ``rng``
    (a game ``Rng`` — the ``UpFront`` stream at run init).

    Mirrors ``RunManager.InitializeNewRun``: the shared bag first (all
    rarities), then the player bag (shared + character, 4 bag rarities). Each
    per-rarity deque is ``UnstableShuffle``d in its bucket-insertion order.
    Returns ``(shared_deques, player_deques)``, each an insertion-ordered
    ``{rarity: [id, ...]}``. Consumes ``sum(len - 1)`` UpFront draws (230 for
    the fully-unlocked Ironclad bags)."""
    # SHARED bag: RelicGrabBag.Populate(SharedRelicPool.GetUnlockedRelics, rng).
    shared = _bucket(SHARED_RELIC_POOL)
    for deque in shared.values():
        rng.shuffle(deque)
    # PLAYER bag: RelicGrabBag.Populate(player, rng) — shared + character,
    # filtered to the 4 bag rarities, in that concatenation order.
    player_pairs = [p for p in SHARED_RELIC_POOL if p[1] in BAG_RARITIES]
    player_pairs += [p for p in character_pool if p[1] in BAG_RARITIES]
    player = _bucket(player_pairs)
    for deque in player.values():
        rng.shuffle(deque)
    return shared, player
