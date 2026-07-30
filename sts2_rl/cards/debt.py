from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DebtCard(Card):
    """Curse — Unplayable; at the end of your turn, lose 10 Gold.

    Source: Debt.cs
      Cost -1 | Curse | Curse | TargetType.None | GoldVar(10)
      Keywords: Unplayable; HasTurnEndInHandEffect
      OnTurnEndInHand: PlayerCmd.LoseGold(min(10, gold))

    The port used to justify a no-op with "the sim has no gold". That claim was
    false: `RunState.gold` exists and `RunState.lose_gold` is implemented with
    the matching floor-at-zero semantics and a PlayerCmd.LoseGold citation, and
    ported content spends gold routinely. So Debt was a strictly weaker curse
    here — in the game, holding it at end of turn costs up to 10 gold every
    turn, which compounds across a combat and changes what the next shop can
    sell you.
    """
    id = "debt"
    name = "Debt"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True

    has_turn_end_in_hand_effect = True
    GOLD = 10       # GoldVar(10), Debt.cs:18 — no upgrade, no ascension branch

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        """Debt.cs:26-30 — `Mathf.Min(DynamicVars.Gold.IntValue, Owner.Gold)`
        then `PlayerCmd.LoseGold(num, Owner)`.

        `Owner.Gold` is the live balance, which inside a combat is the run's
        balance at entry plus what has been won and minus what has been taken or
        spent — the same four-term ledger SealOfGold.cs:27 reads, and the sim
        keeps it on the combat (RunState.finish_combat settles it). The loss type
        is the default, i.e. voluntary/normal rather than Stolen, so it lands on
        `gold_spent`; `gold_stolen` keeps its meaning for Thievery.
        """
        combat = self.combat
        if combat is None:
            return
        balance = (combat.player_gold + combat.gold_gained
                   - combat.gold_stolen - combat.gold_spent)
        combat.gold_spent += max(0, min(self.GOLD, balance))
