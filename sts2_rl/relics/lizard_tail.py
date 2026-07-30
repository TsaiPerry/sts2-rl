from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature
    from ..valueprops import ValueProp


@register_relic
class LizardTail(Relic):
    """When you would die, prevent it once and heal for 50% of your Max HP
    (mirrors ShouldDieLate + AfterPreventingDeath)."""

    id = "lizard_tail"
    name = "Lizard Tail"
    rarity = RelicRarity.RARE

    HEAL_PCT = 50

    def __init__(self) -> None:
        super().__init__()
        self._used = False

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
        # LizardTail.cs:40-51 is a PURE predicate: `creature != Owner.Creature
        # -> true`, `WasUsed -> true`, else false. It reads the flag and does not
        # touch it; the charge is spent in AfterPreventingDeath (:53-59, `WasUsed
        # = true` then the heal). The port set `_used` HERE, so any caller that
        # queried `should_die` without going on to the prevention path burned the
        # relic for nothing -- and a second query in the same breath answered the
        # wrong way. Enumerated 2026-07-29: `hooks.should_die(` has exactly ONE
        # caller (`cmds._resolve_death`) and it always continues to
        # `after_preventing_death`, so nothing observable was reaching the bad
        # path -- but the predicate is now the shape the source has.
        if creature is not self.player:
            return True
        return bool(self._used)

    def after_preventing_death(self, creature: Creature) -> None:
        # LizardTail.cs:53-59 heals from AfterPreventingDeath, which
        # CreatureCmd.cs:567 dispatches to the vetoing listener on the
        # prevented-death arm. The sim hung the heal on on_damage_received,
        # which worked only while a prevented death was floored at 1 HP: now
        # that the corpse is left at 0 (CreatureCmd.cs:565) the killing-blow
        # guard skips AfterDamageReceived and the heal never ran.
        # `Hook.AfterPreventingDeath` is dispatched to the VETOING listener
        # alone (CreatureCmd.cs:567; the sim's dispatcher walks the `preventer`
        # list), so there is nothing to re-check and no `_heal_pending` shim: this
        # runs exactly when this relic is the one that prevented the death.
        # Source order is `Flash(); WasUsed = true; Heal(...)`.
        if creature is not self.player:
            return
        self._used = True
        from ..cmds import CreatureCmd
        CreatureCmd.heal(self.hooks, self.player,
                         max(1, self.player.max_hp * self.HEAL_PCT // 100))
