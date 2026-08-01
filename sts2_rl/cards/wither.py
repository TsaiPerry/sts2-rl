from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class WitherCard(Card):
    """Unplayable status card (the Aeonglass boss). At the end of a turn spent
    in hand it deals 3 unpowered damage to its owner, +3 per fake upgrade.

    Source: Wither.cs — MaxUpgradeLevel 0, Unplayable, HasTurnEndInHandEffect,
    base damage 3 (Unpowered | Move), grows via FakeUpgrade (+3). The
    Aeonglass "Increasing Intensity" move fake-upgrades every existing Wither
    and matches newly generated ones to its upgrade count."""

    id = "wither"
    name = "Wither"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    has_turn_end_in_hand_effect = True

    _BASE_DAMAGE = 3

    def _init_vars(self) -> None:
        self._energy_cost = -1
        self.fake_upgrade_level = 0

    @property
    def damage(self) -> int:
        return self._BASE_DAMAGE + self._BASE_DAMAGE * self.fake_upgrade_level

    @property
    def base_damage(self) -> int:
        """Overrides `Card.base_damage` (which reads a static `_damage`
        instance attribute -- Wither.cs:44's DamageVar). Wither has no such
        attribute because its printed damage grows via FakeUpgrade rather
        than the ordinary `upgrade_level`/`_on_upgrade` path (Wither.cs:65
        mutates the DynamicVar directly); reporting `self.damage` here
        surfaces the exact live number `on_turn_end_in_hand` already deals,
        instead of the base class's None default.
        """
        return self.damage

    def fake_upgrade(self) -> None:
        """Mirrors Wither.FakeUpgrade — +3 to the printed damage."""
        self.fake_upgrade_level += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.player, self.damage, dealer=None, card=self)
