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
    STATUS = "status"
    CURSE = "curse"


class TargetType(Enum):
    ANY_ENEMY = "any_enemy"
    ALL_ENEMIES = "all_enemies"
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
    # When True, play_card calls on_play once for ALL_ENEMIES cards; the card
    # iterates enemies itself (needed when a card has a one-time setup step
    # alongside per-enemy damage, e.g. Breakthrough's self-damage).
    handles_own_routing: bool = False

    def __init__(self) -> None:
        self.upgrade_level: int = 0
        self._energy_cost: int = 0
        # At most one affliction per card (mirrors CardModel.Affliction).
        self.affliction: "Affliction | None" = None
        self._init_vars()

    def _init_vars(self) -> None:
        pass

    def _on_upgrade(self) -> None:
        pass

    def upgrade(self) -> None:
        self.upgrade_level += 1
        self._on_upgrade()

    @property
    def energy_cost(self) -> int:
        return self._energy_cost

    @abstractmethod
    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None: ...

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        pass

    def __repr__(self) -> str:
        suffix = "+" * self.upgrade_level if self.upgrade_level > 0 else ""
        return f"{self.name}{suffix}"
