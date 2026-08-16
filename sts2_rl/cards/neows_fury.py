from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class NeowsFuryCard(Card):
    """Attack (Ancient, 1E) — deal 10 damage; return up to 2 chosen cards from
    your discard pile to your hand. Exhaust.

    Source: NeowsFury.cs
      Cost 1 | Attack | Ancient | TargetType.AnyEnemy | Exhaust
      CanBeGeneratedInCombat = false (only Neow's Torment grants it)
      OnPlay: attack 10 → FromCombatPile(discard, 0..2) → add to hand,
        capped at MaxCardsInHand
      OnUpgrade: damage +4 (→ 14), cards +1 (→ 3)

    Neow's Fury can never pick itself: while it resolves it is in the Play
    pile (CardModel.cs:1875), not the discard, and `NeowsFury.cs:39` passes
    `new CardSelectorPrefs(prompt, 0, num)` with NO filter of any kind. That
    used to need an explicit `c is not self` predicate here, because the sim
    parked a resolving card in the discard pile; round 13 (R5) made the Play
    pile real and the deviation is gone. Same de-hack as `headbutt.py`'s
    (R5-review RV-4).
    """

    id = "neows_fury"
    name = "Neow's Fury"
    card_type = CardType.ATTACK
    rarity = CardRarity.ANCIENT
    target_type = TargetType.ANY_ENEMY
    # NeowsFury.cs:15 — `CanBeGeneratedInCombat => false`. Set explicitly
    # since FilterForCombat reads CardModel.CanBeGeneratedInCombat directly
    # (CardModel.cs:642), not just rarity — same idiom as Feed / Hand of
    # Greed / Hidden Gem.
    can_be_generated_in_combat = False
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 10
        self._cards = 2

    def _on_upgrade(self) -> None:
        self._damage += 4
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd, DamageCmd
        from ..player import PlayerCombatState

        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        room = PlayerCombatState.MAX_HAND_SIZE - len(ctx.player.hand)
        count = min(self._cards, room)
        if count <= 0:
            return
        # NeowsFury.cs:39 — `CardSelectorPrefs(prompt, 0, num)` is a genuine
        # 0..num range (RequireManualConfirmation whenever MinSelect !=
        # MaxSelect), so the auto-select shortcut never fires; confirming
        # NONE is legal.
        chosen = CardSelectCmd.from_pile(
            ctx.hooks, ctx.player.discard_pile, "from_discard",
            count=count, min_select=0,
        )
        for card in chosen:
            ctx.player.discard_pile.remove(card)
            ctx.player.hand.append(card)
