"""Mad Science — the configurable card granted by the Tinker Time event.

Source: MadScience.cs / TinkerTime.cs. One card whose type (Attack / Skill /
Power) and "rider" effect are chosen during the event; it is added to the deck
carrying that configuration. Base effect by type: Attack deals 12, Skill gains
8 block, Power just applies its rider. Upgrading makes it Innate.

Riders by type (each type only ever gets its own three):
  Attack: Sapping (Weak 2 + Vulnerable 2), Violence (3 hits), Choking (Strangle 6)
  Skill:  Energized (+2 energy), Wisdom (draw 3), Chaos (add a random free card)
  Power:  Expertise (Strength 2 + Dexterity 2), Curious (1), Improvement (1)
The Chaos rider draws from the Ironclad combat pool (the sim's stand-in for the
character pool).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx

# Attack/Skill/Power rider groupings and canonical amounts (MadScience.cs).
_ATTACK_RIDERS = frozenset({"sapping", "violence", "choking"})
_SKILL_RIDERS = frozenset({"energized", "wisdom", "chaos"})
_POWER_RIDERS = frozenset({"expertise", "curious", "improvement"})
ALL_RIDERS = _ATTACK_RIDERS | _SKILL_RIDERS | _POWER_RIDERS

_ATTACK_DAMAGE = 12
_SKILL_BLOCK = 8
_SAPPING_WEAK = 2
_SAPPING_VULNERABLE = 2
_VIOLENCE_HITS = 3
_CHOKING_STRANGLE = 6
_ENERGIZED_ENERGY = 2
_WISDOM_CARDS = 3
_EXPERTISE_STRENGTH = 2
_EXPERTISE_DEXTERITY = 2
_CURIOUS_REDUCTION = 1
_IMPROVEMENT = 1

_RIDER_TYPE = {
    CardType.ATTACK: _ATTACK_RIDERS,
    CardType.SKILL: _SKILL_RIDERS,
    CardType.POWER: _POWER_RIDERS,
}


@register_card
class MadScienceCard(Card):
    """Cost 1. Type and rider are set by Tinker Time via `configure`; the
    defaults (Attack / no rider) match the card's canonical constructor.

    Source: MadScience.cs — OnPlay dispatches on the chosen type, then applies
    the rider; OnUpgrade adds Innate."""

    id = "mad_science"
    name = "Mad Science"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY
    can_be_generated_by_modifiers = False

    # Configuration lives on the instance (set by `configure`); class defaults
    # keep a bare make_card("mad_science") valid and survive downgrade's
    # _init_vars rebuild (which does not touch these).
    tinker_type: CardType = CardType.ATTACK
    rider: str = "none"

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = _ATTACK_DAMAGE
        self._block = _SKILL_BLOCK
        self.innate = False  # re-derived by downgrade; set True on upgrade

    def _on_upgrade(self) -> None:
        self.innate = True  # AddKeyword(Innate)

    def configure(self, tinker_type: CardType, rider: str) -> "MadScienceCard":
        """Set the card's type and rider (mirrors setting TinkerTimeType /
        TinkerTimeRider). Raises if the rider is not valid for the type."""
        if rider != "none" and rider not in _RIDER_TYPE[tinker_type]:
            raise ValueError(f"{rider!r} is not a valid rider for {tinker_type}")
        self.tinker_type = tinker_type
        self.card_type = tinker_type
        self.target_type = (
            TargetType.ANY_ENEMY if tinker_type == CardType.ATTACK else TargetType.SELF
        )
        self.rider = rider
        return self

    @property
    def base_damage(self) -> int | None:
        return self._damage if self.tinker_type == CardType.ATTACK else None

    @property
    def base_block(self) -> int | None:
        return self._block if self.tinker_type == CardType.SKILL else None

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        if self.tinker_type == CardType.ATTACK:
            self._play_attack(ctx, target_idx)
        elif self.tinker_type == CardType.SKILL:
            self._play_skill(ctx)
        else:
            self._play_power(ctx)

    # ── Type dispatch ────────────────────────────────────────────────────

    def _play_attack(self, ctx: CombatCtx, target_idx: int | None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import StranglePower, VulnerablePower, WeakPower
        target = ctx.resolve_target(target_idx)
        hits = _VIOLENCE_HITS if self.rider == "violence" else 1
        for _ in range(hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        if target.is_gone:
            return
        if self.rider == "sapping":
            PowerCmd.apply(ctx.hooks, target, WeakPower, _SAPPING_WEAK, applier=ctx.player)
            PowerCmd.apply(
                ctx.hooks, target, VulnerablePower, _SAPPING_VULNERABLE, applier=ctx.player
            )
        elif self.rider == "choking":
            PowerCmd.apply(
                ctx.hooks, target, StranglePower, _CHOKING_STRANGLE, applier=ctx.player
            )

    def _play_skill(self, ctx: CombatCtx) -> None:
        from ..cmds import BlockCmd, DrawCmd, EnergyCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        if self.rider == "energized":
            EnergyCmd.gain(ctx.hooks, ctx.player, _ENERGIZED_ENERGY)
        elif self.rider == "wisdom":
            DrawCmd.draw(ctx.player, _WISDOM_CARDS)
        elif self.rider == "chaos":
            from ..cards.pool import (
                get_distinct_for_combat_parity,
                random_pool_cards,
            )
            from ..cmds import CardPileCmd
            # MadScience.cs ExecuteRider/Chaos: one card from the character pool
            # via GetDistinctForCombat(..., 1, Rng.CombatCardGeneration) — a
            # single UnstableShuffle of the FilterForCombat'd pool, Take(1).
            # Parity routes to the CombatCardGeneration stream; legacy keeps the
            # shared-Random sample (byte-for-byte RL behaviour).
            crng = ctx.combat.combat_rng
            if crng.is_parity:
                cards = get_distinct_for_combat_parity(crng.card_gen, 1)
            else:
                cards = random_pool_cards(ctx.combat._rng, 1, distinct=True)
            for card in cards:
                card.set_free_this_turn()
                CardPileCmd.add_to_hand(ctx.hooks, ctx.player, card)

    def _play_power(self, ctx: CombatCtx) -> None:
        from ..cmds import PowerCmd
        from ..powers import (
            CuriousPower,
            DexterityPower,
            ImprovementPower,
            StrengthPower,
        )
        if self.rider == "expertise":
            PowerCmd.apply(
                ctx.hooks, ctx.player, StrengthPower, _EXPERTISE_STRENGTH, applier=ctx.player
            )
            PowerCmd.apply(
                ctx.hooks, ctx.player, DexterityPower, _EXPERTISE_DEXTERITY, applier=ctx.player
            )
        elif self.rider == "curious":
            PowerCmd.apply(
                ctx.hooks, ctx.player, CuriousPower, _CURIOUS_REDUCTION, applier=ctx.player
            )
        elif self.rider == "improvement":
            PowerCmd.apply(
                ctx.hooks, ctx.player, ImprovementPower, _IMPROVEMENT, applier=ctx.player
            )
