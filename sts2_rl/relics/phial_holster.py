from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PhialHolster(Relic):
    """PhialHolster.cs — gain 1 potion slot and 2 random potions."""

    id = "phial_holster"
    name = "Phial Holster"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    POTION_SLOTS = 1
    POTIONS = 2

    def after_obtained(self, run) -> None:
        run.add_potion_slots(self.POTION_SLOTS)
        # PhialHolster.cs:29 is `PotionFactory.CreateRandomPotionsOutOfCombat(
        # Owner, 2, RunState.Rng.CombatPotionGeneration)` — per potion, an
        # `rng.NextFloat()` for the rarity band (<= 0.1f Rare, <= 0.35f Uncommon,
        # else Common) and then an `rng.NextItem` inside that band, removing each
        # pick from the working list (PotionFactory.cs:46-81). The port called
        # `run.random_potions(2, distinct=True)`, a uniform `choice` over the WHOLE
        # reward pool on the shared run rng: a different DISTRIBUTION and a
        # different STREAM, and the game's four draws were never taken, so every
        # later CombatPotionGeneration draw in the run was shifted. Bug class 16's
        # second half, and the stream is genuinely consumed. The sibling relic with
        # the identical C# call (alchemical_coffer) already used the right helper.
        if run.rng_set is not None:
            from ..potion_pools import generate_random_potions

            potions = generate_random_potions(
                run.rng_set.combat_potion_generation, self.POTIONS,
                pool=run.potion_pool)
        else:
            potions = run.random_potions(self.POTIONS, distinct=True)
        for potion in potions:
            run.add_potion(potion)
