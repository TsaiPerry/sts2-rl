from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ArmamentsCard(Card):
    """Skill (Common, 1E) — gain 5 block; upgrade a CHOSEN card in your hand
    for the combat (upgraded: upgrade ALL upgradable cards in your hand).

    Source: Armaments.cs
      Cost 1 | Skill | Common | TargetType.Self | GainsBlock
      OnPlay: GainBlock(5), then CardSelectCmd.FromHandForUpgrade (filters
        IsUpgradable) → CardCmd.Upgrade; upgraded: upgrade every IsUpgradable
        card in hand instead
      OnUpgrade: no value change (behavior switch only)
    """
    id = "armaments"
    name = "Armaments"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, CardSelectCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        if self.upgrade_level > 0:
            for card in [c for c in ctx.player.hand if c.is_upgradable]:
                card.upgrade()
            return
        chosen = CardSelectCmd.from_hand(
            ctx.hooks, ctx.player, "upgrade",
            predicate=lambda c: c.is_upgradable,
        )
        if chosen:
            chosen[0].upgrade()
