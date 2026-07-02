from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class NotYetCard(Card):
    """Skill (Rare, 2E) — heal 10 HP. Exhaust.

    Source: NotYet.cs
      Cost 2 | Skill | Rare | TargetType.Self | Exhaust
      OnUpgrade: heal +3 (→ 13)
    """
    id = "not_yet"
    name = "Not Yet"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._heal = 10

    def _on_upgrade(self) -> None:
        self._heal += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CreatureCmd
        CreatureCmd.heal(ctx.hooks, ctx.player, self._heal)
