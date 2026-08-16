from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ForgottenRitualCard(Card):
    """Skill (Uncommon, 1E) — if a card was exhausted this turn, gain 3
    energy. Exhaust.

    Source: ForgottenRitual.cs
      Cost 1 | Skill | Uncommon | TargetType.Self | Exhaust keyword
      OnPlay: if a CardExhaustedEntry happened this turn, GainEnergy(3).
        Its own Exhaust hasn't happened yet when the check runs (the keyword
        move fires after OnPlay), so a first Forgotten Ritual doesn't pay for
        itself but enables a second one.
      OnUpgrade: energy +1 (→ 4)
    """
    id = "forgotten_ritual"
    name = "Forgotten Ritual"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._energy = 3

    def _on_upgrade(self) -> None:
        self._energy += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import EnergyCmd
        if ctx.combat.history.card_exhausted_this_turn():
            EnergyCmd.gain(ctx.hooks, ctx.player, self._energy)

    def _should_glow_gold_internal(self, ctx) -> bool:
        # ForgottenRitual.cs:19,33: WasCardExhaustedThisTurn -- same condition
        # as Evil Eye
        return ctx.combat.history.card_exhausted_this_turn()
