from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class TrueGritCard(Card):
    """Skill (Common, 1E) — gain 7 block; exhaust a random card from your hand
    (upgraded: exhaust a CHOSEN card, via the combat's card selector).

    Source: TrueGrit.cs
      Cost 1 | Skill | Common | TargetType.Self
      OnPlay: GainBlock(7), then exhaust a random hand card
        (upgraded: CardSelectCmd.FromHand — player's choice)
      OnUpgrade: block +2 (→ 9), selection instead of random
    """
    id = "true_grit"
    gains_block = True  # CardModel.GainsBlock
    name = "True Grit"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 7

    def _on_upgrade(self) -> None:
        self._block += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, CardSelectCmd, ExhaustCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        if not ctx.player.hand:
            return
        if self.upgrade_level > 0:
            chosen = CardSelectCmd.from_hand(ctx.hooks, ctx.player, "exhaust")
            victim = chosen[0] if chosen else None
        else:
            # TrueGrit.cs (un-upgraded): RunState.Rng.CombatCardSelection
            # .NextItem over the hand — a random card to exhaust. Parity routes
            # to that stream; legacy keeps the shared random.Random pick.
            crng = ctx.combat.combat_rng
            if crng.is_parity:
                victim = crng.card_selection.choice(ctx.player.hand)
            else:
                victim = ctx.combat._rng.choice(ctx.player.hand)
        if victim is not None:
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, victim)
