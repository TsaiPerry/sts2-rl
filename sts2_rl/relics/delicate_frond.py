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
        from ..potion_pools import (
            generate_random_potion, legacy_random_potion_out_of_combat,
        )
        from ..potions import try_to_procure

        player = self.player
        rng_set = self.combat.rng_set
        while player.has_open_potion_slot:
            # DelicateFrond.cs:17 -- PotionFactory.CreateRandomPotionOutOfCombat,
            # which is a RARITY ROLL (NextFloat; Rare <= 0.1, Uncommon <= 0.35,
            # else Common) and then NextItem inside that bucket
            # (PotionFactory.cs:67-81). A uniform pick over the whole pool handed
            # out Rares three times too often.
            if rng_set is not None:
                potion = generate_random_potion(
                    rng_set.combat_potion_generation,
                    pool=self.combat.potion_pool)
            else:
                potion = legacy_random_potion_out_of_combat(
                    self.combat._rng, pool=self.combat.potion_pool)
            # DelicateFrond.cs:18-21 -- `if (!(...TryToProcure(...)).success)
            # break;`. The break is load-bearing, not tidiness: under Sozu the
            # procure always fails and the belt never fills, so a loop without
            # it would spin forever.
            if not try_to_procure(self.hooks, player, potion):
                break
