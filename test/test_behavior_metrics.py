"""Per-episode behavior metrics: ep_end_turns / ep_energy_unspent /
ep_card_offers / ep_card_takes.

Env side (STS2RunEnv + subclasses): count, per episode,
  - how many times the agent ended a combat turn and how much energy it left
    unspent doing so (only real player-turn end-turns; the always-legal
    no-op "end turn" outside the player's turn must not count), and
  - how many resolved REWARD_CARD screens it saw (take or skip answers only —
    reroll/sacrifice re-raise or transform the screen, and a belt drink
    doesn't answer it at all) and how many it took a card on.
Reported in `info` at episode end only, next to is_success.

vec_env: StepBatch carries them as a (E, 4) float32 `metrics` array in
EP_METRIC_KEYS order, NaN everywhere except done envs that reported them.

train_torch: CSV gains energy_unspent (mean per end-turn) and card_take
(take rate) columns.
"""
import numpy as np
import pytest
from gymnasium import spaces

from sts2_rl.combat import Phase
from sts2_rl.curriculum_env import STS2CurriculumRunEnv
from sts2_rl.driver import DecisionKind
from sts2_rl.run_env import CHOICE_BASE

_ENV = None


def shared_env():
    """Construction probes a CombatState, so share one env across tests."""
    global _ENV
    if _ENV is None:
        _ENV = STS2CurriculumRunEnv(column_rooms=3)
    return _ENV


def _expected_counts_step(env, action, tally):
    """Track, independently of the env's own counters, what a step should
    contribute — the spec the reported info must match."""
    request = env._request
    if request is None:
        return
    if (request.kind == DecisionKind.COMBAT and action == 0
            and request.combat is not None
            and request.combat.phase == Phase.PLAYER_TURN):
        tally["end_turns"] += 1
        tally["energy_unspent"] += request.combat.player.energy
    if request.kind == DecisionKind.REWARD_CARD and action >= CHOICE_BASE:
        answer = action - CHOICE_BASE
        n = len(request.rewards.cards)
        if answer <= n:                      # take or skip; not reroll/sacrifice
            tally["card_offers"] += 1
            tally["card_takes"] += int(answer < n)


def test_run_env_reports_episode_behavior_metrics():
    env = shared_env()
    rng = np.random.default_rng(0)
    saw_offers = False
    saw_end_turns = False
    for seed in range(6):
        tally = dict(end_turns=0, energy_unspent=0, card_offers=0, card_takes=0)
        env.reset(seed=seed)
        for _ in range(20_000):
            mask = env.action_masks()
            action = int(rng.choice(np.flatnonzero(mask)))
            _expected_counts_step(env, action, tally)
            _, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
            # Mid-episode steps must NOT carry the episode summary.
            assert "ep_end_turns" not in info
        else:
            pytest.fail("episode did not finish")
        assert info["ep_end_turns"] == tally["end_turns"]
        assert info["ep_energy_unspent"] == pytest.approx(tally["energy_unspent"])
        assert info["ep_card_offers"] == tally["card_offers"]
        assert info["ep_card_takes"] == tally["card_takes"]
        # v23: the per-act split must reconcile with the whole-run tally.
        assert sum(info["ep_card_offers_by_act"].values()) == tally["card_offers"]
        assert sum(info["ep_card_takes_by_act"].values()) == tally["card_takes"]
        saw_end_turns = saw_end_turns or tally["end_turns"] > 0
        saw_offers = saw_offers or tally["card_offers"] > 0
    # The tracked episodes must actually exercise the counters, or the
    # equalities above are vacuous.
    assert saw_end_turns
    assert saw_offers


class _StubEnv:
    """Minimal masked env: episode = 2 steps, reports metrics on done."""

    observation_space = spaces.Dict({
        "f": spaces.Box(0.0, 1.0, (3,), dtype=np.float32),
        "i": spaces.Box(0, 9, (2,), dtype=np.int64),
    })
    action_space = spaces.Discrete(4)

    def __init__(self, report_metrics: bool, floor: int | None = None):
        self._report = report_metrics
        self._floor = floor
        self._n = 0

    def _obs(self):
        return {"f": np.zeros(3, np.float32), "i": np.zeros(2, np.int32)}

    def reset(self, seed=None):
        self._n = 0
        return self._obs(), {}

    def action_masks(self):
        return np.ones(4, bool)

    def step(self, action):
        self._n += 1
        done = self._n >= 2
        info = {}
        if done and self._report:
            info = {"is_success": True, "ep_end_turns": 3,
                    "ep_energy_unspent": 5.0,
                    "ep_card_offers": 2, "ep_card_takes": 1}
        if self._floor is not None:
            info["floor"] = self._floor
        return self._obs(), 1.0, done, False, info

    def close(self):
        pass


def test_vec_env_carries_episode_metrics(monkeypatch):
    from sts2_rl import vec_env as vv

    assert vv.EP_METRIC_KEYS == (
        "ep_end_turns", "ep_energy_unspent", "ep_card_offers", "ep_card_takes",
        "ep_upgrades", "ep_removes", "ep_elites_won",
        "ep_potions_obtained", "ep_potions_used",
        "ep_potions_used_elite", "ep_potions_used_boss", "ep_potions_used_normal",
        "ep_potions_expired", "ep_potion_use_hp",
        "ep_relics",
        "ep_hp_lost",
        # v20 (Task 3b): inserted BEFORE "floor" so metrics[:, -1] stays the
        # floor column.
        "ep_boss_hp_lost",
        # v23: same before-"floor" insertion.
        "ep_potions_discarded",
        "floor")

    built = []

    def _build(spec):
        env = _StubEnv(report_metrics=len(built) == 0)  # env 1 reports nothing
        built.append(env)
        return env

    monkeypatch.setattr(vv, "build_env", _build)
    venv = vv.SerialVecEnv(vv.EnvSpec(kind="column"), 2)

    venv.reset([0, 1])
    batch = venv.step([0, 0])                 # step 1: nobody done
    assert batch.metrics.shape == (2, 19)
    assert np.isnan(batch.metrics).all()

    batch = venv.step([0, 0])                 # step 2: both done
    np.testing.assert_allclose(batch.metrics[0][:4], [3.0, 5.0, 2.0, 1.0])
    # The stub reports only the v6 keys; the v7 tail stays NaN.
    assert np.isnan(batch.metrics[0][4:]).all()
    # A done env that reported no metrics (e.g. the combat env) stays NaN.
    assert np.isnan(batch.metrics[1]).all()
    venv.close()


def test_vec_env_carries_end_of_episode_floor(monkeypatch):
    """train_torch logs metrics[:, -1] as ep_ret, so the floor column has to
    be the floor the episode ENDED on -- harvested on the terminal step only,
    even though run_env's info carries `floor` every step."""
    from sts2_rl import vec_env as vv

    assert vv.EP_METRIC_KEYS[-1] == "floor"

    built = []

    def _build(spec):
        # env 1 is the combat env: no floor in info at all.
        env = _StubEnv(report_metrics=True,
                       floor=17 if not built else None)
        built.append(env)
        return env

    monkeypatch.setattr(vv, "build_env", _build)
    venv = vv.SerialVecEnv(vv.EnvSpec(kind="column"), 2)

    venv.reset([0, 1])
    batch = venv.step([0, 0])                 # step 1: nobody done
    assert np.isnan(batch.metrics[:, -1]).all()

    batch = venv.step([0, 0])                 # step 2: both done
    assert batch.metrics[0, -1] == 17.0
    assert np.isnan(batch.metrics[1, -1])     # combat env -> no floor
    venv.close()


def test_csv_has_behavior_metric_columns(tmp_path):
    import train_torch as tt

    assert "energy_unspent" in tt.CSV_FIELDS
    assert "card_take" in tt.CSV_FIELDS
    path = str(tmp_path / "m.csv")
    tt.append_csv_row(path, dict(
        iter=1, global_step=2, wall_seconds=3.0, sps=4,
        ep_ret=1.5, win=0.0, ep_len=210.0, pg=-0.01, v=0.3,
        ent=0.5, kl=0.001, clipfrac=0.02, lr=3e-4,
        energy_unspent=1.25, card_take=0.4,
        upgrades=2.0, removes=1.0, elites=0.5, potions_got=1.5, potions_used=1.0,
        potions_used_elite=0.2, potions_used_boss=0.1, potions_used_normal=0.7,
        potions_expired=0.3, potion_use_hp=0.55, relics=0.8, hp_lost=12.5,
        aux=0.02,
    ))
    with open(path) as fh:
        header, row = fh.read().strip().splitlines()
    assert header.split(",")[-17:] == [
        "energy_unspent", "card_take",
        "upgrades", "removes", "elites", "potions_got", "potions_used",
        "potions_used_elite", "potions_used_boss", "potions_used_normal",
        "potions_expired", "potion_use_hp", "relics", "hp_lost", "aux",
        "potion_ent",
        # v23: trailing mean voluntary discards per episode.
        "potions_discarded"]
    assert row.split(",")[-17:] == [
        "1.25", "0.4", "2.0", "1.0", "0.5", "1.5", "1.0",
        "0.2", "0.1", "0.7", "0.3", "0.55", "0.8", "12.5", "0.02", "", ""]


# ── Rest sites: heal / upgrade share of visits ────────────────────────────────
#
# A rest site is a decision LOOP, not one screen (driver._rest_site re-asks
# until Leave, and Miniature Tent lets one visit act twice), so the tallies
# are per VISIT: answering heal twice in one visit is still one healed visit.
# Visits are keyed on (act, floor) — a rest site is one room on one floor, and
# its decisions are consecutive, so the key changes exactly at a visit
# boundary. Denominator is every visit, including Leave-only ones.


class _FakeRun:
    def __init__(self, act, floor, hp=100, max_hp=100):
        self.act_index = act
        self.total_floor = floor
        self.hp = hp
        self.max_hp = max_hp


def _rest(env, act, floor, answer, hp=100, max_hp=100):
    """Feed one answered REST decision straight to the tally."""
    from sts2_rl.driver import DecisionRequest

    env._count_behavior(
        DecisionRequest(kind=DecisionKind.REST, run=_FakeRun(act, floor, hp, max_hp)),
        answer)


def _rest_tallies(env):
    return (env._ep_rest_visits, env._ep_rest_heals, env._ep_rest_upgrades)


def _fresh_env():
    env = shared_env()
    env.reset(seed=0)
    return env


def test_one_rest_decision_is_one_visit():
    from sts2_rl.driver import REST_HEAL

    env = _fresh_env()
    before = _rest_tallies(env)
    _rest(env, 0, 6, REST_HEAL)
    assert _rest_tallies(env) == (before[0] + 1, before[1] + 1, before[2])


def test_repeated_actions_on_one_floor_stay_one_visit():
    """Miniature Tent: heal AND smith in a single visit counts once each,
    against a single visit — not two visits."""
    from sts2_rl.driver import REST_HEAL, REST_SMITH

    env = _fresh_env()
    before = _rest_tallies(env)
    _rest(env, 0, 6, REST_HEAL)
    _rest(env, 0, 6, REST_SMITH)
    v, h, u = _rest_tallies(env)
    assert (v, h, u) == (before[0] + 1, before[1] + 1, before[2] + 1)


def test_same_floor_in_a_later_act_is_a_new_visit():
    """Floor alone is not the key — act 2's floor 6 is a different room."""
    from sts2_rl.driver import REST_HEAL

    env = _fresh_env()
    before = _rest_tallies(env)
    _rest(env, 0, 6, REST_HEAL)
    _rest(env, 1, 6, REST_HEAL)
    assert _rest_tallies(env) == (before[0] + 2, before[1] + 2, before[2])


def test_leaving_a_rest_site_still_counts_as_a_visit():
    from sts2_rl.driver import REST_LEAVE

    env = _fresh_env()
    before = _rest_tallies(env)
    _rest(env, 0, 6, REST_LEAVE)
    assert _rest_tallies(env) == (before[0] + 1, before[1], before[2])


def test_extra_rest_options_are_visits_but_neither_heal_nor_upgrade():
    """Dig / Lift / Kindle sit at index 3+ and are their own thing."""
    from sts2_rl.driver import REST_LEAVE

    env = _fresh_env()
    before = _rest_tallies(env)
    _rest(env, 0, 6, REST_LEAVE + 1)
    assert _rest_tallies(env) == (before[0] + 1, before[1], before[2])


def test_rest_hihp_split():
    """rest_visits_hihp/rest_upgrades_hihp condition on hp/max_hp at the
    visit's FIRST answer (>= HIHP_REST_THRESHOLD), classified once per visit
    and unaffected by later answers at the same site."""
    from sts2_rl.driver import REST_SMITH

    env = _fresh_env()
    before_v = env._ep_rest_visits_hihp
    before_u = env._ep_rest_upgrades_hihp
    # hi-HP visit: hp/max_hp >= 0.65 at first answer
    _rest(env, 0, 6, REST_SMITH, hp=70, max_hp=100)
    assert (env._ep_rest_visits_hihp, env._ep_rest_upgrades_hihp) == (
        before_v + 1, before_u + 1)
    # second answer at the same site: no double count
    _rest(env, 0, 6, REST_SMITH, hp=70, max_hp=100)
    assert env._ep_rest_upgrades_hihp == before_u + 1
    # new site, low HP: visit not counted as hihp even if it smiths
    _rest(env, 0, 7, REST_SMITH, hp=30, max_hp=100)
    assert (env._ep_rest_visits_hihp, env._ep_rest_upgrades_hihp) == (
        before_v + 1, before_u + 1)


def test_rest_tallies_are_reported_and_reset_per_episode():
    from sts2_rl.driver import REST_HEAL

    env = _fresh_env()
    _rest(env, 0, 6, REST_HEAL)
    assert env._ep_rest_visits == 1
    env.reset(seed=1)
    assert _rest_tallies(env) == (0, 0, 0)
    assert env._ep_rest_visits_hihp == 0
    assert env._ep_rest_upgrades_hihp == 0
    assert "ep_rest_visits" not in env._info()   # mid-episode: not yet
    assert "ep_rest_visits_hihp" not in env._info()
    assert "ep_rest_upgrades_hihp" not in env._info()
    # Force the episode-end branch (without a full simulated episode) to
    # confirm the new keys are surfaced there, same as ep_rest_visits.
    env._steps = env._max_steps
    end_info = env._info()
    assert "ep_rest_visits_hihp" in end_info
    assert "ep_rest_upgrades_hihp" in end_info
    env.reset(seed=2)   # restore state for later tests sharing this env


# ── Eval side: evaluation.evaluate_run carries the same metrics ───────────────
#
# The env already tallies them per episode (above); these cover the eval
# harness reading them back, the pooled aggregates, the exact-value return
# histogram, and the spreadsheet export.


class _ScriptedRunEnv:
    """A run-env stand-in with hand-written episodes.

    Each script is one episode: the per-step rewards it pays out and the
    `ep_*` tallies its terminal `info` reports. Episodes are consumed in
    reset() order, so `evaluate_run(episodes=len(SCRIPTS))` plays each once.
    Real envs are too expensive to pin exact returns against, and the point
    here is the harness arithmetic, not the game.
    """

    def __init__(self, scripts):
        self._scripts = scripts
        self._i = -1
        self._step = 0

    def reset(self, seed=None):
        self._i += 1
        self._step = 0
        return {}, {"floor": 0, "act": 0}

    def action_masks(self):
        return np.ones(2, bool)

    def step(self, action):
        s = self._scripts[self._i]
        reward = s["rewards"][self._step]
        self._step += 1
        done = self._step >= len(s["rewards"])
        info = {"floor": s["floor"], "act": s["act"]}
        if done:
            info.update({
                "is_success": s["win"], "hp_left": s["hp_left"],
                "decisions": len(s["rewards"]),
                "ep_end_turns": s["end_turns"],
                "ep_energy_unspent": s["energy_unspent"],
                "ep_card_offers": s["card_offers"],
                "ep_card_takes": s["card_takes"],
                "ep_rest_visits": s["rest_visits"],
                "ep_rest_heals": s["rest_heals"],
                "ep_rest_upgrades": s["rest_upgrades"],
                "ep_rest_visits_hihp": s["rest_visits_hihp"],
                "ep_rest_upgrades_hihp": s["rest_upgrades_hihp"],
            })
        return {}, reward, done, False, info


def _script(rewards, end_turns, energy_unspent, card_offers, card_takes,
            floor=1, act=0, win=False, hp_left=0,
            rest_visits=0, rest_heals=0, rest_upgrades=0,
            rest_visits_hihp=0, rest_upgrades_hihp=0):
    return dict(rewards=rewards, end_turns=end_turns,
                energy_unspent=energy_unspent, card_offers=card_offers,
                card_takes=card_takes, floor=floor, act=act, win=win,
                hp_left=hp_left, rest_visits=rest_visits,
                rest_heals=rest_heals, rest_upgrades=rest_upgrades,
                rest_visits_hihp=rest_visits_hihp,
                rest_upgrades_hihp=rest_upgrades_hihp)


# Chosen so the assertions below can't pass by accident:
#   - two different episodes sum to the same return (3.0), so the histogram
#     must actually tally rather than list;
#   - 0.1 + 0.2 and a bare 0.3 must land in ONE bucket, so the tally must
#     round away float noise;
#   - per-episode turn counts differ wildly (2 vs 8), so a mean-of-means
#     energy figure (1.5) differs from the pooled one (10/11).
_SCRIPTS = [
    _script([1.0, 2.0], end_turns=2, energy_unspent=5.0,
            card_offers=2, card_takes=1, floor=17, act=0,
            rest_visits=3, rest_heals=2, rest_upgrades=1,
            rest_visits_hihp=2, rest_upgrades_hihp=1),
    _script([0.5, 0.5, 2.0], end_turns=8, energy_unspent=4.0,
            card_offers=1, card_takes=1, floor=23, act=1, win=True, hp_left=44,
            rest_visits=5, rest_heals=1, rest_upgrades=4,
            rest_visits_hihp=3, rest_upgrades_hihp=2),
    _script([-1.0], end_turns=0, energy_unspent=0.0,
            card_offers=0, card_takes=0, floor=5, act=0),
    _script([0.1, 0.2], end_turns=1, energy_unspent=1.0,
            card_offers=1, card_takes=0, floor=9, act=0,
            rest_visits=2, rest_heals=1, rest_upgrades=0),
    _script([0.3], end_turns=0, energy_unspent=0.0,
            card_offers=0, card_takes=0, floor=3, act=0),
]


def _scripted_report(scripts=_SCRIPTS, seed=100):
    from sts2_rl.evaluation import evaluate_run

    return evaluate_run(lambda env, obs, mask: 0, episodes=len(scripts),
                        seed=seed, env=_ScriptedRunEnv(scripts))


def test_evaluate_run_records_seeds_and_returns():
    report = _scripted_report()
    assert report.seeds == (100, 101, 102, 103, 104)
    assert report.returns == pytest.approx((3.0, 3.0, -1.0, 0.3, 0.3))


def test_evaluate_run_carries_episode_behavior_tallies():
    report = _scripted_report()
    assert report.end_turns == (2, 8, 0, 1, 0)
    assert report.energy_unspent == pytest.approx((5.0, 4.0, 0.0, 1.0, 0.0))
    assert report.card_offers == (2, 1, 0, 1, 0)
    assert report.card_takes == (1, 1, 0, 0, 0)
    assert report.rest_visits == (3, 5, 0, 2, 0)
    assert report.rest_heals == (2, 1, 0, 1, 0)
    assert report.rest_upgrades == (1, 4, 0, 0, 0)
    assert report.rest_visits_hihp == (2, 3, 0, 0, 0)
    assert report.rest_upgrades_hihp == (1, 2, 0, 0, 0)


def test_behavior_rates_pool_over_episodes_not_over_means():
    """Weighted by turns/offers, matching how train_torch aggregates them.

    A mean-of-per-episode-means would give 1.5 energy and 0.5 take here.
    """
    report = _scripted_report()
    assert report.energy_unspent_per_turn == pytest.approx(10.0 / 11.0)
    assert report.card_take_rate == pytest.approx(2.0 / 4.0)
    assert report.rest_heal_rate == pytest.approx(4.0 / 10.0)
    assert report.rest_upgrade_rate == pytest.approx(5.0 / 10.0)


def test_behavior_rates_are_zero_not_nan_without_denominator():
    """The combat envs emit no tallies at all; the report must stay printable."""
    report = _scripted_report([_script([1.0], end_turns=0, energy_unspent=0.0,
                                       card_offers=0, card_takes=0)])
    assert report.energy_unspent_per_turn == 0.0
    assert report.card_take_rate == 0.0
    assert report.rest_heal_rate == 0.0
    assert report.rest_upgrade_rate == 0.0


def test_return_histogram_tallies_exact_values_in_ascending_order():
    report = _scripted_report()
    hist = report.return_histogram
    assert list(hist) == [-1.0, 0.3, 3.0]        # ascending, float noise folded
    assert list(hist.values()) == [1, 2, 2]
    assert sum(hist.values()) == report.episodes


def test_write_run_csv_exports_episode_and_histogram_tables(tmp_path):
    from sts2_rl.evaluation import write_run_csv

    report = _scripted_report()
    ep_path, hist_path = write_run_csv(
        str(tmp_path / "out.csv"), [("ckpt.pt", report)])

    # A trailing .csv on the stem is stripped, not doubled.
    assert ep_path == str(tmp_path / "out.episodes.csv")
    assert hist_path == str(tmp_path / "out.hist.csv")

    with open(ep_path) as fh:
        rows = [line.split(",") for line in fh.read().strip().splitlines()]
    assert rows[0] == ["policy", "seed", "floor", "act", "win", "truncated",
                       "hp_left", "decisions", "ep_return", "end_turns",
                       "energy_unspent", "card_offers", "card_takes",
                       "rest_visits", "rest_heals", "rest_upgrades",
                       "upgrades", "removes", "elites", "elites_fought",
                       "potions_got", "potions_used",
                       "potions_used_elite", "potions_used_boss",
                       "potions_used_normal", "potions_expired",
                       "potion_use_hp", "relics", "hp_lost",
                       "hp_ratio_mean", "rest_visits_hihp", "rest_upgrades_hihp",
                       # v20 (Task 3b): appended at the END so existing
                       # column indices stay valid.
                       "boss_hp_lost",
                       # v21: appended at the END so existing column indices
                       # stay valid.
                       "potion_v_at_use", "potions_wasted", "potions_bought",
                       "potion_rewards_skipped", "potion_rewards_forced",
                       "potion_relic_picks",
                       "potions_discarded",
                       # v23: appended at the END — per-act card-reward split.
                       "card_offers_a1", "card_takes_a1",
                       "card_offers_a2", "card_takes_a2",
                       "card_offers_a3", "card_takes_a3"]
    assert len(rows) == 1 + report.episodes
    assert rows[1] == ["ckpt.pt", "100", "17", "0", "0", "0", "0", "2",
                       "3.0", "2", "5.0", "2", "1", "3", "2", "1",
                       "0", "0", "0", "0", "0", "0",
                       "0", "0", "0", "0", "0.0", "0", "0", "0.0", "2", "1",
                       "0",   # v20: trailing boss_hp_lost
                       "0.0", "0", "0", "0", "0", "0",   # v21: trailing potion fields
                       "0",   # v22: trailing potions_discarded
                       "0", "0", "0", "0", "0", "0"]   # v23: per-act card split
    assert rows[2][:8] == ["ckpt.pt", "101", "23", "1", "1", "0", "44", "3"]

    with open(hist_path) as fh:
        hrows = [line.split(",") for line in fh.read().strip().splitlines()]
    assert hrows[0] == ["policy", "ep_return", "count", "freq"]
    assert hrows[1] == ["ckpt.pt", "-1.0", "1", "0.2"]
    assert hrows[2] == ["ckpt.pt", "0.3", "2", "0.4"]
    assert hrows[3] == ["ckpt.pt", "3.0", "2", "0.4"]


def test_write_run_csv_keeps_policy_rows_together(tmp_path):
    from sts2_rl.evaluation import write_run_csv

    report = _scripted_report()
    ep_path, hist_path = write_run_csv(
        str(tmp_path / "out"), [("masked-random", report), ("ckpt.pt", report)])

    with open(ep_path) as fh:
        names = [line.split(",")[0] for line in fh.read().strip().splitlines()[1:]]
    assert names == ["masked-random"] * 5 + ["ckpt.pt"] * 5

    with open(hist_path) as fh:
        names = [line.split(",")[0] for line in fh.read().strip().splitlines()[1:]]
    assert names == ["masked-random"] * 3 + ["ckpt.pt"] * 3


def test_reward_histogram_lines_render_every_value_with_a_bar():
    from sts2_rl.evaluation import reward_histogram_lines

    report = _scripted_report()
    lines = reward_histogram_lines("ckpt.pt", report)
    body = [ln for ln in lines if "#" in ln]
    assert len(body) == 3
    for value, count in report.return_histogram.items():
        assert any(f"{value:.3f}" in ln and str(count) in ln for ln in body)
    # The modal values get the longest bar.
    assert max(ln.count("#") for ln in body) == body[1].count("#")


def test_card_take_rate_by_act_pools_over_episodes():
    from sts2_rl.evaluation import RunEvalReport

    rep = RunEvalReport(
        episodes=2, floors=(10, 20), acts=(0, 1), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(5, 5),
        seeds=(1, 2), returns=(0.0, 0.0),
        card_offers_by_act=({0: 2, 1: 1}, {0: 2}),
        card_takes_by_act=({0: 1, 1: 1}, {0: 2}))
    assert rep.card_take_rate_by_act == {0: (4, 3, 0.75), 1: (1, 1, 1.0)}


def test_episode_csv_carries_per_act_card_columns(tmp_path):
    import csv as csv_mod
    from sts2_rl.evaluation import RunEvalReport, write_run_csv

    rep = RunEvalReport(
        episodes=1, floors=(10,), acts=(2,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(5,),
        seeds=(1,), returns=(0.0,),
        card_offers_by_act=({0: 3, 2: 1},), card_takes_by_act=({0: 2},))
    ep_path, _ = write_run_csv(str(tmp_path / "out"), [("p", rep)])
    with open(ep_path, newline="") as fh:
        row = next(iter(csv_mod.DictReader(fh)))
    assert (row["card_offers_a1"], row["card_takes_a1"]) == ("3", "2")
    assert (row["card_offers_a3"], row["card_takes_a3"]) == ("1", "0")
