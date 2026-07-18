from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TouchOfOrobas(Relic):
    """TouchOfOrobas.cs — upon pickup, replace the starter relic with its
    refinement (RefinementUpgrades: Burning Blood → Black Blood for the
    Ironclad; RelicCmd.Replace swaps in place and runs AfterObtained). Only
    offered by Orobas when a starter relic is present (SetupForPlayer)."""

    id = "touch_of_orobas"
    name = "Touch of Orobas"
    rarity = RelicRarity.ANCIENT

    # RefinementUpgrades, restricted to the sim's single character.
    REFINEMENTS = {"burning_blood": "black_blood"}

    def after_obtained(self, run) -> None:
        from . import make_relic

        starter = next(
            (r for r in run.relics if r.rarity == RelicRarity.STARTER), None
        )
        if starter is None or starter.id not in self.REFINEMENTS:
            # The game falls back to Circlet for unknown starters; no other
            # starter is constructible in the sim.
            return
        upgraded = make_relic(self.REFINEMENTS[starter.id])
        run.relics[run.relics.index(starter)] = upgraded
        upgraded.after_obtained(run)
