from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BattleTranceCard(Card):
    """Skill (Uncommon, 0E) — draw 3 cards; you cannot draw additional cards
    this turn.

    Source: BattleTrance.cs
      Cost 0 | Skill | Uncommon | TargetType.Self
      OnPlay: CardPileCmd.Draw(3), then PowerCmd.Apply<NoDrawPower>(1)
      OnUpgrade: cards +1 (→ 4)
    """
    id = "battle_trance"
    name = "Battle Trance"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DrawCmd, PowerCmd
        from ..powers import NoDrawPower
        DrawCmd.draw(ctx.player, self._cards)
        PowerCmd.apply(ctx.hooks, ctx.player, NoDrawPower, 1, applier=ctx.player)
