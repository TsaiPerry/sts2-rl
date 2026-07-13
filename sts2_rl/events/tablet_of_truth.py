from __future__ import annotations

from .base import Event, EventOption, register_event

_SMASH_HEAL = 20        # DynamicVar("SmashHPGain", 20)
_INITIAL_COST = 3       # DynamicVar("DecipherMaxHpLoss", 3)
_MAX_DECIPHERS = 5


@register_event
class TabletOfTruth(Event):
    """Tablet of Truth — smash it to heal, or keep deciphering at rising cost.

    Source: TabletOfTruth.cs
      SMASH: heal 20 HP
      DECIPHER (up to 5 times): lose max HP (3, then 6, 12, 24, then
      max HP - 1) and upgrade a random upgradable card — the 5th decipher
      upgrades EVERY upgradable card. If the cost is >= your max HP you are
      reduced to 1 max HP and killed. After each decipher (except the last),
      GIVE_UP ends the event.
    """

    id = "tablet_of_truth"
    name = "Tablet of Truth"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.decipher_count = 0
        self.decipher_cost = _INITIAL_COST

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("DECIPHER", self._decipher),
            EventOption("SMASH", self._smash),
        ]

    def _smash(self) -> None:
        self.run.heal(_SMASH_HEAL)
        self._finish("SMASH")

    def _give_up(self) -> None:
        self._finish("GIVE_UP")

    def _next_cost(self) -> int:
        # TabletOfTruth.GetDecipherCost, keyed by deciphers done so far.
        return {1: 6, 2: 12, 3: 24, 4: self.run.max_hp - 1}[self.decipher_count]

    def _decipher(self) -> None:
        self._lose_max_hp_and_upgrade(self.decipher_cost)
        self.decipher_count += 1
        if self.run.is_dead or self.decipher_count == _MAX_DECIPHERS:
            self._finish(f"DECIPHER_{self.decipher_count}")
            return
        self.decipher_cost = self._next_cost()
        self._set_state(
            f"DECIPHER_{self.decipher_count}",
            [
                EventOption("DECIPHER", self._decipher),
                EventOption("GIVE_UP", self._give_up),
            ],
        )

    def _lose_max_hp_and_upgrade(self, cost: int) -> None:
        # LoseMaxHpAndUpgrade: a cost at or above max HP drops you to 1 max HP
        # and kills you outright.
        if cost >= self.run.max_hp:
            self.run.lose_max_hp(self.run.max_hp - 1)
            self.run.kill()
            return
        self.run.lose_max_hp(cost)
        upgradables = self.run.upgradable_cards()
        if self.decipher_count == _MAX_DECIPHERS - 1:
            # The 5th decipher upgrades the whole deck.
            for card in upgradables:
                card.upgrade()
        elif upgradables:
            self.rng.choice(upgradables).upgrade()  # Rng.NextItem
