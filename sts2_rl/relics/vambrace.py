from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp, is_card_or_monster_move
from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class Vambrace(Relic):
    """The first time you gain Block from a card each combat, double it.

    `modify_block_multiplicative` READS `_triggering_card`/`_used` -- it is
    NOT stateless (round-14 R6: an earlier docstring here claimed the
    opposite, which was itself the bug class 24 misdescription that
    relic/vambrace guard N3 flags -- it read as a justification for the
    since-fixed latch-collapse bug, G3). A preview call is still SAFE,
    though, because only
    `after_modify_block_amount`/`on_card_played` WRITE that state DURING a
    card play (`__init__` and `reset_for_combat` also write them, but only to
    clear) -- a preview only reads it.

    Vambrace overrides no `AfterBlockGained` hook -- not in this port and not
    in `Vambrace.cs`, whose overrides are ModifyBlockMultiplicative,
    AfterModifyingBlockAmount, AfterCardPlayed, BeforeCombatStart and
    AfterCombatEnd. The hook itself is real on BOTH sides (Hook.cs:143,
    dispatched from CreatureCmd.cs:662, overridden by JuggernautPower.cs:17
    and BeaconOfHopePower.cs:36; here `on_block_gained`, hooks.py:138/:1712,
    fired from cmds.py:502) -- it is simply not one of Vambrace's. The state
    comes from the other pair instead: `after_modify_block_amount` latches
    `_triggering_card` (Vambrace.cs:82-96) and `on_card_played` spends
    `_used` at the END of that card's play (Vambrace.cs:98-113)."""

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
