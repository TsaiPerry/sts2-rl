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
        #
        # The sim reimplemented the whole verb inline and, unlike card/cascade,
        # called `card.on_play(...)` directly — which skipped the entire play
        # bracket that `_resolve_card_play` provides: the BeforeCardPlayed /
        # AfterCardPlayed pair (so Free Attack never fired), the play-count loop
        # seeded from `1 + base_replay_count` (so a Hidden-Gem'd card played
        # once instead of twice), the before_attack / after_attack bracket (so
        # Akabeko's Vigor was not consumed), the in-loop EnchantmentModel.OnPlay
        # call, and `captured_x` (so an auto-played Whirlwind did nothing). It
        # also hand-rolled the reshuffle with an UNSTABLE shuffle and hand-moved
        # the card to the exhaust pile, which sent an unplayable Burn to the
        # exhaust for the wrong reason and could not fire AfterCardExhausted
        # through CardCmd.Exhaust.
        CardPileCmd.auto_play_from_draw_pile(
            ctx.hooks, ctx.player, 1, position="top", force_exhaust=True)
