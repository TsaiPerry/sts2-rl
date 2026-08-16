from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class OfferingCard(Card):
    """Skill (Rare, 0E) — lose 6 HP; gain 2 energy; draw 3 cards. Exhaust.

    Source: Offering.cs
      Cost 0 | Skill | Rare | TargetType.Self | Exhaust
      OnPlay: CreatureCmd.Damage(self, 6, Unblockable|Unpowered|Move),
      GainEnergy(2), Draw(3)
      OnUpgrade: draw +2 (→ 5)
    """
    id = "offering"
    name = "Offering"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._hp_loss = 6
        self._energy = 2
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._cards += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, DrawCmd, EnergyCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(ctx.hooks, ctx.player, self._hp_loss, card=self, props=DamageProps.CARD_HP_LOSS)
        # Offering.cs has no is_dead guard: C# unconditionally runs GainEnergy
        # then Draw. No divergence: DrawCmd/EnergyCmd already bail on
        # is_over_or_ending/is_ending (CardPileCmd.cs:800, PlayerCmd.cs:31).
        EnergyCmd.gain(ctx.hooks, ctx.player, self._energy)
        DrawCmd.draw(ctx.player, self._cards)
