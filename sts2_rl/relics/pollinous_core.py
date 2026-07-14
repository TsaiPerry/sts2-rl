from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PollinousCore(Relic):
    """Every 4 turns, draw 2 extra cards (ModifyHandDraw + a turn counter).

    Source: PollinousCore.cs. Granted by the Colossal Flower event. The
    once-every-4-turns hand-draw bonus is not modelled here (a documented
    stub); the relic is registered so the event's reward is constructible."""

    id = "pollinous_core"
    name = "Pollinous Core"
    rarity = RelicRarity.EVENT
