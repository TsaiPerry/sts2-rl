"""Event base classes and registry, mirroring STS2's EventModel/EventOption
(src/Core/Models/EventModel.cs, src/Core/Events/EventOption.cs).

An Event is constructed over a RunState and driven headlessly:

    run = RunState(rng=random.Random(0))
    event = make_event("wellspring", run)
    event.begin()                 # CalculateVars + initial options
    event.choose("BOTTLE")        # option keys mirror the source loc keys
    assert event.finished

Pages mirror the game's loc structure: every event starts on the "INITIAL"
page; choosing an option either finishes the event on a result page
(SetEventFinished) or moves to a new page with new options (SetEventState).
`event.page` always names the page whose description the player would be
reading. Locked options (a null onChosen in the game, e.g. Luminous Choir's
unaffordable tribute) are present but cannot be chosen.

Events that start a fight (Dense Vegetation) set `pending_encounter`; the
caller runs it via `run.create_combat(event.pending_encounter)` — mirroring
EnterCombatWithoutExitingEvent, which hands the encounter to the room system.

Deck choices go through `run.select_cards(purpose, candidates, count)` — the
headless stand-in for the game's card selection screens (CardSelectCmd),
random by default and overridable via RunState.card_selector.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..monsters import Encounter
    from ..run import RunState


_EVENT_CLASSES: dict[str, type[Event]] = {}


def register_event(cls: type[Event]) -> type[Event]:
    _EVENT_CLASSES[cls.id] = cls
    return cls


def make_event(event_id: str, run: RunState) -> Event:
    return _EVENT_CLASSES[event_id](run)


class EventOption:
    """One choice on an event page (mirrors EventOption).

    key mirrors the source's loc option name ("EAT", "TRUDGE_ON", ...).
    on_chosen is None for locked options (EventOption with a null onChosen).
    """

    def __init__(self, key: str, on_chosen: Callable[[], None] | None) -> None:
        self.key = key
        self.on_chosen = on_chosen

    @property
    def locked(self) -> bool:
        return self.on_chosen is None

    def __repr__(self) -> str:
        return f"{self.key}{' (locked)' if self.locked else ''}"


class Event:
    """Base class for all events (mirrors EventModel)."""

    id: str
    name: str

    def __init__(self, run: RunState) -> None:
        self.run = run
        # The game gives each event its own RNG seeded from the run seed +
        # event id; the sim keeps its single-RNG-stream convention.
        self.rng = run.rng
        self.page = "INITIAL"
        self.finished = False
        self._options: list[EventOption] = []
        # Set when an option starts a combat (EnterCombatWithoutExitingEvent);
        # the caller enters it with run.create_combat(pending_encounter).
        self.pending_encounter: Encounter | None = None

    # ── Subclass surface ─────────────────────────────────────────────────

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        """Whether this event may be entered (mirrors EventModel.IsAllowed).
        Gates use the same canonical values as the source."""
        return True

    def calculate_vars(self) -> None:
        """Roll per-visit dynamic values (mirrors EventModel.CalculateVars)."""

    def initial_options(self) -> list[EventOption]:
        """The INITIAL page's options (mirrors GenerateInitialOptions)."""
        raise NotImplementedError

    # ── Lifecycle ────────────────────────────────────────────────────────

    def begin(self) -> Event:
        """Mirrors BeginEvent: roll vars, then present the initial page."""
        self.calculate_vars()
        self._set_state("INITIAL", self.initial_options())
        return self

    @property
    def options(self) -> list[EventOption]:
        return list(self._options)

    def option_keys(self) -> list[str]:
        return [opt.key for opt in self._options]

    def choose(self, option: int | str) -> bool:
        """Choose an option by index or key. Returns False for unknown or
        locked options (the game renders those unclickable)."""
        if self.finished:
            return False
        if isinstance(option, str):
            matches = [o for o in self._options if o.key == option]
            if not matches:
                return False
            opt = matches[0]
        else:
            if option < 0 or option >= len(self._options):
                return False
            opt = self._options[option]
        if opt.locked:
            return False
        opt.on_chosen()
        return True

    # ── State transitions (SetEventState / SetEventFinished) ────────────

    def _set_state(self, page: str, options: list[EventOption]) -> None:
        self.page = page
        self._options = list(options)
        if not self._options:
            self.finished = True

    def _finish(self, page: str) -> None:
        """Mirrors SetEventFinished: land on a result page with no options."""
        self._set_state(page, [])

    def __repr__(self) -> str:
        state = "finished" if self.finished else f"page={self.page}"
        return f"{self.name} ({state})"
