"""v7 reward terms (plan Task 6+). All default OFF: a default-constructed env
must be bit-identical to v6 behavior (the whole existing suite is that
regression test). These tests only exercise the opted-in terms."""
import random

import numpy as np

from sts2_rl.driver import DecisionKind, REST_SMITH
from sts2_rl.run_env import CHOICE_BASE, STS2RunEnv


def _roll(env, seed, steps=400):
    obs, _ = env.reset(seed=seed)
    total = 0.0
    info = {}
    for _ in range(steps):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        obs, r, term, trunc, info = env.step(a)
        total += r
        if term or trunc:
            break
    return total, info


def _roll_smith(env, seed, steps=600):
    """First-legal policy, except: at a rest site prefer the SMITH slot when
    it is masked legal (so the run actually upgrades cards)."""
    obs, _ = env.reset(seed=seed)
    total = 0.0
    info = {}
    for _ in range(steps):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        req = env._request
        if (req is not None and req.kind == DecisionKind.REST
                and mask[CHOICE_BASE + REST_SMITH]):
            a = CHOICE_BASE + REST_SMITH
        obs, r, term, trunc, info = env.step(a)
        total += r
        if term or trunc:
            break
    return total, info


def test_act_scaled_floor_rewards_match_scalar_when_flat():
    r_flat, _ = _roll(STS2RunEnv(), seed=3)
    r_tuple, _ = _roll(STS2RunEnv(floor_rewards_by_act=(1.0, 1.0, 1.0)), seed=3)
    assert r_flat == r_tuple            # (1,1,1) tuple == scalar 1.0


def test_upgrade_reward_fires_on_smith():
    r_off, info_off = _roll_smith(STS2RunEnv(), seed=4)
    r_on, info_on = _roll_smith(STS2RunEnv(reward_upgrade=0.5), seed=4)
    ups = info_on.get("ep_upgrades", 0)
    assert ups > 0, "seed 4 smith trajectory produced no upgrades — repin seed"
    assert info_off.get("ep_upgrades") == ups   # tally is metric-only, always on
    assert abs((r_on - r_off) - 0.5 * ups) < 1e-9


def test_default_env_reward_unchanged():
    r_a, info_a = _roll(STS2RunEnv(), seed=7)
    r_b, info_b = _roll(STS2RunEnv(floor_rewards_by_act=None, reward_upgrade=0.0,
                                   reward_remove=0.0, reward_elite=0.0), seed=7)
    assert r_a == r_b
    # New tallies are present at episode end even when rewards are off.
    for k in ("ep_upgrades", "ep_removes", "ep_elites_won",
              "ep_potions_obtained", "ep_potions_used"):
        assert k in info_a and info_a[k] == info_b[k]


def test_card_offer_and_take_ids_reported():
    # First-legal dies on floor 1 without ever winning a combat, so use a
    # masked-random policy (it survives long enough to see card rewards).
    env = STS2RunEnv()
    rng = np.random.default_rng(0)
    info = {}
    for seed in range(6):
        env.reset(seed=seed)
        for _ in range(20_000):
            mask = env.action_masks()
            a = int(rng.choice(np.flatnonzero(mask)))
            _, _, term, trunc, info = env.step(a)
            if term or trunc:
                break
        if info.get("ep_card_take_ids"):
            break
    offers = info.get("ep_card_offer_ids")
    takes = info.get("ep_card_take_ids")
    assert isinstance(offers, dict) and offers, "no card offers in 6 seeds — repin"
    assert isinstance(takes, dict) and takes
    assert all(isinstance(k, str) and isinstance(v, int) for k, v in offers.items())
    assert set(takes) <= set(offers)
    assert sum(takes.values()) <= sum(offers.values())


def test_run_eval_report_potion_rate_and_card_counts():
    from sts2_rl.evaluation import RunEvalReport, write_cards_csv

    report = RunEvalReport(
        episodes=2, floors=(5, 9), acts=(0, 0), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(10, 12),
        potions_obtained=(2, 2), potions_used=(1, 2),
        card_offer_counts={"Cleave": 3, "Bash": 1},
        card_take_counts_raw={"Cleave": 2},
    )
    assert report.potion_use_rate == 0.75          # pooled 3/4
    assert report.card_take_counts == {"Cleave": (3, 2), "Bash": (1, 0)}

    empty = RunEvalReport(
        episodes=1, floors=(1,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(1,))
    assert empty.potion_use_rate == 0.0            # nothing obtained -> 0, not NaN

    import io
    buf = io.StringIO()
    write_cards_csv(buf, [("p", report)])
    rows = buf.getvalue().strip().splitlines()
    assert rows[0] == "policy,card,offered,taken,take_rate"
    assert "p,Cleave,3,2,0.666667" in rows
    assert "p,Bash,1,0,0.0" in rows


def test_deck_randomization_adds_pool_cards():
    from sts2_rl.cards.pool import reward_pool_card_ids

    base_env = STS2RunEnv()
    base_env.reset(seed=0)
    starter = [type(c).__name__ for c in base_env._run.deck]

    env = STS2RunEnv(deck_random_prob=1.0)
    decks = []
    for seed in range(20):
        env.reset(seed=seed)
        deck = env._run.deck
        pool = set(reward_pool_card_ids(env._run.card_pool))
        extras = deck[len(starter):]
        assert len(starter) + 4 <= len(deck) <= len(starter) + 14
        assert [type(c).__name__ for c in deck[:len(starter)]] == starter
        for c in extras:
            assert c.id in pool
            if c.upgrade_level:
                assert c.max_upgrade_level > 0
        decks.append(tuple((c.id, c.upgrade_level) for c in deck))
    assert len(set(decks)) > 1          # decks differ across seeds


def test_deck_random_off_is_bit_identical():
    import numpy as np

    for seed in range(5):
        a = STS2RunEnv()
        b = STS2RunEnv(deck_random_prob=0.0)
        obs_a, _ = a.reset(seed=seed)
        obs_b, _ = b.reset(seed=seed)
        assert [(c.id, c.upgrade_level) for c in a._run.deck] == \
               [(c.id, c.upgrade_level) for c in b._run.deck]
        # Same RNG stream: prob=0.0 must draw NOTHING extra (branch_prob
        # precedent, curriculum_env.py:238-244).
        assert np.array_equal(obs_a["f"], obs_b["f"])
        assert np.array_equal(obs_a["i"], obs_b["i"])


def test_full_combat_env_ascension_reaches_hooks():
    # Task 10: the combat env passes ascension into CombatState, which seeds
    # hooks.ascension BEFORE create_monsters — so Tough (asc 8+) HP shows.
    from sts2_rl.full_env import STS2FullCombatEnv
    from sts2_rl.monsters import DECIMILLIPEDE_ELITE

    env9 = STS2FullCombatEnv(encounter=DECIMILLIPEDE_ELITE, ascension=9)
    env9.reset(seed=0)
    assert env9._state.hooks.ascension == 9
    env0 = STS2FullCombatEnv(encounter=DECIMILLIPEDE_ELITE)
    env0.reset(seed=0)
    assert env0._state.hooks.ascension == 0
    hp9 = sum(m.hp for m in env9._state.enemies)
    hp0 = sum(m.hp for m in env0._state.enemies)
    assert hp9 > hp0


def test_default_kwargs_inert():
    env = STS2RunEnv()
    assert env._floor_rewards_by_act is None
    assert env._reward_upgrade == 0.0
    assert env._reward_remove == 0.0
    assert env._reward_elite == 0.0


def test_run_eval_report_deck_histogram():
    from sts2_rl.evaluation import RunEvalReport

    report = RunEvalReport(
        episodes=2, floors=(5, 9), acts=(0, 0), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(10, 12),
        deck_rarity_counts={
            "rare": {"DemonFormCard": 1},
            "common": {"AngerCard": 3, "ArmamentsCard": 1},
            "uncommon": {"InflameCard": 2},
        },
    )
    # Rarity blocks in COMMON/UNCOMMON/RARE order (not the dict's insertion
    # order, not alphabetical); cards descending by copies inside a block.
    assert report.deck_histogram == [
        ("common", "AngerCard", 3, 0.75, 1.5),
        ("common", "ArmamentsCard", 1, 0.25, 0.5),
        ("uncommon", "InflameCard", 2, 1.0, 1.0),
        ("rare", "DemonFormCard", 1, 1.0, 0.5),
    ]

    empty = RunEvalReport(
        episodes=1, floors=(1,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(1,))
    assert empty.deck_histogram == []


def test_deck_histogram_ties_break_on_card_name():
    from sts2_rl.evaluation import RunEvalReport

    report = RunEvalReport(
        episodes=1, floors=(1,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(1,),
        deck_rarity_counts={"common": {"ZzzCard": 2, "AaaCard": 2}},
    )
    assert [row[1] for row in report.deck_histogram] == ["AaaCard", "ZzzCard"]


def test_deck_histogram_zero_episodes_does_not_divide_by_zero():
    from sts2_rl.evaluation import RunEvalReport

    report = RunEvalReport(
        episodes=0, floors=(), acts=(), victories=(), truncations=(),
        hp_left=(), decisions=(),
        deck_rarity_counts={"common": {"AngerCard": 3}},
    )
    assert report.deck_histogram == [("common", "AngerCard", 3, 1.0, 0.0)]


def test_write_deck_csv():
    import io

    from sts2_rl.evaluation import RunEvalReport, write_deck_csv

    report = RunEvalReport(
        episodes=2, floors=(5, 9), acts=(0, 0), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(10, 12),
        deck_rarity_counts={
            # common total is 6 (3+2+1), not a power of 2/5, so BodySlamCard's
            # and ArmamentsCard's shares are repeating decimals -- this pins
            # the round(x, 6) behavior (0.75/0.25-style fixtures can't
            # distinguish round(x, 6) from round(x, 2)).
            "common": {"AngerCard": 3, "ArmamentsCard": 1, "BodySlamCard": 2},
            "rare": {"DemonFormCard": 1},
        },
    )
    buf = io.StringIO()
    write_deck_csv(buf, [("p", report)])
    rows = buf.getvalue().strip().splitlines()
    assert rows[0] == "policy,rarity,card,copies,share_of_rarity,copies_per_run"
    # common total = 6; sorted by copies desc, ties on name.
    assert rows[1] == "p,common,AngerCard,3,0.5,1.5"
    assert rows[2] == "p,common,BodySlamCard,2,0.333333,1.0"
    # 1/6 = 0.1666666...; pins the round(x, 6) precision, not round(x, 2).
    assert rows[3] == "p,common,ArmamentsCard,1,0.166667,0.5"
    assert rows[4] == "p,rare,DemonFormCard,1,1.0,0.5"

    # A report with no census writes the header and nothing else.
    empty = RunEvalReport(
        episodes=1, floors=(1,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(1,))
    buf2 = io.StringIO()
    write_deck_csv(buf2, [("p", empty)])
    assert buf2.getvalue().strip().splitlines() == [
        "policy,rarity,card,copies,share_of_rarity,copies_per_run"]
