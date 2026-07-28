from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..player import PlayerCombatState


@register_card
class HowlFromBeyondCard(Card):
    """Attack (Uncommon, 3E) — deal 16 damage to ALL enemies. At the end of
    your turn, if this card is in the exhaust pile, auto-play it.

    Source: HowlFromBeyond.cs
      Cost 3 | Attack | Uncommon | TargetType.AllEnemies
      OnPlay: attack 16 targeting all opponents
      AfterAutoPostPlayPhaseEntered: if this card's pile is Exhaust,
        CardCmd.AutoPlay(this) — the auto-play pulls it out of the exhaust
        pile and it resolves to the discard pile like a normal play
      OnUpgrade: damage +5 (→ 21)
    """
    id = "howl_from_beyond"
    name = "Howl from Beyond"  # localization cards.json HOWL_FROM_BEYOND.title
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ALL_ENEMIES

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._damage = 16

    def _on_upgrade(self) -> None:
        self._damage += 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.enemies[target_idx] if target_idx is not None else ctx.enemy
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)

    # ── Card-level hook: replays itself from the exhaust pile ─────────────

    def after_auto_post_play_phase_entered(self, player: PlayerCombatState) -> None:
        # HowlFromBeyond.cs:32 is AfterAutoPostPlayPhaseEntered.
        # The end-of-turn auto-play phase (same phase Stampede triggers in).
        if self.combat is None:
            return
        if self in self.combat.player.exhaust_pile:
            self.combat.auto_play_card(self)
