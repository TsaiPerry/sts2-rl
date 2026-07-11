from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class MiniatureCannon(Relic):
    """Your Upgraded Attacks deal 3 additional damage."""

    id = "miniature_cannon"
    name = "Miniature Cannon"
    rarity = RelicRarity.UNCOMMON

    EXTRA_DAMAGE = 3

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        # Powered-attack-only path (the pipeline only calls this for powered
        # attacks). Applies to the owner's Upgraded Attack cards.
        if card is not None and card.upgrade_level > 0 and dealer is self.player:
            return self.EXTRA_DAMAGE
        return 0
