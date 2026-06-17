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


class Card(ABC):
    id: str
    name: str
    card_type: CardType
    energy_cost: int
    is_playable: bool = True
    is_ethereal: bool = False
    has_turn_end_in_hand_effect: bool = False

    @abstractmethod
    def on_play(self, ctx: CombatCtx) -> None: ...

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        pass

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


class BurnCard(Card):
    """Status — Unplayable. At end of turn, deal 2 damage to the player."""
    id = "burn"
    name = "Burn"
    card_type = CardType.STATUS
    energy_cost = 0
    is_playable = False
    has_turn_end_in_hand_effect = True

    def on_play(self, ctx: CombatCtx) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from .cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.player, 2, dealer=None, card=self)


class WoundCard(Card):
    """Status — Unplayable. No effect."""
    id = "wound"
    name = "Wound"
    card_type = CardType.STATUS
    energy_cost = 0
    is_playable = False

    def on_play(self, ctx: CombatCtx) -> None:
        pass


STRIKE = StrikeCard()
DEFEND = DefendCard()
BURN = BurnCard()
WOUND = WoundCard()

CARD_REGISTRY: dict[str, Card] = {
    "strike": STRIKE,
    "defend": DEFEND,
    "burn": BURN,
    "wound": WOUND,
}
CARD_TO_IDX: dict[str, int] = {"strike": 0, "defend": 1}
