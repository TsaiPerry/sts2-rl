"""Darv — the SHARED Ancient, eligible at any act after the first.

Port of Darv.cs GenerateInitialOptions. Unlike the per-act shrines, Darv
lives in UnlockState.SharedAncients: RunManager.GenerateRooms shuffles that
list and partitions it across acts 2..N, and each act rolls its shrine from
`its own ancients ∪ its shared subset` (ActModel.GenerateRooms).

Options are built from `_validRelicSets` — one relic picked per set whose
filter passes, unstable-shuffled, then either the first 3, or (on a coin
flip) the first 2 plus Dusty Tome:

  always:  Astrolabe, Black Star, Calling Bell, Empty Cage, Pandora's Box,
           Runic Pyramid, Snecko Eye
  act 2:   Ectoplasm | Sozu
  act 3:   Philosopher's Stone | Velvet Choker

Pandora's Box's own set is filtered on "no run modifier clears the deck",
which no ported modifier does, so it is always eligible here.
"""
from __future__ import annotations

from .ancient import AncientEvent
from .base import EventOption, register_event

# Darv._validRelicSets, in source order. Each entry is (act filter, relics):
# act_index None = always eligible.
_RELIC_SETS: tuple[tuple[int | None, tuple[str, ...]], ...] = (
    (None, ("astrolabe",)),
    (None, ("black_star",)),
    (None, ("calling_bell",)),
    (None, ("empty_cage",)),
    (None, ("pandoras_box",)),
    (None, ("runic_pyramid",)),
    (None, ("snecko_eye",)),
    (1, ("ectoplasm", "sozu")),
    (2, ("philosophers_stone", "velvet_choker")),
)


@register_event
class DarvEvent(AncientEvent):
    id = "darv"
    name = "Darv"

    def initial_options(self) -> list[EventOption]:
        rng = self.rng
        picks = [
            rng.choice(relics)
            for act_index, relics in _RELIC_SETS
            if act_index is None or act_index == self.run.act_index
        ]
        # UnstableShuffle over the picked relics, then take 2 or 3.
        rng.shuffle(picks)
        if rng.random() < 0.5:          # Rng.NextBool()
            chosen = picks[:2]
            tome = self._dusty_tome_option()
            return [self._relic_option(rid) for rid in chosen] + [tome]
        return [self._relic_option(rid) for rid in picks[:3]]

    def _dusty_tome_option(self) -> EventOption:
        """DustyTome is rolled through SetupForPlayer before being offered, so
        the Ancient card it will grant is fixed when the option appears."""
        from ..relics import make_relic

        tome = make_relic("dusty_tome")
        tome.setup_for_player(self.run)

        def on_chosen() -> None:
            self.run.add_relic(tome)
            self._finish("DONE")

        return EventOption("dusty_tome", on_chosen)
