from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature
    from ..player import PlayerCombatState


@register_relic
class MusicBox(Relic):
    """MusicBox.cs — once per turn, when you play an Attack, add an ETHEREAL
    copy of it to your hand (BeforeCardPlayed captures the play,
    AfterCardPlayed clones with CardKeyword.Ethereal)."""

    id = "music_box"
    name = "Music Box"
    rarity = RelicRarity.ANCIENT

    def __init__(self) -> None:
        super().__init__()
        self.used_this_turn = False
        self._card_being_played: "Card | None" = None

    def before_card_played(
        self, card: "Card", target: "Creature | None" = None,
    ) -> None:
        from ..cards import CardType

        if (
            self._card_being_played is None
            and not self.used_this_turn
            and card.card_type == CardType.ATTACK
        ):
            self._card_being_played = card

    def on_card_played(self, card: "Card",
                       is_auto_play: bool = False) -> None:
        if card is not self._card_being_played:
            return
        from ..cards.base import create_clone
        from ..cmds import CardPileCmd

        copy = create_clone(card)
        copy.is_ethereal = True
        CardPileCmd.add_to_hand(self.hooks, self.player, copy)
        self.used_this_turn = True
        self._card_being_played = None

    def on_player_turn_start(self, player: "PlayerCombatState") -> None:
        self.used_this_turn = False
        self._card_being_played = None
