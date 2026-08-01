from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature


@register_relic
class RuinedHelmet(Relic):
    """The first time you gain Strength each combat, gain twice as much."""

    id = "ruined_helmet"
    name = "Ruined Helmet"
    rarity = RelicRarity.RARE

    def __init__(self) -> None:
        super().__init__()
        self._used = False

    def reset_for_combat(self) -> None:
        # RuinedHelmet.AfterCombatEnd (:57-61).
        self._used = False

    def modify_power_amount_received(
        self,
        power_cls: type,
        target: Creature,
        amount: int,
        applier: Creature | None,
    ) -> int | None:
        """RuinedHelmet.cs:32-53 (`TryModifyPowerAmountReceived`) — a
        RECEIVED-side listener (power_cmd/G3, G4): dispatched by
        `hooks.modify_power_amount_received`, unconditionally (no applier
        gate exists for the received side at all). Returns the new amount to
        take effect, or `None` for "did not apply" (C#'s `bool` return +
        `out modifiedAmount`) — not the unchanged amount, which is how the
        given-side chain signals "no effect" instead.

        `self._used` is NOT set here — see `after_modify_power_amount_received`.
        C#'s own `TryModifyPowerAmountReceived` is a pure decision + value
        read; `UsedThisCombat = true` happens in the companion event
        (RuinedHelmet.cs:55-60), a real second phase, not a side effect
        folded into the modifier check itself.
        """
        from ..powers import StrengthPower
        if self._used:
            return None
        if power_cls is not StrengthPower:
            return None
        if target is not self.player:
            return None
        if amount <= 0:
            return None
        return amount * 2

    def after_modify_power_amount_received(self, power) -> None:
        """RuinedHelmet.cs:55-60 — `Flash()` has no sim counterpart (VFX
        only); `UsedThisCombat = true` is `self._used = True`."""
        self._used = True
