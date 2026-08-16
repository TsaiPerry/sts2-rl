from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class HavocCard(Card):
    """Skill (Common, 1E) — play the top card of your draw pile and exhaust it.

    Source: Havoc.cs → CardPileCmd.AutoPlayFromDrawPile(count=1, Top, forceExhaust=true)
      Cost 1 | Skill | Common | TargetType.Self
      AutoPlay semantics (CardCmd.AutoPlay): unplayable or hook-blocked cards
      go straight to the exhaust pile without playing; AnyEnemy cards target a
      random living enemy; the card is played for free, then exhausted.
      Power cards vanish instead of exhausting.
      OnUpgrade: cost -1 (→ 0)
    """
    id = "havoc"
    name = "Havoc"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardPileCmd

        # Havoc.cs:21 is ONE line: `CardPileCmd.AutoPlayFromDrawPile(
        # choiceContext, Owner, 1, CardPilePosition.Top, forceExhaust: true)`.
        # Must route through the full play bracket (BeforeCardPlayed/
        # AfterCardPlayed, replay-count loop, before/after_attack, captured_x)
        # rather than calling `card.on_play` directly, and reshuffle must use
        # a STABLE shuffle — a prior inline reimplementation skipped both.
        CardPileCmd.auto_play_from_draw_pile(
            ctx.hooks, ctx.player, 1, position="top", force_exhaust=True)
