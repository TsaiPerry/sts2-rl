from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ThrashCard(Card):
    """Attack (Rare, 1E) — deal 4 damage twice; exhaust a random Attack from your
    hand and permanently add its damage to this card.

    Source: Thrash.cs
      Cost 1 | Attack | Rare | TargetType.AnyEnemy
      Damage 4 × 2 hits; then a random Attack in hand is exhausted and its
      (hook-modified) damage is added to this card's base damage.
      OnUpgrade: damage +2 (→ 6)
    """
    id = "thrash"
    name = "Thrash"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    # `_extraDamage*`, the private field (Thrash.cs:20, :72). `DowngradeInternal` rebuilds
    # the damage var from canonical and does NOT touch this, which is the
    # whole point: `AfterDowngraded` then re-adds it. Deliberately a CLASS
    # default rather than an `_init_vars` line, because `_init_vars` is what
    # the downgrade re-runs.
    _extra_damage = 0

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 4
        self._hits = 2

    def _on_upgrade(self) -> None:
        self._damage += 2

    def _absorbed_damage(self, ctx: CombatCtx, victim: Card) -> int:
        """The victim's damage after outgoing modifiers (mirrors Hook.ModifyDamage
        with a null target: Strength/Weak apply, target debuffs don't)."""
        from ..valueprops import DamageProps, is_powered_attack
        if hasattr(victim, "calc_damage"):
            amount = victim.calc_damage(ctx, None)
        else:
            amount = getattr(victim, "_damage", 0)
        props = DamageProps.CARD_UNPOWERED if victim.is_unpowered else DamageProps.CARD
        amount = ctx.hooks.modify_damage_additive(
            None, amount, ctx.player, victim, None, props)
        amount = int(ctx.hooks.modify_damage_multiplicative(
            None, amount, ctx.player, victim, None, props))
        return max(0, amount)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cards import CardType as CT
        from ..cmds import DamageCmd, ExhaustCmd
        target = ctx.resolve_target(target_idx)
        for _ in range(self._hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        attacks = [c for c in ctx.player.hand if c.card_type == CT.ATTACK]
        if attacks:
            # Thrash.cs: RunState.Rng.CombatCardSelection.NextItem over the
            # hand's Attacks (a random one to exhaust and absorb). Parity routes
            # to that stream; legacy keeps the shared random.Random pick.
            crng = ctx.combat.combat_rng
            if crng.is_parity:
                victim = crng.card_selection.choice(attacks)
            else:
                victim = ctx.combat._rng.choice(attacks)
            absorbed = self._absorbed_damage(ctx, victim)
            self._damage += absorbed
            self._extra_damage += absorbed   # Thrash.cs:71-72
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, victim)

    def _after_downgraded(self) -> None:
        self._damage += self._extra_damage   # Thrash.cs:77-81
