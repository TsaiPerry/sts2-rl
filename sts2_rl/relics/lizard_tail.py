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

    def should_die_late(self, creature: Creature) -> bool:
        # LizardTail.cs is the source's ONLY ShouldDieLate implementer,
        # and Hook.ShouldDie (Hook.cs:2229-2249) runs a COMPLETE
        # ShouldDie pass over every listener before it starts the Late
        # one. That ordering is the whole of damage_pipeline/N4: a
        # Fairy in a Bottle (a plain ShouldDie) must always be spent
        # before the Tail, and with one flat pass the sim spent
        # whichever happened to be registered first.
        if creature is self.player and not self._used:
            self._used = True
            self._heal_pending = True
            return False
        return True

    def after_preventing_death(self, creature: Creature) -> None:
        # LizardTail.cs:53-59 heals from AfterPreventingDeath, which
        # CreatureCmd.cs:567 dispatches to the vetoing listener on the
        # prevented-death arm. The sim hung the heal on on_damage_received,
        # which worked only while a prevented death was floored at 1 HP: now
        # that the corpse is left at 0 (CreatureCmd.cs:565) the killing-blow
        # guard skips AfterDamageReceived and the heal never ran.
        if creature is not self.player or not self._heal_pending:
            return
        self._heal_pending = False
        from ..cmds import CreatureCmd
        CreatureCmd.heal(self.hooks, self.player,
                         max(1, self.player.max_hp * self.HEAL_PCT // 100))
