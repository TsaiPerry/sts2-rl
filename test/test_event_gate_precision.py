"""Event-gate arithmetic and Dense Vegetation's rest-site heal, vs the source
(UnrestSite.cs, DenseVegetation.cs -> PlayerCmd.cs -> HealRestSiteOption.cs).

Covers audit/GAP-QUEUE.md entries 4 (`event/unrest_site/IsAllowed`) and 44
(`creature_card_cmds/step38a`)."""
import random

import pytest

from sts2_rl.events.dense_vegetation import DenseVegetation
from sts2_rl.events.unrest_site import UnrestSite
from sts2_rl.relics import make_relic
from sts2_rl.run import RunState


def fresh_run(seed=0, **kwargs):
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# Unrest Site's IsAllowed gate (UnrestSite.cs:28)
# ═════════════════════════════════════════════════════════════════════════

# The (max_hp, hp) pairs where hp is EXACTLY 70% of max_hp and binary float
# lands just under it -- e.g. 90 * 0.70 == 62.99999999999999, while the
# game's 90m * 0.70m is exactly 63.00m. Swept over every pair with
# max_hp <= 400 (audit/tools/event_probes_b.py gate): these seven, and only
# these seven, disagreed.
EXACTLY_SEVENTY_PERCENT = [
    (90, 63),
    (170, 119),
    (180, 126),
    (330, 231),
    (340, 238),
    (350, 245),
    (360, 252),
]


@pytest.mark.parametrize("max_hp,hp", EXACTLY_SEVENTY_PERCENT)
def test_unrest_site_allowed_at_exactly_seventy_percent(max_hp, hp):
    """UnrestSite.cs:28 compares in `decimal`, so HP at exactly 70% of max
    passes the `<=`. A binary-float `max_hp * 0.70` refuses these seven."""
    run = fresh_run()
    run.max_hp = max_hp
    run.hp = hp
    assert UnrestSite.is_allowed(run) is True


@pytest.mark.parametrize("max_hp,hp", EXACTLY_SEVENTY_PERCENT)
def test_unrest_site_refused_one_hp_above_the_gate(max_hp, hp):
    """One HP over exactly 70% is still over: the gate is `<=`, not `<`."""
    run = fresh_run()
    run.max_hp = max_hp
    run.hp = hp + 1
    assert UnrestSite.is_allowed(run) is False


def test_unrest_site_gate_agrees_with_decimal_over_the_whole_sweep():
    """Rule 5: the representation must not move the gate anywhere."""
    from decimal import Decimal

    for max_hp in range(1, 401):
        threshold = Decimal(max_hp) * Decimal("0.70")
        for hp in range(0, max_hp + 1):
            run = fresh_run()
            run.max_hp = max_hp
            run.hp = hp
            assert UnrestSite.is_allowed(run) is (Decimal(hp) <= threshold), (
                f"max_hp={max_hp} hp={hp}"
            )


# ═════════════════════════════════════════════════════════════════════════
# Dense Vegetation's Rest option (DenseVegetation.cs:90)
# ═════════════════════════════════════════════════════════════════════════

def _rest_option(run):
    event = DenseVegetation(run).begin()
    return event, next(o for o in event.options if o.key == "REST")


def test_dense_vegetation_rest_fires_after_rest_site_heal():
    """PlayerCmd.MimicRestSiteHeal -> HealRestSiteOption.ExecuteRestSiteHeal
    fires Hook.AfterRestSiteHeal after the heal, so Stone Humidifier's
    +5 Max HP lands on Dense Vegetation's Rest."""
    run = fresh_run(14)
    run.add_relic(make_relic("stone_humidifier"))
    run.hp = 40
    before_max = run.max_hp
    _, rest = _rest_option(run)
    rest.on_chosen()
    assert run.max_hp == before_max + 5
    # 30% of 80 healed, then GainMaxHp heals its 5 too.
    assert run.hp == 40 + 24 + 5


def test_dense_vegetation_rest_builds_the_heal_rewards():
    """...and then Hook.ModifyRestSiteHealRewards, which is what BUILDS Dream
    Catcher's 3-card choice. That the driver then offers it is
    test_driver.py::test_mimicked_rest_heal_offers_its_rewards_too."""
    run = fresh_run(16)
    run.add_relic(make_relic("dream_catcher"))
    event, rest = _rest_option(run)
    rest.on_chosen()
    assert event.pending_rewards is not None
    assert len(event.pending_rewards.cards) == 3


def test_dense_vegetation_rest_rewards_are_empty_without_a_listener():
    run = fresh_run(16)
    event, rest = _rest_option(run)
    rest.on_chosen()
    assert event.pending_rewards is not None
    assert event.pending_rewards.is_empty


def test_dense_vegetation_rest_still_leads_to_the_ambush():
    run = fresh_run(16)
    event, rest = _rest_option(run)
    rest.on_chosen()
    assert event.page == "REST"
    assert event.option_keys() == ["FIGHT"]
