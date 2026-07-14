"""Combat potions, mirroring STS2's PotionModel + PotionCmd (values taken from
the source models in src/Core/Models/Potions)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .combat import CombatCtx
    from .creatures import Creature


_POTION_CLASSES: dict[str, type[Potion]] = {}


def register_potion(cls: type[Potion]) -> type[Potion]:
    _POTION_CLASSES[cls.id] = cls
    return cls


def make_potion(potion_id: str) -> Potion:
    return _POTION_CLASSES[potion_id]()


class Potion:
    """Base class for potions. targeted potions require an enemy target."""

    id: str
    name: str
    targeted: bool = False
    # Mirrors whether a potion appears in the character/shared reward pools
    # (PotionReward). Event-only potions (Glowwater) set this False so the
    # sim's random_potion helper doesn't offer them.
    in_reward_pool: bool = True

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        return self.name


@register_potion
class FirePotion(Potion):
    """Deal 20 damage to target enemy (unpowered: not boosted by Strength or
    Vulnerable, but blockable — mirrors the source's ValueProp.Unpowered)."""

    id = "fire_potion"
    name = "Fire Potion"
    targeted = True
    DAMAGE = 20

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            ctx.hooks,
            target or ctx.enemy,
            self.DAMAGE,
            dealer=ctx.player,
            props=DamageProps.NON_CARD_UNPOWERED,
        )


@register_potion
class BlockPotion(Potion):
    """Gain 12 block (unpowered: unaffected by Dexterity/Frail)."""

    id = "block_potion"
    name = "Block Potion"
    BLOCK = 12

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import BlockCmd
        from .valueprops import DamageProps
        BlockCmd.apply(
            ctx.hooks, ctx.player, self.BLOCK, props=DamageProps.NON_CARD_UNPOWERED
        )


@register_potion
class StrengthPotion(Potion):
    """Gain 2 Strength."""

    id = "strength_potion"
    name = "Strength Potion"
    STRENGTH = 2

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import StrengthCmd
        StrengthCmd.apply(ctx.hooks, ctx.player, self.STRENGTH)


@register_potion
class BloodPotion(Potion):
    """Heal 20% of max HP."""

    id = "blood_potion"
    name = "Blood Potion"
    HEAL_PERCENT = 20

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import CreatureCmd
        heal = ctx.player.max_hp * self.HEAL_PERCENT // 100
        CreatureCmd.heal(ctx.hooks, ctx.player, heal)


@register_potion
class WeakPotion(Potion):
    """Apply 3 Weak to target enemy."""

    id = "weak_potion"
    name = "Weak Potion"
    targeted = True
    WEAK = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import WeakPower
        PowerCmd.apply(
            ctx.hooks, target or ctx.enemy, WeakPower, self.WEAK, applier=ctx.player
        )


@register_potion
class GlowwaterPotion(Potion):
    """Exhaust your whole hand, then draw 10 cards.

    Source: GlowwaterPotion.cs — Event rarity, CombatOnly. Granted by the
    Drowning Beacon event (not part of the random reward pool)."""

    id = "glowwater"
    name = "Glowwater Potion"
    in_reward_pool = False
    DRAW = 10

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DrawCmd, ExhaustCmd
        for card in list(ctx.player.hand):
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, card)
        DrawCmd.draw(ctx.player, self.DRAW)


ALL_POTIONS: dict[str, type[Potion]] = dict(_POTION_CLASSES)
