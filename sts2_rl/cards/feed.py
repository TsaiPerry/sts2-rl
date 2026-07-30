from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class FeedCard(Card):
    """Attack (Rare, 1E) — deal 10 damage; if Fatal, raise your max HP by 3. Exhaust.

    Source: Feed.cs
      Cost 1 | Attack | Rare | TargetType.AnyEnemy | Exhaust
      Fatal check: the attack killed the target (death-prevented targets such
      as Illusions don't count, which falls out of the is_dead check here).
      GainMaxHp raises max HP and heals the same amount.
      OnUpgrade: damage +2 (→ 12), max HP +1 (→ 4)
    """
    id = "feed"
    name = "Feed"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY
    exhausts = True
    # Feed.cs: CanBeGeneratedInCombat => false — excluded from FilterForCombat
    # (Attack Potion, Discovery, Vexing Puzzlebox, …).
    can_be_generated_in_combat = False

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 10
        self._max_hp = 3

    def _on_upgrade(self) -> None:
        self._damage += 2
        self._max_hp += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CreatureCmd, DamageCmd, should_trigger_fatal
        target = ctx.resolve_target(target_idx)
        # Feed.cs:38 — the power veto is read BEFORE the attack, because the
        # killing blow strips the very powers it asks about
        # (Creature.RemoveAllPowersAfterDeath). It is not death prevention:
        # the minion really dies, and only the Max HP is suppressed.
        fatal = should_trigger_fatal(target)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        if fatal and target.is_dead:
            ctx.player.max_hp += self._max_hp
            CreatureCmd.heal(ctx.hooks, ctx.player, self._max_hp)
