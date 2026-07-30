from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class LastingCandy(Relic):
    """Every other combat, the card reward carries an extra Power option.

    Source: LastingCandy.cs — AfterCombatEnd counts combats, and
    TryModifyCardRewardOptions (LastingCandy.cs:100-136) APPENDS one Power
    card to a post-encounter reward's options while `IsInTriggeringCombat`.
    It is the game's only implementer of the EARLY (non-Late) pass, which is
    why the option is visible to every Late listener — the egg relics, Silver
    Crucible, Silken Tress, Glitter — whichever relic registered first.
    """

    id = "lasting_candy"
    name = "Lasting Candy"
    rarity = RelicRarity.UNCOMMON

    def __init__(self) -> None:
        super().__init__()
        self.combats_seen = 0

    @property
    def is_in_triggering_combat(self) -> bool:
        """LastingCandy.cs:68-78 — `CombatsSeen > 0 && CombatsSeen % 2 == 0`."""
        return self.combats_seen > 0 and self.combats_seen % 2 == 0

    def after_combat_end(self, run, room_type) -> None:
        self.combats_seen += 1

    def modify_card_reward_options(self, run, cards, options=None):
        from ..cards import CardType
        from ..rewards import CardCreationSource, create_reward_cards

        if options is None or options.source is not CardCreationSource.ENCOUNTER:
            return False
        if not self.is_in_triggering_combat:
            return False
        # `from c in creationOptions.GetPossibleCards(player) where c.Type ==
        # Power && options.TrueForAll(o => o.originalCard.Id != c.Id)` — the
        # Powers not already offered, falling back to ALL Powers in the pool
        # when the offer already holds every one of them.
        from ..cards.base import _CARD_CLASSES

        powers = [cid for cid in options.pool
                  if _CARD_CLASSES[cid].card_type is CardType.POWER]
        offered = {c.id for c in cards}
        candidates = [cid for cid in powers if cid not in offered] or powers
        if not candidates:
            return False
        # `new CardCreationOptions(enumerable, CardCreationSource.Other,
        # creationOptions.RarityOdds).WithFlags(NoModifyHooks |
        # NoCardPoolModifications)` then CreateForReward(owner, 1, options2):
        # Source Other means RollForRarity does NOT mutate the pity counters,
        # NoModifyHooks means this creation runs no hooks of its own, and the
        # absence of a NoUpgradeRoll flag means it still spends the upgrade
        # draw on the Rewards stream.
        added = create_reward_cards(
            run, options.odds_type, count=1,
            mutate_pity=False, modify_hooks=False, pool=candidates,
        )
        cards.extend(added)
        return True

    @classmethod
    def is_allowed(cls, run) -> bool:
        """LastingCandy.cs:80-98 — the pool's only MULTI-clause IsAllowed. Its
        tail is IsBeforeAct3TreasureChest, so the relic leaves the pools from
        floor 41. Its head (`p.Character is Ironclad && p.UnlockState
        .NumberOfRuns == 0`) vetoes the relic on a profile's very first
        Ironclad run and is unported on purpose: the sim has no profile /
        UnlockState model at all, so it behaves as a veteran profile always."""
        return is_before_act3_treasure_chest(run)
