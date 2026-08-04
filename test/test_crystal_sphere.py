"""Crystal Sphere — the shared event and its 11x11 reveal minigame.

Source: src/Core/Models/Events/CrystalSphere.cs (the event) and
src/Core/Events/Custom/CrystalSphereEvent/ (the minigame: CrystalSphereMinigame
.cs, CrystalSphereCell.cs, CrystalSphereItem.cs, CrystalSphereItems/*.cs).

The event was a deferred-port stub until this port; see the module docstring of
sts2_rl/events/crystal_sphere.py for what the sim models and what it does not.

Run with:  py -m pytest test/test_crystal_sphere.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.events import make_event
from sts2_rl.events._crystal_sphere import (
    TOOL_BIG,
    TOOL_SMALL,
    CrystalSphereMinigame,
    ItemKind,
)
from sts2_rl.events.crystal_sphere import CrystalSphere
from sts2_rl.run import RunState


def first_pick(seq):
    """A deterministic stand-in for `Rng.NextItem` — always the first legal
    candidate, so placement is exactly reproducible in tests."""
    return seq[0]


def game(pick=first_pick, divinations=3, on_reveal=None):
    return CrystalSphereMinigame(pick, divinations, on_reveal=on_reveal)


# ═════════════════════════════════════════════════════════════════════════
# Grid construction — CrystalSphereMinigame.cs:92-135
# ═════════════════════════════════════════════════════════════════════════

def test_grid_is_11x11():
    g = game()
    assert g.width == 11
    assert g.height == 11


def test_the_four_corners_start_pre_cleared_to_manhattan_radius_2():
    """The ctor seeds the four corners and expands the list TWICE by
    horizontal+vertical neighbours (CrystalSphereMinigame.cs:104-125), then
    clears every cell in it. Two orthogonal expansions from a corner reach
    exactly the cells within manhattan distance 2 of it — 6 per corner (the
    quarter-diamond that fits on the board), 24 in all."""
    g = game()
    corners = [(0, 0), (10, 0), (10, 10), (0, 10)]

    def near_a_corner(x, y):
        return any(abs(x - cx) + abs(y - cy) <= 2 for cx, cy in corners)

    for x in range(11):
        for y in range(11):
            assert g.is_hidden(x, y) is not near_a_corner(x, y), (x, y)

    assert sum(
        0 if g.is_hidden(x, y) else 1
        for x in range(11) for y in range(11)
    ) == 24


# ═════════════════════════════════════════════════════════════════════════
# Item placement — PopulateItems (:159-203) + CrystalSphereItem.PlaceItem
# (CrystalSphereItem.cs:37-65)
# ═════════════════════════════════════════════════════════════════════════

# PopulateItems' literal construction order. Order matters twice over: it is
# the order the 15 `Rng.NextItem` placement draws come off the event's stream,
# and earlier items shrink the legal-position list for later ones.
EXPECTED_ITEMS = [
    (ItemKind.RELIC, (4, 4), True, None),
    (ItemKind.POTION, (1, 3), True, "common"),
    (ItemKind.POTION, (1, 3), True, "common"),
    (ItemKind.POTION, (2, 2), True, "rare"),
    (ItemKind.CARD, (2, 2), True, "common"),
    (ItemKind.CARD, (2, 2), True, "uncommon"),
    (ItemKind.CARD, (2, 2), True, "rare"),
    (ItemKind.CURSE, (2, 2), False, None),
    (ItemKind.GOLD, (1, 1), True, None),
    (ItemKind.GOLD, (1, 1), True, None),
    (ItemKind.GOLD, (1, 1), True, None),
    (ItemKind.GOLD, (1, 1), True, None),
    (ItemKind.GOLD, (1, 1), True, None),
    (ItemKind.GOLD, (2, 1), True, None),
    (ItemKind.GOLD, (2, 1), True, None),
]


def test_populate_places_the_fifteen_items_in_source_order():
    g = game()
    assert [
        (i.kind, i.size, i.is_good, i.rarity) for i in g.items
    ] == EXPECTED_ITEMS


def test_each_item_costs_exactly_one_placement_draw():
    """PlaceItem enumerates every legal top-left and spends ONE
    `Rng.NextItem(list)` on it (CrystalSphereItem.cs:50-54) — so a full
    populate is exactly 15 draws, no more and no fewer."""
    draws = []

    def counting_pick(seq):
        draws.append(list(seq))
        return seq[0]

    game(pick=counting_pick)
    assert len(draws) == 15


def test_placement_candidates_are_enumerated_x_outer_y_inner():
    """PlaceItem's scan is `for (i = 0..GridSize.X) for (j = 0..GridSize.Y)`
    (CrystalSphereItem.cs:40-49) — x outer. The order fixes which candidate a
    given NextItem roll maps to, so it is load-bearing for parity, not just
    style."""
    seen = []

    def spy_pick(seq):
        seen.append(list(seq))
        return seq[0]

    game(pick=spy_pick)
    first = seen[0]
    assert first == sorted(first)  # (x, y) tuples ascending == x-outer scan


def test_the_relic_is_placed_first_at_the_first_legal_top_left():
    """Hand-derived from the source rather than snapshotted: the 4x4 relic is
    item #1, so it scans a board carrying only the 24 pre-cleared corner
    cells. Column x=0 is blocked at y=0,1,2 (the (0,0) corner diamond reaches
    (0,2)) and at y>=7 (the (0,10) diamond reaches (0,8)); y=3 is the first
    top-left whose 4x4 footprint x0..3 / y3..6 misses every pre-cleared
    cell."""
    g = game()
    assert g.items[0].pos == (0, 3)


def test_placed_items_never_overlap_and_never_sit_on_a_pre_cleared_cell():
    for seed in range(20):
        rng = random.Random(seed)
        g = game(pick=rng.choice)
        occupied = set()
        for item in g.items:
            for cx, cy in item.cells():
                assert 0 <= cx < 11 and 0 <= cy < 11
                assert (cx, cy) not in occupied, "items overlap"
                occupied.add((cx, cy))
                # A pre-cleared cell is not hidden, and CanPlaceHere rejects
                # any footprint touching one (CrystalSphereItem.cs:90-93).
                assert g.is_hidden(cx, cy)


def test_every_occupied_cell_maps_back_to_its_item():
    g = game()
    for item in g.items:
        for cx, cy in item.cells():
            assert g.item_at(cx, cy) is item


# ═════════════════════════════════════════════════════════════════════════
# Clicking — CellClicked (:259-278) and ClearCell (:285-308)
# ═════════════════════════════════════════════════════════════════════════

def cleared(g):
    return {(x, y) for x in range(11) for y in range(11) if not g.is_hidden(x, y)}


def test_big_tool_clears_the_clicked_cell_and_its_eight_neighbours():
    g = game(divinations=3)
    before = cleared(g)
    g.click(5, 5, TOOL_BIG)
    assert cleared(g) - before == {
        (x, y) for x in range(4, 7) for y in range(4, 7)
    }


def test_big_tool_clips_at_the_board_edge():
    """GetHorizontal/Vertical/DiagonalCells all bounds-check before adding
    (:345-389), so a Big click in a corner clears only what exists."""
    g = game(divinations=3)
    before = cleared(g)
    g.click(0, 0, TOOL_BIG)
    assert cleared(g) - before <= {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_small_tool_clears_exactly_one_cell():
    g = game(divinations=3)
    before = cleared(g)
    g.click(5, 5, TOOL_SMALL)
    assert cleared(g) - before == {(5, 5)}


def test_each_click_spends_one_divination_whatever_the_tool():
    g = game(divinations=3)
    g.click(5, 5, TOOL_BIG)
    assert g.divinations == 2
    g.click(5, 5, TOOL_SMALL)
    assert g.divinations == 1


def test_a_click_on_already_cleared_ground_still_costs_a_divination():
    """`DivinationCount--` is the first statement of CellClicked (:261),
    before any ClearCell — a wasted click is still a spent divination."""
    g = game(divinations=3)
    g.click(0, 0, TOOL_SMALL)  # (0,0) is pre-cleared
    assert g.divinations == 2


def test_the_game_is_finished_when_the_divinations_run_out():
    g = game(divinations=2)
    assert g.is_finished is False
    g.click(5, 5, TOOL_SMALL)
    assert g.is_finished is False
    g.click(6, 6, TOOL_SMALL)
    assert g.is_finished is True


def test_an_item_reveals_only_once_every_cell_it_occupies_is_clear():
    """AreAllOccupiedCellsClear (:315-330) — a partially uncovered item is
    visible on the board but has NOT fired, which is the whole reason the
    Small tool exists (it lets a player stop short of completing the curse)."""
    g = game(divinations=99)
    item = next(i for i in g.items if i.size == (2, 2))
    (px, py) = item.pos

    for cx, cy in [(px, py), (px + 1, py), (px, py + 1)]:
        g.click(cx, cy, TOOL_SMALL)
    assert g.revealed == []

    g.click(px + 1, py + 1, TOOL_SMALL)
    assert g.revealed == [item]


def test_on_reveal_fires_once_per_item_as_its_last_cell_clears():
    seen = []
    g = game(divinations=99, on_reveal=seen.append)
    item = next(i for i in g.items if i.size == (1, 1))
    g.click(*item.pos, TOOL_SMALL)
    assert seen == [item]

    # Re-clearing ground it already owns must not fire it a second time
    # (ClearCell early-returns on a visible cell, :295-298).
    g.click(*item.pos, TOOL_SMALL)
    assert seen == [item]


def test_a_click_off_the_board_is_rejected():
    g = game(divinations=3)
    with pytest.raises(ValueError):
        g.click(11, 0, TOOL_SMALL)


# ═════════════════════════════════════════════════════════════════════════
# The event — CrystalSphere.cs
# ═════════════════════════════════════════════════════════════════════════

def sphere_run(gold=250, act_index=1, seed=0, **kwargs):
    """A run standing where the event's own gate opens: act 2+ with the gold
    to pay for it."""
    run = RunState(rng=random.Random(seed), gold=gold, **kwargs)
    run.act_index = act_index
    return run


def reveal_only(*kinds):
    """A click policy that digs out the items of the given kinds, then burns
    any leftover divinations on a pre-cleared corner. Lets a test name the
    payout it is after.

    Big tool, aimed at the target's first still-hidden cell: the 3x3 always
    contains the cell it is aimed at, so every click makes progress. Note the
    splash — a Big click can finish a neighbouring item too, which is why the
    assertions below count rows against `minigame.revealed` rather than
    against `kinds`."""
    def policy(g):
        for kind in kinds:                      # priority = argument order
            for item in g.items:
                if item.kind is kind:
                    for cx, cy in item.cells():
                        if g.is_hidden(cx, cy):
                            return (cx, cy, TOOL_BIG)
        return (0, 0, TOOL_BIG)
    return policy


def play(run, option, policy):
    run.crystal_sphere_clicks = policy
    event = make_event("crystal_sphere", run).begin()
    event.choose(option)
    return event


# ── The gate (IsAllowed, CrystalSphere.cs:49-56) ─────────────────────────

def test_the_event_is_offered_with_100_gold_past_act_one():
    assert CrystalSphere.is_allowed(sphere_run(gold=100, act_index=1)) is True


def test_the_event_is_refused_below_100_gold():
    assert CrystalSphere.is_allowed(sphere_run(gold=99, act_index=1)) is False


def test_the_event_is_refused_in_act_one():
    """`runState.CurrentActIndex > 0` — the first act never offers it however
    rich the player is."""
    assert CrystalSphere.is_allowed(sphere_run(gold=999, act_index=0)) is False


# ── CalculateVars (:44-47) ───────────────────────────────────────────────

def test_uncover_future_costs_50_plus_a_1_to_49_roll():
    """`DynamicVars["UncoverFutureCost"].BaseValue += Rng.NextInt(1, 50)` on a
    base of 50. NextInt's upper bound is exclusive, so the cost lands in
    51..99."""
    seen = set()
    for seed in range(60):
        run = sphere_run(seed=seed)
        event = make_event("crystal_sphere", run).begin()
        assert 51 <= event.cost <= 99
        seen.add(event.cost)
    assert len(seen) > 1, "the cost must actually vary with the roll"


# ── The two options (:58-81) ─────────────────────────────────────────────

def test_the_event_offers_uncover_future_and_payment_plan():
    run = sphere_run()
    event = make_event("crystal_sphere", run).begin()
    assert event.option_keys() == ["UNCOVER_FUTURE", "PAYMENT_PLAN"]


def test_uncover_future_charges_its_gold_and_grants_three_divinations():
    run = sphere_run(gold=250)
    event = play(run, "UNCOVER_FUTURE", reveal_only())
    assert run.gold == 250 - event.cost
    assert event.minigame.divinations == 0
    assert event.divinations_spent == 3


def test_payment_plan_adds_a_debt_curse_and_grants_six_divinations():
    run = sphere_run(gold=250)
    before = len(run.deck)
    event = play(run, "PAYMENT_PLAN", reveal_only())
    assert run.gold == 250, "PaymentPlan is paid in curses, not gold"
    assert [c.id for c in run.deck[before:]] == ["debt"]
    assert event.divinations_spent == 6


def test_the_event_finishes_after_the_minigame():
    run = sphere_run()
    event = play(run, "UNCOVER_FUTURE", reveal_only())
    assert event.finished is True
    assert event.options == []


# ── Payouts (CrystalSphereItems/*.cs -> OfferCrystalSphereRewards) ───────

def test_revealing_the_curse_adds_doubt_to_the_deck_immediately():
    """CrystalSphereCurse.RevealItem (CrystalSphereCurse.cs:18-26) adds the
    card at REVEAL time — not with the rest of the payout at the end — so a
    player who uncovers it cannot decline it."""
    run = sphere_run()
    before = len(run.deck)
    play(run, "UNCOVER_FUTURE", reveal_only(ItemKind.CURSE))
    assert "doubt" in [c.id for c in run.deck[before:]]


def test_every_revealed_item_gets_one_reward_row_except_the_curse():
    """`revealed.Select(r => r.ToReward(owner, rng)).OfType<Reward>()`
    (OneOffSynchronizer.cs:205-209) drops nulls, and CrystalSphereCurse never
    overrides the base `ToReward` — its damage is already done, so it is the
    one revealed item that contributes no row."""
    run = sphere_run()
    event = play(run, "PAYMENT_PLAN", reveal_only(
        ItemKind.CURSE, ItemKind.CARD, ItemKind.POTION))
    revealed = event.minigame.revealed
    assert any(i.kind is ItemKind.CURSE for i in revealed)

    def revealed_count(kind):
        return len([i for i in revealed if i.kind is kind])

    rewards = event.pending_rewards
    assert len(rewards.card_rewards) == revealed_count(ItemKind.CARD)
    assert len(rewards.potions) == revealed_count(ItemKind.POTION)
    assert len(rewards.relics) == revealed_count(ItemKind.RELIC)


def test_revealing_gold_pays_out_10_or_30():
    run = sphere_run(gold=250)
    event = play(run, "UNCOVER_FUTURE", reveal_only(ItemKind.GOLD))
    paid = run.gold - (250 - event.cost)
    revealed_gold = [i for i in event.minigame.revealed if i.kind is ItemKind.GOLD]
    assert paid == sum(30 if i.is_big else 10 for i in revealed_gold)
    assert revealed_gold, "the policy should have uncovered at least one pile"


def test_revealing_a_card_item_opens_a_three_card_screen_of_that_rarity():
    run = sphere_run()
    event = play(run, "UNCOVER_FUTURE", reveal_only(ItemKind.CARD))
    groups = event.pending_rewards.card_rewards
    revealed_cards = [i for i in event.minigame.revealed if i.kind is ItemKind.CARD]
    assert len(groups) == len(revealed_cards) >= 1
    for group in groups:
        assert len(group.cards) == 3


def test_revealing_the_relic_offers_one():
    """PAYMENT_PLAN, not UNCOVER_FUTURE: the relic is 4x4 (CrystalSphereRelic
    .cs:8), which takes four Big clicks to clear — more than UNCOVER_FUTURE's
    three divinations can buy. The 6-divination option is the only one that
    can reach it, which is the source's own difficulty curve, not a sim
    limitation."""
    run = sphere_run()
    before = len(run.relics)
    event = play(run, "PAYMENT_PLAN", reveal_only(ItemKind.RELIC))
    assert any(i.kind is ItemKind.RELIC for i in event.minigame.revealed)
    assert len(run.relics) == before + 1


def test_revealing_potions_offers_each_one():
    run = sphere_run()
    event = play(run, "UNCOVER_FUTURE", reveal_only(ItemKind.POTION))
    revealed = [i for i in event.minigame.revealed if i.kind is ItemKind.POTION]
    assert revealed
    assert len(event.pending_rewards.potions) == len(revealed)


# ── RNG discipline ───────────────────────────────────────────────────────

def parity_run(gold=250, act_index=1):
    run = RunState(string_seed="933T39V18D", gold=gold)
    run.act_index = act_index
    return run


def test_clicking_never_touches_a_parity_rng_stream():
    """In the game a click is human input: it consumes no run RNG at all. The
    sim has to invent a click from somewhere, so it draws on a dedicated
    sim-only stream — if that draw ever landed on a parity stream instead,
    every later placement and reward draw in the run would shift and this port
    would be worse than the stub it replaced."""
    run = parity_run()
    before = (dict(run.rng_set.counters()), dict(run.player_rng.counters()))
    play(run, "UNCOVER_FUTURE", reveal_only(ItemKind.GOLD))
    assert (dict(run.rng_set.counters()), dict(run.player_rng.counters())) == before


def test_the_payout_draws_on_the_events_own_rng_not_the_rewards_stream():
    """Every ToReward in the source is handed the event's Rng
    (`WithRngOverride(rng)` / `SetRng(rng)` / `rng.NextItem(...)`,
    CrystalSphereItems/*.cs), so a relic, potion or card revealed here must
    not advance the per-player Rewards stream the way an ordinary reward
    screen does."""
    run = parity_run()
    before = dict(run.player_rng.counters())
    play(run, "UNCOVER_FUTURE", reveal_only(
        ItemKind.RELIC, ItemKind.POTION, ItemKind.CARD))
    assert dict(run.player_rng.counters()) == before


def test_the_relic_pulls_at_its_reveal_position_not_after_the_card_sweep():
    """`GenerateWithoutOffering`'s FIRST loop is
    `foreach (Reward reward in Rewards) reward.Populate()` (RewardsSet.cs:
    130-134) — list order, i.e. reveal order, and before Hook.ModifyRewards.
    `RelicReward.Populate` is the grab-bag pull and `CardReward.Populate` draws
    the three options, both on the event's own Rng, so a relic revealed before
    a card item pulls FIRST. Hoisting the pull behind every card group's
    populate reorders the event stream and changes both the relic and the
    cards."""
    from sts2_rl.rewards import CardRewardGroup

    order = []
    real_pull = RunState.pull_relic_from_front
    real_populate = CardRewardGroup.populate

    def spy_pull(self, *a, **kw):
        order.append("relic")
        return real_pull(self, *a, **kw)

    def spy_populate(self, *a, **kw):
        order.append("card")
        return real_populate(self, *a, **kw)

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(RunState, "pull_relic_from_front", spy_pull)
        monkey.setattr(CardRewardGroup, "populate", spy_populate)
        run = sphere_run(seed=6)
        event = play(run, "PAYMENT_PLAN", reveal_only(ItemKind.RELIC, ItemKind.CARD))
    finally:
        monkey.undo()

    revealed = [
        i.kind for i in event.minigame.revealed
        if i.kind in (ItemKind.RELIC, ItemKind.CARD)
    ]
    assert revealed[:2] == [ItemKind.RELIC, ItemKind.CARD], (
        "the fixture must reveal the relic before a card item")
    assert order == [k.value for k in revealed]


def test_the_same_seed_replays_the_same_board():
    """The click stream is sim-only but must still be deterministic, or a
    seeded RL run stops being reproducible."""
    boards = []
    for _ in range(2):
        run = parity_run()
        event = play(run, "UNCOVER_FUTURE", reveal_only(ItemKind.GOLD))
        boards.append([i.pos for i in event.minigame.items])
    assert boards[0] == boards[1]


# ── Conformance replay ───────────────────────────────────────────────────

def click_cmds(*triples):
    from sts2_rl.conformance.recording import Command
    return [
        Command("CrystalSphereClick", [str(x), str(y), str(t)], "", None, i)
        for i, (x, y, t) in enumerate(triples, 1)
    ]


def test_a_recorded_click_list_drives_the_minigame_exactly():
    """RunReplays already records the spatial decision as
    `CrystalSphereClick {x} {y} {tool}` (RunReplays/Commands/
    CrystalSphereClickCommand.cs), so a replay needs no policy at all — the
    clicks are data."""
    from sts2_rl.conformance.runner import _CommandCursor, crystal_sphere_click_policy

    cursor = _CommandCursor(click_cmds((3, 4, TOOL_SMALL), (7, 2, TOOL_BIG),
                                       (9, 5, TOOL_SMALL)))
    run = sphere_run()
    run.crystal_sphere_clicks = crystal_sphere_click_policy(cursor)
    event = make_event("crystal_sphere", run).begin()
    event.choose("UNCOVER_FUTURE")

    g = event.minigame
    assert not g.is_hidden(3, 4)
    assert not g.is_hidden(9, 5)
    for x in range(6, 9):
        for y in range(1, 4):
            assert not g.is_hidden(x, y)
    assert cursor.pos == 3, "all three recorded clicks consumed, in order"


def test_the_click_lookahead_stops_at_the_next_room_boundary():
    """`take_before`-style bounding: a crystal sphere later in the recording
    must not be raided for clicks by an earlier one. With nothing recorded for
    THIS minigame the policy falls back to the automated rule and leaves the
    cursor where it was."""
    from sts2_rl.conformance.recording import Command
    from sts2_rl.conformance.runner import _CommandCursor, crystal_sphere_click_policy

    later = click_cmds((3, 4, TOOL_SMALL))
    cursor = _CommandCursor(
        [Command("MoveToMapCoord", ["1", "2"], "", None, 1)] + later)
    run = sphere_run()
    run.crystal_sphere_clicks = crystal_sphere_click_policy(cursor)
    event = make_event("crystal_sphere", run).begin()
    event.choose("UNCOVER_FUTURE")

    assert event.divinations_spent == 3
    assert cursor.pos == 0, "the boundary was never crossed"


def test_nothing_revealed_pays_nothing():
    """A player who spends every divination on the pre-cleared corner gets the
    cost and no payout — the source has no consolation prize."""
    run = sphere_run(gold=250)
    event = play(run, "UNCOVER_FUTURE", lambda g: (0, 0, TOOL_SMALL))
    assert event.minigame.revealed == []
    assert run.gold == 250 - event.cost
    assert event.pending_rewards is None
