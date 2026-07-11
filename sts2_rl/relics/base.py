"""Relic base class, rarity enum, and the id→class registry.

Mirrors STS2's RelicModel (src/Core/Models/Relics). Every relic subclasses
`Relic` and, like powers and cards, is a hook listener for the whole combat
(mirrors RelicModel.ShouldReceiveCombatHooks): it overrides only the hook
methods it needs and the HookSystem calls them by duck-typing. Pass relics to
`CombatState(relics=[...])`; `attach()` wires the combat back-reference and
registers the listener.

Hook mapping from the game (see CombatManager.SetupPlayerTurn):
  BeforeSideTurnStart (player)          → on_player_turn_start (pre-draw)
  AfterBlockCleared                     → on_block_cleared
  AfterEnergyReset                      → on_energy_reset
  ModifyHandDraw                        → modify_hand_draw
  AfterPlayerTurnStart(Late) /
  AfterSideTurnStart (player, post-draw)→ on_player_turn_started (post-draw)
  BeforeSideTurnEnd / AfterSideTurnEnd  → on_player_turn_end
  AfterCombatVictory                    → on_combat_end(player_won=True)

Relics whose entire effect lives outside combat (gold, map, deck edits, card
rewards, rest sites, potion rewards) are registered as documented no-op stubs
so the full pool is constructible; they simply have no hook methods. The sim
runs a single combat, so per-run counters (Girya lifts, Happy Flower's carry-
over turn counter) are per-combat / constructor-injected.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..combat import CombatState
    from ..creatures import Creature
    from ..hooks import HookSystem
    from ..monsters import Monster
    from ..player import PlayerCombatState


class RelicRarity(Enum):
    STARTER = "starter"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    SHOP = "shop"
    EVENT = "event"
    ANCIENT = "ancient"


_RELIC_CLASSES: dict[str, type[Relic]] = {}


def register_relic(cls: type[Relic]) -> type[Relic]:
    _RELIC_CLASSES[cls.id] = cls
    return cls


def make_relic(relic_id: str) -> Relic:
    return _RELIC_CLASSES[relic_id]()


class Relic:
    """Base class for all relics, mirroring STS2's RelicModel.

    Subclasses override hook methods as needed; the hook system calls them via
    hasattr duck-typing. `attach` must be called before combat starts (done by
    CombatState.__init__ for relics passed to the constructor).
    """

    id: str
    name: str
    rarity: RelicRarity

    def __init__(self) -> None:
        self.combat: CombatState | None = None

    def attach(self, combat: CombatState) -> None:
        self.combat = combat
        combat.hooks.register(self)

    # ── Convenience reads ────────────────────────────────────────────────

    @property
    def player(self) -> PlayerCombatState:
        return self.combat.player

    @property
    def hooks(self) -> HookSystem:
        return self.combat.hooks

    @property
    def turn(self) -> int:
        return self.combat.turn

    def living_enemies(self) -> list[Monster]:
        """Mirrors ICombatState.HittableEnemies (the sim's DamageCmd applies
        the should_allow_hitting predicate on top)."""
        return [e for e in self.combat.enemies if not e.is_gone]

    def _check_win(self) -> None:
        """End combat if a relic effect just killed the last enemy (mirrors
        the CheckWinCondition that follows game commands). Needed because
        relic damage can fire outside play_card/end_turn's own checks."""
        if not self.combat.is_over and self.combat._all_enemies_dead():
            self.combat._end_combat(player_won=True)

    def __repr__(self) -> str:
        return self.name
