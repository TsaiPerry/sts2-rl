from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FragrantMushroom(Relic):
    """On pickup, lose 15 HP and upgrade 2 random upgradable cards.

    Source: FragrantMushroom.cs — AfterObtained deals HpLossVar(15)
    unblockable, unpowered damage (CreatureCmd.Damage, so HP-loss modifiers
    like Tungsten Rod apply) then upgrades CardsVar(2) random upgradable
    deck cards. Fired by RunState.add_relic's after_obtained dispatch, so
    any grant path (the Hungry for Mushrooms event) triggers it."""

    id = "fragrant_mushroom"
    name = "Fragrant Mushroom"
    rarity = RelicRarity.EVENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    HP_LOSS = 15  # HpLossVar(15)
    CARDS = 2     # CardsVar(2)

    def after_obtained(self, run) -> None:
        run.lose_hp(self.HP_LOSS)
        upgradable = run.upgradable_cards()
        count = min(self.CARDS, len(upgradable))
        # FragrantMushroom.cs: Deck IsUpgradable cards,
        # StableShuffle(Rng.Niche).Take(count). StableShuffle sorts by ModelId
        # (card id, then upgrade level) before the game UnstableShuffle.
        if run.rng_set is not None:
            from ..actmap import stable_shuffle
            chosen = stable_shuffle(
                list(upgradable), run.rng_set.niche,
                key=lambda c: (c.id, c.upgrade_level),
            )[:count]
        else:
            chosen = run.rng.sample(upgradable, count)
        for card in chosen:
            card.upgrade()
