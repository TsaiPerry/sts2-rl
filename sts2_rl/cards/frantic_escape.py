from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class FranticEscapeCard(Card):
    """Status added by The Insatiable's LIQUIFY_GROUND move.

    Source: FranticEscape.cs
      Cost 1 | Status | Status | TargetType.Self
      On play: add 1 to the Sandpit power's counter (delaying the devour by a
      turn), then this card costs 1 more for the rest of the combat
      (EnergyCost.AddThisCombat).
    """
    id = "frantic_escape"
    name = "Frantic Escape"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.SELF
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import SandpitPower
        for enemy in ctx.enemies:
            sandpit = enemy.powers.get("sandpit")
            if sandpit is not None and not enemy.is_gone:
                PowerCmd.apply(ctx.hooks, enemy, SandpitPower, 1)
                break
        # AddThisCombat(1): permanent for this combat, not cleared at turn end.
        self._energy_cost += 1
