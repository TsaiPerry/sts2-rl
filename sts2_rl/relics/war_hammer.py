from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WarHammer(Relic):
    """WarHammer.cs — after every Elite victory (AfterCombatVictory), upgrade
    4 random upgradable cards in the deck."""

    id = "war_hammer"
    name = "War Hammer"
    rarity = RelicRarity.ANCIENT

    CARDS = 4  # CardsVar(4)

    def after_combat_end(self, run, room_type) -> None:
        from ..rooms import RoomType

        if room_type != RoomType.ELITE or run.is_dead:
            return
        upgradable = run.upgradable_cards()
        count = min(self.CARDS, len(upgradable))
        # WarHammer.cs: Deck IsUpgradable cards,
        # StableShuffle(Rng.Niche).Take(count). StableShuffle sorts by ModelId
        # (CardModel.CompareTo — the game's UPPERCASE entry compared ordinally,
        # then the upgrade level) before the game UnstableShuffle.
        if run.rng_set is not None:
            from ..actmap import stable_shuffle
            from ..player import _compare_to_key
            chosen = stable_shuffle(
                list(upgradable), run.rng_set.niche, key=_compare_to_key,
            )[:count]
        else:
            chosen = run.rng.sample(upgradable, count)
        for card in chosen:
            card.upgrade()
