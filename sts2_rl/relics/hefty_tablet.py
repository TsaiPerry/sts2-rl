from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class HeftyTablet(Relic):
    """HeftyTablet.cs — choose one of 3 random Rare cards (uniform, never
    upgraded; skippable) and gain an Injury curse."""

    id = "hefty_tablet"
    name = "Hefty Tablet"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    CARDS = 3

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import reward_pool_card_ids
        from ..rewards import CardCreationFlags, RarityOddsType, create_reward_cards

        # HeftyTablet.cs:29 goes through CardFactory.CreateForReward, whose
        # candidate set is `options.GetPossibleCards(player)` =
        # `CardPools.SelectMany(p => p.GetUnlockedCards(...))`
        # (CardCreationOptions.cs:168-178). There is NO FilterForCombat anywhere
        # on that path — the Uniform arm only drops Basic and Ancient
        # (CardFactory.cs:221-224), which `reward_pool_card_ids` reflects. The
        # port used `pool_card_ids()`, the FilterForCombat mirror, which drops
        # `can_be_generated_in_combat = False` cards: `feed` and `not_yet`, two
        # of the strongest Rares in the pool, could never be offered, and because
        # NextItem indexes into the candidate list in pool order a 23-item list
        # returns a DIFFERENT card than a 25-item list for the same draw, so all
        # three offers diverged on every seed. (Fixed prior to R14.)
        #
        # R14 (round 14, R10): HeftyTablet.cs:29 builds its own
        # `CardCreationOptions(character pool, CardCreationSource.Other,
        # CardRarityOddsType.Uniform, c => c.Rarity == Rare)
        # .WithFlags(CardCreationFlags.NoUpgradeRoll)` and calls
        # `CardFactory.CreateForReward(owner, 3, options)` DIRECTLY — not
        # through `CardReward.cs`, so `IsCardReward` is never set (only
        # `CardReward.cs:114-115`/`:134` sets it — DingyRug.cs:23,
        # PrismaticGem.cs:38, SilkenTress.cs:53, SilverCrucible.cs:104 all key
        # off that flag, so a False here is what lets them fire on this
        # screen), and `Source.Other` means the pity offset must not advance
        # (`CardFactory.RollForRarity` only mutates for
        # `Source == Encounter`, CardFactory.cs:244-260) — irrelevant for the
        # Uniform arm's own roll (CardFactory.cs:219-221 takes none) but it
        # still matters for `create_reward_cards`' `roll_for_upgrade` gate and
        # for a future caller reusing this odds type mutably. The previous
        # port hand-rolled the pick loop, which SKIPPED
        # `Hook.ModifyCardRewardCreationOptions` (pool-widening — Dingy Rug /
        # Prismatic Gem) and `Hook.TryModifyCardRewardOptions[Late]`
        # (CardFactory.cs:104/106) — the egg relics / Silver Crucible / Silken
        # Tress / Glitter never got a chance to upgrade or enchant an offered
        # card. Routing through `create_reward_cards` (rewards.py:313) restores
        # both hook passes and keeps the RNG draw order (one `Rewards.NextItem`
        # per card; `NoUpgradeRoll` also suppresses the per-card upgrade draw
        # AND its `Rewards.NextFloat`, exactly as `CardFactory.cs:98-102`
        # guards it) — see `create_reward_cards`'s own docstring for the flag
        # semantics.
        rares = [
            cid for cid in reward_pool_card_ids(pool=run.card_pool)
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        options = create_reward_cards(
            run, RarityOddsType.UNIFORM, count=self.CARDS,
            mutate_pity=False,
            pool=rares,
            is_card_reward=False,
            extra_flags=CardCreationFlags.NO_UPGRADE_ROLL,
        )
        for card in run.select_cards("obtain", options, 1):
            run.add_card(card)
        run.add_card(make_card("injury"))
