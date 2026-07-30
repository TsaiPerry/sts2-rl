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
        # FranticEscape.cs:45 is `EnergyCost.AddThisCombat(1)`, a
        # LocalCostModifier with EndOfCombat expiration — so the card is back
        # to cost 1 in the NEXT combat. Mutating `_energy_cost` changed the
        # card's BASE cost, and `reset_combat_state` does not re-run
        # `_init_vars`, so a Frantic Escape played twice and carried into the
        # next fight started it at 3.
        self.set_cost_this_combat(self.energy_cost + 1)
