"""STS2RunEnv — the full-run Gymnasium environment (a complete game run).

The engine side is `driver.py`'s RunDriver: the whole run written as plain
synchronous code that calls ``ask(DecisionRequest) -> int`` at every decision.
This env runs the driver on a **greenlet**; ``ask`` switches back to the env,
so every decision — map path, Neow/event options, shop purchases, rest
choices, post-combat reward picks, every combat action, and every
mid-resolution card selection (RL.md's "two-phase env") — surfaces as one
masked Gym step, fully on-policy.

Action space (flat Discrete, three blocks):

  [0 .. N_COMBAT)                combat block — identical semantics to
                                 STS2FullCombatEnv (end turn / play h@e /
                                 potion p@e), sized for MAX_POTION_SLOTS=4
                                 belts (Phial Holster): 61 + 4×6 = 85
  [CHOICE_BASE .. +CHOICE_SLOTS) generic choice slots: the i-th option of the
                                 current MAP / EVENT / SHOP / REST /
                                 REWARD_* / SELECT_OPTION decision (shop slot
                                 12 = leave, reward slot len(cards) = skip …
                                 exactly DecisionRequest.legal_actions()).
                                 During a skippable SELECT_CARDS, slot 0 =
                                 skip.
  [SELECT_BASE .. +2·N_CARDS)    select-by-card block: pick the candidate
                                 with (card id, upgraded) — pair 2i = base
                                 copy of CARD_IDS[i], 2i+1 = upgraded. The
                                 driver receives the FIRST matching
                                 candidate (copies differing only by
                                 enchantment/cost modifiers are collapsed —
                                 documented approximation).

Observation (flat Box, probe-verified at construction): a run block (phase
one-hot, vitals, gold, act/floor, potion belt, deck histogram, relic
presence), phase-specific blocks (map slots with 1-ply lookahead, event
identity+option slots, shop stock with prices/affordability, reward slots,
select purpose+candidate histogram), then the full combat block of
full_env.build_combat_obs (zeroed outside combat). Conventions follow
OBS_PLAN: shared /100+/500 absolute unit, named segments (run_obs_segments /
run_obs_slices), sorted vocabularies (CARD_IDS/…/RELIC_IDS/EVENT_IDS/
PURPOSE_IDS).

Reward (configurable): per-step run-HP delta, small floor/act progress
bonuses, terminal win/loss (+ optional HP-conserved bonus). info carries
floor/act/phase and, at episode end, is_success + hp_left.
"""
from __future__ import annotations

import random
from typing import Any, Callable

import greenlet
import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .actmap import MapPointType
from .combat import CombatState
from .driver import DecisionKind, DecisionRequest, RunDriver, RunResult
from .events import ALL_EVENTS
from .full_env import (
    CARD_IDS,
    CARD_INDEX,
    N_CARDS,
    N_POTIONS,
    POTION_INDEX,
    _abs2,
    _clip01,
    build_combat_obs,
    combat_action_count,
    pile_composition,
)
from .relics import ALL_RELICS
from .run import RunState
from .vocab import capacity as vocab_capacity, frozen_ids

# Bump whenever the run-observation layout or action layout changes (any
# change invalidates saved run-env models — retrain). v2: capacity-padded
# frozen vocabularies (vocab.py) — dims are reserved capacities, so future
# content additions no longer bump this. v3: the shop's Colorless section
# (SHOP_CARD_SLOTS 5 → 7, shifting the relic/potion/removal segments and
# the SHOP decision's entry indices).
RUN_OBS_SCHEMA_VERSION = 3

# ── Fixed-size bounds ────────────────────────────────────────────────────
# Potion belt headroom: base 3 slots + Phial Holster's +1.
MAX_POTION_SLOTS = 4
# Generic choice slots. Must cover every non-combat, non-select decision's
# option count: map rows are ≤7 wide (free travel), shops have 14 entries
# (5 character + 2 Colorless cards, 3 relics, 3 potions, removal) + leave,
# events assert ≤ CHOICE_SLOTS options at mask time.
CHOICE_SLOTS = 16
# Map row width (7-wide grid) — the most travel options free travel allows.
MAP_SLOTS = 7
# Shop stock layout (MerchantInventory.all_entries order): 5 character card
# slots followed by the 2 Colorless slots (Uncommon, Rare).
SHOP_CARD_SLOTS = 7
SHOP_RELIC_SLOTS = 3
SHOP_POTION_SLOTS = 3
# Reward screen card choices (RewardsSet: always 3).
REWARD_CARD_SLOTS = 3

# ── Action layout ────────────────────────────────────────────────────────
N_COMBAT_ACTIONS = combat_action_count(MAX_POTION_SLOTS)      # 85
CHOICE_BASE = N_COMBAT_ACTIONS
SELECT_BASE = CHOICE_BASE + CHOICE_SLOTS
N_ACTIONS = SELECT_BASE + 2 * N_CARDS

# ── Stable vocabularies (frozen append-only + capacity-padded; vocab.py) ──
RELIC_IDS: list[str] = frozen_ids("relics", ALL_RELICS)
RELIC_INDEX: dict[str, int] = {rid: i for i, rid in enumerate(RELIC_IDS)}
N_RELICS = vocab_capacity("relics")

EVENT_IDS: list[str] = frozen_ids("events", ALL_EVENTS)
EVENT_INDEX: dict[str, int] = {eid: i for i, eid in enumerate(EVENT_IDS)}
N_EVENTS = vocab_capacity("events")

# Every select_cards / select_option purpose in the engine (collected from
# the source; unknown future purposes land in the "_unknown" bucket until
# added here — the frozen registry pins each purpose's index once seen).
PURPOSE_IDS: list[str] = frozen_ids("purposes", [
    "bundle", "card_reward", "curse_of_knowledge", "duplicate", "enchant",
    "exhaust", "from_discard", "from_draw", "gambling_chip", "obtain",
    "remove", "to_draw_top", "transform", "upgrade", "_unknown",
])
PURPOSE_INDEX: dict[str, int] = {p: i for i, p in enumerate(PURPOSE_IDS)}
N_PURPOSES = vocab_capacity("purposes")

# Phase vocabulary = DecisionKind in declaration order.
PHASES: list[DecisionKind] = list(DecisionKind)
PHASE_INDEX: dict[DecisionKind, int] = {k: i for i, k in enumerate(PHASES)}
N_PHASES = len(PHASES)

_POINT_TYPES = list(MapPointType)
_N_POINT_TYPES = len(_POINT_TYPES)
_POINT_TYPE_INDEX = {t: i for i, t in enumerate(_POINT_TYPES)}

# Cost scale for shop prices (removal climbs 75+25k; relics ~316 max).
_COST_SCALE = 500.0

_N_ACTS = 3   # act-index one-hot width (the game's 3-act run)


def run_obs_segments(card_obs: str = "hybrid") -> list[tuple[str, int]]:
    """The run observation as an ordered (segment name, width) list. The
    trailing "combat" segment's width depends on the combat schema and is
    probe-measured at env construction — here it is a placeholder of width
    0; STS2RunEnv.obs_segments() fills it in."""
    segs: list[tuple[str, int]] = [
        ("phase", N_PHASES),
        ("run.hp_ratio", 1),
        ("run.hp_abs", 2),
        ("run.max_hp_abs", 2),
        ("run.gold", 2),
        ("run.act", _N_ACTS),
        ("run.floor", 1),
    ]
    for p in range(MAX_POTION_SLOTS):
        segs.append((f"run.potion{p}", 1 + N_POTIONS + 1))
    segs.append(("run.deck", 2 * N_CARDS))
    segs.append(("run.relics", N_RELICS))
    for m in range(MAP_SLOTS):
        segs.append((f"map{m}", 1 + _N_POINT_TYPES + _N_POINT_TYPES))
    segs.extend([
        ("event.present", 1),
        ("event.identity", N_EVENTS),
        ("event.page", 1),
        ("event.options", 2 * CHOICE_SLOTS),
    ])
    for c in range(SHOP_CARD_SLOTS):
        segs.append((f"shop.card{c}", 1 + N_CARDS + 3))
    for r in range(SHOP_RELIC_SLOTS):
        segs.append((f"shop.relic{r}", 1 + N_RELICS + 2))
    for p in range(SHOP_POTION_SLOTS):
        segs.append((f"shop.potion{p}", 1 + N_POTIONS + 2))
    segs.append(("shop.removal", 3))
    for c in range(REWARD_CARD_SLOTS):
        segs.append((f"reward.card{c}", 1 + N_CARDS + 1))
    segs.append(("reward.potion", 1 + N_POTIONS))
    segs.extend([
        ("select.purpose", N_PURPOSES),
        ("select.count", 1),
        ("select.skippable", 1),
        ("select.candidates", 2 * N_CARDS),
    ])
    return segs


def run_obs_slices(card_obs: str = "hybrid") -> dict[str, slice]:
    """Segment name → slice into the flat run observation (combat excluded;
    the combat block occupies everything past the last run segment)."""
    out: dict[str, slice] = {}
    i = 0
    for name, width in run_obs_segments(card_obs):
        out[name] = slice(i, i + width)
        i += width
    return out


class STS2RunEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        *,
        acts: list[str] | None = None,
        ascension: int = 0,
        include_neow: bool = True,
        card_obs: str = "hybrid",
        reward_win: float = 1.0,
        reward_loss: float = 0.0,
        win_hp_bonus: float = 0.0,
        hp_reward_scale: float = 1.0,
        floor_reward: float = 0.02,
        act_reward: float = 0.25,
        max_steps: int = 10_000,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        if card_obs not in ("hybrid", "features"):
            raise ValueError("card_obs must be 'hybrid' or 'features'")
        self._acts = list(acts) if acts is not None else None
        self._ascension = ascension
        self._include_neow = include_neow
        self._card_obs = card_obs
        self._reward_win = reward_win
        self._reward_loss = reward_loss
        self._win_hp_bonus = win_hp_bonus
        self._hp_reward_scale = hp_reward_scale
        self._floor_reward = floor_reward
        self._act_reward = act_reward
        self._max_steps = max_steps
        self.render_mode = render_mode

        self.n_actions = N_ACTIONS
        self.action_space = spaces.Discrete(self.n_actions)

        # Combat block width, probe-measured so it can never drift from
        # build_combat_obs (same pattern as STS2FullCombatEnv).
        probe = CombatState(rng=random.Random(0))
        self._combat_obs_dim = len(build_combat_obs(probe, card_obs))
        self._run_obs_dim = sum(w for _, w in run_obs_segments(card_obs))
        obs_dim = self._run_obs_dim + self._combat_obs_dim
        self.observation_space = spaces.Box(0.0, 1.0, shape=(obs_dim,), dtype=np.float32)

        self._rng = random.Random()
        self._run: RunState | None = None
        self._glet: greenlet.greenlet | None = None
        self._request: DecisionRequest | None = None
        self._result: RunResult | None = None
        self._steps = 0

    # ------------------------------------------------------------------
    # Named layout (pin tests)
    # ------------------------------------------------------------------

    def obs_segments(self) -> list[tuple[str, int]]:
        """run_obs_segments plus the probe-measured combat block."""
        return run_obs_segments(self._card_obs) + [("combat", self._combat_obs_dim)]

    def obs_slices(self) -> dict[str, slice]:
        out = run_obs_slices(self._card_obs)
        out["combat"] = slice(self._run_obs_dim, self._run_obs_dim + self._combat_obs_dim)
        return out

    # ------------------------------------------------------------------
    # Greenlet plumbing
    # ------------------------------------------------------------------

    def _kill_driver(self) -> None:
        if self._glet is not None and not self._glet.dead:
            self._glet.throw(greenlet.GreenletExit)
        self._glet = None

    def _deliver(self, request: DecisionRequest) -> int:
        """RunDriver's ask callback — runs INSIDE the driver greenlet: hand
        the request to the env greenlet and park until step() answers."""
        return greenlet.getcurrent().parent.switch(request)

    def _switch(self, value: Any) -> None:
        """Resume the driver greenlet; it returns either the next
        DecisionRequest (parked in _deliver) or the RunResult (finished)."""
        out = self._glet.switch(value)
        if isinstance(out, RunResult):
            self._result = out
            self._request = None
        elif isinstance(out, DecisionRequest):
            self._request = out
        elif self._glet.dead:
            # GreenletExit during teardown lands here; treat as terminal.
            self._request = None
        else:  # pragma: no cover - driver protocol violation
            raise AssertionError(f"unexpected switch value: {out!r}")

    # ------------------------------------------------------------------
    # gym interface
    # ------------------------------------------------------------------

    def _make_run_state(self) -> RunState:
        """Build the RunState the driver plays. Curriculum envs override this
        to install a RunState subclass (e.g. curriculum_env.ColumnRunState)."""
        return RunState(rng=self._rng)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self._kill_driver()
        if seed is not None:
            self._rng = random.Random(seed)
        self._run = self._make_run_state()
        self._result = None
        self._steps = 0

        run = self._run

        def _drive(*_ignored) -> RunResult:
            # greenlet passes the first switch()'s argument into the target;
            # the kickoff value is meaningless here.
            driver = RunDriver(
                run,
                self._deliver,
                acts=self._acts,
                ascension=self._ascension,
                include_neow=self._include_neow,
            )
            return driver.play()

        self._glet = greenlet.greenlet(_drive)
        self._switch(None)   # run until the first decision
        return self._build_obs(), self._info()

    def step(self, action: int):
        assert self._run is not None, "call reset() before step()"
        run = self._run
        request = self._request
        self._steps += 1

        if request is not None:
            answer = self._translate(int(action), request)
            if answer is None:
                # Illegal action: a no-op step (mirrors full_env semantics).
                return self._build_obs(), 0.0, False, self._steps >= self._max_steps, self._info()
            hp_before = run.hp
            floor_before = run.total_floor
            act_before = run.act_index
            self._switch(answer)
        else:
            hp_before, floor_before, act_before = run.hp, run.total_floor, run.act_index

        reward = self._hp_reward_scale * (min(run.hp, run.max_hp) - min(hp_before, run.max_hp)) / max(1, run.max_hp)
        reward += self._floor_reward * (run.total_floor - floor_before)
        reward += self._act_reward * (run.act_index - act_before)

        terminated = self._result is not None
        if terminated:
            if self._result.victory:
                reward += self._reward_win + self._win_hp_bonus * (
                    self._result.hp / max(1, self._result.max_hp)
                )
            else:
                reward += self._reward_loss
        truncated = (not terminated) and self._steps >= self._max_steps

        return self._build_obs(), float(reward), terminated, truncated, self._info()

    def close(self) -> None:
        self._kill_driver()
        super().close()

    # ------------------------------------------------------------------
    # Action translation / masking
    # ------------------------------------------------------------------

    def _translate(self, action: int, request: DecisionRequest) -> int | None:
        """Env action → the driver's answer for the pending request; None if
        the action is illegal for the current phase."""
        kind = request.kind
        legal = request.legal_actions()
        if kind == DecisionKind.COMBAT:
            return action if action < N_COMBAT_ACTIONS and action in legal else None
        if kind == DecisionKind.SELECT_CARDS:
            if request.skippable and action == CHOICE_BASE:
                return len(request.candidates)
            # len(CARD_IDS), not N_CARDS: actions in the reserved-capacity
            # tail decode to no card and fall through to illegal (None).
            if SELECT_BASE <= action < SELECT_BASE + 2 * len(CARD_IDS):
                pair = action - SELECT_BASE
                cid = CARD_IDS[pair // 2]
                upgraded = pair % 2 == 1
                for i, card in enumerate(request.candidates):
                    if card.id == cid and (card.upgrade_level > 0) == upgraded:
                        return i
            return None
        # Every other kind answers with a generic choice-slot index.
        if CHOICE_BASE <= action < CHOICE_BASE + CHOICE_SLOTS:
            answer = action - CHOICE_BASE
            return answer if answer in legal else None
        return None

    def action_masks(self) -> np.ndarray:
        mask = np.zeros(self.n_actions, dtype=bool)
        request = self._request
        if request is None:
            mask[0] = True   # terminal/truncated: one harmless no-op
            return mask
        kind = request.kind
        legal = request.legal_actions()
        if kind == DecisionKind.COMBAT:
            mask[legal] = True
        elif kind == DecisionKind.SELECT_CARDS:
            for card in request.candidates:
                pair = 2 * CARD_INDEX[card.id] + (1 if card.upgrade_level > 0 else 0)
                mask[SELECT_BASE + pair] = True
            if request.skippable:
                mask[CHOICE_BASE] = True
        else:
            assert max(legal) < CHOICE_SLOTS, (
                f"{kind} offered {max(legal) + 1} options; grow CHOICE_SLOTS"
            )
            for i in legal:
                mask[CHOICE_BASE + i] = True
        assert mask.any()
        return mask

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def _build_obs(self) -> np.ndarray:
        run = self._run
        request = self._request
        o: list[float] = []

        # ── Phase one-hot (all zero at terminal) ─────────────────────────
        phase = [0.0] * N_PHASES
        if request is not None:
            phase[PHASE_INDEX[request.kind]] = 1.0
        o.extend(phase)

        # ── Run vitals ───────────────────────────────────────────────────
        hp = max(0, run.hp)
        o.append(_clip01(hp / max(1, run.max_hp)))
        o.extend(_abs2(hp))
        o.extend(_abs2(run.max_hp))
        o.append(_clip01(run.gold / 100.0))
        o.append(_clip01(run.gold / 1000.0))
        act = [0.0] * _N_ACTS
        if 0 <= run.act_index < _N_ACTS:
            act[run.act_index] = 1.0
        o.extend(act)
        o.append(_clip01(run.total_floor / 50.0))

        # ── Potion belt (run-level; combat exposes its own rows too) ─────
        for p in range(MAX_POTION_SLOTS):
            potion = run.potions[p] if p < len(run.potions) else None
            o.append(1.0 if potion is not None else 0.0)
            hot = [0.0] * N_POTIONS
            if potion is not None:
                hot[POTION_INDEX[potion.id]] = 1.0
            o.extend(hot)
            o.append(1.0 if p < run.max_potions else 0.0)   # slot exists

        # ── Deck histogram + relic presence ──────────────────────────────
        o.extend(pile_composition(run.deck))
        relics = [0.0] * N_RELICS
        for relic in run.relics:
            idx = RELIC_INDEX.get(relic.id)
            if idx is not None:
                relics[idx] = 1.0
        o.extend(relics)

        # ── Map block (filled during MAP; slots align with choice slots) ─
        points = request.points if request is not None and request.kind == DecisionKind.MAP else []
        for m in range(MAP_SLOTS):
            point = points[m] if m < len(points) else None
            o.append(1.0 if point is not None else 0.0)
            type_hot = [0.0] * _N_POINT_TYPES
            child_hist = [0.0] * _N_POINT_TYPES
            if point is not None:
                type_hot[_POINT_TYPE_INDEX[point.point_type]] = 1.0
                for child in point.children:
                    child_hist[_POINT_TYPE_INDEX[child.point_type]] += 1.0
                child_hist = [_clip01(c / 3.0) for c in child_hist]
            o.extend(type_hot)
            o.extend(child_hist)

        # ── Event block ──────────────────────────────────────────────────
        event = request.event if request is not None and request.kind == DecisionKind.EVENT else None
        o.append(1.0 if event is not None else 0.0)
        hot = [0.0] * N_EVENTS
        if event is not None:
            idx = EVENT_INDEX.get(event.id)
            if idx is not None:
                hot[idx] = 1.0
        o.extend(hot)
        o.append(1.0 if (event is not None and event.page != "INITIAL") else 0.0)
        opts = event.options if event is not None else []
        for i in range(CHOICE_SLOTS):
            if i < len(opts):
                o.append(1.0)
                o.append(1.0 if opts[i].locked else 0.0)
            else:
                o.extend((0.0, 0.0))

        # ── Shop block ───────────────────────────────────────────────────
        shop = request.shop if request is not None and request.kind == DecisionKind.SHOP else None
        card_entries = shop.card_entries if shop is not None else []
        for c in range(SHOP_CARD_SLOTS):
            entry = card_entries[c] if c < len(card_entries) else None
            stocked = entry is not None and entry.is_stocked
            o.append(1.0 if stocked else 0.0)
            hot = [0.0] * N_CARDS
            if stocked:
                hot[CARD_INDEX[entry.card.id]] = 1.0
            o.extend(hot)
            o.append(_clip01(entry.cost / _COST_SCALE) if stocked else 0.0)
            o.append(1.0 if stocked and entry.enough_gold else 0.0)
            o.append(1.0 if stocked and entry.on_sale else 0.0)
        relic_entries = shop.relic_entries if shop is not None else []
        for r in range(SHOP_RELIC_SLOTS):
            entry = relic_entries[r] if r < len(relic_entries) else None
            stocked = entry is not None and entry.is_stocked
            o.append(1.0 if stocked else 0.0)
            hot = [0.0] * N_RELICS
            if stocked:
                hot[RELIC_INDEX[entry.relic.id]] = 1.0
            o.extend(hot)
            o.append(_clip01(entry.cost / _COST_SCALE) if stocked else 0.0)
            o.append(1.0 if stocked and entry.enough_gold else 0.0)
        potion_entries = shop.potion_entries if shop is not None else []
        for p in range(SHOP_POTION_SLOTS):
            entry = potion_entries[p] if p < len(potion_entries) else None
            stocked = entry is not None and entry.is_stocked
            o.append(1.0 if stocked else 0.0)
            hot = [0.0] * N_POTIONS
            if stocked:
                hot[POTION_INDEX[entry.potion.id]] = 1.0
            o.extend(hot)
            o.append(_clip01(entry.cost / _COST_SCALE) if stocked else 0.0)
            o.append(1.0 if stocked and entry.enough_gold else 0.0)
        removal = shop.card_removal_entry if shop is not None else None
        stocked = removal is not None and removal.is_stocked
        o.append(1.0 if stocked else 0.0)
        o.append(_clip01(removal.cost / _COST_SCALE) if stocked else 0.0)
        o.append(1.0 if stocked and removal.enough_gold else 0.0)

        # ── Reward block ─────────────────────────────────────────────────
        rewards = request.rewards if request is not None and request.kind in (
            DecisionKind.REWARD_CARD, DecisionKind.REWARD_POTION,
        ) else None
        cards = rewards.cards if rewards is not None and request.kind == DecisionKind.REWARD_CARD else []
        for c in range(REWARD_CARD_SLOTS):
            card = cards[c] if c < len(cards) else None
            o.append(1.0 if card is not None else 0.0)
            hot = [0.0] * N_CARDS
            if card is not None:
                hot[CARD_INDEX[card.id]] = 1.0
            o.extend(hot)
            o.append(1.0 if (card is not None and card.upgrade_level > 0) else 0.0)
        potion = rewards.potion if rewards is not None and request.kind == DecisionKind.REWARD_POTION else None
        o.append(1.0 if potion is not None else 0.0)
        hot = [0.0] * N_POTIONS
        if potion is not None:
            hot[POTION_INDEX[potion.id]] = 1.0
        o.extend(hot)

        # ── Select block ─────────────────────────────────────────────────
        selecting = request is not None and request.kind in (
            DecisionKind.SELECT_CARDS, DecisionKind.SELECT_OPTION,
        )
        purpose_hot = [0.0] * N_PURPOSES
        if selecting:
            purpose_hot[PURPOSE_INDEX.get(request.purpose, N_PURPOSES - 1)] = 1.0
        o.extend(purpose_hot)
        o.append(_clip01(request.count_remaining / 5.0) if selecting else 0.0)
        o.append(1.0 if (selecting and request.skippable) else 0.0)
        if selecting and request.kind == DecisionKind.SELECT_CARDS:
            o.extend(pile_composition(request.candidates))
        else:
            o.extend([0.0] * (2 * N_CARDS))

        # ── Combat block ─────────────────────────────────────────────────
        combat = request.combat if request is not None else None
        if combat is not None:
            o.extend(build_combat_obs(combat, self._card_obs).tolist())
        else:
            o.extend([0.0] * self._combat_obs_dim)

        obs = np.asarray(o, dtype=np.float32)
        assert obs.shape == self.observation_space.shape, (
            f"obs dim drifted: {obs.shape} vs {self.observation_space.shape}"
        )
        return obs

    # ------------------------------------------------------------------

    def _info(self) -> dict[str, Any]:
        run = self._run
        info: dict[str, Any] = {
            "floor": run.total_floor,
            "act": run.act_index,
            "phase": self._request.kind.value if self._request is not None else "done",
        }
        if self._result is not None:
            info["is_success"] = self._result.victory
            info["hp_left"] = self._result.hp
            info["decisions"] = self._result.decisions
        return info

    def render(self) -> None:
        if self.render_mode != "human" or self._run is None:
            return
        run = self._run
        phase = self._request.kind.value if self._request is not None else "done"
        print(
            f"[{phase}] act {run.act_index + 1} floor {run.total_floor}  "
            f"HP {max(0, run.hp)}/{run.max_hp}  gold {run.gold}  "
            f"deck {len(run.deck)}  relics {len(run.relics)}"
        )


def masked_random_run_policy(rng: random.Random) -> Callable:
    """(env, obs, mask) -> action — uniform over the mask (baseline)."""

    def policy(env, obs, mask):
        return int(rng.choice(np.flatnonzero(mask)))

    return policy
