"""Run-scale micro-probes — OBS_PLAN phase 3, Task 6 (evaluation rider).

`probes.py` proves numeric grasp inside one combat turn; this module proves
the analogous thing one level up — that a policy makes the single obviously
correct choice at a fixed out-of-combat decision (rest / shop / card
reward), the same way a human would given the exact numbers on screen.

Construction mirrors `probes.py`'s own pattern one layer up: instead of
mutating a `CombatState` after a seeded `env.reset()`, a probe here
overrides `STS2RunEnv._make_run_state()` (the same override point
`curriculum_env.ColumnRunState` uses) with a `RunState` subclass that pins a
single fixed-type room right behind the Ancient node — `curriculum_env.
column_map` already builds exactly this shape for a randomized column, so a
probe just hands it a one-room, one-type tuple instead. `include_neow=False`
skips the Neow event (irrelevant to every probe scenario and, left on,
would be one more branch build() would have to force through). No edit to
run_env.py / driver.py / curriculum_env.py: every override here composes an
existing seam (`_make_run_state`, `RunState._generate_map`, `RunState.
rest_heal_rewards`) or mutates an already-built object post-hoc exactly the
way `probes._build` mutates `CombatState` fields directly.

`build()` still has to clear the single forced hop off the Ancient (the
column's only MAP option) before the env is parked at the probe's actual
target decision — `_drive_forced_map_hop` does that unwind, asserting (not
silently skipping) that it really was forced. Requirement 3's REWARD_CARD
probe additionally forces the REST_HEAL branch to reach the reward screen
(the only ported source of a card-reward decision with no combat needed);
that forced answer is a *build-time* scripted step, never the decision
`check()` scores.

`run_run_probe` does not track `DecisionKind` transitions to find "the
target decision resolved" — some resolutions cross an interstitial kind
(buying a shop's removal entry asks a SELECT_CARDS "which card" sub-decision
before the purchase completes), so kind-tracking would either stop too early
or need a bespoke per-probe kind allowlist. Polling `probe.check(env)` after
every accepted action is the smaller, uniform mechanism the brief asks for:
it is exactly the run-state outcome predicate every probe already needs for
its pass/fail call, so nothing new is invented to also serve as the stop
condition.
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
    # Scenario engineering, not gameplay: price every non-removal slot out of
    # reach so the removal is the only stocked-and-affordable entry —
    # mirrors probes.py's direct post-reset CombatState mutation, applied to
    # the shop object build() already reached instead of re-plumbing
    # MerchantInventory generation. The removal's own cost is left exactly
    # as the source computes it (no jitter on card removal — shop.py's own
    # docstring: "Cost climbs 75 + 25 x removals used").
    for entry in [*inventory.card_entries, *inventory.relic_entries, *inventory.potion_entries]:
        entry._cost = 10 ** 9
    return env


def _removal_bought(env: STS2RunEnv) -> bool:
    # Buying the removal is a two-action purchase: the entry pick lands on an
    # interstitial SELECT_CARDS "which card" sub-decision before the removal
    # actually resolves. Checking card_shop_removals_used alone goes true
    # after just the first action (still mid-purchase), so also require the
    # run to be back at the SHOP decision — i.e. the purchase fully resolved
    # — without adding kind-tracking to the shared `run_run_probe` runner
    # (see module docstring on why that stays out of the runner itself).
    request = getattr(env, "_request", None)
    at_shop = request is not None and request.kind == DecisionKind.SHOP
    return at_shop and env._run.card_shop_removals_used >= 1


# ── Probe (c): card reward, one on-curve pick vs traps ─────────────────────

REWARD_ON_CURVE_ID = "iron_wave"
REWARD_TRAP_IDS = ("clash", "bloodletting")


def _build_card_reward() -> _RunProbeEnv:
    env = _RunProbeEnv(
        room_type=MapPointType.REST_SITE,
        run_state_cls=_FixedRewardRunState,
        run_kwargs=dict(
            hp=REST_MAX_HP - 10,
            max_hp=REST_MAX_HP,
            reward_card_ids=(REWARD_ON_CURVE_ID, *REWARD_TRAP_IDS),
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
        "Exactly 75 gold at a shop where every other slot is priced out: "
        "buy the removal — it is the only stocked, affordable purchase.",
        _build_shop_removal,
        _removal_bought,
    ),
    RunProbe(
        "card_reward_on_curve",
        "A pinned 3-card reward (iron_wave vs clash/bloodletting): take the "
        "on-curve pick, not a trap.",
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
