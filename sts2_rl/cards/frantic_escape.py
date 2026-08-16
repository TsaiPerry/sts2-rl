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

    FranticEscape.cs:38-42 calls `PowerCmd.ModifyAmount` directly on the
    found SandpitPower instance rather than `PowerCmd.Apply` — SandpitPower
    is now InstanceType.Instanced (power_cmd/G5), so Apply would start a
    fresh, independent instance instead of extending the existing timer.
    """
    id = "frantic_escape"
    name = "Frantic Escape"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.SELF
    max_upgrade_level = 0
    is_unpowered = True
    # FranticEscape.cs:30 overrides `CanBeGeneratedInCombat => false` and
    # does NOT override `CanBeGeneratedByModifiers` (CardModel.cs:648 default
    # stays `=> true`) -- the flags were backwards here.
    can_be_generated_in_combat = False

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        for enemy in ctx.enemies:
            sandpit = enemy.powers.get("sandpit")
            if sandpit is not None and not enemy.is_gone:
                # PowerCmd.modify_amount is the decrement-only path (cmds.py):
                # skips ModifyPowerAmountGiven/Received and takes no applier.
                # Safe only because current listeners on that chain
                # (UnsettlingLamp/Ruined Helmet/Vicious) are all
                # domain-disjoint from Sandpit; revisit if a future listener
                # gates on Buff power amounts generally.
                PowerCmd.modify_amount(ctx.hooks, sandpit, 1)
                break
        # FranticEscape.cs:45 `EnergyCost.AddThisCombat(1)` is a
        # LocalCostModifier with EndOfCombat expiration (back to cost 1 next
        # combat). Use set_cost_this_combat, not `_energy_cost` (that would
        # mutate the base cost, which `reset_combat_state` never re-derives).
        self.set_cost_this_combat(self.energy_cost + 1)
