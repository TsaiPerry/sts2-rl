"""Post-combat and treasure rewards (the game's RewardsSet layer).

Ports the reward-generation slice of the source:
  - RewardsSet.cs GenerateRewardsFor — what each room type awards, in reward
    order (gold, potion, cards, relic):
      Monster: gold 10–20 (× the encounter's GoldProportion) + potion roll
               + a 3-card choice
      Elite:   gold 35–45 + potion roll + 3 cards + a grab-bag relic
      Boss:    gold 100 + potion roll + 3 all-Rare cards, NO relic; the
               final act's boss yields no rewards at all (victory)
  - CardRarityOdds.cs — the card-rarity roll: one uniform draw against a
    rare threshold (base rare odds + a per-run drifting pity offset), then
    the uncommon band, else common. The offset starts at −0.05, grows by
    +0.01 per non-rare result (capped at +0.40) and resets to −0.05 on a
    rare. Boss rolls use offset 0 but still reset the counter. Shops read
    the offset without mutating it (RollWithoutChangingFutureOdds).
  - PotionRewardOdds.cs — the potion drop: threshold starts at 0.40, −0.10
    after a hit / +0.10 after a miss; Elite rooms add eliteBonus×0.5 =
    +0.125 to that roll only. Hook.ShouldForcePotionReward (relics) can
    force a drop.
  - CardFactory.CreateForReward — per reward card: mutating rarity roll,
    no duplicates within one reward (blacklist), rarity escalated with
    wrapping when the pool has no card of the rolled rarity, then a uniform
    pick; an upgrade draw per card (act_index × 0.25 for non-rares only —
    Act 1: 0%, Act 2: 25%, Act 3: 50%; rare cards never auto-upgrade).
  - Treasure chest (OneOffSynchronizer): gold 42–52 + a grab-bag relic.

Deliberate deviations (repo conventions):
  - one shared run RNG instead of the per-player `PlayerRng.Rewards` stream;
  - `GoldProportion` (partial gold when enemies escape) defaults to 1.0 —
    the sim's encounters don't do escape accounting;
  - non-ascension values only (no Scarcity/Poverty scaling);
  - Hook.ModifyRewards / reward-modifying relics (Prayer Wheel-likes) are
    dispatched duck-typed over the run's relics, like run.py's map pipeline.
  - the dispatch itself (`apply_reward_modifiers`) runs at each construction
    site AND, idempotently (`CombatRewards.generated`), as an offer-time
    backstop in driver._offer_rewards / RunState.offer_rewards — see that
    function's docstring for why both call it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, IntFlag
from typing import TYPE_CHECKING

from .cards import Card, CardRarity, make_card
from .cards.base import _CARD_CLASSES
from .cards.pool import pool_card_ids, reward_pool_card_ids
from .rooms import RoomType

if TYPE_CHECKING:
    from .monsters import Encounter
    from .potions import Potion
    from .relics import Relic
    from .run import RunState


def _uniform(rng) -> float:
    """One uniform [0,1) draw. In the SP2 parity path ``rng`` is a game ``Rng``
    (``NextFloat``, the primitive the source's odds/upgrade rolls use); the
    legacy RL path is a ``random.Random`` (``random()``)."""
    from .rng import Rng

    return rng.next_float() if isinstance(rng, Rng) else rng.random()


def _draw_choice(rng, seq):
    """Uniform pick from a sequence: ``Rng.NextItem`` (parity) or
    ``random.Random.choice`` (legacy)."""
    from .rng import Rng

    return rng.next_item(seq) if isinstance(rng, Rng) else rng.choice(seq)


class RarityOddsType(Enum):
    """CardRarityOddsType — which base-odds table a card roll uses."""

    REGULAR = "regular"
    ELITE = "elite"
    BOSS = "boss"
    SHOP = "shop"
    UNIFORM = "uniform"


class CardCreationSource(Enum):
    """CardCreationSource (src/Core/Runs/CardCreationSource.cs) — what a card
    is being created FOR. Relics that only modify post-combat reward options
    gate on it (LastingCandy.cs:106-109)."""

    NONE = "none"
    ENCOUNTER = "encounter"   # a post-encounter card reward
    SHOP = "shop"
    OTHER = "other"           # a reward generated from an event or a relic


class CardCreationFlags(IntFlag):
    """CardCreationFlags (src/Core/Runs/CardCreationFlags.cs), as much of it as
    the sim needs. The values are the source's, because they are a [Flags]
    enum and the composites depend on them.

    Only the flags a ported listener actually reads are carried:
    `IS_CARD_REWARD` is the one four relics gate on (DingyRug.cs:23,
    PrismaticGem.cs:38, SilkenTress.cs:53, SilverCrucible.cs:104) and is set
    exactly where C# sets it — `CardReward.cs:114-115` and `:134`, i.e. a card
    REWARD screen and nothing else. `NO_CARD_POOL_MODIFICATIONS` and
    `NO_MODIFY_HOOKS` are the two the generators pass.

    Where a flag comes from: a construction site's flags are
    the OR of its `CardCreationOptions` factory's own (`ForNonCombatWith*` all
    set `NO_UPGRADE_ROLL` — CardCreationOptions.cs:139/152/162) and whatever
    it adds with `.WithFlags(...)`, which is itself an OR
    (CardCreationOptions.cs:212-216). `create_reward_cards`' `extra_flags`
    carries that set through, and `CardRewardGroup.flags` declares it per
    screen. THREE of these are live in the sim today:
    `IS_CARD_REWARD` (the four relics above), `NO_MODIFY_HOOKS`
    (CardFactory.cs:104) and `NO_UPGRADE_ROLL` (CardFactory.cs:98-102, which
    skips the upgrade roll AND its Rewards draw). `NO_CARD_POOL_MODIFICATIONS`
    is read by `dingy_rug.py:31` and is what keeps a Colorless pool off a
    screen whose caller specified the pool. The rest have no ported reader.
    """

    NO_RARITY_MODIFICATION = 1
    NO_UPGRADE_ROLL = 2
    NO_HOOK_UPGRADES = 4
    NO_MODIFY_HOOKS = 8
    NO_CARD_POOL_MODIFICATIONS = 0x10
    NO_CARD_MODEL_MODIFICATIONS = 0x20
    FORCE_RARITY_ODDS_CHANGE = 0x40
    IS_CARD_REWARD = 0x80


@dataclass(frozen=True)
class CardCreationOptions:
    """The `CardCreationOptions` a creation runs against (src/Core/Runs/
    CardCreationOptions.cs), as much of it as the sim models: the pool
    `GetPossibleCards` returns, the source, the rarity-odds table and the
    creation flags.

    Handed to the TryModifyCardRewardOptions hooks so a listener can inspect
    the creation it is modifying rather than just the resulting options."""

    pool: tuple[str, ...]
    source: CardCreationSource
    odds_type: "RarityOddsType"
    flags: CardCreationFlags = CardCreationFlags(0)

    def has_flag(self, flag: CardCreationFlags) -> bool:
        """`options.Flags.HasFlag(...)` — the form every C# listener uses."""
        return bool(self.flags & flag)


# CardRarityOdds.GetBaseOdds, non-ascension values: (rare, uncommon, common).
# NOTE (verified against source): GetBaseOdds' switch only ever reads the
# Rare and Uncommon slots — `common` is never queried by Roll/
# RollWithoutChangingFutureOdds/RollWithBaseOdds (CardRarityOdds.cs:96-165);
# it is carried here purely for table completeness/documentation, exactly as
# dead in the source as it is here.
_BASE_RARITY_ODDS: dict[RarityOddsType, tuple[float, float, float]] = {
    RarityOddsType.REGULAR: (0.03, 0.37, 0.60),
    RarityOddsType.ELITE: (0.10, 0.40, 0.50),
    RarityOddsType.BOSS: (1.0, 0.0, 0.0),
    RarityOddsType.SHOP: (0.09, 0.37, 0.54),
    RarityOddsType.UNIFORM: (0.33, 0.33, 0.33),
}

# Scarcity (Asc 7, CardRarityOdds.cs:13-41) overrides Rare and (dead/display)
# Common per type via `AscensionHelper.GetValueIfAscension(Scarcity, ...)`;
# the Uncommon band (`regularUncommonOdds`/`eliteUncommonOdds`/
# `shopUncommonOdds`) is a `const` in the source — NOT ascension-gated —
# so it is carried over unchanged from `_BASE_RARITY_ODDS` below. Boss and
# Uniform have no Scarcity entry in the source and are absent here too.
_SCARCITY_RARITY_ODDS: dict[RarityOddsType, tuple[float, float, float]] = {
    RarityOddsType.REGULAR: (0.0149, 0.37, 0.615),
    RarityOddsType.ELITE: (0.05, 0.40, 0.549),
    RarityOddsType.SHOP: (0.045, 0.37, 0.585),
}

# Room type → the odds table its card reward rolls with (RewardsSet).
ROOM_RARITY_ODDS: dict[RoomType, RarityOddsType] = {
    RoomType.MONSTER: RarityOddsType.REGULAR,
    RoomType.ELITE: RarityOddsType.ELITE,
    RoomType.BOSS: RarityOddsType.BOSS,
}

# EncounterModel.MinGoldReward/MaxGoldReward by room type (inclusive ranges).
GOLD_REWARD_RANGES: dict[RoomType, tuple[int, int]] = {
    RoomType.MONSTER: (10, 20),
    RoomType.ELITE: (35, 45),
    RoomType.BOSS: (100, 100),
}

# Treasure chest gold (OneOffSynchronizer: NextInt(42, 53), inclusive 42–52).
TREASURE_GOLD = (42, 52)

# How many card choices a combat reward offers (RewardsSet: always 3).
CARD_REWARD_COUNT = 3

# CardFactory.UpgradedCardOddScaling — reward-card upgrade odds per act index
# (CardFactory.cs:23: `AscensionHelper.GetValueIfAscension(Scarcity, 0.125m,
# 0.25m)`). Kept as a module constant for callers that don't have a `run`
# (matching the pre-Task-2 non-ascension convention); `upgraded_card_odd_
# scaling(run)` below is the ascension-aware lookup used at the reward site.
UPGRADED_CARD_ODD_SCALING = 0.25


def upgraded_card_odd_scaling(run: "RunState") -> float:
    """CardFactory.cs:23 — halved (0.25 -> 0.125) under Scarcity (Asc 7)."""
    from .actmap import AscensionLevel

    if run.has_ascension(AscensionLevel.SCARCITY):
        return 0.125
    return UPGRADED_CARD_ODD_SCALING

# CardRarityExtensions.GetNextHighestRarityWithWrapping (pool-card portion).
NEXT_RARITY_WRAP = {
    CardRarity.COMMON: CardRarity.UNCOMMON,
    CardRarity.UNCOMMON: CardRarity.RARE,
    CardRarity.RARE: CardRarity.COMMON,
}


def next_allowed_card_rarity(rarity: CardRarity, is_allowed) -> CardRarity | None:
    """CardFactory.GetNextAllowedRarity: step up with wrapping until a rarity
    passes the predicate; None if the whole Common/Uncommon/Rare cycle fails."""
    initial = rarity
    while not is_allowed(rarity):
        rarity = NEXT_RARITY_WRAP.get(rarity)
        if rarity is None or rarity == initial:
            return None
    return rarity


class CardRarityOdds:
    """CardRarityOdds.cs — the drifting rare-pity offset, one per run.

    A single uniform draw is compared against `rare_base + offset` for Rare,
    then against the added Uncommon band, else Common. `roll` mutates the
    offset (encounter rewards); `roll_without_changing_future_odds` reads it
    (shops); `roll_with_base_odds` ignores it (some events).
    """

    BASE_OFFSET = -0.05    # _baseRarityOffset (also the post-rare reset value)
    MAX_OFFSET = 0.40      # _maxRarityOffset

    def __init__(self, rng: random.Random, run: "RunState | None" = None) -> None:
        self._rng = rng
        self.current_value = self.BASE_OFFSET
        # `run`, kept for the two ascension-gated lookups below (RarityGrowth
        # and the Rare/Common table swap under Scarcity). Optional and
        # storable at construction time even though ascension isn't known
        # yet at RunState.__init__ — both lookups run has_ascension() lazily,
        # at roll time, by which point start_act has set it.
        self.run = run

    @property
    def GROWTH(self) -> float:  # noqa: N802 - matches the C# property name
        """RarityGrowth (CardRarityOdds.cs:29): 0.005 under Scarcity (Asc 7),
        else 0.01."""
        from .actmap import AscensionLevel

        if self.run is not None and self.run.has_ascension(AscensionLevel.SCARCITY):
            return 0.005
        return 0.01

    def _odds(self, odds_type: RarityOddsType) -> tuple[float, float, float]:
        """GetBaseOdds — the (rare, uncommon, common) row for `odds_type`,
        swapped to the Scarcity table (Asc 7) when the type has one."""
        from .actmap import AscensionLevel

        if (self.run is not None and self.run.has_ascension(AscensionLevel.SCARCITY)
                and odds_type in _SCARCITY_RARITY_ODDS):
            return _SCARCITY_RARITY_ODDS[odds_type]
        return _BASE_RARITY_ODDS[odds_type]

    def roll(self, odds_type: RarityOddsType) -> CardRarity:
        """The mutating roll used for encounter card rewards. Boss rolls use
        offset 0 (they are all-Rare regardless) but still reset the pity."""
        offset = 0.0 if odds_type == RarityOddsType.BOSS else self.current_value
        rarity = self.roll_without_changing_future_odds(odds_type, offset)
        if rarity == CardRarity.RARE:
            self.current_value = self.BASE_OFFSET
        else:
            self.current_value = min(self.current_value + self.GROWTH, self.MAX_OFFSET)
        return rarity

    def roll_without_changing_future_odds(
        self, odds_type: RarityOddsType, offset: float | None = None
    ) -> CardRarity:
        """The read-only roll (shops): current offset applied, not advanced."""
        if offset is None:
            offset = self.current_value
        rare, uncommon, _ = self._odds(odds_type)
        roll = _uniform(self._rng)
        rare_threshold = rare + offset
        if roll < rare_threshold:
            return CardRarity.RARE
        if roll < uncommon + rare_threshold:
            return CardRarity.UNCOMMON
        return CardRarity.COMMON

    def roll_with_base_odds(self, odds_type: RarityOddsType) -> CardRarity:
        """RollWithBaseOdds: pure base-odds roll, no offset (some events).
        Note the source compares against the raw uncommon band here (not
        rare+uncommon) — transcribed as-is."""
        rare, uncommon, _ = self._odds(odds_type)
        roll = _uniform(self._rng)
        if roll < rare:
            return CardRarity.RARE
        if roll < uncommon:
            return CardRarity.UNCOMMON
        return CardRarity.COMMON


class PotionRewardOdds:
    """PotionRewardOdds.cs — the potion-drop pity threshold, one per run."""

    BASE = 0.40           # _basePotionRewardOdds (initial CurrentValue)
    STEP = 0.10           # pity: −0.10 on a hit, +0.10 on a miss
    ELITE_BONUS = 0.25    # eliteBonus; applied × 0.5 to the roll threshold

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self.current_value = self.BASE

    def roll(self, room_type: RoomType, force: bool = False) -> bool:
        """Whether this room's rewards include a potion. Mutates the pity.

        PotionRewardOdds.Roll takes its `NextFloat` BEFORE testing the force
        flag (`float num4 = _rng.NextFloat(); if (flag || num4 < num3)`), so a
        forced drop still consumes exactly one Rewards draw. Evaluating the
        draw first rather than short-circuiting on `force` keeps the stream
        aligned for White Beast Statue, the hook's only implementer."""
        bonus = self.ELITE_BONUS if room_type == RoomType.ELITE else 0.0
        threshold = self.current_value + bonus * 0.5
        rolled = _uniform(self._rng) < threshold
        hit = force or rolled
        self.current_value += -self.STEP if hit else self.STEP
        return hit


def roll_gold_reward(
    rng: random.Random,
    room_type: RoomType,
    proportion: float = 1.0,
    gold_range: tuple[int, int] | None = None,
    run: "RunState | None" = None,
) -> int:
    """GoldReward.Populate: NextInt(min, max+1) on the room type's range,
    with the Monster range scaled by the encounter's GoldProportion.

    `gold_range` overrides the room-type default with an encounter's own
    Min/MaxGoldReward (both are virtual on EncounterModel — the Fake Merchant
    pins 300).

    `run`, when given, gates Poverty (Asc 3): EncounterModel.MinGoldReward/
    MaxGoldReward (EncounterModel.cs:75-97) multiply the double `num` by
    `AscensionHelper.PovertyAscensionGoldMultiplier` (0.75, AscensionHelper.
    cs:12) BEFORE the `(int)num` truncating cast — applied to both bounds,
    ahead of the Monster GoldProportion scaling below (which operates on the
    already-truncated ints), matching the getters' own order of operations."""
    from .actmap import AscensionLevel
    from .rng import Rng

    lo, hi = gold_range if gold_range is not None else GOLD_REWARD_RANGES[room_type]
    if run is not None and run.has_ascension(AscensionLevel.POVERTY):
        lo, hi = int(lo * 0.75), int(hi * 0.75)
    if room_type == RoomType.MONSTER:
        lo, hi = round(lo * proportion), round(hi * proportion)
    if hi <= 0:
        return 0
    # GoldReward.Populate: NextInt(min, max+1) on the parity Rewards stream, else
    # the legacy random.Random.randint (inclusive).
    if isinstance(rng, Rng):
        return rng.next_int_range(lo, hi + 1)
    return rng.randint(lo, hi)


def create_reward_cards(
    run: "RunState",
    odds_type: RarityOddsType,
    count: int = CARD_REWARD_COUNT,
    mutate_pity: bool = True,
    modify_hooks: bool = True,
    pool: list[str] | None = None,
    is_card_reward: bool = False,
    extra_flags: CardCreationFlags = CardCreationFlags(0),
    rng=None,
) -> list[Card]:
    """CardFactory.CreateForReward: `count` distinct pool cards, each from a
    rarity roll (escalated with wrapping when the pool lacks the rolled
    rarity) and an act-scaled upgrade draw.

    `mutate_pity=False` uses the non-mutating base-odds roll — the path for
    non-Encounter sources like Lost Coffer (RollForRarity only calls the
    mutating Roll for CardCreationSource.Encounter).
    `modify_hooks=False` skips Hook.TryModifyCardRewardOptionsLate
    (CardCreationFlags.NoModifyHooks).
    `pool` overrides the character pool (CardCreationOptions' explicit pool
    list — Lead Paperweight passes the Colorless pool).

    `extra_flags` is the rest of the caller's
    `CardCreationFlags` — everything its `CardCreationOptions` factory and its
    `.WithFlags(...)` chain set, OR-ed onto the two this function derives from
    `is_card_reward` / `modify_hooks`. Two of them change what happens here,
    exactly as they do in C#:

    - `NO_UPGRADE_ROLL` skips `RollForUpgrade` **and the Rewards draw it
      takes**: `CardFactory.cs:98-102` guards the whole call, and the
      `rng.NextFloat()` lives inside `RollForUpgrade` (CardFactory.cs:290), so
      such a creation spends `count` draws, not `2 * count`. Every
      `ForNonCombatWith*` factory sets this flag
      (CardCreationOptions.cs:139/152/162), i.e. every event/relic creation
      that is not `ForRoom`.
    - `NO_MODIFY_HOOKS` is the flag spelling of `modify_hooks=False`
      (`CardFactory.cs:104` is the single gate on the reward-options passes),
      so passing either has the same effect.

    The others are inert here and exist for the LISTENERS to read off
    `CardCreationOptions.flags`: `NO_CARD_POOL_MODIFICATIONS` is what makes
    Dingy Rug (DingyRug.cs:19-22), Prismatic Gem, Character Cards and Big Game
    Hunter leave a caller-specified pool alone, and `NO_RARITY_MODIFICATION` /
    `NO_CARD_MODEL_MODIFICATIONS` have no ported reader yet.
    """
    # CardFactory.CreateForReward draws on the per-player Rewards stream in the
    # SP2 parity path (rng_set present); the legacy RL path stays on run.rng.
    # `rng` overrides that for a caller whose CardCreationOptions carry
    # `.WithRngOverride(...)` — Crystal Sphere hands every ToReward the EVENT's
    # own Rng (CrystalSphereCardReward.cs:49-54), so its screens must not
    # advance the per-player Rewards stream.
    if rng is None:
        rng = run.rewards_rng
    if pool is None:
        # The game's reward pool is CardCreationOptions.GetPossibleCards ==
        # CardPool.GetUnlockedCards() — the FULL unlocked pool, NOT
        # FilterForCombat. In the SP2 parity path use it so Feed / NotYet
        # (Rare, CanBeGeneratedInCombat=false) can be offered as rewards; the
        # legacy RL path keeps the combat-filtered pool byte-for-byte.
        pool = (
            reward_pool_card_ids(run.card_pool) if run.rng_set is not None
            else pool_card_ids(pool=run.card_pool)  # minus Basic/Ancient
        )
    # Hook.ModifyCardRewardCreationOptions (CardFactory.cs:216) runs BEFORE
    # the pool is read, so a listener can widen it — Dingy Rug appends the
    # Colorless pool (DingyRug.cs:13-36), Prismatic Gem the other characters'.
    # C# dispatches it once per card, always from the same starting options,
    # so a single pass before the loop yields the same pool.
    flags = ((CardCreationFlags.IS_CARD_REWARD if is_card_reward
              else CardCreationFlags(0))
             | (CardCreationFlags(0) if modify_hooks
                else CardCreationFlags.NO_MODIFY_HOOKS)
             | extra_flags)
    # `!options.Flags.HasFlag(NoModifyHooks)` (CardFactory.cs:104) is the one
    # gate C# puts on the reward-options passes, so the boolean parameter and
    # the flag are the same switch seen from two sides — a caller that spells
    # it as a flag must get the same behaviour as one that passes the bool.
    if flags & CardCreationFlags.NO_MODIFY_HOOKS:
        modify_hooks = False
    # `if (!options.Flags.HasFlag(CardCreationFlags.NoUpgradeRoll))
    #      RollForUpgrade(player, cardModel, 0m, rng);` (CardFactory.cs:98-102).
    # The draw itself (`rng.NextFloat()`, CardFactory.cs:290) is INSIDE the
    # guarded call, so suppressing the roll also gives the draw back.
    roll_for_upgrade = not (flags & CardCreationFlags.NO_UPGRADE_ROLL)
    creation = CardCreationOptions(
        pool=tuple(pool),
        source=(CardCreationSource.ENCOUNTER if mutate_pity
                else CardCreationSource.OTHER),
        odds_type=odds_type,
        flags=flags,
    )
    if modify_hooks:
        for relic in list(run.relics):
            creation = relic.modify_card_reward_creation_options(run, creation)
        pool = list(creation.pool)
    chosen_ids: list[str] = []
    cards: list[Card] = []
    for _ in range(count):
        options = [cid for cid in pool if cid not in chosen_ids]
        if not options:
            break
        if odds_type is RarityOddsType.UNIFORM:
            # CardFactory.cs:219-221: the Uniform branch takes NO rarity roll
            # at all. `items` is the whole blacklist-filtered candidate list
            # (minus Basic and Ancient, which both pool helpers already drop)
            # and NextItem picks straight out of it — the caller narrows the
            # pool instead, which is what `GetPossibleCards`' predicate does
            # (Glass Eye's `c.Rarity == rarity`, Room Full of Cheese's
            # `Rarity == Common`). The sim ran RollWithBaseOdds here too, which
            # burned one extra PlayerRng.Rewards draw per card the game never
            # takes and could roll a rarity the caller's pool did not contain.
            matching = options
        else:
            if mutate_pity:
                rarity = run.card_rarity_odds.roll(odds_type)
            else:
                rarity = run.card_rarity_odds.roll_with_base_odds(odds_type)
            rarity = next_allowed_card_rarity(
                rarity,
                lambda r: any(_CARD_CLASSES[cid].rarity == r for cid in options),
            )
            if rarity is None:
                break
            matching = [cid for cid in options
                        if _CARD_CLASSES[cid].rarity == rarity]
        card = make_card(_draw_choice(rng, matching))
        chosen_ids.append(card.id)
        # RollForUpgrade: the draw happens for every reward card; only
        # upgradable non-rares get the act-scaled chance (rares stay at 0).
        # Skipped WHOLESALE — draw included — under NoUpgradeRoll, see above.
        if roll_for_upgrade:
            upgrade_roll = _uniform(rng)
            if card.is_upgradable:
                odds = 0.0
                if card.rarity != CardRarity.RARE:
                    odds = run.act_index * upgraded_card_odd_scaling(run)
                if upgrade_roll <= odds:
                    card.upgrade()
        cards.append(card)
    if modify_hooks:
        options = creation
        # Hook.TryModifyCardRewardOptions (Hook.cs:1445-1467) makes TWO
        # complete passes over the listeners: every relic's plain hook, then
        # every relic's Late hook. The order is load-bearing — Lasting Candy
        # ADDS an option in the first pass and the egg relics / Silver Crucible
        # / Silken Tress / Glitter all upgrade or enchant in the second, so
        # the added card must be visible to them whichever relic registered
        # first.
        #
        # Each pass collects the listeners that returned TRUE into `modifiers`,
        # and Hook.AfterModifyingCardRewardOptions (Hook.cs:679-690, dispatched
        # from CardFactory.cs:106 and CardReward.cs:153) notifies exactly
        # those. Silken Tress and Silver Crucible spend their one-shot THERE,
        # not inside the modifier.
        modifiers: list = []
        for relic in list(run.relics):
            if relic.modify_card_reward_options(run, cards, options):
                modifiers.append(relic)
        for relic in list(run.relics):
            if relic.modify_card_reward_options_late(run, cards, options):
                modifiers.append(relic)
        for relic in modifiers:
            relic.after_modify_card_reward_options(run)
    return cards


class RewardExtraKind(Enum):
    """Which payload a queued post-combat extra carries.

    Source: a combat (or combat event) queues extra reward instances onto its
    room via CombatRoom.AddExtraReward (src/Core/Rooms/CombatRoom.cs); the
    reward screen folds them in via RewardsSet.WithRewardsFromRoom
    (src/Core/Rewards/RewardsSet.cs). Each Reward subtype maps to a kind here.
    """

    CARD = "card"        # SpecialCardReward — a specific card added to the deck
    RELIC = "relic"      # a specific relic instance
    POTION = "potion"    # a specific potion instance
    UPGRADE = "upgrade"  # an upgrade granted to a specific deck card
    GOLD = "gold"        # GoldReward(wasGoldStolenBack) — stolen gold returned


@dataclass
class RewardExtra:
    """One "pending post-combat extra": a reward a combat appends during the
    fight for the reward screen to surface afterwards. Exactly one payload
    field is set, selected by `kind`.

    Producers today: CARD — Thieving Hopper's returned card
    (src/Core/Models/Powers/SwipePower.cs BeforeDeath -> SpecialCardReward)
    and The Lantern Key's card (TheLanternKey.cs Fight); RELIC / POTION —
    Punch-Off's fight purse (PunchOff.cs Fight: RelicReward + PotionReward,
    rolled at screen time when the payload is None). UPGRADE is declared for
    completeness but has no producer — Battleworn Dummy's upgrades are
    granted directly on event resume (BattlewornDummy.cs Resume), not via
    the reward screen."""

    kind: RewardExtraKind
    card: "Card | None" = None
    relic: "Relic | None" = None
    potion: "Potion | None" = None
    upgrade: "Card | None" = None
    gold: int = 0

    @classmethod
    def of_card(cls, card: Card) -> "RewardExtra":
        """A returned/special card reward (SpecialCardReward)."""
        return cls(kind=RewardExtraKind.CARD, card=card)

    @classmethod
    def of_relic(cls, relic: "Relic | None" = None) -> "RewardExtra":
        """A relic reward (RelicReward); None rolls the grab bag at screen
        time, like the game's RelicReward(player)."""
        return cls(kind=RewardExtraKind.RELIC, relic=relic)

    @classmethod
    def of_potion(cls, potion: "Potion | None" = None) -> "RewardExtra":
        """A potion offer (PotionReward); None rolls a random potion at
        screen time, like the game's PotionReward(player)."""
        return cls(kind=RewardExtraKind.POTION, potion=potion)

    @classmethod
    def of_gold(cls, amount: int) -> "RewardExtra":
        """Stolen gold returned on the reward screen (GoldReward with
        wasGoldStolenBack — HeistPower.cs BeforeDeath)."""
        return cls(kind=RewardExtraKind.GOLD, gold=amount)


@dataclass
class CardRewardGroup:
    """One `CardReward` instance on a reward set (src/Core/Rewards/CardReward.cs):
    an independent pick-one-of-N screen with its own creation options, its own
    CanReroll flag and its own alternatives list.

    A reward set holds a LIST of Rewards, so several CardRewards can sit on one
    screen and each is taken separately — Prayer Wheel adds a second one to
    every Monster room (PrayerWheel.cs:14-25) and White Star adds a Boss-odds
    one to every Elite (WhiteStar.cs:19-28). Modelling the card choice as a
    single flat list on CombatRewards collapsed those into one pick-one-of-N,
    which halved what the player could keep.
    """

    cards: list[Card] = field(default_factory=list)
    # `CardCreationOptions.ForRoom(owner, roomType)` — this group's odds table,
    # which is NOT always the room's: White Star's extra Elite group draws on
    # Boss odds, and Dream Catcher's rest group on Monster odds.
    room_type: RoomType = RoomType.MONSTER
    # CardReward.CanReroll (Driftwood): one-shot; the reroll regenerates the
    # options through the same creation path and clears the flag.
    can_reroll: bool = False
    # Hook.TryModifyCardRewardAlternatives (Pael's Wing): the relic offering a
    # SACRIFICE alternative on THIS card reward — choosing it forgoes the cards
    # and calls relic.on_sacrifice(run).
    sacrifice_relic: "Relic | None" = None
    # `new CardReward(options, count, player)` — 3 everywhere today.
    count: int = CARD_REWARD_COUNT
    # Reward.IsPopulated. A group a hook ADDS during Hook.ModifyRewards is
    # still unpopulated when the passes finish, and RewardsSet.cs:137-143
    # populates it only afterwards — so its card draws land AFTER the late
    # pass, not in the middle of it.
    populated: bool = False
    # A group whose `CardCreationOptions` are NOT `ForRoom(owner, roomType)`.
    # `ForNonCombatWithUniformOdds(pool, predicate)` is the other constructor
    # in the source — Glass Eye's five fixed-rarity screens (GlassEye.cs:29),
    # Room Full of Cheese's Commons, The Future of Potions' typed screen. Set
    # `pool` (the predicate, applied by the caller) and `odds_type` together;
    # `room_type` then only labels the screen for the obs.
    pool: "tuple[str, ...] | None" = None
    odds_type: "RarityOddsType | None" = None
    # The rest of this screen's `CardCreationFlags` — everything its
    # construction site's `CardCreationOptions` factory and `.WithFlags(...)`
    # chain set, on top of the `IsCardReward` every `CardReward` constructor
    # ORs on unconditionally (CardReward.cs:114-115).
    #
    # `CardCreationOptions.ForRoom` (the post-combat screens) sets NONE, which
    # is why the default is empty. Every `ForNonCombatWith*` factory sets
    # `NO_UPGRADE_ROLL` (CardCreationOptions.cs:139/152/162) and its caller
    # adds its own on top — The Future of Potions' screen is
    # `ForNonCombatWithUniformOdds(...).WithFlags(NoRarityModification |
    # NoCardPoolModifications)` (TheFutureOfPotions.cs:127), so its group
    # declares all three. Without this field a group could not express the
    # flags at all (create_reward_cards built its options internally), which
    # is how a NoCardPoolModifications screen ended up admitting Dingy Rug's
    # Colorless pool — see test_the_future_of_potions_offer_is_not_widened_
    # by_dingy_rug.
    flags: CardCreationFlags = CardCreationFlags(0)
    # The `CardCreationSource` this screen's `CardCreationOptions`
    # actually carries. `Source` is set by the *factory method* the
    # construction site calls (`ForRoom` -> Encounter/Shop/Other by room
    # type; every `ForNonCombatWith*` -> Other unconditionally —
    # CardCreationOptions.cs:102-163) and nothing else; it is INDEPENDENT of
    # whether the caller also overrode `pool`. `None` (the default) means "not
    # stated explicitly" and falls back to the old pool-is-None heuristic
    # below for every construction site that predates this field and never
    # needed to disagree with it. Set this explicitly on a group whose source
    # diverges from that heuristic — e.g. a `ForNonCombatWithDefaultOdds`
    # screen that reads the UN-overridden character pool (Source=Other,
    # pool=None): `events/trial.py`'s `_NonCombatCardRewardGroup` hardcodes
    # `mutate_pity=False` for exactly this case (Nondescript Guilty) instead
    # of using this field, and remains correct doing so — this field is an
    # alternative way to say the same thing for a group that doesn't need a
    # whole subclass.
    source: "CardCreationSource | None" = None
    # `CardCreationOptions.WithRngOverride(rng)` — the stream this screen's
    # draws come off when it is NOT the per-player Rewards one. Crystal
    # Sphere's card items are the only ported site that sets it
    # (CrystalSphereCardReward.cs:49-54).
    rng: object | None = None

    def _odds(self) -> "RarityOddsType":
        return (self.odds_type if self.odds_type is not None
                else ROOM_RARITY_ODDS[self.room_type])

    def _mutate_pity(self) -> bool:
        """Whether this screen's rarity roll mutates the run's pity offset:
        true only for `CardCreationSource.Encounter`
        (`CardFactory.RollForRarity`, CardFactory.cs:244-260). Prefers the
        explicit `source` field; falls back to the pool-is-None heuristic
        (a pool override implies a non-Encounter, Other-sourced creation,
        which holds for every site that doesn't set `source`) when it is
        unset."""
        if self.source is not None:
            return self.source == CardCreationSource.ENCOUNTER
        return self.pool is None

    def populate(self, run) -> None:
        """CardReward.Populate: draw this group's options."""
        self.populated = True
        self.cards = create_reward_cards(
            run, self._odds(), count=self.count,
            mutate_pity=self._mutate_pity(),
            pool=list(self.pool) if self.pool is not None else None,
            is_card_reward=True,          # CardReward.cs:114-115
            extra_flags=self.flags,
            rng=self.rng,
        )

    def reroll(self, run) -> None:
        """CardReward.Reroll: one-shot — clear the flag and regenerate the
        options via the same room-typed creation path (Populate)."""
        self.can_reroll = False
        self.populate(run)


@dataclass
class CombatRewards:
    """One post-combat reward screen: gold is granted when the screen is
    generated (the sim has no skip-gold button); the card choice, the potion
    and each relic are decisions the caller (env/driver) presents to the
    policy."""

    room_type: RoomType
    # `RewardsSet.Room` (RewardsSet.cs:45), as a room type. Set only by
    # WithRewardsFromRoom / EmptyForRoom; a set built by
    # RewardsCmd.OfferCustom for a rest-site heal, an event or a relic leaves
    # it null (RewardsSet.cs:106-110), and every room-gated TryModifyRewards
    # implementer short-circuits on that null — AmethystAubergine.cs:29-32,
    # BlackStar.cs, LavaRock.cs, WhiteStar.cs, PrayerWheel.cs on
    # `room == null`, WongosMysteryTicket.cs:86 on `!(room is CombatRoom)`.
    # DISTINCT from `room_type` above, which is this screen's card-odds table:
    # a rest-heal screen draws on Monster odds (CardCreationOptions.ForRoom
    # (owner, RoomType.Monster) in DreamCatcher.cs) with no room at all.
    room: "RoomType | None" = None
    gold: int = 0
    # Every PotionReward on this set, in list order. Usually one (the pity
    # drop), but a set built by RewardsCmd.OfferCustom can carry several —
    # Crystal Sphere reveals up to three at once (two Common + one Rare,
    # CrystalSphereMinigame.cs:165-173). `potion` below is a view onto the
    # FIRST, the same shape `card_rewards` / `cards` already uses, so every
    # single-potion reader and the one-slot `reward.potion` obs block keep
    # working unchanged.
    potions: list["Potion"] = field(default_factory=list)
    # Every CardReward on this set, in list order. Usually one; a relic can
    # add more (Prayer Wheel, White Star). `cards` / `can_reroll` /
    # `sacrifice_relic` below are views onto the FIRST, which is what a
    # one-group screen — every screen the sim built before Prayer Wheel — is.
    card_rewards: list[CardRewardGroup] = field(default_factory=list)
    # The RelicRewards on this screen: the elite's grab-bag relic, plus any
    # hook-added extras (Lava Rock's two on the act-1 boss). Each is OFFERED
    # take-or-skip as the screen is populated (RunState.offer_relic), so a
    # declined one is still listed here — its Populate already spent the bag
    # slot — but never joins run.relics.
    relics: "list[Relic]" = field(default_factory=list)
    # Extra single-card rewards queued during combat (CombatRoom.ExtraRewards:
    # Thieving Hopper's returned card, The Lantern Key's card). Unlike `cards`
    # (a pick-one-of-N group), each is an independent take-or-skip
    # SpecialCardReward.
    special_cards: list[Card] = field(default_factory=list)
    # Extra potion offers (PotionReward extras: Punch-Off's fight purse).
    # Each is an independent take-or-skip offer, separate from the pity-rolled
    # `potion` slot.
    special_potions: "list[Potion]" = field(default_factory=list)
    # `RewardsSet._isGenerated` (RewardsSet.cs:41, guard :127-130, set :146):
    # whether `apply_reward_modifiers` has already run on this set. Makes the
    # dispatch idempotent per instance, mirroring how `GenerateWithoutOffering`
    # no-ops on a set that already went through it — which is what lets
    # `Offer()` call it again unconditionally at RewardsSet.cs:159. Construction
    # sites call `apply_reward_modifiers` explicitly (RNG-order-preserving —
    # see the function's docstring), and `driver._offer_rewards` /
    # `RunState.offer_rewards` call it again as a backstop; this flag is what
    # makes calling it from both places safe instead of double-firing hooks.
    generated: bool = False

    # ── The first CardReward, as flat attributes ─────────────────────────
    # Every screen the sim generates on its own has exactly one card group,
    # and the driver, the RL obs and the conformance runner all describe ONE
    # card choice at a time, so these read and write `card_rewards[0]`.
    # Assigning any of them on an empty screen creates that first group.

    def _first_group(self) -> CardRewardGroup:
        if not self.card_rewards:
            self.card_rewards.append(
                CardRewardGroup(room_type=self.room_type, populated=True))
        return self.card_rewards[0]

    @property
    def cards(self) -> list[Card]:
        return self.card_rewards[0].cards if self.card_rewards else []

    @cards.setter
    def cards(self, value: list[Card]) -> None:
        self._first_group().cards = value

    @property
    def can_reroll(self) -> bool:
        return bool(self.card_rewards) and self.card_rewards[0].can_reroll

    @can_reroll.setter
    def can_reroll(self, value: bool) -> None:
        self._first_group().can_reroll = value

    @property
    def sacrifice_relic(self) -> "Relic | None":
        return self.card_rewards[0].sacrifice_relic if self.card_rewards else None

    @sacrifice_relic.setter
    def sacrifice_relic(self, value: "Relic | None") -> None:
        self._first_group().sacrifice_relic = value

    def reroll(self, run) -> None:
        """CardReward.Reroll on the first card group."""
        self._first_group().reroll(run)

    @property
    def potion(self) -> "Potion | None":
        """The first PotionReward on the screen — the pity drop on every set
        the sim generates on its own. A view onto `potions`, so the driver's
        one-at-a-time REWARD_POTION decision and the one-slot `reward.potion`
        obs block read the potion currently being offered."""
        return self.potions[0] if self.potions else None

    @potion.setter
    def potion(self, value: "Potion | None") -> None:
        if value is None:
            self.potions = []
        elif self.potions:
            self.potions[0] = value
        else:
            self.potions.append(value)

    @property
    def relic(self) -> "Relic | None":
        """The primary relic (an elite's drop), if any."""
        return self.relics[0] if self.relics else None

    @property
    def is_empty(self) -> bool:
        return (
            self.gold == 0
            and not self.potions
            and not any(g.cards for g in self.card_rewards)
            and not self.relics
            and not self.special_cards
            and not self.special_potions
        )


def apply_reward_modifiers(run: "RunState", rewards: CombatRewards) -> None:
    """`Hook.ModifyRewards(RunState, Player, Rewards, Room)` (Hook.cs:1981-1999)
    — two complete passes over the listeners, TryModifyRewards then
    TryModifyRewardsLate, so Driftwood's reroll flag lands on a reward list
    that already holds everything the plain pass added.

    C#'s ONE choke point is `RewardsSet.GenerateWithoutOffering`
    (RewardsSet.cs:125-147), but it is reached from TWO different entry
    points, not one:

    - Room-end sets dispatch at GENERATE time: `RewardsCmd.GenerateForRoomEnd`
      (RewardsCmd.cs:55-60) builds the set and calls
      `GenerateWithoutOffering()` itself, before the caller ever offers it
      (`CombatRoom.cs:267`, `TreasureRoom.cs:82`).
    - Every OfferCustom set dispatches at OFFER time, for the first and only
      time: `RewardsCmd.OfferCustom` (RewardsCmd.cs:47-50) is
      `new RewardsSet(player).WithCustomRewards(rewards).Offer()` — there is
      no `GenerateWithoutOffering` call beforehand, so `Offer()`'s own call
      to it at RewardsSet.cs:159 is the FIRST dispatch, not a repeat. This is
      the majority case: every rest-site heal (HealRestSiteOption.cs:112), 13
      events (14 call sites; e.g. BrainLeech.cs:58, Trial.cs:185) and 8
      relics (e.g. GlassEye.cs:32) go through `OfferCustom`.

    `GenerateWithoutOffering` is guarded idempotent by `_isGenerated`
    (RewardsSet.cs:127-130, set :146) precisely so it is safe to call from
    BOTH entry points — for a room-end set the call at `Offer()`:159 really is
    a no-op repeat, but for an OfferCustom set it is the only call that ever
    fires. The guard exists for the two-entry-point shape, not because one
    entry point "always generates before offering" (it doesn't, for most
    callers).

    The sim mirrors both entry points: `rewards.generated` is the
    `_isGenerated` mirror — a set this function has already processed returns
    immediately — so this call still sits at each construction site
    (rewards.py:751,814; run.py:1456; glass_eye.py:78; brain_leech.py:89;
    trial.py:118), preserving their exact RNG draw order and mirroring the
    generate-time entry point, AND `driver._offer_rewards` /
    `RunState.offer_rewards` call it again as an idempotent backstop mirroring
    the offer-time entry point — so a future site that forgets the explicit
    call still gets dispatched exactly once, at offer time, instead of
    silently skipping every reward-modifying relic (see GAP-QUEUE.md's
    event/3C section).

    What keeps the room-gated relics off a custom screen is `rewards.room`
    being None there, exactly as `RewardsSet.Room` is null for
    `WithCustomRewards`.
    """
    if rewards.generated:
        return
    for relic in list(run.relics):
        relic.modify_combat_rewards(run, rewards)
    for relic in list(run.relics):
        relic.modify_combat_rewards_late(run, rewards)
    # `foreach (Reward item in Rewards.Except(second)) if (!item.IsPopulated)
    # item.Populate();` (RewardsSet.cs:137-143): a card group a hook ADDED
    # draws its options here, after BOTH passes — so Prayer Wheel's three
    # cards come off the Rewards stream behind everything the late pass did.
    for group in rewards.card_rewards:
        if not group.populated:
            group.populate(run)
    # `_isGenerated = true` (RewardsSet.cs:146) — set LAST, after the passes
    # and the populate sweep, matching the source's own ordering.
    rewards.generated = True


def generate_combat_rewards(
    run: "RunState",
    room_type: RoomType,
    gold_proportion: float = 1.0,
    encounter: "Encounter | None" = None,
) -> CombatRewards:
    """RewardsSet.WithRewardsFromRoom + GenerateRewardsFor for a combat room.

    Gold is added to the run and any elite relic is obtained immediately
    (both are pure gains); the 3-card choice and the potion are left on the
    returned CombatRewards for the caller to offer. The final act's boss
    yields nothing (the run is over).

    `encounter` supplies its Min/MaxGoldReward override when it has one.
    """
    rewards = CombatRewards(room_type=room_type, room=room_type)
    if room_type not in GOLD_REWARD_RANGES:
        raise ValueError(f"No combat rewards for room type {room_type!r}")
    if room_type == RoomType.BOSS and run.is_final_act:
        # `RewardsSet.WithRewardsFromRoom` returns early here (RewardsSet.cs:
        # 85-91) WITHOUT adding the room's own Gold/Potion/Card rewards — but
        # it has already set `Room`, and the separate GenerateWithoutOffering
        # still runs Hook.ModifyRewards over the (empty) list. So the hooks
        # fire on the run's last boss like anywhere else; AmethystAubergine.cs:
        # 33-35's explicit final-act guard would be dead code otherwise.
        apply_reward_modifiers(run, rewards)
        return rewards

    gold_range = None
    if encounter is not None and encounter.min_gold is not None:
        gold_range = (encounter.min_gold, encounter.max_gold)

    # Hook.ShouldForcePotionReward over the run's relics.
    force = any(
        relic.should_force_potion_reward(run, room_type) for relic in run.relics
    )
    give_gold = not (room_type == RoomType.MONSTER and gold_proportion <= 0.0)

    if run.rng_set is not None:
        # SP2 parity: reproduce RewardsSet's exact draw order on the per-player
        # Rewards stream. The potion-drop *pity* is rolled during reward
        # generation (RollForPotionAndAddTo), before any reward Populate — so it
        # precedes the gold draw — while the potion itself is generated later
        # (PotionReward.Populate runs after GoldReward.Populate in list order).
        rew = run.rewards_rng
        got_potion = run.potion_reward_odds.roll(room_type, force=force)
        if give_gold:
            rewards.gold = roll_gold_reward(
                rew, room_type, gold_proportion, gold_range, run=run)
            run.gain_gold(rewards.gold)
        if got_potion:
            from .potion_pools import generate_random_potion
            rewards.potion = generate_random_potion(rew, pool=run.potion_pool)
        rewards.cards = create_reward_cards(
            run, ROOM_RARITY_ODDS[room_type], is_card_reward=True)
        if room_type == RoomType.ELITE:
            # RelicReward.Populate -> PullNextRelicFromFront(player): the rarity
            # roll is the only Rewards draw (the bag pull consumes none). Roll on
            # the reward stream for counter parity, then pull the implemented
            # relic from the sim's bag.
            from .run import roll_relic_rarity
            rarity = roll_relic_rarity(rew)
            relic = run.pull_relic_from_front(rarity=rarity)
            if relic is not None:
                # RelicReward is take-or-skip (RelicReward.cs:109-123): offer
                # it, and list it on the screen either way — the pull already
                # happened in Populate, so a decline still spends the bag slot.
                run.offer_relic(relic)
                rewards.relics.append(relic)
    else:
        # Legacy RL path (pre-SP2 draw order on the shared run.rng).
        if give_gold:
            rewards.gold = roll_gold_reward(
                run.rng, room_type, gold_proportion, gold_range, run=run)
            run.gain_gold(rewards.gold)
        if run.potion_reward_odds.roll(room_type, force=force):
            rewards.potion = run.random_potion()
        rewards.cards = create_reward_cards(
            run, ROOM_RARITY_ODDS[room_type], is_card_reward=True)
        if room_type == RoomType.ELITE:
            relic = run.pull_relic_from_front()
            if relic is not None:
                # RelicReward is take-or-skip (RelicReward.cs:109-123): offer
                # it, and list it on the screen either way — the pull already
                # happened in Populate, so a decline still spends the bag slot.
                run.offer_relic(relic)
                rewards.relics.append(relic)

    apply_reward_modifiers(run, rewards)

    # Pending post-combat extras queued during the fight or attached by a
    # combat event (CombatRoom's ExtraRewards, folded in by
    # RewardsSet.WithRewardsFromRoom). CARD = SpecialCardReward (Thieving
    # Hopper's return, The Lantern Key's card): a take-or-skip offer. RELIC =
    # RelicReward (Punch-Off's fight): payload-less entries roll the grab bag
    # at screen time and are granted with the screen, like the elite branch
    # above. POTION = PotionReward (Punch-Off's fight): payload-less entries
    # roll a random potion at screen time; each is its own take-or-skip
    # offer. Consume and clear the run's channel so each screen surfaces its
    # own extras once.
    for extra in run.pending_reward_extras:
        if extra.kind == RewardExtraKind.CARD and extra.card is not None:
            rewards.special_cards.append(extra.card)
        elif extra.kind == RewardExtraKind.RELIC:
            relic = extra.relic if extra.relic is not None else run.pull_relic_from_front()
            if relic is not None:
                # RelicReward is take-or-skip (RelicReward.cs:109-123): offer
                # it, and list it on the screen either way — the pull already
                # happened in Populate, so a decline still spends the bag slot.
                run.offer_relic(relic)
                rewards.relics.append(relic)
        elif extra.kind == RewardExtraKind.POTION:
            potion = extra.potion if extra.potion is not None else run.random_potion()
            rewards.special_potions.append(potion)
        elif extra.kind == RewardExtraKind.GOLD and extra.gold > 0:
            # Stolen gold returned (GoldReward wasGoldStolenBack): granted
            # with the screen like the normal gold reward.
            rewards.gold += extra.gold
            run.gain_gold(extra.gold)
    run.pending_reward_extras.clear()
    return rewards
