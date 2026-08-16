"""Run-scale micro-probes — OBS_PLAN phase 3, Task 6 (evaluation rider).

`probes.py` proves numeric grasp inside one combat turn; this module proves
the analogous thing one level up: a policy makes the single obviously
correct choice at a fixed out-of-combat decision (rest / shop / card
reward).

Construction mirrors `probes.py` one layer up: instead of mutating a
`CombatState` after a seeded `env.reset()`, a probe overrides
`STS2RunEnv._make_run_state()` (same override point as
`curriculum_env.ColumnRunState`) with a `RunState` subclass pinning a
single fixed-type room right behind the Ancient node, reusing
`curriculum_env.column_map`. `include_neow=False` skips the irrelevant
Neow event. Every override here composes an existing seam
(`_make_run_state`, `RunState._generate_map`, `RunState.rest_heal_rewards`)
or mutates an already-built object post-hoc, same as `probes._build`.

`build()` clears the single forced MAP hop off the Ancient before parking
at the probe's target decision — `_drive_forced_map_hop` asserts (not
silently skips) that it really was forced. The REWARD_CARD probe
additionally forces the REST_HEAL branch to reach the reward screen; that
forced step is build-time scripting, never the decision `check()` scores.

`run_run_probe` polls `probe.check(env)` after every accepted action rather
than tracking `DecisionKind` transitions, because some resolutions cross an
interstitial kind (buying shop removal asks a SELECT_CARDS sub-decision
first) that kind-tracking would mishandle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .actmap import MapPointType, OVERGROWTH_MAP
from .cards import make_card
from .curriculum_env import column_map
from .driver import DecisionKind
from .rewards import CardRewardGroup, CombatRewards
from .rooms import RoomType
from .run import RunState
from .run_env import CHOICE_BASE, STS2RunEnv

# A policy is any callable (env, obs, mask) -> action int (see evaluation.py),
# same contract probes.py and evaluation.TorchPolicy already share.
Policy = Callable[..., int]


# ── Fixed-map RunState (the `_make_run_state` override point) ───────────────


class _FixedRoomRunState(RunState):
    """A RunState whose act map is ONE room of a chosen type, directly behind
    the Ancient node — `curriculum_env.column_map` already builds exactly
    this shape for a randomized column; a probe just pins a one-entry type
    tuple. Composes the same override point `ColumnRunState` does
    (`_generate_map`), nothing new."""

    def __init__(self, room_type: MapPointType, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._probe_room_type = room_type

    def _generate_map(self):
        config = self.act_config or OVERGROWTH_MAP
        return column_map(self.rng, config, types=(self._probe_room_type,))


class _FixedRewardRunState(_FixedRoomRunState):
    """A `_FixedRoomRunState` whose rest-site heal reward screen is a pinned
    3-card offer instead of Dream Catcher's RNG-drawn one — composes
    `RunState.rest_heal_rewards`, an existing override point (`rest_heal_
    rewards`'s own docstring: "the caller ... offers it the same way it
    offers post-combat rewards"), no relic/RNG plumbing needed."""

    def __init__(self, room_type: MapPointType, reward_card_ids: Sequence[str], **kwargs: Any) -> None:
        super().__init__(room_type, **kwargs)
        self._reward_card_ids = tuple(reward_card_ids)

    def rest_heal_rewards(self) -> CombatRewards:
        cards = [make_card(cid) for cid in self._reward_card_ids]
        group = CardRewardGroup(cards=cards, room_type=RoomType.MONSTER, populated=True)
        return CombatRewards(room_type=RoomType.MONSTER, card_rewards=[group])


class _RunProbeEnv(STS2RunEnv):
    """STS2RunEnv parked, after `reset()` + the forced Ancient hop, at a
    single fixed-type room. Only the RunState factory differs (matches
    `STS2CurriculumRunEnv`'s own relationship to its parent) — observation/
    action layout and RUN_OBS_SCHEMA_VERSION are untouched."""

    def __init__(self, *, room_type: MapPointType, run_state_cls: type = _FixedRoomRunState,
                 run_kwargs: dict | None = None, **kwargs: Any) -> None:
        super().__init__(include_neow=False, acts=["overgrowth"], **kwargs)
        self._room_type = room_type
        self._run_state_cls = run_state_cls
        self._run_kwargs = dict(run_kwargs or {})

    def _make_run_state(self) -> RunState:
        return self._run_state_cls(
            self._room_type, rng=self._rng, character=self._character, **self._run_kwargs
        )


def _drive_forced_map_hop(env: STS2RunEnv, max_hops: int = 4) -> None:
    """Unwind the column's own forced, single-option MAP screens (the hop off
    the Ancient onto the probe's one room). NOT a policy decision under test
    — `own_actions()` having exactly one entry is asserted, not assumed, so a
    map shape that stopped being forced would fail loudly here instead of
    silently answering on the probed policy's behalf."""
    for _ in range(max_hops):
        request = env._request
        if request is None or request.kind != DecisionKind.MAP:
            return
        legal = request.own_actions()
        if len(legal) != 1:
            raise AssertionError(
                f"run_probes expected a single forced MAP hop, got {legal!r}"
            )
        env.step(CHOICE_BASE + legal[0])
    raise AssertionError("forced MAP hop did not resolve within bound")


# ── Probe (a): REST at critically low HP ─────────────────────────────────

REST_LOW_HP = 8
REST_MAX_HP = 80


def _build_rest_low_hp() -> _RunProbeEnv:
    env = _RunProbeEnv(
        room_type=MapPointType.REST_SITE,
        run_kwargs=dict(hp=REST_LOW_HP, max_hp=REST_MAX_HP),
    )
    env.reset(seed=0)
    _drive_forced_map_hop(env)
    request = env._request
    assert request is not None and request.kind == DecisionKind.REST, (
        f"run_probes: expected a REST decision, got {request!r}"
    )
    return env


def _rested_and_healed(env: STS2RunEnv) -> bool:
    run = env._run
    return run.hp > REST_LOW_HP


# ── Probe (b): shop with exactly enough gold for the dominant removal ──────

# MerchantCardRemovalEntry.BASE_COST — the first-visit removal price
# (75 + 25 * removals_used, removals_used == 0 on a fresh run).
SHOP_REMOVAL_GOLD = 75
# A cheap, deliberately-wrong purchase left affordable at all_entries[0] (the
# first `card_entries` slot — always index 0, strictly below the removal's
# index: MerchantInventory.all_entries appends card_removal_entry LAST, so
# the removal is never the lowest-indexed legal action here). Priced so
# SHOP_TRAP_GOLD + SHOP_REMOVAL_GOLD > SHOP_REMOVAL_GOLD's own gold budget —
# buying the trap first permanently prices the removal out, defeating a
# lowest-legal-index (argmin) policy without making the probe unsolvable for
# a policy that reads the screen (the oracle skips straight to the removal).
SHOP_TRAP_GOLD = 40


def _build_shop_removal() -> _RunProbeEnv:
    env = _RunProbeEnv(
        room_type=MapPointType.SHOP,
        run_kwargs=dict(gold=SHOP_REMOVAL_GOLD),
    )
    env.reset(seed=0)
    _drive_forced_map_hop(env)
    request = env._request
    assert request is not None and request.kind == DecisionKind.SHOP, (
        f"run_probes: expected a SHOP decision, got {request!r}"
    )
    inventory = request.shop
    removal = inventory.card_removal_entry
    trap = inventory.card_entries[0]
    assert inventory.all_entries[-1] is removal, (
        "run_probes: expected the removal entry last in all_entries"
    )
    assert inventory.all_entries[0] is trap, (
        "run_probes: expected a card entry first in all_entries"
    )
    # Price every slot but the trap and the removal out of reach. Removal's
    # own cost is left as the source computes it (shop.py: "Cost climbs 75 +
    # 25 x removals used").
    for entry in inventory.all_entries:
        if entry is removal:
            continue
        entry._cost = 10 ** 9
    trap._cost = SHOP_TRAP_GOLD
    return env


def _removal_bought(env: STS2RunEnv) -> bool:
    # Buying the removal is a two-action purchase (entry pick -> interstitial
    # SELECT_CARDS sub-decision -> resolve), so also require being back at
    # SHOP to confirm it fully resolved, not just started.
    # `gold == 0` confirms the trap (cheaper, lower action index) was never
    # bought: starting gold == SHOP_REMOVAL_GOLD, so only spending it all on
    # the removal reaches 0.
    request = getattr(env, "_request", None)
    at_shop = request is not None and request.kind == DecisionKind.SHOP
    return (
        at_shop
        and env._run.card_shop_removals_used >= 1
        and env._run.gold == 0
    )


# ── Probe (c): card reward, one on-curve pick vs traps ─────────────────────

REWARD_ON_CURVE_ID = "iron_wave"
REWARD_TRAP_IDS = ("clash", "bloodletting")
# Offer order == action index order (CombatRewards.cards is a plain list
# view onto CardRewardGroup.cards, own_actions() is range(n+1) over it — no
# shuffle anywhere in between; verified empirically, see the report), so
# pinning `iron_wave` in the MIDDLE of this tuple keeps its correct action
# index (1) away from both extremes a constant-index policy could exploit.
REWARD_OFFER_IDS = (REWARD_TRAP_IDS[0], REWARD_ON_CURVE_ID, REWARD_TRAP_IDS[1])


def _build_card_reward() -> _RunProbeEnv:
    env = _RunProbeEnv(
        room_type=MapPointType.REST_SITE,
        run_state_cls=_FixedRewardRunState,
        run_kwargs=dict(
            hp=REST_MAX_HP - 10,
            max_hp=REST_MAX_HP,
            reward_card_ids=REWARD_OFFER_IDS,
        ),
    )
    env.reset(seed=0)
    _drive_forced_map_hop(env)
    request = env._request
    assert request is not None and request.kind == DecisionKind.REST, (
        f"run_probes: expected a REST decision, got {request!r}"
    )
    # Force the heal branch (build-time only — never the probed decision) to
    # reach the pinned card-reward screen behind it; see module docstring.
    env.step(CHOICE_BASE + 0)
    request = env._request
    assert request is not None and request.kind == DecisionKind.REWARD_CARD, (
        f"run_probes: expected a REWARD_CARD decision, got {request!r}"
    )
    ids = [c.id for c in request.rewards.cards]
    assert ids == list(REWARD_OFFER_IDS), (
        f"run_probes: expected the reward offer in tuple order, got {ids!r}"
    )
    return env


def _on_curve_card_added(env: STS2RunEnv) -> bool:
    ids = [c.id for c in env._run.deck]
    return REWARD_ON_CURVE_ID in ids and not any(t in ids for t in REWARD_TRAP_IDS)


# ── Probe table + runner ─────────────────────────────────────────────────


@dataclass(frozen=True)
class RunProbe:
    id: str
    description: str
    build: Callable[[], Any]
    check: Callable[[Any], bool]


RUN_PROBES: tuple[RunProbe, ...] = (
    RunProbe(
        "rest_at_low_hp",
        "8/80 HP at a rest site: heal — the alternative (leave/smith) walks "
        "back onto the map still critically low.",
        _build_rest_low_hp,
        _rested_and_healed,
    ),
    RunProbe(
        "shop_removal_dominant",
        "Exactly 75 gold at a shop where a cheap (40g) card is affordable at "
        "a LOWER action index than the removal and every other slot is "
        "priced out: buy the removal, not the cheap card — the two together "
        "cost more than the 75g on hand, so grabbing the cheap card first "
        "permanently prices the removal out.",
        _build_shop_removal,
        _removal_bought,
    ),
    RunProbe(
        "card_reward_on_curve",
        "A pinned 3-card reward with the on-curve pick in the MIDDLE slot "
        "(clash, iron_wave, bloodletting): take iron_wave, not a trap at "
        "either end.",
        _build_card_reward,
        _on_curve_card_added,
    ),
)


def run_run_probe(probe: RunProbe, policy: Policy, max_actions: int = 40) -> bool:
    """Let `policy` answer decisions from `probe.build()`'s parked env until
    `probe.check(env)` reads true, bounded by `max_actions`. Fails outright
    on an illegal action; fails by exhausting the bound if the check never
    reads true (mirrors `probes.run_probe`'s "never ends the turn" failure,
    one level up: here there is no single "turn" boundary common to every
    screen shape, so the outcome predicate itself is the stop condition)."""
    env = probe.build()
    for _ in range(max_actions):
        request = getattr(env, "_request", None)
        if request is None:
            break
        obs = env._build_obs()
        mask = env.action_masks()
        action = int(policy(env, obs, mask))
        if not mask[action]:
            return False
        env.step(action)
        if probe.check(env):
            return True
    return bool(probe.check(env))


def run_run_probes(policy: Policy, probes: Sequence[RunProbe] | None = None) -> list[bool]:
    return [run_run_probe(p, policy) for p in (RUN_PROBES if probes is None else probes)]


def run_probe_accuracy(policy: Policy, probes: Sequence[RunProbe] | None = None) -> float:
    results = run_run_probes(policy, probes)
    return sum(results) / len(results) if results else 0.0
