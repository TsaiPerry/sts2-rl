from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class RegalPillow(Relic):
    """RegalPillow.cs — the rest site's heal is 15 HP larger.

    C# computes the heal as `Hook.ModifyRestSiteHealAmount(runState, creature,
    GetBaseHealAmount(creature))` where the base is `MaxHp * 0.3m`
    (HealRestSiteOption.cs:60-63, 90-93; MendRestSiteOption.cs:58 runs the same
    hook over the same base), and RegalPillow.cs:19-26 adds 15 to that chain.
    C# adds its integer 15 to the untruncated `MaxHp * 0.3m`, so truncating
    the base first coincides at every max HP.
    """

    id = "regal_pillow"
    name = "Regal Pillow"
    rarity = RelicRarity.COMMON

    HEAL = 15   # HealVar(15)

    def modify_rest_site_heal_amount(self, run, amount: int) -> int:
        return amount + self.HEAL
