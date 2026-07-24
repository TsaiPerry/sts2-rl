from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class AlchemicalCoffer(Relic):
    """AlchemicalCoffer.cs — upon pickup, gain 4 potion slots (PotionSlots
    DynamicVar) and fill them with 4 random potions."""

    id = "alchemical_coffer"
    name = "Alchemical Coffer"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    POTION_SLOTS = 4

    def after_obtained(self, run) -> None:
        run.max_potions += self.POTION_SLOTS
        # Parity: `PotionFactory.CreateRandomPotionsOutOfCombat(owner, 4,
        # RunState.Rng.CombatPotionGeneration)` — two draws per potion (rarity
        # NextFloat + NextItem over that rarity's bucket) on the serialized
        # CombatPotionGeneration stream. Legacy keeps the uniform helper.
        if run.rng_set is not None:
            from ..potion_pools import generate_random_potions

            potions = generate_random_potions(
                run.rng_set.combat_potion_generation, self.POTION_SLOTS)
        else:
            potions = run.random_potions(self.POTION_SLOTS)
        for potion in potions:
            run.add_potion(potion)
