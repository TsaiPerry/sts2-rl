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
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .cards import Card, CardRarity, make_card
from .cards.base import _CARD_CLASSES
from .cards.pool import pool_card_ids
from .rooms import RoomType

if TYPE_CHECKING:
    from .potions import Potion
    from .relics import Relic
    from .run import RunState


class RarityOddsType(Enum):
    """CardRarityOddsType — which base-odds table a card roll uses."""

    REGULAR = "regular"
    ELITE = "elite"
    BOSS = "boss"
    SHOP = "shop"
    UNIFORM = "uniform"


# CardRarityOdds.GetBaseOdds, non-ascension values: (rare, uncommon, common).
_BASE_RARITY_ODDS: dict[RarityOddsType, tuple[float, float, float]] = {
    RarityOddsType.REGULAR: (0.03, 0.37, 0.60),
    RarityOddsType.ELITE: (0.10, 0.40, 0.50),
    RarityOddsType.BOSS: (1.0, 0.0, 0.0),
    RarityOddsType.SHOP: (0.09, 0.37, 0.54),
    RarityOddsType.UNIFORM: (0.33, 0.33, 0.33),
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

# CardFactory.UpgradedCardOddScaling — reward-card upgrade odds per act index.
UPGRADED_CARD_ODD_SCALING = 0.25

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
    GROWTH = 0.01          # RarityGrowth (non-Scarcity)

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self.current_value = self.BASE_OFFSET

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
        rare, uncommon, _ = _BASE_RARITY_ODDS[odds_type]
        roll = self._rng.random()
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
        rare, uncommon, _ = _BASE_RARITY_ODDS[odds_type]
        roll = self._rng.random()
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
        """Whether this room's rewards include a potion. Mutates the pity."""
        bonus = self.ELITE_BONUS if room_type == RoomType.ELITE else 0.0
        threshold = self.current_value + bonus * 0.5
        hit = force or self._rng.random() < threshold
        self.current_value += -self.STEP if hit else self.STEP
        return hit


def roll_gold_reward(
    rng: random.Random, room_type: RoomType, proportion: float = 1.0
) -> int:
    """GoldReward.Populate: NextInt(min, max+1) on the room type's range,
    with the Monster range scaled by the encounter's GoldProportion."""
    lo, hi = GOLD_REWARD_RANGES[room_type]
    if room_type == RoomType.MONSTER:
        lo, hi = round(lo * proportion), round(hi * proportion)
    if hi <= 0:
        return 0
    return rng.randint(lo, hi)


def create_reward_cards(
    run: "RunState",
    odds_type: RarityOddsType,
    count: int = CARD_REWARD_COUNT,
    mutate_pity: bool = True,
    modify_hooks: bool = True,
) -> list[Card]:
    """CardFactory.CreateForReward: `count` distinct pool cards, each from a
    rarity roll (escalated with wrapping when the pool lacks the rolled
    rarity) and an act-scaled upgrade draw.

    `mutate_pity=False` uses the non-mutating base-odds roll — the path for
    non-Encounter sources like Lost Coffer (RollForRarity only calls the
    mutating Roll for CardCreationSource.Encounter).
    `modify_hooks=False` skips Hook.TryModifyCardRewardOptionsLate
    (CardCreationFlags.NoModifyHooks).
    """
    rng = run.rng
    pool = pool_card_ids()  # Ironclad pool minus Basic/Ancient
    chosen_ids: list[str] = []
    cards: list[Card] = []
    for _ in range(count):
        options = [cid for cid in pool if cid not in chosen_ids]
        if not options:
            break
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
        matching = [cid for cid in options if _CARD_CLASSES[cid].rarity == rarity]
        card = make_card(rng.choice(matching))
        chosen_ids.append(card.id)
        # RollForUpgrade: the draw happens for every reward card; only
        # upgradable non-rares get the act-scaled chance (rares stay at 0).
        upgrade_roll = rng.random()
        if card.is_upgradable:
            odds = 0.0
            if card.rarity != CardRarity.RARE:
                odds = run.act_index * UPGRADED_CARD_ODD_SCALING
            if upgrade_roll <= odds:
                card.upgrade()
        cards.append(card)
    if modify_hooks:
        # Hook.TryModifyCardRewardOptionsLate over the run's relics (Silver
        # Crucible upgrades the options, Silken Tress enchants them).
        for relic in list(run.relics):
            relic.modify_card_reward_options(run, cards)
    return cards


@dataclass
class CombatRewards:
    """One post-combat reward screen: gold and any relics are granted when the
    screen is generated (the sim has no skip-gold button); the card choice and
    the potion are decisions the caller (env/driver) presents to the policy."""

    room_type: RoomType
    gold: int = 0
    potion: "Potion | None" = None
    cards: list[Card] = field(default_factory=list)
    # Relics granted with this screen: the elite's grab-bag relic, plus any
    # hook-added extras (Lava Rock's two on the act-1 boss).
    relics: "list[Relic]" = field(default_factory=list)

    @property
    def relic(self) -> "Relic | None":
        """The primary relic (an elite's drop), if any."""
        return self.relics[0] if self.relics else None

    @property
    def is_empty(self) -> bool:
        return (
            self.gold == 0
            and self.potion is None
            and not self.cards
            and not self.relics
        )


def generate_combat_rewards(
    run: "RunState",
    room_type: RoomType,
    gold_proportion: float = 1.0,
) -> CombatRewards:
    """RewardsSet.WithRewardsFromRoom + GenerateRewardsFor for a combat room.

    Gold is added to the run and any elite relic is obtained immediately
    (both are pure gains); the 3-card choice and the potion are left on the
    returned CombatRewards for the caller to offer. The final act's boss
    yields nothing (the run is over).
    """
    rewards = CombatRewards(room_type=room_type)
    if room_type not in GOLD_REWARD_RANGES:
        raise ValueError(f"No combat rewards for room type {room_type!r}")
    if room_type == RoomType.BOSS and run.is_final_act:
        return rewards

    if not (room_type == RoomType.MONSTER and gold_proportion <= 0.0):
        rewards.gold = roll_gold_reward(run.rng, room_type, gold_proportion)
        run.gain_gold(rewards.gold)

    # Hook.ShouldForcePotionReward over the run's relics.
    force = any(
        relic.should_force_potion_reward(run, room_type) for relic in run.relics
    )
    if run.potion_reward_odds.roll(room_type, force=force):
        rewards.potion = run.random_potion()

    rewards.cards = create_reward_cards(run, ROOM_RARITY_ODDS[room_type])

    if room_type == RoomType.ELITE:
        relic = run.pull_relic_from_front()
        if relic is not None:
            run.add_relic(relic)
            rewards.relics.append(relic)

    # Hook.ModifyRewards over the run's relics (Lava Rock adds two relic
    # rewards to the first act's boss screen). A hook that appends to
    # rewards.relics grants them itself (run.add_relic), like the elite
    # branch above.
    for relic in list(run.relics):
        relic.modify_combat_rewards(run, rewards)
    return rewards
