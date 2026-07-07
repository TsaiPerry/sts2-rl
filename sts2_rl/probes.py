"""Lethal-arithmetic probe suite — OBS_PLAN Phase 4, step 11.

Scripted micro-scenarios where the right move hinges on exact numbers the
observation encodes: strike-lethal edges (enemy at 6 vs 7 HP), block-or-die
edges (12 vs 11 telegraphed against 12 HP), and Weak/Vulnerable modifier
variants. Each probe builds a tiny constructed combat against a fixed-stat
dummy enemy, lets a policy play ONE player turn, and checks a turn-level
outcome (won untouched / survived / raced). Paired probes differ by a single
number, so a policy can only pass both sides of a pair by actually doing the
arithmetic — probe accuracy *measures* numeric grasp directly instead of
inferring it from win rate. Runners and adapters live in ``evaluation.py``;
the CLI is ``py eval.py --env full``.

Scenario surgery happens once at build time, before the policy sees the
state: powers go through ``PowerCmd`` (hook registration stays correct) and
plain integers (hp, energy) are set directly, exactly as the unit tests do.
Dummy ``Monster`` subclasses are created lazily per build, so the monster
vocabulary ``full_env`` froze at import is never affected — a dummy's identity
one-hot is all zeros, the documented unknown-enemy encoding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Sequence

from .cmds import PowerCmd
from .full_env import MAX_ENEMIES, MAX_HAND, STS2FullCombatEnv
from .monsters.base import Encounter, Intent, Monster, MoveType
from .powers import VulnerablePower, WeakPower
from .previews import (
    preview_card_block,
    preview_card_damage,
    preview_total_incoming,
)

if TYPE_CHECKING:
    from .combat import CombatState

# A policy is any callable (env, obs, mask) -> action int (see evaluation.py).
Policy = Callable[..., int]

# Every probe pins the player at this HP so the lethal edges below are exact.
PROBE_PLAYER_HP = 12


def probe_dummy(name: str, *, hp: int, damage: int, hits: int = 1) -> type[Monster]:
    """A fixed-stat enemy: exactly ``hp`` HP (no roll) and one eternal attack
    intent of ``damage`` × ``hits`` — the controlled variable of a probe."""

    class _ProbeDummy(Monster):
        min_hp = max_hp = hp

        @property
        def current_intent(self) -> Intent:
            return Intent(MoveType.ATTACK, damage=damage, hits=hits)

        def take_turn(self, ctx) -> None:
            self._execute_attack(ctx, damage, hits)

    _ProbeDummy.__name__ = _ProbeDummy.__qualname__ = name
    return _ProbeDummy


def _build(
    dummy: type[Monster],
    setup: Callable[[CombatState], None] | None = None,
) -> STS2FullCombatEnv:
    """A one-dummy combat: hand = [Strike, Defend], 1 energy, player at
    PROBE_PLAYER_HP — the policy gets exactly one meaningful card play."""
    env = STS2FullCombatEnv(
        encounter=Encounter(id=f"probe_{dummy.__name__}", monster_classes=[dummy]),
        deck=["strike", "defend"],
        max_steps=60,
    )
    env.reset(seed=0)
    s = env._state
    s.player.hp = PROBE_PLAYER_HP
    s.player.energy = 1
    if setup is not None:
        setup(s)
    return env


# ── Outcome checks (evaluated after the probe turn ends) ─────────────────────


def _won_untouched(env: STS2FullCombatEnv) -> bool:
    s = env._state
    return s.is_over and s.result.player_won and s.player.hp == PROBE_PLAYER_HP


def _survived(env: STS2FullCombatEnv) -> bool:
    return not env._state.player.is_dead


def _raced(env: STS2FullCombatEnv) -> bool:
    # Struck (the enemy lost Strike damage) and lived through the hit.
    s = env._state
    return not s.player.is_dead and s.enemies[0].hp == 14


@dataclass(frozen=True)
class Probe:
    id: str
    description: str
    build: Callable[[], STS2FullCombatEnv]
    check: Callable[[STS2FullCombatEnv], bool]


PROBES: list[Probe] = [
    # ── Strike-lethal edge: enemy HP 6 vs 7 (Strike deals 6) ─────────────────
    Probe(
        "lethal_edge_kill",
        "Enemy at 6 HP, 12 telegraphed vs 12 HP: Strike kills — take the kill, take nothing.",
        lambda: _build(probe_dummy("LethalEdgeKill", hp=6, damage=12)),
        _won_untouched,
    ),
    Probe(
        "lethal_edge_hold",
        "Enemy at 7 HP, 12 telegraphed vs 12 HP: Strike leaves 1 — block or die.",
        lambda: _build(probe_dummy("LethalEdgeHold", hp=7, damage=12)),
        _survived,
    ),
    # ── Incoming edge: 12 vs 11 telegraphed against 12 HP ────────────────────
    Probe(
        "incoming_lethal_block",
        "6×2 telegraphed (12 total) vs 12 HP, enemy at 20: unkillable this turn — block or die.",
        lambda: _build(probe_dummy("IncomingLethalBlock", hp=20, damage=6, hits=2)),
        _survived,
    ),
    Probe(
        "incoming_survivable_race",
        "11 telegraphed vs 12 HP, enemy at 20: the hit is survivable — deal damage, don't hide.",
        lambda: _build(probe_dummy("IncomingSurvivableRace", hp=20, damage=11)),
        _raced,
    ),
    # ── Vulnerable: 6×1.5 = 9 turns a 9-HP enemy lethal ──────────────────────
    Probe(
        "vulnerable_makes_lethal",
        "Enemy at 9 HP with Vulnerable: Strike previews 9 — kill now.",
        lambda: _build(
            probe_dummy("VulnerableMakesLethal", hp=9, damage=12),
            setup=lambda s: PowerCmd.apply(s.hooks, s.enemies[0], VulnerablePower, 1),
        ),
        _won_untouched,
    ),
    Probe(
        "no_vulnerable_hold",
        "Enemy at 9 HP without Vulnerable: Strike previews 6 — not lethal; 12 telegraphed: block.",
        lambda: _build(probe_dummy("NoVulnerableHold", hp=9, damage=12)),
        _survived,
    ),
    # ── Weak: 6×0.75 = 4 removes the kill on a 5-HP enemy ────────────────────
    Probe(
        "kill_without_weak",
        "Enemy at 5 HP, player not Weak: Strike previews 6 — kill now, take nothing.",
        lambda: _build(probe_dummy("KillWithoutWeak", hp=5, damage=12)),
        _won_untouched,
    ),
    Probe(
        "weak_removes_kill",
        "Enemy at 5 HP but the player is Weak: Strike previews 4 — no kill; 12 telegraphed: block.",
        lambda: _build(
            probe_dummy("WeakRemovesKill", hp=5, damage=12),
            setup=lambda s: PowerCmd.apply(s.hooks, s.player, WeakPower, 1),
        ),
        _survived,
    ),
]


# ── Runner ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    passed: bool
    actions: tuple[int, ...]


def run_probe(probe: Probe, policy: Policy, max_actions: int = 30) -> ProbeResult:
    """Let the policy play the probe's first player turn, then apply the check.

    The policy is called as ``policy(env, obs, mask)`` and must return a legal
    action; an illegal action (or never ending the turn within ``max_actions``)
    fails the probe outright. The turn ends when the policy ends it or combat
    ends mid-turn.
    """
    env = probe.build()
    s = env._state
    actions: list[int] = []
    for _ in range(max_actions):
        if s.is_over:
            break
        turn_before = s.turn
        obs = env._build_obs()
        mask = env.action_masks()
        action = int(policy(env, obs, mask))
        if not mask[action]:
            return ProbeResult(probe.id, False, tuple(actions))
        actions.append(action)
        env.step(action)
        if s.is_over or s.turn != turn_before:
            break
    else:
        return ProbeResult(probe.id, False, tuple(actions))
    return ProbeResult(probe.id, probe.check(env), tuple(actions))


def run_probes(policy: Policy, probes: Sequence[Probe] | None = None) -> list[ProbeResult]:
    return [run_probe(p, policy) for p in (PROBES if probes is None else probes)]


def probe_accuracy(results: Sequence[ProbeResult]) -> float:
    return sum(r.passed for r in results) / len(results) if results else 0.0


# ── Reference policy ──────────────────────────────────────────────────────────


def lethal_oracle(env, obs, mask) -> int:
    """A scripted reference player that does the probes' arithmetic explicitly
    through the preview helpers: take a kill if one is on the table, play the
    biggest block when the telegraphed post-block damage is lethal, otherwise
    attack, else end the turn. The ceiling for probe accuracy (passes every
    probe by construction) and a numerate scripted baseline for win-rate
    evals."""
    s = env.unwrapped._state
    p = s.player
    living = [(i, e) for i, e in enumerate(s.enemies[:MAX_ENEMIES]) if not e.is_gone]

    def action_for(h: int, e_i: int) -> int:
        return 1 + h * MAX_ENEMIES + e_i

    # 1. A play that kills an enemy outright (per-hit preview × hits vs
    #    hp + block — the on-card number against the visible pool).
    for h, card in enumerate(p.hand[:MAX_HAND]):
        for e_i, enemy in living:
            a = action_for(h, e_i)
            if not mask[a]:
                continue
            dmg = preview_card_damage(s, card, enemy)
            if dmg is not None and dmg * card.base_hits >= enemy.hp + enemy.block:
                return a

    # 2. The biggest block play when the telegraphed damage would kill us.
    if living and preview_total_incoming(s) >= p.hp:
        first = living[0][0]
        best: tuple[int, int] | None = None
        for h, card in enumerate(p.hand[:MAX_HAND]):
            blk = preview_card_block(s, card)
            if not blk:
                continue
            a = action_for(h, first)   # block cards sit at the canonical target
            if mask[a] and (best is None or blk > best[0]):
                best = (blk, a)
        if best is not None:
            return best[1]

    # 3. Otherwise make progress: the first legal damaging play.
    for h, card in enumerate(p.hand[:MAX_HAND]):
        for e_i, enemy in living:
            a = action_for(h, e_i)
            if mask[a] and preview_card_damage(s, card, enemy) is not None:
                return a

    return 0
