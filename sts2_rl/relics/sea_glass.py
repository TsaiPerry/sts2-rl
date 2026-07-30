from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SeaGlass(Relic):
    """SeaGlass.cs — upon pickup, a grid pick from another character's card
    pool (15 cards: 5 Common / 5 Uncommon / 5 Rare of the assigned character).
    Cross-character card generation is out of scope for the single-character
    sim, so the CARDS are a documented no-op (the Orobas option can still be
    chosen; it simply grants nothing).

    The RNG is not a no-op. `AfterObtained` (SeaGlass.cs:74-91) calls
    `CardFactory.CreateForReward` three times with `DynamicVars.Cards.IntValue
    / 3` == 15 / 3 == 5 cards each, and every card is one
    `(options.RngOverride ?? player.PlayerRng.Rewards).NextItem(items)`
    (CardFactory.cs:235-236) with no upgrade roll — `ForNonCombatWithUniformOdds`
    already sets `NoUpgradeRoll` (CardCreationOptions.cs:162) and SeaGlass's
    own `WithFlags` ORs onto it (:212-216). So 15 Rewards draws happen whether
    or not the player keeps a card, and skipping them shifted every later
    Rewards consumer in the run — a grade-A stream desync, not a content gap.

    The count is portable without the pool: `Rng.next_int` costs exactly one
    MegaRandom draw whatever its range (rng.py:178-180), so the stream lands
    where the game's does even though the sim cannot say which cards it named.
    """

    id = "sea_glass"
    name = "Sea Glass"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    CARDS = 15                     # CardsVar(15), SeaGlass.cs:70

    def after_obtained(self, run) -> None:
        if run.rng_set is None:
            # Legacy RL play has one shared rng and no Rewards stream to keep
            # in position; burning draws there would only perturb training
            # sequences for an effect that grants nothing.
            return
        for _ in range(self.CARDS):
            run.player_rng.rewards.next_int(2)
