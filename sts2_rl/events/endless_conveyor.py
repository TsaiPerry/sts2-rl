from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from ..cards.pool import random_pool_cards
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_GRAB_COST = 40          # GoldVar(40)
_GOLDEN_FYSH_GOLD = 75   # GoldVar("GoldenFyshGold", 75)
_CLAM_ROLL_HEAL = 10     # HealVar("ClamRollHeal", 10)
_CAVIAR_MAX_HP = 4       # MaxHpVar("CaviarMaxHp", 4)
_MIN_GOLD = 120          # IsAllowed threshold


@register_event
class EndlessConveyor(Event):
    """Endless Conveyor — grab dishes off the belt (40 gold each), or observe.

    Source: EndlessConveyor.cs
      IsAllowed: gold >= 120
      A weighted dish is rolled each grab (every 5th grab is a forced Seapunk
      Salad). Grabbing costs 40 gold unless the dish is a Golden Fysh.
        CAVIAR (+4 Max HP), SPICY_SNAPPY (upgrade a random card),
        JELLY_LIVER (transform 1 card), FRIED_EEL (add a random colourless card),
        SUSPICIOUS_CONDIMENT (a random potion), CLAM_ROLL (heal 10),
        GOLDEN_FYSH (+75 gold, free to grab), SEAPUNK_SALAD (add Feeding Frenzy)
      OBSERVE_CHEF: upgrade a random card and leave.
    """

    id = "endless_conveyor"
    name = "Endless Conveyor"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.num_of_grabs = 0
        self.last_dish_id = ""
        self.current_dish_id = ""
        self._current_action = None

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.gold >= _MIN_GOLD

    def calculate_vars(self) -> None:
        self._roll_dish()

    # ── Dish rolling (RollDish) ──────────────────────────────────────────

    def _roll_dish(self) -> None:
        self.num_of_grabs += 1
        if self.num_of_grabs % 5 == 0:
            self.last_dish_id = "SEAPUNK_SALAD"
            self.current_dish_id = "SEAPUNK_SALAD"
            self._current_action = self._seapunk_salad
            return
        dishes = [
            ("CAVIAR", 6.0, self._caviar),
            ("SPICY_SNAPPY", 3.0, self._spicy_snappy),
            ("JELLY_LIVER", 3.0, self._jelly_liver),
            ("FRIED_EEL", 3.0, self._fried_eel),
        ]
        if len(self.run.potions) < self.run.MAX_POTIONS:
            dishes.append(("SUSPICIOUS_CONDIMENT", 3.0, self._suspicious_condiment))
        if self.run.hp != self.run.max_hp:
            dishes.append(("CLAM_ROLL", 6.0, self._clam_roll))
        if self.num_of_grabs > 1:
            dishes.append(("GOLDEN_FYSH", 1.0, self._golden_fysh))
        dishes = [d for d in dishes if d[0] != self.last_dish_id]

        total = sum(w for _, w, _ in dishes)
        roll = self.rng.random() * total  # Rng.NextFloat() * total
        acc = 0.0
        for did, weight, action in dishes:
            acc += weight
            if roll < acc:
                self.last_dish_id = did
                self.current_dish_id = did
                self._current_action = action
                break

    # ── Dishes ───────────────────────────────────────────────────────────

    def _caviar(self) -> None:
        self.run.gain_max_hp(_CAVIAR_MAX_HP)

    def _spicy_snappy(self) -> None:
        upgradable = self.run.upgradable_cards()
        if upgradable:
            self.rng.choice(upgradable).upgrade()

    def _jelly_liver(self) -> None:
        for card in self.run.select_cards("transform", self.run.transformable_cards(), 1):
            self.run.transform_card(card)

    def _fried_eel(self) -> None:
        # ColorlessCardPool has no sim equivalent; approximate with a random
        # character-pool card.
        for card in random_pool_cards(self.rng, 1):
            self.run.add_card(card)

    def _suspicious_condiment(self) -> None:
        if len(self.run.potions) < self.run.MAX_POTIONS:
            self.run.add_potion(self.run.random_potion())

    def _clam_roll(self) -> None:
        self.run.heal(_CLAM_ROLL_HEAL)

    def _golden_fysh(self) -> None:
        self.run.gain_gold(_GOLDEN_FYSH_GOLD)

    def _seapunk_salad(self) -> None:
        self.run.add_card(make_card("feeding_frenzy"))

    # ── Options ──────────────────────────────────────────────────────────

    def _grab_option(self) -> EventOption:
        # Locked unless the player can pay the 40-gold grab cost (checked even
        # for the free Golden Fysh, mirroring the source).
        if self.run.gold >= _GRAB_COST:
            return EventOption(self.current_dish_id, self._grab)
        return EventOption("LOCKED", None)

    def initial_options(self) -> list[EventOption]:
        return [
            self._grab_option(),
            EventOption("OBSERVE_CHEF", self._observe_chef),
        ]

    def _grab(self) -> None:
        if self.current_dish_id != "GOLDEN_FYSH":
            self.run.lose_gold(_GRAB_COST)
        self._current_action()
        self._roll_dish()
        self._set_state(
            "GRAB_SOMETHING_OFF_THE_BELT",
            [self._grab_option(), EventOption("LEAVE", self._leave)],
        )

    def _observe_chef(self) -> None:
        upgradable = self.run.upgradable_cards()
        if upgradable:
            self.rng.choice(upgradable).upgrade()
        self._finish("OBSERVE_CHEF")

    def _leave(self) -> None:
        self._finish("LEAVE")
