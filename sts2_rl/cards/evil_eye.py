from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class EvilEyeCard(Card):
    """Skill (Uncommon, 1E) — gain 8 block; if a card was exhausted this turn,
    gain the block twice.

    Source: EvilEye.cs
      Cost 1 | Skill | Uncommon | TargetType.Self | GainsBlock
      OnPlay: blockGains = 2 if a CardExhaustedEntry happened this turn else 1;
        GainBlock(8) that many times (two separate gains, so on-block triggers
        like Juggernaut fire per gain)
      OnUpgrade: block +3 (→ 11)
    """
    id = "evil_eye"
    name = "Evil Eye"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 8

    def _on_upgrade(self) -> None:
        self._block += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd
        gains = 2 if ctx.combat.history.card_exhausted_this_turn() else 1
        for _ in range(gains):
            BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
