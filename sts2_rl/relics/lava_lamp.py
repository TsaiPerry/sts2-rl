from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp
from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class LavaLamp(Relic):
    """LavaLamp.cs — if you took no damage during a combat, every upgradable
    card in its reward is offered Upgraded.

    Three hooks: AfterRoomEntered clears the latch, AfterDamageReceived sets it
    for any UNBLOCKED, non-Unblockable damage the owner takes in a combat room,
    and TryModifyCardRewardOptionsLate upgrades the offer while the latch is
    clear."""

    id = "lava_lamp"
    name = "Lava Lamp"
    rarity = RelicRarity.SHOP

    def __init__(self) -> None:
        super().__init__()
        self.took_damage_this_combat = False

    def after_room_entered(self, run, point, room_type) -> None:
        self.took_damage_this_combat = False

    def on_damage_received(
        self,
        target: "Creature",
        amount: int,
        dealer: "Creature | None",
        card: "Card | None",
        props: ValueProp,
    ) -> None:
        if target is not self.player or amount <= 0:
            return
        if ValueProp.UNBLOCKABLE in props:
            return
        self.took_damage_this_combat = True

    def modify_card_reward_options_late(self, run, cards) -> None:
        if self.took_damage_this_combat:
            return
        for card in cards:
            if card.is_upgradable:
                card.upgrade()
