from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MawBank(Relic):
    """Whenever you climb to a new room, gain 12 Gold. Stops working the
    first time you spend gold at a shop.

    Source: MawBank.cs — AfterRoomEntered grants base.DynamicVars.Gold
    (GoldVar(12)) whenever RunState.BaseRoom == the entered room and
    !HasItemBeenBought; AfterItemPurchased sets HasItemBeenBought = true
    (which sets RelicStatus.Disabled via IsUsedUp) the first time the owning
    player spends > 0 gold on a merchant purchase. Granted by the Trash Heap
    event."""

    id = "maw_bank"
    name = "Maw Bank"
    rarity = RelicRarity.EVENT

    GOLD_PER_ROOM = 12  # CanonicalVars: GoldVar(12)

    def __init__(self) -> None:
        super().__init__()
        self.has_item_been_bought = False

    @property
    def is_used_up(self) -> bool:   # IsUsedUp => HasItemBeenBought
        return self.has_item_been_bought

    def after_room_entered(self, run, point, room_type) -> None:
        if not self.has_item_been_bought:
            run.gain_gold(self.GOLD_PER_ROOM)

    def after_item_purchased(self, run, entry, gold_spent) -> None:
        if self.has_item_been_bought or gold_spent <= 0:
            return
        self.has_item_been_bought = True
