from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BrightestFlameCard(Card):
    """BrightestFlame.cs — 0-cost Ancient Skill: gain 2 Energy, draw 2 cards,
    lose 1 Max HP (upgrade: 3 Energy, 3 cards). Granted by Storybook."""

    id = "brightest_flame"
    name = "Brightest Flame"
    card_type = CardType.SKILL
    rarity = CardRarity.ANCIENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._energy = 2
        self._cards = 2
        self._max_hp = 1

    def _on_upgrade(self) -> None:
        self._energy += 1
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CreatureCmd, DrawCmd, EnergyCmd

        EnergyCmd.gain(ctx.hooks, ctx.player, self._energy)
        DrawCmd.draw(ctx.player, self._cards)
        CreatureCmd.lose_max_hp(ctx.hooks, ctx.player, self._max_hp)
