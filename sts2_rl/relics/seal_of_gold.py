from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class SealOfGold(Relic):
    """SealOfGold.cs — at the start of EACH turn, if you have at least 5 gold:
    pay 5 gold, gain 1 Energy (AfterSideTurnStart; EnergyVar(1), GoldVar(5))."""

    id = "seal_of_gold"
    name = "Seal of Gold"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1
    GOLD = 5

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        combat = self.combat
        # SealOfGold.cs:27 gates on `Owner.Gold`, and PlayerCmd.GainGold
        # updates Player.Gold live (PlayerCmd.cs:141-170) — so gold won mid
        # combat is immediately spendable. `combat.gold_gained` is the sim's
        # accumulator for exactly that, and ThieveryPower already reads the
        # balance this way (powers.py).
        balance = (combat.player_gold + combat.gold_gained
                   - combat.gold_stolen - combat.gold_spent)
        if balance < self.GOLD:
            return
        from ..cmds import EnergyCmd

        combat.gold_spent += self.GOLD
        EnergyCmd.gain(self.hooks, player, self.ENERGY)
