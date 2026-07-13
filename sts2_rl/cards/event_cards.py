"""Cards granted only by events — not part of any reward pool.

Sources: ByrdonisEgg.cs (Byrdonis Nest), Peck.cs and ToricToughness.cs
(Wood Carvings).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ByrdonisEggCard(Card):
    """Quest — Unplayable. Taken from the Byrdonis Nest event; in the game it
    adds a "Hatch" rest-site option (pet). The sim has no rest sites, so in
    combat it is simply an unplayable card clogging the deck.

    Source: ByrdonisEgg.cs
      Cost -1 | Quest | Quest | TargetType.None | Unplayable | MaxUpgradeLevel 0
    """
    id = "byrdonis_egg"
    name = "Byrdonis Egg"
    card_type = CardType.QUEST
    rarity = CardRarity.QUEST
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass


@register_card
class PeckCard(Card):
    """Attack (Event, 1E) — deal 2 damage 3 times.

    Source: Peck.cs
      Cost 1 | Attack | Event | TargetType.AnyEnemy
      OnPlay: Attack(2) × Repeat(3)
      OnUpgrade: repeat +1 (→ 4 hits)
    Granted by Wood Carvings (Bird), transforming a Basic card.
    """
    id = "peck"
    name = "Peck"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 2
        self._hits = 3

    def _on_upgrade(self) -> None:
        self._hits += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        for _ in range(self._hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)


@register_card
class ToricToughnessCard(Card):
    """Skill (Event, 2E) — gain 5 block; for the next 2 turns, gain 5 block
    after your block is cleared.

    Source: ToricToughness.cs
      Cost 2 | Skill | Event | TargetType.Self
      OnPlay: GainBlock(5, Move), then Apply ToricToughnessPower(2 turns)
              carrying the block actually gained
      OnUpgrade: block +2 (→ 7)
    Granted by Wood Carvings (Torus), transforming a Basic card.
    """
    id = "toric_toughness"
    name = "Toric Toughness"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._block = 5
        self._turns = 2

    def _on_upgrade(self) -> None:
        self._block += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import ToricToughnessPower
        gained = BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(
            ctx.hooks, ctx.player, ToricToughnessPower, self._turns, applier=ctx.player
        )
        power = ctx.player.powers.get("toric_toughness")
        if power is not None:
            power.set_block(gained)
