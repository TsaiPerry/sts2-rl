from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ToyBox(Relic):
    """ToyBox.cs — upon pickup, obtain 4 WAX copies of grab-bag relics
    (RelicFactory.PullNextRelicFromFront ×4, IsWax = true). Every 3rd combat
    (CombatsSeen % 3 == 0) one wax relic MELTS — the sim removes it from the
    run's relics (a melted relic stops working)."""

    id = "toy_box"
    name = "Toy Box"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    RELICS = 4
    COMBATS_PER_MELT = 3

    def __init__(self) -> None:
        super().__init__()
        self.combats_seen = 0

    @property
    def is_used_up(self) -> bool:   # CombatsSeen >= Combats*Relics
        return self.combats_seen >= self.COMBATS_PER_MELT * self.RELICS

    def after_obtained(self, run) -> None:
        for _ in range(self.RELICS):
            relic = run.pull_relic_from_front()
            if relic is None:
                break
            relic.is_wax = True
            # ToyBox.cs:96 OFFERS the four (RewardsCmd.OfferCustom): each is
            # take-or-skip, and a declined one never runs its AfterObtained.
            run.offer_relic(relic)

    def after_combat_end(self, run, room_type) -> None:
        self.combats_seen += 1
        if self.combats_seen % self.COMBATS_PER_MELT != 0:
            return
        wax = next((r for r in run.relics if r.is_wax), None)
        if wax is not None:
            run.relics.remove(wax)
