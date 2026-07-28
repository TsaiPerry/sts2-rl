from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class RainbowRing(Relic):
    """The first time each turn you have played an Attack, a Skill, and a Power,
    gain 1 Strength and 1 Dexterity."""

    id = "rainbow_ring"
    name = "Rainbow Ring"
    rarity = RelicRarity.RARE

    def __init__(self) -> None:
        super().__init__()
        self._attack = False
        self._skill = False
        self._power = False
        self._activated = False

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        self._attack = self._skill = self._power = self._activated = False

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if self._activated:
            return
        if card.card_type == CardType.ATTACK:
            self._attack = True
        elif card.card_type == CardType.SKILL:
            self._skill = True
        elif card.card_type == CardType.POWER:
            self._power = True
        if self._attack and self._skill and self._power:
            self._activated = True
            from ..cmds import PowerCmd
            from ..powers import DexterityPower, StrengthPower
            PowerCmd.apply(self.hooks, self.player, StrengthPower, 1, applier=self.player)
            PowerCmd.apply(self.hooks, self.player, DexterityPower, 1, applier=self.player)
