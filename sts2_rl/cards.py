from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .combat import CombatCtx


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

    def __init__(self) -> None:
        self.upgrade_level: int = 0
        self._energy_cost: int = 0
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


@register_card
class StrikeCard(Card):
    id = "strike"
    name = "Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.BASIC
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 6

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)


@register_card
class DefendCard(Card):
    id = "defend"
    name = "Defend"
    card_type = CardType.SKILL
    rarity = CardRarity.BASIC
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)


@register_card
class BurnCard(Card):
    id = "burn"
    name = "Burn"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    is_playable = False
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from .cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.player, 2, dealer=None, card=self)


@register_card
class WoundCard(Card):
    id = "wound"
    name = "Wound"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    is_playable = False
    is_unpowered = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass


@register_card
class SweepCard(Card):
    """Hits every living enemy for 4 damage.

    play_card routes ALL_ENEMIES cards by calling on_play once per living
    enemy with that enemy's index as target_idx, so on_play just applies
    damage to the routed target.
    """
    id = "sweep"
    name = "Sweep"
    card_type = CardType.ATTACK
    rarity = CardRarity.BASIC
    target_type = TargetType.ALL_ENEMIES

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
