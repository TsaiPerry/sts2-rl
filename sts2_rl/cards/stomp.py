from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class StompCard(Card):
    """Attack (Uncommon, 3E) — deal 12 damage to ALL enemies; costs 1 less
    this turn for each Attack you played this turn.

    Source: Stomp.cs
      Cost 3 | Attack | Uncommon | TargetType.AllEnemies
      OnPlay: attack 12 targeting all opponents
      OnUpgrade: damage +3 (→ 15)
      AfterCardEnteredCombat(self): seed the discount from the number of
        attack plays already made this turn (for Stomps generated mid-turn;
        the game skips clones because their copied cost already carries the
        discount — this sim's clones are fresh instances, so seeding IS the
        carried-over discount)
      BeforeCardPlayed(attack): EnergyCost.AddThisTurn(-1) — fires wherever
        the card sits (hand, draw, discard), including for Stomp's own play
    """
    id = "stomp"
    name = "Stomp"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ALL_ENEMIES

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._damage = 12

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.enemies[target_idx] if target_idx is not None else ctx.enemy
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)

    # ── Card-level hooks (cost discount) ──────────────────────────────────

    def on_card_entered_combat(self, card: Card) -> None:
        if card is not self or self.combat is None:
            return
        plays = self.combat.history.attack_plays_this_turn()
        if plays > 0:
            self.add_cost_this_turn(-plays)

    def on_energy_spent(self, card: Card, amount: int) -> None:
        if card.card_type == CardType.ATTACK:
            self.add_cost_this_turn(-1)
