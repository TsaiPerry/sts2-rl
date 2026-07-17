from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class HandDrill(Relic):
    """Whenever you break an enemy's block, apply 2 Vulnerable to it.

    Source: HandDrill.cs — AfterDamageGiven when result.WasBlockBroken
    (Block <= 0 && blockedDamage > 0: an exact break counts) on a non-player
    target whose damage came from the owner -> PowerVar<VulnerablePower>(2).
    Granted by the Trash Heap event."""

    id = "hand_drill"
    name = "Hand Drill"
    rarity = RelicRarity.EVENT

    VULNERABLE = 2  # PowerVar<VulnerablePower>(2)

    def on_block_broken(self, target, dealer=None, card=None) -> None:
        if dealer is not self.player or target is self.player:
            return
        from ..cmds import PowerCmd
        from ..powers import VulnerablePower
        PowerCmd.apply(
            self.combat.hooks, target, VulnerablePower, self.VULNERABLE,
            applier=self.player,
        )
