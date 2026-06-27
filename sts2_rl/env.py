from __future__ import annotations

import random
from typing import Any

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from .cards import StrikeCard, DefendCard
from .combat import CombatState, Phase
from .monsters import MoveType, Intent

# action 0 = end turn, 1 = play a Strike, 2 = play a Defend
N_ACTIONS = 3

# Observation layout (12 floats, all in [0, 1]):
#   [0]  player_hp_norm
#   [1]  player_block_norm       (cap 30)
#   [2]  player_energy_norm      (cap 3)
#   [3]  strikes_in_hand_norm    (cap 5)
#   [4]  defends_in_hand_norm    (cap 5)
#   [5]  draw_pile_size_norm     (cap 9)
#   [6]  discard_pile_size_norm  (cap 9)
#   [7]  enemy_hp_norm
#   [8]  enemy_block_norm        (cap 30)
#   [9]  enemy_strength_norm     (cap 50)
#   [10] enemy_intent_is_attack  (0 or 1)
#   [11] enemy_intent_damage_norm (cap 30)
OBS_DIM = 12


class STS2CombatEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(self, render_mode: str | None = None) -> None:
        super().__init__()
        self.render_mode = render_mode

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(N_ACTIONS)

        self._state: CombatState | None = None
        self._rng = random.Random()

    # ------------------------------------------------------------------
    # gym interface
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        if seed is not None:
            self._rng = random.Random(seed)
        self._state = CombatState(rng=self._rng)
        return self._obs(), self._info()

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        assert self._state is not None, "Call reset() before step()"
        s = self._state
        hp_before = s.player.hp

        if action == 0:
            s.end_turn()
        elif action == 1:
            for i, card in enumerate(s.player.hand):
                cost = s.hooks.modify_card_energy_cost(card, card.energy_cost)
                if isinstance(card, StrikeCard) and cost <= s.player.energy:
                    s.play_card(i)
                    break
        elif action == 2:
            for i, card in enumerate(s.player.hand):
                cost = s.hooks.modify_card_energy_cost(card, card.energy_cost)
                if isinstance(card, DefendCard) and cost <= s.player.energy:
                    s.play_card(i)
                    break

        reward = (s.player.hp - hp_before) / s.player.max_hp

        terminated = s.is_over
        if terminated:
            reward += 1.0 if s.result.player_won else 0.0

        return self._obs(), reward, terminated, False, self._info()

    def render(self) -> None:
        if self.render_mode != "human":
            return
        s = self._state
        print(f"\n=== Turn {s.turn} ===")
        print(
            f"Player  HP {s.player.hp}/{s.player.max_hp}"
            f"  Block {s.player.block}  Energy {s.player.energy}"
        )
        print(f"Hand    {[c.name for c in s.player.hand]}")
        print(
            f"Piles   draw={len(s.player.draw_pile)}"
            f"  discard={len(s.player.discard_pile)}"
        )
        intent = s.enemy.current_intent
        intent_str = (
            f"Attack {intent.total_damage + s.enemy.strength}"
            if intent.move_type == MoveType.ATTACK
            else "Buff"
        )
        print(
            f"Enemy   HP {s.enemy.hp}/{s.enemy.max_hp}"
            f"  Str {s.enemy.strength}  Intent: {intent_str}"
        )

    def action_masks(self) -> np.ndarray:
        """For use with sb3-contrib MaskablePPO."""
        s = self._state
        mask = np.zeros(N_ACTIONS, dtype=bool)
        if s.phase != Phase.PLAYER_TURN:
            return mask
        mask[0] = True
        for card in s.player.hand:
            cost = s.hooks.modify_card_energy_cost(card, card.energy_cost)
            if cost <= s.player.energy:
                if isinstance(card, StrikeCard):
                    mask[1] = True
                elif isinstance(card, DefendCard):
                    mask[2] = True
        return mask

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _obs(self) -> np.ndarray:
        s = self._state
        p = s.player

        strikes = sum(1 for c in p.hand if isinstance(c, StrikeCard))
        defends = sum(1 for c in p.hand if isinstance(c, DefendCard))

        intent = s.enemy.current_intent
        intent_attack = float(intent.move_type == MoveType.ATTACK)
        intent_dmg = (intent.total_damage + s.enemy.strength) if intent.move_type == MoveType.ATTACK else 0

        return np.array(
            [
                p.hp / p.max_hp,
                min(p.block, 30) / 30.0,
                p.energy / 3.0,
                min(strikes, 5) / 5.0,
                min(defends, 5) / 5.0,
                min(len(p.draw_pile), 9) / 9.0,
                min(len(p.discard_pile), 9) / 9.0,
                s.enemy.hp / s.enemy.max_hp,
                min(s.enemy.block, 30) / 30.0,
                min(s.enemy.strength, 50) / 50.0,
                intent_attack,
                min(intent_dmg, 30) / 30.0,
            ],
            dtype=np.float32,
        )

    def _info(self) -> dict[str, Any]:
        s = self._state
        return {
            "valid_actions": s.valid_actions(),
            "turn": s.turn,
            "phase": s.phase.value,
        }
