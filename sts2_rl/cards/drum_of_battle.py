from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DrumOfBattleCard(Card):
    """Skill (Uncommon, 1E) — draw 2 cards. Whenever this card is exhausted,
    gain 2 energy.

    Source: DrumOfBattle.cs
      Cost 1 | Skill | Uncommon | TargetType.Self
      OnPlay: Draw(2)
      AfterCardExhausted(self): GainEnergy(2) × GeneratePlayCount (the
        play-count modifier chain; attack-only effects like One-Two Punch
        don't apply to this skill)
      OnUpgrade: energy +2 → +3 (cards drawn stays 2)
    """
    id = "drum_of_battle"
    name = "Drum of Battle"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._cards = 2
        self._energy = 2

    def _on_upgrade(self) -> None:
        self._energy += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DrawCmd
        DrawCmd.draw(ctx.player, self._cards)

    # ── Card-level hook: pays out whenever it is exhausted ────────────────

    def on_card_exhausted(self, card: Card,
                          caused_by_ethereal: bool = False) -> None:
        from ..cmds import EnergyCmd
        if card is not self or self.combat is None:
            return
        play_count = self.combat.hooks.modify_card_play_count(self, None, 1)
        for _ in range(play_count):
            EnergyCmd.gain(self.combat.hooks, self.combat.player, self._energy)
