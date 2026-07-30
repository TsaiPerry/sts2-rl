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
        # AlchemicalCoffer.cs:22 snapshots `originalSlotCount =
        # Owner.MaxPotionCount` BEFORE growing the belt, and :27 procures each
        # potion into the EXPLICIT slot `originalSlotCount + i` — on a fresh belt
        # slots 3, 4, 5, 6, leaving 0-2 empty. `run.add_potion` fills the FIRST
        # open slot instead, so the sim put them in 0-3. Slot identity is not
        # cosmetic: a UsePotion replay command names a SLOT, and the conformance
        # runner diffs `floor_potions` slot by slot.
        original_slots = run.max_potions
        run.add_potion_slots(self.POTION_SLOTS)
        # Parity: `PotionFactory.CreateRandomPotionsOutOfCombat(owner, 4,
        # RunState.Rng.CombatPotionGeneration)` — two draws per potion (rarity
        # NextFloat + NextItem over that rarity's bucket) on the serialized
        # CombatPotionGeneration stream. Legacy keeps the uniform helper.
        if run.rng_set is not None:
            from ..potion_pools import generate_random_potions

            potions = generate_random_potions(
                run.rng_set.combat_potion_generation, self.POTION_SLOTS,
                pool=run.potion_pool)
        else:
            potions = run.random_potions(self.POTION_SLOTS)
        for i, potion in enumerate(potions):
            run.add_potion(potion, slot=original_slots + i)
