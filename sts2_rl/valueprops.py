"""Damage/block typing — ValueProp flags and DamageProps combinations.

Every `DamageCmd.deal` / `BlockCmd.apply` is typed with `ValueProp` flags,
mirroring STS2's ValueProp. The flags decide which parts of the damage
pipeline apply: only MOVE-and-not-UNPOWERED ("powered") damage is boosted by
Strength/Vulnerable/Weak (`is_powered_attack`), and UNBLOCKABLE damage skips
block absorption. `DamageProps` bundles the common flag combinations by source
(card attack, monster move, HP-loss drawback, Poison, ...).
"""
from __future__ import annotations

from enum import IntFlag


class ValueProp(IntFlag):
    """Damage/block typing flags, mirroring STS2's ValueProp:

      UNBLOCKABLE — HP loss that ignores block (e.g. Poison)
      UNPOWERED   — not boosted by Strength / Vulnerable / Weak
                    (damage from relics, potions, powers, status cards)
      MOVE        — attack damage from Attack cards or enemy moves
    """

    NONE = 0
    UNBLOCKABLE = 2
    UNPOWERED = 4
    MOVE = 8


class DamageProps:
    """Common flag combinations, mirroring STS2's DamageProps."""

    # Normal damage done by a card.
    CARD = ValueProp.MOVE
    # Unpowered damage done by a card (Curse/Status cards damaging the player).
    CARD_UNPOWERED = ValueProp.UNPOWERED | ValueProp.MOVE
    # "Lose X HP" drawbacks on cards (e.g. Offering).
    CARD_HP_LOSS = ValueProp.UNBLOCKABLE | ValueProp.UNPOWERED | ValueProp.MOVE
    # Normal damage done by a monster move.
    MONSTER_MOVE = ValueProp.MOVE
    # Blockable damage from powers/relics/potions (e.g. Thorns, Fire Potion).
    NON_CARD_UNPOWERED = ValueProp.UNPOWERED
    # Unblockable HP loss from powers (e.g. Poison).
    NON_CARD_HP_LOSS = ValueProp.UNBLOCKABLE | ValueProp.UNPOWERED


def is_powered_attack(props: ValueProp) -> bool:
    """True for damage boosted by Strength/Vulnerable/Weak (mirrors IsPoweredAttack)."""
    return ValueProp.MOVE in props and ValueProp.UNPOWERED not in props


def is_powered_card_or_monster_move_block(props: ValueProp) -> bool:
    """The block-side twin of `is_powered_attack`
    (ValuePropExtensions.IsPoweredCardOrMonsterMoveBlock) — Dexterity, Frail
    and Fasten gate on this."""
    return ValueProp.MOVE in props and ValueProp.UNPOWERED not in props


def is_card_or_monster_move(props: ValueProp) -> bool:
    """`ValuePropExtensions.IsCardOrMonsterMove` (ValuePropExtensions.cs:23-26)
    — `props.HasFlag(ValueProp.Move)`, **Move alone**.

    Deliberately weaker than `is_powered_attack`: it PERMITS Unpowered. Three
    listeners gate on this and would be wrong under the powered test —
    UnmovablePower.cs:27-30, Vambrace.cs:59-63 and PaelsLegion.cs:132-134.
    Hoisting the powered gate into the pipeline is what stopped all three from
    ever running on Unpowered block (`damage_pipeline/G3`).
    """
    return ValueProp.MOVE in props
