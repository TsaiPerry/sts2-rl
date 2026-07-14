from __future__ import annotations

from .base import Event, EventOption, register_event

_MAX_HP_GAIN = 2   # MaxHpVar(2)
_BASE_DAMAGE = 3   # DamageVar(3, Unblockable | Unpowered)
_HEAL = 10         # HealVar(10)
_MAX_LINGER = 9


@register_event
class AbyssalBaths(Event):
    """Abyssal Baths — immerse for Max HP at the cost of escalating damage.

    Source: AbyssalBaths.cs
      Each immersion: gain 2 Max HP, then take the current damage (unblockable,
      unpowered), and the damage rises by 1 for next time.
      IMMERSE: immerse once, then offer Linger / Exit.
      ABSTAIN: heal 10 and leave.
      LINGER:  immerse again (up to a death warning when the next hit is lethal).
      EXIT_BATHS: leave.
    """

    id = "abyssal_baths"
    name = "Abyssal Baths"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.damage = _BASE_DAMAGE
        self.linger_count = 0

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("IMMERSE", self._immerse),
            EventOption("ABSTAIN", self._abstain),
        ]

    def _on_immerse(self) -> None:
        # OnImmerse: GainMaxHp(2) (heals 2), take the current damage, damage += 1.
        self.run.gain_max_hp(_MAX_HP_GAIN)
        self.run.lose_hp(self.damage)
        self.damage += 1

    def _bath_options(self) -> list[EventOption]:
        return [
            EventOption("LINGER", self._linger),
            EventOption("EXIT_BATHS", self._exit_baths),
        ]

    def _immerse(self) -> None:
        self._on_immerse()
        self._set_state("IMMERSE", self._bath_options())

    def _abstain(self) -> None:
        self.run.heal(_HEAL)
        self._finish("ABSTAIN")

    def _linger(self) -> None:
        self.linger_count = min(self.linger_count + 1, _MAX_LINGER)
        self._on_immerse()
        # Net HP loss the next immersion would cost (damage already incremented).
        next_net = self.damage - _MAX_HP_GAIN
        if self.run.hp <= next_net:
            self._set_state("DEATH_WARNING", self._bath_options())
        else:
            self._set_state(f"LINGER{self.linger_count}", self._bath_options())

    def _exit_baths(self) -> None:
        self._finish("EXIT_BATHS")
