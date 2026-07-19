from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature
    from ..valueprops import ValueProp


@register_relic
class LizardTail(Relic):
    """When you would die, prevent it once per combat and heal to 50% of your
    Max HP (mirrors ShouldDieLate + AfterPreventingDeath). The sim's death
    check resets prevented HP to 1, so the heal is applied in the immediately-
    following on_damage_received event."""

    id = "lizard_tail"
    name = "Lizard Tail"
    rarity = RelicRarity.RARE

    HEAL_PCT = 50

    def __init__(self) -> None:
        super().__init__()
        self._used = False
        self._heal_pending = False

    @property
    def is_used_up(self) -> bool:   # IsUsedUp => _wasUsed
        return self._used

    def should_die(self, creature: Creature) -> bool:
        if creature is self.player and not self._used:
            self._used = True
            self._heal_pending = True
            return False
        return True

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp,
    ) -> None:
        if self._heal_pending and target is self.player:
            self._heal_pending = False
            from ..cmds import CreatureCmd
            CreatureCmd.heal(self.hooks, self.player, max(1, self.player.max_hp * self.HEAL_PCT // 100))
