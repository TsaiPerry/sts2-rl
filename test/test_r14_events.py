"""Round 14, lane R3 — the LIVE reroll family: `event/brain_leech/g6`,
`event/brain_leech/g7`, `event/trial/g17`.

g6 / g17 (F-R13a, filed identically on both events): a Driftwood reroll fell
back to `CardRewardGroup.populate`'s `pool is None` default instead of the
screen's own creation options, because the bare `CardRewardGroup(cards=...,
populated=True)` constructor both events used never carried `pool` /
`odds_type` / `flags` onto the group for `reroll()` to reuse. Fixed by
building the group the way `_PotionCardRewardGroup` (events/
the_future_of_potions.py) already does: construct with the real options,
then call `group.populate(run)`.

For Brain Leech's Rip this really was "wrong pool" (Colorless -> character
pool) exactly as filed. For Trial's Nondescript Guilty it was NOT -- that
screen's pool was already the (un-overridden) character pool before any
reroll, so the record's "redraws from the CHARACTER pool" wording (copied
verbatim from g6) does not apply. Re-deriving both draws against Trial.cs:183
found the real live defect instead: `mutate_pity` defaulted True (mutating)
on the FIRST draw already, not just on reroll, because Trial.cs uses
`CardCreationOptions.ForNonCombatWithDefaultOdds` (Source=Other,
CardCreationOptions.cs:150-153), which `CardFactory.RollForRarity`
(CardFactory.cs:244-260) only mutates for `Source == Encounter`.

g7: `modify_hooks=False` in brain_leech.py's Rip stood in for a DIFFERENT C#
flag pair (BrainLeech.cs:56 is `NoRarityModification | NoCardPoolModifications`,
never `NoModifyHooks`), so it wrongly suppressed the whole
`Hook.TryModifyCardRewardOptions[Late]` dispatch (CardFactory.cs:104) that
Silken Tress / Silver Crucible / the eggs / Glitter read. Both relics ALSO
gate on `IsCardReward` (SilkenTress.cs:53-56 / SilverCrucible.cs:104-107),
which neither event's hand-rolled `create_reward_cards` call ever set on the
first draw either -- fixed for both events by routing through
`CardRewardGroup.populate`, which sets `is_card_reward=True`
unconditionally, mirroring `CardReward.cs:114-115`'s
`Options = options.WithFlags(CardCreationFlags.IsCardReward)`.

Also pins two `NoUpgradeRoll` sites (CardCreationOptions.cs:139: every
`ForNonCombatWithDefaultOdds` call sets it) that neither event modelled --
narrowing `creature_card_cmds/guard26` ("NoUpgradeRoll is unmodelled at
roughly eleven non-combat creation sites") by exactly these two, each
verified individually against the C# rather than swept.

Run with:  py -m pytest test/test_r14_events.py -v
"""
from __future__ import annotations

import random

from sts2_rl import make_event
from sts2_rl.cards.pool import COLORLESS_POOL
from sts2_rl.rewards import CardCreationFlags
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


def _trial_forced(run: RunState, roll: int):
    """Begin Trial and force the sub-trial roll to `roll` (0/1/2) — mirrors
    test_event_reward_modifiers.py's `_trial_forced` helper."""
    ev = make_event("trial", run).begin()

    class _Fixed:
        def randrange(self, _n):
            return roll

    ev.rng = _Fixed()
    ev.choose("ACCEPT")
    return ev


# ── g6: Brain Leech's Rip reroll ─────────────────────────────────────────


def test_brain_leech_rip_reroll_stays_on_the_colorless_pool():
    """`CardReward.Reroll` regenerates against the SAME options as the first
    draw (CardReward.cs:114-115 / :322-332: `RerollOptions = options.
    WithFlags(...)` is the identical `options` object). Before the fix, the
    group never carried `pool=COLORLESS_POOL` onto itself, so `reroll()`
    fell back to `populate`'s `pool is None` default: the full CHARACTER
    pool at MONSTER odds."""
    run = fresh_run(3)
    run.add_relic("driftwood")

    ev = make_event("brain_leech", run).begin()
    ev.choose("RIP")
    group = ev.pending_rewards.card_rewards[0]
    assert group.cards
    assert all(c.id in COLORLESS_POOL for c in group.cards)

    group.reroll(run)
    assert group.cards
    assert all(c.id in COLORLESS_POOL for c in group.cards), (
        "reroll must stay on the Colorless pool, not fall back to the "
        "character pool"
    )


def test_brain_leech_rip_reroll_does_not_mutate_the_rarity_pity_counter():
    """BrainLeech.cs:56's `ForNonCombatWithDefaultOdds` sets Source=Other
    (CardCreationOptions.cs:150-153), so `CardFactory.RollForRarity` takes
    the non-mutating `RollWithBaseOdds` path (CardFactory.cs:244-260) on
    every draw — first AND every reroll. Before the fix, `reroll()`'s `pool
    is None` fallback also flipped `mutate_pity` to True."""
    run = fresh_run(4)
    run.add_relic("driftwood")

    ev = make_event("brain_leech", run).begin()
    before = run.card_rarity_odds.current_value
    ev.choose("RIP")
    after_first = run.card_rarity_odds.current_value
    assert after_first == before, "the first draw must not mutate the pity"

    group = ev.pending_rewards.card_rewards[0]
    for _ in range(4):
        group.reroll(run)
    after_rerolls = run.card_rarity_odds.current_value
    assert after_rerolls == before, "rerolls must not mutate the pity either"


# ── g7: Brain Leech's Rip reward-modifier hooks ──────────────────────────


def test_brain_leech_rip_silken_tress_and_silver_crucible_fire_on_first_draw():
    """`modify_hooks=False` (NoModifyHooks) suppressed the WHOLE
    `Hook.TryModifyCardRewardOptions[Late]` dispatch (CardFactory.cs:104)
    these relics gate their one-shot on — BrainLeech.cs:56 never sets that
    flag. Both relics ALSO gate on `IsCardReward` (SilkenTress.cs:53-56 /
    SilverCrucible.cs:104-107), missing before on the hand-rolled
    `create_reward_cards` call regardless of `modify_hooks`."""
    run = fresh_run(5)
    silken_tress = run.add_relic("silken_tress")
    silver_crucible = run.add_relic("silver_crucible")

    ev = make_event("brain_leech", run).begin()
    ev.choose("RIP")

    assert silken_tress.is_used is True, "Silken Tress should have fired"
    assert silver_crucible.times_used == 1, "Silver Crucible should have fired"


def test_brain_leech_rip_reward_flags_match_the_source():
    """BrainLeech.cs:56 — `NoUpgradeRoll` (every `ForNonCombatWithDefaultOdds`
    call, CardCreationOptions.cs:139) | `NoRarityModification` |
    `NoCardPoolModifications`. NOT `NoModifyHooks` (g7's original bug)."""
    run = fresh_run(6)
    ev = make_event("brain_leech", run).begin()
    ev.choose("RIP")
    group = ev.pending_rewards.card_rewards[0]

    assert group.flags == (CardCreationFlags.NO_UPGRADE_ROLL
                            | CardCreationFlags.NO_RARITY_MODIFICATION
                            | CardCreationFlags.NO_CARD_POOL_MODIFICATIONS)


def test_brain_leech_rip_takes_no_upgrade_roll():
    """`ForNonCombatWithDefaultOdds` always sets `NoUpgradeRoll`
    (CardCreationOptions.cs:139), so Rip's cards are never auto-upgraded and
    take no `RollForUpgrade` draw (CardFactory.cs:98-102), regardless of act
    index. Narrows `creature_card_cmds/guard26` ("NoUpgradeRoll is
    unmodelled at roughly eleven non-combat creation sites") by this one
    site — verified against BrainLeech.cs:56 individually, not swept."""
    for seed in range(10):
        run = fresh_run(100 + seed)
        run.act_index = 3   # UPGRADED_CARD_ODD_SCALING * 3 == 0.75 if unfixed
        ev = make_event("brain_leech", run).begin()
        ev.choose("RIP")
        cards = ev.pending_rewards.card_rewards[0].cards
        assert cards
        assert all(c.upgrade_level == 0 for c in cards), (
            "Rip's cards must never come back pre-upgraded"
        )


# ── g17: Trial's Nondescript Guilty reroll ───────────────────────────────


def test_trial_nondescript_guilty_does_not_mutate_pity_on_first_draw_or_reroll():
    """g17 (F-R13a) was filed with brain_leech's wording verbatim: "the
    reroll redraws from the CHARACTER pool". That framing does not apply to
    Trial — Nondescript Guilty's pool was ALREADY the character pool
    (Trial.cs:183's `ForNonCombatWithDefaultOdds` never narrows it), so a
    reroll draws from the same pool either way; see
    test_trial_nondescript_guilty_reroll_pool_stays_the_character_pool
    below. The record's VERDICT (live gap) still holds — for a different
    reason: Source=Other (CardCreationOptions.cs:150-153) means
    `CardFactory.RollForRarity` must stay on the non-mutating
    `RollWithBaseOdds` path (CardFactory.cs:244-260), and the unfixed
    `create_reward_cards(..., count=3)` call defaulted `mutate_pity=True` on
    the FIRST draw already, not just on reroll."""
    run = fresh_run(7)
    run.add_relic("driftwood")

    ev = _trial_forced(run, 2)
    before = run.card_rarity_odds.current_value
    ev.choose("GUILTY")
    after_first = run.card_rarity_odds.current_value
    assert after_first == before, (
        "Nondescript Guilty's FIRST draw must not mutate the rarity pity "
        "counter (Source=Other)"
    )

    for group in ev.pending_rewards.card_rewards:
        group.reroll(run)
    after_rerolls = run.card_rarity_odds.current_value
    assert after_rerolls == before, "rerolls must not mutate the pity either"


def test_trial_nondescript_guilty_reroll_pool_stays_the_character_pool():
    """Sanity check for the corrected g17 framing above: the pool is the
    (un-overridden) character pool both before AND after a reroll — there is
    no Colorless narrowing here for a reroll to lose."""
    run = fresh_run(8)
    run.add_relic("driftwood")
    ev = _trial_forced(run, 2)
    ev.choose("GUILTY")

    ids = set(run.card_pool)
    for group in ev.pending_rewards.card_rewards:
        assert group.cards
        assert all(c.id in ids for c in group.cards)
        group.reroll(run)
        assert group.cards
        assert all(c.id in ids for c in group.cards)


def test_trial_nondescript_guilty_silken_tress_fires_on_first_draw():
    """Same shape of defect as g7 on Brain Leech's Rip, never separately
    filed for Trial: the un-fixed hand-rolled `create_reward_cards` call
    never set `IsCardReward` (CardReward.cs:114-115) on the first draw, so
    Silken Tress could never fire here either."""
    run = fresh_run(9)
    silken_tress = run.add_relic("silken_tress")

    ev = _trial_forced(run, 2)
    ev.choose("GUILTY")

    assert silken_tress.is_used is True


def test_trial_nondescript_guilty_reward_flags_match_the_source():
    """Trial.cs:183 — `ForNonCombatWithDefaultOdds` sets ONLY
    `NoUpgradeRoll` (CardCreationOptions.cs:139); no extra `.WithFlags(...)`
    call on top (unlike Brain Leech's Rip), so `NoCardPoolModifications`
    must NOT be set here — Dingy Rug / Prismatic Gem stay free to widen this
    screen's pool."""
    run = fresh_run(10)
    ev = _trial_forced(run, 2)
    ev.choose("GUILTY")

    for group in ev.pending_rewards.card_rewards:
        assert group.flags == CardCreationFlags.NO_UPGRADE_ROLL


def test_trial_nondescript_guilty_takes_no_upgrade_roll():
    """Second `NoUpgradeRoll` site narrowing `creature_card_cmds/guard26` —
    see test_brain_leech_rip_takes_no_upgrade_roll's docstring."""
    for seed in range(10):
        run = fresh_run(200 + seed)
        run.act_index = 3
        ev = _trial_forced(run, 2)
        ev.choose("GUILTY")
        for group in ev.pending_rewards.card_rewards:
            assert group.cards
            assert all(c.upgrade_level == 0 for c in group.cards)
