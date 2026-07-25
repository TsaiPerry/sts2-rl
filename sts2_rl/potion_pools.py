"""Draw-count-faithful potion roster for SP2 reward/shop parity.

The game generates reward and shop potions with ``PotionFactory`` off the
per-player ``Rewards`` / ``Shops`` RNG streams: one ``NextFloat`` rolls a
rarity, then ``NextItem`` picks from that rarity's bucket of the unlocked
pool (``Character.PotionPool ∪ SharedPotionPool``). The sim only *implements*
a handful of potions, so a naive pick would leave the Uncommon/Rare buckets
empty and ``NextItem`` would consume no draw — desyncing the stream counter.

This module ports the full pool as ``(id, rarity)`` data (identities/rarity
transcribed from ``src/Core/Models/Potions/*.cs`` plus ``Ironclad4Epoch``),
so the parity generators draw exactly what the game draws: two draws per
potion, over non-empty buckets. Epoch/unlock gating is not modelled
(fully-unlocked run), matching the rest of the sim.

Every potion in this roster is now implemented in ``potions.py``
(test_potions.TestPoolCoverage gates that), so ``_make`` builds a real class
for every pool id. The ``_ParityPotion`` placeholder remains for ids that are
*not* in the pool at all: a save/recording can name a cross-character potion
(Silent's Poison Potion, Defect's Focus Potion, …) that the sim does not
implement, and the belt resync must still be able to rebuild that slot.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .potions import Potion, _POTION_CLASSES
from .rng import Rng, snake_case

if TYPE_CHECKING:
    from .combat import CombatCtx
    from .creatures import Creature


# GetPotionOptions order: the character (Ironclad) pool first, then the shared
# pool. Names + rarity are the source classes; the rarity drives the shop price
# and the reward/shop pick's rarity bucket.
_RAW_POOL: tuple[tuple[str, str], ...] = (
    # IroncladPotionPool (Ironclad4Epoch.Potions)
    ("BloodPotion", "common"), ("SoldiersStew", "rare"), ("Ashwater", "uncommon"),
    # SharedPotionPool.GenerateAllPotions (source list order)
    ("AttackPotion", "common"), ("BeetleJuice", "rare"),
    ("BlessingOfTheForge", "uncommon"), ("BlockPotion", "common"),
    ("BottledPotential", "rare"), ("Clarity", "uncommon"),
    ("ColorlessPotion", "common"), ("CureAll", "uncommon"),
    ("DexterityPotion", "common"), ("DistilledChaos", "rare"),
    ("DropletOfPrecognition", "rare"), ("Duplicator", "uncommon"),
    ("EnergyPotion", "common"), ("EntropicBrew", "rare"),
    ("ExplosiveAmpoule", "common"), ("FairyInABottle", "rare"),
    ("FirePotion", "common"), ("FlexPotion", "common"),
    ("Fortifier", "uncommon"), ("FruitJuice", "rare"),
    ("FyshOil", "uncommon"), ("GamblersBrew", "uncommon"),
    ("GigantificationPotion", "rare"), ("HeartOfIron", "uncommon"),
    ("LiquidBronze", "uncommon"), ("LiquidMemories", "rare"),
    ("LuckyTonic", "rare"), ("MazalethsGift", "rare"),
    ("OrobicAcid", "rare"), ("PotionOfBinding", "uncommon"),
    ("PowderedDemise", "uncommon"), ("PowerPotion", "common"),
    ("RadiantTincture", "uncommon"), ("RegenPotion", "uncommon"),
    ("ShacklingPotion", "rare"), ("ShipInABottle", "rare"),
    ("SkillPotion", "common"), ("SneckoOil", "rare"),
    ("SpeedPotion", "common"), ("StableSerum", "uncommon"),
    ("StrengthPotion", "common"), ("SwiftPotion", "common"),
    ("TouchOfInsanity", "uncommon"), ("VulnerablePotion", "common"),
    ("WeakPotion", "common"),
)

# (id, rarity) in game order — ids are snake_case of the source class name.
POTION_POOL: tuple[tuple[str, str], ...] = tuple(
    (snake_case(name), rarity) for name, rarity in _RAW_POOL
)

# PotionModel.CanBeGeneratedInCombat => false — the three potions
# CreateRandomPotionInCombat filters out (FairyInABottle / FruitJuice /
# RegenPotion; the healing-adjacent ones). Everything else defaults to true.
NOT_GENERATED_IN_COMBAT: frozenset[str] = frozenset(
    {"fairy_in_a_bottle", "fruit_juice", "regen_potion"}
)


class _ParityPotion(Potion):
    """A pool-membership placeholder for a potion the sim doesn't implement.

    Only ``id`` / ``name`` / ``rarity`` are read (shop pricing, reward display);
    it is never ``use``-d — the parity runner never consumes a generated potion.
    """

    def __init__(self, potion_id: str, rarity: str) -> None:
        self.id = potion_id
        self.name = potion_id
        self.rarity = rarity

    def use(self, ctx: "CombatCtx", target: "Creature | None" = None) -> None:
        raise NotImplementedError(
            f"potion {self.id!r} is a parity-pool placeholder and has no effect"
        )


def _make(potion_id: str, rarity: str) -> Potion:
    cls = _POTION_CLASSES.get(potion_id)
    return cls() if cls is not None else _ParityPotion(potion_id, rarity)


# id -> rarity for every pooled potion (implemented or placeholder), so a
# potion can be rebuilt from its id alone (belt resync in the conformance
# runner, which knows the slot id but not the rarity).
_POOL_RARITY: dict[str, str] = {pid: rarity for pid, rarity in POTION_POOL}


def make_pool_potion(potion_id: str) -> Potion:
    """Build a potion by id — its real class if implemented, else a
    pool-membership ``_ParityPotion`` placeholder (id + rarity from
    ``POTION_POOL``). Mirrors ``potions.make_potion`` but never KeyErrors on a
    potion the sim only tracks for pool parity (e.g. MazalethsGift), which the
    belt resync must be able to reconstruct into its slot."""
    return _make(potion_id, _POOL_RARITY.get(potion_id, "common"))


def roll_potion_rarity(rng: Rng) -> str:
    """PotionFactory.CreateRandomPotion rarity roll: one NextFloat, Rare <= 0.1,
    Uncommon <= 0.35, else Common."""
    num = rng.next_float()
    if num <= 0.1:
        return "rare"
    if num <= 0.35:
        return "uncommon"
    return "common"


def generate_random_potion(rng: Rng, blacklist: "set[str] | None" = None) -> Potion:
    """PotionFactory.CreateRandomPotionOutOfCombat: roll a rarity, then NextItem
    from that rarity's bucket. Two draws over a non-empty bucket."""
    used = set(blacklist or ())
    rarity = roll_potion_rarity(rng)
    options = [pid for pid, r in POTION_POOL if r == rarity and pid not in used]
    return _make(rng.next_item(options), rarity)


def generate_random_potion_in_combat(
    rng: Rng, blacklist: "set[str] | None" = None
) -> Potion:
    """PotionFactory.CreateRandomPotionInCombat: same two draws as the
    out-of-combat form, over the pool minus the potions that cannot be
    generated in combat."""
    used = set(blacklist or ()) | NOT_GENERATED_IN_COMBAT
    return generate_random_potion(rng, used)


def generate_random_potions(
    rng: Rng, count: int, blacklist: "set[str] | None" = None
) -> list[Potion]:
    """PotionFactory.CreateRandomPotionsOutOfCombat: `count` potions, each a
    rarity roll + NextItem pick, deduping the chosen ids as the source removes
    picked potions from the working list."""
    used = set(blacklist or ())
    chosen: list[Potion] = []
    for _ in range(count):
        rarity = roll_potion_rarity(rng)
        options = [pid for pid, r in POTION_POOL if r == rarity and pid not in used]
        pid = rng.next_item(options)
        if pid is None:
            continue
        used.add(pid)
        chosen.append(_make(pid, rarity))
    return chosen
