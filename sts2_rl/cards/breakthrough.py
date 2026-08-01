from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BreakthroughCard(Card):
    """Attack (Common, 1E) — deal 1 unblockable HP loss to self, then 9 damage to ALL enemies.

    Source: Breakthrough.cs
      Cost 1 | Attack | Common | TargetType.AllEnemies
      OnPlay:
        CreatureCmd.Damage(self, 1, Unblockable | Unpowered | Move)   ← bypasses block, no Strength
        DamageCmd.Attack(9).TargetingAllOpponents                      ← scales with Strength
      OnUpgrade: damage +4 (→ 13)

    handles_own_routing = True because the self-damage must fire exactly once
    regardless of how many enemies are alive; the framework's per-enemy loop
    would call on_play multiple times and repeat the self-damage.
    """
    id = "breakthrough"
    name = "Breakthrough"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ALL_ENEMIES
    handles_own_routing = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 9
        self._hp_loss = 1   # HpLossVar(1m), Breakthrough.cs:16 — no upgrade, no ascension

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        from ..valueprops import ValueProp

        # Breakthrough.cs:27 is `CreatureCmd.Damage(choiceContext,
        # Owner.Creature, DynamicVars.HpLoss.BaseValue, Unblockable | Unpowered
        # | Move, this)` — the FULL damage pipeline, with the damage modifiers,
        # the cap, Hook.AfterCurrentHpChanged, Hook.AfterDamageReceived, the
        # death check and Kill. The sim hand-rolled it (`p.hp = max(0, p.hp - 1)`
        # plus a bare on_hp_changed and a manual should_die/on_death), so
        # `on_damage_received` never fired and no damage modifier was consulted:
        # play Breakthrough holding Rupture and the game gains Strength while the
        # sim did not. The bypass also skipped the Intangible cap and Buffer.
        DamageCmd.deal(
            ctx.hooks, ctx.player, self._hp_loss, dealer=ctx.player, card=self,
            props=ValueProp.UNBLOCKABLE | ValueProp.UNPOWERED | ValueProp.MOVE)
        # Breakthrough.cs has no is_dead guard here -- C# unconditionally
        # awaits DamageCmd.Attack(...).TargetingAllOpponents(...).Execute()
        # next (Breakthrough.cs:28-30). No divergence to reproduce: the
        # per-enemy DamageCmd.deal below already carries dealer=ctx.player, and
        # DamageCmd.deal's own dealer.is_dead bail (cmds.py, mirrors
        # AttackCommand.Execute's Attacker.IsDead bail, AttackCommand.cs:528 --
        # checked once per hit-iteration, and Breakthrough is a single hit) is
        # a no-op on every enemy once the self-damage has killed the player --
        # see card/_is_dead_early_return (Task 27) and
        # test/test_is_dead_early_returns.py.
        # 9 (+ Strength) damage to each living enemy.
        for enemy in list(ctx.enemies):
            if not enemy.is_dead:
                DamageCmd.deal(ctx.hooks, enemy, self._damage, dealer=ctx.player, card=self)
                if ctx.player.is_dead:
                    break
