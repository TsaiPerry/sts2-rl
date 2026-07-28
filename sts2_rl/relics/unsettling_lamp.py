from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class UnsettlingLamp(Relic):
    """The first card play that Debuffs an enemy each combat has that play's
    debuffs doubled.

    Source: UnsettlingLamp.cs — BeforeCombatStart resets; the first
    card-sourced, owner-applied, enemy-targeted visible Debuff latches its
    card (BeforePowerAmountChanged), ModifyPowerAmountGivenMultiplicative
    doubles every debuff from that card, and AfterCardPlayed marks the relic
    finished for the combat. The sim tracks the in-flight card via the
    before/on_card_played bracket instead of a card-source parameter on the
    power pipeline."""

    id = "unsettling_lamp"
    name = "Unsettling Lamp"
    rarity = RelicRarity.RARE

    def __init__(self) -> None:
        super().__init__()
        self._in_flight = None   # card currently resolving
        self._triggering = None  # the latched card whose debuffs double
        self._finished = False   # used up for this combat

    def on_combat_start(self) -> None:
        self._in_flight = None
        self._triggering = None
        self._finished = False

    # target=None keeps this compatible with the hook both before and after
    # the card-play hook carries its target.
    def before_card_played(self, card, target=None) -> None:
        self._in_flight = card

    def on_card_played(self, card,
                       is_auto_play: bool = False) -> None:
        if card is self._triggering:
            self._finished = True
        self._in_flight = None

    def modify_power_amount(self, power_cls, target, amount, applier) -> int:
        if self._finished or self._in_flight is None or amount <= 0:
            return amount
        if applier is not self.player or target is self.player:
            return amount
        from ..powers import PowerType
        if power_cls.power_type != PowerType.DEBUFF:
            return amount
        self._triggering = self._in_flight
        return amount * 2
