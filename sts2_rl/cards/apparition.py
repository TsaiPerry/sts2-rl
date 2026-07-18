from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ApparitionCard(Card):
    """Apparition.cs — 1-cost Ancient Skill (Ethereal, Exhaust): gain 1
    Intangible (upgrade: loses Ethereal). Granted by Distinguished Cape."""

    id = "apparition"
    name = "Apparition"
    card_type = CardType.SKILL
    rarity = CardRarity.ANCIENT
    target_type = TargetType.SELF
    exhausts = True
    is_ethereal = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._intangible = 1

    def _on_upgrade(self) -> None:
        self.is_ethereal = False

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import IntangiblePower

        PowerCmd.apply(
            ctx.hooks, ctx.player, IntangiblePower, self._intangible,
            applier=ctx.player,
        )
