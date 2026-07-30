from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class MaulCard(Card):
    """Maul.cs — 1-cost Ancient Attack: deal 5 damage twice; then EVERY Maul
    in your combat deck (this one included) gains +1 damage for the rest of
    combat ("Increase"). Upgrade: 6 damage, +2 increase. Claws transforms
    chosen cards into these."""

    id = "maul"
    name = "Maul"
    card_type = CardType.ATTACK
    rarity = CardRarity.ANCIENT
    target_type = TargetType.ANY_ENEMY

    # `_extraDamage*`, the private field (Maul.cs:19, :72-76). `DowngradeInternal` rebuilds
    # the damage var from canonical and does NOT touch this, which is the
    # whole point: `AfterDowngraded` then re-adds it. Deliberately a CLASS
    # default rather than an `_init_vars` line, because `_init_vars` is what
    # the downgrade re-runs.
    _extra_damage = 0

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 5
        self._hits = 2
        self._increase = 1

    def _on_upgrade(self) -> None:
        self._damage += 1
        self._increase += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd

        target = ctx.resolve_target(target_idx)
        for _ in range(self._hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(
                ctx.hooks, target, self._damage, dealer=ctx.player, card=self,
            )
        for card in ctx.player.all_cards:
            if isinstance(card, MaulCard):
                card._buff_from_maul_play(self._increase)

    def _buff_from_maul_play(self, extra_damage: int) -> None:
        # Maul.cs:72-76 — the buff and the tally are the same statement.
        self._damage += extra_damage
        self._extra_damage += extra_damage

    def _after_downgraded(self) -> None:
        self._damage += self._extra_damage   # Maul.cs:66-70
