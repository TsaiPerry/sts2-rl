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
        player = ctx.player
        # ShuffleIfNecessary: refill the draw pile from the discard pile.
        if not player.draw_pile and player.discard_pile:
            player.draw_pile = player.discard_pile
            player.discard_pile = []
            ctx.combat._rng.shuffle(player.draw_pile)
            ctx.hooks.on_shuffle(player)
        if not player.draw_pile:
            return
        card = player.draw_pile.pop()  # top of the draw pile

        if card.is_playable and ctx.hooks.should_play_card(card):
            living = [i for i, e in enumerate(ctx.enemies) if not e.is_gone]
            if card.target_type == TargetType.ALL_ENEMIES and not card.handles_own_routing:
                for i in living:
                    if not ctx.enemies[i].is_gone:
                        card.on_play(ctx, i)
                        if ctx.player.is_dead:
                            break
            else:
                idx = ctx.combat._rng.choice(living) if (card.target_type == TargetType.ANY_ENEMY and living) else None
                card.on_play(ctx, idx)
            ctx.hooks.on_card_played(card)

        # forceExhaust: the card ends up in the exhaust pile either way
        # (unplayable cards are moved there without playing). Powers vanish.
        if card.card_type != CardType.POWER:
            player.exhaust_pile.append(card)
            ctx.hooks.on_card_exhausted(card)
