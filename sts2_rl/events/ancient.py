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

    def _relic_option(self, relic_id: str) -> EventOption:
        """An option whose key is the relic id; choosing it obtains the relic
        (AfterObtained runs via RunState.add_relic) and finishes the event —
        mirrors AncientEventModel.RelicOption<T>()."""
        from ..relics import make_relic

        def on_chosen() -> None:
            self.run.add_relic(make_relic(relic_id))
            self._finish("DONE")

        return EventOption(relic_id, on_chosen)
