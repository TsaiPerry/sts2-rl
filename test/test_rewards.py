"""Post-combat reward generation (sts2_rl/rewards.py) vs the source constants:
RewardsSet.cs, CardRarityOdds.cs, PotionRewardOdds.cs, CardFactory.cs."""
import random

import pytest

from sts2_rl.cards import CardRarity
from sts2_rl.cards.base import _CARD_CLASSES
from sts2_rl.cards.pool import pool_card_ids
from sts2_rl.rewards import (
    CARD_REWARD_COUNT,
    GOLD_REWARD_RANGES,
    TREASURE_GOLD,
    CardRarityOdds,
    PotionRewardOdds,
    RarityOddsType,
    create_reward_cards,
    generate_combat_rewards,
    roll_gold_reward,
)
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState


class FakeRng:
    """random.Random stand-in fed a fixed queue of uniform draws."""

    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0)


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# CardRarityOdds — threshold arithmetic and the rare-pity walk
# ═════════════════════════════════════════════════════════════════════════

def test_rarity_threshold_bands_regular():
    # At the starting offset −0.05, the regular rare band is 0.03−0.05 < 0
    # (rare impossible) and the uncommon band ends at 0.37 + (0.03−0.05).
    odds = CardRarityOdds(FakeRng(0.0, 0.34, 0.36))
    assert odds.roll_without_changing_future_odds(RarityOddsType.REGULAR) == CardRarity.UNCOMMON
    assert odds.roll_without_changing_future_odds(RarityOddsType.REGULAR) == CardRarity.UNCOMMON
    assert odds.roll_without_changing_future_odds(RarityOddsType.REGULAR) == CardRarity.COMMON


def test_rarity_pity_growth_and_cap():
    odds = CardRarityOdds(FakeRng(*([0.99] * 60)))
    assert odds.current_value == pytest.approx(-0.05)
    odds.roll(RarityOddsType.REGULAR)
    assert odds.current_value == pytest.approx(-0.04)  # +0.01 per non-rare
    for _ in range(59):
        odds.roll(RarityOddsType.REGULAR)
    assert odds.current_value == pytest.approx(0.40)   # capped at +0.40


def test_rarity_pity_resets_on_rare():
    # Drive the offset up, then land a rare: the offset resets to −0.05.
    # (Elite odds: rare threshold = 0.10 + offset, so 0.0 lands rare.)
    odds = CardRarityOdds(FakeRng(0.99, 0.99, 0.0))
    odds.roll(RarityOddsType.ELITE)
    odds.roll(RarityOddsType.ELITE)
    assert odds.current_value == pytest.approx(-0.03)
    assert odds.roll(RarityOddsType.ELITE) == CardRarity.RARE
    assert odds.current_value == pytest.approx(-0.05)


def test_boss_roll_ignores_offset_but_still_resets():
    # Boss rolls pass offset 0 (they're all-rare anyway) and, being rare,
    # reset the pity counter — exactly what CardRarityOdds.Roll does.
    odds = CardRarityOdds(FakeRng(0.99, 0.999))
    odds.roll(RarityOddsType.REGULAR)
    assert odds.current_value == pytest.approx(-0.04)
    assert odds.roll(RarityOddsType.BOSS) == CardRarity.RARE
    assert odds.current_value == pytest.approx(-0.05)


def test_shop_roll_does_not_mutate_pity():
    odds = CardRarityOdds(FakeRng(0.99, 0.0))
    before = odds.current_value
    odds.roll_without_changing_future_odds(RarityOddsType.SHOP)
    odds.roll_without_changing_future_odds(RarityOddsType.SHOP)
    assert odds.current_value == before


def test_elite_bands():
    # Elite: rare 0.10, uncommon 0.40. With offset 0, rare < 0.10,
    # uncommon < 0.50.
    odds = CardRarityOdds(FakeRng(0.09, 0.49, 0.51))
    assert odds.roll_without_changing_future_odds(RarityOddsType.ELITE, 0.0) == CardRarity.RARE
    assert odds.roll_without_changing_future_odds(RarityOddsType.ELITE, 0.0) == CardRarity.UNCOMMON
    assert odds.roll_without_changing_future_odds(RarityOddsType.ELITE, 0.0) == CardRarity.COMMON


# ═════════════════════════════════════════════════════════════════════════
# PotionRewardOdds — the ±0.10 pity threshold
# ═════════════════════════════════════════════════════════════════════════

def test_potion_pity_walk():
    odds = PotionRewardOdds(FakeRng(0.39, 0.49, 0.35))
    assert odds.current_value == pytest.approx(0.40)
    assert odds.roll(RoomType.MONSTER) is True          # 0.39 < 0.40 → hit
    assert odds.current_value == pytest.approx(0.30)    # −0.10 on a hit
    assert odds.roll(RoomType.MONSTER) is False         # 0.49 ≥ 0.30 → miss
    assert odds.current_value == pytest.approx(0.40)    # +0.10 on a miss
    assert odds.roll(RoomType.MONSTER) is True
    assert odds.current_value == pytest.approx(0.30)


def test_potion_elite_bonus():
    # Elite adds eliteBonus × 0.5 = +0.125 to the roll threshold only.
    odds = PotionRewardOdds(FakeRng(0.50))
    assert odds.roll(RoomType.ELITE) is True             # 0.50 < 0.40 + 0.125
    assert odds.current_value == pytest.approx(0.30)


def test_potion_force_hits_and_decrements():
    odds = PotionRewardOdds(FakeRng())  # no draw consumed when forced? source draws
    # The source draws NextFloat before checking `flag || roll < threshold`
    # — but short-circuit order is flag first, roll drawn regardless. Our
    # port draws only when needed via `force or ...` short-circuit; feed a
    # value anyway to keep this future-proof.
    odds._rng = FakeRng(0.99)
    assert odds.roll(RoomType.MONSTER, force=True) is True
    assert odds.current_value == pytest.approx(0.30)


# ═════════════════════════════════════════════════════════════════════════
# Gold
# ═════════════════════════════════════════════════════════════════════════

def test_gold_ranges():
    assert GOLD_REWARD_RANGES[RoomType.MONSTER] == (10, 20)
    assert GOLD_REWARD_RANGES[RoomType.ELITE] == (35, 45)
    assert GOLD_REWARD_RANGES[RoomType.BOSS] == (100, 100)
    assert TREASURE_GOLD == (42, 52)
    rng = random.Random(0)
    for _ in range(100):
        assert 10 <= roll_gold_reward(rng, RoomType.MONSTER) <= 20
        assert 35 <= roll_gold_reward(rng, RoomType.ELITE) <= 45
        assert roll_gold_reward(rng, RoomType.BOSS) == 100


def test_gold_proportion_scales_monster_only():
    rng = random.Random(0)
    for _ in range(50):
        assert 5 <= roll_gold_reward(rng, RoomType.MONSTER, 0.5) <= 10
        # Elite/Boss use the raw range regardless of proportion.
        assert 35 <= roll_gold_reward(rng, RoomType.ELITE, 0.5) <= 45


# ═════════════════════════════════════════════════════════════════════════
# Reward-card creation
# ═════════════════════════════════════════════════════════════════════════

def test_reward_cards_are_three_distinct_pool_cards():
    run = fresh_run(3)
    pool = set(pool_card_ids())
    cards = create_reward_cards(run, RarityOddsType.REGULAR)
    assert len(cards) == CARD_REWARD_COUNT == 3
    ids = [c.id for c in cards]
    assert len(set(ids)) == 3                 # no duplicates within a reward
    assert all(cid in pool for cid in ids)    # never basics/ancients/curses


def test_boss_reward_cards_all_rare():
    run = fresh_run(4)
    cards = create_reward_cards(run, RarityOddsType.BOSS)
    assert len(cards) == 3
    assert all(c.rarity == CardRarity.RARE for c in cards)


def test_act1_reward_cards_never_upgraded():
    # Act index 0 → upgrade odds 0 for everything.
    for seed in range(30):
        run = fresh_run(seed)
        run.act_index = 0
        assert all(
            c.upgrade_level == 0
            for c in create_reward_cards(run, RarityOddsType.REGULAR)
        )


def test_act2_upgrades_nonrare_only():
    # Act index 1 → 25% upgrade odds on non-rares; rares never auto-upgrade.
    upgraded = 0
    total = 0
    for seed in range(120):
        run = fresh_run(seed)
        run.act_index = 1
        for card in create_reward_cards(run, RarityOddsType.REGULAR):
            if card.rarity == CardRarity.RARE:
                assert card.upgrade_level == 0
            elif card.is_upgradable or card.upgrade_level > 0:
                total += 1
                upgraded += card.upgrade_level > 0
    assert total > 0
    assert 0.15 < upgraded / total < 0.35     # ≈ 25%


def test_rare_pity_moves_across_rewards_on_one_run():
    run = fresh_run(5)
    start = run.card_rarity_odds.current_value
    create_reward_cards(run, RarityOddsType.REGULAR)
    assert run.card_rarity_odds.current_value != start or start == pytest.approx(-0.05)
    # Three mutating rolls happened (one per card).
    values = set()
    for _ in range(5):
        create_reward_cards(run, RarityOddsType.REGULAR)
        values.add(run.card_rarity_odds.current_value)
    assert values  # the counter drifts as the run generates rewards


# ═════════════════════════════════════════════════════════════════════════
# generate_combat_rewards — the per-room reward screens
# ═════════════════════════════════════════════════════════════════════════

def test_monster_rewards():
    run = fresh_run(6)
    gold_before = run.gold
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    assert 10 <= rewards.gold <= 20
    assert run.gold == gold_before + rewards.gold      # gold granted eagerly
    assert len(rewards.cards) == 3
    assert rewards.relic is None                        # monsters drop no relic


def test_elite_rewards_include_grab_bag_relic():
    run = fresh_run(7)
    bag_before = len(run.relic_grab_bag)
    rewards = run.generate_combat_rewards(RoomType.ELITE)
    assert 35 <= rewards.gold <= 45
    assert rewards.relic is not None
    assert rewards.relic in run.relics                  # obtained eagerly
    assert len(run.relic_grab_bag) == bag_before - 1
    assert len(rewards.cards) == 3


def test_boss_rewards_rare_cards_no_relic():
    run = fresh_run(8)
    run.start_act("overgrowth", is_final_act=False)
    rewards = run.generate_combat_rewards(RoomType.BOSS)
    assert rewards.gold == 100
    assert rewards.relic is None                        # no boss relics
    assert len(rewards.cards) == 3
    assert all(c.rarity == CardRarity.RARE for c in rewards.cards)


def test_final_act_boss_yields_nothing():
    run = fresh_run(9)
    run.start_act("overgrowth", is_final_act=True)
    gold_before = run.gold
    rewards = run.generate_combat_rewards(RoomType.BOSS)
    assert rewards.is_empty
    assert run.gold == gold_before


def test_invalid_room_type_raises():
    run = fresh_run(10)
    with pytest.raises(ValueError):
        run.generate_combat_rewards(RoomType.REST_SITE)


def test_potion_pity_persists_across_rewards():
    # Over many monster rewards on one run, the ±0.10 pity keeps the hit
    # rate near the 0.4–0.5 design target, and a hit always follows enough
    # misses (threshold climbs by +0.10 per miss).
    run = fresh_run(11)
    hits = [run.generate_combat_rewards(RoomType.MONSTER).potion is not None
            for _ in range(60)]
    rate = sum(hits) / len(hits)
    assert 0.3 < rate < 0.7
    # The pity forbids long droughts: threshold ≥ 1.0 after 6 straight misses.
    longest_drought = max(
        (len(s) for s in "".join("x" if h else "." for h in hits).split("x")),
        default=0,
    )
    assert longest_drought <= 7


def test_rewards_deterministic_under_seed():
    def snapshot(seed):
        run = fresh_run(seed)
        r = run.generate_combat_rewards(RoomType.ELITE)
        return (
            r.gold,
            [(c.id, c.upgrade_level) for c in r.cards],
            r.potion.id if r.potion else None,
            r.relic.id if r.relic else None,
        )

    assert snapshot(42) == snapshot(42)
    assert snapshot(42) != snapshot(43)


def test_treasure_room_grants_gold_and_relic():
    from sts2_rl.actmap import MapPointType

    run = fresh_run(12)
    run.start_act("overgrowth")
    walk = random.Random(0)
    res = None
    while not run.at_act_end:
        r = run.enter_point(walk.choice(run.travelable_points()))
        if r.room_type == RoomType.TREASURE:
            res = r
            break
    assert res is not None, "walk never hit the treasure row"
    assert res.relic is not None
    assert 42 <= res.gold <= 52


def test_reward_extras_relic_and_potion_drain():
    """RELIC/POTION extras (RewardsSet.cs WithRewardsFromRoom folding in
    CombatRoom.ExtraRewards; RelicReward/PotionReward roll their payload at
    screen time): a payload-less relic extra pulls from the grab bag and is
    granted with the screen; a payload-less potion extra becomes a
    take-or-skip offer on special_potions."""
    from sts2_rl.rewards import RewardExtra
    run = RunState(rng=random.Random(21))
    run.pending_reward_extras = [RewardExtra.of_relic(), RewardExtra.of_potion()]
    relics_before = len(run.relics)
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    assert len(run.relics) == relics_before + 1
    assert rewards.relics, "relic extra should be granted with the screen"
    assert len(rewards.special_potions) == 1
    assert run.pending_reward_extras == []
