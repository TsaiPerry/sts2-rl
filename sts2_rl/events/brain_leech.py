from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_RIP_HP_LOSS = 5           # DamageVar(5, Unblockable | Unpowered)
_REWARD_COUNT = 1          # IntVar RewardCount
_CARD_CHOICE_COUNT = 1     # IntVar CardChoiceCount
_FROM_CHOICE_COUNT = 5     # IntVar FromCardChoiceCount


@register_event
class BrainLeech(Event):
    """Brain Leech — share knowledge for a card, or rip it free.

    Shared event (ModelDb.AllSharedEvents). Source: BrainLeech.cs
      IsAllowed: acts 1-2 only (CurrentActIndex < 2)
      SHARE_KNOWLEDGE: pick 1 of 5 character-pool reward cards (default
                       non-mutating odds; the screen is not cancelable)
      RIP: take 5 damage, then a 3-card Colorless reward choice (default
           odds, no rarity/pool modification hooks)
    """

    id = "brain_leech"
    name = "Brain Leech"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index < 2

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("SHARE_KNOWLEDGE", self._share_knowledge),
            EventOption("RIP", self._rip),
        ]

    def _share_knowledge(self) -> None:
        from ..rewards import CardCreationFlags, RarityOddsType, create_reward_cards

        # BrainLeech.cs:66 builds this screen through
        # `CardCreationOptions.ForNonCombatWithDefaultOdds([Character.CardPool])`,
        # which always ORs `NoUpgradeRoll` (CardCreationOptions.cs:139) — same
        # as the RIP branch below (BrainLeech.cs:56) and every other
        # `ForNonCombatWith*` factory call. Without it this screen took
        # `2 * count` Rewards draws and could pre-upgrade a card
        # AfterGenerated then upgrade it again.
        cards = create_reward_cards(
            self.run, RarityOddsType.REGULAR, count=_FROM_CHOICE_COUNT,
            mutate_pity=False,
            extra_flags=CardCreationFlags.NO_UPGRADE_ROLL,
        )
        for card in self.run.select_cards("card_reward", cards,
                                          _CARD_CHOICE_COUNT):
            self.run.add_card(card)
        self._finish("SHARE_KNOWLEDGE")

    def _rip(self) -> None:
        from ..cards.pool import COLORLESS_POOL
        from ..rewards import (CardCreationFlags, CardRewardGroup, CombatRewards,
                               RarityOddsType, apply_reward_modifiers)
        from ..rooms import RoomType

        self.run.lose_hp(_RIP_HP_LOSS)
        # BrainLeech.cs:51-61 hands its RewardCount 3-card colourless CardRewards
        # to `RewardsCmd.OfferCustom` — a SKIPPABLE screen. The sim ran them
        # through `select_cards`, which always returns a card when the candidate
        # list is non-empty (run.py), so the player could not decline: the
        # colourless pool holds curses and situational cards, and the source
        # distinguishes the two screens deliberately — SHARE_KNOWLEDGE sets
        # `Cancelable = false` and this branch does not. `pending_rewards` is the
        # sim's mid-event OfferCustom channel (the driver offers and clears it as
        # soon as the option returns), the same one Dense Vegetation's rest heal
        # uses.
        #
        # BrainLeech.cs:56 — `CardCreationOptions.ForNonCombatWithDefaultOdds(
        # [ColorlessCardPool]).WithFlags(NoRarityModification |
        # NoCardPoolModifications)`: Source=Other, so `CardFactory.RollForRarity`
        # stays on the non-mutating `RollWithBaseOdds` path (CardCreationOptions.
        # cs:150-153 sets Source=Other unconditionally; CardFactory.cs:244-260
        # only mutates for Source==Encounter) — and `ForNonCombatWithDefaultOdds`
        # itself always adds `NoUpgradeRoll` (CardCreationOptions.cs:139), on top
        # of the two the call site adds. NEITHER overload ever sets
        # `NoModifyHooks` — `modify_hooks=False` here (R13's fix, F-R13b / g7)
        # was a stand-in for this different flag pair and wrongly suppressed the
        # WHOLE `Hook.TryModifyCardRewardOptions[Late]` dispatch (CardFactory.
        # cs:104), keeping Silken Tress / Silver Crucible / the eggs / Glitter
        # off this screen.
        #
        # Building the group through `CardRewardGroup(...).populate()` — the
        # pattern `_PotionCardRewardGroup` established for The Future of
        # Potions (events/the_future_of_potions.py) — rather than a hand-rolled
        # `create_reward_cards` call also carries `is_card_reward=True` onto the
        # options those relics gate on (CardReward.cs:114-115), missing before
        # on the very first draw, not just the reroll; and, critically, it
        # carries `pool` / `odds_type` / `flags` onto the GROUP itself, so
        # `CardReward.Reroll` (CardReward.cs:322-332) regenerates against the
        # SAME options as the first draw (`RerollOptions = options.WithFlags(
        # IsCardReward)` is the identical `options` the constructor was given,
        # CardReward.cs:114-115) instead of falling back to
        # `CardRewardGroup.populate`'s `pool is None` default (the sim's
        # character-pool / mutating-pity path) — F-R13a / g6.
        groups = []
        for _ in range(_REWARD_COUNT):
            group = CardRewardGroup(
                room_type=RoomType.MONSTER, count=3,
                pool=tuple(COLORLESS_POOL), odds_type=RarityOddsType.REGULAR,
                flags=(CardCreationFlags.NO_UPGRADE_ROLL
                       | CardCreationFlags.NO_RARITY_MODIFICATION
                       | CardCreationFlags.NO_CARD_POOL_MODIFICATIONS),
            )
            group.populate(self.run)
            groups.append(group)
        rewards = CombatRewards(room_type=RoomType.MONSTER, card_rewards=groups)
        # `RewardsCmd.OfferCustom` is `new RewardsSet(player).WithCustomRewards(
        # rewards).Offer()` (RewardsCmd.cs:47-50), whose Offer -> Generate
        # WithoutOffering runs Hook.ModifyRewards (RewardsSet.cs:136) same as
        # any other screen. `rewards.room` stays None here (no AbstractRoom
        # behind a mid-event screen), which is what keeps the room-gated
        # relics off it — Driftwood.TryModifyRewardsLate doesn't check room
        # (Driftwood.cs:14-25), so it still reaches this CardReward.
        apply_reward_modifiers(self.run, rewards)
        self.pending_rewards = rewards
        self._finish("RIP")
