"""Ancient shrine events — the act-start relic offers (mirrors STS2's
AncientEventModel, src/Core/Models/Events/{Neow,Orobas,Pael,Tezcatara,
Nonupeipe,Tanx,Vakuu}.cs).

Each act begins at an "Ancient" map node (MapPointType.ANCIENT) whose event
offers a small set of relic options; choosing one obtains the relic (its
AfterObtained pickup effect runs) and finishes the event. Act 1 is always Neow;
Act 2 (Hive) rolls one of Orobas / Pael / Tezcatara; Act 3 (Glory) rolls one of
Nonupeipe / Tanx / Vakuu. The driver fires the chosen ancient at act entry
(RunDriver.play).

This base factors the shared "offer relics, grant on choose" shape out of the
per-ancient GenerateInitialOptions logic; subclasses implement
`initial_options()`.
"""
from __future__ import annotations

from .base import Event, EventOption


class AncientEvent(Event):
    """Base for act-start Ancient shrines (mirrors AncientEventModel)."""

    def begin(self) -> Event:
        # AncientEventModel.BeforeEventStarted: entering any Ancient heals
        # the player to full (amount = MaxHp - CurrentHp via CreatureCmd.Heal)
        # — this is the game's between-acts heal. Neow first zeroes HP (the
        # run-start revive animation), which at non-ascension nets the same
        # full heal, so the sim skips it. Weary Traveler (Asc 2,
        # AncientEventModel.cs:180-183) scales the DECIMAL amount to 80%
        # BEFORE the heal — `if (HasAscension(WearyTraveler)) amount *=
        # 0.8m; await CreatureCmd.Heal(creature, amount, ...)` — so the gate
        # sits here, not inside heal()'s int() truncation (RunState.heal
        # already truncates toward zero via `int(amount)`, matching the
        # C# decimal->int cast the game's Heal command performs).
        from ..actmap import AscensionLevel

        amount = self.run.max_hp - self.run.hp
        if self.run.has_ascension(AscensionLevel.WEARY_TRAVELER):
            amount *= 0.8
        self.run.heal(amount)
        return super().begin()

    def _relic_option(self, relic_id: str) -> EventOption:
        """An option whose key is the relic id; choosing it obtains the relic
        (AfterObtained runs via RunState.add_relic) and finishes the event —
        mirrors AncientEventModel.RelicOption<T>()."""
        from ..relics import make_relic

        def on_chosen() -> None:
            self.run.add_relic(make_relic(relic_id))
            self._finish("DONE")

        return EventOption(relic_id, on_chosen)
