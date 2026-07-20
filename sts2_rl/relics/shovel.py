from __future__ import annotations

from .base import Relic, RelicRarity, RestSiteOption, register_relic


@register_relic
class Shovel(Relic):
    """Shovel.cs — the DIG rest-site option: pull the next relic from the
    front of the grab bag (RelicFactory.PullNextRelicFromFront), the same
    mechanism a treasure chest uses. Only offered while the bag has a relic
    left."""

    id = "shovel"
    name = "Shovel"
    rarity = RelicRarity.RARE

    def modify_rest_site_options(self, run, options) -> None:
        if not run.has_available_relics():
            return
        options.append(
            RestSiteOption("DIG", lambda run: run.obtain_relic_from_grab_bag())
        )
