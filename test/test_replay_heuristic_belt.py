"""The replay runner's positional answer fallbacks must never leave the
own-action namespace (v22 regression).

`_answer_event` ("no guidance: proceed/leave") and `_answer_select_grid`
(the skippable stop action) picked `legal[-1]`. Belt actions are appended
AFTER own actions (`legal_actions = own + potion + discard`), and belt
drinks/discards replay only through recorded `UsePotion` commands — so a
held potion at an unguided screen made the fallback silently drink (pre-v22,
AnyTime potions only — never hit by the recordings) or discard (v22,
EVERY held potion — broke 933T39V18D act-2 player_hp parity) instead of
proceeding.
"""
from types import SimpleNamespace

from sts2_rl.conformance.runner import _ForceWinDriver
from sts2_rl.driver import (
    DecisionKind,
    DecisionRequest,
    POTION_ACTION_BASE,
)
from sts2_rl.run_env import STS2RunEnv


class _EmptyCursor:
    """A cursor with no recorded guidance for anything."""

    def take(self, *names):
        return None

    def take_before(self, name, boundary):
        return None

    def take_first_of(self, names, boundary):
        return None


def _bare_runner():
    driver = _ForceWinDriver.__new__(_ForceWinDriver)
    driver._cursor = _EmptyCursor()
    driver._grid_open = None
    driver._grid_picks = []
    return driver


def _run_with_belt(pids):
    env = STS2RunEnv()
    env.reset(seed=0)
    run = env._run
    from sts2_rl.potions import make_potion

    for i, pid in enumerate(pids):
        run.potions[i] = make_potion(pid)
    return run


def test_unguided_event_fallback_ignores_belt_actions():
    # fire_potion is combat-only: pre-v22 it added nothing to legal_actions
    # out of combat; v22's discard namespace lists it, so it became
    # legal[-1] on every unguided event screen.
    run = _run_with_belt(["fire_potion"])
    event = SimpleNamespace(
        options=[SimpleNamespace(locked=False) for _ in range(3)])
    req = DecisionRequest(
        kind=DecisionKind.EVENT, run=run, event=event,
        purpose="event",
    )
    legal = req.legal_actions()
    assert max(legal) >= POTION_ACTION_BASE, "test needs a belt action last"
    answer = _bare_runner()._answer_event(req, legal)
    assert answer in req.own_actions(), (
        f"unguided event fallback left the own-action namespace: {answer}"
    )


def test_skippable_grid_stop_ignores_belt_actions():
    run = _run_with_belt(["fire_potion"])
    card = SimpleNamespace(name="Strike")
    req = DecisionRequest(
        kind=DecisionKind.SELECT_CARDS, run=run,
        purpose="smith", candidates=[card], count_remaining=1,
        skippable=True,
    )
    legal = req.legal_actions()
    assert max(legal) >= POTION_ACTION_BASE, "test needs a belt action last"
    answer = _bare_runner()._answer_select_grid(req, legal)
    assert answer in req.own_actions(), (
        f"skippable grid stop left the own-action namespace: {answer}"
    )
