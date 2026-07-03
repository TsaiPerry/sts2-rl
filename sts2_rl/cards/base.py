from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..afflictions import Affliction
    from ..combat import CombatCtx


class CardType(Enum):
    ATTACK = "attack"
    SKILL = "skill"
    POWER = "power"
    STATUS = "status"
    CURSE = "curse"


class CardRarity(Enum):
    BASIC = "basic"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    ANCIENT = "ancient"
    TOKEN = "token"
    STATUS = "status"
    CURSE = "curse"


class TargetType(Enum):
    ANY_ENEMY = "any_enemy"
    ALL_ENEMIES = "all_enemies"
    RANDOM_ENEMY = "random_enemy"
    SELF = "self"
    NONE = "none"


_CARD_CLASSES: dict[str, type[Card]] = {}


def register_card(cls: type[Card]) -> type[Card]:
    _CARD_CLASSES[cls.id] = cls
    return cls


def make_card(card_id: str) -> Card:
    return _CARD_CLASSES[card_id]()


class Card(ABC):
    id: str
    name: str
    card_type: CardType
    rarity: CardRarity
    target_type: TargetType = TargetType.ANY_ENEMY
    is_playable: bool = True
    is_ethereal: bool = False
    has_turn_end_in_hand_effect: bool = False
    is_unpowered: bool = False
    # Exhaust keyword: the card goes to the exhaust pile instead of the
    # discard pile after being played (mirrors CardKeyword.Exhaust).
    exhausts: bool = False
    # Innate keyword: starts on top of the draw pile, and the first-turn hand
    # draw is raised to include all innate cards (mirrors CardKeyword.Innate).
    innate: bool = False
    # X-cost (mirrors HasEnergyCostX): the card costs ALL remaining energy;
    # play_card stores the amount spent in captured_x for on_play to read
    # (mirrors EnergyCost.CapturedXValue / ResolveEnergyXValue).
    energy_cost_x: bool = False
    # Card tags (mirrors CardModel.Tags, e.g. "strike" for Perfected Strike).
    tags: frozenset[str] = frozenset()
    # Mirrors CardModel.MaxUpgradeLevel (0 for statuses/curses — they can
    # never be upgraded, e.g. by Armaments).
    max_upgrade_level: int = 1
    # When True, play_card calls on_play once for ALL_ENEMIES cards; the card
    # iterates enemies itself (needed when a card has a one-time setup step
    # alongside per-enemy damage, e.g. Breakthrough's self-damage).
    handles_own_routing: bool = False

    def __init__(self) -> None:
        self.upgrade_level: int = 0
        self._energy_cost: int = 0
        # X value captured when an X-cost card is played (energy spent).
        self.captured_x: int = 0
        # Per-turn cost modifiers, cleared at the start of each player turn
        # (mirror EnergyCost.AddThisTurn and SetToFreeThisTurn).
        self._cost_delta_this_turn: int = 0
        self._free_this_turn: bool = False
        # At most one affliction per card (mirrors CardModel.Affliction).
        self.affliction: "Affliction | None" = None
        # Back-reference to the owning combat (mirrors CardModel.CombatState),
        # set when the card is registered as a hook listener; lets card-level
        # hook methods reach combat state (Stomp, Drum of Battle, Howl).
        self.combat = None
        self._init_vars()

    def _init_vars(self) -> None:
        pass

    def _on_upgrade(self) -> None:
        pass

    def upgrade(self) -> None:
        self.upgrade_level += 1
        self._on_upgrade()

    @property
    def is_upgradable(self) -> bool:
        """Mirrors CardModel.IsUpgradable (upgrade level below the max)."""
        return self.upgrade_level < self.max_upgrade_level

    @property
    def energy_cost(self) -> int:
        if self._free_this_turn:
            return 0
        return max(0, self._energy_cost + self._cost_delta_this_turn)

    def add_cost_this_turn(self, delta: int) -> None:
        """Change this card's cost until the end of the turn (mirrors
        EnergyCost.AddThisTurn, e.g. Stomp's per-attack discount)."""
        self._cost_delta_this_turn += delta

    def set_free_this_turn(self) -> None:
        """Make this card cost 0 until the end of the turn (mirrors
        SetToFreeThisTurn, e.g. Infernal Blade's generated attack)."""
        self._free_this_turn = True

    def reset_turn_cost_modifiers(self) -> None:
        """Clear per-turn cost modifiers (called at player turn start)."""
        self._cost_delta_this_turn = 0
        self._free_this_turn = False

    @abstractmethod
    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None: ...

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        pass

    def __repr__(self) -> str:
        suffix = "+" * self.upgrade_level if self.upgrade_level > 0 else ""
        return f"{self.name}{suffix}"
