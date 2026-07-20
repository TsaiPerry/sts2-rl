from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ColossusCard(Card):
    """Skill (Uncommon, 1E) — gain 5 block; for 1 turn, attacks from Vulnerable
    enemies deal half damage to you.

    Source: Colossus.cs
      Cost 1 | Skill | Uncommon | TargetType.Self
      OnPlay: GainBlock(5, Move), then PowerCmd.Apply<ColossusPower>(1)
      OnUpgrade: block +3 (→ 8)
    """
    id = "colossus"
    gains_block = True  # CardModel.GainsBlock
    name = "Colossus"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 5

    def _on_upgrade(self) -> None:
        self._block += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import ColossusPower
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(ctx.hooks, ctx.player, ColossusPower, 1, applier=ctx.player)
