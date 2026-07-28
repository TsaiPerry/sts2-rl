from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DelicateFrond(Relic):
    """DelicateFrond.cs — at the start of each combat (BeforeCombatStart),
    fill every open potion slot with a random potion
    (PotionFactory.CreateRandomPotionOutOfCombat while HasOpenPotionSlots)."""

    id = "delicate_frond"
    name = "Delicate Frond"
    rarity = RelicRarity.ANCIENT

    def on_combat_start(self) -> None:
        from ..potions import _POTION_CLASSES

        player = self.player
        pool = sorted(
            (
                c for c in _POTION_CLASSES.values()
                if c.in_reward_pool and self.combat.owns_potion(c)
            ),
            key=lambda c: c.id,
        )
        while player.has_open_potion_slot:
            player.add_potion(self.combat._rng.choice(pool)())
