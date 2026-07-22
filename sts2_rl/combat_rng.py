"""Per-purpose combat RNG accessor — the SP3 combat seam.

CombatState funnels all combat randomness through one object. The real game
splits it across independent RunRngSet streams (Shuffle, MonsterAi, the Combat*
streams), each drawn in an exact order and count. `CombatRng` exposes one named
accessor per purpose:

  - legacy mode  (CombatRng.legacy): every accessor returns the ONE shared
    `random.Random`, so RL training/eval sequences are unchanged.
  - parity mode  (CombatRng.parity): each accessor is a GameRandomAdapter over
    the matching game stream, so a string-seeded run reproduces the game.
"""
from __future__ import annotations

from .rng import GameRandomAdapter, RunRngSet

_PARITY_STREAMS = {
    "shuffle": "shuffle",
    "monster_ai": "monster_ai",
    "card_gen": "combat_card_generation",
    "card_selection": "combat_card_selection",
    "targets": "combat_targets",
    "energy": "combat_energy_costs",
    "potion_gen": "combat_potion_generation",
}


class CombatRng:
    def __init__(self, accessors: dict, is_parity: bool = False) -> None:
        self._accessors = accessors
        # True only for string-seeded parity runs. Consumers that must bridge a
        # game-oriented result into the sim's own convention (e.g. the draw pile
        # stores its top at the END of the list, but the game's shuffle yields
        # top-at-index-0) branch on this. Legacy stays byte-for-byte unchanged.
        self.is_parity = is_parity

    @classmethod
    def legacy(cls, rng) -> "CombatRng":
        return cls({name: rng for name in _PARITY_STREAMS}, is_parity=False)

    @classmethod
    def parity(cls, rng_set: RunRngSet) -> "CombatRng":
        return cls({
            name: GameRandomAdapter(getattr(rng_set, attr))
            for name, attr in _PARITY_STREAMS.items()
        }, is_parity=True)

    shuffle = property(lambda self: self._accessors["shuffle"])
    monster_ai = property(lambda self: self._accessors["monster_ai"])
    card_gen = property(lambda self: self._accessors["card_gen"])
    card_selection = property(lambda self: self._accessors["card_selection"])
    targets = property(lambda self: self._accessors["targets"])
    energy = property(lambda self: self._accessors["energy"])
    potion_gen = property(lambda self: self._accessors["potion_gen"])
