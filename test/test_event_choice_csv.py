"""Event-choice tallies (``ep_event_choices``) + ``PATH.events.csv`` export.

The env counts every chosen event option as (event id, page, option key);
`evaluate_run` pools them across episodes; `write_events_csv` renders the
per-(event, page) choice percentages in the same (policy, key...) shape as
the cards/potions CSVs.
"""
import io
import random

from sts2_rl.driver import DecisionKind, DecisionRequest, POTION_ACTION_BASE
from sts2_rl.events.base import EventOption
from sts2_rl.run_env import STS2RunEnv


class _StubEvent:
    def __init__(self, event_id, page, options):
        self.id = event_id
        self.page = page
        self.options = options


def _event_request(run, event):
    return DecisionRequest(kind=DecisionKind.EVENT, run=run, event=event)


def test_event_choices_tallied_and_reported_at_episode_end():
    env = STS2RunEnv()
    env.reset(seed=0)
    ev = _StubEvent("reflections", "INITIAL", [
        EventOption("TOUCH_A_MIRROR", lambda: None),
        EventOption("SHATTER", lambda: None),
    ])
    req = _event_request(env._run, ev)
    env._count_behavior(req, 1)
    env._count_behavior(req, 1)
    env._count_behavior(req, 0)
    # A mid-event belt drink is legal but is NOT an event choice.
    env._count_behavior(req, POTION_ACTION_BASE)
    assert dict(env._ep_event_choices) == {
        ("reflections", "INITIAL", "SHATTER"): 2,
        ("reflections", "INITIAL", "TOUCH_A_MIRROR"): 1,
    }
    # Episode-end info carries the tally like the other ep_ dicts.
    env._steps = env._max_steps
    info = env._info()
    assert info["ep_event_choices"] == dict(env._ep_event_choices)


def test_event_choices_reset_per_episode():
    env = STS2RunEnv()
    env.reset(seed=0)
    ev = _StubEvent("reflections", "INITIAL", [EventOption("SHATTER", lambda: None)])
    env._count_behavior(_event_request(env._run, ev), 0)
    assert env._ep_event_choices
    env.reset(seed=1)
    assert not env._ep_event_choices


def test_run_eval_report_event_table_and_events_csv():
    from sts2_rl.evaluation import RunEvalReport, write_events_csv

    report = RunEvalReport(
        episodes=2, floors=(5, 9), acts=(0, 0), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(10, 12),
        event_choice_counts_raw={
            ("reflections", "INITIAL", "SHATTER"): 3,
            ("reflections", "INITIAL", "TOUCH_A_MIRROR"): 1,
            ("big_fish", "INITIAL", "EAT"): 1,
        },
    )
    buf = io.StringIO()
    write_events_csv(buf, [("p", report)])
    rows = buf.getvalue().strip().splitlines()
    assert rows[0] == "policy,event,page,option,chosen,visits,pct"
    # pct is within the (event, page) group; visits is the group total.
    assert "p,reflections,INITIAL,SHATTER,3,4,0.75" in rows
    assert "p,reflections,INITIAL,TOUCH_A_MIRROR,1,4,0.25" in rows
    assert "p,big_fish,INITIAL,EAT,1,1,1.0" in rows
    # Most-visited (event, page) group first; inside a group, most-chosen
    # first — each group reads as its own histogram.
    assert rows[1] == "p,reflections,INITIAL,SHATTER,3,4,0.75"


def test_evaluate_run_pools_event_choices():
    from sts2_rl.evaluation import evaluate_run
    from sts2_rl.run_env import masked_random_run_policy

    rep = evaluate_run(masked_random_run_policy(random.Random(0)), episodes=1,
                       seed=0, env=STS2RunEnv())
    # Every run opens on the Ancient (Neow) event, so one episode is enough
    # to see at least one pooled choice.
    assert rep.event_choice_counts_raw
    assert all(isinstance(k, tuple) and len(k) == 3 and isinstance(v, int)
               for k, v in rep.event_choice_counts_raw.items())
