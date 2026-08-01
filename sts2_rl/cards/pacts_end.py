from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class PactsEndCard(Card):
    """Attack (Rare, 0E) — if you have 3+ cards in the exhaust pile, deal 17 damage to ALL enemies.

    Source: PactsEnd.cs
      Cost 0 | Attack | Rare | TargetType.AllEnemies
      CanDealDamage = exhaust pile count >= 3; otherwise the play does nothing
      OnUpgrade: damage +6 (→ 23)
    """
    id = "pacts_end"
    name = "Pact's End"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ALL_ENEMIES

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 17
        self._cards = 3     # CardsVar(3), PactsEnd.cs:18 — cards/base.py's
        # `magic_number` scans `_cards` (a `_MAGIC_ATTRS` entry); the old name
        # `_required_exhausted` was not in that tuple, so the printed 3 never
        # surfaced. No upgrade, no ascension branch.

    def _on_upgrade(self) -> None:
        self._damage += 6

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        if len(ctx.player.exhaust_pile) < self._cards:
            return
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
