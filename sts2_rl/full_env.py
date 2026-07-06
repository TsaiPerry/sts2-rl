"""STS2FullCombatEnv — a Gymnasium env that exposes the *whole* combat.

Unlike the toy ``STS2CombatEnv`` (3 actions, one hardcoded fight), this env
drives the real engine: play any card in hand at any target, use potions, and
end the turn — across a configurable pool of encounters and a configurable
deck. It is built for ``sb3-contrib``'s ``MaskablePPO`` (an ``action_masks``
method reports the legal actions each step).

Design at a glance
------------------
Action space (flat ``Discrete``), decoded in ``_decode_action``::

    0                          end turn
    1 .. H*E                   play hand card h at enemy target e
    1+H*E .. 1+H*E+P*E         use potion p at enemy target e

  where H = MAX_HAND, E = MAX_ENEMIES, P = MAX_POTIONS. Cards/potions that
  don't need a target (SELF / ALL_ENEMIES / non-targeted potions) are masked to
  a single canonical target so equivalent actions don't bloat the space.

Observation (flat ``Box`` in [0, 1], layout in ``_build_obs``): player vitals +
a curated set of player powers, one row per hand slot (card identity one-hot in
``card_obs="hybrid"`` mode, plus engineered card features either way), one row
per enemy slot (vitals + intent + a curated set of enemy powers), and one row
per potion slot. The exact dimension is measured once at construction so the
two never drift.

Reward (all configurable): per-step normalized player-HP delta, plus a terminal
win/loss bonus. Because only ``end turn`` advances the enemy, damage taken is
naturally attributed to the step that ended the turn.

Simplifications (documented, not silent): mid-play card *selections* (Armaments,
Burning Pact, the Knowledge Demon curse pick, …) are still resolved by the
engine's default random ``card_selector`` — they are not exposed as separate
timesteps. Pass ``card_selector=`` to override. Living enemies past
``MAX_ENEMIES`` (only reachable via unusually spammy summons) are not
targetable.
"""
from __future__ import annotations

import random
from typing import Any, Callable, Sequence

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from .cards import Card, CardType, TargetType, make_card
from .cards.base import _CARD_CLASSES
from .combat import CombatState, Phase
from .monsters import Encounter, MoveType
from .monsters.overgrowth import ENCOUNTERS as _OVERGROWTH
from .player import PlayerCombatState
from .potions import ALL_POTIONS, Potion, make_potion

# ── Fixed-size bounds (obs/action slots). Bump + retrain if an encounter or a
#    relic ever exceeds these. ────────────────────────────────────────────────
MAX_HAND = PlayerCombatState.MAX_HAND_SIZE      # 10
MAX_POTIONS = PlayerCombatState.MAX_POTIONS      # 3
MAX_ENEMIES = 6                                  # initial lineup ≤4; headroom for summons

# Stable, sorted vocabularies (index = position). Importing .cards / .potions
# has already registered every class into these registries.
CARD_IDS: list[str] = sorted(_CARD_CLASSES)
CARD_INDEX: dict[str, int] = {cid: i for i, cid in enumerate(CARD_IDS)}
N_CARDS = len(CARD_IDS)

POTION_IDS: list[str] = sorted(ALL_POTIONS)
POTION_INDEX: dict[str, int] = {pid: i for i, pid in enumerate(POTION_IDS)}
N_POTIONS = len(POTION_IDS)

# Curated powers surfaced in the observation (amount, normalized). Strength /
# dexterity get dedicated signed scalar slots, so they are omitted here.
PLAYER_POWER_IDS = [
    "vulnerable", "weak", "frail", "poison", "artifact", "intangible",
    "barricade", "regen", "thorns", "plating", "feel_no_pain", "dark_embrace",
    "demon_form", "rupture", "rage", "vigor", "constrict", "tangled",
    "no_draw", "no_energy_gain",
]
ENEMY_POWER_IDS = [
    "vulnerable", "weak", "frail", "poison", "artifact", "intangible",
    "barricade", "thorns", "ritual", "curl_up", "plating", "shriek",
    "asleep", "minion", "illusion", "constrict", "vigor", "slow",
]

_CARD_TYPES = [CardType.ATTACK, CardType.SKILL, CardType.POWER, CardType.STATUS, CardType.CURSE]
_TARGET_TYPES = [
    TargetType.ANY_ENEMY, TargetType.ALL_ENEMIES, TargetType.RANDOM_ENEMY,
    TargetType.SELF, TargetType.NONE,
]

DEFAULT_DECK_IDS = ["strike"] * 5 + ["defend"] * 4
# Default training pool: the whole Act 1 (Overgrowth). Pass encounter=/encounters=
# to fix a single fight or supply your own curriculum.
DEFAULT_ENCOUNTERS: list[Encounter] = list(_OVERGROWTH.values())


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _signed(x: float, cap: float) -> float:
    """Map a signed value in [-cap, cap] onto [0, 1] (0.5 = zero)."""
    return _clip01((x + cap) / (2.0 * cap))


class STS2FullCombatEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        *,
        encounter: Encounter | None = None,
        encounters: Sequence[Encounter] | None = None,
        deck: Sequence[str] | None = None,
        potions: Sequence[str] | None = None,
        card_obs: str = "hybrid",
        card_selector: Callable[[str, list[Card], int], list[Card]] | None = None,
        reward_win: float = 1.0,
        reward_loss: float = 0.0,
        hp_reward_scale: float = 1.0,
        enemy_hp_reward_scale: float = 0.0,
        max_steps: int = 2000,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        if card_obs not in ("hybrid", "features"):
            raise ValueError("card_obs must be 'hybrid' or 'features'")

        # Encounter pool to sample each reset.
        if encounter is not None:
            self._encounters: list[Encounter] = [encounter]
        elif encounters is not None:
            self._encounters = list(encounters)
            if not self._encounters:
                raise ValueError("encounters is empty")
        else:
            self._encounters = list(DEFAULT_ENCOUNTERS)

        self._deck_ids = list(deck) if deck is not None else list(DEFAULT_DECK_IDS)
        self._potion_ids = list(potions) if potions is not None else []
        self._card_obs = card_obs
        self._card_selector = card_selector
        self._reward_win = reward_win
        self._reward_loss = reward_loss
        self._hp_reward_scale = hp_reward_scale
        self._enemy_hp_reward_scale = enemy_hp_reward_scale
        self._max_steps = max_steps
        self.render_mode = render_mode

        # Action space: end turn + play(hand, target) + potion(slot, target).
        self._play_base = 1
        self._potion_base = 1 + MAX_HAND * MAX_ENEMIES
        self.n_actions = self._potion_base + MAX_POTIONS * MAX_ENEMIES
        self.action_space = spaces.Discrete(self.n_actions)

        self._state: CombatState | None = None
        self._rng = random.Random()
        self._steps = 0

        # Measure the observation dimension once from a throwaway combat so the
        # declared space can never disagree with _build_obs.
        probe = self._new_state(random.Random(0))
        self._state = probe
        obs_dim = len(self._build_obs())
        self._state = None
        self.observation_space = spaces.Box(0.0, 1.0, shape=(obs_dim,), dtype=np.float32)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _new_state(self, rng: random.Random) -> CombatState:
        deck = [make_card(cid) for cid in self._deck_ids]
        potions = [make_potion(pid) for pid in self._potion_ids] or None
        encounter = rng.choice(self._encounters)
        state = CombatState(starting_deck=deck, rng=rng, encounter=encounter, potions=potions)
        if self._card_selector is not None:
            state.card_selector = self._card_selector
        return state

    # ------------------------------------------------------------------
    # gym interface
    # ------------------------------------------------------------------

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = random.Random(seed)
        self._state = self._new_state(self._rng)
        self._steps = 0
        return self._build_obs(), self._info()

    def step(self, action: int):
        assert self._state is not None, "call reset() before step()"
        s = self._state
        self._steps += 1

        hp_before = s.player.hp
        enemy_hp_before = self._total_enemy_hp()

        kind, a, b = self._decode_action(int(action))
        if kind == "end":
            s.end_turn()
        elif kind == "play":
            s.play_card(a, b)          # a=hand slot, b=target; no-op if illegal
        elif kind == "potion":
            s.use_potion(a, b)         # a=potion slot, b=target

        reward = self._hp_reward_scale * (s.player.hp - hp_before) / max(1, s.player.max_hp)
        if self._enemy_hp_reward_scale:
            reward += self._enemy_hp_reward_scale * (enemy_hp_before - self._total_enemy_hp()) / 100.0

        terminated = s.is_over
        if terminated:
            reward += self._reward_win if s.result.player_won else self._reward_loss
        truncated = (not terminated) and self._steps >= self._max_steps

        return self._build_obs(), float(reward), terminated, truncated, self._info()

    def action_masks(self) -> np.ndarray:
        """Boolean legality mask over the flat action space (for MaskablePPO)."""
        s = self._state
        mask = np.zeros(self.n_actions, dtype=bool)
        if s is None or s.phase != Phase.PLAYER_TURN:
            mask[0] = True   # keep at least one legal action (a harmless no-op)
            return mask

        mask[0] = True       # end turn is always legal on the player's turn
        living = [i for i, e in enumerate(s.enemies) if not e.is_gone and i < MAX_ENEMIES]
        first = living[0] if living else 0

        for h, card in enumerate(s.player.hand[:MAX_HAND]):
            if not card.is_playable or not s.hooks.should_play_card(card):
                continue
            if not card.energy_cost_x:
                if s.hooks.modify_card_energy_cost(card, card.energy_cost) > s.player.energy:
                    continue
            if card.target_type == TargetType.ANY_ENEMY:
                for e in living:
                    mask[self._play_base + h * MAX_ENEMIES + e] = True
            else:
                mask[self._play_base + h * MAX_ENEMIES + first] = True

        for p, potion in enumerate(s.player.potions[:MAX_POTIONS]):
            if potion.targeted:
                for e in living:
                    mask[self._potion_base + p * MAX_ENEMIES + e] = True
            else:
                mask[self._potion_base + p * MAX_ENEMIES + first] = True

        return mask

    def render(self) -> None:
        if self.render_mode != "human" or self._state is None:
            return
        s = self._state
        print(f"\n=== Turn {s.turn} ===")
        p = s.player
        print(f"Player HP {p.hp}/{p.max_hp}  Block {p.block}  Energy {p.energy}")
        for i, e in enumerate(s.enemies):
            tag = "DEAD" if e.is_gone else f"HP {e.hp}/{e.max_hp} Block {e.block}"
            intent = "" if e.is_gone else f"  intent={e.current_intent.move_type.value}"
            print(f"  [{i}] {e.__class__.__name__}: {tag}{intent}")
        print(f"Hand: {[repr(c) for c in p.hand]}")

    # ------------------------------------------------------------------
    # Action decoding
    # ------------------------------------------------------------------

    def _decode_action(self, action: int) -> tuple[str, int, int | None]:
        if action <= 0:
            return "end", 0, None
        if action < self._potion_base:
            idx = action - self._play_base
            return "play", idx // MAX_ENEMIES, idx % MAX_ENEMIES
        idx = action - self._potion_base
        return "potion", idx // MAX_ENEMIES, idx % MAX_ENEMIES

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def _total_enemy_hp(self) -> int:
        return sum(e.hp for e in self._state.enemies if not e.is_gone)

    @staticmethod
    def _power_amt(creature, pid: str) -> float:
        pw = creature.powers.get(pid)
        return float(pw.amount) if pw is not None else 0.0

    def _build_obs(self) -> np.ndarray:
        s = self._state
        p = s.player
        o: list[float] = []

        # ── Player vitals ────────────────────────────────────────────────
        o.append(_clip01(p.hp / max(1, p.max_hp)))
        o.append(_clip01(p.block / 50.0))
        o.append(_clip01(p.energy / 10.0))
        o.append(_signed(p.strength, 30))
        o.append(_signed(getattr(p, "dexterity", 0), 30))
        o.append(_clip01(len(p.hand) / MAX_HAND))
        o.append(_clip01(len(p.draw_pile) / 40.0))
        o.append(_clip01(len(p.discard_pile) / 40.0))
        o.append(_clip01(len(p.exhaust_pile) / 40.0))
        o.append(_clip01(s.turn / 30.0))
        for pid in PLAYER_POWER_IDS:
            o.append(_clip01(self._power_amt(p, pid) / 20.0))

        # ── Hand rows ────────────────────────────────────────────────────
        for h in range(MAX_HAND):
            card = p.hand[h] if h < len(p.hand) else None
            o.append(1.0 if card is not None else 0.0)
            if self._card_obs == "hybrid":
                onehot = [0.0] * N_CARDS
                if card is not None:
                    onehot[CARD_INDEX[card.id]] = 1.0
                o.extend(onehot)
            o.extend(self._card_features(card))

        # ── Enemy rows ───────────────────────────────────────────────────
        for e_i in range(MAX_ENEMIES):
            e = s.enemies[e_i] if e_i < len(s.enemies) else None
            o.extend(self._enemy_row(e))

        # ── Potion rows ──────────────────────────────────────────────────
        for pi in range(MAX_POTIONS):
            potion = p.potions[pi] if pi < len(p.potions) else None
            o.append(1.0 if potion is not None else 0.0)
            hot = [0.0] * N_POTIONS
            if potion is not None:
                hot[POTION_INDEX[potion.id]] = 1.0
            o.extend(hot)
            o.append(1.0 if (potion is not None and potion.targeted) else 0.0)

        return np.asarray(o, dtype=np.float32)

    def _card_features(self, card: Card | None) -> list[float]:
        f = [0.0] * 17
        if card is None:
            return f
        s = self._state
        f[0] = 0.0 if card.energy_cost_x else _clip01(card.energy_cost / 6.0)
        f[1] = 1.0 if card.energy_cost_x else 0.0
        for i, t in enumerate(_CARD_TYPES):
            if card.card_type == t:
                f[2 + i] = 1.0
        for i, t in enumerate(_TARGET_TYPES):
            if card.target_type == t:
                f[7 + i] = 1.0
        f[12] = 1.0 if card.exhausts else 0.0
        f[13] = 1.0 if card.is_ethereal else 0.0
        f[14] = 1.0 if card.is_playable else 0.0
        affordable = card.energy_cost_x or (
            s.hooks.modify_card_energy_cost(card, card.energy_cost) <= s.player.energy
        )
        f[15] = 1.0 if affordable else 0.0
        f[16] = _clip01(card.upgrade_level / 5.0)
        return f

    def _enemy_row(self, e) -> list[float]:
        row: list[float] = []
        if e is None or e.is_gone:
            # present flag + hp + block + str + 9 intent flags + dmg + hits + powers
            return [0.0] * (4 + 9 + 2 + len(ENEMY_POWER_IDS))
        row.append(1.0)
        row.append(_clip01(e.hp / max(1, e.max_hp)))
        row.append(_clip01(e.block / 50.0))
        row.append(_signed(e.strength, 30))

        intent = e.current_intent
        flags = [
            intent.has(MoveType.ATTACK),
            intent.has(MoveType.DEFEND),
            intent.has(MoveType.BUFF),
            intent.has(MoveType.DEBUFF) or intent.has(MoveType.DEBUFF_STRONG)
            or intent.has(MoveType.CARD_DEBUFF),
            intent.has(MoveType.STATUS_CARD),
            intent.has(MoveType.SUMMON),
            intent.has(MoveType.ESCAPE),
            intent.has(MoveType.HEAL),
            intent.has(MoveType.STUN) or intent.has(MoveType.SLEEP),
        ]
        row.extend(1.0 if x else 0.0 for x in flags)
        incoming = (intent.damage + e.strength) * intent.hits if intent.has(MoveType.ATTACK) else 0
        row.append(_clip01(incoming / 60.0))
        row.append(_clip01(intent.hits / 10.0))
        for pid in ENEMY_POWER_IDS:
            row.append(_clip01(self._power_amt(e, pid) / 20.0))
        return row

    # ------------------------------------------------------------------

    def _info(self) -> dict[str, Any]:
        s = self._state
        info: dict[str, Any] = {"turn": s.turn, "phase": s.phase.value}
        if s.is_over:
            info["is_success"] = bool(s.result.player_won)
        return info
