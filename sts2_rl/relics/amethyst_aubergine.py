from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic

@register_relic
class AmethystAubergine(Relic):
    """AmethystAubergine.cs — every combat-room reward screen carries an
    extra GoldReward(15). TryModifyRewards (the plain, non-Late pass) adds it
    for Monster/Elite/Boss rooms, except the final act's boss (whose screen
    the game skips entirely)."""

    id = "amethyst_aubergine"
    name = "Amethyst Aubergine"
    rarity = RelicRarity.COMMON
    is_allowed_in_shops = False  # AmethystAubergine.IsAllowedInShops

    GOLD = 15

    def modify_combat_rewards(self, run, rewards) -> None:
        from ..rooms import RoomType

        if rewards.room_type not in (
            RoomType.MONSTER, RoomType.ELITE, RoomType.BOSS,
        ):
            return
        if rewards.room_type == RoomType.BOSS and run.is_final_act:
            return
        # GoldReward is granted with the screen, like the room's own gold.
        rewards.gold += self.GOLD
        run.gain_gold(self.GOLD)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """AmethystAubergine.cs:20-23: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
