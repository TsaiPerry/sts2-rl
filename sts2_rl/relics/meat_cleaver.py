from __future__ import annotations

from .base import Relic, RelicRarity, RestSiteOption, register_relic


@register_relic
class MeatCleaver(Relic):
    """MeatCleaver.cs — adds the COOK rest-site option
    (CookRestSiteOption: remove 2 chosen deck cards, gain 9 Max HP; only
    enabled with at least 2 removable cards)."""

    id = "meat_cleaver"
    name = "Meat Cleaver"
    rarity = RelicRarity.ANCIENT

    CARDS = 2
    MAX_HP = 9

    def modify_rest_site_options(self, run, options) -> None:
        if len(run.removable_cards()) < self.CARDS:
            return                             # CookRestSiteOption.IsEnabled

        def cook(run) -> None:
            for card in run.select_cards(
                "remove", run.removable_cards(), self.CARDS,
            ):
                run.remove_cards([card])   # CardPileCmd.RemoveFromDeck
            run.gain_max_hp(self.MAX_HP)

        options.append(RestSiteOption("COOK", cook))
