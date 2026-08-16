from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SpiteCard(Card):
    """Attack (Uncommon, 0E) — deal 5 damage; if you lost HP this turn, hit
    2 times instead.

    Source: Spite.cs
      Cost 0 | Attack | Uncommon | TargetType.AnyEnemy
      OnPlay: hitCount = Repeat(2) if the owner has a DamageReceivedEntry
        with UnblockedDamage > 0 this turn, else 1; attack 5 × hitCount
      OnUpgrade: repeat +1 (→ 3 hits)
    """
    id = "spite"
    name = "Spite"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 5
        self._repeat = 2
        # RepeatVar's printed base value (Spite.cs CanonicalVars) — this is
        # what base_hits/the game obs writer report regardless of the
        # runtime lost-hp-this-turn condition checked in on_play() below.
        self._hits = 2

    def _on_upgrade(self) -> None:
        self._repeat += 1
        self._hits = self._repeat

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        hits = self._repeat if ctx.combat.history.lost_hp_this_turn(ctx.player) else 1
        for _ in range(hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)

    def _should_glow_gold_internal(self, ctx) -> bool:
        # Spite.cs:18,46: LostHpThisTurn(owner.creature) -- unblocked damage
        # received by the owner this turn
        return ctx.combat.history.lost_hp_this_turn(ctx.player)
