from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp, is_powered_attack
from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class PenNib(Relic):
    """Every 10th Attack you play deals double damage. The 10th Attack is
    marked as it starts (before_card_played) and doubled through the damage
    multiplier for every hit it deals, then unmarked once it resolves."""

    id = "pen_nib"
    name = "Pen Nib"
    rarity = RelicRarity.UNCOMMON

    ATTACKS = 10

    def __init__(self) -> None:
        super().__init__()
        self._attacks_played = 0
        self._card_to_double: Card | None = None

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_played = (self._attacks_played + 1) % self.ATTACKS
        if self._attacks_played == 0:
            self._card_to_double = card

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # PenNib.cs:108
            return 1.0
        if card is None:                   # :112
            return 1.0
        if dealer is not self.player:      # :116
            return 1.0
        if self._card_to_double is None:
            # PenNib.cs:120-128, the arm the port had no counterpart for: with
            # no latched card, a cardSource that is NOT in PileType.Play doubles
            # once AttacksPlayed == 9. A card mid-OnPlay IS in PileType.Play
            # (bug class 7), so this arm can only be taken for a card the game is
            # PREVIEWING — the relic's promise made visible on the tenth Attack
            # while it still sits in hand. The pile clause is load-bearing: drop
            # it and the real play would double twice.
            #
            # The sim consumes the previewed number in its OBSERVATION vector
            # (previews.preview_card_damage -> full_env), not only in a sprite,
            # which is why this is a gap and not presentation.
            #
            # The predicate is `pile == null || pile.Type != PileType.Play`
            # verbatim: `card not in play_pile` is true both for a card in no
            # pile at all and for a card in any of the other four. Until round
            # 13 (R5) the sim had no Play pile and read `player._playing_card`
            # instead; that marker is now the NARROWER "the card whose
            # OnPlayWrapper is on the stack", and the two differ whenever
            # `CardPileCmd.AutoPlayFromDrawPile` has more than one pick parked
            # in Play (Havoc, Mayhem, Cascade, Distilled Chaos) — the parked
            # picks are in `PileType.Play` and are NOT `_playing_card`, so the
            # old predicate would have doubled a queued Attack's preview.
            # `getattr` because a relic's `player` is not always a live
            # PlayerCombatState (out-of-combat previews).
            if (card not in getattr(self.player, "play_pile", ())
                    and self._attacks_played == self.ATTACKS - 1):
                return 2.0
            return 1.0
        if card is self._card_to_double:   # :129
            return 2.0
        return 1.0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card is self._card_to_double:
            self._card_to_double = None
