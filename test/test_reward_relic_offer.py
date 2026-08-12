"""`DecisionKind.REWARD_RELIC`'s `request.relic` is the sim's own grab-bag
pull (`RunState.pull_relic_from_front`), drawn off a stream that is not
draw-order-faithful yet — so during a conformance/dump replay it usually
names the wrong relic, even though the FINAL relic list is corrected
against the save afterward by `ReplayRunner._reconcile_node_relics`. Any obs
built from the request while it still carries the sim's raw pull (run_env.py's
`reward.relic.ids`/`reward.relic.f`, read straight off `request.relic` at
run_env.py ~1298-1304) inherits that wrong identity.

`_ForceWinDriver._relabel_relic_offer` fixes this at the source: given an
oracle attached (`ReplayRunner.run()` wires one), it relabels `request.relic`
to the save's Nth `relic_choices` entry (unfiltered — offered, not just
picked) for the current node BEFORE the take/skip decision, so any obs built
from the request afterward shows what the game actually offered.
"""
from __future__ import annotations

from sts2_rl.conformance.runner import (
    DecisionKind,
    DecisionRequest,
    _CommandCursor,
    _ForceWinDriver,
    _node_relic_choices,
)
from sts2_rl.relics import make_relic
from sts2_rl.run import RunState


class _FakeOracle:
    """A minimal stand-in for `SaveOracle` carrying only `map_history`, shaped
    exactly like the real parser's output for the bits `_node_relic_choices`
    reads: `map_history[act][room]["player_stats"][*]["relic_choices"]`."""

    def __init__(self, choices: dict[tuple[int, int], list[dict]]) -> None:
        max_act = max((a for a, _ in choices), default=-1)
        history: list[list[dict]] = []
        for act in range(max_act + 1):
            rooms_here = [r for a, r in choices if a == act]
            max_room = max(rooms_here, default=-1)
            rooms: list[dict] = [{} for _ in range(max_room + 1)]
            for (a, r), entries in choices.items():
                if a == act:
                    rooms[r] = {"player_stats": [{"relic_choices": entries}]}
            history.append(rooms)
        self.map_history = history


def _make_driver() -> _ForceWinDriver:
    run = RunState(string_seed="TEST")
    run.start_run(acts=["overgrowth"], ascension=0)
    cursor = _CommandCursor([])
    return _ForceWinDriver(run, cursor, acts=["overgrowth"], ascension=0)


def _ask(driver: _ForceWinDriver, relic_id: str) -> DecisionRequest:
    request = DecisionRequest(
        kind=DecisionKind.REWARD_RELIC, run=driver.run, relic=make_relic(relic_id),
    )
    driver._ask_decision(request)
    return request


def test_node_relic_choices_is_unfiltered_and_ordered() -> None:
    oracle = _FakeOracle({
        (1, 8): [
            {"choice": "RELIC.ASTROLABE", "was_picked": True},
            {"choice": "RELIC.STRIKE_DUMMY", "was_picked": False},
        ],
    })
    assert _node_relic_choices(oracle, 1, 8) == ["astrolabe", "strike_dummy"]


def test_relabels_offer_to_the_saves_ground_truth_taken() -> None:
    # The sim's own grab-bag pull names the wrong relic (`akabeko`); the save
    # says this node's one offer was actually Astrolabe, and it was taken.
    oracle = _FakeOracle({
        (1, 8): [{"choice": "RELIC.ASTROLABE", "was_picked": True}],
    })
    driver = _make_driver()
    driver._oracle = oracle
    driver._cur_act_index, driver._cur_room_index = 1, 8
    request = _ask(driver, "akabeko")
    assert request.relic.id == "astrolabe"


def test_relabels_offer_to_the_saves_ground_truth_even_when_declined() -> None:
    # Obs is built pre-decision, so a relic the player will SKIP still has to
    # show as the offer, not vanish or fall back to the sim's wrong pull.
    oracle = _FakeOracle({
        (1, 10): [{"choice": "RELIC.STRIKE_DUMMY", "was_picked": False}],
    })
    driver = _make_driver()
    driver._oracle = oracle
    driver._cur_act_index, driver._cur_room_index = 1, 10
    request = _ask(driver, "akabeko")
    assert request.relic.id == "strike_dummy"


def test_multiple_offers_at_one_node_are_served_in_order() -> None:
    # Calling Bell / Toy Box: several relics offered one at a time at the same
    # node — each ask must consume the next choice in the save's list, not
    # replay the first one repeatedly.
    oracle = _FakeOracle({
        (2, 7): [
            {"choice": "RELIC.CALLING_BELL", "was_picked": True},
            {"choice": "RELIC.PANDORAS_BOX", "was_picked": True},
        ],
    })
    driver = _make_driver()
    driver._oracle = oracle
    driver._cur_act_index, driver._cur_room_index = 2, 7
    first = _ask(driver, "akabeko")
    second = _ask(driver, "akabeko")
    assert (first.relic.id, second.relic.id) == ("calling_bell", "pandoras_box")


def test_no_oracle_leaves_the_sim_pull_untouched() -> None:
    # A bare unit-test driver (no `ReplayRunner` wiring `_oracle`) must not
    # crash and must behave exactly as before this fix.
    driver = _make_driver()
    request = _ask(driver, "akabeko")
    assert request.relic.id == "akabeko"


def test_ran_out_of_recorded_offers_leaves_the_sim_pull_untouched() -> None:
    oracle = _FakeOracle({(1, 8): [{"choice": "RELIC.ASTROLABE", "was_picked": True}]})
    driver = _make_driver()
    driver._oracle = oracle
    driver._cur_act_index, driver._cur_room_index = 1, 8
    _ask(driver, "akabeko")               # consumes the one recorded offer
    second = _ask(driver, "strike_dummy")  # nothing left to relabel from
    assert second.relic.id == "strike_dummy"
