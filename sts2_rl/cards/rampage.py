from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class RampageCard(Card):
    """Attack (Uncommon, 1E) — deal 9 damage; increase this card's damage by 5 each play.

    Source: Rampage.cs
      Cost 1 | Attack | Uncommon | TargetType.AnyEnemy
      OnPlay: Attack(damage), then damage += Increase (5)
      OnUpgrade: increase +4 (→ 9 per play)

    The damage growth lives on this card instance, mirroring the game's
    per-CardModel BaseValue mutation.
    """
    id = "rampage"
    name = "Rampage"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    # `_extraDamage*`, the private field (Rampage.cs:16, :24-38). `DowngradeInternal` rebuilds
    # the damage var from canonical and does NOT touch this, which is the
    # whole point: `AfterDowngraded` then re-adds it. Deliberately a CLASS
    # default rather than an `_init_vars` line, because `_init_vars` is what
    # the downgrade re-runs.
    _extra_damage = 0

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 9
        self._increase = 5

    def _on_upgrade(self) -> None:
        self._increase += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
        self._damage += self._increase
        self._extra_damage += self._increase   # Rampage.cs:52

    def _after_downgraded(self) -> None:
        # Rampage.cs:55-59 — re-add the accumulation the canonical rebuild
        # just discarded.
        self._damage += self._extra_damage
