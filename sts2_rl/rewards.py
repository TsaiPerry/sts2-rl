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
        rare, uncommon, _ = _BASE_RARITY_ODDS[odds_type]
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
        """Whether this room's rewards include a potion. Mutates the pity."""
        bonus = self.ELITE_BONUS if room_type == RoomType.ELITE else 0.0
        threshold = self.current_value + bonus * 0.5
        hit = force or _uniform(self._rng) < threshold
        self.current_value += -self.STEP if hit else self.STEP
        return hit


def roll_gold_reward(
    rng: random.Random,
    room_type: RoomType,
    proportion: float = 1.0,
    gold_range: tuple[int, int] | None = None,
) -> int:
    """GoldReward.Populate: NextInt(min, max+1) on the room type's range,
    with the Monster range scaled by the encounter's GoldProportion.

    `gold_range` overrides the room-type default with an encounter's own
    Min/MaxGoldReward (both are virtual on EncounterModel — the Fake Merchant
    pins 300)."""
    from .rng import Rng

    lo, hi = gold_range if gold_range is not None else GOLD_REWARD_RANGES[room_type]
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
    """
    # CardFactory.CreateForReward draws on the per-player Rewards stream in the
    # SP2 parity path (rng_set present); the legacy RL path stays on run.rng.
    rng = run.rewards_rng
    if pool is None:
        # The game's reward pool is CardCreationOptions.GetPossibleCards ==
        # CardPool.GetUnlockedCards() — the FULL unlocked pool, NOT
        # FilterForCombat. In the SP2 parity path use it so Feed / NotYet
        # (Rare, CanBeGeneratedInCombat=false) can be offered as rewards; the
        # legacy RL path keeps the combat-filtered pool byte-for-byte.
        pool = (
            reward_pool_card_ids() if run.rng_set is not None
            else pool_card_ids()  # Ironclad pool minus Basic/Ancient
        )
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
        card = make_card(_draw_choice(rng, matching))
        chosen_ids.append(card.id)
        # RollForUpgrade: the draw happens for every reward card; only
        # upgradable non-rares get the act-scaled chance (rares stay at 0).
        upgrade_roll = _uniform(rng)
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
    # Extra single-card rewards queued during combat (CombatRoom.ExtraRewards:
    # Thieving Hopper's returned card, The Lantern Key's card). Unlike `cards`
    # (a pick-one-of-N group), each is an independent take-or-skip
    # SpecialCardReward.
    special_cards: list[Card] = field(default_factory=list)
    # Extra potion offers (PotionReward extras: Punch-Off's fight purse).
    # Each is an independent take-or-skip offer, separate from the pity-rolled
    # `potion` slot.
    special_potions: "list[Potion]" = field(default_factory=list)
    # CardReward.CanReroll (Driftwood): the card choice may be rerolled once —
    # the reroll regenerates the options through the same creation path and
    # clears the flag (CardReward.Reroll).
    can_reroll: bool = False
    # Hook.TryModifyCardRewardAlternatives (Pael's Wing): the relic offering a
    # SACRIFICE alternative on this card reward — choosing it forgoes the
    # cards and calls relic.on_sacrifice(run) (every 2nd sacrifice pulls the
    # next grab-bag relic).
    sacrifice_relic: "Relic | None" = None

    def reroll(self, run) -> None:
        """CardReward.Reroll: one-shot — clear the flag and regenerate the
        card options via the same room-typed creation path (Populate)."""
        self.can_reroll = False
        self.cards = create_reward_cards(run, ROOM_RARITY_ODDS[self.room_type])

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
            and not self.special_cards
            and not self.special_potions
        )


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
    rewards = CombatRewards(room_type=room_type)
    if room_type not in GOLD_REWARD_RANGES:
        raise ValueError(f"No combat rewards for room type {room_type!r}")
    if room_type == RoomType.BOSS and run.is_final_act:
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
                rew, room_type, gold_proportion, gold_range)
            run.gain_gold(rewards.gold)
        if got_potion:
            from .potion_pools import generate_random_potion
            rewards.potion = generate_random_potion(rew)
        rewards.cards = create_reward_cards(run, ROOM_RARITY_ODDS[room_type])
        if room_type == RoomType.ELITE:
            # RelicReward.Populate -> PullNextRelicFromFront(player): the rarity
            # roll is the only Rewards draw (the bag pull consumes none). Roll on
            # the reward stream for counter parity, then pull the implemented
            # relic from the sim's bag.
            from .run import roll_relic_rarity
            rarity = roll_relic_rarity(rew)
            relic = run.pull_relic_from_front(rarity=rarity)
            if relic is not None:
                run.add_relic(relic)
                rewards.relics.append(relic)
    else:
        # Legacy RL path (pre-SP2 draw order on the shared run.rng).
        if give_gold:
            rewards.gold = roll_gold_reward(
                run.rng, room_type, gold_proportion, gold_range)
            run.gain_gold(rewards.gold)
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
                run.add_relic(relic)
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
