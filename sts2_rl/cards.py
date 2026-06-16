from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .combat import CombatCtx


class CardType(Enum):
    ATTACK = "attack"
    SKILL = "skill"


class Card(ABC):
    id: str
    name: str
    card_type: CardType
    energy_cost: int

    @abstractmethod
    def on_play(self, ctx: CombatCtx) -> None: ...

    def __repr__(self) -> str:
        return self.name


class StrikeCard(Card):
    id = "strike"
    name = "Strike"
    card_type = CardType.ATTACK
    energy_cost = 1

    def on_play(self, ctx: CombatCtx) -> None:
        from .cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.enemy, 6 + ctx.player.strength, dealer=ctx.player, card=self)


class DefendCard(Card):
    id = "defend"
    name = "Defend"
    card_type = CardType.SKILL
    energy_cost = 1

    def on_play(self, ctx: CombatCtx) -> None:
        from .cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, ctx.player, 5, card=self)


STRIKE = StrikeCard()
DEFEND = DefendCard()

CARD_REGISTRY: dict[str, Card] = {"strike": STRIKE, "defend": DEFEND}
CARD_TO_IDX: dict[str, int] = {"strike": 0, "defend": 1}
