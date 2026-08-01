"""Colorless Power cards (ColorlessCardPool.cs).

One class per card, numbers transcribed from src/Core/Models/Cards/<Name>.cs.
The pool's 11 multiplayer-only cards are excluded (FilterForPlayerCount).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class AutomationCard(Card):
    """Power (Uncommon, 1E) — every 10 cards you draw, gain 1 energy.

    Source: Automation.cs — AutomationPower(EnergyVar 1). OnUpgrade: cost -1.
    """
    id = "automation"
    name = "Automation"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._energy_gain = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import AutomationPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, AutomationPower, self._energy_gain,
            applier=ctx.player,
        )


@register_card
class CalamityCard(Card):
    """Power (Rare, 3E) — whenever you play an Attack, add a random Attack
    to your hand.

    Source: Calamity.cs — CalamityPower 1. OnUpgrade: cost -1.
    """
    id = "calamity"
    name = "Calamity"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 3

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import CalamityPower
        PowerCmd.apply(ctx.hooks, ctx.player, CalamityPower, 1, applier=ctx.player)


@register_card
class EntropyCard(Card):
    """Power (Rare, 1E) — at the start of each turn, transform 1 card in
    your hand into a random card.

    Source: Entropy.cs — EntropyPower(CardsVar 1). OnUpgrade: gains Innate.
    """
    id = "entropy"
    name = "Entropy"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._cards = 1
        self.innate = False

    def _on_upgrade(self) -> None:
        self.innate = True

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import EntropyPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, EntropyPower, self._cards, applier=ctx.player
        )


@register_card
class EternalArmorCard(Card):
    """Power (Rare, 3E) — gain 9 Plating.

    Source: EternalArmor.cs — PlatingPower 9. OnUpgrade +3.
    """
    id = "eternal_armor"
    name = "Eternal Armor"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._plating = 9

    def _on_upgrade(self) -> None:
        self._plating += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import PlatingPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, PlatingPower, self._plating, applier=ctx.player
        )


@register_card
class FastenCard(Card):
    """Power (Uncommon, 1E) — Defend cards grant 4 additional block.

    Source: Fasten.cs — FastenPower(ExtraBlock 4). OnUpgrade +2.
    """
    id = "fasten"
    name = "Fasten"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._extra = 4

    def _on_upgrade(self) -> None:
        self._extra += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import FastenPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, FastenPower, self._extra, applier=ctx.player
        )


@register_card
class MayhemCard(Card):
    """Power (Rare, 2E) — at the start of your turn, play the top card of
    your draw pile.

    Source: Mayhem.cs — MayhemPower 1. OnUpgrade: cost -1.
    """
    id = "mayhem"
    name = "Mayhem"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import MayhemPower
        PowerCmd.apply(ctx.hooks, ctx.player, MayhemPower, 1, applier=ctx.player)


@register_card
class NostalgiaCard(Card):
    """Power (Rare, 1E) — the first Attack or Skill you play each turn
    returns to the top of your draw pile.

    Source: Nostalgia.cs — NostalgiaPower 1. OnUpgrade: cost -1.
    """
    id = "nostalgia"
    name = "Nostalgia"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import NostalgiaPower
        PowerCmd.apply(ctx.hooks, ctx.player, NostalgiaPower, 1, applier=ctx.player)


@register_card
class PanacheCard(Card):
    """Power (Uncommon, 0E) — every time you play 5 cards, deal 10 damage to
    ALL enemies.

    Source: Panache.cs — PanachePower(PanacheDamage 10). OnUpgrade +4.
    """
    id = "panache"
    name = "Panache"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._power_amount = 10

    def _on_upgrade(self) -> None:
        self._power_amount += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import PanachePower
        PowerCmd.apply(
            ctx.hooks, ctx.player, PanachePower, self._power_amount,
            applier=ctx.player,
        )


@register_card
class PrepTimeCard(Card):
    """Power (Uncommon, 1E) — at the start of each turn, gain 4 Vigor.

    Source: PrepTime.cs — PrepTimePower 4. OnUpgrade +2.
    """
    id = "prep_time"
    name = "Prep Time"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._power_amount = 4

    def _on_upgrade(self) -> None:
        self._power_amount += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import PrepTimePower
        PowerCmd.apply(
            ctx.hooks, ctx.player, PrepTimePower, self._power_amount,
            applier=ctx.player,
        )


@register_card
class ProwessCard(Card):
    """Power (Uncommon, 1E) — gain 1 Strength and 1 Dexterity.

    Source: Prowess.cs — StrengthPower 1 + DexterityPower 1. OnUpgrade
    +1/+1.
    """
    id = "prowess"
    name = "Prowess"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._power_amount = 1

    def _on_upgrade(self) -> None:
        self._power_amount += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd, StrengthCmd
        from ..powers import DexterityPower
        StrengthCmd.apply(ctx.hooks, ctx.player, self._power_amount, card=self)
        PowerCmd.apply(
            ctx.hooks, ctx.player, DexterityPower, self._power_amount,
            applier=ctx.player,
        )


@register_card
class RollingBoulderCard(Card):
    """Power (Rare, 3E) — at the start of each turn, deal 5 damage to ALL
    enemies; the damage grows by 5 every turn.

    Source: RollingBoulder.cs — RollingBoulderPower 5 (IncrementAmount 5).
    OnUpgrade: starting damage +5.
    """
    id = "rolling_boulder"
    name = "Rolling Boulder"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._power_amount = 5
        # DynamicVar("IncrementAmount", 5m), RollingBoulder.cs:20 — the
        # per-turn growth the card face prints alongside the starting 5.
        # `magic_number` still reports `_power_amount` (it precedes `_increase`
        # in cards/base.py's _MAGIC_ATTRS scan order and IS the number the
        # game's own hover UI leads with), so this line only makes the second
        # printed number introspectable; it does not change any encoded obs
        # value. The growth itself is RollingBoulderPower.INCREMENT (powers.py,
        # outside this card's footprint) and is NOT rewired to read this — the
        # two already agree (5) and the power owns that behaviour.
        self._increase = 5

    def _on_upgrade(self) -> None:
        self._power_amount += 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import RollingBoulderPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, RollingBoulderPower, self._power_amount,
            applier=ctx.player,
        )


@register_card
class StratagemCard(Card):
    """Power (Uncommon, 1E) — whenever you shuffle your draw pile, choose a
    card from it to put into your hand.

    Source: Stratagem.cs — StratagemPower 1. OnUpgrade: cost -1.
    """
    id = "stratagem"
    name = "Stratagem"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import StratagemPower
        PowerCmd.apply(ctx.hooks, ctx.player, StratagemPower, 1, applier=ctx.player)
