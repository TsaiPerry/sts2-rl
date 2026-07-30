from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PollinousCore(Relic):
    """Every 4 player turns, draw 2 extra cards.

    Source: PollinousCore.cs — BeforeSideTurnStart counts the owner's turns
    (a [SavedProperty]: AfterCombatEnd only resets the display, so the count
    persists across combats); when it reaches Turns(4), ModifyHandDraw adds
    Cards(2) and AfterModifyingHandDraw resets it. Granted by the Colossal
    Flower event."""

    id = "pollinous_core"
    name = "Pollinous Core"
    rarity = RelicRarity.EVENT

    TURNS = 4  # DynamicVar("Turns", 4)
    CARDS = 2  # CardsVar(2)

    def __init__(self) -> None:
        super().__init__()
        self.turns_seen = 0

    def before_side_turn_start(self, player) -> None:
        if player is self.player:
            self.turns_seen += 1

    def modify_hand_draw(self, player, count: int) -> int:
        if player is not self.player or self.turns_seen != self.TURNS:
            return count
        self.turns_seen = 0
        return count + self.CARDS
