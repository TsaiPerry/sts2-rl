from __future__ import annotations

from .base import Relic, RelicRarity, RestSiteOption, register_relic


@register_relic
class Girya(Relic):
    """Girya.cs — start each combat with Strength equal to the times lifted
    at rest sites (0-3, via the LIFT rest-site option: LiftRestSiteOption
    just increments TimesLifted)."""

    id = "girya"
    name = "Girya"
    rarity = RelicRarity.RARE

    MAX_LIFTS = 3

    def __init__(self, times_lifted: int = 0) -> None:
        super().__init__()
        self.times_lifted = min(times_lifted, self.MAX_LIFTS)

    def on_combat_start(self) -> None:
        if self.times_lifted > 0:
            from ..cmds import PowerCmd
            from ..powers import StrengthPower
            PowerCmd.apply(
                self.hooks, self.player, StrengthPower, self.times_lifted,
                applier=self.player,
            )

    def modify_rest_site_options(self, run, options) -> None:
        if self.times_lifted >= self.MAX_LIFTS:
            return
        options.append(RestSiteOption("LIFT", lambda run: self._lift()))

    def _lift(self) -> None:
        self.times_lifted += 1
