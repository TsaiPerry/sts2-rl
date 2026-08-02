"""R14 R10 — relic/hefty_tablet/AfterObtained.

HeftyTablet.cs:29 builds `CardCreationOptions(character pool,
CardCreationSource.Other, CardRarityOddsType.Uniform, c => c.Rarity == Rare)
.WithFlags(CardCreationFlags.NoUpgradeRoll)` and calls
`CardFactory.CreateForReward(owner, 3, options)` directly. That still runs
BOTH `Hook.TryModifyCardRewardOptions[Late]` passes (CardFactory.cs:104/106) —
only the standalone upgrade ROLL is suppressed, not the reward-options hooks —
so a co-held Toxic/Frozen/Molten Egg (or Silver Crucible / Silken Tress /
Glitter / Lasting Candy) still gets a chance to modify the three offered
cards.

The prior port hand-rolled its own `PlayerRng.Rewards.NextItem` pick loop and
never dispatched those hooks at all, which is invisible on a run with no
relics (the old test's "dormant" verdict) — the base `Relic` class declares
both hook methods so `hasattr` is trivially true for anything, and a relic
that never gets ADDED never gets a chance to run one. The bug only shows once
something is CO-HELD when Hefty Tablet's own `AfterObtained` fires — exactly
what `RunState.add_relic` produces (append, then `after_obtained`), and
exactly the Neow's-Bones-drew-two-relics-then-Hefty-Tablet's-own-screen-opens
shape the queue entry traces.
"""
from __future__ import annotations

from sts2_rl.cards import CardRarity, CardType
from sts2_rl.cards.base import _CARD_CLASSES
from sts2_rl.run import RunState

# A seed whose Hefty Tablet Uniform-Rare draw (character pool, Ironclad)
# includes at least one Skill: `cascade`, un-upgraded before the fix.
_SEED = "R14HEFTY"


def _offer_hefty_tablet(co_held=(), run_kwargs=None):
    """Adds every relic id in `co_held` (in order — mirrors Neow's Bones
    obtaining two relics before Hefty Tablet's own screen opens), then Hefty
    Tablet, and captures the 3-card offer by installing a card_selector that
    records the candidates and takes the first (mirroring `canSkip: true` —
    a real pick is fine, the test only inspects what was OFFERED)."""
    captured: dict = {}

    def selector(purpose, candidates, count):
        captured["candidates"] = list(candidates)
        return candidates[:count]

    run = RunState(string_seed=_SEED, card_selector=selector,
                    **(run_kwargs or {}))
    for relic_id in co_held:
        run.add_relic(relic_id)
    run.add_relic("hefty_tablet")
    return run, captured["candidates"]


def test_hefty_tablet_offer_is_all_rare():
    """HeftyTablet.cs:29's predicate (`c.Rarity == Rare`) is the whole
    candidate pool — the Uniform arm takes no rarity roll at all
    (CardFactory.cs:219-221)."""
    run, offered = _offer_hefty_tablet()
    assert len(offered) == 3
    assert all(_CARD_CLASSES[c.id].rarity == CardRarity.RARE for c in offered)
    # No duplicates: each draw excludes the prior picks (the reward
    # blacklist, CardFactory.cs's `chosen_ids`).
    assert len({c.id for c in offered}) == 3


def test_hefty_tablet_offer_is_upgraded_by_a_co_held_toxic_egg():
    """THE LIVE BUG: a co-held Toxic Egg upgrades any Skill in the offer via
    `Hook.TryModifyCardRewardOptionsLate` (EggRelicHelper.UpgradeValidCards,
    ToxicEgg.cs -> _eggs.py's `modify_card_reward_options_late`). The old
    hand-rolled pick loop skipped both hook passes entirely, so `cascade`
    (a Rare Skill) came back at upgrade_level 0 where the game hands it over
    already Upgraded."""
    run, offered = _offer_hefty_tablet(co_held=["toxic_egg"])
    skills = [c for c in offered if c.card_type == CardType.SKILL]
    assert skills, "seed must offer at least one Skill to be a real pin"
    assert all(c.upgrade_level >= 1 for c in skills)
    # Non-Skill offers are untouched by Toxic Egg.
    non_skills = [c for c in offered if c.card_type != CardType.SKILL]
    assert all(c.upgrade_level == 0 for c in non_skills)


def test_hefty_tablet_does_not_roll_its_own_upgrade():
    """`WithFlags(CardCreationFlags.NoUpgradeRoll)` (HeftyTablet.cs:29)
    suppresses `RollForUpgrade` and its `Rewards.NextFloat` draw wholesale
    (CardFactory.cs:98-102) — the ONLY reason any offered card is upgraded is
    a hook (egg/Silver Crucible/etc.), never the reward-card upgrade roll
    every other Uniform-odds reward would take. With no egg relic held, every
    offered card must come back un-upgraded regardless of rarity/act."""
    run, offered = _offer_hefty_tablet()
    assert all(c.upgrade_level == 0 for c in offered)


def test_hefty_tablet_still_adds_the_chosen_card_and_an_injury():
    """The take/injury tail (HeftyTablet.cs:32-38) is unchanged by routing
    the draw through `create_reward_cards`: the picked card (here, whatever
    `select_cards` — the first candidate, per the test's selector — returns)
    plus one Injury land in the deck."""
    run, offered = _offer_hefty_tablet()
    deck_ids = [c.id for c in run.deck]
    assert offered[0].id in deck_ids
    assert deck_ids.count("injury") == 1
