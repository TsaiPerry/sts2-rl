from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class LetterOpener(Relic):
    """Every time you play 3 Skills in a single turn, deal 5 damage to ALL
    enemies."""

    id = "letter_opener"
    name = "Letter Opener"
    rarity = RelicRarity.UNCOMMON

    SKILLS = 3
    DAMAGE = 5

    def __init__(self) -> None:
        super().__init__()
        self._skills_this_turn = 0

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        self._skills_this_turn = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type != CardType.SKILL:
            return
        self._skills_this_turn += 1
        if self._skills_this_turn % self.SKILLS == 0:
            from ..cmds import DamageCmd
            for enemy in self.living_enemies():
                DamageCmd.deal(
                    self.hooks, enemy, self.DAMAGE,
                    dealer=self.player, props=DamageProps.NON_CARD_UNPOWERED,
                )
            self._check_win()
