from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp, is_card_or_monster_move
from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class Vambrace(Relic):
    """The first time you gain Block from a card each combat, double it. The
    multiplier hook stays stateless (safe for previews); the one-shot flag is
    set from the real on_block_gained event."""

    id = "vambrace"
    name = "Vambrace"
    rarity = RelicRarity.UNCOMMON

    def __init__(self) -> None:
        super().__init__()
        # Vambrace.cs:21/34. `_triggering_card` latches the card whose block
        # gain Vambrace actually doubled; `_used` is BlockGainedThisCombat.
        self._triggering_card = None
        self._used = False

    def reset_for_combat(self) -> None:
        # Vambrace.BeforeCombatStart (:47-53) and AfterCombatEnd (:104-110)
        # both clear the state.
        self._triggering_card = None
        self._used = False

    def modify_block_multiplicative(
        self,
        target: Creature,
        amount: int,
        card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        # Vambrace.cs:57-80, clause for clause.
        if not is_card_or_monster_move(props):          # :59 — Move ALONE
            return 1.0
        if card is None:                                # :63
            return 1.0
        if self._triggering_card is not None and self._triggering_card is not card:
            return 1.0                                  # :67
        if target is not self.player:                   # :71
            return 1.0
        if self._used:                                  # :75
            return 1.0
        return 2.0

    def after_modify_block_amount(self, target: Creature, amount: int,
                                  card: Card | None = None) -> None:
        # Vambrace.cs:82-95 — fired only for a listener that ACTUALLY modified
        # the amount, which is what Hook.ModifyBlock's `out modifiers` list
        # carries. Latching the card here is what makes Vambrace double EVERY
        # block gain of one card play; the sim's old on_block_gained hand-roll
        # burned the once-per-combat flag on the FIRST gain instead.
        if amount <= 0:                                 # :84
            return
        if card is None:                                # :88
            return
        self._triggering_card = card

    def on_card_played(self, card: "Card",
                       is_auto_play: bool = False) -> None:
        # Vambrace.cs:98-113 — the lockout lands at the END of the triggering
        # card's play, not on its first block gain.
        if card is not self._triggering_card or self._used:
            return
        self._used = True
