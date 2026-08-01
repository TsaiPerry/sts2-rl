"""Knowledge Demon's Curse of Knowledge choice cards.

Source: Disintegration.cs / MindRot.cs / Sloth.cs / WasteAway.cs — Status cards
implementing KnowledgeDemon.IChoosable. They are never added to a pile: the
player is shown a pair on a choose-a-card screen and the chosen card's
OnChosen() immediately applies its power to the player. The sim mirrors that
via CombatState.select_cards (purpose "curse_of_knowledge") and applies
`power_cls` / `power_amount` of the chosen card.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


class _ChoosableCurse(Card):
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    max_upgrade_level = 0
    is_unpowered = True
    # Disintegration.cs:16 / MindRot.cs:14 / Sloth.cs:16 / WasteAway.cs:15 all
    # override `CanBeGeneratedInCombat => false`; none of the four overrides
    # `CanBeGeneratedByModifiers` (CardModel.cs:648's default stays `=> true`)
    # and none declares a `CanonicalKeywords` override (CardModel.cs:498's
    # empty-array default applies, so `CardKeyword.Unplayable` is never
    # added) -- so in the game these are PLAYABLE no-effect Statuses, the
    # same shape as Beckon (cards/beckon.py), gated only from in-combat
    # generation, not from being played or from random-curse generation.
    # `is_playable` therefore stays at the base class's True default.
    can_be_generated_in_combat = False

    #: Power applied to the player when this curse is chosen (set by subclass).
    power_cls: type | None = None

    def _init_vars(self) -> None:
        self._energy_cost = -1
        # Disintegration's amount scales with the Curse of Knowledge counter
        # (6/7/8); the others are fixed.
        self.power_amount = self.default_power_amount

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass


@register_card
class DisintegrationCard(_ChoosableCurse):
    """Chosen: take 6/7/8 unpowered damage at the end of each of your turns."""
    id = "disintegration"
    name = "Disintegration"
    default_power_amount = 6

    @property
    def power_cls(self):
        from ..powers import DisintegrationPower
        return DisintegrationPower


@register_card
class MindRotCard(_ChoosableCurse):
    """Chosen: draw 1 fewer card each turn."""
    id = "mind_rot"
    name = "Mind Rot"
    default_power_amount = 1

    @property
    def power_cls(self):
        from ..powers import MindRotPower
        return MindRotPower


@register_card
class SlothCard(_ChoosableCurse):
    """Chosen: you can only play 3 cards per turn."""
    id = "sloth"
    name = "Sloth"
    default_power_amount = 3

    @property
    def power_cls(self):
        from ..powers import SlothPower
        return SlothPower


@register_card
class WasteAwayCard(_ChoosableCurse):
    """Chosen: gain 1 less energy at the start of each turn."""
    id = "waste_away"
    name = "Waste Away"
    default_power_amount = 1

    @property
    def power_cls(self):
        from ..powers import WasteAwayPower
        return WasteAwayPower
