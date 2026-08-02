from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class GlassEye(Relic):
    """GlassEye.cs — upon pickup, a reward set of five 3-card choices from the
    character pool: two Common, two Uncommon, one Rare.

    Each screen is `new CardReward(ForNonCombatWithUniformOdds(
    Character.CardPool, c => c.Rarity == rarity).WithFlags(
    NoRarityModification), 3, owner)` and all five ride ONE
    `RewardsCmd.OfferCustom` (GlassEye.cs:16-33). Uniform odds means
    CardFactory takes no rarity roll — the predicate narrows the pool and
    `NextItem` picks out of it (CardFactory.cs:216-225).

    `ForNonCombatWithUniformOdds` itself ORs `NoUpgradeRoll`
    (CardCreationOptions.cs:160-163) on top of the `NoRarityModification`
    GlassEye.cs:29 adds — R14 finding, corrected from an earlier round's
    "neither is set" reading, which was wrong: it looked only at the visible
    `.WithFlags(...)` call and missed the flag the factory method itself ORs
    in. `NoModifyHooks` is genuinely absent, so every screen still fires
    `Hook.TryModifyCardRewardOptions` (both passes), but each created card
    skips `RollForUpgrade` and the Rewards draw inside it
    (CardFactory.cs:98-102) — 15 draws across the five screens, not 30.
    """

    id = "glass_eye"
    name = "Glass Eye"
    rarity = RelicRarity.ANCIENT

    CHOICES = 3
    # The five screens, in the order GlassEye.cs:18-25 lists them.
    SCREEN_RARITIES = ("common", "common", "uncommon", "uncommon", "rare")

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import pool_card_ids, reward_pool_card_ids
        from ..rewards import (
            CardCreationFlags,
            CardRewardGroup,
            CombatRewards,
            RarityOddsType,
            apply_reward_modifiers,
        )
        from ..rooms import RoomType

        # `options.GetPossibleCards(player)` is CardPool.GetUnlockedCards — the
        # full unlocked pool, NOT FilterForCombat, so Feed and Not Yet (Rare,
        # CanBeGeneratedInCombat=false) really are offerable on the Rare screen.
        # Same split as rewards.create_reward_cards: the parity path uses the
        # game's pool, the legacy RL path stays byte-for-byte.
        pool = (reward_pool_card_ids(run.card_pool) if run.rng_set is not None
                else pool_card_ids(pool=run.card_pool))

        # RewardsSet.WithCustomRewards: Room stays null, so every room-gated
        # TryModifyRewards implementer short-circuits on it. room_type only
        # labels the screen for the observation; `odds_type`/`pool` are what
        # each group actually draws with.
        rewards = CombatRewards(room_type=RoomType.MONSTER, room=None)
        for name in self.SCREEN_RARITIES:
            rarity = CardRarity[name.upper()]
            matching = tuple(
                cid for cid in pool if _CARD_CLASSES[cid].rarity == rarity)
            if not matching:
                # C# throws when a rarity has no candidates; the sim skips the
                # screen rather than kill the run (recorded as note N5).
                continue
            rewards.card_rewards.append(CardRewardGroup(
                room_type=RoomType.MONSTER,
                odds_type=RarityOddsType.UNIFORM,
                pool=matching,
                count=min(self.CHOICES, len(matching)),
                flags=CardCreationFlags.NO_UPGRADE_ROLL,
            ))

        # RewardsSet.GenerateWithoutOffering (RewardsSet.cs:125-147): populate
        # every reward FIRST, then the two Hook.ModifyRewards passes, then the
        # groups a hook added. All fifteen draws therefore land before the
        # player is asked about the first screen — the sim used to populate,
        # resolve and ADD one screen at a time, so a card taken from screen 1
        # could change what screens 2-5 drew.
        for group in rewards.card_rewards:
            group.populate(run)
        apply_reward_modifiers(run, rewards)
        run.offer_rewards(rewards)
