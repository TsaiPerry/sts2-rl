from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import CardRarity, CardType
from ..rewards import (CardCreationFlags, CardRewardGroup, CombatRewards,
                        RarityOddsType, apply_reward_modifiers)
from ..rooms import RoomType
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..potions import Potion
    from ..run import RunState

# PotionRarity -> CardRarity (GetCardRarity; unknown rarities throw there,
# the sim's potion rarities are all covered).
_CARD_RARITY = {
    "rare": CardRarity.RARE,
    "event": CardRarity.RARE,
    "uncommon": CardRarity.UNCOMMON,
    "common": CardRarity.COMMON,
    "token": CardRarity.COMMON,
}

# The screen's CardCreationFlags, re-derived from the source rather than from
# the one `.WithFlags(...)` call that is easy to see:
#
#   CardCreationOptions.ForNonCombatWithUniformOdds(pool, predicate)
#       -> .WithFlags(NoUpgradeRoll)          CardCreationOptions.cs:159-162
#   .WithFlags(NoRarityModification | NoCardPoolModifications)
#                                             TheFutureOfPotions.cs:127
#   new CardReward(options, 3, Owner)
#       -> Options = options.WithFlags(IsCardReward)   CardReward.cs:114-115
#
# `WithFlags` ORs (`Flags |= flag`, CardCreationOptions.cs:212-216), so the
# creation runs against all four. `IS_CARD_REWARD` is not listed here because
# `CardRewardGroup.populate` already ORs it on for every CardReward, exactly
# as the constructor does. What each of the other three does in the sim:
#
#   NO_UPGRADE_ROLL           CardFactory.cs:98-102 skips RollForUpgrade AND
#                             its Rewards draw — so this screen takes 3 draws,
#                             not 6, and its cards reach AfterGenerated at +0
#                             (the offer is +1, never +2, in every act).
#   NO_CARD_POOL_MODIFICATIONS DingyRug.cs:19-22 (and Prismatic Gem / Character
#                             Cards / Big Game Hunter) return the options
#                             untouched, so the Colorless pool never joins the
#                             candidates the predicate above already narrowed.
#   NO_RARITY_MODIFICATION    no ported reader yet; declared because the source
#                             sets it and a future rarity-modifying hook must
#                             see it (this screen's rarity is the event's
#                             choice, per the flag's own doc comment).
_SCREEN_FLAGS = (CardCreationFlags.NO_UPGRADE_ROLL
                 | CardCreationFlags.NO_RARITY_MODIFICATION
                 | CardCreationFlags.NO_CARD_POOL_MODIFICATIONS)


class _PotionCardRewardGroup(CardRewardGroup):
    """CardRewardGroup that reapplies TheFutureOfPotions' `AfterGenerated`
    upgrade (TheFutureOfPotions.cs:129, body :132-138) every time Populate
    draws new cards — both the FIRST generation and Driftwood's Reroll
    (CardReward.cs:322-332: `Reroll` clears `_cards` then calls `Populate()`
    again). C#'s `AfterGenerated` fires from inside `Populate`'s own
    `_cards.Count <= 0` branch (CardReward.cs:156-164), which both the first
    draw and every reroll reach — overriding `populate()` here, instead of
    upgrading once outside the reroll loop, is what makes a reroll
    re-upgrade the newly-drawn cards instead of leaving them at +0.

    Routing through the base `populate()` (rather than hand-rolling the
    `create_reward_cards` call the way `_trade` used to) also passes
    `is_card_reward=True` (rewards.py, mirroring CardReward.cs:114-115's
    unconditional `Options = options.WithFlags(CardCreationFlags.
    IsCardReward)`), which the hand-rolled call never set — see R2-report.md
    for the SilkenTress/SilverCrucible divergence that missing flag caused.

    `IsCardReward` alone is NOT the source's flag set, though, and setting only
    it is its own divergence: it un-gates Dingy Rug, whose first guard
    (DingyRug.cs:19-22) is `NoCardPoolModifications`. The group therefore
    carries `flags=_SCREEN_FLAGS` (above), the full set the source's options
    accumulate, and `CardRewardGroup.flags` -> `create_reward_cards
    (extra_flags=...)` carries them to the creation. Pinned by
    `test_the_future_of_potions_offer_is_not_widened_by_dingy_rug` and
    `..._offer_takes_no_upgrade_roll`."""

    def populate(self, run: "RunState") -> None:
        super().populate(run)
        for card in self.cards:
            card.upgrade()


@register_event
class TheFutureOfPotions(Event):
    """The Future of Potions — trade a potion for its card of the future.

    Shared event (ModelDb.AllSharedEvents). Source: TheFutureOfPotions.cs
      IsAllowed: every player holds at least 2 potions
      POTION_i (first 3 held potions): discard it, then pick 1 of 3 UPGRADED
        character-pool cards whose rarity maps from the potion's
        (Rare/Event -> Rare, Uncommon -> Uncommon, Common/Token -> Common)
        and whose type was pre-rolled per potion (Attack/Skill, plus Power
        only for Uncommon+ rarities) — uniform odds, distinct cards. The
        screen is a real RewardsCmd.OfferCustom CardReward (R2, round 13):
        skippable as a whole, rerollable with Driftwood held (re-upgrading
        the new cards each time) and offers Pael's Wing's sacrifice
        alternative — surfaced via `pending_rewards`, same as brain_leech.py
        / trial.py's mid-event reward screens.

    The source's CanRemovePotions=false guard is UI-only (the sim has no
    out-of-combat potion discard surface) and is not modeled.
    """

    id = "the_future_of_potions"
    name = "The Future of Potions"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return len(run.held_potions) >= 2

    def calculate_vars(self) -> None:
        # PotionToCardType: one roll per held potion, in belt order.
        er = self.event_rng
        self._card_types: dict[int, CardType] = {}
        for potion in self.run.held_potions:
            types = [CardType.ATTACK, CardType.SKILL, CardType.POWER]
            if potion.rarity in ("common", "token"):
                types.remove(CardType.POWER)
            # `base.Rng.NextItem(list2)` — the event's own Rng
            # (TheFutureOfPotions.cs:59).
            self._card_types[id(potion)] = (
                er.next_item(types) if er is not None
                else self.rng.choice(types))

    def initial_options(self) -> list[EventOption]:
        options = []
        for i, potion in enumerate(self.run.held_potions[:3]):
            options.append(EventOption(
                f"POTION_{i}",
                lambda p=potion: self._trade(p),
            ))
        return options

    def _trade(self, potion: Potion) -> None:
        from ..cards.pool import _CARD_CLASSES, reward_pool_card_ids

        target_rarity = _CARD_RARITY[potion.rarity]
        card_type = self._card_types[id(potion)]
        self.run.discard_potion(potion)
        candidates = [
            cid for cid in reward_pool_card_ids(self.run.card_pool)
            if _CARD_CLASSES[cid].rarity == target_rarity
            and _CARD_CLASSES[cid].card_type == card_type
        ]
        # `new CardReward(ForNonCombatWithUniformOdds(Character.CardPool,
        #  Rarity == targetRarity && Type == PotionToCardType[potion])
        #  .WithFlags(NoRarityModification | NoCardPoolModifications), 3, ...)`
        # (TheFutureOfPotions.cs:127-129) — CardFactory.CreateForReward, so the
        # offer reaches Hook.TryModifyCardRewardOptions[Late] (CardFactory.cs:
        # 102-105, `create_reward_cards`'s `modify_hooks` pass — NoModifyHooks
        # is NOT among the flags below) before AfterGenerated upgrades every
        # offered card — on the first draw AND on every Driftwood reroll
        # (_PotionCardRewardGroup.populate, above). `flags` carries the rest of
        # the source's creation options through; see _SCREEN_FLAGS above for
        # the derivation and for what each one does.
        group = _PotionCardRewardGroup(
            room_type=RoomType.MONSTER, count=3,
            pool=tuple(candidates), odds_type=RarityOddsType.UNIFORM,
            flags=_SCREEN_FLAGS,
        )
        group.populate(self.run)
        # `RewardsCmd.OfferCustom(base.Owner, [reward])` (TheFutureOfPotions.
        # cs:130) -> `new RewardsSet(player).WithCustomRewards(rewards)
        # .Offer()` (RewardsCmd.cs:47-50) -> `GenerateWithoutOffering` runs
        # `Hook.ModifyRewards` (RewardsSet.cs:136) on this set exactly like
        # any other — where Driftwood's reroll (Driftwood.cs:14-25, no room
        # check) and Pael's Wing's sacrifice alternative land. `rewards.room`
        # stays None: a mid-event OfferCustom set has no AbstractRoom behind
        # it (RewardsSet.cs:106-110), same as brain_leech's Rip and trial's
        # Nondescript Guilty.
        rewards = CombatRewards(room_type=RoomType.MONSTER, card_rewards=[group])
        apply_reward_modifiers(self.run, rewards)
        # The whole screen is skippable (CardReward.CanSkip defaults true,
        # CardReward.cs:95, never overridden here) — the potion is already
        # spent either way (PotionCmd.Discard above). `pending_rewards` is
        # the sim's mid-event OfferCustom channel (brain_leech.py / trial.py
        # use the same one); the driver drains it into a REWARD_CARD decision
        # that surfaces pick / skip / reroll / sacrifice.
        self.pending_rewards = rewards
        self._finish("DONE")
