"""Glass Eye's five card rewards, as one `RewardsCmd.OfferCustom` set.

`GlassEye.AfterObtained` (GlassEye.cs:16-33) builds five `CardReward`s —
Common, Common, Uncommon, Uncommon, Rare — each `ForNonCombatWithUniformOdds
(Character.CardPool, c => c.Rarity == rarity).WithFlags(NoRarityModification)`,
and hands all five to one `RewardsCmd.OfferCustom`. That closes four separate
findings the port had:

  G2  the LEGACY (non-parity) branch created its cards with no upgrade roll at
      all, where the sim's own house convention performs the roll in both modes
      and varies only the stream
  G3  no `Hook.TryModifyCardRewardOptions` — CardFactory fires both passes at
      the end of every `CreateForReward` (CardFactory.cs:104-107), which is how
      the egg relics and Glitter reach an offer
  G4  the candidates came from `pool_card_ids()` (FilterForCombat), so Feed and
      Not Yet could never appear on the Rare screen
  G5  the port populated, resolved and ADDED one screen at a time, where
      `RewardsSet.GenerateWithoutOffering` populates every reward before any is
      offered

Plus the Uniform branch itself: `CardFactory.CreateForReward` takes NO rarity
roll when `RarityOdds == Uniform` (CardFactory.cs:219-221) — the predicate
narrows the pool and `NextItem` picks out of it.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.cards import CardRarity
from sts2_rl.rewards import RarityOddsType, create_reward_cards
from sts2_rl.run import RunState

SEED = "89U21BV1TZ"


def _run(seed: str = SEED) -> RunState:
    run = RunState(rng=random.Random(0), string_seed=seed)
    run.start_run()
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]
    return run


# ── the Uniform branch (shared with Room Full of Cheese / Future of Potions) ──

def test_uniform_odds_take_no_rarity_roll():
    """CardFactory.cs:219-221. The sim ran RollWithBaseOdds even here, which
    burned one extra PlayerRng.Rewards draw per card: `count` NextItem +
    `count` NextFloat is the whole cost, not three draws each."""
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import reward_pool_card_ids

    run = _run()
    commons = [cid for cid in reward_pool_card_ids(run.card_pool)
               if _CARD_CLASSES[cid].rarity == CardRarity.COMMON]
    before = run.player_rng.rewards.counter
    cards = create_reward_cards(run, RarityOddsType.UNIFORM, count=4,
                                mutate_pity=False, pool=commons)
    assert len(cards) == 4
    assert run.player_rng.rewards.counter - before == 8   # 4 pick + 4 upgrade
    # ...and every card really came from the narrowed pool.
    assert all(c.rarity == CardRarity.COMMON for c in cards)


def test_uniform_odds_do_not_touch_the_pity_counters():
    """`RollForRarity` is the only thing that moves them and the Uniform branch
    never calls it."""
    run = _run()
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import reward_pool_card_ids

    commons = [cid for cid in reward_pool_card_ids(run.card_pool)
               if _CARD_CLASSES[cid].rarity == CardRarity.COMMON]
    before = dict(vars(run.card_rarity_odds))
    create_reward_cards(run, RarityOddsType.UNIFORM, count=3,
                        mutate_pity=False, pool=commons)
    after = {k: v for k, v in vars(run.card_rarity_odds).items()
             if k != "_rng"}
    assert {k: v for k, v in before.items() if k != "_rng"} == after


# ── the five screens ─────────────────────────────────────────────────────

def test_five_screens_in_the_declared_rarity_order():
    run = _run()
    before = len(run.deck)
    run.add_relic("glass_eye")
    added = run.deck[before:]
    assert [c.rarity for c in added] == [
        CardRarity.COMMON, CardRarity.COMMON,
        CardRarity.UNCOMMON, CardRarity.UNCOMMON,
        CardRarity.RARE,
    ]


def test_g5_every_screen_is_populated_before_any_is_offered():
    """RewardsSet.GenerateWithoutOffering (RewardsSet.cs:125-147). All fifteen
    draws land before the first decision, so a card taken from screen 1 cannot
    change what screens 2-5 drew — pinned by watching the Rewards counter from
    inside the selector."""
    run = _run()
    counters: list[int] = []

    def selector(purpose, cands, count):
        counters.append(run.player_rng.rewards.counter)
        return list(cands)[:count]

    run.card_selector = selector
    run.add_relic("glass_eye")
    assert len(counters) == 5
    # R14/R11: `ForNonCombatWithUniformOdds` itself ORs `NoUpgradeRoll`
    # (CardCreationOptions.cs:160-163) on top of the `NoRarityModification`
    # GlassEye.cs:29 adds explicitly — a fact this test previously missed,
    # asserting 30 (15 NextItem + 15 upgrade-roll NextFloat). Under
    # NoUpgradeRoll the upgrade-roll draw (and its NextFloat) never happens:
    # 15 NextItem picks only, all before the first ask, none after.
    assert counters == [15, 15, 15, 15, 15]


def test_g3_the_option_hooks_reach_every_screen():
    """CardFactory.cs:104-107 fires TryModifyCardRewardOptions (and its Late
    pass) at the end of EVERY CreateForReward. Glitter enchants every
    Glam-eligible offered card there; the port's hand-rolled loop never
    dispatched it."""
    run = _run()
    run.add_relic("glitter")
    before = len(run.deck)
    run.add_relic("glass_eye")
    added = run.deck[before:]
    assert len(added) == 5
    assert all(c.enchantment is not None for c in added), (
        [(c.id, c.enchantment) for c in added])


def test_g4_the_rare_screen_can_offer_feed_and_not_yet():
    """`options.GetPossibleCards(player)` is GetUnlockedCards; the port used
    FilterForCombat, which drops exactly the two Rares that cannot be generated
    in combat, so they could never be offered."""
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids, reward_pool_card_ids

    run = _run()
    combat_only = set(pool_card_ids(pool=run.card_pool))
    dropped = {cid for cid in reward_pool_card_ids(run.card_pool)
               if cid not in combat_only
               and _CARD_CLASSES[cid].rarity is CardRarity.RARE}
    assert dropped == {"feed", "not_yet"}, dropped

    seen: set[str] = set()

    def selector(purpose, cands, count):
        seen.update(c.id for c in cands)
        return list(cands)[:count]

    # The Rare screen is 3 of a small pool, so a handful of seeds covers it.
    # R14/R11: NoUpgradeRoll (see test_g5/test_g2 above) shifted the Rewards
    # stream this screen consumes, so the previous 4-seed list no longer
    # happens to land on Feed/Not Yet; widened rather than cherry-picked to
    # the new stream, so the property (reachable at all) stays honest.
    for seed in (
        "89U21BV1TZ", "933T39V18D", "DJDCQRWCL081", "TZEK1234567",
        *(f"SEED{i}" for i in range(30)),
    ):
        r = _run(seed)
        r.card_selector = selector
        r.add_relic("glass_eye")
    assert seen & dropped, (
        "no seed offered Feed or Not Yet; the reward pool is still filtered")


def test_g2_neither_path_ever_upgrades():
    """R14/R11 supersedes this test's old name and claim: the non-parity
    branch created cards with `rng.sample` and no roll at all, and the
    original G2 fix made both modes roll for upgrade. That fix was itself
    wrong — `ForNonCombatWithUniformOdds` ORs `NoUpgradeRoll`
    (CardCreationOptions.cs:160-163), so GlassEye's `CreateForReward` call
    NEVER rolls for upgrade in either mode (CardFactory.cs:98-102 skips
    `RollForUpgrade` wholesale under the flag). Act 3 would have made the old
    (wrong) 0.5 odds easy to observe; correctly, it observes nothing."""
    upgraded = 0
    for seed in range(40):
        run = RunState(rng=random.Random(seed))
        run.start_run()
        run.card_selector = lambda purpose, cands, count: list(cands)[:count]
        run.act_index = 2                     # act 3 -> 0.5 for non-Rares, if rolled
        before = len(run.deck)
        run.add_relic("glass_eye")
        upgraded += sum(1 for c in run.deck[before:] if c.upgrade_level > 0)
    assert upgraded == 0, "Glass Eye upgraded a card despite NoUpgradeRoll"


def test_the_set_carries_no_room_so_room_gated_relics_stay_off_it():
    """RewardsSet.WithCustomRewards leaves Room null (RewardsSet.cs:106-110),
    which is what every room-gated TryModifyRewards implementer short-circuits
    on — Prayer Wheel must not put a sixth screen on a Glass Eye pickup."""
    run = _run()
    run.add_relic("prayer_wheel")
    before = len(run.deck)
    run.add_relic("glass_eye")
    assert len(run.deck) - before == 5
