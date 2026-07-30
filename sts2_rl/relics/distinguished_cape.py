from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DistinguishedCape(Relic):
    """DistinguishedCape.cs — upon pickup, lose 9 Max HP and then add 3
    Apparition cards.

    `AfterObtained` (:30-41) is two statements in that order: `CreatureCmd
    .LoseMaxHp(..., DynamicVars.HpLoss.BaseValue, isFromCard: false)` with
    HpLossVar(9m) (:25, also pinned as `public const int maxHpLoss` at :15),
    then the CardsVar(3) Apparition adds.

    This docstring used to say the −9 came from the Vakuu OPTION instead —
    `RelicOption<DistinguishedCape>().ThatDecreasesMaxHp(9m)` (Vakuu.cs:38).
    It does not: `ThatDecreasesMaxHp` is `ThatWillKillPlayerIf(p =>
    p.MaxHp <= value)` (EventOption.cs:194-197), a UI flag that flashes the
    option red when taking it would be lethal. It applies no HP at all."""

    id = "distinguished_cape"
    name = "Distinguished Cape"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 3
    MAX_HP_LOSS = 9  # HpLossVar(9m), DistinguishedCape.cs:25

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.lose_max_hp(self.MAX_HP_LOSS)     # :31, BEFORE the card adds
        for _ in range(self.CARDS):
            run.add_card(make_card("apparition"))
