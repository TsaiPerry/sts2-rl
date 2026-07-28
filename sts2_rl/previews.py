"""Pure damage/block/cost previews — the numbers the game shows the player.

The game runs the full modifier pipeline for every displayed number: intent
damage goes through `Hook.ModifyDamage(..., ValueProp.Move, ...)` in
`AttackIntent.GetSingleDamage` (src/Core/MonsterMoves/Intents/AttackIntent.cs),
and card faces print fully modified values (`CardModel.UpdateDynamicVarPreview`).
This module mirrors that: each helper replays the exact modifier stages of
`DamageCmd.deal` / `BlockCmd.apply` (cmds.py) as *pure reads* — modifier hooks
are stateless by design (state changes live in event hooks), and no Cmd is
called — so previewing can never mutate combat state.

Used by the RL env (full_env.py) to expose pipeline-accurate incoming-damage
and card-value features, and usable by any policy that needs lethal math.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .monsters.base import MoveType
from .valueprops import DamageProps, ValueProp, is_powered_attack

if TYPE_CHECKING:
    from .cards import Card
    from .combat import CombatState
    from .creatures import Creature
    from .hooks import HookSystem
    from .monsters import Monster


@dataclass(frozen=True)
class AttackPreview:
    """A telegraphed enemy attack, fully modified (what the intent displays).

    per_hit / total are pre-block (the displayed numbers); post_block is the
    HP the player would actually lose against their current block, absorbing
    block hit by hit and applying modify_hp_lost exactly as DamageCmd will.
    """

    per_hit: int
    hits: int
    total: int
    post_block: int


def _modified_damage(
    hooks: HookSystem,
    target: Creature,
    amount: int,
    dealer: Creature | None,
    card: Card | None,
    props: ValueProp,
) -> int:
    """Steps 1–2 of DamageCmd.deal: the modifier passes, then the damage cap.

    Mirrors DamageCmd.deal exactly — the source card's enchantment folds in
    first, then every listener is called and self-gates on props. Pure-read, so
    it passes no `modifiers` list and notifies nobody.
    """
    ench = card.enchantment if card is not None else None
    if ench is not None:
        amount += ench.enchant_damage_additive(amount, props)
        amount *= ench.enchant_damage_multiplicative(amount, props)
    amount = amount + hooks.modify_damage_additive(
        target, amount, dealer, card, None, props)
    amount = int(hooks.modify_damage_multiplicative(
        target, amount, dealer, card, None, props))
    cap = hooks.modify_damage_cap(target, dealer, card)
    if cap is not None:
        amount = min(amount, cap)
    return max(0, amount)


def _post_block_hp_loss(
    hooks: HookSystem,
    target: Creature,
    per_hit: int,
    hits: int,
    dealer: Creature | None,
    block: int,
) -> tuple[int, int]:
    """Steps 4–5 of DamageCmd.deal per hit: block absorption then
    modify_hp_lost. Returns (hp lost, block remaining)."""
    lost = 0
    for _ in range(hits):
        hp = per_hit
        if block > 0:
            absorbed = min(block, hp)
            block -= absorbed
            hp -= absorbed
        if hp > 0:
            hp = hooks.modify_hp_lost(target, hp, dealer, None)
        lost += hp
    return lost, block


def preview_incoming_damage(combat: CombatState, enemy: Monster) -> AttackPreview | None:
    """Preview an enemy's telegraphed attack against the player.

    Mirrors AttackIntent.GetSingleDamage: the intent's per-hit damage through
    the full modifier pipeline (enemy Strength/Weak, player Vulnerable,
    Intangible cap) with MOVE props — exactly what DamageCmd.deal will compute
    when the enemy takes its turn. Returns None when the enemy is gone,
    stunned (it will skip the move), or not attacking.
    """
    if enemy.is_gone or enemy.stunned:
        return None
    intent = enemy.current_intent
    if not intent.has(MoveType.ATTACK):
        return None
    player = combat.player
    per_hit = _modified_damage(
        combat.hooks, player, intent.damage, enemy, None, DamageProps.MONSTER_MOVE
    )
    post_block, _ = _post_block_hp_loss(
        combat.hooks, player, per_hit, intent.hits, enemy, player.block
    )
    return AttackPreview(per_hit, intent.hits, per_hit * intent.hits, post_block)


def preview_total_incoming(combat: CombatState) -> int:
    """Post-block HP the player stands to lose to every telegraphed attack
    this turn, absorbing block sequentially in enemy order — the number an
    end-turn decision hinges on."""
    block = combat.player.block
    total = 0
    for enemy in combat.enemies:
        if enemy.is_gone or enemy.stunned:
            continue
        intent = enemy.current_intent
        if not intent.has(MoveType.ATTACK):
            continue
        per_hit = _modified_damage(
            combat.hooks, combat.player, intent.damage, enemy, None,
            DamageProps.MONSTER_MOVE,
        )
        lost, block = _post_block_hp_loss(
            combat.hooks, combat.player, per_hit, intent.hits, enemy, block
        )
        total += lost
    return total


def card_base_damage(
    combat: CombatState, card: Card, target: Creature | None = None
) -> int | None:
    """The card's printed per-hit damage before modifiers.

    Prefers the card's calc_damage(ctx, target) when it computes damage from
    combat state (Body Slam, Perfected Strike, ...); otherwise the declared
    base_damage. None for cards that deal no enemy damage.
    """
    calc = getattr(card, "calc_damage", None)
    if calc is not None:
        return calc(combat._ctx(), target)
    return card.base_damage


def preview_card_damage(
    combat: CombatState, card: Card, target: Creature
) -> int | None:
    """Fully modified per-hit damage this card would deal to target — the
    number the game prints on the card face for that target."""
    base = card_base_damage(combat, card, target)
    if base is None:
        return None
    props = DamageProps.CARD_UNPOWERED if card.is_unpowered else DamageProps.CARD
    return _modified_damage(combat.hooks, target, base, combat.player, card, props)


def preview_card_block(combat: CombatState, card: Card) -> int | None:
    """Fully modified block this card would grant the player (Dexterity,
    Frail) — mirrors BlockCmd.apply's powered pipeline. None for cards that
    grant no block."""
    base = card.base_block
    if base is None:
        return None
    hooks = combat.hooks
    player = combat.player
    ench = card.enchantment
    amount = base
    if ench is not None:
        amount += ench.enchant_block_additive(amount, ValueProp.MOVE)
        amount *= ench.enchant_block_multiplicative(amount, ValueProp.MOVE)
    amount = amount + hooks.modify_block_additive(
        player, amount, card, None, ValueProp.MOVE)
    amount = int(hooks.modify_block_multiplicative(
        player, amount, card, None, ValueProp.MOVE))
    return max(0, amount)


def preview_card_energy_cost(combat: CombatState, card: Card) -> int:
    """The energy actually spent to play the card right now: the hook-modified
    effective cost, or ALL remaining energy for X-cost cards (mirrors
    play_card's cost resolution)."""
    if card.energy_cost_x:
        return combat.player.energy
    return combat.hooks.modify_card_energy_cost(card, card.energy_cost)
