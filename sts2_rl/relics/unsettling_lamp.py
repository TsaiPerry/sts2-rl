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

    def on_combat_end(self) -> None:
        # UnsettlingLamp.cs:147-154 AfterCombatEnd — the game clears
        # TriggeringCard/DoubledPowers AND IsFinishedTriggering (and drops
        # Status back to Normal) when the combat ENDS, not only at the next
        # combat's start. Without this the sim's `_finished` stayed True on
        # every out-of-combat decision after a combat where the lamp
        # triggered, while the game (and the obs flag reading its finished
        # latch) reads False — 933T act-1 f13+ Map/Event/Rest lines, 38
        # cells.
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

    def modify_power_amount_given_multiplicative(
        self, power_cls, target, amount, applier
    ) -> int:
        """UnsettlingLamp.cs:106-129 (`ModifyPowerAmountGivenMultiplicative`)
        — a GIVEN-side listener (power_cmd/G3, G4): dispatched by
        `hooks.modify_power_amount_given_multiplicative`, only ever called
        when `applier is not None and _combat_contains_creature(hooks,
        applier)` (PowerCmd.apply's own gate, mirroring PowerCmd.cs:122-123).
        Returns a FACTOR (1 = unchanged, 2 = double), not the multiplied
        amount — the dispatcher folds it in, matching C#'s own return shape
        (`return 2m;`) and `modify_damage_multiplicative`'s chain contract.

        UnsettlingLamp.cs has no `amount <= 0` bail anywhere (read in full):
        BeforePowerAmountChanged (:71-104) and
        ModifyPowerAmountGivenMultiplicative (:106-129) both gate purely on
        `power.GetTypeForAmount(amount) != PowerType.Debuff` below. A sim-only
        `amount <= 0` bail here would reject Malaise/Resonance's negative
        Strength steal before the sign-aware check ever ran (power_cmd/G2,
        closed).
        """
        if self._finished or self._in_flight is None:
            return 1
        if applier is not self.player or target is self.player:
            return 1
        from ..powers import PowerType
        # UnsettlingLamp.cs:97,124 test `power.GetTypeForAmount(amount)`, not
        # the static Type: a negative-amount application of a Buff-typed
        # allow_negative power (Malaise/Resonance stealing Strength) is a
        # Debuff by C#'s rule and doubles here. This also self-protects a
        # duration tick (a negative offset on a non-allow_negative Debuff like
        # Weak/Vulnerable) without any extra bail: GetTypeForAmount flips that
        # case to Buff, so the `!= DEBUFF` check below already skips it.
        if power_cls.type_for_amount(amount) != PowerType.DEBUFF:
            return 1
        self._triggering = self._in_flight
        return 2
